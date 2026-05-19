"""Output dispatcher.

``write(envelope, cfg)`` picks the right writer based on ``cfg.format`` and
applies any post-serialisation transformations (field projection).

Field projection in NDJSON/TSV applies to each *item* of the natural stream
(e.g. ``SearchResult.books``), not to the envelope dict; that matches what
shell pipelines like ``| jq '.bibid'`` expect.
"""
from __future__ import annotations

from typing import Any

from ..config import RunConfig
from ..projection import parse_fields, project
from . import json_fmt, ndjson_fmt, table, tsv, yaml_fmt
from ._envelope import error as error_envelope, listing, single

__all__ = [
    "write",
    "single",
    "listing",
    "error_envelope",
]


def _stream_items(envelope: dict[str, Any]) -> list[Any]:
    """Decide what to stream for list-style output (NDJSON / TSV).

    Falls through with a single-item list when the envelope wraps a single
    object so callers always get a homogeneous iterable.
    """
    t = envelope.get("type", "")
    data = envelope.get("data")
    if t == "SearchResult" and isinstance(data, dict) and "books" in data:
        return list(data.get("books") or [])
    if t == "HoldingMap" and isinstance(data, dict):
        # Flatten the {bibid: [...]} map into rows tagged with bibid.
        rows: list[Any] = []
        for bibid, copies in data.items():
            for c in copies or []:
                rows.append({"bibid": bibid, **c})
        return rows
    if t == "FacetMap" and isinstance(data, dict):
        rows = []
        for type_name, info in data.items():
            for v in (info or {}).get("values", []):
                rows.append({"facet_type": type_name, **v})
        return rows
    if isinstance(data, list):
        return data
    if data is None:
        return []
    return [data]


def _apply_projection_to_items(items: list[Any], cfg: RunConfig) -> list[Any]:
    if not cfg.fields:
        return items
    paths = parse_fields(",".join(cfg.fields))
    if paths is None:
        return items
    return [project(item, paths) for item in items]


def _apply_projection_to_envelope(envelope: dict[str, Any], cfg: RunConfig) -> dict[str, Any]:
    if not cfg.fields:
        return envelope
    paths = parse_fields(",".join(cfg.fields))
    if paths is None:
        return envelope
    data = envelope.get("data")
    new = dict(envelope)
    if isinstance(data, list):
        new["data"] = [project(item, paths) for item in data]
        new["count"] = len(new["data"])
    else:
        new["data"] = project(data, paths)
    return new


def write(envelope: dict[str, Any], cfg: RunConfig) -> None:
    """Render the envelope according to ``cfg.format``.

    The caller is responsible for adding ``cfg.meta()`` to the envelope before
    invoking this function.
    """
    fmt = cfg.format
    if fmt == "json":
        json_fmt.write(_apply_projection_to_envelope(envelope, cfg))
        return
    if fmt == "ndjson":
        items = _apply_projection_to_items(_stream_items(envelope), cfg)
        ndjson_fmt.write_items(items)
        return
    if fmt == "yaml":
        yaml_fmt.write(_apply_projection_to_envelope(envelope, cfg))
        return
    if fmt == "tsv":
        items = _apply_projection_to_items(_stream_items(envelope), cfg)
        tsv.write([i for i in items if isinstance(i, dict)])
        return
    # default: table
    table.write(_apply_projection_to_envelope(envelope, cfg), no_color=cfg.no_color)
