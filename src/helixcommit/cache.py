"""Lightweight JSON-backed disk cache."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional


class DiskCache:
    """A minimal file-system cache with TTL semantics.

    Values are stored as JSON. Keys are translated into file paths relative to
    ``cache_dir`` and may contain forward slashes to create namespaces.
    """

    def __init__(self, cache_dir: Path, *, ttl_seconds: int) -> None:
        self.cache_dir = cache_dir
        self.ttl_seconds = max(0, ttl_seconds)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value for ``key`` if present and fresh."""
        path = self._path_for_key(key)
        if not path.exists():
            return None
        if self.ttl_seconds and self._is_expired(path):
            self._safe_remove(path)
            return None
        try:
            with path.open("r", encoding="utf-8") as file_handle:
                return json.load(file_handle)
        except (OSError, ValueError):
            self._safe_remove(path)
            return None

    def set(self, key: str, value: Any) -> None:
        """Persist ``value`` for ``key``."""
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False
            ) as tmp_file:
                json.dump(value, tmp_file, ensure_ascii=False)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(Path(tmp_file.name), path)
        except OSError:
            self._safe_remove(path)

    def _path_for_key(self, key: str) -> Path:
        key_path = key.strip("/").split("/")
        return self.cache_dir.joinpath(*key_path).with_suffix(".json")

    def _is_expired(self, path: Path) -> bool:
        if self.ttl_seconds <= 0:
            return False
        try:
            modified = path.stat().st_mtime
        except OSError:
            return True
        return (time.time() - modified) > self.ttl_seconds

    @staticmethod
    def _safe_remove(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass


__all__ = ["DiskCache"]

