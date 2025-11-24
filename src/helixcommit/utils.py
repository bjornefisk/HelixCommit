"""Utility helpers for HelixCommit."""

from __future__ import annotations

import json
from typing import Any


def to_json(data: Any, *, indent: int = 2) -> str:
    """Serialize Python objects into JSON with relaxed defaults."""
    return json.dumps(data, indent=indent, sort_keys=True, default=str)


__all__ = ["to_json"]
