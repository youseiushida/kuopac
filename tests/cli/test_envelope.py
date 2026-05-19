"""Envelope shape — single / listing / error."""
from __future__ import annotations

from kuopac.cli.formatters._envelope import error, listing, single


def test_single_envelope() -> None:
    e = single("Foo", {"a": 1})
    assert e == {"type": "Foo", "schema_version": "1", "data": {"a": 1}}


def test_single_envelope_with_meta() -> None:
    e = single("Foo", {"a": 1}, meta={"requests": []})
    assert e["_meta"] == {"requests": []}


def test_listing_envelope_uses_list_suffix() -> None:
    e = listing("Book", [{"x": 1}, {"x": 2}], total=999)
    assert e["type"] == "BookList"
    assert e["count"] == 2
    assert e["total"] == 999


def test_error_envelope() -> None:
    e = error("PARSE_ERROR", "boom", request_url="http://x", http_status=200)
    assert e["type"] == "Error"
    assert e["error"]["code"] == "PARSE_ERROR"
    assert e["error"]["request_url"] == "http://x"
    assert e["error"]["http_status"] == 200
