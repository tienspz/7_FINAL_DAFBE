"""Runtime wiring: a local refresh publishes the new snapshot to subscribers."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from backend.__main__ import build_runtime
from backend.settings import BackendConfig
from tests.helpers import write_dashboard_snapshot


def _timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def test_build_runtime_publishes_the_snapshot_after_a_local_refresh(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    config = BackendConfig(
        data_dir=root,
        host="127.0.0.1",
        port=0,
        auto_refresh=False,
        stale_after_seconds=3600,
        pipeline_command=(sys.executable, "-c", "print('noop crawl')"),
        log_dir=tmp_path / "logs",
    )

    server, runner, broker, target = build_runtime(config)
    subscription = broker.subscribe()
    try:
        assert target == "local"
        assert runner.trigger("test")[0] == 202
        assert runner.wait(30) is True

        events: list[str] = []
        while True:
            message = subscription.get(timeout=2)
            if message is None:
                break
            events.append(message["event"])

        assert events[:1] == ["refresh"]
        assert "snapshot" in events
        assert events[-1] == "refresh_finished"
        assert runner.status()["snapshot_version"] == "v20261106.5"
    finally:
        runner.stop()
        server.server_close()


def test_build_runtime_runs_the_post_refresh_hook_before_reloading(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    manifest_path = root / "manifest.json"
    script = (
        "import json, pathlib, sys; "
        "path = pathlib.Path(sys.argv[1]); "
        "data = json.loads(path.read_text(encoding='utf-8')); "
        "data['snapshot_version'] = 'v20261108.9'; "
        "path.write_text(json.dumps(data), encoding='utf-8')"
    )
    config = BackendConfig(
        data_dir=root,
        host="127.0.0.1",
        port=0,
        auto_refresh=False,
        stale_after_seconds=3600,
        pipeline_command=(sys.executable, "-c", "print('noop crawl')"),
        post_refresh_command=(sys.executable, "-c", script, str(manifest_path)),
        log_dir=tmp_path / "logs",
    )

    server, runner, broker, target = build_runtime(config)
    subscription = broker.subscribe()
    try:
        assert runner.trigger("test")[0] == 202
        assert runner.wait(30) is True

        messages = []
        while True:
            message = subscription.get(timeout=2)
            if message is None:
                break
            messages.append(message)

        status = runner.status()
        assert status["status"] == "succeeded"
        assert status["snapshot_version"] == "v20261108.9"
        assert status["snapshot_changed"] is True
        snapshots = [
            message for message in messages if message["event"] == "snapshot"
        ]
        assert snapshots[0]["data"]["snapshot"]["snapshot_version"] == "v20261108.9"
    finally:
        runner.stop()
        server.server_close()
