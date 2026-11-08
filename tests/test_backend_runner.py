"""Refresh orchestration: single flight, local subprocess, GitHub dispatch."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
from pathlib import Path

import pytest

from backend.runner import (
    DispatchResult,
    GitHubWorkflowDispatcher,
    LocalPipelineDispatcher,
    RefreshRunner,
    build_dispatcher,
    build_post_refresh,
    run_post_refresh_command,
)
from backend.settings import BackendConfig


class BlockingDispatcher:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls: list[dict[str, object]] = []

    def dispatch(self, job):
        self.calls.append(job)
        self.started.set()
        self.release.wait(5)
        return DispatchResult(ok=True, detail="pipeline finished", exit_code=0)


class ExplodingDispatcher:
    def dispatch(self, job):
        raise RuntimeError("token ghs_secret must not leak")


class JsonResponse:
    def __init__(self, status: int = 204, payload=None) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8") if payload is not None else b""

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeGitHub:
    """Route GitHub API calls to canned responses and record the requests."""

    def __init__(
        self,
        *,
        dispatch_status: int = 204,
        existing_runs: tuple[dict, ...] = (),
        new_run_id: int | None = 101,
        run_states: list[dict] | None = None,
        dispatch_failures: list[int] | None = None,
    ) -> None:
        self.requests: list[dict] = []
        self.dispatch_status = dispatch_status
        self.runs = [dict(run) for run in existing_runs]
        self.new_run_id = new_run_id
        self.run_states = list(
            run_states or [{"status": "completed", "conclusion": "success"}]
        )
        self.dispatch_failures = list(dispatch_failures or [])

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.requests.append(
            {
                "method": request.get_method(),
                "url": url,
                "headers": dict(request.header_items()),
                "body": json.loads(request.data) if request.data else None,
                "timeout": timeout,
            }
        )
        if url.endswith("/dispatches"):
            if self.dispatch_failures:
                return JsonResponse(self.dispatch_failures.pop(0))
            if 200 <= self.dispatch_status < 300 and self.new_run_id is not None:
                self.runs.append({"id": self.new_run_id})
            return JsonResponse(self.dispatch_status)
        if "/actions/runs?" in url:
            return JsonResponse(200, {"workflow_runs": self.runs})
        if "/actions/runs/" in url:
            state = (
                self.run_states.pop(0)
                if len(self.run_states) > 1
                else self.run_states[0]
            )
            return JsonResponse(200, {"id": int(url.rsplit("/", 1)[1]), **state})
        return JsonResponse(404)

    def dispatch_requests(self) -> list[dict]:
        return [item for item in self.requests if item["url"].endswith("/dispatches")]


def test_local_dispatcher_runs_command(tmp_path):
    marker = tmp_path / "marker.txt"
    script = (
        "import pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_text('4677 facts', encoding='utf-8')"
    )
    dispatcher = LocalPipelineDispatcher(
        command=(sys.executable, "-c", script, str(marker)),
        cwd=tmp_path,
        timeout_seconds=30,
    )

    result = dispatcher.dispatch({"job_id": "job_1", "reason": "test"})

    assert result.ok is True
    assert result.exit_code == 0
    assert marker.read_text(encoding="utf-8") == "4677 facts"


def test_local_dispatcher_reports_failure(tmp_path):
    dispatcher = LocalPipelineDispatcher(
        command=(
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('crawl failed'); sys.exit(3)",
        ),
        cwd=tmp_path,
        timeout_seconds=30,
    )

    result = dispatcher.dispatch({"job_id": "job_2", "reason": "test"})

    assert result.ok is False
    assert result.exit_code == 3
    assert "crawl failed" in result.detail


def test_local_dispatcher_reports_timeout(tmp_path):
    dispatcher = LocalPipelineDispatcher(
        command=(sys.executable, "-c", "import time; time.sleep(10)"),
        cwd=tmp_path,
        timeout_seconds=1,
    )

    result = dispatcher.dispatch({"job_id": "job_3", "reason": "test"})

    assert result.ok is False
    assert "timed out" in result.detail


def test_runner_single_flight_and_event_order():
    events: list[tuple[str, dict]] = []
    dispatcher = BlockingDispatcher()
    runner = RefreshRunner(
        dispatcher=dispatcher,
        on_event=lambda event, payload: events.append((event, payload)),
        job_id_factory=lambda: "job_test",
    )

    status, payload = runner.trigger("stale-snapshot")
    assert status == 202
    assert payload["refresh"]["job_id"] == "job_test"
    assert dispatcher.started.wait(5)

    conflict, conflict_payload = runner.trigger("manual")
    assert conflict == 409
    assert conflict_payload["status"] == "conflict"
    assert runner.running is True

    dispatcher.release.set()
    assert runner.wait(5) is True

    final = runner.status()
    assert final["status"] == "succeeded"
    assert final["reason"] == "stale-snapshot"
    assert final["exit_code"] == 0
    assert [event for event, _ in events] == ["refresh", "refresh_finished"]
    assert events[1][1]["status"] == "succeeded"


def test_runner_marks_dispatch_failure():
    class FailingDispatcher:
        def dispatch(self, job):
            return DispatchResult(ok=False, detail="pipeline exited with 2", exit_code=2)

    runner = RefreshRunner(dispatcher=FailingDispatcher())
    status, _ = runner.trigger("missing-snapshot")
    assert status == 202
    assert runner.wait(5) is True

    final = runner.status()
    assert final["status"] == "failed"
    assert final["exit_code"] == 2
    assert final["detail"] == "pipeline exited with 2"


def test_runner_sanitizes_dispatch_exception():
    runner = RefreshRunner(dispatcher=ExplodingDispatcher())
    runner.trigger("manual")
    assert runner.wait(5) is True

    final = runner.status()
    assert final["status"] == "failed"
    assert final["detail"] == "dispatcher error: RuntimeError"
    assert "ghs_secret" not in json.dumps(final)


def test_github_dispatcher_posts_workflow_dispatch_and_follows_the_run():
    fake = FakeGitHub()
    dispatcher = GitHubWorkflowDispatcher(
        repository="owner/aicor",
        token="ghs_secret",
        workflow="hourly-crawl.yml",
        ref="main",
        opener=fake,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    result = dispatcher.dispatch({"job_id": "job_4"})

    assert result.ok is True
    assert result.exit_code == 0
    assert result.run_id == 101
    assert result.detail == "workflow run 101 completed: success"
    dispatched = fake.dispatch_requests()
    assert len(dispatched) == 1
    assert dispatched[0]["url"] == (
        "https://api.github.com/repos/owner/aicor/actions/workflows/"
        "hourly-crawl.yml/dispatches"
    )
    assert dispatched[0]["method"] == "POST"
    assert dispatched[0]["body"] == {"ref": "main"}
    assert dispatched[0]["headers"]["Authorization"] == "Bearer ghs_secret"
    assert dispatched[0]["timeout"] == 30
    assert "ghs_secret" not in result.detail


def test_github_dispatcher_reports_http_error_without_token():
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    dispatcher = GitHubWorkflowDispatcher(
        repository="owner/aicor",
        token="ghs_secret",
        opener=opener,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    result = dispatcher.dispatch({"job_id": "job_5"})

    assert result.ok is False
    assert result.exit_code == 403
    assert "403" in result.detail
    assert "ghs_secret" not in result.detail


def test_github_dispatcher_reports_network_error():
    calls = {"count": 0, "dispatch": 0}

    def opener(request, timeout=None):
        calls["count"] += 1
        if request.full_url.endswith("/dispatches"):
            calls["dispatch"] += 1
        raise urllib.error.URLError("name resolution failed")

    dispatcher = GitHubWorkflowDispatcher(
        repository="owner/aicor",
        token="ghs_secret",
        opener=opener,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    result = dispatcher.dispatch({"job_id": "job_6"})

    assert result.ok is False
    assert result.detail == "GitHub dispatch network error"
    assert calls["dispatch"] == 3  # baseline lookup + three dispatch attempts


def test_github_dispatcher_retries_transient_dispatch_failures():
    fake = FakeGitHub(dispatch_failures=[500, 503])
    dispatcher = GitHubWorkflowDispatcher(
        repository="owner/aicor",
        token="ghs_secret",
        opener=fake,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    result = dispatcher.dispatch({"job_id": "job_7"})

    assert result.ok is True
    assert len(fake.dispatch_requests()) == 3


def test_github_dispatcher_reports_a_failed_run():
    fake = FakeGitHub(
        run_states=[{"status": "completed", "conclusion": "failure"}]
    )
    dispatcher = GitHubWorkflowDispatcher(
        repository="owner/aicor",
        token="ghs_secret",
        opener=fake,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    result = dispatcher.dispatch({"job_id": "job_8"})

    assert result.ok is False
    assert result.exit_code == 1
    assert result.run_id == 101
    assert "failure" in result.detail


def test_github_dispatcher_times_out_without_a_completed_run():
    fake = FakeGitHub(run_states=[{"status": "in_progress"}])
    dispatcher = GitHubWorkflowDispatcher(
        repository="owner/aicor",
        token="ghs_secret",
        opener=fake,
        poll_interval_seconds=0,
        run_timeout_seconds=1,
        sleep=lambda _seconds: None,
    )

    result = dispatcher.dispatch({"job_id": "job_9"})

    assert result.ok is False
    assert result.run_id == 101
    assert "did not complete" in result.detail


def test_github_dispatcher_reports_a_missing_run():
    fake = FakeGitHub(new_run_id=None)
    dispatcher = GitHubWorkflowDispatcher(
        repository="owner/aicor",
        token="ghs_secret",
        opener=fake,
        poll_interval_seconds=0,
        run_timeout_seconds=1,
        sleep=lambda _seconds: None,
    )

    result = dispatcher.dispatch({"job_id": "job_10"})

    assert result.ok is False
    assert "not found" in result.detail


def test_build_dispatcher_prefers_github_when_configured(tmp_path):
    configured = BackendConfig(
        data_dir=tmp_path,
        github_repository="owner/aicor",
        github_token="ghs_secret",
    )
    dispatcher, target = build_dispatcher(configured)
    assert target == "github"
    assert isinstance(dispatcher, GitHubWorkflowDispatcher)

    local, local_target = build_dispatcher(BackendConfig(data_dir=tmp_path))
    assert local_target == "local"
    assert isinstance(local, LocalPipelineDispatcher)


class ImmediateDispatcher:
    def __init__(self, *, ok: bool = True) -> None:
        self._ok = ok

    def dispatch(self, job):
        if self._ok:
            return DispatchResult(ok=True, detail="pipeline finished", exit_code=0)
        return DispatchResult(ok=False, detail="pipeline exited with 2", exit_code=2)


class CancellableDispatcher:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def dispatch(self, job):
        self.started.set()
        self.cancelled.wait(10)
        return DispatchResult(ok=False, detail="refresh cancelled during shutdown")

    def cancel(self) -> None:
        self.cancelled.set()


def test_local_dispatcher_streams_output_to_a_log_file(tmp_path):
    script = "print('4677 facts')\nprint('5964 prices')"
    dispatcher = LocalPipelineDispatcher(
        command=(sys.executable, "-c", script),
        cwd=tmp_path,
        timeout_seconds=60,
        log_dir=tmp_path / "logs",
    )

    result = dispatcher.dispatch({"job_id": "job_log"})

    assert result.ok is True
    log_path = Path(result.log_path or "")
    assert log_path.exists()
    assert "4677 facts" in log_path.read_text(encoding="utf-8")
    assert result.detail.endswith("5964 prices")


def test_local_dispatcher_kills_the_process_on_timeout(tmp_path):
    dispatcher = LocalPipelineDispatcher(
        command=(sys.executable, "-c", "import time; time.sleep(30)"),
        cwd=tmp_path,
        timeout_seconds=1,
        log_dir=tmp_path / "logs",
    )

    started = time.monotonic()
    result = dispatcher.dispatch({"job_id": "job_timeout"})
    elapsed = time.monotonic() - started

    assert result.ok is False
    assert "timed out" in result.detail
    assert elapsed < 15


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group semantics")
def test_local_dispatcher_force_kills_a_process_that_ignores_sigterm(tmp_path):
    script = (
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ignoring SIGTERM', flush=True); "
        "time.sleep(60)"
    )
    dispatcher = LocalPipelineDispatcher(
        command=(sys.executable, "-c", script),
        cwd=tmp_path,
        timeout_seconds=1,
        log_dir=tmp_path / "logs",
    )

    started = time.monotonic()
    result = dispatcher.dispatch({"job_id": "job_force_timeout"})
    elapsed = time.monotonic() - started

    assert result.ok is False
    assert "timed out" in result.detail
    assert "ignoring SIGTERM" in result.detail
    assert elapsed < 15


def test_runner_publishes_the_new_snapshot_after_success():
    events: list[tuple[str, dict]] = []
    versions = ["v20261108.0", "v20261108.1"]
    reads = {"count": 0}

    def reader():
        index = min(reads["count"], len(versions) - 1)
        reads["count"] += 1
        return {
            "snapshot_version": versions[index],
            "generated_at": "2026-11-08T06:00:00Z",
            "data_as_of": "2026-11-08",
            "run_id": "run_new",
        }

    runner = RefreshRunner(
        dispatcher=ImmediateDispatcher(),
        on_event=lambda event, payload: events.append((event, payload)),
        snapshot_reader=reader,
        job_id_factory=lambda: "job_fixed",
    )

    status, _ = runner.trigger("manual")
    assert status == 202
    assert runner.wait(5) is True

    assert [event for event, _ in events] == ["refresh", "snapshot", "refresh_finished"]
    assert events[1][1]["changed"] is True
    assert events[1][1]["snapshot"]["snapshot_version"] == "v20261108.1"
    assert events[2][1]["snapshot_version"] == "v20261108.1"
    assert events[2][1]["snapshot_changed"] is True
    assert events[2][1]["status"] == "succeeded"


def test_runner_reports_unchanged_snapshot_when_version_is_stable():
    events: list[tuple[str, dict]] = []
    runner = RefreshRunner(
        dispatcher=ImmediateDispatcher(),
        on_event=lambda event, payload: events.append((event, payload)),
        snapshot_reader=lambda: {
            "snapshot_version": "v20261108.1",
            "generated_at": "2026-11-08T06:00:00Z",
            "data_as_of": "2026-11-08",
            "run_id": "run_same",
        },
        job_id_factory=lambda: "job_same",
    )

    runner.trigger("manual")
    assert runner.wait(5) is True

    assert [event for event, _ in events] == ["refresh", "snapshot", "refresh_finished"]
    assert events[1][1]["changed"] is False
    assert events[2][1]["snapshot_changed"] is False


def test_runner_runs_post_refresh_before_rereading_the_snapshot():
    events: list[tuple[str, dict]] = []
    state = {"synced": False, "order": []}

    class SyncDispatcher:
        def dispatch(self, job):
            state["order"].append("dispatch")
            return DispatchResult(ok=True, detail="workflow finished", exit_code=0)

    def post_refresh():
        state["order"].append("post_refresh")
        state["synced"] = True
        return DispatchResult(ok=True, detail="snapshot synced", exit_code=0)

    def reader():
        version = "v20261108.1" if state["synced"] else "v20261108.0"
        return {
            "snapshot_version": version,
            "generated_at": "2026-11-08T06:00:00Z",
            "data_as_of": "2026-11-08",
            "run_id": "run_sync",
        }

    runner = RefreshRunner(
        dispatcher=SyncDispatcher(),
        on_event=lambda event, payload: events.append((event, payload)),
        snapshot_reader=reader,
        post_refresh=post_refresh,
    )

    runner.trigger("manual")
    assert runner.wait(5) is True

    assert state["order"] == ["dispatch", "post_refresh"]
    assert runner.status()["status"] == "succeeded"
    assert runner.status()["snapshot_version"] == "v20261108.1"
    assert runner.status()["snapshot_changed"] is True
    assert events[1][1]["snapshot"]["snapshot_version"] == "v20261108.1"


def test_runner_marks_the_refresh_failed_when_post_refresh_fails():
    events: list[tuple[str, dict]] = []
    runner = RefreshRunner(
        dispatcher=ImmediateDispatcher(),
        on_event=lambda event, payload: events.append((event, payload)),
        snapshot_reader=lambda: {
            "snapshot_version": "v20261108.0",
            "generated_at": "2026-11-08T06:00:00Z",
        },
        post_refresh=lambda: DispatchResult(
            ok=False, detail="git pull exited with 1", exit_code=1
        ),
    )

    runner.trigger("manual")
    assert runner.wait(5) is True

    final = runner.status()
    assert final["status"] == "failed"
    assert final["snapshot_changed"] is None
    assert "post-refresh failed" in final["detail"]
    assert [event for event, _ in events] == ["refresh", "refresh_finished"]


def test_runner_sanitizes_a_post_refresh_exception():
    runner = RefreshRunner(
        dispatcher=ImmediateDispatcher(),
        post_refresh=lambda: (_ for _ in ()).throw(RuntimeError("token ghs_secret")),
    )

    runner.trigger("manual")
    assert runner.wait(5) is True

    final = runner.status()
    assert final["status"] == "failed"
    assert final["detail"] == "post-refresh failed: post-refresh error: RuntimeError"
    assert "ghs_secret" not in json.dumps(final)


def test_runner_does_not_publish_a_snapshot_after_failure():
    events: list[tuple[str, dict]] = []
    runner = RefreshRunner(
        dispatcher=ImmediateDispatcher(ok=False),
        on_event=lambda event, payload: events.append((event, payload)),
        snapshot_reader=lambda: {"snapshot_version": "v20261108.1"},
    )

    runner.trigger("manual")
    assert runner.wait(5) is True

    assert [event for event, _ in events] == ["refresh", "refresh_finished"]
    final = runner.status()
    assert final["status"] == "failed"
    assert final["snapshot_version"] is None


def test_post_refresh_command_runs_and_reports_output(tmp_path):
    result = run_post_refresh_command(
        (sys.executable, "-c", "print('synced snapshot')"),
        cwd=tmp_path,
        timeout_seconds=30,
    )

    assert result.ok is True
    assert result.exit_code == 0
    assert "synced snapshot" in result.detail


def test_post_refresh_command_reports_failure(tmp_path):
    result = run_post_refresh_command(
        (
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('pull failed'); sys.exit(2)",
        ),
        cwd=tmp_path,
        timeout_seconds=30,
    )

    assert result.ok is False
    assert result.exit_code == 2
    assert "pull failed" in result.detail


def test_post_refresh_command_reports_timeout(tmp_path):
    result = run_post_refresh_command(
        (sys.executable, "-c", "import time; time.sleep(10)"),
        cwd=tmp_path,
        timeout_seconds=1,
    )

    assert result.ok is False
    assert "timed out" in result.detail


def test_build_post_refresh_is_none_without_a_command(tmp_path):
    assert build_post_refresh(BackendConfig(data_dir=tmp_path)) is None


def test_build_post_refresh_runs_the_configured_command(tmp_path):
    config = BackendConfig(
        data_dir=tmp_path,
        post_refresh_command=(sys.executable, "-c", "print('hook ran')"),
        refresh_timeout_seconds=30,
    )

    hook = build_post_refresh(config)

    assert hook is not None
    result = hook()
    assert result.ok is True
    assert "hook ran" in result.detail


def test_runner_stop_cancels_an_in_flight_refresh():
    dispatcher = CancellableDispatcher()
    runner = RefreshRunner(dispatcher=dispatcher)

    assert runner.trigger("manual")[0] == 202
    assert dispatcher.started.wait(5) is True

    runner.stop(5)

    assert runner.wait(5) is True
    assert runner.status()["status"] == "failed"
    assert runner.trigger("after-stop")[0] == 503
