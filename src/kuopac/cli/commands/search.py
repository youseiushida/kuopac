"""``kuopac search`` — keyword and advanced search.

Maps every CLI flag onto either a :class:`SearchQuery` condition or filter, then
delegates to :class:`KulineClient`.  Supports ``--all`` page walking with
streaming NDJSON output, ``--with holdings`` (one POST per page), and
``--refine`` post-search facet narrowing.
"""
from __future__ import annotations

import json
import sys
from typing import Annotated, Iterable, Optional

import typer

from ...client import KulineClient
from ...enums import (
    BoolOp,
    CiniiSort,
    MediaType,
    Scope,
    SearchField,
    Sort,
)
from ...models import SearchResult
from ...query import SearchQuery
from .._listflag import split_list_flag
from ..config import RunConfig
from ..errors import CliError
from ..formatters import listing, single, write
from ..formatters._serialize import to_jsonable
from ..runtime import build_client

_MEDIA_ALIASES: dict[str, MediaType] = {
    "book": MediaType.BOOK,
    "book-ja": MediaType.BOOK_JA,
    "book-en": MediaType.BOOK_EN,
    "serial": MediaType.SERIAL,
    "serial-ja": MediaType.SERIAL_JA,
    "serial-en": MediaType.SERIAL_EN,
    "ebook": MediaType.EBOOK,
    "ejournal": MediaType.EJOURNAL,
    "rare-image": MediaType.RARE_IMAGE,
    "thesis": MediaType.THESIS,
}

_SORT_ALIASES: dict[str, Sort] = {
    "relevance": Sort.RELEVANCE,
    "title-asc": Sort.TITLE_ASC,
    "title-desc": Sort.TITLE_DESC,
    "author-asc": Sort.AUTHOR_ASC,
    "author-desc": Sort.AUTHOR_DESC,
    "year-asc": Sort.YEAR_ASC,
    "year-desc": Sort.YEAR_DESC,
}

_CINII_SORT_ALIASES: dict[str, CiniiSort] = {
    "relevance": CiniiSort.RELEVANCE,
    "year-asc": CiniiSort.YEAR_ASC,
    "year-desc": CiniiSort.YEAR_DESC,
    "holdings-asc": CiniiSort.HOLDINGS_ASC,
    "holdings-desc": CiniiSort.HOLDINGS_DESC,
    "title-asc": CiniiSort.TITLE_ASC,
    "title-desc": CiniiSort.TITLE_DESC,
}

_BOOL_OP_ALIASES: dict[str, BoolOp] = {
    "AND": BoolOp.AND, "OR": BoolOp.OR, "NOT": BoolOp.NOT,
    "and": BoolOp.AND, "or": BoolOp.OR, "not": BoolOp.NOT,
}

_FIELD_FLAGS = (
    ("title", SearchField.TITLE),
    ("title_exact", SearchField.TITLE_EXACT),
    ("author", SearchField.AUTHOR),
    ("publisher", SearchField.PUBLISHER),
    ("subject", SearchField.SUBJECT),
    ("isbn", SearchField.ISBN),
    ("issn", SearchField.ISSN),
    ("ncid", SearchField.NCID),
    ("bibid", SearchField.BIB_ID),
    ("call_no", SearchField.CALL_NO),
)

# ``--field NAME=VALUE`` accepts both wire codes (titlekey_ja, pubkey, ...)
# and the friendly names used by dedicated flags (title, publisher, ...).
# Built from ``_FIELD_FLAGS`` plus dashed variants so ``--field title-exact=X``
# also resolves.
_FIELD_NAME_ALIASES: dict[str, SearchField] = {
    name: field for name, field in _FIELD_FLAGS
}
_FIELD_NAME_ALIASES.update({
    name.replace("_", "-"): field for name, field in _FIELD_FLAGS
})


def _resolve_field_name(name: str) -> SearchField | None:
    """Resolve a ``--field NAME=`` to a :class:`SearchField`, or ``None``.

    Tries (1) friendly alias (``publisher`` / ``title-exact``), then (2) wire
    code (``pubkey`` / ``ftitlekey``).  Case-insensitive on the alias side,
    case-sensitive on the wire code (KULINE's codes are lowercase).
    """
    key = name.strip()
    if not key:
        return None
    alias = _FIELD_NAME_ALIASES.get(key.lower())
    if alias is not None:
        return alias
    try:
        return SearchField(key)
    except ValueError:
        return None


def _parse_year_range(spec: str | None) -> tuple[int | None, int | None]:
    if not spec:
        return (None, None)
    if "-" in spec:
        a, _, b = spec.partition("-")
        return (
            int(a) if a.strip() else None,
            int(b) if b.strip() else None,
        )
    n = int(spec)
    return (n, n)


def _parse_refine(refine_args: list[str]) -> dict[str, str | list[str]]:
    """Flatten ``--refine key=val,key2=val2`` (possibly repeated) into a dict.

    Repeated values for the same key collapse to a list — KULINE accepts
    multiple ``fc_val`` values for the same facet type.
    """
    bucket: dict[str, list[str]] = {}
    for raw in refine_args:
        for pair in raw.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise CliError("INVALID_ARGUMENT", f"--refine entry not k=v: {pair!r}")
            k, _, v = pair.partition("=")
            bucket.setdefault(k.strip(), []).append(v.strip())
    return {k: (vs[0] if len(vs) == 1 else vs) for k, vs in bucket.items()}




def _build_query(
    *,
    keyword: str | None,
    fields_kv: dict[str, str | None],
    extra_fields: list[str],
    op: BoolOp,
    scope: Scope,
    media: list[str],
    year: str | None,
    year_from: int | None,
    year_to: int | None,
    country: int | None,
    language: int | None,
    classification: int | None,
    department: str,
    collection: str,
    sort: str | None,
    page_size: int,
) -> tuple[SearchQuery | str, bool]:
    """Build a :class:`SearchQuery` from CLI flags.

    Returns ``(query, is_simple)`` so the caller knows whether to use the
    string-mode (1 keyword + no advanced filter) path on the client.
    """
    advanced_used = any(fields_kv.values()) or extra_fields or media or year \
        or year_from is not None or year_to is not None or country is not None \
        or language is not None or classification is not None \
        or department != "all" or collection != "" or scope is Scope.CINII

    if not advanced_used and keyword and sort is None:
        return keyword, True

    q = SearchQuery(scope=scope)
    if keyword:
        q.any(keyword, op=op)
    for flag_name, field in _FIELD_FLAGS:
        val = fields_kv.get(flag_name)
        if val:
            q.add(field, val, op=op)
    for raw in extra_fields:
        if "=" not in raw:
            raise CliError("INVALID_ARGUMENT",
                           f"--field expects NAME=VALUE: {raw!r}")
        name, _, value = raw.partition("=")
        field = _resolve_field_name(name)
        if field is None:
            raise CliError("INVALID_ARGUMENT",
                           f"unknown search field: {name!r}")
        q.add(field, value.strip(), op=op)

    for m in media:
        m_lower = m.lower()
        if m_lower not in _MEDIA_ALIASES:
            raise CliError("INVALID_ARGUMENT", f"unknown media: {m!r}")
        q.media(_MEDIA_ALIASES[m_lower])

    yf, yt = _parse_year_range(year)
    if year_from is not None:
        yf = year_from
    if year_to is not None:
        yt = year_to
    if yf is not None or yt is not None:
        q.year_range(yf, yt)

    if country is not None:
        q.country_code = country
    if language is not None:
        q.text_language = language
    if classification is not None:
        q.classification = classification
    if department != "all":
        q.in_department(department)
    if collection:
        q.in_collection(collection)

    if sort:
        table = _CINII_SORT_ALIASES if scope is Scope.CINII else _SORT_ALIASES
        if sort not in table:
            raise CliError("INVALID_ARGUMENT", f"unknown sort: {sort!r}")
        q.sorted_by(table[sort])

    q.per_page(page_size)
    return q, False


def _run_search(
    kuline: KulineClient,
    *,
    query: SearchQuery | str,
    is_simple: bool,
    scope: Scope,
    sort: str | None,
    page_size: int,
    refine: dict[str, str | list[str]] | None,
) -> SearchResult:
    if is_simple:
        sort_enum: Sort | CiniiSort | None = None
        if sort:
            sort_enum = (_CINII_SORT_ALIASES if scope is Scope.CINII
                         else _SORT_ALIASES).get(sort)
        result = kuline.search(query, scope=scope, sort=sort_enum,
                               page_size=page_size)
    else:
        result = kuline.search(query)
    if refine:
        result = result.refine(**refine)
    return result


def _iter_pages(result: SearchResult, max_pages: int | None):
    """Walk pages until exhausted or the cap is hit (``max_pages=0`` = unlimited)."""
    page: SearchResult | None = result
    seen = 0
    while page is not None:
        yield page
        seen += 1
        if max_pages and seen >= max_pages:
            return
        page = page.next_page()


def _serialise_result(result: SearchResult) -> dict:
    return to_jsonable(result)


def register(app: typer.Typer) -> None:
    @app.command("search", help="KULINE で書誌検索 (簡易/詳細/他大学)")
    def search_cmd(
        ctx: typer.Context,
        keyword: Annotated[Optional[str], typer.Argument(help="フリーキーワード")] = None,
        title: Annotated[Optional[str], typer.Option("--title")] = None,
        title_exact: Annotated[Optional[str], typer.Option("--title-exact")] = None,
        author: Annotated[Optional[str], typer.Option("--author")] = None,
        publisher: Annotated[Optional[str], typer.Option("--publisher")] = None,
        subject: Annotated[Optional[str], typer.Option("--subject")] = None,
        isbn: Annotated[Optional[str], typer.Option("--isbn")] = None,
        issn: Annotated[Optional[str], typer.Option("--issn")] = None,
        ncid: Annotated[Optional[str], typer.Option("--ncid")] = None,
        bibid: Annotated[Optional[str], typer.Option("--bibid")] = None,
        call_no: Annotated[Optional[str], typer.Option("--call-no")] = None,
        extra_field: Annotated[
            Optional[list[str]],
            typer.Option(
                "--field",
                help="任意フィールド: NAME=VALUE "
                     "(NAME は title/publisher などの別名でも、"
                     "titlekey_ja/pubkey などの wire code でも可。"
                     "複数指定可: 繰り返し or カンマ区切り)",
            ),
        ] = None,
        op: Annotated[str, typer.Option("--op", help="AND|OR|NOT")] = "AND",
        scope_: Annotated[
            str, typer.Option("--scope", help="local | cinii"),
        ] = "local",
        media: Annotated[
            Optional[list[str]],
            typer.Option(
                "--media",
                help="メディア種別 (複数指定可: 繰り返し or カンマ区切り)",
            ),
        ] = None,
        year: Annotated[Optional[str], typer.Option("--year", help="2020-2024 または 2024")] = None,
        year_from: Annotated[Optional[int], typer.Option("--year-from")] = None,
        year_to: Annotated[Optional[int], typer.Option("--year-to")] = None,
        country: Annotated[Optional[int], typer.Option("--country")] = None,
        language_code: Annotated[
            Optional[int], typer.Option("--language", help="本文言語コード"),
        ] = None,
        classification: Annotated[
            Optional[int], typer.Option("--classification"),
        ] = None,
        department: Annotated[str, typer.Option("--department")] = "all",
        collection: Annotated[str, typer.Option("--collection")] = "",
        sort: Annotated[Optional[str], typer.Option("--sort")] = None,
        page_size: Annotated[int, typer.Option("--page-size", min=1)] = 20,
        start: Annotated[int, typer.Option("--start", min=1)] = 1,
        all_: Annotated[
            bool, typer.Option("--all", help="全ページ走査 (NDJSON 推奨)"),
        ] = False,
        max_pages: Annotated[
            int, typer.Option("--max-pages",
                              help="--all 時のページ数上限 (0=無制限)"),
        ] = 5,
        refine: Annotated[
            Optional[list[str]],
            typer.Option(
                "--refine",
                help="検索後ファセット適用: k=v "
                     "(複数指定可: 繰り返し or カンマ区切り)",
            ),
        ] = None,
        with_: Annotated[
            Optional[list[str]],
            typer.Option(
                "--with",
                help="追加情報 holdings "
                     "(複数指定可: 繰り返し or カンマ区切り)",
            ),
        ] = None,
        limit: Annotated[
            Optional[int],
            typer.Option("--limit", help="表示件数上限"),
        ] = None,
    ) -> None:
        cfg: RunConfig = ctx.obj

        op_enum = _BOOL_OP_ALIASES.get(op)
        if op_enum is None:
            raise CliError("INVALID_ARGUMENT", f"unknown --op: {op!r}")

        scope_lower = scope_.lower()
        if scope_lower not in ("local", "cinii"):
            raise CliError("INVALID_ARGUMENT", f"unknown --scope: {scope_!r}")
        scope = Scope.CINII if scope_lower == "cinii" else Scope.LOCAL

        fields_kv = {
            "title": title, "title_exact": title_exact, "author": author,
            "publisher": publisher, "subject": subject, "isbn": isbn,
            "issn": issn, "ncid": ncid, "bibid": bibid, "call_no": call_no,
        }
        media_tokens = split_list_flag(media)
        extra_field_tokens = split_list_flag(extra_field)
        query, is_simple = _build_query(
            keyword=keyword, fields_kv=fields_kv,
            extra_fields=extra_field_tokens,
            op=op_enum, scope=scope,
            media=media_tokens, year=year,
            year_from=year_from, year_to=year_to,
            country=country, language=language_code,
            classification=classification,
            department=department, collection=collection,
            sort=sort, page_size=page_size,
        )

        refine_map = _parse_refine(refine or [])
        with_set = set(split_list_flag(with_, lowercase=True))
        want_holdings = "holdings" in with_set
        invalid_with = with_set - {"holdings"}
        if invalid_with:
            raise CliError(
                "INVALID_ARGUMENT",
                f"--with {sorted(invalid_with)} not supported on search; "
                "use 'detail --with' for synopsis/live-status",
            )

        max_pages_arg = None if max_pages == 0 else max_pages
        ndjson_stream = cfg.format == "ndjson" and (all_ or want_holdings)

        with build_client(cfg) as kuline:
            initial = _run_search(
                kuline, query=query, is_simple=is_simple,
                scope=scope, sort=sort, page_size=page_size,
                refine=refine_map,
            )
            if start > 1:
                initial = initial.start_at(start)

            if not all_:
                if want_holdings:
                    initial.load_holdings()
                if limit is not None:
                    initial.books = initial.books[:limit]
                _emit(initial, cfg, ndjson_stream=ndjson_stream)
                _enforce_strict(cfg, initial.total)
                return

            # --all: page-walk; in NDJSON we stream each book as we see it.
            total = initial.total
            emitted = 0
            if ndjson_stream:
                for page in _iter_pages(initial, max_pages_arg):
                    if want_holdings:
                        page.load_holdings()
                    for book in page.books:
                        if limit is not None and emitted >= limit:
                            _enforce_strict(cfg, total)
                            return
                        _emit_book_line(book, cfg)
                        emitted += 1
                _enforce_strict(cfg, total)
                return

            # Non-NDJSON --all: aggregate books into one envelope.
            all_books = []
            opkey = initial.opkey
            sort_code = initial.sort
            for page in _iter_pages(initial, max_pages_arg):
                if want_holdings:
                    page.load_holdings()
                all_books.extend(page.books)
                if limit is not None and len(all_books) >= limit:
                    all_books = all_books[:limit]
                    break
            aggregated = SearchResult(
                books=all_books, total=total, opkey=opkey,
                scope=initial.scope, page_start=1,
                page_size=initial.page_size, sort=sort_code,
                query_summary=initial.query_summary,
                raw_url=initial.raw_url,
            )
            _emit(aggregated, cfg)
            _enforce_strict(cfg, total)


def _emit(result: SearchResult, cfg: RunConfig, *, ndjson_stream: bool = False) -> None:
    if ndjson_stream:
        for book in result.books:
            _emit_book_line(book, cfg)
        return
    envelope = single("SearchResult", to_jsonable(result), meta=cfg.meta())
    write(envelope, cfg)


def _emit_book_line(book, cfg: RunConfig) -> None:
    """NDJSON streaming: write one book at a time to stdout."""
    data = to_jsonable(book)
    # honour --fields by treating the item as a list-of-one for projection
    if cfg.fields:
        from ..projection import parse_fields, project
        paths = parse_fields(",".join(cfg.fields))
        data = project(data, paths)
    json.dump(data, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _enforce_strict(cfg: RunConfig, total: int) -> None:
    if cfg.strict and total == 0:
        raise CliError("NO_HITS", "no hits")
