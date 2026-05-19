"""Parser regression tests for ``/opac/opac_search/`` HTML.

Each fixture is the minimum HTML that exercises one extraction contract.  The
shapes mirror what KULINE actually serves (see ``docs/opac-spec.md`` §3).
"""
from __future__ import annotations

from kuopac._parse import parse_search_results
from kuopac.enums import DataType, Scope


def _wrap(body: str) -> str:
    """Slap a minimal <html> envelope around a body fragment for lxml."""
    return f"<html><body>{body}</body></html>"


# ---------------------------------------------------------------------------
# Local (cmode=0) results
# ---------------------------------------------------------------------------

LOCAL_TWO_HITS = _wrap(r"""
<p class="current-search-key">検索キーワード：<span>(Python)</span></p>
<p class="search-results-hits_num pull-left">該当件数:1,122件</p>
<ul class="result-list">
  <li>
    <input type="hidden" name="list_bibid" value="BB08815134" />
    <input type="hidden" name="list_datatype" value="10" />
    <span class="result-num">1.</span>
    <p class="result-book-title">
      <a href="/opac/opac_details/?lang=0&amode=11&bibid=BB08815134&opkey=B17791234567890&start=1&listnum=0">
        Python入門 / 山田太郎
      </a>
    </p>
    <p class="result-book-publisher">東京 : 技術評論社 , 2024.6</p>
    <p class="book-type pull-left">
      <span class="icon-opac_book-2"></span>&nbsp;図書
      &lt;BB08815134&gt; [BD13906877]
    </p>
  </li>
  <li>
    <input type="hidden" name="list_bibid" value="EB14488611" />
    <input type="hidden" name="list_datatype" value="19" />
    <span class="result-num">2.</span>
    <p class="result-book-title">
      <a href="/opac/opac_details/?bibid=EB14488611">eBook title</a>
    </p>
    <p class="result-book-publisher">[S.l.] : O'Reilly , 2026</p>
    <p class="book-type">電子ブック</p>
  </li>
</ul>
<script>
img_out_link_list_all('/opac/opac_imgoutlink/',
  '[[{"bibid":"BB08815134","isbn":"9784621311639","jfcd":"2","datatype":"10","thfmt":"","ncid":"BD13906877","nbn":"JP24199089"},{"bibid":"EB14488611","isbn":"9784814401482","jfcd":"1","datatype":"19","thfmt":"","ncid":"","nbn":""}]]',
  'csrf-token-here', 'bookplus,openbd', '1');
</script>
""")


def test_total_hits_handles_comma() -> None:
    r = parse_search_results(
        LOCAL_TWO_HITS, request_url="http://x", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
    )
    assert r.total == 1122


def test_opkey_is_extracted_from_url() -> None:
    r = parse_search_results(
        LOCAL_TWO_HITS, request_url="http://x", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
    )
    assert r.opkey == "B17791234567890"


def test_book_basic_fields() -> None:
    r = parse_search_results(
        LOCAL_TWO_HITS, request_url="http://x", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
    )
    assert len(r.books) == 2
    first = r.books[0]
    assert first.ids.bibid == "BB08815134"
    assert first.data_type is DataType.BOOK
    assert first.list_index == 1
    assert first.title.startswith("Python入門")
    assert "技術評論社" in first.publisher_line
    assert first.scope is Scope.LOCAL


def test_ebook_datatype_is_parsed() -> None:
    r = parse_search_results(
        LOCAL_TWO_HITS, request_url="http://x", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
    )
    assert r.books[1].data_type is DataType.EBOOK


def test_inline_json_seed_supplies_isbn_ncid_nbn() -> None:
    """HTML lacks ISBN; the JS seed array does — without it search results
    would have no ISBN at all, breaking ``synopsis`` lookups."""
    r = parse_search_results(
        LOCAL_TWO_HITS, request_url="http://x", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
    )
    first = r.books[0]
    assert first.ids.isbn == "9784621311639"
    assert first.ids.ncid == "BD13906877"
    assert first.ids.nbn == "JP24199089"


def test_query_summary_collapses_whitespace() -> None:
    r = parse_search_results(
        LOCAL_TWO_HITS, request_url="http://x", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
    )
    assert "Python" in r.query_summary
    # No multi-space runs (the parser ``.split()``-joins).
    assert "  " not in r.query_summary


# ---------------------------------------------------------------------------
# Zero hits
# ---------------------------------------------------------------------------

ZERO_HITS = _wrap("""
<p class="current-search-key">検索キーワード：<span>(zzz)</span></p>
<ul class="result-list"></ul>
""")


def test_zero_hits_returns_empty() -> None:
    r = parse_search_results(
        ZERO_HITS, request_url="http://x", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
    )
    assert r.total == 0
    assert r.books == []


# ---------------------------------------------------------------------------
# CiNii (cmode=5) — no hidden list_bibid; NCID lives in detail URL
# ---------------------------------------------------------------------------

CINII_RESULT = _wrap("""
<p class="search-results-hits_num">該当件数:54件</p>
<ul class="result-list">
  <li>
    <p class="result-book-title">
      <span class="result-num">1.</span>
      <a href="/opac/opac_detail_ciniibooks/?lang=0&amode=11&ncid=BD18625252&listnum=1&totalnum=54&start=1&opkey=B17799999999999">
        深層学習入門
      </a>
      &nbsp;/&nbsp;山田 太郎
    </p>
    <p class="result-book-publisher">出版社 , 2024</p>
    <p class="result-book-datatype book-type">図書</p>
  </li>
</ul>
""")


def test_cinii_extracts_ncid_from_detail_url() -> None:
    r = parse_search_results(
        CINII_RESULT, request_url="http://x", scope=Scope.CINII,
        page_start=1, page_size=20, sort=3,
    )
    assert r.total == 54
    assert len(r.books) == 1
    b = r.books[0]
    assert b.ids.ncid == "BD18625252"
    assert b.ids.bibid is None
    assert b.scope is Scope.CINII
