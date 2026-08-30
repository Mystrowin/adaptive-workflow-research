"""Canonical save/load/hash helpers for future benchmark router calibration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..statistics import RoutingStatistics


def rows_from_statistics(statistics: RoutingStatistics) -> list[dict[str, Any]]:
    return [asdict(row) for row in statistics._rows]


def router_state_hash(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def save_router_state(path: Path, statistics: RoutingStatistics) -> str:
    rows = rows_from_statistics(statistics)
    encoded = json.dumps(
        {"schema_version": 1, "rows": rows, "sha256": router_state_hash(rows)},
        indent=2,
        sort_keys=True,
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded + "\n", encoding="utf-8")
    temporary.replace(path)
    return router_state_hash(rows)


def load_router_state(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("rows"), list):
        raise ValueError("router state schema is unsupported")
    rows = [dict(row) for row in payload["rows"]]
    if payload.get("sha256") != router_state_hash(rows):
        raise ValueError("router state checksum mismatch")
    return rows
