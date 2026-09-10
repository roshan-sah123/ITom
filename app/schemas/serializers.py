"""Plain-dict serializers for SQLAlchemy ORM rows.

WHY THIS FILE EXISTS
--------------------
FastAPI serialises endpoint return values with Pydantic. Pydantic does not know
how to turn a SQLAlchemy ORM object into JSON, so any endpoint that returns
``ConfigurationItem`` objects inside a plain ``Dict[str, Any]`` fails with:

    PydanticSerializationError: Unable to serialize unknown type:
    <class 'app.models.ci.ConfigurationItem'>

That is exactly what broke ``GET /api/v1/cmdb/cis``, ``/intune/devices`` and
``/solarwinds/nodes`` - the three list endpoints the frontend depends on most.

These helpers convert ORM rows into JSON-safe dictionaries by reading the
mapped columns directly, so they stay correct if a column is added or renamed.

Design notes
------------
* UUIDs become strings, datetimes become ISO-8601 strings.
* Relationship attributes are never touched, so no lazy-load is triggered and
  no ``MissingGreenlet`` error can occur on an async session.
* Anything already a plain dict is passed through untouched.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect as sa_inspect


def _json_safe(value: Any) -> Any:
    """Convert a single column value into something JSON serialisable."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def orm_to_dict(row: Any) -> Any:
    """Convert one ORM row into a JSON-safe dict.

    Non-ORM values (plain dicts, primitives) are returned unchanged, so this is
    safe to apply to a mixed or already-serialised collection.
    """
    if row is None:
        return None
    if isinstance(row, dict):
        return {str(k): _json_safe(v) for k, v in row.items()}

    try:
        mapper = sa_inspect(type(row))
        columns = [c.key for c in mapper.mapper.column_attrs]
    except Exception:
        # Not a mapped ORM class - fall back to whatever it is.
        return _json_safe(row)

    return {name: _json_safe(getattr(row, name, None)) for name in columns}


def orm_list_to_dicts(rows: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Convert a list of ORM rows into a list of JSON-safe dicts."""
    if not rows:
        return []
    return [orm_to_dict(row) for row in rows]
