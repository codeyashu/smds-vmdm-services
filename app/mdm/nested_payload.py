"""Nested dict path read/write — mirrors portal nested-payload."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def read_nested_value(obj: dict[str, Any], path: str) -> Any:
    current: Any = obj
    for part in path.split("."):
        if current is None or not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def set_nested_value(obj: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    next_obj = deepcopy(obj)
    parts = path.split(".")
    cur: dict[str, Any] = next_obj
    for part in parts[:-1]:
        child = cur.get(part)
        if child is None or not isinstance(child, dict):
            child = {}
            cur[part] = child
        cur = child
    cur[parts[-1]] = value
    return next_obj
