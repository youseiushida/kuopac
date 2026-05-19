"""Enum-level invariants — mainly ``DataType.parse``'s exception-swallowing."""
from __future__ import annotations

import pytest

from kuopac.enums import DataType


@pytest.mark.parametrize("raw,expected", [
    (None, DataType.UNKNOWN),
    ("", DataType.UNKNOWN),
    ("10", DataType.BOOK),
    ("19", DataType.EBOOK),
    ("20", DataType.SERIAL),
    (10, DataType.BOOK),
    (19, DataType.EBOOK),
    ("0", DataType.UNKNOWN),
    ("999", DataType.UNKNOWN),
    ("not a number", DataType.UNKNOWN),
    (object(), DataType.UNKNOWN),
])
def test_data_type_parse_never_raises(raw, expected) -> None:
    """``DataType.parse`` is best-effort — every input must map to *some* enum
    value rather than raising.  This is the contract the search parser leans
    on to keep going even when KULINE returns an unfamiliar datatype code."""
    assert DataType.parse(raw) is expected
