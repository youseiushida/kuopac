"""Live integration tests against the real KULINE server.

Each test pins **structural** invariants — endpoint reachability, response
shape, parser doesn't crash, round-trip identifier consistency.  Specific
hit counts, titles, or holding counts are explicitly *not* asserted: the
catalog is a moving dataset and value-based assertions would produce false
positives the moment a librarian re-shelves anything.

The tests are skipped by default; pass ``--live`` or set ``KUOPAC_LIVE=1``.
"""
from __future__ import annotations

import pytest

from kuopac import KulineClient, SearchQuery
from kuopac.enums import DataType, FacetType, Scope

pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# 1. Search endpoint produces a parseable, well-shaped response
# ---------------------------------------------------------------------------

def test_search_endpoint_parses(kuline: KulineClient) -> None:
    r = kuline.search("Python")
    # Threshold (not exact): an evergreen programming-language keyword at a
    # research-university library always returns hundreds of records.
    assert r.total >= 100, f"unexpectedly low hit count: {r.total}"
    assert r.books, "search returned zero books on page 1"
    assert r.opkey.startswith("B") and len(r.opkey) >= 10
    for b in r.books:
        # At least one identifier is required for any downstream operation.
        assert b.bibid or b.ncid
        assert b.title
        assert b.data_type is not DataType.UNKNOWN, (
            f"unrecognised datatype for {b.bibid!r} — KULINE may have added a new code"
        )


# ---------------------------------------------------------------------------
# 2. search → detail round-trip preserves identifier identity
# ---------------------------------------------------------------------------

def test_search_then_detail_round_trip(kuline: KulineClient) -> None:
    r = kuline.search("Python")
    book = next(
        (b for b in r.books if b.bibid and b.bibid.startswith(("BB", "EB"))),
        None,
    )
    if book is None:
        pytest.skip("no local-catalog book on page 1 — only CiNii-like records")
    detail = kuline.detail(book)
    assert detail.bibid == book.bibid
    assert detail.title
    assert detail.data_type is not DataType.UNKNOWN


# ---------------------------------------------------------------------------
# 3. Bulk holdings (1 POST + lazy CSRF) works against the real server
# ---------------------------------------------------------------------------

def test_load_holdings_attaches_copies_for_local_books(kuline: KulineClient) -> None:
    r = kuline.search("Python").load_holdings()
    local_books = [b for b in r.books if b.bibid and b.bibid.startswith("BB")]
    if not local_books:
        pytest.skip("no local BB-prefixed books in this page's results")
    # At least *some* physical books must come back with at least one Holding
    # row — if zero, either the localhold POST broke or CSRF preflight failed.
    with_holdings = [b for b in local_books if b.holdings]
    assert with_holdings, "localhold returned no copies for any local book"


# ---------------------------------------------------------------------------
# 4. Pagination yields distinct records (KULINE invariant)
# ---------------------------------------------------------------------------

def test_pagination_yields_distinct_records(kuline: KulineClient) -> None:
    r1 = kuline.search("Python")
    if not r1.has_next():
        pytest.skip("only one page of results")
    r2 = r1.next_page()
    assert r2 is not None
    p1 = {b.bibid for b in r1.books if b.bibid}
    p2 = {b.bibid for b in r2.books if b.bibid}
    overlap = p1 & p2
    assert not overlap, f"pagination returned duplicate bibids: {overlap}"


# ---------------------------------------------------------------------------
# 5. CiNii path: different params, NCID instead of bibid
# ---------------------------------------------------------------------------

def test_cinii_search_returns_ncid_not_bibid(kuline: KulineClient) -> None:
    q = SearchQuery().title("機械学習").in_cinii()
    r = kuline.search(q)
    assert r.scope is Scope.CINII
    assert r.total > 0, "CiNii returned zero hits for 機械学習 — surprising"
    for b in r.books:
        assert b.ncid, f"CiNii record missing ncid: {b}"
        # The audit fixed a bug where bibid leaked in; make sure it doesn't.
        assert b.bibid is None, (
            f"CiNii record unexpectedly has bibid={b.bibid!r} — list_bibid "
            f"input crept back into the CiNii layout?"
        )


# ---------------------------------------------------------------------------
# 6. Facets endpoint returns aggregate buckets
# ---------------------------------------------------------------------------

def test_facets_publisher_returns_buckets(kuline: KulineClient) -> None:
    r = kuline.search("Python")
    facets = kuline.facets(r, types=[FacetType.PUBLISHER])
    info = facets[FacetType.PUBLISHER]
    assert info.values, "facet=fpub returned an empty bucket list"
    # Total count across buckets should be positive and capped by the page-level total.
    total_counts = sum(v.count for v in info.values)
    assert total_counts > 0


# ---------------------------------------------------------------------------
# 7. Refine narrows the result set (or at minimum doesn't break)
# ---------------------------------------------------------------------------

def test_refine_does_not_grow_result_set(kuline: KulineClient) -> None:
    r = kuline.search("Python")
    refined = r.refine(datatype="10")  # 図書のみ
    # The narrowed total must be ≤ original. Equal is acceptable if every hit
    # is already 図書, but greater is a bug (or KULINE silently ignored the filter).
    assert refined.total <= r.total, (
        f"refine widened the result set: {r.total} → {refined.total}"
    )


# ---------------------------------------------------------------------------
# 8. Suggest endpoint shape
# ---------------------------------------------------------------------------

def test_suggest_returns_list_shape(kuline: KulineClient) -> None:
    out = kuline.suggest("機械")
    assert isinstance(out, list)
    # An evergreen prefix like 機械 should return *some* candidates, but we
    # don't assert specific terms (those drift as new books are catalogued).
    if out:
        assert all(isinstance(t, str) for t in out)
        assert all(t for t in out), "suggestion list contains empty strings"


# ---------------------------------------------------------------------------
# 9. did_you_mean endpoint at least responds (empty result is OK)
# ---------------------------------------------------------------------------

def test_did_you_mean_handles_zero_hits(kuline: KulineClient) -> None:
    r = kuline.search("zzz_unlikely_keyword_xyz_no_such_thing_9999")
    candidates = kuline.did_you_mean(r)
    # The endpoint must not raise. An empty list is a valid response.
    assert isinstance(candidates, list)


# ---------------------------------------------------------------------------
# 10. Detail page for a known classic ISBN resolves (Referer required)
# ---------------------------------------------------------------------------

# KULINE supports `--field isbn=...` searching.  Using ISBN→bibid resolution
# (instead of pinning a specific bibid) means we survive renumbering.  Pick a
# classic textbook that any research library would always carry; if KULINE
# doesn't have it, ``skip`` rather than fail.

_EVERGREEN_ISBN = "9784274068478"  # 計算機プログラムの構造と解釈 (SICP) Japanese ed.


def test_detail_for_evergreen_isbn_resolves(kuline: KulineClient) -> None:
    r = kuline.search(SearchQuery().isbn(_EVERGREEN_ISBN))
    if r.total == 0 or not r.books:
        pytest.skip(f"ISBN {_EVERGREEN_ISBN} not in KULINE — replace with another classic")
    book = r.books[0]
    detail = kuline.detail(book)
    # Detail must round-trip the bibid and produce a non-empty title; we don't
    # assert *which* title in case the cataloguer changes it.
    assert detail.bibid == book.bibid
    assert detail.title
    # ISBN survives the round trip (BBISBN row → BibIdentifiers.isbn).
    assert detail.isbn and detail.isbn.replace("-", "") == _EVERGREEN_ISBN
