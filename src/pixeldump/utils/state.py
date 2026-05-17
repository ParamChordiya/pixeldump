"""On-disk run state: thumbnail cache, manifests, resumable progress."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pixeldump.core.types import (
    Classification,
    LibraryStats,
    MoveOperation,
    RunManifest,
)


def state_dir(target: Path) -> Path:
    """Return the .pixeldump/ state directory for `target`, creating it if missing."""
    base = target / ".pixeldump"
    (base / "manifests").mkdir(parents=True, exist_ok=True)
    (base / "runs").mkdir(parents=True, exist_ok=True)
    (base / "thumbnails").mkdir(parents=True, exist_ok=True)
    return base


def thumbnail_cache_path(target: Path) -> Path:
    """Path to the thumbnail cache for `target`."""
    return state_dir(target) / "thumbnails"


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses, Paths, datetimes, and Enums to JSON-friendly forms."""
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result: dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            result[f.name] = _to_jsonable(getattr(obj, f.name))
        return result
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def write_manifest(target: Path, manifest: RunManifest) -> Path:
    """Persist a manifest under target/.pixeldump/manifests/<run_id>.json."""
    base = state_dir(target)
    out = base / "manifests" / f"{manifest.run_id}.json"
    payload = _to_jsonable(manifest)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out.chmod(0o600)  # manifests contain file paths; restrict to owner
    return out


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _classification_from_dict(data: dict[str, Any] | None) -> Classification | None:
    if data is None:
        return None
    return Classification(
        category=data["category"],
        subcategory=data.get("subcategory"),
        confidence=float(data.get("confidence", 0.0)),
        description=data.get("description", ""),
        notable=list(data.get("notable", []) or []),
    )


def _move_op_from_dict(data: dict[str, Any]) -> MoveOperation:
    ts = _parse_datetime(data.get("timestamp"))
    assert ts is not None
    return MoveOperation(
        action=data.get("action", "move"),
        source=Path(data["source"]),
        destination=Path(data["destination"]),
        timestamp=ts,
        classification=_classification_from_dict(data.get("classification")),
        reason=data.get("reason"),
    )


def _stats_from_dict(data: dict[str, Any] | None) -> LibraryStats:
    if not data:
        return LibraryStats()
    return LibraryStats(
        total_photos=int(data.get("total_photos", 0)),
        sorted=int(data.get("sorted", 0)),
        duplicates=int(data.get("duplicates", 0)),
        screenshots=int(data.get("screenshots", 0)),
        cats=int(data.get("cats", 0)),
        food=int(data.get("food", 0)),
        selfies=int(data.get("selfies", 0)),
        needs_review=int(data.get("needs_review", 0)),
        folders_created=int(data.get("folders_created", 0)),
        elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
        cost_usd=float(data.get("cost_usd", 0.0)),
        notable_findings=list(data.get("notable_findings", []) or []),
    )


def load_manifest(path: Path) -> RunManifest:
    """Load a manifest from JSON."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    started = _parse_datetime(raw.get("started_at"))
    assert started is not None
    completed = _parse_datetime(raw.get("completed_at"))
    operations = [_move_op_from_dict(op) for op in raw.get("operations", [])]
    stats = _stats_from_dict(raw.get("stats"))
    return RunManifest(
        version=raw.get("version", "1.0"),
        run_id=raw["run_id"],
        provider=raw.get("provider", ""),
        naming_mode=raw.get("naming_mode", ""),
        started_at=started,
        completed_at=completed,
        operations=operations,
        stats=stats,
    )
