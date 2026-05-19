"""
Data classes returned by the KULINE client.

These are deliberately split into a lightweight `Book` (parsed from result lists)
and a richer `BookDetail` (parsed from the detail page) so callers can iterate
search results without paying the cost of a detail fetch per record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator

from .enums import DataType, FacetType, Scope, SupplementarySource

if TYPE_CHECKING:
    from .client import KulineClient


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BibIdentifiers:
    """All identifiers known for one bibliographic record."""

    bibid: str | None = None        # KULINE local bib ID (e.g. BB08818020)
    ncid: str | None = None         # NACSIS-CAT ID (e.g. BD14456776)
    isbn: str | None = None
    issn: str | None = None
    nbn: str | None = None          # 全国書誌番号 (e.g. JP24215802)

    def primary_key(self) -> str:
        """The key used to fetch the detail page for this record."""
        if self.bibid:
            return self.bibid
        if self.ncid:
            return self.ncid
        raise ValueError("record has neither bibid nor ncid")


# ---------------------------------------------------------------------------
# Lightweight book record (search result item)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Book:
    """One record as seen in a search-result list.

    Only the fields shown in the list HTML + the inline JSON seed are populated.
    Call :meth:`KulineClient.detail` to enrich into a :class:`BookDetail`.
    Call ``SearchResult.load_holdings()`` to populate :attr:`holdings` in bulk
    (one POST for the whole page).
    """

    ids: BibIdentifiers
    title: str                          # raw title line including responsibility
    publisher_line: str                 # "place : publisher , year" (raw)
    data_type: DataType                 # 10=book, 19=ebook ...
    detail_url: str                     # relative URL to the detail page
    list_index: int                     # 1-based ordinal in the result page
    scope: Scope                        # local vs cinii (affects detail_url shape)

    # Filled by SearchResult.load_holdings(); empty list before then.
    holdings: list["Holding"] = field(default_factory=list)

    @property
    def bibid(self) -> str | None:
        return self.ids.bibid

    @property
    def ncid(self) -> str | None:
        return self.ids.ncid

    @property
    def has_holdings_loaded(self) -> bool:
        return bool(self.holdings)

    def __repr__(self) -> str:
        key = self.bibid or self.ncid or "?"
        return f"Book({key} {self.title[:40]!r})"


# ---------------------------------------------------------------------------
# Detail-page record
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AuthorHeading:
    """One row of the AHDNG (著者標目) field."""

    name: str
    kana: str | None = None
    role: str | None = None             # 著者 / 編 / 訳 etc.
    auid: str | None = None             # Authority ID (AU########)


@dataclass(slots=True)
class Subject:
    """One subject heading entry (BBSUBJECT row)."""

    scheme: str                         # e.g. BSH, NDLSH
    term: str


@dataclass(slots=True)
class Classification:
    """One classification entry (BBCLS row)."""

    scheme: str                         # NDC9, NDC10, NDLC ...
    code: str


@dataclass(slots=True)
class ParentSeries:
    """One PTBL entry (parent bibliography / series)."""

    title: str
    bibid: str | None = None


@dataclass(slots=True)
class ChildBib:
    """One row of the 子書誌情報 table on a series-parent detail page."""

    number: int                 # 1-based volume index in the series
    bibid: str | None
    title: str
    publication: str            # raw "place : publisher , yyyy"


@dataclass(slots=True)
class Publication:
    """Structured form of the raw publication / publisher line."""

    raw: str
    edition: str | None = None          # e.g. "第2版", "Ver.1.1", "4th ed."
    place: str | None = None            # primary place
    publisher: str | None = None        # primary publisher
    year: int | None = None
    series: str | None = None           # text inside trailing "(... ; vol)"


@dataclass(slots=True)
class RdaTypes:
    """RDA 表現種別/機器種別/キャリア種別 triplet extracted from BBNOTE."""

    content: str | None = None          # 表現種別 (e.g. "テキスト")
    media: str | None = None            # 機器種別 (e.g. "機器不用")
    carrier: str | None = None          # キャリア種別 (e.g. "冊子")


@dataclass(slots=True)
class ExternalLinks:
    """Out-bound search links shown on the detail page sidebar."""

    permalink: str | None = None
    cinii: str | None = None
    ndl: str | None = None
    google: str | None = None
    google_books: str | None = None
    google_scholar: str | None = None


@dataclass(slots=True)
class BookDetail:
    """Full bibliographic record from /opac/opac_details/."""

    ids: BibIdentifiers
    title: str
    title_kana: str | None
    title_main: str | None             # title before " / " separator
    responsibility: str | None         # text after " / " in title (著/編/訳 statement)
    data_type: DataType
    publication: Publication            # structured form of PUBLICATION
    language: str | None
    alt_titles: list[str] = field(default_factory=list)
    physical_description: str | None = None     # PHYS
    volume_info: str | None = None              # BBVOLG raw
    volume_info_parts: dict[str, str] = field(default_factory=dict)  # BBVOLG parsed
    notes: str | None = None                    # BBNOTE raw
    rda_types: RdaTypes = field(default_factory=RdaTypes)
    authors: list[AuthorHeading] = field(default_factory=list)
    subjects: list[Subject] = field(default_factory=list)
    classifications: list[Classification] = field(default_factory=list)
    parent_series: list[ParentSeries] = field(default_factory=list)
    children: list[ChildBib] = field(default_factory=list)   # 子書誌情報
    external_links: ExternalLinks = field(default_factory=ExternalLinks)
    holdings: list[Holding] = field(default_factory=list)
    raw_fields: dict[str, str] = field(default_factory=dict)
    """All `<th class="CODE">` rows verbatim, including ones not normalised above."""

    @property
    def bibid(self) -> str | None:
        return self.ids.bibid

    @property
    def ncid(self) -> str | None:
        return self.ids.ncid

    @property
    def isbn(self) -> str | None:
        return self.ids.isbn


# ---------------------------------------------------------------------------
# Holdings (one physical / electronic copy)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BLStatusQuery:
    """Parameters needed to query live loan status for one physical copy.

    KULINE renders the holdings table with empty CONDITION cells and then runs
    AJAX (`opac_blstat`) per row to fill them in.  We expose these parameters
    on the Holding so callers can choose to make that extra request only when
    they actually need the live status — keeping the default flow at 1 POST.
    """

    blipkey: str                        # primary key (e.g. "BL19200695")
    phasecd: str = "50"
    hldstat: str = "1"
    lkcd: str = "1"
    prlndflg: str = "0"
    blcd: str = "1"
    odrno: str = ""                     # order number, e.g. "OT00477489"
    bbcd: str = "1"
    contcd: str = ""
    addmsg: str = "返却期限"


@dataclass(slots=True)
class Holding:
    """One copy of a book — physical shelf, online access, or other-uni holding."""

    volume: str | None = None
    location: str | None = None         # e.g. "情報学||図書室" or "電子ブック"
    call_no: str | None = None          # e.g. "007.1||FIX 1||3"
    barcode: str | None = None          # 資料番号
    blkey: str | None = None            # internal copy key (for reservations)
    condition: str | None = None        # live status text (may be empty unless explicitly fetched)
    comments: str | None = None
    online_url: str | None = None       # set when this is an e-resource
    online_label: str | None = None     # e.g. "eBook", "リンク"
    library_floor_pdf: str | None = None

    # Set when `condition` can be refreshed via opac_blstat. Empty CONDITION
    # in localhold means "available" only after this query is actually made.
    status_query: BLStatusQuery | None = None

    # CiNii (other-university) holdings use a different column shape
    institution: str | None = None      # e.g. "神戸大学 附属図書館 ..."
    cinii_orderno: str | None = None    # CiNii column "orderno"
    cinii_rgtn: str | None = None       # CiNii column "rgtn" (registration no.)

    @property
    def is_online(self) -> bool:
        return self.online_url is not None

    @property
    def is_remote_university(self) -> bool:
        return self.institution is not None

    @property
    def availability(self) -> str:
        """Cheap, non-fetching availability hint based on what we already know.

        Returns:
          * "online" — e-resource with proxy login URL
          * "remote" — held by another university (CiNii result)
          * "available_on_shelf" — physical copy with no live status loaded
            (the OPAC populates this only via opac_blstat; this library does
            NOT auto-fetch it).  Use `KulineClient.fetch_status(holding)` to
            confirm.
          * "<status_text>" — when `condition` has been explicitly populated
        """
        if self.condition:
            return self.condition
        if self.is_online:
            return "online"
        if self.is_remote_university:
            return "remote"
        return "available_on_shelf"


# ---------------------------------------------------------------------------
# Search result page
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SearchResult:
    """One page of search results.

    Iterating the object yields :class:`Book` instances.  Use :meth:`iter_all`
    to walk every page transparently.
    """

    books: list[Book]
    total: int
    opkey: str                          # server-side search-session key
    scope: Scope
    page_start: int                     # 1-based "start" of this page
    page_size: int
    sort: int                           # raw sort code; cast to enum at call site
    query_summary: str                  # 検索キーワード:(...) — verbatim
    raw_url: str                        # URL of the request that produced this page

    # The client reference is set after construction so the result can navigate.
    _client: "KulineClient | None" = field(default=None, repr=False)

    def __iter__(self) -> Iterator[Book]:
        return iter(self.books)

    def __len__(self) -> int:
        return len(self.books)

    # ---- pagination -------------------------------------------------------

    def has_next(self) -> bool:
        return self.page_start - 1 + len(self.books) < self.total

    def next_page(self) -> "SearchResult | None":
        """Fetch the next page, or return None if exhausted."""
        if self._client is None:
            raise RuntimeError("SearchResult is detached from its client")
        if not self.has_next():
            return None
        return self._client._page(self, self.page_start + self.page_size)

    def iter_all(self, *, max_pages: int | None = None) -> Iterator[Book]:
        """Yield every book across pages until exhausted or `max_pages` reached."""
        page: SearchResult | None = self
        n = 0
        while page is not None:
            yield from page.books
            n += 1
            if max_pages is not None and n >= max_pages:
                return
            page = page.next_page()

    # ---- refinement -------------------------------------------------------

    def refine(self, **facets: str | list[str]) -> "SearchResult":
        """Re-search with one or more facet filters applied.

        Example::

            r2 = result.refine(datatype="10", publisher="丸善出版")
        """
        if self._client is None:
            raise RuntimeError("SearchResult is detached from its client")
        return self._client._refine(self, facets)

    # ---- holdings enrichment (single POST) -------------------------------

    def load_holdings(self) -> "SearchResult":
        """Populate `book.holdings` for every book on this page with **one** POST.

        Calls ``/opac/opac_search_localhold/`` once with all bibids on the
        current page and attaches the parsed Holding lists to each Book in
        place.  Returns self for chaining.

        The live "貸出中 / 返却期限 …" status is **not** included — KULINE
        delivers that through a separate per-copy AJAX (``opac_blstat``).  Use
        :meth:`KulineClient.fetch_status` on individual Holdings if you need
        the live status (each call is one extra GET).
        """
        if self._client is None:
            raise RuntimeError("SearchResult is detached from its client")
        local = [b for b in self.books if b.bibid]
        if not local:
            return self
        mapping = self._client.holdings(local)
        for b in self.books:
            if b.bibid and b.bibid in mapping:
                b.holdings = mapping[b.bibid]
        return self


# ---------------------------------------------------------------------------
# Facet aggregates
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FacetValue:
    """One bucket of a facet (e.g. publisher=丸善出版 count=8)."""

    value: str
    label: str
    count: int


@dataclass(slots=True)
class FacetInfo:
    """All facet buckets for a single facet type, for one search."""

    type: FacetType
    values: list[FacetValue]

    def top(self, n: int = 10) -> list[FacetValue]:
        return sorted(self.values, key=lambda v: -v.count)[:n]


# ---------------------------------------------------------------------------
# Suggestion / spellcheck
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Suggestion:
    """Sub-string suggestion from opac_suggest (autocomplete)."""

    term: str


@dataclass(slots=True)
class SpellCorrection:
    """One "did you mean" candidate from opac_spellcheck."""

    term: str
    search_url: str


# ---------------------------------------------------------------------------
# Supplementary content (synopsis + TOC from external DBs)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Supplementary:
    """Synopsis / table-of-contents fetched from BookPlus or openBD.

    These come from external suppliers (日外アソシエーツ BookPlus, openBD) and
    are only available for a fraction of academic-library holdings — most
    queries return :attr:`empty` ``= True``.

    Use :class:`KulineClient.fetch_supplementary` to obtain one of these.
    """

    source: SupplementarySource
    synopsis: str | None = None          # あらすじ — may be multi-line
    toc: list[str] = field(default_factory=list)  # 目次 — one entry per chapter/section
    raw_text: str = ""                   # full server text (HTML stripped)
    empty: bool = False                  # True if the server returned a "no data" message

    def __bool__(self) -> bool:
        return not self.empty
