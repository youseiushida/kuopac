"""
KulineClient — the public entry point.

Design principles:
* GET-only operations require no warm-up
* The single CSRF preflight is deferred until the first POST
* Methods accept either a raw identifier (str) or a Book/BookDetail
* Multi-page navigation is exposed through SearchResult.next_page() / iter_all()
"""
from __future__ import annotations

import json
import re
import warnings
from typing import Iterable, Self

from . import _parse
from ._http import HttpSession
from .enums import (
    BoolOp,
    CiniiSort,
    DataType,
    FacetType,
    MediaType,
    Scope,
    SearchField,
    Sort,
    SupplementarySource,
)
from .errors import NotFoundError
from .models import (
    BibIdentifiers,
    BLStatusQuery,
    Book,
    BookDetail,
    FacetInfo,
    Holding,
    SearchResult,
    Supplementary,
)
from .query import SearchQuery


class KulineClient:
    """High-level client for the KULINE OPAC.

    Use it as a context manager::

        with KulineClient() as kuline:
            result = kuline.search("機械学習")
            for book in result.iter_all(max_pages=3):
                print(book.title)
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 30.0,
        _http: "HttpSession | None" = None,
    ):
        from ._http import DEFAULT_UA
        # ``_http`` is an injection point for tests (httpx.MockTransport) and
        # advanced consumers who want a custom session — leading underscore
        # marks it as internal.
        self._http = _http or HttpSession(
            user_agent=user_agent or DEFAULT_UA, timeout=timeout,
        )

    # ---- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # =====================================================================
    # SEARCH
    # =====================================================================

    def search(
        self,
        query: str | SearchQuery,
        *,
        scope: Scope = Scope.LOCAL,
        sort: Sort | CiniiSort | None = None,
        page_size: int = 20,
    ) -> SearchResult:
        """Run a search.

        Pass a bare string for a simple keyword search, or a :class:`SearchQuery`
        for full advanced control.
        """
        if isinstance(query, str):
            params = self._params_for_simple(query, scope=scope,
                                              sort=sort, page_size=page_size)
        else:
            params = self._params_for_advanced(query)
        r = self._http.get("/opac/opac_search/", params=params)
        result = _parse.parse_search_results(
            r.text,
            request_url=str(r.request.url),
            scope=(query.scope if isinstance(query, SearchQuery) else scope),
            page_start=1,
            page_size=(query.page_size if isinstance(query, SearchQuery) else page_size),
            sort=(int(query.sort) if isinstance(query, SearchQuery) and query.sort
                  else int(sort or Sort.YEAR_DESC)),
        )
        result._client = self
        return result

    def _params_for_simple(self, keyword: str, *, scope: Scope,
                            sort: Sort | CiniiSort | None, page_size: int) -> dict:
        return {
            "lang": "0", "amode": "2", "cmode": str(int(scope)),
            "smode": "0", "kywd": keyword,
            "index_amazon_s": "Books", "node_s": "",
        }

    def _params_for_advanced(self, q: SearchQuery) -> dict:
        params: dict[str, str | list[str]] = {
            "lang": "0", "amode": "2", "cmode": str(int(q.scope)),
            "smode": "1",
            "sort_exp": str(int(q.sort)),
            "disp_exp": str(q.page_size),
            "dpmc_exp": q.department,
        }

        if q.scope is Scope.LOCAL:
            for i, cond in enumerate(q.conditions, 1):
                params[f"kywd{i}_exp"] = cond.keyword
                params[f"con{i}_exp"] = cond.field.value
                if i >= 2:
                    params[f"op{i}_exp"] = cond.op.value
            if q.media_types:
                params["file_exp"] = [str(int(m)) for m in q.media_types]
            if q.year_from is not None:
                params["year1_exp"] = str(q.year_from)
            if q.year_to is not None:
                params["year2_exp"] = str(q.year_to)
            if q.country_code is not None:
                params["cntry_exp"] = str(q.country_code)
            if q.text_language is not None:
                params["txtl_exp"] = str(q.text_language)
            if q.classification is not None:
                params["cls_exp"] = str(q.classification)
            if q.library_collection:
                params["lib_exp"] = q.library_collection
        else:
            # CiNii (cmode=5) uses *_ciniibooks suffixed parameters.
            cinii_field_map = {
                SearchField.ANY: "default_ciniibooks",
                SearchField.TITLE: "titlekey_ja_ciniibooks",
                SearchField.TITLE_EXACT: "ftitlekey_ciniibooks",
                SearchField.AUTHOR: "alkey_ciniibooks",
                SearchField.PUBLISHER: "pubkey_ciniibooks",
                SearchField.SUBJECT: "shkey_ciniibooks",
                SearchField.ISBN: "isbn_ciniibooks",
                SearchField.ISSN: "issn_ciniibooks",
                SearchField.NCID: "ncid_ciniibooks",
            }
            for cond in q.conditions:
                param_name = cinii_field_map.get(cond.field)
                if param_name:
                    params[param_name] = cond.keyword
                else:
                    warnings.warn(
                        f"CiNii (cmode=5) does not support search field "
                        f"{cond.field.name!r}; condition {cond.keyword!r} dropped. "
                        f"Supported fields: "
                        f"{sorted(f.name for f in cinii_field_map)}.",
                        UserWarning,
                        stacklevel=3,
                    )
            if q.media_types:
                accepted = [m for m in q.media_types if int(m) in (1, 5)]
                dropped = [m for m in q.media_types if int(m) not in (1, 5)]
                if dropped:
                    warnings.warn(
                        f"CiNii (cmode=5) only accepts MediaType.BOOK and "
                        f"MediaType.SERIAL filters; dropped: "
                        f"{[m.name for m in dropped]}.",
                        UserWarning,
                        stacklevel=3,
                    )
                if accepted:
                    params["ciniibooks_file_exp"] = [str(int(m)) for m in accepted]
            if q.year_from is not None:
                params["year1_ciniibooks"] = str(q.year_from)
            if q.year_to is not None:
                params["year2_ciniibooks"] = str(q.year_to)
            params["sort_ciniibooks"] = str(int(q.sort))
            params["ciniibooks_disp"] = str(q.page_size)

        return params

    # =====================================================================
    # PAGINATION
    # =====================================================================

    def _page(self, prev: SearchResult, start: int) -> SearchResult:
        """Fetch a specific 1-based start offset using a prior opkey."""
        r = self._http.get("/opac/opac_search/", params={
            "lang": "0", "amode": "22", "opkey": prev.opkey,
            "start": str(start), "cmode": str(int(prev.scope)),
            "place": "", "list_disp": str(prev.page_size),
            "list_sort": str(prev.sort),
        })
        result = _parse.parse_search_results(
            r.text, request_url=str(r.request.url), scope=prev.scope,
            page_start=start, page_size=prev.page_size, sort=prev.sort,
        )
        result._client = self
        return result

    # =====================================================================
    # FACETS
    # =====================================================================

    def facets(self, result: SearchResult, types: Iterable[FacetType] = (FacetType.DATATYPE,
                                                                          FacetType.YEAR,
                                                                          FacetType.PUBLISHER,
                                                                          FacetType.SUBJECT)) -> dict[FacetType, FacetInfo]:
        """Fetch facet aggregates for a search result.

        These calls are independent and parallel-safe; the synchronous loop
        keeps the API simple — callers can swap in an async / threaded
        executor if they need it.
        """
        out: dict[FacetType, FacetInfo] = {}
        for ft in types:
            r = self._http.get("/opac/opac_facet/", params={
                "lang": "0", "opkey": result.opkey, "facet_type": ft.value,
                "amode": "2", "cmode": str(int(result.scope)),
                "place": "", "list_disp": str(result.page_size),
                "list_sort": str(result.sort),
            })
            out[ft] = _parse.parse_facet(r.text, facet_type=ft)
        return out

    def _refine(self, prev: SearchResult, facets: dict[str, str | list[str]]) -> SearchResult:
        """Apply one or more facet filters and re-run the search."""
        fc_vals: list[str] = []
        for ft, val in facets.items():
            if isinstance(val, list):
                fc_vals.extend(f"{ft}#@#{v}" for v in val)
            else:
                fc_vals.append(f"{ft}#@#{val}")
        r = self._http.get("/opac/opac_search/", params={
            "opkey": prev.opkey, "lang": "0", "amode": "23",
            "place": "", "list_disp": str(prev.page_size),
            "list_sort": str(prev.sort), "cmode": str(int(prev.scope)),
            "fc_val": fc_vals,
        })
        result = _parse.parse_search_results(
            r.text, request_url=str(r.request.url), scope=prev.scope,
            page_start=1, page_size=prev.page_size, sort=prev.sort,
        )
        result._client = self
        return result

    # =====================================================================
    # DETAIL
    # =====================================================================

    def detail(
        self,
        book_or_bibid: str | Book,
        *,
        scope: Scope | None = None,
    ) -> BookDetail:
        """Fetch the full bibliographic detail for a book.

        Accepts either a bibid string or a :class:`Book` from a search result.
        For CiNii records pass the ncid (or a CiNii :class:`Book`).

        ``scope`` overrides the scope inferred from a :class:`Book` — useful
        when you only have a bare identifier string and need to force the
        CiNii endpoint (e.g. ``kuline.detail("BD18537825", scope=Scope.CINII)``).
        """
        if isinstance(book_or_bibid, Book):
            effective_scope = scope if scope is not None else book_or_bibid.scope
            if effective_scope is Scope.CINII:
                return self._cinii_detail(
                    book_or_bibid.ncid or book_or_bibid.ids.primary_key()
                )
            bibid = book_or_bibid.bibid or book_or_bibid.ids.primary_key()
        else:
            if scope is Scope.CINII:
                return self._cinii_detail(book_or_bibid)
            bibid = book_or_bibid

        r = self._http.get("/opac/opac_details/", params={
            "lang": "0", "amode": "11", "bibid": bibid,
        })
        # KULINE responds with HTTP 200 for invalid bibids — the not-found
        # signal is the absence of the detail table.  Distinguishing this
        # from a genuine template-change ParseError lets callers handle the
        # former cleanly without losing diagnostic value for the latter.
        # See docs/opac-spec.md §4.6.
        if "book-title-trd" not in r.text:
            raise NotFoundError(f"bibid {bibid!r} not found in KULINE")
        return _parse.parse_detail(r.text, bibid=bibid)

    def _cinii_detail(self, ncid: str) -> BookDetail:
        r = self._http.get("/opac/opac_detail_ciniibooks/", params={
            "lang": "0", "amode": "11", "ncid": ncid,
        })
        if "book-title-trd" not in r.text:
            raise NotFoundError(f"ncid {ncid!r} not found in CiNii")
        return _parse.parse_detail(r.text, ncid=ncid)

    # =====================================================================
    # HOLDINGS  (POST → triggers lazy CSRF)
    # =====================================================================

    def holdings(self, books: Iterable[Book | BookDetail | str]) -> dict[str, list[Holding]]:
        """Fetch live holding info for one or more bibids in a single POST.

        Accepts :class:`Book`, :class:`BookDetail`, or plain bibid strings —
        anything that identifies a record.  Returns ``{bibid: [Holding, ...]}``.
        This is the only method in the library that requires a CSRF preflight;
        it is performed once, lazily, on first invocation.
        """
        rec: list[dict[str, str]] = []
        for b in books:
            if isinstance(b, (Book, BookDetail)):
                rec.append({
                    "bibid": b.ids.bibid or "",
                    "datatype": str(int(b.data_type)),
                    "fieldcd": "", "mtid": "",
                })
            else:  # str
                rec.append({"bibid": b, "datatype": str(int(DataType.BOOK)),
                            "fieldcd": "", "mtid": ""})

        r = self._http.post("/opac/opac_search_localhold/", data={
            "lang": "0", "place": "", "mdptid": "",
            "q_param": f"opkey=&start=&totalnum={len(rec)}&list_disp=20&list_sort=6",
            "rec": json.dumps(rec, ensure_ascii=False),
        })
        return _parse.parse_localhold_response(r.json())

    # =====================================================================
    # LIVE LOAN STATUS  (one GET per copy — explicit, never auto-fanned-out)
    # =====================================================================

    def fetch_status(self, holding_or_query: Holding | BLStatusQuery) -> str | None:
        """Fetch the live loan status text for one copy. **One HTTP request.**

        KULINE renders the holdings table with empty CONDITION cells and fills
        them in via per-copy AJAX (``opac_blstat``).  This method makes that
        single call for one Holding/BLStatusQuery and returns the resulting
        status text (e.g. ``"研究室"``, ``"貸出中"``, ``"返却期限 …"``), or
        ``None`` if the copy is on the shelf with no special status.

        This library intentionally does **not** call this automatically on
        ``load_holdings()`` so a typical "list page" workflow stays at one POST.
        """
        q = holding_or_query.status_query if isinstance(holding_or_query, Holding) else holding_or_query
        if q is None:
            return None
        r = self._http.get("/opac/opac_blstat/", params={
            "lang": "0",
            "phasecd": q.phasecd, "hldstat": q.hldstat, "lkcd": q.lkcd,
            "blipkey": q.blipkey, "prlndflg": q.prlndflg, "blcd": q.blcd,
            "odrno": q.odrno, "bbcd": q.bbcd, "contcd": q.contcd,
            "addmsg": q.addmsg,
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        text = " ".join(re.sub(r"<[^>]+>", " ", r.text).split())
        if isinstance(holding_or_query, Holding):
            holding_or_query.condition = text or None
        return text or None

    # =====================================================================
    # SUPPLEMENTARY CONTENT (synopsis + TOC, opt-in, one source per call)
    # =====================================================================

    def fetch_supplementary(
        self,
        target: Book | BookDetail | str,
        *,
        source: SupplementarySource = SupplementarySource.BOOKPLUS,
    ) -> Supplementary:
        """Fetch the synopsis (あらすじ) and table of contents (目次) for a book.

        **One HTTP request per call.**  The library never auto-merges this
        into :class:`BookDetail` — call this explicitly when you need it.

        Two sources are available; pick one per call:
          * :attr:`SupplementarySource.BOOKPLUS` — 日外アソシエーツ BookPlus.
            Has data for the majority of recently-acquired books.
          * :attr:`SupplementarySource.OPENBD` — openBD.  Usually empty for
            academic-library holdings; useful only as a fallback.

        ``target`` may be a :class:`Book`, :class:`BookDetail`, or a plain
        ISBN string.  When passing an ISBN string, ``bibid`` is sent as an
        empty value (KULINE still answers but with lower hit rate).
        """
        if isinstance(target, (Book, BookDetail)):
            ids = target.ids
            isbn = ids.isbn or ""
            bibid = ids.bibid or ""
        else:
            isbn = target
            bibid = ""

        if not isbn:
            # Both endpoints key off ISBN; without one they always return "no data".
            return Supplementary(source=source, empty=True)

        if source is SupplementarySource.BOOKPLUS:
            r = self._http.get("/opac/opac_bookplusinfo/", params={
                "isbn": isbn, "bibid": bibid, "lang": "0",
            }, headers={"X-Requested-With": "XMLHttpRequest"})
        else:  # OPENBD
            r = self._http.get("/opac/opac_openbdinfo/", params={
                "isbn": isbn, "bibid": bibid,
            }, headers={"X-Requested-With": "XMLHttpRequest"})

        return _parse.parse_supplementary(r.text, source=source)

    # =====================================================================
    # SUGGESTIONS / SPELLCHECK
    # =====================================================================

    def suggest(self, term: str) -> list[str]:
        """Return autocomplete suggestions for a partial keyword."""
        r = self._http.get("/opac/opac_suggest/", params={"q_word": term})
        try:
            return list(r.json())
        except json.JSONDecodeError:
            return []

    def did_you_mean(self, result: SearchResult) -> list[str]:
        """Return spell-correction candidates for a search that had few hits."""
        r = self._http.get("/opac/opac_spellcheck/", params={
            "lang": "0", "opkey": result.opkey, "srvce": "0", "tikey": "",
        })
        return [c.term for c in _parse.parse_spellcheck(r.text)]
