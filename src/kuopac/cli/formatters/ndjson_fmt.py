"""``--format=ndjson`` writer: one JSON object per line.

For list-shaped results the envelope is *not* emitted; only the items.  For
single-object results, the (single) ``data`` object is emitted as one line so
the stream remains valid NDJSON for downstream consumers.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Iterable, TextIO


def write_items(items: Iterable[Any], *, stream: TextIO | None = None) -> int:
    """Write each item as one JSON line.  Returns the number of lines written."""
    out = stream or sys.stdout
    count = 0
    for item in items:
        json.dump(item, out, ensure_ascii=False)
        out.write("\n")
        out.flush()
        count += 1
    return count


def write_envelope(envelope: dict[str, Any], *, stream: TextIO | None = None) -> int:
    """Unwrap an already-built envelope and emit just its ``data`` payload."""
    data = envelope.get("data")
    if isinstance(data, list):
        return write_items(data, stream=stream)
    out = stream or sys.stdout
    json.dump(data, out, ensure_ascii=False)
    out.write("\n")
    out.flush()
    return 1
