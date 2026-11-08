from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.sync import SyncLog, archive_raw_file
from pipeline.util import write_json


def test_sync_log_records_success_and_failure(tmp_path: Path):
    path = tmp_path / "sync_log.jsonl"
    log = SyncLog(path, run_id="run_test")

    with log.source("prices") as source:
        source.records_added = 4
    with pytest.raises(RuntimeError):
        with log.source("sec") as source:
            source.records_added = 2
            raise RuntimeError("SEC unavailable")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["status"] == "success"
    assert rows[0]["records_added"] == 4
    assert rows[1]["status"] == "failed"
    assert rows[1]["error_message"] == "SEC unavailable"
    assert rows[1]["run_id"] == "run_test"


def test_raw_snapshot_is_immutable_and_atomic_json_write(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    source = raw_dir / "sec" / "facts.csv"
    source.parent.mkdir(parents=True)
    source.write_text("value\n1\n", encoding="utf-8")

    archived = archive_raw_file(raw_dir, "run_test", source)
    source.write_text("value\n2\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        archive_raw_file(raw_dir, "run_test", source)

    assert archived.read_text(encoding="utf-8") == "value\n1\n"

    target = tmp_path / "latest.json"
    target.write_text('{"old":true}\n', encoding="utf-8")
    write_json(target, {"new": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
