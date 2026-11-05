"""Durable source-level sync logging and immutable raw-run snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from pipeline.util import utc_now_iso


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def archive_raw_file(raw_dir: Path, run_id: str, source_path: Path) -> Path:
    resolved_raw_dir = raw_dir.resolve()
    resolved_source = source_path.resolve()
    relative_path = resolved_source.relative_to(resolved_raw_dir)
    target = raw_dir / "runs" / run_id / relative_path
    if target.exists():
        raise FileExistsError(f"Raw run artifact is immutable: {target}")
    atomic_write_bytes(target, resolved_source.read_bytes())
    return target


@dataclass
class SourceSync:
    source: str
    records_added: int = 0
    status: str = "success"
    error_message: str = ""

    def mark_partial(self, message: str) -> None:
        self.status = "partial"
        self.error_message = message


class SyncLog:
    def __init__(self, path: Path, *, run_id: str):
        self.path = path
        self.run_id = run_id

    @contextmanager
    def source(self, name: str) -> Iterator[SourceSync]:
        started_at = utc_now_iso()
        state = SourceSync(source=name)
        try:
            yield state
        except Exception as exc:
            state.status = "failed"
            state.error_message = str(exc)
            self._append(state, started_at)
            raise
        self._append(state, started_at)

    def _append(self, state: SourceSync, started_at: str) -> None:
        row = {
            "run_id": self.run_id,
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "source": state.source,
            "status": state.status,
            "records_added": state.records_added,
            "error_message": state.error_message,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def raw_file_manifest(run_id: str, archived_paths: list[Path], raw_dir: Path) -> dict:
    files = []
    for path in sorted(archived_paths):
        content = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(raw_dir).as_posix(),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {"schema_version": "1.0", "run_id": run_id, "files": files}
