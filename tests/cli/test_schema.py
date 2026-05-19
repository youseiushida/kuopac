"""JSON Schema generation for the public dataclasses."""
from __future__ import annotations

import pytest

from kuopac.cli.schema_gen import all_schemas, list_types, schema_for


def test_every_public_type_resolves() -> None:
    schemas = all_schemas()
    assert set(schemas.keys()) == set(list_types())


def test_schema_for_book_has_required_fields() -> None:
    s = schema_for("Book")
    assert s["$schema"].startswith("https://json-schema.org/")
    props = s["properties"]
    assert "ids" in props
    assert "data_type" in props
    # IntEnum should become a $ref into $defs
    assert "$ref" in props["data_type"]
    # required list excludes default_factory fields like ``holdings``
    assert "ids" in s["required"]
    assert "holdings" not in s["required"]


def test_schema_for_search_result_skips_private_client() -> None:
    s = schema_for("SearchResult")
    assert "_client" not in s["properties"]
    # required reflects positional fields
    assert "books" in s["required"]


def test_enum_appears_in_defs() -> None:
    s = schema_for("Book")
    defs = s["$defs"]
    assert "DataType" in defs
    assert defs["DataType"]["enum"] == ["BOOK", "EBOOK", "SERIAL", "UNKNOWN"]


def test_unknown_type_raises() -> None:
    with pytest.raises(KeyError):
        schema_for("NoSuchType")
