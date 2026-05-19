"""Parser tests for the smaller AJAX endpoints — localhold / facet /
spellcheck / supplementary.
"""
from __future__ import annotations

from kuopac._parse import (
    parse_facet,
    parse_localhold_response,
    parse_spellcheck,
    parse_supplementary,
)
from kuopac.enums import FacetType, SupplementarySource


# ---------------------------------------------------------------------------
# /opac/opac_search_localhold/ — JSON-wrapped HTML fragment per bibid
# ---------------------------------------------------------------------------

def test_localhold_parses_holdings_per_bibid() -> None:
    payload = [
        {
            "bibid": "BB1",
            "res": """
                <table>
                  <tr class="list_bl_item_tr">
                    <td class="LOCATION">情報学||図書室</td>
                    <td class="CALLNO">007.1||X 1</td>
                    <td class="BARCODE">200047045652</td>
                    <td class="CONDITION">
                      <script>dispStatName('u','50','1','1','BL19200695','0','1','OT1','1','','0','返却期限','');</script>
                    </td>
                  </tr>
                </table>
            """,
        },
        {
            "bibid": "EB2",
            "res": """
                <table>
                  <tr class="list_bl_item_tr">
                    <td class="ONLINE">
                      <a href="https://proxy/login?url=ssj1">eBook</a>
                    </td>
                    <td class="LOCATION">電子ブック</td>
                    <td class="CALLNO"></td>
                    <td class="BARCODE"></td>
                  </tr>
                </table>
            """,
        },
    ]
    out = parse_localhold_response(payload)
    assert set(out.keys()) == {"BB1", "EB2"}
    bb = out["BB1"][0]
    assert bb.location == "情報学||図書室"
    assert bb.call_no == "007.1||X 1"
    assert bb.barcode == "200047045652"
    # dispStatName JS stripped from CONDITION, status_query populated.
    assert bb.condition is None
    assert bb.status_query is not None
    assert bb.status_query.blipkey == "BL19200695"
    # E-book branch
    eb = out["EB2"][0]
    assert eb.online_url == "https://proxy/login?url=ssj1"
    assert eb.online_label == "eBook"


def test_localhold_empty_payload() -> None:
    assert parse_localhold_response([]) == {}


# ---------------------------------------------------------------------------
# /opac/opac_facet/ — two shapes (checkbox for datatype, link otherwise)
# ---------------------------------------------------------------------------

def test_facet_datatype_uses_checkbox_shape() -> None:
    body = """
    <ul>
      <li>
        <label>
          <input type="checkbox" value="10" name="facet_datatype"
                 class="datatype" onclick="facet_datatype_search(...)" />
          <span class="check_datatype" title="図書">図書</span>
        </label>
        <span class="data_cnt">(875)</span>
      </li>
      <li>
        <label>
          <input type="checkbox" value="19" name="facet_datatype" class="datatype" />
          <span class="check_datatype" title="電子ブック">電子ブック</span>
        </label>
        <span class="data_cnt">(1824)</span>
      </li>
    </ul>
    """
    info = parse_facet(body, facet_type=FacetType.DATATYPE)
    assert info.type is FacetType.DATATYPE
    assert {(v.value, v.label, v.count) for v in info.values} == {
        ("10", "図書", 875),
        ("19", "電子ブック", 1824),
    }


def test_facet_link_shape_for_publisher() -> None:
    body = """
    <ul>
      <li>
        <a title="丸善出版" href="?...">丸善出版</a>
        &nbsp;<span class="data_cnt">(8)</span>
      </li>
      <li>
        <a title="技術評論社" href="?...">技術評論社</a>
        <span class="data_cnt">(12)</span>
      </li>
    </ul>
    """
    info = parse_facet(body, facet_type=FacetType.PUBLISHER)
    assert {(v.value, v.count) for v in info.values} == {
        ("丸善出版", 8),
        ("技術評論社", 12),
    }


def test_facet_empty_body() -> None:
    info = parse_facet("", facet_type=FacetType.PUBLISHER)
    assert info.values == []


# ---------------------------------------------------------------------------
# /opac/opac_spellcheck/
# ---------------------------------------------------------------------------

def test_spellcheck_with_candidates() -> None:
    body = """
    <p id="opac_spellcheck" class="spellcheck">
      もしかして：
      <a href="/opac/opac_search/?kywd=python"><em>python</em></a>,&nbsp;
      <a href="/opac/opac_search/?kywd=pitson"><em>pitson</em></a>
    </p>
    """
    candidates = parse_spellcheck(body)
    assert [c.term for c in candidates] == ["python", "pitson"]


def test_spellcheck_no_candidates() -> None:
    assert parse_spellcheck("    ") == []
    assert parse_spellcheck("") == []


# ---------------------------------------------------------------------------
# /opac/opac_bookplusinfo/ and openbdinfo
# ---------------------------------------------------------------------------

def test_supplementary_parses_synopsis_and_toc() -> None:
    body = """
    日外アソシエーツ『BOOKデータASPサービス』より

    実践的パフォーマンスエンジニアリングによるＡＩ高速化
    (出典：日外アソシエーツ『BookPlus』より)

    [あらすじ]
    性能を制する者が、ＡＩを制す。

    [目次]
    第１章　パフォーマンスエンジニアリング概論
    第２章　まずはパフォーマンスを計測する
    第３章　最適化技法
    """
    sup = parse_supplementary(body, source=SupplementarySource.BOOKPLUS)
    assert not sup.empty
    assert sup.synopsis is not None
    assert "性能を制する者" in sup.synopsis
    # Parser ``" ".join(line.split())``-normalises whitespace, collapsing
    # U+3000 (ideographic space) into ASCII space.  That's intentional —
    # most consumers want a single canonical separator.
    assert sup.toc == [
        "第１章 パフォーマンスエンジニアリング概論",
        "第２章 まずはパフォーマンスを計測する",
        "第３章 最適化技法",
    ]
    assert sup.source is SupplementarySource.BOOKPLUS


def test_supplementary_no_data_message_marks_empty() -> None:
    body = "目次・あらすじの電子情報はありません。"
    sup = parse_supplementary(body, source=SupplementarySource.OPENBD)
    assert sup.empty
    assert bool(sup) is False
    assert sup.synopsis is None
    assert sup.toc == []


def test_supplementary_empty_body() -> None:
    sup = parse_supplementary("", source=SupplementarySource.BOOKPLUS)
    assert sup.empty
