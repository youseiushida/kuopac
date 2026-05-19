"""``--format=tsv`` writer: header + tab-separated rows.

Requires a list-shaped envelope.  Field selection is mandatory when the
records contain nested objects; if ``--fields`` was not given the writer falls
back to the top-level scalar fields of the first item.
"""
from __future__ import annotations

import sys
from typing import Any, TextIO


def _coerce(value: Any) -> str:
    """Render one cell.  Lists/dicts collapse to JSON-ish text to stay one column."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(_coerce(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}={_coerce(v)}" for k, v in value.items())
    text = str(value)
    return text.replace("\t", " ").replace("\n", " ")


def write(items: list[dict[str, Any]], *, stream: TextIO | None = None) -> None:
    out = stream or sys.stdout
    if not items:
        return
    columns = list(items[0].keys())
    out.write("\t".join(columns) + "\n")
    for item in items:
        out.write("\t".join(_coerce(item.get(c)) for c in columns) + "\n")
