"""``SearchQuery`` builder invariants — pure dataclass logic."""
from __future__ import annotations

import pytest

from kuopac.enums import BoolOp, CiniiSort, MediaType, Scope, SearchField, Sort
from kuopac.query import SearchQuery


def test_chained_helpers_create_conditions_in_order() -> None:
    q = SearchQuery().title("a").author("b")
    assert len(q.conditions) == 2
    assert q.conditions[0].field is SearchField.TITLE
    assert q.conditions[0].keyword == "a"
    assert q.conditions[1].field is SearchField.AUTHOR
    assert q.conditions[1].keyword == "b"


def test_default_op_is_and() -> None:
    q = SearchQuery().title("a").author("b")
    assert q.conditions[1].op is BoolOp.AND


def test_explicit_op_overrides_default() -> None:
    q = SearchQuery().title("a").author("b", op=BoolOp.OR)
    assert q.conditions[1].op is BoolOp.OR


def test_kuline_three_condition_cap() -> None:
    q = SearchQuery().title("a").author("b").publisher("c")
    with pytest.raises(ValueError):
        q.subject("d")


def test_year_range_sets_both_endpoints() -> None:
    q = SearchQuery().year_range(2020, 2024)
    assert q.year_from == 2020
    assert q.year_to == 2024


def test_year_range_accepts_one_sided() -> None:
    q = SearchQuery().year_range(year_to=2024)
    assert q.year_from is None
    assert q.year_to == 2024


def test_media_accumulates() -> None:
    q = SearchQuery().media(MediaType.BOOK).media(MediaType.EBOOK)
    assert q.media_types == [MediaType.BOOK, MediaType.EBOOK]


def test_in_cinii_auto_converts_default_sort() -> None:
    """If the caller hasn't picked a CiNii-specific sort, ``in_cinii()`` must
    swap the local default for the CiNii default — otherwise the wire layer
    sends the wrong numeric code."""
    q = SearchQuery().in_cinii()
    assert q.scope is Scope.CINII
    assert isinstance(q.sort, CiniiSort)
    assert q.sort is CiniiSort.YEAR_DESC


def test_in_cinii_preserves_explicit_cinii_sort() -> None:
    q = SearchQuery().sorted_by(CiniiSort.HOLDINGS_DESC).in_cinii()
    assert q.sort is CiniiSort.HOLDINGS_DESC


def test_in_local_reverses_scope() -> None:
    q = SearchQuery().in_cinii().in_local()
    assert q.scope is Scope.LOCAL
    assert isinstance(q.sort, Sort)


def test_per_page_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        SearchQuery().per_page(0)
    with pytest.raises(ValueError):
        SearchQuery().per_page(-5)


def test_per_page_assigns_page_size() -> None:
    assert SearchQuery().per_page(50).page_size == 50


def test_add_with_unknown_field_via_extra() -> None:
    """``add()`` accepts any ``SearchField`` enum value, including the ones
    without dedicated convenience helpers."""
    q = SearchQuery().add(SearchField.LCCN, "n2002000123")
    assert q.conditions[0].field is SearchField.LCCN


def test_department_and_collection_setters() -> None:
    q = SearchQuery().in_department("dept-code").in_collection("411")
    assert q.department == "dept-code"
    assert q.library_collection == "411"
