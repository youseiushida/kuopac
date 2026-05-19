"""Serialiser invariants — dataclass → JSON-safe dict."""
from __future__ import annotations

from kuopac.enums import DataType, Scope
from kuopac.models import (
    BibIdentifiers,
    BLStatusQuery,
    Book,
    Holding,
    Supplementary,
)
from kuopac.cli.formatters._serialize import to_jsonable
from kuopac.enums import SupplementarySource


def test_intenum_becomes_name() -> None:
    book = Book(
        ids=BibIdentifiers(bibid="BB1"),
        title="t", publisher_line="",
        data_type=DataType.EBOOK,
        detail_url="", list_index=1, scope=Scope.LOCAL,
    )
    out = to_jsonable(book)
    assert out["data_type"] == "EBOOK"
    assert out["scope"] == "LOCAL"


def test_book_hoists_bibid_and_ncid() -> None:
    book = Book(
        ids=BibIdentifiers(bibid="BB1", ncid="BD2"),
        title="t", publisher_line="",
        data_type=DataType.BOOK,
        detail_url="", list_index=1, scope=Scope.LOCAL,
    )
    out = to_jsonable(book)
    assert out["bibid"] == "BB1"
    assert out["ncid"] == "BD2"
    assert out["ids"]["bibid"] == "BB1"


def test_holding_status_query_is_simplified() -> None:
    h = Holding(
        location="loc", call_no="c",
        status_query=BLStatusQuery(blipkey="BL123", odrno="OT1"),
    )
    out = to_jsonable(h)
    assert out["status_query"] == {"blipkey": "BL123"}
    assert out["availability"] == "available_on_shelf"


def test_holding_online() -> None:
    h = Holding(online_url="https://x", online_label="eBook")
    out = to_jsonable(h)
    assert out["availability"] == "online"


def test_supplementary_drops_raw_text() -> None:
    sup = Supplementary(
        source=SupplementarySource.BOOKPLUS,
        synopsis="s", toc=["c1"],
        raw_text="<noisy raw text>",
    )
    out = to_jsonable(sup)
    assert "raw_text" not in out
    assert out["source"] == "BOOKPLUS"
    assert out["synopsis"] == "s"
    assert out["toc"] == ["c1"]


def test_private_fields_are_skipped() -> None:
    """``SearchResult._client`` must not leak into JSON."""
    from kuopac.models import SearchResult
    r = SearchResult(
        books=[], total=0, opkey="B1", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
        query_summary="", raw_url="",
    )
    r._client = object()  # sentinel — should not be serialised
    out = to_jsonable(r)
    assert "_client" not in out
