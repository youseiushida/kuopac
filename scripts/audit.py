"""
Audit harness: run 3 searches + 4 detail fetches, save both library output
and the raw HTML, and emit a side-by-side comparison.

The point is to verify:
1. Search params are actually applied (current-search-key reflects them, hit
   count differs from the unfiltered baseline).
2. The library extracts everything the HTML exposes — anything in raw HTML
   but missing from the parsed model is a schema gap.
"""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from lxml import html as lxml_html

from kuopac import (
    BookDetail,
    CiniiSort,
    KulineClient,
    MediaType,
    Scope,
    SearchField,
    SearchQuery,
    SearchResult,
    Sort,
)
from kuopac._http import HttpSession

OUT = Path("audit_data")
OUT.mkdir(exist_ok=True)


def serialize(obj):
    if dataclasses.is_dataclass(obj):
        d = {}
        for f in dataclasses.fields(obj):
            if f.name.startswith("_"):
                continue
            d[f.name] = serialize(getattr(obj, f.name))
        return d
    if isinstance(obj, list):
        return [serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if hasattr(obj, "name") and hasattr(obj, "value"):  # IntEnum/Enum
        return f"{type(obj).__name__}.{obj.name}"
    return obj


def save_audit(label: str, *, raw_html: str, raw_url: str, lib_output) -> Path:
    d = OUT / label
    d.mkdir(exist_ok=True)
    (d / "raw.html").write_text(raw_html, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"url": raw_url}, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    (d / "lib.json").write_text(json.dumps(serialize(lib_output), ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# Helpers to extract "everything the HTML shows" so we can compare
# ---------------------------------------------------------------------------

def html_summary_search(html: str) -> dict:
    tree = lxml_html.fromstring(html)
    summary = {}
    summary["hits_text"] = " ".join(tree.xpath(
        "//p[contains(@class,'search-results-hits_num')]//text()"
    )).strip()
    summary["current_search_key"] = " ".join("".join(
        tree.xpath("//p[contains(@class,'current-search-key')]//text()")
    ).split())
    items = tree.xpath("//ul[contains(@class,'result-list')]/li")
    summary["items"] = len(items)
    # Per-item raw dump
    dump = []
    for i, li in enumerate(items[:5], 1):
        rec = {}
        rec["bibid"] = (li.xpath(".//input[@name='list_bibid']/@value") or [None])[0]
        rec["datatype"] = (li.xpath(".//input[@name='list_datatype']/@value") or [None])[0]
        title_a = li.xpath(".//p[contains(@class,'result-book-title')]//a")
        rec["title"] = title_a[0].text_content().strip() if title_a else None
        rec["detail_href"] = title_a[0].get("href") if title_a else None
        rec["publisher"] = " ".join("".join(
            li.xpath(".//p[contains(@class,'result-book-publisher')]//text()")
        ).split())
        rec["book_type_raw"] = " ".join("".join(
            li.xpath(".//p[contains(@class,'book-type')]//text()")
        ).split())
        # what icon?
        icons = li.xpath(".//p[contains(@class,'book-type')]//span/@class")
        rec["icon_class"] = icons[0] if icons else None
        dump.append(rec)
    summary["sample_items"] = dump

    # All distinct <p class=...> children of <li> — what fields exist that we might be ignoring?
    field_classes = set()
    for li in items[:20]:
        for p in li.xpath(".//p[@class]"):
            field_classes.add(p.get("class"))
    summary["all_p_classes"] = sorted(field_classes)

    # Inline JS seed
    m = re.search(r"img_out_link_list_all\([^,]+,\s*'(\[\[.*?\]\])'", html, re.DOTALL)
    if m:
        summary["seed_json_sample"] = json.loads(m.group(1))[0][:3]

    return summary


def html_summary_detail(html: str) -> dict:
    tree = lxml_html.fromstring(html)
    summary: dict = {}
    summary["title"] = " ".join("".join(tree.xpath(
        "//h2[contains(@class,'book-title')]//span[contains(@class,'book-title-trd')]//text()"
    )).split())
    summary["kana"] = " ".join("".join(tree.xpath(
        "//h2[contains(@class,'book-title')]//span[contains(@class,'book-title-kana')]//text()"
    )).split())

    # Every <th class=*> in the book-detail-table
    rows: list[dict] = []
    seen = set()
    for tr in tree.xpath("//table[contains(@class,'book-detail-table')]//tr"):
        ths = tr.xpath("./th")
        tds = tr.xpath("./td")
        if not ths or not tds:
            continue
        code = (ths[0].get("class") or "").split()[0]
        if code in seen:
            continue
        seen.add(code)
        text = " ".join(tds[0].text_content().split())
        rows.append({"code": code, "label": ths[0].text_content().strip(),
                     "value": text[:300]})
    summary["bib_table_rows"] = rows

    # Library-info-table2 holdings rows
    holds = []
    for tr in tree.xpath("//table[contains(@class,'library-info-table2')]//tr[contains(@class,'library-info-data')]"):
        d = {}
        for td in tr.xpath("./td"):
            cls = (td.get("class") or "").strip()
            text = " ".join(td.text_content().split())
            d[cls] = text[:200]
        holds.append(d)
    summary["holdings_rows"] = holds

    # Other interesting blocks: TOC, abstract, related works, PTBL, sns urls
    summary["ptbl"] = tree.xpath("//span[@id='PTBL']//a/text()")
    summary["nav_page"] = " ".join(tree.xpath(
        "//span[contains(@class,'nav-page')]//text()"
    )).strip()

    # All <h3> headings in body to see if there are sections we ignore
    summary["h3_sections"] = [h.text_content().strip()
                              for h in tree.xpath("//h3")
                              if h.text_content().strip()]

    # All distinct field-codes referenced anywhere in the document
    all_field_codes = set()
    for el in tree.xpath("//*[contains(concat(' ',normalize-space(@class),' '),' AHDNG ') or "
                          "contains(concat(' ',normalize-space(@class),' '),' PUBLICATION ')]"):
        pass
    for code in re.findall(r'class="([A-Z][A-Z0-9_]+)"', html):
        all_field_codes.add(code)
    summary["all_uppercase_field_classes"] = sorted(all_field_codes)
    return summary


# ---------------------------------------------------------------------------
# Audit cases
# ---------------------------------------------------------------------------

def run_search_audits(client: KulineClient, raw: HttpSession) -> None:
    # --- A: baseline ----------------------------------------------------
    print("\n=== AUDIT A: baseline 'Python' (no filters) ===")
    q0 = SearchQuery().any("Python")
    r0 = client.search(q0)
    print(f"  hit count: {r0.total}")
    # Save just the count for comparison
    (OUT / "_baseline_count.json").write_text(json.dumps({"Python_any": r0.total}),
                                              encoding="utf-8")

    # --- B: 3-param advanced search ------------------------------------
    print("\n=== AUDIT B: advanced title+year+media ===")
    q = (SearchQuery()
         .title("Python")
         .year_range(2022, 2024)
         .media(MediaType.BOOK)
         .sorted_by(Sort.YEAR_DESC))
    r = client.search(q)
    raw_resp = raw.get("/opac/opac_search/", params=_advanced_params_for(q))
    save_audit("A_advanced_title_year_media",
                raw_html=raw_resp.text, raw_url=str(raw_resp.request.url),
                lib_output=r)
    s = html_summary_search(raw_resp.text)
    (OUT / "A_advanced_title_year_media" / "html_summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  lib total={r.total}  lib items={len(r.books)}")
    print(f"  html summary: hits_text={s['hits_text']!r}")
    print(f"                search_key={s['current_search_key']!r}")
    print(f"                items in HTML={s['items']}")

    # --- C: ISBN + author sort -------------------------------------------
    print("\n=== AUDIT C: ISBN field + sort by author asc ===")
    q = (SearchQuery()
         .isbn("9784297153496")
         .sorted_by(Sort.AUTHOR_ASC)
         .per_page(20))
    r = client.search(q)
    raw_resp = raw.get("/opac/opac_search/", params=_advanced_params_for(q))
    save_audit("C_isbn_sort_author",
                raw_html=raw_resp.text, raw_url=str(raw_resp.request.url),
                lib_output=r)
    s = html_summary_search(raw_resp.text)
    (OUT / "C_isbn_sort_author" / "html_summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  lib total={r.total}  lib items={len(r.books)}")
    print(f"  html hits={s['hits_text']!r}  key={s['current_search_key']!r}")

    # --- D: CiNii year-range subject ---------------------------------
    print("\n=== AUDIT D: CiNii subject + year range ===")
    q = (SearchQuery()
         .title("深層学習")
         .year_range(2020, 2024)
         .in_cinii()
         .sorted_by(CiniiSort.YEAR_DESC))
    r = client.search(q)
    raw_resp = raw.get("/opac/opac_search/", params=_advanced_params_for(q))
    save_audit("D_cinii_title_year",
                raw_html=raw_resp.text, raw_url=str(raw_resp.request.url),
                lib_output=r)
    s = html_summary_search(raw_resp.text)
    (OUT / "D_cinii_title_year" / "html_summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  lib total={r.total}  lib items={len(r.books)}")
    print(f"  html hits={s['hits_text']!r}  key={s['current_search_key']!r}")


def run_detail_audits(client: KulineClient, raw: HttpSession) -> None:
    """Audit several detail pages of different shapes."""
    cases = [
        ("D1_book_BB08818020", "BB08818020", "local"),  # plain book
        ("D2_ebook_EB13920383", "EB13920383", "local"),  # e-book
        ("D3_series_parent_BB08773638", "BB08773638", "local"),  # has PTBL children
        ("D4_cinii_BD18537825", "BD18537825", "cinii"),  # cinii detail
    ]
    for label, key, kind in cases:
        print(f"\n=== AUDIT {label} ({kind} {key}) ===")
        if kind == "local":
            raw_resp = raw.get("/opac/opac_details/", params={
                "lang": "0", "amode": "11", "bibid": key,
            })
            bd = client.detail(key)
        else:
            raw_resp = raw.get("/opac/opac_detail_ciniibooks/", params={
                "lang": "0", "amode": "11", "ncid": key,
            })
            bd = client._cinii_detail(key)
        save_audit(label,
                    raw_html=raw_resp.text, raw_url=str(raw_resp.request.url),
                    lib_output=bd)
        s = html_summary_detail(raw_resp.text)
        (OUT / label / "html_summary.json").write_text(
            json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  lib title:       {bd.title[:60]}")
        print(f"  html bib rows:   {len(s['bib_table_rows'])}")
        print(f"  lib raw_fields:  {len(bd.raw_fields)}")
        print(f"  html holdings:   {len(s['holdings_rows'])}")
        print(f"  lib holdings:    {len(bd.holdings)}")
        print(f"  h3 sections:     {s['h3_sections'][:8]}")


# ---------------------------------------------------------------------------
# Build the actual params from a SearchQuery (mirrors KulineClient._params_for_advanced)
# ---------------------------------------------------------------------------

def _advanced_params_for(q: SearchQuery) -> dict:
    # We re-use the client's method via a throwaway client instance.
    c = KulineClient()
    try:
        return c._params_for_advanced(q)
    finally:
        c.close()


if __name__ == "__main__":
    with KulineClient() as client, HttpSession() as raw:
        run_search_audits(client, raw)
        run_detail_audits(client, raw)
    print("\nSaved to audit_data/")
