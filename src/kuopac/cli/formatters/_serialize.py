"""dataclass / Enum / nested container → JSON-safe dict.

Concentrates every CLI-specific serialisation rule in one place so commands
don't reach into model internals.  In particular:

* ``Enum`` / ``IntEnum`` become their **name** (``"BOOK"``, ``"LOCAL"``).
* Private fields (``_client`` etc.) are dropped.
* ``Holding.status_query`` is reduced to ``{"blipkey": "..."}`` since the rest
  of the AJAX query payload leaks internal Django/JS plumbing.
* ``Supplementary.raw_text`` is dropped (the structured ``synopsis`` + ``toc``
  carry the same information without the noisy boilerplate).
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

# Field-specific overrides keyed by ``(dataclass_name, field_name)``.
_SKIP_FIELDS: set[tuple[str, str]] = {
    ("Supplementary", "raw_text"),
}


def to_jsonable(obj: Any) -> Any:
    """Recursively convert ``obj`` into JSON-safe primitives."""
    if obj is None:
        return None
    # IntEnum is a subclass of int — check Enum *before* primitive types.
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if is_dataclass(obj):
        cls_name = type(obj).__name__
        out: dict[str, Any] = {}
        for f in fields(obj):
            if f.name.startswith("_"):
                continue
            if (cls_name, f.name) in _SKIP_FIELDS:
                continue
            value = getattr(obj, f.name)
            if cls_name == "Holding" and f.name == "status_query" and value is not None:
                out[f.name] = {"blipkey": value.blipkey}
                continue
            out[f.name] = to_jsonable(value)
        # Computed convenience fields hoisted from dataclass @property's.
        if cls_name == "Holding":
            out["availability"] = obj.availability
        elif cls_name in ("Book", "BookDetail"):
            out["bibid"] = obj.bibid
            out["ncid"] = obj.ncid
            if cls_name == "BookDetail":
                out["isbn"] = obj.isbn
        return out
    # Last resort: stringify.
    return str(obj)
