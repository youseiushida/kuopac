"""Wire-format tests for ``KulineClient.search`` and pagination/refine.

KULINE accepts a wide variety of parameter shapes; sending the wrong key
causes the server to silently return unfiltered results (200 OK).  These
tests pin the exact URL parameters each scenario must send.
"""
from __future__ import annotations

from urllib.parse import parse_qs

import httpx

from kuopac.enums import BoolOp, CiniiSort, MediaType, Scope, SearchField, Sort
from kuopac.query import SearchQuery

from .conftest import SEARCH_RESULTS_HTML


def _search_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=SEARCH_RESULTS_HTML)


def _params(request: httpx.Request) -> dict[str, list[str]]:
    """Decode the raw query string into a multidict."""
    query = request.url.query
    if isinstance(query, bytes):
        query = query.decode("utf-8")
    return parse_qs(query, keep_blank_values=True)


# ---------------------------------------------------------------------------
# Simple search
# ---------------------------------------------------------------------------

def test_simple_keyword_search_sends_kywd(make_client) -> None:
    client, log = make_client(_search_handler)
    client.search("機械学習")
    req = log.for_path("/opac/opac_search/")[0]
    p = _params(req)
    assert p["kywd"] == ["機械学習"]
    assert p["amode"] == ["2"]
    assert p["smode"] == ["0"]
    assert p["cmode"] == ["0"]


def test_simple_search_with_scope_cinii(make_client) -> None:
    client, log = make_client(_search_handler)
    client.search("深層学習", scope=Scope.CINII)
    p = _params(log.requests[0])
    assert p["cmode"] == ["5"]
    assert p["kywd"] == ["深層学習"]


# ---------------------------------------------------------------------------
# Advanced search — local
# ---------------------------------------------------------------------------

def test_advanced_search_emits_field_pair(make_client) -> None:
    client, log = make_client(_search_handler)
    q = SearchQuery().title("Python")
    client.search(q)
    p = _params(log.requests[0])
    assert p["kywd1_exp"] == ["Python"]
    assert p["con1_exp"] == ["titlekey_ja"]
    assert p["smode"] == ["1"]


def test_advanced_search_year_range_and_media(make_client) -> None:
    client, log = make_client(_search_handler)
    q = (SearchQuery()
         .title("Python")
         .year_range(2022, 2024)
         .media(MediaType.BOOK))
    client.search(q)
    p = _params(log.requests[0])
    assert p["year1_exp"] == ["2022"]
    assert p["year2_exp"] == ["2024"]
    assert p["file_exp"] == ["1"]


def test_advanced_search_with_op_chain(make_client) -> None:
    client, log = make_client(_search_handler)
    q = (SearchQuery()
         .title("ML")
         .author("斎藤", op=BoolOp.AND)
         .add(SearchField.PUBLISHER, "丸善", op=BoolOp.OR))
    client.search(q)
    p = _params(log.requests[0])
    assert p["kywd1_exp"] == ["ML"]
    assert p["kywd2_exp"] == ["斎藤"]
    assert p["op2_exp"] == ["AND"]
    assert p["kywd3_exp"] == ["丸善"]
    assert p["op3_exp"] == ["OR"]
    # The first condition has no op_exp (it's the anchor).
    assert "op1_exp" not in p


def test_sort_and_page_size_are_serialised(make_client) -> None:
    client, log = make_client(_search_handler)
    q = (SearchQuery()
         .title("X")
         .sorted_by(Sort.AUTHOR_ASC)
         .per_page(50))
    client.search(q)
    p = _params(log.requests[0])
    assert p["sort_exp"] == ["3"]
    assert p["disp_exp"] == ["50"]


# ---------------------------------------------------------------------------
# Advanced search — CiNii (different parameter names)
# ---------------------------------------------------------------------------

def test_cinii_warns_on_unsupported_media_type(make_client, recwarn) -> None:
    """CiNii only accepts BOOK (1) and SERIAL (5).  Passing BOOK_JA (2) or
    similar must produce a UserWarning, not a silent drop."""
    client, _log = make_client(_search_handler)
    q = (SearchQuery()
         .title("X")
         .media(MediaType.BOOK_JA, MediaType.BOOK, MediaType.EBOOK)
         .in_cinii())
    client.search(q)
    warnings_text = " ".join(str(w.message) for w in recwarn.list)
    assert "BOOK_JA" in warnings_text and "EBOOK" in warnings_text


def test_cinii_warns_on_unsupported_search_field(make_client, recwarn) -> None:
    """``SearchField.SUBJECT`` is supported in CiNii; ``CALL_NO`` is not.
    The unsupported field must trigger a warning instead of being dropped."""
    client, _ = make_client(_search_handler)
    q = (SearchQuery()
         .title("ML")
         .call_no("007.1")
         .in_cinii())
    client.search(q)
    warnings_text = " ".join(str(w.message) for w in recwarn.list)
    assert "CALL_NO" in warnings_text


def test_cinii_accepted_media_still_serialised(make_client) -> None:
    """Mixed accepted+rejected media types: the accepted ones still go out."""
    import warnings as _w
    client, log = make_client(_search_handler)
    q = (SearchQuery()
         .title("X")
         .media(MediaType.BOOK_JA, MediaType.BOOK)  # 2 (drop), 1 (keep)
         .in_cinii())
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        client.search(q)
    p = _params(log.requests[0])
    assert p["ciniibooks_file_exp"] == ["1"]


def test_cinii_advanced_uses_ciniibooks_suffixed_params(make_client) -> None:
    """Spec §2.14 — CiNii fields end with ``_ciniibooks``.  Local-flavoured
    names must NOT leak through when scope is CINII."""
    client, log = make_client(_search_handler)
    q = (SearchQuery()
         .title("深層学習")
         .year_range(2020, 2024)
         .in_cinii())
    client.search(q)
    p = _params(log.requests[0])
    assert p["cmode"] == ["5"]
    assert p["titlekey_ja_ciniibooks"] == ["深層学習"]
    assert p["year1_ciniibooks"] == ["2020"]
    assert p["year2_ciniibooks"] == ["2024"]
    # ``in_cinii()`` auto-converts Sort to CiniiSort.YEAR_DESC (value 3).
    assert p["sort_ciniibooks"] == [str(int(CiniiSort.YEAR_DESC))]
    # Local-flavoured keys must NOT appear.
    assert "kywd1_exp" not in p
    assert "year1_exp" not in p


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_next_page_uses_amode_22_and_carries_opkey(make_client) -> None:
    client, log = make_client(_search_handler)
    result = client.search("X")
    log.requests.clear()
    # Public API exercises the same wire path as ``next_page()``.
    page2 = result.start_at(21)
    p = _params(log.requests[0])
    assert p["amode"] == ["22"]
    assert p["start"] == ["21"]
    assert p["opkey"] == [result.opkey]
    assert page2 is not None


def test_start_at_rejects_zero_or_negative(make_client) -> None:
    client, log = make_client(_search_handler)
    result = client.search("X")
    import pytest as _pytest
    with _pytest.raises(ValueError):
        result.start_at(0)
    with _pytest.raises(ValueError):
        result.start_at(-1)


# ---------------------------------------------------------------------------
# Refine (facet application)
# ---------------------------------------------------------------------------

def test_refine_uses_amode_23_with_fc_val_encoding(make_client) -> None:
    """Spec §6.2 — ``fc_val=<type>#@#<value>`` repeated for each filter."""
    client, log = make_client(_search_handler)
    result = client.search("X")
    log.requests.clear()
    result.refine(datatype="10", publisher="丸善出版")
    req = log.requests[0]
    p = _params(req)
    assert p["amode"] == ["23"]
    assert p["opkey"] == [result.opkey]
    fc_vals = set(p.get("fc_val", []))
    assert "datatype#@#10" in fc_vals
    assert "publisher#@#丸善出版" in fc_vals


def test_refine_repeats_fc_val_for_list_values(make_client) -> None:
    client, log = make_client(_search_handler)
    result = client.search("X")
    log.requests.clear()
    result.refine(datatype=["10", "19"])
    fc_vals = set(_params(log.requests[0]).get("fc_val", []))
    assert fc_vals == {"datatype#@#10", "datatype#@#19"}


# ---------------------------------------------------------------------------
# SearchResult.next_page() guard
# ---------------------------------------------------------------------------

def test_detached_search_result_refuses_to_navigate() -> None:
    """SearchResult constructed outside a client must not pretend to page."""
    from kuopac.models import SearchResult
    r = SearchResult(
        books=[], total=0, opkey="B1", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
        query_summary="", raw_url="",
    )
    import pytest as _pytest
    with _pytest.raises(RuntimeError):
        r.next_page()
    with _pytest.raises(RuntimeError):
        r.refine(datatype="10")
    with _pytest.raises(RuntimeError):
        r.load_holdings()
