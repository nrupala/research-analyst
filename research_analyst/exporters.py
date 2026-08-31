"""Typed-export layer — machine-consumable payloads for RA.

Turns the Pydantic API contract into three interchangeable artifacts:
  * JSON Schema   — canonical, versioned schema per endpoint payload
  * TypeScript    — ``.d.ts`` definitions auto-generated from the same models
  * XML           — content-negotiated XML serialization of the same payloads

The export layer honors the wire-format guarantee (see api_models.py): every
format is derived from the SAME typed model, so JSON / TS / XML never drift.
"""
# Module: research_analyst/exporters.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ForwardRef, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from .api_models import API_RESPONSE_MODELS, SCHEMA_VERSION

# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------


def json_schema_for(model: type[BaseModel], schema_id: str) -> dict[str, Any]:
    """Canonical JSON Schema for a Pydantic API model (draft 2020-12)."""
    schema = model.model_json_schema()
    schema["$id"] = schema_id
    schema["$comment"] = (
        f"schema_version: {SCHEMA_VERSION}; generated from "
        f"{model.__module__}.{model.__name__} — do not edit by hand"
    )
    return schema


def json_schemas_all() -> dict[str, dict[str, Any]]:
    """JSON Schema for every public API endpoint payload."""
    return {
        name: json_schema_for(model, f"https://ra.devinfo.dev/schemas/{name}.schema.json")
        for name, model in API_RESPONSE_MODELS.items()
    }


# ---------------------------------------------------------------------------
# TypeScript definitions
# ---------------------------------------------------------------------------

_TS_UNKNOWN = "unknown"


def _ts_literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return repr(value)


def _ts_type(annotation: Any, walker: _TSWalker) -> str:
    origin = get_origin(annotation)
    if origin is None:
        # Plain type (or an unresolved forward ref -> conservative unknown).
        if isinstance(annotation, ForwardRef):
            return _TS_UNKNOWN
        try:
            if annotation is Any:
                return _TS_UNKNOWN
            if annotation is type(None):
                return "null"
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                walker.visit(annotation)
                return annotation.__name__
            if isinstance(annotation, type) and issubclass(annotation, Enum):
                return " | ".join(_ts_literal(m.value) for m in annotation)
            if annotation is bool:
                return "boolean"
            if annotation is int or annotation is float or annotation is Decimal:
                return "number"
            if annotation is str:
                return "string"
            if annotation is bytes:
                return "string"
            if annotation is date or annotation is datetime:
                return "string"
            return _TS_UNKNOWN
        except TypeError:
            return _TS_UNKNOWN

    if origin is list or origin is set or origin is frozenset:
        (item,) = get_args(annotation)
        return f"{_ts_type(item, walker)}[]"
    if origin is dict:
        _key, value = get_args(annotation)
        return f"Record<string, {_ts_type(value, walker)}>"
    if origin is tuple:
        return "[" + ", ".join(_ts_type(a, walker) for a in get_args(annotation)) + "]"
    # Union[...] / Optional[...] — Pydantic v2 uses (typing.Union, types.UnionType)
    if origin.__name__ == "Union" or origin.__name__ == "UnionType":
        args = get_args(annotation)
        parts = [_ts_type(a, walker) for a in args]
        return "(" + " | ".join(parts) + ")" if len(parts) > 1 else parts[0]
    return _TS_UNKNOWN


def _ts_field_type(annotation: Any, walker: _TSWalker) -> tuple[str, bool]:
    """Return (ts_type, is_optional) for a field annotation."""
    origin = get_origin(annotation)
    if origin is not None and (origin.__name__ == "Union" or origin.__name__ == "UnionType"):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) != len(get_args(annotation)) and args:
            inner = _ts_type(args[0], walker) if len(args) == 1 else _ts_type(annotation, walker)
            if len(args) > 1:
                inner = inner.strip("()")
            return f"{inner} | null", True
    return _ts_type(annotation, walker), False


class _TSWalker:
    """Collects model closure (children first) and emits deterministic .d.ts."""

    def __init__(self) -> None:
        self._ordered: list[type[BaseModel]] = []
        self._seen: set[type[BaseModel]] = set()

    def visit(self, model: type[BaseModel]) -> None:
        if model in self._seen:
            return
        self._seen.add(model)
        hints = self._resolved_hints(model)
        for name, field in model.model_fields.items():
            _ts_type(hints.get(name, field.annotation), self)
        self._ordered.append(model)

    @staticmethod
    def _resolved_hints(model: type[BaseModel]) -> dict[str, Any]:
        """Resolve forward refs (models.py declares some fields before their
        type is defined; Pydantic's partial rebuild leaves ForwardRefs)."""
        try:
            return get_type_hints(model)
        except (NameError, TypeError):
            return {}

    def render(self, extra_models: list[type[BaseModel]] | None = None) -> str:
        for model in extra_models or []:
            self.visit(model)
        lines = [
            "// Auto-generated from research_analyst.api_models (do not edit by hand).",
            f"// schema_version: {SCHEMA_VERSION}",
            "",
            f'export const RA_SCHEMA_VERSION = "{SCHEMA_VERSION}";',
            "",
        ]
        for model in self._ordered:
            hints = self._resolved_hints(model)
            fields: list[str] = []
            for name, field in model.model_fields.items():
                ts_type, optional = _ts_field_type(hints.get(name, field.annotation), self)
                # Normalize a "| null" suffix into the optional marker.
                nullable = ts_type.endswith(" | null")
                if nullable:
                    ts_type = ts_type.removesuffix(" | null").strip()
                opt = optional or nullable
                ts_type = f"{ts_type} | null" if nullable else ts_type
                decl = f"  {name}{'?' if opt else ''}: {ts_type};"
                fields.append(decl)
            if not fields:
                fields = ["  [key: string]: unknown;"]
            lines.append(f"export interface {model.__name__} {{")
            lines.extend(fields)
            lines.append("}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def ts_definitions() -> str:
    """TypeScript definitions for every public API payload + dependencies."""
    walker = _TSWalker()
    return walker.render(list(API_RESPONSE_MODELS.values()))


# ---------------------------------------------------------------------------
# XML serialization (same payload, same guarantee)
# ---------------------------------------------------------------------------

_XML_TAG_SAFE = re.compile(r"[^\w.\-]")


def _xml_tag(key: str) -> str:
    return _XML_TAG_SAFE.sub("_", key)


def _xml_add(parent: ET.Element, key: str, value: Any) -> None:
    tag = _xml_tag(key)
    if value is None:
        el = ET.SubElement(parent, tag)
        el.set("null", "true")
        return
    if isinstance(value, dict):
        el = ET.SubElement(parent, tag)
        for k, v in value.items():
            _xml_add(el, k, v)
        return
    if isinstance(value, (list, tuple)):
        el = ET.SubElement(parent, tag)
        for item in value:
            _xml_add(el, "item", item)
        return
    if isinstance(value, bool):
        ET.SubElement(parent, tag).text = "true" if value else "false"
        return
    if isinstance(value, (int, float, Decimal)):
        ET.SubElement(parent, tag).text = str(value)
        return
    ET.SubElement(parent, tag).text = str(value)


def xml_from_dict(data: dict[str, Any], root: str) -> str:
    """Serialize a JSON-safe dict (model_dump(mode='json')) to XML."""
    root_el = ET.Element(_xml_tag(root))
    for k, v in data.items():
        _xml_add(root_el, k, v)
    return ET.tostring(root_el, encoding="unicode", xml_declaration=True)
