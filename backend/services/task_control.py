"""Persistent scan task state and cooperative pause controls."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.config import settings


def _tasks_dir() -> Path:
    path = settings.CACHE_DIR / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_state_path(task_id: str) -> Path:
    return _tasks_dir() / f"{task_id}.json"


def task_control_path(task_id: str) -> Path:
    return _tasks_dir() / f"{task_id}.control.json"


def read_task_state(task_id: str) -> dict[str, Any] | None:
    path = task_state_path(task_id)
    if not path.exists():
        return None
    try:
        with path.open("r") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def write_task_progress(
    task_id: str | None,
    status: str,
    *,
    total_found: int | None = None,
    processed: int | None = None,
    new_inserted: int | None = None,
    duplicates_skipped: int | None = None,
    errors: int | None = None,
    current_file: str | None = None,
    start_time: float | None = None,
    result: dict[str, Any] | None = None,
    path: str | None = None,
    mode: str | None = None,
    generate_thumbs: bool | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    if not task_id:
        return None

    previous = read_task_state(task_id) or {}
    previous_progress = previous.get("progress") or {}
    progress = {
        "total_found": previous_progress.get("total_found", 0) if total_found is None else total_found,
        "processed": previous_progress.get("processed", 0) if processed is None else processed,
        "new_inserted": previous_progress.get("new_inserted", 0) if new_inserted is None else new_inserted,
        "duplicates_skipped": previous_progress.get("duplicates_skipped", 0)
        if duplicates_skipped is None
        else duplicates_skipped,
        "errors": previous_progress.get("errors", 0) if errors is None else errors,
        "current_file": previous_progress.get("current_file") if current_file is None else current_file,
        "start_time": previous_progress.get("start_time") if start_time is None else start_time,
    }
    payload: dict[str, Any] = {
        **previous,
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "result": result if result is not None else previous.get("result"),
        "path": path if path is not None else previous.get("path"),
        "mode": mode if mode is not None else previous.get("mode", "scan"),
        "generate_thumbs": generate_thumbs
        if generate_thumbs is not None
        else previous.get("generate_thumbs", True),
        "error_message": error_message,
    }

    state_path = task_state_path(task_id)
    temporary_path = state_path.with_suffix(".tmp")
    with temporary_path.open("w") as handle:
        json.dump(payload, handle)
    temporary_path.replace(state_path)

    try:
        import redis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        client = redis.Redis.from_url(redis_url)
        client.publish("scan_progress", json.dumps(payload))
    except Exception:
        pass

    return payload


def request_pause(task_id: str) -> None:
    with task_control_path(task_id).open("w") as handle:
        json.dump({"action": "pause"}, handle)


def pause_requested(task_id: str | None) -> bool:
    if not task_id:
        return False
    path = task_control_path(task_id)
    if not path.exists():
        return False
    try:
        with path.open("r") as handle:
            return json.load(handle).get("action") == "pause"
    except (OSError, json.JSONDecodeError):
        return False


def clear_task_control(task_id: str) -> None:
    task_control_path(task_id).unlink(missing_ok=True)


def list_task_states(*, include_complete: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    states: list[tuple[float, dict[str, Any]]] = []
    for path in _tasks_dir().glob("*.json"):
        if path.name.endswith(".control.json"):
            continue
        try:
            with path.open("r") as handle:
                state = json.load(handle)
            if not include_complete and state.get("status") == "complete":
                continue
            states.append((path.stat().st_mtime, state))
        except (OSError, json.JSONDecodeError):
            continue
    states.sort(key=lambda item: item[0], reverse=True)
    return [state for _, state in states[:limit]]
