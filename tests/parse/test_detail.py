"""Parser regression tests for ``/opac/opac_details/`` and CiNii detail.

Each test fixates one extraction contract — most map 1:1 to a bug listed in
``docs/audit-report.md`` §C3 ("監査で発見し、修正した抽出バグ").  When KULINE
changes a template, the failing test pinpoints which extraction broke.
"""
from __future__ import annotations

import pytest

from kuopac._parse import parse_detail
from kuopac.enums import DataType
from kuopac.errors import ParseError


def _detail_html(*, title: str, kana: str = "", rows: str = "",
                  extra: str = "") -> str:
    """Assemble a minimal detail page with a controllable bib-table body.

    KULINE serves the detail table twice (PC + mobile breakpoint).  The parser
    is supposed to dedupe by ``raw_fields`` first-occurrence; we mimic that
    duplication in fixtures that need to prove the dedupe works.
    """
    return f"""
<html><body>
  <h2 class="book-title">
    <span class="book-title-kana">{kana}</span>
    <br />
    <span class="book-title-trd">{title}</span>
    {extra}
  </h2>
  <table class="book-detail-table">
    {rows}
  </table>
</body></html>
"""


# ---------------------------------------------------------------------------
# Title + responsibility
# ---------------------------------------------------------------------------

def test_title_split_on_ascii_slash() -> None:
    html = _detail_html(
        title="実践的パフォーマンスエンジニアリング / フィックスターズ",
        rows="""
          <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
        """,
    )
    book = parse_detail(html)
    assert book.title_main == "実践的パフォーマンスエンジニアリング"
    assert book.responsibility == "フィックスターズ"


def test_title_split_on_nbsp_slash_for_cinii() -> None:
    """audit-report §C3 — CiNii titles use NBSP around the slash; the parser
    normalises to ASCII space before partitioning, otherwise ``title_main``
    and ``responsibility`` are both ``None``."""
    html = _detail_html(
        title="深層学習 / 山田 太郎",
        rows="""
          <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
        """,
    )
    book = parse_detail(html)
    assert book.title_main == "深層学習"
    assert book.responsibility == "山田 太郎"


def test_missing_title_raises_parse_error() -> None:
    bad = "<html><body><h2 class='book-title'></h2></body></html>"
    with pytest.raises(ParseError):
        parse_detail(bad)


# ---------------------------------------------------------------------------
# RDA triplet pulled out of free-form BBNOTE
# ---------------------------------------------------------------------------

def test_rda_types_extracted_from_bbnote() -> None:
    """audit-report §C3 — BBNOTE was unstructured; RDA fields are now parsed."""
    html = _detail_html(
        title="t",
        rows="""
          <tr><th class="BBNOTE">注記</th>
              <td class="BBNOTE">表現種別: テキスト (ncrcontent),
                                  機器種別: 機器不用 (ncrmedia),
                                  キャリア種別: 冊子 (ncrcarrier)
              </td>
          </tr>
        """,
    )
    book = parse_detail(html)
    assert book.rda_types.content == "テキスト"
    assert book.rda_types.media == "機器不用"
    assert book.rda_types.carrier == "冊子"


# ---------------------------------------------------------------------------
# BBVOLG parsing
# ---------------------------------------------------------------------------

def test_bbvolg_split_into_kv_parts() -> None:
    """audit-report §C3 — BBVOLG's ``KEY:value ; KEY2:value2`` was opaque."""
    html = _detail_html(
        title="t",
        rows="""
          <tr><th class="BBVOLG">巻冊次</th>
              <td class="BBVOLG">ISBN:9784297153496 ; PRICE:3400円+税</td></tr>
        """,
    )
    book = parse_detail(html)
    assert book.volume_info_parts == {
        "ISBN": "9784297153496",
        "PRICE": "3400円+税",
    }


# ---------------------------------------------------------------------------
# Subjects + classifications (multiple SCHEME: value rows in a single <td>)
# ---------------------------------------------------------------------------

def test_subjects_split_by_scheme() -> None:
    html = _detail_html(
        title="t",
        rows="""
          <tr><th class="BBSUBJECT">件名</th>
              <td class="BBSUBJECT">BSH: 人工知能 NDLSH: 機械学習</td></tr>
          <tr><th class="BBCLS">分類</th>
              <td class="BBCLS">NDC9: 007.13 NDC10: 007.13 NDLC: M121</td></tr>
        """,
    )
    book = parse_detail(html)
    schemes = [(s.scheme, s.term) for s in book.subjects]
    assert ("BSH", "人工知能") in schemes
    assert ("NDLSH", "機械学習") in schemes
    codes = [(c.scheme, c.code) for c in book.classifications]
    assert ("NDC9", "007.13") in codes
    assert ("NDLC", "M121") in codes


# ---------------------------------------------------------------------------
# Holdings: physical + dispStatName JS cleanup
# ---------------------------------------------------------------------------

PHYSICAL_HOLDING_HTML = """
<html><body>
  <h2 class="book-title">
    <span class="book-title-trd">t</span>
  </h2>
  <table class="book-detail-table">
    <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
  </table>
  <table class="library-info-table2">
    <tr class="library-info-data">
      <td class="LOCATION"><a href="floor.pdf">情報学||図書室</a></td>
      <td class="CALLNO">007.1||FIX 1||3</td>
      <td class="BARCODE"><a href="/opac/opac_detail_book/?blkey=19200695">200047045652</a></td>
      <td class="CONDITION">
        <span class="blstat_block_BL19200695"></span>
        <script>dispStatName('/opac/opac_blstat/','50','1','1','BL19200695','0','1','OT00477489','1','','0','返却期限','waiting...');</script>
      </td>
      <td class="COMMENTS"></td>
    </tr>
  </table>
</body></html>
"""


def test_condition_cleaned_of_dispstat_js() -> None:
    """audit-report §C3 — CONDITION cell included the AJAX trigger as text."""
    book = parse_detail(PHYSICAL_HOLDING_HTML)
    assert len(book.holdings) == 1
    h = book.holdings[0]
    assert h.condition is None
    assert h.call_no == "007.1||FIX 1||3"
    assert h.barcode == "200047045652"
    assert h.blkey == "19200695"


def test_status_query_extracted_from_dispstat_args() -> None:
    book = parse_detail(PHYSICAL_HOLDING_HTML)
    sq = book.holdings[0].status_query
    assert sq is not None
    assert sq.blipkey == "BL19200695"
    assert sq.phasecd == "50"
    assert sq.odrno == "OT00477489"
    assert sq.addmsg == "返却期限"


def test_floor_pdf_url_captured() -> None:
    book = parse_detail(PHYSICAL_HOLDING_HTML)
    assert book.holdings[0].library_floor_pdf == "floor.pdf"


# ---------------------------------------------------------------------------
# Online (e-book) holding
# ---------------------------------------------------------------------------

EBOOK_HOLDING_HTML = """
<html><body>
  <h2 class="book-title"><span class="book-title-trd">eBook title</span></h2>
  <table class="book-detail-table">
    <tr><th class="DATATYPE">種別</th><td class="DATATYPE">電子ブック</td></tr>
  </table>
  <table class="library-info-table2">
    <tr class="library-info-data">
      <td class="setCenter ONLINE">
        <a href="https://proxy.example/login?url=https://oreilly/book/123">eBook</a>
      </td>
      <td class="LOCATION">電子ブック</td>
      <td class="CALLNO"></td>
      <td class="BARCODE"></td>
      <td class="CONDITION">オンライン</td>
    </tr>
  </table>
</body></html>
"""


def test_ebook_online_url_and_label_captured() -> None:
    """audit-report §C3 — the ONLINE label ('eBook' etc.) used to be dropped."""
    book = parse_detail(EBOOK_HOLDING_HTML)
    assert book.data_type is DataType.EBOOK
    h = book.holdings[0]
    assert h.online_url == "https://proxy.example/login?url=https://oreilly/book/123"
    assert h.online_label == "eBook"
    assert h.is_online


# ---------------------------------------------------------------------------
# CiNii holding shape (institution/orderno/rgtn)
# ---------------------------------------------------------------------------

CINII_HOLDING_HTML = """
<html><body>
  <h2 class="book-title"><span class="book-title-trd">外大書</span></h2>
  <table class="book-detail-table">
    <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
  </table>
  <table class="library-info-table2">
    <tr class="library-info-data">
      <td class="institution">神戸大学 附属図書館</td>
      <td class="location">本館</td>
      <td class="orderno">CB-12345</td>
      <td class="rgtn">RG-9999</td>
    </tr>
  </table>
</body></html>
"""


def test_cinii_holding_uses_institution_columns() -> None:
    """audit-report §C3 — CiNii column classes are institution/location/
    orderno/rgtn, not LOCATION/CALLNO/BARCODE.  Pre-fix this row was all
    ``None``."""
    book = parse_detail(CINII_HOLDING_HTML)
    h = book.holdings[0]
    assert h.institution == "神戸大学 附属図書館"
    assert h.cinii_orderno == "CB-12345"
    assert h.cinii_rgtn == "RG-9999"
    assert h.is_remote_university


# ---------------------------------------------------------------------------
# Child bibliographies (series parent → children list)
# ---------------------------------------------------------------------------

SERIES_PARENT_HTML = """
<html><body>
  <h2 class="book-title"><span class="book-title-trd">叢書のタイトル</span></h2>
  <table class="book-detail-table">
    <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
  </table>
  <h3>子書誌情報</h3>
  <table>
    <tr><td>1</td>
        <td><a href="/opac/opac_details/?bibid=BB00000001">第1巻</a> 東京 : 出版者 , 2024</td>
    </tr>
    <tr><td>2</td>
        <td><a href="/opac/opac_details/?bibid=BB00000002">第2巻</a> 東京 : 出版者 , 2025</td>
    </tr>
  </table>
</body></html>
"""


def test_child_bibliographies_are_extracted() -> None:
    """audit-report §C3 — the parser used to ignore 子書誌情報 entirely."""
    book = parse_detail(SERIES_PARENT_HTML)
    assert len(book.children) == 2
    first = book.children[0]
    assert first.number == 1
    assert first.bibid == "BB00000001"
    assert first.title == "第1巻"
    assert "東京" in first.publication


# ---------------------------------------------------------------------------
# Parent series link
# ---------------------------------------------------------------------------

def test_parent_series_link_captured() -> None:
    html = """
<html><body>
  <h2 class="book-title">
    <span class="book-title-trd">本の書名</span>
    <span id="PTBL"><a href="/opac/opac_details/?bibid=BB99999999">ML systems</a></span>
  </h2>
  <table class="book-detail-table">
    <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
  </table>
</body></html>
"""
    book = parse_detail(html)
    assert len(book.parent_series) == 1
    assert book.parent_series[0].title == "ML systems"
    assert book.parent_series[0].bibid == "BB99999999"


# ---------------------------------------------------------------------------
# External links sidebar
# ---------------------------------------------------------------------------

def test_external_links_are_categorised() -> None:
    html = """
<html><body>
  <h2 class="book-title"><span class="book-title-trd">t</span></h2>
  <table class="book-detail-table">
    <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
  </table>
  <div class="panel panel-primary">
    <div class="panel-body">
      <ul class="list-group">
        <li><a href="https://ci.nii.ac.jp/books/openurl/?ncid=BD1">CiNii</a></li>
        <li><a href="https://ndlsearch.ndl.go.jp/api/openurl?isbn=978">NDL</a></li>
        <li><a href="https://www.google.co.jp/search?q=978">Google</a></li>
        <li><a href="https://books.google.co.jp/books?q=978">Google Books</a></li>
        <li><a href="https://scholar.google.co.jp/scholar?q=978">Google Scholar</a></li>
      </ul>
    </div>
  </div>
  <a href="https://kuline.kulib.kyoto-u.ac.jp/opac/opac_link/bibid/BB1">permalink</a>
</body></html>
"""
    book = parse_detail(html)
    ext = book.external_links
    assert ext.cinii is not None and "ci.nii.ac.jp" in ext.cinii
    assert ext.ndl is not None and "ndlsearch.ndl.go.jp" in ext.ndl
    assert ext.google_books is not None
    assert ext.google_scholar is not None
    assert ext.permalink == "https://kuline.kulib.kyoto-u.ac.jp/opac/opac_link/bibid/BB1"


# ---------------------------------------------------------------------------
# Detail row dedupe (PC + mobile breakpoints duplicate the table)
# ---------------------------------------------------------------------------

def test_duplicate_detail_rows_keep_first_occurrence() -> None:
    """Spec §11.7 — KULINE serves PC+mobile duplicates of each ``<th class>``;
    the parser must keep the first only."""
    html = _detail_html(
        title="t",
        rows="""
          <tr><th class="LANGUAGE">言語</th><td class="LANGUAGE">日本語</td></tr>
          <tr><th class="LANGUAGE">言語</th><td class="LANGUAGE">jpn</td></tr>
        """,
    )
    book = parse_detail(html)
    assert book.language == "日本語"
