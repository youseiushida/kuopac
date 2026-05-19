"""Smoke-test that every ``examples/*.py`` module's ``main()`` runs to completion.

The examples are written to exercise the public API end-to-end against the
real KULINE.  In CI we re-route all HTTP through an :class:`httpx.MockTransport`
serving canned responses for every endpoint they touch.  Tests assert only
that the example doesn't raise — actual content correctness is covered by
the parser and client wire-format suites.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Iterable

import httpx
import pytest

from kuopac._http import HttpSession
from kuopac.client import KulineClient

# ---------------------------------------------------------------------------
# Canned responses — designed to satisfy every example's main() flow.
# ---------------------------------------------------------------------------

_BIBID_ONE = "BB08818020"
_BIBID_TWO = "BB08815134"
_ISBN_ONE = "9784000000000"


def _search_html(total: int = 50) -> str:
    """Multi-page-looking search results so ``iter_all`` actually paginates."""
    return f"""
<html><body>
<form><input type='hidden' name='csrfmiddlewaretoken' value='TOK' /></form>
<p class="current-search-key">検索キーワード：<span>(test)</span></p>
<p class="search-results-hits_num">該当件数:{total}件</p>
<ul class="result-list">
  <li>
    <input type="hidden" name="list_bibid" value="{_BIBID_ONE}" />
    <input type="hidden" name="list_datatype" value="10" />
    <span class="result-num">1.</span>
    <p class="result-book-title">
      <a href="/opac/opac_details/?bibid={_BIBID_ONE}&opkey=B999&start=1">First Book</a>
    </p>
    <p class="result-book-publisher">Tokyo : Pub , 2024</p>
    <p class="book-type">図書 &lt;{_BIBID_ONE}&gt;</p>
  </li>
  <li>
    <input type="hidden" name="list_bibid" value="{_BIBID_TWO}" />
    <input type="hidden" name="list_datatype" value="10" />
    <span class="result-num">2.</span>
    <p class="result-book-title">
      <a href="/opac/opac_details/?bibid={_BIBID_TWO}&opkey=B999&start=1">Second Book</a>
    </p>
    <p class="result-book-publisher">Tokyo : Pub , 2024</p>
    <p class="book-type">図書 &lt;{_BIBID_TWO}&gt;</p>
  </li>
</ul>
<script>
img_out_link_list_all('/x', '[[{{"bibid":"{_BIBID_ONE}","isbn":"{_ISBN_ONE}","ncid":"BD1","nbn":""}},{{"bibid":"{_BIBID_TWO}","isbn":"{_ISBN_ONE}","ncid":"BD2","nbn":""}}]]', 't', 'b,o', '1');
</script>
</body></html>
"""


_DETAIL_HTML = f"""
<html><body>
<h2 class="book-title">
  <span class="book-title-kana">テスト</span>
  <span class="book-title-trd">Test Book / Test Author</span>
</h2>
<table class="book-detail-table">
  <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
  <tr><th class="BBBIBID">書誌ID</th><td class="BBBIBID">{_BIBID_ONE}</td></tr>
  <tr><th class="BBISBN">ISBN</th><td class="BBISBN">{_ISBN_ONE}</td></tr>
  <tr><th class="PUBLICATION">出版</th><td class="PUBLICATION">Tokyo : Pub , 2024</td></tr>
  <tr><th class="AHDNG">著者</th>
      <td class="AHDNG">
        <a href="/opac/opac_search/?con1_exp=alkey&kywd1_exp=%23Test">Test Author</a>
        &nbsp;著者
      </td></tr>
</table>
<table class="library-info-table2">
  <tr class="library-info-data">
    <td class="LOCATION">情報学||図書室</td>
    <td class="CALLNO">007.1||X 1</td>
    <td class="BARCODE"><a href="?blkey=19000001">200000001</a></td>
    <td class="CONDITION"></td>
  </tr>
</table>
</body></html>
"""

_FACET_HTML = """
<ul>
  <li>
    <label>
      <input type="checkbox" value="10" name="facet_datatype" class="datatype" />
      <span class="check_datatype" title="図書">図書</span>
    </label>
    <span class="data_cnt">(40)</span>
  </li>
</ul>
"""

_LOCALHOLD_JSON = [
    {
        "bibid": _BIBID_ONE,
        "res": '<table><tr class="list_bl_item_tr">'
               '<td class="LOCATION">loc</td>'
               '<td class="CALLNO">c</td>'
               '<td class="BARCODE">b</td></tr></table>',
    },
    {
        "bibid": _BIBID_TWO,
        "res": '<table><tr class="list_bl_item_tr">'
               '<td class="LOCATION">loc2</td>'
               '<td class="CALLNO">c2</td>'
               '<td class="BARCODE">b2</td></tr></table>',
    },
]

_SUPPL_HTML = """
日外アソシエーツ より

[あらすじ]
Test synopsis line 1.
Test synopsis line 2.

[目次]
第1章 introduction
第2章 main content
"""

_SPELL_HTML = """
<p id="opac_spellcheck">
  <a href="?kywd=python"><em>python</em></a>
</p>
"""


# ---------------------------------------------------------------------------
# Mock transport handler — routes by URL path.
# ---------------------------------------------------------------------------

def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method
    if path.endswith("/opac/opac_search/") and method == "GET":
        return httpx.Response(200, text=_search_html())
    if path.endswith("/opac/opac_details/"):
        return httpx.Response(200, text=_DETAIL_HTML)
    if path.endswith("/opac/opac_detail_ciniibooks/"):
        return httpx.Response(200, text=_DETAIL_HTML)
    if path.endswith("/opac/opac_facet/"):
        return httpx.Response(200, text=_FACET_HTML)
    if path.endswith("/opac/opac_suggest/"):
        return httpx.Response(
            200, json=["sug1", "sug2"],
            headers={"Content-Type": "application/json"},
        )
    if path.endswith("/opac/opac_spellcheck/"):
        return httpx.Response(200, text=_SPELL_HTML)
    if path.endswith("/opac/opac_blstat/"):
        return httpx.Response(200, text="<span>available</span>")
    if path.endswith("/opac/opac_bookplusinfo/"):
        return httpx.Response(200, text=_SUPPL_HTML)
    if path.endswith("/opac/opac_openbdinfo/"):
        return httpx.Response(200, text="目次・あらすじの電子情報はありません。")
    if path.endswith("/opac/opac_search_localhold/") and method == "POST":
        return httpx.Response(200, json=_LOCALHOLD_JSON)
    return httpx.Response(200, text="<html></html>")


# ---------------------------------------------------------------------------
# Patch the live ``KulineClient`` to use the mock transport so
# ``with KulineClient() as kuline:`` works inside every example.
# ---------------------------------------------------------------------------

@pytest.fixture
def stubbed_kuline(monkeypatch: pytest.MonkeyPatch):
    real_init = KulineClient.__init__

    def patched(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault(
            "_http",
            HttpSession(transport=httpx.MockTransport(_handler)),
        )
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(KulineClient, "__init__", patched)


# ---------------------------------------------------------------------------
# Load each example as a module and invoke its main().
# ---------------------------------------------------------------------------

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _example_modules() -> Iterable[tuple[str, Path]]:
    for path in sorted(_EXAMPLES_DIR.glob("*.py")):
        yield path.stem, path


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"_example_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name,path", list(_example_modules()),
                         ids=lambda v: v if isinstance(v, str) else "")
def test_example_main_runs(
    name: str, path: Path, stubbed_kuline, capsys: pytest.CaptureFixture,
) -> None:
    """Each ``examples/*.py`` ``main()`` must complete without raising."""
    module = _load(name, path)
    assert hasattr(module, "main"), f"{name} has no main()"
    # Suppress all output — examples print a lot.  We only care that no
    # exception is raised on the mocked happy path.
    module.main()
    # Sanity: something was actually written; otherwise the patching failed
    # in a way that bypassed the example body silently.
    captured = capsys.readouterr()
    assert captured.out, f"{name} produced no output — patching may be broken"
