"""dataclass → JSON Schema generator.

Covers exactly the surface that the kuopac models expose:
* dataclass nesting
* ``Enum`` / ``IntEnum`` → ``{"enum": [name, ...]}``
* ``list[T]`` / ``T | None`` / ``str | None`` (PEP 604 unions)
* ``dict[K, V]`` → ``additionalProperties``
"""
from __future__ import annotations

import dataclasses
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints

from .. import models as kuopac_models

PUBLIC_TYPES = (
    "AuthorHeading",
    "BibIdentifiers",
    "BLStatusQuery",
    "Book",
    "BookDetail",
    "ChildBib",
    "Classification",
    "ExternalLinks",
    "FacetInfo",
    "FacetValue",
    "Holding",
    "ParentSeries",
    "Publication",
    "RdaTypes",
    "SearchResult",
    "SpellCorrection",
    "Subject",
    "Suggestion",
    "Supplementary",
)


def _is_union(origin: Any) -> bool:
    return origin is Union or origin is types.UnionType


def type_to_schema(tp: Any, defs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if tp is type(None):
        return {"type": "null"}
    if tp is str:
        return {"type": "string"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}

    origin = get_origin(tp)
    args = get_args(tp)

    if origin is None and isinstance(tp, type):
        if issubclass(tp, Enum):
            ref = tp.__name__
            if ref not in defs:
                defs[ref] = {
                    "title": ref,
                    "type": "string",
                    "enum": [e.name for e in tp],
                }
            return {"$ref": f"#/$defs/{ref}"}
        if is_dataclass(tp):
            ref = tp.__name__
            if ref not in defs:
                defs[ref] = _dataclass_schema(tp, defs)
            return {"$ref": f"#/$defs/{ref}"}

    if origin is list:
        return {"type": "array", "items": type_to_schema(args[0], defs)}
    if origin is tuple:
        return {"type": "array", "items": type_to_schema(args[0], defs)}
    if origin is dict:
        return {
            "type": "object",
            "additionalProperties": type_to_schema(args[1], defs),
        }
    if _is_union(origin):
        non_none = [a for a in args if a is not type(None)]
        sub = [type_to_schema(a, defs) for a in non_none]
        if type(None) in args:
            sub.append({"type": "null"})
        if len(sub) == 1:
            return sub[0]
        return {"oneOf": sub}

    return {}


def _dataclass_schema(cls: type, defs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # Models reference ``KulineClient`` as a string forward-ref for cyclic
    # imports.  Inject a stub into the local namespace so ``get_type_hints``
    # resolves without pulling the client module in.
    try:
        hints = get_type_hints(cls, localns={"KulineClient": object})
    except Exception:  # noqa: BLE001 — partial resolution is better than failing
        hints = {}
    props: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for f in fields(cls):
        if f.name.startswith("_"):
            continue
        tp = hints.get(f.name, f.type)
        props[f.name] = type_to_schema(tp, defs)
        if (
            f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
        ):
            required.append(f.name)
    schema: dict[str, Any] = {
        "title": cls.__name__,
        "type": "object",
        "properties": props,
    }
    if required:
        schema["required"] = required
    return schema


def schema_for(name: str) -> dict[str, Any]:
    """Build a JSON Schema for one public type name."""
    cls = getattr(kuopac_models, name, None)
    if cls is None or not (is_dataclass(cls) or (isinstance(cls, type) and issubclass(cls, Enum))):
        raise KeyError(f"unknown type: {name!r}")
    defs: dict[str, dict[str, Any]] = {}
    if is_dataclass(cls):
        root = _dataclass_schema(cls, defs)
    else:  # Enum
        root = {"title": name, "type": "string", "enum": [e.name for e in cls]}
    # Pull the root out of $defs (avoids self-referential pointer at top level).
    defs.pop(name, None)
    out: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **root,
    }
    if defs:
        out["$defs"] = defs
    return out


def list_types() -> list[str]:
    return list(PUBLIC_TYPES)


def all_schemas() -> dict[str, dict[str, Any]]:
    """Render every public type's schema in one bundle (for ``manifest``)."""
    return {name: schema_for(name) for name in PUBLIC_TYPES}
