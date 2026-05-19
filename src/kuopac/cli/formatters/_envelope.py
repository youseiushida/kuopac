"""JSON envelope helpers (``docs/cli-design.md`` §6)."""
from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1"


def single(obj_type: str, data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Envelope a single object."""
    out: dict[str, Any] = {
        "type": obj_type,
        "schema_version": SCHEMA_VERSION,
        "data": data,
    }
    if meta:
        out["_meta"] = meta
    return out


def listing(
    item_type: str,
    items: list[Any],
    *,
    total: int | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Envelope a list of items.

    ``item_type`` is the dataclass name of one element (e.g. ``"Book"``); the
    envelope's ``type`` becomes ``"BookList"``.
    """
    out: dict[str, Any] = {
        "type": f"{item_type}List",
        "schema_version": SCHEMA_VERSION,
        "data": items,
        "count": len(items),
    }
    if total is not None:
        out["total"] = total
    if meta:
        out["_meta"] = meta
    return out


def error(
    code: str,
    message: str,
    *,
    request_url: str | None = None,
    http_status: int | None = None,
) -> dict[str, Any]:
    """Envelope an error (``docs/cli-design.md`` §6.3)."""
    err: dict[str, Any] = {"code": code, "message": message}
    if request_url is not None:
        err["request_url"] = request_url
    if http_status is not None:
        err["http_status"] = http_status
    return {
        "type": "Error",
        "schema_version": SCHEMA_VERSION,
        "error": err,
    }
