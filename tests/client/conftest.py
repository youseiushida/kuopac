"""Shared fixtures for client-layer tests.

These tests follow the Detroit-school discipline of mocking only at the I/O
boundary (httpx).  The real :class:`KulineClient`, real :class:`HttpSession`,
and real :mod:`kuopac._parse` run end-to-end — only the transport is faked so
no network is touched.
"""
from __future__ import annotations

from typing import Callable

import httpx
import pytest

from kuopac._http import HttpSession
from kuopac.client import KulineClient


# ---------------------------------------------------------------------------
# Canned HTML responses — only the fragments the parser actually needs.
# ---------------------------------------------------------------------------

SEARCH_RESULTS_HTML = """
<html><body>
<p class="search-results-hits_num">該当件数:1件</p>
<ul class="result-list">
  <li>
    <input type="hidden" name="list_bibid" value="BB1" />
    <input type="hidden" name="list_datatype" value="10" />
    <span class="result-num">1.</span>
    <p class="result-book-title">
      <a href="/opac/opac_details/?bibid=BB1&opkey=B99999999999999&start=1">
        Test Book
      </a>
    </p>
    <p class="result-book-publisher">Tokyo : Publisher , 2024</p>
    <p class="book-type">図書 &lt;BB1&gt;</p>
  </li>
</ul>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <h2 class="book-title"><span class="book-title-trd">Test Detail</span></h2>
  <table class="book-detail-table">
    <tr><th class="DATATYPE">種別</th><td class="DATATYPE">図書</td></tr>
    <tr><th class="BBBIBID">書誌ID</th><td class="BBBIBID">BB1</td></tr>
  </table>
</body></html>
"""

CSRF_LANDING_HTML = """
<html><body>
  <form><input type="hidden" name="csrfmiddlewaretoken" value="CSRF-TOKEN-VALUE" /></form>
</body></html>
"""

LOCALHOLD_JSON = [
    {
        "bibid": "BB1",
        "res": '<table><tr class="list_bl_item_tr">'
               '<td class="LOCATION">loc</td>'
               '<td class="CALLNO">c</td>'
               '<td class="BARCODE">b</td>'
               '</tr></table>',
    }
]

SPELLCHECK_HTML = """
<p id="opac_spellcheck">
  <a href="?kywd=python"><em>python</em></a>
</p>
"""


# ---------------------------------------------------------------------------
# Mock transport + client factory
# ---------------------------------------------------------------------------

class RequestLog:
    """Captures every request the client makes so tests can introspect later."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def append(self, req: httpx.Request) -> None:
        self.requests.append(req)

    def for_path(self, suffix: str) -> list[httpx.Request]:
        """All captured requests whose URL path ends with ``suffix``."""
        return [r for r in self.requests if r.url.path.endswith(suffix)]


@pytest.fixture
def make_client() -> Callable[[Callable[[httpx.Request], httpx.Response]],
                              tuple[KulineClient, RequestLog]]:
    """Build a :class:`KulineClient` wired up to a mock transport.

    The returned factory takes a handler ``(request) -> Response`` and yields
    ``(client, log)``.  The log captures every request for later assertions.
    """
    created: list[KulineClient] = []

    def factory(handler):  # type: ignore[no-untyped-def]
        log = RequestLog()

        def wrapped(request: httpx.Request) -> httpx.Response:
            log.append(request)
            return handler(request)

        transport = httpx.MockTransport(wrapped)
        session = HttpSession(transport=transport)
        client = KulineClient(_http=session)
        created.append(client)
        return client, log

    yield factory
    for c in created:
        c.close()
