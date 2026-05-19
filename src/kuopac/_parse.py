"""
HTML → models parsers.

Kept private to allow the parsing layer to evolve when KULINE changes its
templates.  All XPath/regex knowledge is concentrated here.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from lxml import html as lxml_html

from ._http import BASE_URL
from .enums import DataType, FacetType, Scope, SupplementarySource
from .errors import ParseError
from .models import (
    AuthorHeading,
    BibIdentifiers,
    BLStatusQuery,
    Book,
    BookDetail,
    ChildBib,
    Classification,
    ExternalLinks,
    FacetInfo,
    FacetValue,
    Holding,
    ParentSeries,
    Publication,
    RdaTypes,
    SearchResult,
    SpellCorrection,
    Subject,
    Supplementary,
)

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_RE_OPKEY = re.compile(r"(?:opkey=|name=['\"]opkey['\"]\s+value=['\"])(B\d+)")
_RE_HITS = re.compile(r"search-results-hits_num[^>]*>([^<]+)<")
_RE_NUM = re.compile(r"([\d,]+)")
_RE_SEED = re.compile(
    r"""img_out_link_list_all\([^,]+,\s*['"](?P<seed>\[\[.*?\]\])['"]""",
    re.DOTALL,
)
_RE_BIBID_NCID = re.compile(r"<(?P<bibid>[A-Z]{2}\d+)>\s*(?:\[(?P<ncid>[A-Z]{2}\d+)\])?")


def _int_from_text(s: str | None) -> int | None:
    if s is None:
        return None
    m = _RE_NUM.search(s)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


# ---------------------------------------------------------------------------
# Search results
# ---------------------------------------------------------------------------

def parse_search_results(body: str, *, request_url: str, scope: Scope,
                         page_start: int, page_size: int, sort: int) -> SearchResult:
    """Parse a search-results HTML page into :class:`SearchResult`."""
    tree = lxml_html.fromstring(body)

    # Total hit count: "該当件数:886件" / "該当件数:1,122件"
    hits_text = "".join(tree.xpath(
        "//p[contains(@class,'search-results-hits_num')]/text()"
    )).strip()
    total = _int_from_text(hits_text) or 0

    # opkey from any embedded URL or hidden input
    m = _RE_OPKEY.search(body)
    opkey = m.group(1) if m else ""

    # Search keyword summary
    summary = " ".join("".join(
        tree.xpath("//p[contains(@class,'current-search-key')]//text()")
    ).split())

    # Inline JSON seed gives isbn/ncid/nbn per record (the HTML alone omits ISBN)
    seed_by_bibid = {}
    sm = _RE_SEED.search(body)
    if sm:
        try:
            seeded = json.loads(sm.group("seed"))[0]
            seed_by_bibid = {rec["bibid"]: rec for rec in seeded if rec.get("bibid")}
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

    books: list[Book] = []
    items = tree.xpath("//ul[contains(@class,'result-list')]/li")
    for i, li in enumerate(items, start=1):
        # Local result has hidden inputs; CiNii result doesn't.
        bibid_vals = li.xpath(".//input[@name='list_bibid']/@value")
        datatype_vals = li.xpath(".//input[@name='list_datatype']/@value")
        title_a = li.xpath(".//p[contains(@class,'result-book-title')]//a[contains(@href,'opac_detail')]")
        if not title_a:
            continue
        title = " ".join(title_a[0].text_content().split())
        href = title_a[0].get("href", "")

        # Extract NCID from CiNii detail URLs when no bibid is present
        ncid = None
        if not bibid_vals:
            q = parse_qs(urlparse(href).query)
            ncid = (q.get("ncid") or [None])[0]
        bibid = bibid_vals[0] if bibid_vals else None
        if bibid is None and "BB" in href:
            bm = re.search(r"bibid=([A-Z]{2}\d+)", href)
            bibid = bm.group(1) if bm else None

        data_type = DataType.parse(datatype_vals[0]) if datatype_vals else DataType.UNKNOWN
        publisher_line = " ".join(
            "".join(li.xpath(".//p[contains(@class,'result-book-publisher')]//text()")).split()
        )

        # ISBN/NCID/NBN from the inline JSON seed (when available)
        seed = seed_by_bibid.get(bibid or "", {})
        if not ncid:
            ncid = seed.get("ncid") or None

        # ncid may also appear inline as "<BBxxx> [NCID]" in book-type cell
        if not ncid:
            bt = " ".join(li.xpath(".//p[contains(@class,'book-type')]//text()"))
            bm = _RE_BIBID_NCID.search(bt)
            if bm:
                ncid = bm.group("ncid")

        ids = BibIdentifiers(
            bibid=bibid,
            ncid=ncid,
            isbn=seed.get("isbn") or None,
            nbn=seed.get("nbn") or None,
        )
        books.append(Book(
            ids=ids, title=title, publisher_line=publisher_line,
            data_type=data_type, detail_url=href,
            list_index=i, scope=scope,
        ))

    return SearchResult(
        books=books, total=total, opkey=opkey, scope=scope,
        page_start=page_start, page_size=page_size, sort=sort,
        query_summary=summary, raw_url=request_url,
    )


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------

_RE_PERMALINK = re.compile(
    re.escape(BASE_URL) + r"/opac/opac_link/bibid/[^\"']+",
)


def parse_detail(body: str, *, bibid: str | None = None,
                 ncid: str | None = None) -> BookDetail:
    """Parse /opac/opac_details/ or /opac/opac_detail_ciniibooks/ into BookDetail."""
    tree = lxml_html.fromstring(body)

    title_kana = "".join(tree.xpath(
        "//h2[contains(@class,'book-title')]//span[contains(@class,'book-title-kana')]/text()"
    )).strip() or None
    title = "".join(tree.xpath(
        "//h2[contains(@class,'book-title')]//span[contains(@class,'book-title-trd')]/text()"
    )).strip()
    if not title:
        raise ParseError("could not find <span class=book-title-trd>")

    raw_fields: dict[str, str] = {}
    raw_field_elems: dict[str, Any] = {}
    for tr in tree.xpath("//table[contains(@class,'book-detail-table')]//tr"):
        th = tr.xpath("./th")
        td = tr.xpath("./td")
        if not th or not td:
            continue
        code = (th[0].get("class") or "").split()[0]
        text = " ".join(td[0].text_content().split())
        # The detail HTML duplicates rows for PC + mobile; keep first occurrence.
        if code and code not in raw_fields:
            raw_fields[code] = text
            raw_field_elems[code] = td[0]

    # ---- Authors (AHDNG) ------------------------------------------------
    authors: list[AuthorHeading] = []
    ahdng_td = tree.xpath("//table[contains(@class,'book-detail-table')]//th[contains(@class,'AHDNG')]/following-sibling::td[1]")
    if ahdng_td:
        html_str = lxml_html.tostring(ahdng_td[0], encoding="unicode")
        for chunk in re.split(r"<br\s*/?>", html_str):
            sub = lxml_html.fragment_fromstring(chunk, create_parent="div")
            text_all = " ".join(sub.text_content().split())
            if not text_all:
                continue
            name_a = sub.xpath(".//a[contains(@href,'opac_search') or contains(@href,'opac_authority')]")
            if name_a:
                name = " ".join(name_a[0].text_content().split())
            else:
                # CiNii: no link; strip "<カナ>" off the right
                name = re.sub(r"\s*<[^<>]*>\s*$", "", text_all).strip()
                # Also strip role suffixes
                name = re.sub(r"\s*(著者|編集|編|訳|監修|著)\s*$", "", name).strip()
            auid = None
            if name_a and "opac_authority" in (name_a[0].get("href") or ""):
                m = re.search(r"auid=(AU\d+)", name_a[0].get("href"))
                if m:
                    auid = m.group(1)
            kana_m = re.search(r"<\s*([^<>]+?)\s*>\s*$", text_all)
            kana = kana_m.group(1).strip() if kana_m else None
            role_m = re.search(r"(著者|編集|編|訳|監修|著)", text_all.replace(name, "", 1))
            role = role_m.group(1) if role_m else None
            authors.append(AuthorHeading(name=name, kana=kana, role=role, auid=auid))

    # ---- Subjects (BBSUBJECT) -------------------------------------------
    subjects: list[Subject] = []
    if "BBSUBJECT" in raw_field_elems:
        for scheme, term in _split_scheme_value_rows(raw_field_elems["BBSUBJECT"]):
            subjects.append(Subject(scheme=scheme, term=term))

    # ---- Classifications (BBCLS) ----------------------------------------
    classifications: list[Classification] = []
    if "BBCLS" in raw_field_elems:
        for scheme, code in _split_scheme_value_rows(raw_field_elems["BBCLS"]):
            classifications.append(Classification(scheme=scheme, code=code))

    # ---- Parent series (PTBL) -------------------------------------------
    parents: list[ParentSeries] = []
    for a in tree.xpath("//span[@id='PTBL']//a"):
        href = a.get("href") or ""
        m = re.search(r"bibid=([A-Z]{2}\d+)", href)
        parents.append(ParentSeries(title=a.text_content().strip(),
                                    bibid=m.group(1) if m else None))

    # ---- External links --------------------------------------------------
    ext = ExternalLinks()
    for a in tree.xpath("//div[contains(@class,'panel-body')]//ul[contains(@class,'list-group')]//a"):
        href = a.get("href") or ""
        if "ci.nii.ac.jp" in href:
            ext.cinii = href
        elif "ndlsearch.ndl.go.jp" in href:
            ext.ndl = href
        elif "scholar.google" in href:
            ext.google_scholar = href
        elif "books.google" in href:
            ext.google_books = href
        elif "google.co.jp/search" in href:
            ext.google = href
    pm = _RE_PERMALINK.search(body)
    if pm:
        ext.permalink = pm.group(0)

    # ---- Identifiers -----------------------------------------------------
    isbn = raw_fields.get("BBISBN", "").split()[0] if raw_fields.get("BBISBN") else None
    ncid_val = raw_fields.get("NCID") or ncid

    # ---- Data type -------------------------------------------------------
    dt_label = raw_fields.get("DATATYPE", "")
    data_type = {"図書": DataType.BOOK, "電子ブック": DataType.EBOOK,
                 "雑誌": DataType.SERIAL}.get(dt_label, DataType.UNKNOWN)

    # ---- Holdings -------------------------------------------------------
    holdings = _parse_holdings_rows(tree)

    # ---- Child bibliographies (子書誌情報) -------------------------------
    children = _parse_child_bibs(tree)

    # ---- Title split: "main / responsibility" ---------------------------
    # KULINE detail uses ASCII " / "; CiNii detail uses NBSP " / ".
    title_normalized = title.replace(" ", " ")
    main, sep, resp = title_normalized.partition(" / ")
    title_main = main.strip() if sep else None
    responsibility = resp.strip() if sep else None

    # ---- Structured publication & BBVOLG --------------------------------
    pub_text = raw_fields.get("PUBLICATION") or raw_fields.get("PUBLISHER", "")
    publication = _parse_publication(pub_text, year_hint=raw_fields.get("PUBYEAR"))
    volume_info_parts = _parse_kv_semis(raw_fields.get("BBVOLG", ""))

    # ---- RDA triplet from BBNOTE ----------------------------------------
    rda = _parse_rda(raw_fields.get("BBNOTE", ""))

    return BookDetail(
        ids=BibIdentifiers(
            bibid=raw_fields.get("BBBIBID") or bibid,
            ncid=ncid_val,
            isbn=isbn,
        ),
        title=title,
        title_kana=title_kana,
        title_main=title_main,
        responsibility=responsibility,
        data_type=data_type,
        publication=publication,
        language=raw_fields.get("LANGUAGE"),
        alt_titles=[raw_fields["BBVT"]] if raw_fields.get("BBVT") else [],
        physical_description=raw_fields.get("PHYS"),
        volume_info=raw_fields.get("BBVOLG"),
        volume_info_parts=volume_info_parts,
        notes=raw_fields.get("BBNOTE"),
        rda_types=rda,
        authors=authors,
        subjects=subjects,
        classifications=classifications,
        parent_series=parents,
        children=children,
        external_links=ext,
        holdings=holdings,
        raw_fields=raw_fields,
    )


_RE_SCHEME_PAIR = re.compile(
    r"([A-Z][A-Z0-9]+):\s*(.+?)(?=\s*[A-Z][A-Z0-9]+:|\s*$)",
    re.DOTALL,
)


def _split_scheme_value_rows(td_elem: Any) -> list[tuple[str, str]]:
    """Split a `<td>` whose text concatenates multiple `SCHEME: value` rows.

    Schemes in KULINE are always 2+ uppercase/digit chars followed by a colon
    (BSH, NDLSH, NDC9, NDC10, NDLC, ...).  We rely on that to delimit them
    without needing the original HTML structure.
    """
    text = " ".join(td_elem.text_content().split())
    return [(s, v.strip()) for s, v in _RE_SCHEME_PAIR.findall(text)]


def _parse_holdings_rows(tree: Any) -> list[Holding]:
    """Extract holdings from a <table class=library-info-table2>.

    Supports both shapes:
    * Local KULINE: cells use LOCATION / CALLNO / BARCODE / CONDITION / etc.
    * CiNii (cmode=5): cells use institution / location / orderno / rgtn.
    """
    out: list[Holding] = []
    for tr in tree.xpath("//table[contains(@class,'library-info-table2')]//tr[contains(@class,'library-info-data')]"):
        def cell(cls: str) -> str | None:
            els = tr.xpath(f"./td[contains(@class,'{cls}')]")
            if not els:
                return None
            text = " ".join(els[0].text_content().split())
            return text or None

        # Detect shape by checking for CiNii-specific class
        if tr.xpath("./td[contains(@class,'institution')]"):
            out.append(Holding(
                institution=cell("institution"),
                location=cell("location"),
                cinii_orderno=cell("orderno"),
                cinii_rgtn=cell("rgtn"),
            ))
            continue

        # Local shape
        blkey = None
        bk_links = tr.xpath(".//a[contains(@href,'blkey=')]/@href")
        if bk_links:
            m = re.search(r"blkey=([A-Z]*\d+)", bk_links[0])
            if m:
                blkey = m.group(1)

        online_url = None
        online_label = None
        online_cells = tr.xpath(".//td[contains(@class,'ONLINE')]")
        if online_cells:
            online_a = online_cells[0].xpath(".//a/@href")
            if online_a:
                online_url = online_a[0]
            label_text = " ".join(online_cells[0].text_content().split())
            if label_text and label_text != "リンク":
                online_label = label_text

        floor_pdf = None
        floor_a = tr.xpath(".//td[contains(@class,'LOCATION')]//a/@href")
        if floor_a and floor_a[0].endswith(".pdf"):
            floor_pdf = floor_a[0]

        # Extract the AJAX dispStatName() args so callers can fetch live status later
        cond_html = lxml_html.tostring(tr, encoding="unicode")
        status_query = _parse_blstat_query(cond_html)

        out.append(Holding(
            volume=cell("VOLUME"),
            location=cell("LOCATION"),
            call_no=cell("CALLNO"),
            barcode=cell("BARCODE"),
            blkey=blkey,
            condition=_clean_condition(cell("CONDITION")),
            comments=cell("COMMENTS"),
            online_url=online_url,
            online_label=online_label,
            library_floor_pdf=floor_pdf,
            status_query=status_query,
        ))
    return out


def _parse_blstat_query(html_fragment: str) -> BLStatusQuery | None:
    m = _RE_DISP_STAT_ARGS.search(html_fragment)
    if not m:
        return None
    return BLStatusQuery(
        blipkey=m.group("blipkey"),
        phasecd=m.group("phasecd"),
        hldstat=m.group("hldstat"),
        lkcd=m.group("lkcd"),
        prlndflg=m.group("prlndflg"),
        blcd=m.group("blcd"),
        odrno=m.group("odrno"),
        bbcd=m.group("bbcd"),
        contcd=m.group("contcd"),
        addmsg=m.group("addmsg"),
    )


_RE_DISP_STAT_ARGS = re.compile(
    r"""dispStatName\s*\(\s*
        ['"](?P<url>[^'"]*)['"]\s*,\s*
        ['"](?P<phasecd>[^'"]*)['"]\s*,\s*
        ['"](?P<hldstat>[^'"]*)['"]\s*,\s*
        ['"](?P<lkcd>[^'"]*)['"]\s*,\s*
        ['"](?P<blipkey>[^'"]*)['"]\s*,\s*
        ['"](?P<prlndflg>[^'"]*)['"]\s*,\s*
        ['"](?P<blcd>[^'"]*)['"]\s*,\s*
        ['"](?P<odrno>[^'"]*)['"]\s*,\s*
        ['"](?P<bbcd>[^'"]*)['"]\s*,\s*
        ['"](?P<contcd>[^'"]*)['"]\s*,\s*
        ['"](?P<lang>[^'"]*)['"]\s*,\s*
        ['"](?P<addmsg>[^'"]*)['"]\s*,\s*
        ['"](?P<loadmsg>[^'"]*)['"]\s*
    \)""",
    re.VERBOSE,
)
_RE_DISP_STAT = re.compile(r"dispStatName\s*\([^)]*\);?\s*", re.DOTALL)
_RE_DISP_ILL = re.compile(r"dispInsideIll\w*\s*\([^)]*\);?\s*", re.DOTALL)
_RE_WAITING = re.compile(r"['\"]waiting\.\.\.['\"]")


def _clean_condition(text: str | None) -> str | None:
    """Strip the inline JS placeholder so empty CONDITION cells return None."""
    if text is None:
        return None
    cleaned = _RE_DISP_STAT.sub("", text)
    cleaned = _RE_DISP_ILL.sub("", cleaned)
    cleaned = _RE_WAITING.sub("", cleaned).strip()
    return cleaned or None


def _parse_child_bibs(tree: Any) -> list[ChildBib]:
    """Parse the 子書誌情報 (child bibliography) table for series parents.

    Observed layout (each <tr> has 2 cells):
      td[0]: ordinal number (e.g. "1")
      td[1]: <a href="...bibid=...">title</a> 出版地 : 出版者 , 年月
    """
    out: list[ChildBib] = []
    h3s = tree.xpath("//h3[contains(., '子書誌')]")
    if not h3s:
        return out
    tables = h3s[0].xpath("following::table[1]")
    if not tables:
        return out
    for tr in tables[0].xpath(".//tr"):
        tds = tr.xpath("./td")
        if len(tds) < 2:
            continue
        num_text = " ".join(tds[0].text_content().split())
        if not re.fullmatch(r"\d+", num_text):
            continue
        links = tds[1].xpath(".//a[contains(@href,'bibid=')]")
        if not links:
            continue
        href = links[0].get("href") or ""
        bibid_m = re.search(r"bibid=([A-Z]{2}\d+)", href)
        title = " ".join(links[0].text_content().split())
        # publication = whole second-cell text minus the link text
        full = " ".join(tds[1].text_content().split())
        pub = full.replace(title, "", 1).strip()
        out.append(ChildBib(
            number=int(num_text),
            bibid=bibid_m.group(1) if bibid_m else None,
            title=title,
            publication=pub,
        ))
    return out


# ----- Structured publication / volume parts / RDA -------------------------

_RE_PUB_YEAR = re.compile(r"(?:^|[\s,])\[?c?(?P<year>\d{4})\]?(?:[.\d]*\s*)$")
_RE_PUB_SERIES = re.compile(r"\.\s*-\s*\(([^)]+)\)\s*$")
_RE_PUB_EDITION = re.compile(
    r"^(?P<edition>(?:第\s*\d+\s*版|Ver\.?\s*\d[\w.]*|\d+(?:st|nd|rd|th)\s*ed\.?|新版|改訂版|増訂版|[\w.]+ ed\.|Ver\.?\s*\d[\w.]*))\.\s*-\s*"
)


def _parse_publication(raw: str, *, year_hint: str | None = None) -> Publication:
    """Best-effort split of a KULINE PUBLICATION line into structured parts."""
    if not raw:
        if year_hint:
            return Publication(raw="", year=int(year_hint) if year_hint.isdigit() else None)
        return Publication(raw="")
    text = raw.strip()

    edition: str | None = None
    em = _RE_PUB_EDITION.match(text)
    if em:
        edition = em.group("edition")
        text = text[em.end():]

    series: str | None = None
    sm = _RE_PUB_SERIES.search(text)
    if sm:
        series = sm.group(1).strip()
        text = text[: sm.start()].rstrip()
    # also handle &nbsp;-&nbsp; series
    if not series:
        sm2 = re.search(r" ?- ?\(([^)]+)\)\s*$", text)
        if sm2:
            series = sm2.group(1).strip()
            text = text[: sm2.start()].rstrip()

    year: int | None = None
    ym = re.search(r"[,\s]\[?c?(\d{4})\]?(?:[.\d]*)?\s*$", text)
    if ym:
        year = int(ym.group(1))
        text = text[: ym.start()].rstrip(", ").rstrip()
    elif year_hint and year_hint.isdigit():
        year = int(year_hint)

    # Now text is roughly "place : publisher [. - place : publisher2]"
    # Take the FIRST "place : publisher" segment.
    place: str | None = None
    publisher: str | None = None
    seg = text.split(". - ")[0]
    pm = re.match(r"\s*(?P<place>[^:]+?)\s*:\s*(?P<pub>.+?)\s*$", seg)
    if pm:
        place = pm.group("place").strip()
        publisher = pm.group("pub").strip()
    else:
        publisher = seg.strip() or None

    return Publication(
        raw=raw, edition=edition, place=place, publisher=publisher,
        year=year, series=series,
    )


def _parse_kv_semis(text: str) -> dict[str, str]:
    """Parse "KEY:value ; KEY2:value2" style strings (BBVOLG)."""
    out: dict[str, str] = {}
    if not text:
        return out
    for part in re.split(r"\s*;\s*", text):
        m = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*:\s*(.+?)\s*$", part)
        if m:
            out[m.group(1)] = m.group(2)
    return out


_RE_RDA_CONTENT = re.compile(r"表現種別\s*:\s*(.+?)\s*\((?:ncrcontent)\)")
_RE_RDA_MEDIA = re.compile(r"機器種別\s*:\s*(.+?)\s*\((?:ncrmedia)\)")
_RE_RDA_CARRIER = re.compile(r"キャリア種別\s*:\s*(.+?)\s*\((?:ncrcarrier)\)")


def _parse_rda(notes: str) -> RdaTypes:
    if not notes:
        return RdaTypes()
    c = _RE_RDA_CONTENT.search(notes)
    m = _RE_RDA_MEDIA.search(notes)
    car = _RE_RDA_CARRIER.search(notes)
    return RdaTypes(
        content=c.group(1).strip() if c else None,
        media=m.group(1).strip() if m else None,
        carrier=car.group(1).strip() if car else None,
    )


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------

def parse_facet(body: str, facet_type: FacetType) -> FacetInfo:
    """Parse an opac_facet response fragment."""
    if not body.strip():
        return FacetInfo(type=facet_type, values=[])
    tree = lxml_html.fromstring(body)
    values: list[FacetValue] = []
    for li in tree.xpath("//li"):
        # Two shapes: checkbox (datatype) and link (all other types)
        cb = li.xpath(".//input[@type='checkbox' and not(starts-with(@value,'all'))]")
        if cb:
            value = cb[0].get("value") or ""
            label = " ".join(li.xpath(".//span[contains(@class,'check_datatype')]/text()")).strip()
        else:
            a = li.xpath(".//a")
            if not a:
                continue
            value = a[0].get("title") or a[0].text_content().strip()
            label = a[0].text_content().strip()
        cnt_text = " ".join(li.xpath(".//span[contains(@class,'data_cnt')]/text()")).strip()
        m = re.search(r"\((\d+)\)", cnt_text)
        count = int(m.group(1)) if m else 0
        if value:
            values.append(FacetValue(value=value, label=label, count=count))
    return FacetInfo(type=facet_type, values=values)


# ---------------------------------------------------------------------------
# Spellcheck / suggest
# ---------------------------------------------------------------------------

def parse_spellcheck(body: str) -> list[SpellCorrection]:
    if not body.strip():
        return []
    tree = lxml_html.fromstring(body)
    out: list[SpellCorrection] = []
    for a in tree.xpath("//p[@id='opac_spellcheck']//a"):
        term = a.text_content().strip()
        url = a.get("href") or ""
        if term:
            out.append(SpellCorrection(term=term, search_url=url))
    return out


# ---------------------------------------------------------------------------
# Localhold JSON → Holding[]
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Supplementary (BookPlus / openBD synopsis + TOC)
# ---------------------------------------------------------------------------

_RE_NO_DATA = re.compile(
    r"(?:あらすじ・目次|目次・あらすじ).*?(?:情報はありません|電子情報はありません)"
)
_RE_SECTION = re.compile(r"\[(あらすじ|目次|著者紹介|内容|要旨)\]")


def parse_supplementary(body: str, source: SupplementarySource) -> Supplementary:
    """Parse a BookPlus/openBD response into a structured :class:`Supplementary`."""
    # Strip HTML tags and decode entities
    if "<" in body:
        try:
            tree = lxml_html.fromstring(f"<div>{body}</div>")
            text = tree.text_content()
        except Exception:
            text = re.sub(r"<[^>]+>", "", body)
    else:
        text = body
    text = text.strip()

    if not text or _RE_NO_DATA.search(text):
        return Supplementary(source=source, raw_text=text, empty=True)

    # Split on section headers like "[あらすじ]" and "[目次]"
    pieces = _RE_SECTION.split(text)
    # pieces = [intro, "あらすじ", body, "目次", body, ...]
    synopsis: str | None = None
    toc: list[str] = []
    for i in range(1, len(pieces) - 1, 2):
        name = pieces[i].strip()
        content = pieces[i + 1].strip()
        if name in ("あらすじ", "要旨", "内容"):
            # Collapse internal whitespace but preserve paragraph breaks
            synopsis = "\n".join(
                " ".join(line.split())
                for line in content.splitlines()
                if line.strip()
            ).strip() or None
        elif name == "目次":
            toc = [
                " ".join(line.split())
                for line in content.splitlines()
                if line.strip()
            ]
    empty = synopsis is None and not toc
    return Supplementary(
        source=source,
        synopsis=synopsis,
        toc=toc,
        raw_text=text,
        empty=empty,
    )


def parse_localhold_response(payload: list[dict]) -> dict[str, list[Holding]]:
    """Map JSON ``[{bibid, res}, ...]`` to ``{bibid: [Holding, ...]}``."""
    out: dict[str, list[Holding]] = {}
    for item in payload:
        bibid = item.get("bibid", "")
        html = item.get("res", "")
        tree = lxml_html.fromstring(f"<div>{html}</div>")
        rows = []
        for tr in tree.xpath("//tr[contains(@class,'list_bl_item_tr')]"):
            def cell(cls: str) -> str | None:
                els = tr.xpath(f"./td[contains(@class,'{cls}')]")
                if not els:
                    return None
                text = " ".join(els[0].text_content().split())
                return text or None

            blkey = None
            bk_links = tr.xpath(".//a[contains(@href,'blkey=')]/@href")
            if bk_links:
                m = re.search(r"blkey=([A-Z]*\d+)", bk_links[0])
                if m:
                    blkey = m.group(1)
            online_url = None
            online_label = None
            online_cells = tr.xpath(".//td[contains(@class,'ONLINE')]")
            if online_cells:
                a = online_cells[0].xpath(".//a/@href")
                if a:
                    online_url = a[0]
                lab = " ".join(online_cells[0].text_content().split())
                if lab and lab != "リンク":
                    online_label = lab
            floor_a = tr.xpath(".//td[contains(@class,'LOCATION')]//a/@href")
            floor_pdf = floor_a[0] if floor_a and floor_a[0].endswith(".pdf") else None

            tr_html = lxml_html.tostring(tr, encoding="unicode")
            status_query = _parse_blstat_query(tr_html)

            rows.append(Holding(
                volume=cell("VOLUME"),
                location=cell("LOCATION"),
                call_no=cell("CALLNO"),
                barcode=cell("BARCODE"),
                blkey=blkey,
                condition=_clean_condition(cell("CONDITION")),
                comments=cell("COMMENTS"),
                online_url=online_url,
                online_label=online_label,
                library_floor_pdf=floor_pdf,
                status_query=status_query,
            ))
        out[bibid] = rows
    return out
