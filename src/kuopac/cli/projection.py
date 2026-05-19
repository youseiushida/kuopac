"""``--fields`` projection for CLI output.

Supports dot notation with ``[]`` for list traversal::

    bibid
    title
    ids.isbn
    authors[].name
    authors[].auid
    holdings[].location
"""
from __future__ import annotations

from typing import Any


def parse_fields(spec: str | None) -> list[list[str]] | None:
    """Split a comma-separated ``--fields`` value into path tokens.

    Returns ``None`` if the spec is empty so callers can fall through to
    "no projection".  Each path is a list of segments where ``[]`` is its own
    segment (a list-flatten marker)::

        "authors[].name" -> ["authors", "[]", "name"]
    """
    if not spec:
        return None
    paths: list[list[str]] = []
    for raw in spec.split(","):
        token = raw.strip()
        if not token:
            continue
        parts: list[str] = []
        for piece in token.split("."):
            sub = piece
            while sub.endswith("[]"):
                if sub[:-2]:
                    parts.append(sub[:-2])
                parts.append("[]")
                sub = ""
            if sub:
                parts.append(sub)
        paths.append(parts)
    return paths or None


def _gather(node: Any, path: list[str], idx: int) -> Any:
    """Walk one path token at a time. Lists hit by ``[]`` flatten into output."""
    if node is None or idx == len(path):
        return node
    seg = path[idx]
    if seg == "[]":
        if not isinstance(node, list):
            return None
        return [_gather(item, path, idx + 1) for item in node]
    if isinstance(node, dict):
        return _gather(node.get(seg), path, idx + 1)
    return None


def project(data: Any, fields: list[list[str]] | None) -> Any:
    """Apply a parsed field spec to a serialised dict (or list thereof).

    For each path, store the final value under its joined dotted name.  Mirrors
    ``jq -r '.a, .b.c'`` style output but stays JSON-shaped.
    """
    if not fields:
        return data
    if isinstance(data, list):
        return [project(item, fields) for item in data]
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for path in fields:
        key = "".join(
            seg if seg == "[]" else (f".{seg}" if i else seg)
            for i, seg in enumerate(path)
        )
        out[key] = _gather(data, path, 0)
    return out
