"""Wire-format tests for detail / holdings / status / supplementary / suggest."""
from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from kuopac.enums import DataType, Scope, SupplementarySource
from kuopac.errors import NotFoundError
from kuopac.models import BibIdentifiers, BLStatusQuery, Book, Holding

from .conftest import (
    CSRF_LANDING_HTML,
    DETAIL_HTML,
    LOCALHOLD_JSON,
    SPELLCHECK_HTML,
)


def _params(request: httpx.Request) -> dict[str, list[str]]:
    query = request.url.query
    if isinstance(query, bytes):
        query = query.decode("utf-8")
    return parse_qs(query, keep_blank_values=True)


def _body(request: httpx.Request) -> dict[str, list[str]]:
    data = request.content
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return parse_qs(data, keep_blank_values=True)


# ---------------------------------------------------------------------------
# detail()
# ---------------------------------------------------------------------------

def test_detail_targets_opac_details_endpoint(make_client) -> None:
    client, log = make_client(lambda r: httpx.Response(200, text=DETAIL_HTML))
    client.detail("BB1")
    req = log.requests[0]
    assert req.url.path.endswith("/opac/opac_details/")
    p = _params(req)
    assert p["bibid"] == ["BB1"]
    assert p["amode"] == ["11"]


def test_detail_not_found_raises_when_title_span_absent(make_client) -> None:
    """KULINE returns HTTP 200 even for invalid bibids — the signal is the
    missing ``book-title-trd`` span.  See ``docs/opac-spec.md`` §4.6."""
    not_found_html = """
    <html><head><title>京都大学 KULINE</title></head>
    <body><div>not a detail page</div></body></html>
    """
    client, log = make_client(lambda r: httpx.Response(200, text=not_found_html))
    with pytest.raises(NotFoundError):
        client.detail("XX9999999")


def test_cinii_detail_not_found_raises(make_client) -> None:
    not_found_html = "<html><body>nothing here</body></html>"
    client, log = make_client(lambda r: httpx.Response(200, text=not_found_html))
    with pytest.raises(NotFoundError):
        client._cinii_detail("XX99999999")


def test_detail_dispatches_to_cinii_for_cinii_book(make_client) -> None:
    """Passing a ``Book(scope=CINII)`` must route to the CiNii endpoint with
    the ``ncid`` parameter, not ``bibid``."""
    client, log = make_client(lambda r: httpx.Response(200, text=DETAIL_HTML))
    book = Book(
        ids=BibIdentifiers(ncid="BD1234"),
        title="t", publisher_line="",
        data_type=DataType.BOOK, detail_url="",
        list_index=1, scope=Scope.CINII,
    )
    client.detail(book)
    req = log.requests[0]
    assert req.url.path.endswith("/opac/opac_detail_ciniibooks/")
    assert _params(req)["ncid"] == ["BD1234"]


def test_detail_scope_kwarg_forces_cinii_for_bare_string(make_client) -> None:
    """``kuline.detail("BD18537825", scope=Scope.CINII)`` lets callers
    target the CiNii endpoint without first constructing a ``Book``."""
    client, log = make_client(lambda r: httpx.Response(200, text=DETAIL_HTML))
    client.detail("BD18537825", scope=Scope.CINII)
    req = log.requests[0]
    assert req.url.path.endswith("/opac/opac_detail_ciniibooks/")
    assert _params(req)["ncid"] == ["BD18537825"]


def test_detail_scope_kwarg_overrides_book_scope(make_client) -> None:
    """Explicit ``scope=Scope.CINII`` must win over ``Book.scope``."""
    client, log = make_client(lambda r: httpx.Response(200, text=DETAIL_HTML))
    book = Book(
        ids=BibIdentifiers(bibid="BB1", ncid="BD1"),
        title="t", publisher_line="",
        data_type=DataType.BOOK, detail_url="",
        list_index=1, scope=Scope.LOCAL,    # ← would default to local
    )
    client.detail(book, scope=Scope.CINII)
    assert log.requests[0].url.path.endswith("/opac/opac_detail_ciniibooks/")


def test_detail_uses_bibid_when_book_has_one(make_client) -> None:
    client, log = make_client(lambda r: httpx.Response(200, text=DETAIL_HTML))
    book = Book(
        ids=BibIdentifiers(bibid="BB1", ncid="BD1"),
        title="t", publisher_line="",
        data_type=DataType.BOOK, detail_url="",
        list_index=1, scope=Scope.LOCAL,
    )
    client.detail(book)
    assert _params(log.requests[0])["bibid"] == ["BB1"]


# ---------------------------------------------------------------------------
# holdings() — lazy CSRF + POST body shape
# ---------------------------------------------------------------------------

def _holdings_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and "csrfmiddlewaretoken" in CSRF_LANDING_HTML:
        # Preflight to fetch CSRF token.
        return httpx.Response(200, text=CSRF_LANDING_HTML)
    if request.method == "POST":
        return httpx.Response(200, json=LOCALHOLD_JSON)
    return httpx.Response(200, text="")


def test_holdings_posts_to_localhold(make_client) -> None:
    client, log = make_client(_holdings_handler)
    client.holdings(["BB1"])
    post_reqs = [r for r in log.requests if r.method == "POST"]
    assert len(post_reqs) == 1
    assert post_reqs[0].url.path.endswith("/opac/opac_search_localhold/")


def test_holdings_lazy_csrf_preflight_fires_once(make_client) -> None:
    """Spec §0.2 — first POST triggers exactly one GET preflight for the CSRF
    token; subsequent POSTs reuse the cached value (no extra preflight)."""
    client, log = make_client(_holdings_handler)
    client.holdings(["BB1"])
    client.holdings(["BB2"])
    get_count = sum(1 for r in log.requests if r.method == "GET")
    post_count = sum(1 for r in log.requests if r.method == "POST")
    assert get_count == 1   # one preflight, cached afterwards
    assert post_count == 2


def test_holdings_rec_body_encodes_datatype_per_book(make_client) -> None:
    client, log = make_client(_holdings_handler)
    book = Book(
        ids=BibIdentifiers(bibid="EB99"),
        title="t", publisher_line="",
        data_type=DataType.EBOOK,        # 19 — must round-trip in ``rec``
        detail_url="", list_index=1, scope=Scope.LOCAL,
    )
    client.holdings([book])
    post = next(r for r in log.requests if r.method == "POST")
    body = _body(post)
    rec_list = json.loads(body["rec"][0])
    assert rec_list == [
        {"bibid": "EB99", "datatype": "19", "fieldcd": "", "mtid": ""},
    ]


def test_holdings_rec_body_for_raw_bibid_strings(make_client) -> None:
    """Raw bibid strings default to ``DataType.BOOK`` (10)."""
    client, log = make_client(_holdings_handler)
    client.holdings(["BB1", "BB2"])
    post = next(r for r in log.requests if r.method == "POST")
    rec_list = json.loads(_body(post)["rec"][0])
    assert [r["bibid"] for r in rec_list] == ["BB1", "BB2"]
    assert all(r["datatype"] == "10" for r in rec_list)


def test_holdings_post_includes_csrf_token(make_client) -> None:
    client, log = make_client(_holdings_handler)
    client.holdings(["BB1"])
    post = next(r for r in log.requests if r.method == "POST")
    body = _body(post)
    assert body["csrfmiddlewaretoken"] == ["CSRF-TOKEN-VALUE"]
    assert post.headers.get("x-csrftoken") == "CSRF-TOKEN-VALUE"


# ---------------------------------------------------------------------------
# fetch_status() — blstat URL with every status_query field
# ---------------------------------------------------------------------------

def test_fetch_status_serialises_full_query(make_client) -> None:
    client, log = make_client(
        lambda r: httpx.Response(200, text="<span>貸出中</span>"),
    )
    sq = BLStatusQuery(
        blipkey="BL12345", phasecd="50", hldstat="1", lkcd="1",
        prlndflg="0", blcd="1", odrno="OT9999", bbcd="1",
        contcd="X", addmsg="返却期限",
    )
    out = client.fetch_status(sq)
    assert out == "貸出中"
    req = log.requests[0]
    assert req.url.path.endswith("/opac/opac_blstat/")
    p = _params(req)
    assert p["blipkey"] == ["BL12345"]
    assert p["odrno"] == ["OT9999"]
    assert p["addmsg"] == ["返却期限"]
    # spec §0 — AJAX endpoints expect the XHR sentinel header.
    assert req.headers.get("x-requested-with") == "XMLHttpRequest"


def test_fetch_status_writes_back_to_holding(make_client) -> None:
    """When a Holding (not a bare BLStatusQuery) is passed, the live text
    must be assigned back to ``holding.condition`` for downstream consumers."""
    client, log = make_client(
        lambda r: httpx.Response(200, text="<span>取置</span>"),
    )
    h = Holding(
        location="loc",
        status_query=BLStatusQuery(blipkey="BL1"),
    )
    client.fetch_status(h)
    assert h.condition == "取置"


def test_fetch_status_returns_none_when_holding_has_no_query() -> None:
    from kuopac.client import KulineClient
    c = KulineClient(_http=__import__("kuopac")._http.HttpSession(
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    ))
    h = Holding(location="loc", status_query=None)
    assert c.fetch_status(h) is None
    c.close()


# ---------------------------------------------------------------------------
# fetch_supplementary()
# ---------------------------------------------------------------------------

def test_fetch_supplementary_skips_http_when_no_isbn(make_client) -> None:
    """ISBN-less targets must short-circuit to an empty result without firing
    an HTTP request (which would always return "no data" anyway)."""
    client, log = make_client(
        lambda r: httpx.Response(500, text="should not be reached"),
    )
    book = Book(
        ids=BibIdentifiers(bibid="BB1", isbn=None),
        title="t", publisher_line="",
        data_type=DataType.BOOK, detail_url="",
        list_index=1, scope=Scope.LOCAL,
    )
    sup = client.fetch_supplementary(book)
    assert sup.empty
    assert log.requests == []


def test_fetch_supplementary_uses_bookplus_endpoint(make_client) -> None:
    client, log = make_client(
        lambda r: httpx.Response(200, text="[あらすじ]\nABSTRACT\n[目次]\n章1\n"),
    )
    book = Book(
        ids=BibIdentifiers(bibid="BB1", isbn="9784000000000"),
        title="t", publisher_line="",
        data_type=DataType.BOOK, detail_url="",
        list_index=1, scope=Scope.LOCAL,
    )
    sup = client.fetch_supplementary(book, source=SupplementarySource.BOOKPLUS)
    req = log.requests[0]
    assert req.url.path.endswith("/opac/opac_bookplusinfo/")
    assert _params(req)["isbn"] == ["9784000000000"]
    assert _params(req)["bibid"] == ["BB1"]
    assert sup.synopsis == "ABSTRACT"


def test_fetch_supplementary_uses_openbd_endpoint(make_client) -> None:
    client, log = make_client(lambda r: httpx.Response(200, text=""))
    book = Book(
        ids=BibIdentifiers(bibid="BB1", isbn="9784000000000"),
        title="t", publisher_line="",
        data_type=DataType.BOOK, detail_url="",
        list_index=1, scope=Scope.LOCAL,
    )
    client.fetch_supplementary(book, source=SupplementarySource.OPENBD)
    assert log.requests[0].url.path.endswith("/opac/opac_openbdinfo/")


# ---------------------------------------------------------------------------
# suggest() and did_you_mean()
# ---------------------------------------------------------------------------

def test_suggest_returns_json_list(make_client) -> None:
    client, log = make_client(
        lambda r: httpx.Response(200, json=["abc", "abcd"],
                                  headers={"Content-Type": "application/json"}),
    )
    out = client.suggest("a")
    assert out == ["abc", "abcd"]
    req = log.requests[0]
    assert req.url.path.endswith("/opac/opac_suggest/")
    assert _params(req)["q_word"] == ["a"]


def test_suggest_returns_empty_list_on_invalid_json(make_client) -> None:
    client, log = make_client(lambda r: httpx.Response(200, text="not json"))
    assert client.suggest("x") == []


def test_did_you_mean_uses_spellcheck_endpoint(make_client) -> None:
    from kuopac.models import SearchResult
    client, log = make_client(
        lambda r: httpx.Response(200, text=SPELLCHECK_HTML),
    )
    shell = SearchResult(
        books=[], total=0, opkey="B999", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
        query_summary="", raw_url="",
    )
    out = client.did_you_mean(shell)
    assert out == ["python"]
    p = _params(log.requests[0])
    assert log.requests[0].url.path.endswith("/opac/opac_spellcheck/")
    assert p["opkey"] == ["B999"]


# ---------------------------------------------------------------------------
# facets()
# ---------------------------------------------------------------------------

def test_facets_fires_one_request_per_type(make_client) -> None:
    from kuopac.enums import FacetType
    from kuopac.models import SearchResult
    facet_body = """
    <ul>
      <li><a title="X" href="">X</a><span class="data_cnt">(5)</span></li>
    </ul>
    """
    client, log = make_client(
        lambda r: httpx.Response(200, text=facet_body),
    )
    shell = SearchResult(
        books=[], total=0, opkey="B1", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
        query_summary="", raw_url="",
    )
    out = client.facets(shell, types=[FacetType.PUBLISHER, FacetType.YEAR])
    assert set(out.keys()) == {FacetType.PUBLISHER, FacetType.YEAR}
    types_seen = [_params(r)["facet_type"][0] for r in log.requests]
    assert sorted(types_seen) == sorted(["fpub", "yearkey"])
