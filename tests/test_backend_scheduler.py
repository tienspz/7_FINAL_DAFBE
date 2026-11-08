"""Background freshness scheduler decisions."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.scheduler import FreshnessScheduler
from backend.snapshot import SnapshotStore
from tests.helpers import write_dashboard_snapshot


class StubRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._running = False
        self.triggered = threading.Event()

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> dict:
        return {"status": "running" if self._running else "idle"}

    def trigger(self, reason: str) -> tuple[int, dict]:
        self.calls.append(reason)
        self._running = True
        self.triggered.set()
        return 202, {"status": "accepted", "refresh": {"job_id": "job_stub"}}


def build_scheduler(
    tmp_path: Path,
    *,
    age_hours: float,
    runner: StubRunner | None = None,
    events: list[tuple[str, dict]] | None = None,
    stale_after_seconds: int = 3600,
    interval_seconds: int = 60,
) -> tuple[FreshnessScheduler, StubRunner, Path, datetime]:
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    generated = (now - timedelta(hours=age_hours)).isoformat().replace("+00:00", "Z")
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=generated)
    stub = runner or StubRunner()
    on_event = (lambda event, payload: events.append((event, payload))) if events is not None else None
    scheduler = FreshnessScheduler(
        store=SnapshotStore(root),
        runner=stub,
        interval_seconds=interval_seconds,
        stale_after_seconds=stale_after_seconds,
        on_event=on_event,
        clock=lambda: now,
    )
    return scheduler, stub, root, now


def test_fresh_snapshot_does_not_refresh(tmp_path):
    scheduler, runner, _, _ = build_scheduler(tmp_path, age_hours=0.1)

    decision = scheduler.tick()

    assert decision == {"action": "none", "reason": "fresh", "age_seconds": 360}
    assert runner.calls == []


def test_stale_snapshot_triggers_refresh(tmp_path):
    scheduler, runner, _, _ = build_scheduler(tmp_path, age_hours=3)

    decision = scheduler.tick()

    assert decision["action"] == "triggered"
    assert decision["reason"] == "stale-snapshot"
    assert decision["job_id"] == "job_stub"
    assert runner.calls == ["stale-snapshot"]


def test_missing_snapshot_triggers_refresh(tmp_path):
    runner = StubRunner()
    scheduler = FreshnessScheduler(
        store=SnapshotStore(tmp_path / "empty"),
        runner=runner,
        interval_seconds=60,
        stale_after_seconds=3600,
    )

    decision = scheduler.tick()

    assert decision["action"] == "triggered"
    assert decision["reason"] == "missing-snapshot"
    assert runner.calls == ["missing-snapshot"]


def test_running_refresh_blocks_another_trigger(tmp_path):
    runner = StubRunner()
    runner._running = True
    scheduler, _, _, _ = build_scheduler(tmp_path, age_hours=3, runner=runner)

    decision = scheduler.tick()

    assert decision == {"action": "wait", "reason": "refresh-in-flight"}
    assert runner.calls == []


def test_snapshot_event_is_published_once_per_manifest_change(tmp_path):
    events: list[tuple[str, dict]] = []
    scheduler, _, root, _ = build_scheduler(
        tmp_path, age_hours=0.1, events=events
    )

    scheduler.tick()
    scheduler.tick()
    assert [event for event, _ in events] == ["snapshot"]
    assert events[0][1]["changed"] is False
    assert events[0][1]["snapshot"]["snapshot_version"] == "v20261106.5"
    assert events[0][1]["snapshot"]["stale"] is False
    assert events[0][1]["snapshot"]["checksum_ok"] is True

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["snapshot_version"] = "v20261108.1"
    manifest["generated_at"] = "2026-11-08T11:59:00Z"
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    scheduler.tick()

    assert [event for event, _ in events] == ["snapshot", "snapshot"]
    assert events[1][1]["changed"] is True
    assert events[1][1]["snapshot"]["snapshot_version"] == "v20261108.1"
    assert events[1][1]["snapshot"]["run_id"] == "run_20261107T122003Z_test"


def test_missing_generated_at_triggers_a_refresh(tmp_path):
    events: list[tuple[str, dict]] = []
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    root = write_dashboard_snapshot(tmp_path / "data", generated_at="")
    runner = StubRunner()
    scheduler = FreshnessScheduler(
        store=SnapshotStore(root),
        runner=runner,
        interval_seconds=60,
        stale_after_seconds=3600,
        on_event=lambda event, payload: events.append((event, payload)),
        clock=lambda: now,
    )

    decision = scheduler.tick()

    assert decision["action"] == "triggered"
    assert decision["reason"] == "missing-generated-at"
    assert runner.calls == ["missing-generated-at"]
    assert events[0][1]["snapshot"]["age_seconds"] is None
    assert events[0][1]["snapshot"]["stale"] is True


def test_thread_starts_and_stops(tmp_path):
    scheduler, runner, _, _ = build_scheduler(
        tmp_path, age_hours=3, interval_seconds=1
    )

    scheduler.start()
    assert runner.triggered.wait(5)
    scheduler.stop(timeout=5)

    assert not scheduler.is_alive()
    assert runner.calls == ["stale-snapshot"]
