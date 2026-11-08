"""Refresh orchestration for the AICOR backend.

Only one refresh may run at a time. A refresh either runs the pipeline as a
local subprocess or dispatches the GitHub Actions workflow (SI-09). The GitHub
path polls the dispatched run until it finishes, so ``succeeded`` means the
crawl completed rather than merely that the dispatch was accepted.

Failure details are sanitized: no token, URL with a query key, or raw response
body is ever reported. Local pipeline output is streamed to a log file instead
of being buffered in memory.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import quote

from backend.settings import PROJECT_ROOT, BackendConfig
from backend.snapshot import snapshot_event
from pipeline.util import utc_now_iso

DETAIL_LIMIT = 400
TAIL_READ_BYTES = 8_192
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of one refresh attempt."""

    ok: bool
    detail: str = ""
    exit_code: int | None = None
    log_path: str | None = None
    run_id: int | None = None


@dataclass(frozen=True)
class RefreshState:
    """Public, secret-free refresh state."""

    status: str = "idle"
    job_id: str | None = None
    reason: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    detail: str = ""
    exit_code: int | None = None
    target: str = "local"
    log_path: str | None = None
    run_id: int | None = None
    snapshot_version: str | None = None
    snapshot_changed: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Dispatcher(Protocol):
    def dispatch(self, job: dict[str, Any]) -> DispatchResult: ...


class RefreshController(Protocol):
    @property
    def running(self) -> bool: ...

    def status(self) -> dict[str, Any]: ...

    def trigger(self, reason: str) -> tuple[int, dict[str, Any]]: ...


class _GitHubNetworkError(Exception):
    """Transport failure while talking to the GitHub API."""


class LocalPipelineDispatcher:
    """Run the pipeline in-process tree as a bounded subprocess."""

    def __init__(
        self,
        *,
        command: tuple[str, ...],
        cwd: str | Any,
        timeout_seconds: int,
        log_dir: str | Path | None = None,
    ) -> None:
        self._command = tuple(command)
        self._cwd = str(cwd)
        self._timeout = max(1, int(timeout_seconds))
        self._log_dir = Path(log_dir) if log_dir is not None else Path(cwd) / "logs"
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._cancelled = False

    def dispatch(self, job: dict[str, Any]) -> DispatchResult:
        job_id = str(job.get("job_id") or "job")
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return DispatchResult(
                ok=False,
                detail=f"could not create the log directory: {type(error).__name__}",
            )
        log_path = self._log_dir / f"backend-refresh-{_safe_token(job_id)}.log"

        try:
            handle = log_path.open("w", encoding="utf-8", errors="replace")
        except OSError as error:
            return DispatchResult(
                ok=False,
                detail=f"could not open the refresh log: {type(error).__name__}",
            )

        with self._lock:
            if self._cancelled:
                handle.close()
                return DispatchResult(
                    ok=False, detail="refresh cancelled during shutdown"
                )

        try:
            with handle:
                process = subprocess.Popen(
                    list(self._command),
                    cwd=self._cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    **_process_group_kwargs(),
                )
                with self._lock:
                    self._process = process
                try:
                    exit_code = process.wait(timeout=self._timeout)
                except subprocess.TimeoutExpired:
                    self._terminate(process)
                    tail = _tail_file(log_path)
                    detail = f"pipeline timed out after {self._timeout}s"
                    if tail:
                        detail = f"{detail}: {tail}"
                    return DispatchResult(
                        ok=False, detail=detail, log_path=str(log_path)
                    )
                finally:
                    with self._lock:
                        if self._process is process:
                            self._process = None
        except OSError as error:
            return DispatchResult(
                ok=False,
                detail=f"pipeline could not start: {type(error).__name__}",
                log_path=str(log_path),
            )

        tail = _tail_file(log_path)
        if exit_code != 0:
            return DispatchResult(
                ok=False,
                detail=tail or f"pipeline exited with {exit_code}",
                exit_code=exit_code,
                log_path=str(log_path),
            )
        return DispatchResult(
            ok=True,
            detail=tail or "pipeline finished",
            exit_code=0,
            log_path=str(log_path),
        )

    def cancel(self) -> None:
        """Terminate an in-flight pipeline tree (called during shutdown)."""
        with self._lock:
            self._cancelled = True
            process = self._process
        if process is not None and process.poll() is None:
            self._terminate(process)

    def _terminate(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process_group: int | None = None
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            try:
                process_group = os.getpgid(process.pid)
                os.killpg(process_group, signal.SIGTERM)
            except OSError:
                process_group = None
                try:
                    process.terminate()
                except OSError:
                    pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # A pipeline that ignores SIGTERM must not leave grandchildren
            # running: force-kill the whole process group, not only the parent.
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            elif process_group is not None:
                try:
                    os.killpg(process_group, signal.SIGKILL)
                except OSError:
                    pass
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


class GitHubWorkflowDispatcher:
    """Trigger ``workflow_dispatch`` and follow the run to completion (SI-09)."""

    def __init__(
        self,
        *,
        repository: str,
        token: str,
        workflow: str = "hourly-crawl.yml",
        ref: str = "main",
        api_base: str = "https://api.github.com",
        opener: Callable[..., Any] | None = None,
        timeout_seconds: int = 30,
        poll_interval_seconds: int = 20,
        run_timeout_seconds: int = 1800,
        track_run: bool = True,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._repository = repository.strip()
        self._token = token
        self._workflow = workflow.strip()
        self._ref = ref.strip() or "main"
        self._api_base = api_base.rstrip("/")
        self._opener = opener or urllib.request.urlopen
        self._timeout = max(1, int(timeout_seconds))
        self._poll_interval = max(0, int(poll_interval_seconds))
        self._run_timeout = max(1, int(run_timeout_seconds))
        self._track_run = track_run
        self._sleep = sleep or time.sleep

    @property
    def url(self) -> str:
        workflow = quote(self._workflow, safe="")
        return (
            f"{self._api_base}/repos/{self._repository}"
            f"/actions/workflows/{workflow}/dispatches"
        )

    def dispatch(self, job: dict[str, Any]) -> DispatchResult:
        baseline = self._baseline_run_id() if self._track_run else None
        accepted = self._request_dispatch()
        if not accepted.ok or not self._track_run:
            return accepted
        return self._await_run(baseline)

    # -- dispatch ------------------------------------------------------

    def _request_dispatch(self) -> DispatchResult:
        delay = 1.0
        for attempt in range(3):
            try:
                status, _ = self._api(
                    f"/repos/{self._repository}/actions/workflows/"
                    f"{quote(self._workflow, safe='')}/dispatches",
                    method="POST",
                    payload={"ref": self._ref},
                )
            except _GitHubNetworkError:
                if attempt == 2:
                    return DispatchResult(
                        ok=False, detail="GitHub dispatch network error"
                    )
                self._sleep(delay)
                delay *= 2
                continue
            if status in (201, 202, 204):
                return DispatchResult(
                    ok=True, detail="workflow_dispatch accepted", exit_code=status
                )
            if status in _RETRY_STATUSES and attempt < 2:
                self._sleep(delay)
                delay *= 2
                continue
            return DispatchResult(
                ok=False,
                detail=f"GitHub dispatch rejected with HTTP {status}",
                exit_code=status,
            )
        return DispatchResult(ok=False, detail="GitHub dispatch failed")

    def _baseline_run_id(self) -> int | None:
        runs = self._runs()
        ids = [run["id"] for run in runs if isinstance(run.get("id"), int)]
        return max(ids) if ids else None

    def _await_run(self, baseline: int | None) -> DispatchResult:
        deadline = time.monotonic() + self._run_timeout
        known = baseline or 0
        run_id: int | None = None
        while True:
            if run_id is None:
                candidates = [
                    run["id"] for run in self._runs() if run.get("id", 0) > known
                ]
                if candidates:
                    run_id = max(candidates)
            if run_id is not None:
                status, body = self._read_run(run_id)
                if status == 200 and isinstance(body, dict):
                    if body.get("status") == "completed":
                        conclusion = str(body.get("conclusion") or "unknown")
                        ok = conclusion == "success"
                        return DispatchResult(
                            ok=ok,
                            detail=f"workflow run {run_id} completed: {conclusion}",
                            exit_code=0 if ok else 1,
                            run_id=run_id,
                        )
            if time.monotonic() >= deadline:
                if run_id is None:
                    detail = (
                        "dispatched workflow run was not found within "
                        f"{self._run_timeout}s"
                    )
                else:
                    detail = (
                        f"workflow run {run_id} did not complete within "
                        f"{self._run_timeout}s"
                    )
                return DispatchResult(ok=False, detail=detail, run_id=run_id)
            self._sleep(self._poll_interval)

    # -- API -----------------------------------------------------------

    def _runs(self) -> list[dict[str, Any]]:
        path = (
            f"/repos/{self._repository}/actions/runs"
            f"?event=workflow_dispatch&branch={quote(self._ref, safe='')}&per_page=10"
        )
        try:
            status, body = self._api(path)
        except _GitHubNetworkError:
            return []
        if status != 200 or not isinstance(body, dict):
            return []
        runs = body.get("workflow_runs")
        if not isinstance(runs, list):
            return []
        return [run for run in runs if isinstance(run, dict)]

    def _read_run(self, run_id: int) -> tuple[int, Any]:
        try:
            return self._api(f"/repos/{self._repository}/actions/runs/{run_id}")
        except _GitHubNetworkError:
            return 0, None

    def _api(
        self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self._api_base}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "AICOR-backend",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                status = int(getattr(response, "status", None) or response.getcode())
                raw = response.read() if status < 300 else b""
        except urllib.error.HTTPError as error:
            return int(error.code), None
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise _GitHubNetworkError from error
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except ValueError:
            return status, None


class RefreshRunner:
    """Single-flight refresh controller."""

    def __init__(
        self,
        *,
        dispatcher: Dispatcher,
        target: str = "local",
        on_event: Callable[[str, dict[str, Any]], Any] | None = None,
        job_id_factory: Callable[[], str] | None = None,
        snapshot_reader: Callable[[], dict[str, Any] | None] | None = None,
        post_refresh: Callable[[], DispatchResult] | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._target = target
        self._on_event = on_event
        self._job_id_factory = job_id_factory or (
            lambda: "job_" + uuid.uuid4().hex[:12]
        )
        self._snapshot_reader = snapshot_reader
        self._post_refresh = post_refresh
        self._lock = threading.Lock()
        self._state = RefreshState(target=target)
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._state.status == "running"

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._state.as_dict()

    def trigger(self, reason: str) -> tuple[int, dict[str, Any]]:
        safe_reason = (str(reason or "manual").strip() or "manual")[:120]
        with self._lock:
            if self._stopped.is_set():
                return 503, {"status": "shutting_down"}
            if self._state.status == "running":
                return 409, {
                    "status": "conflict",
                    "reason": "refresh already in progress",
                    "refresh": self._state.as_dict(),
                }
            self._state = RefreshState(
                status="running",
                job_id=self._job_id_factory(),
                reason=safe_reason,
                started_at=utc_now_iso(),
                target=self._target,
            )
            job = self._state

        self._emit("refresh", job.as_dict())
        thread = threading.Thread(
            target=self._execute,
            args=(job.job_id or "", safe_reason),
            name=f"aicor-refresh-{job.job_id}",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return 202, {"status": "accepted", "refresh": self.status()}

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the current job thread; return ``True`` when it finished."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def stop(self, timeout: float | None = 10.0) -> None:
        """Stop accepting refreshes and terminate an in-flight local pipeline."""
        self._stopped.set()
        cancel = getattr(self._dispatcher, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _execute(self, job_id: str, reason: str) -> None:
        baseline = self._read_snapshot()
        baseline_version = baseline.get("snapshot_version") if baseline else None
        try:
            result = self._dispatcher.dispatch({"job_id": job_id, "reason": reason})
        except Exception as error:  # dispatchers must not leak message content
            result = DispatchResult(
                ok=False, detail=f"dispatcher error: {type(error).__name__}"
            )

        if result.ok and self._post_refresh is not None:
            try:
                sync = self._post_refresh()
            except Exception as error:
                sync = DispatchResult(
                    ok=False,
                    detail=f"post-refresh error: {type(error).__name__}",
                )
            if not sync.ok:
                result = replace(
                    result,
                    ok=False,
                    detail=f"post-refresh failed: {sync.detail}",
                    exit_code=sync.exit_code,
                    log_path=sync.log_path or result.log_path,
                )

        snapshot = self._read_snapshot() if result.ok else None
        version = snapshot.get("snapshot_version") if snapshot else None
        changed = None if version is None else version != baseline_version
        with self._lock:
            if self._state.job_id != job_id:
                return
            self._state = replace(
                self._state,
                status="succeeded" if result.ok else "failed",
                finished_at=utc_now_iso(),
                detail=result.detail,
                exit_code=result.exit_code,
                log_path=result.log_path,
                run_id=result.run_id,
                snapshot_version=version,
                snapshot_changed=changed,
            )
            final = self._state.as_dict()

        if snapshot is not None:
            self._emit("snapshot", snapshot_event(snapshot, changed=bool(changed)))
        self._emit("refresh_finished", final)

    def _read_snapshot(self) -> dict[str, Any] | None:
        if self._snapshot_reader is None:
            return None
        try:
            return self._snapshot_reader()
        except Exception:
            return None

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event, payload)
        except Exception:  # observability must never break a refresh
            pass


def build_dispatcher(config: BackendConfig) -> tuple[Dispatcher, str]:
    """Return the configured dispatcher and its public target name."""
    if config.github_token and config.github_repository:
        return (
            GitHubWorkflowDispatcher(
                repository=config.github_repository,
                token=config.github_token,
                workflow=config.github_workflow,
                ref=config.github_ref,
                poll_interval_seconds=config.github_poll_seconds,
                run_timeout_seconds=config.refresh_timeout_seconds,
            ),
            "github",
        )
    return (
        LocalPipelineDispatcher(
            command=config.pipeline_command,
            cwd=PROJECT_ROOT,
            timeout_seconds=config.refresh_timeout_seconds,
            log_dir=config.log_dir,
        ),
        "local",
    )


def run_post_refresh_command(
    command: tuple[str, ...],
    *,
    cwd: str | Path,
    timeout_seconds: int,
) -> DispatchResult:
    """Run the configured data-sync command after a successful refresh.

    GitHub dispatch mode commits data to the repository; it does not update the
    daemon's local snapshot. This hook lets the operator pull/download the new
    snapshot before the runner rereads it. Failure fails the refresh instead of
    reporting success against stale data.
    """
    timeout = max(1, int(timeout_seconds))
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return DispatchResult(
            ok=False, detail=f"post-refresh timed out after {timeout}s"
        )
    except OSError as error:
        return DispatchResult(
            ok=False,
            detail=f"post-refresh could not start: {type(error).__name__}",
        )

    output = _tail(completed.stdout.decode("utf-8", "replace"))
    if completed.returncode != 0:
        return DispatchResult(
            ok=False,
            detail=output or f"post-refresh exited with {completed.returncode}",
            exit_code=completed.returncode,
        )
    return DispatchResult(
        ok=True,
        detail=output or "post-refresh finished",
        exit_code=0,
    )


def build_post_refresh(config: BackendConfig) -> Callable[[], DispatchResult] | None:
    """Return the optional post-refresh sync hook for the configured command."""
    if not config.post_refresh_command:
        return None
    timeout = min(max(1, int(config.refresh_timeout_seconds)), 300)
    return lambda: run_post_refresh_command(
        config.post_refresh_command,
        cwd=PROJECT_ROOT,
        timeout_seconds=timeout,
    )


def _process_group_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _safe_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    return cleaned[:80] or "job"


def _tail_file(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_READ_BYTES))
            data = handle.read()
    except OSError:
        return ""
    return _tail(data.decode("utf-8", "replace"))


def _tail(text: str, limit: int = DETAIL_LIMIT) -> str:
    compact = " ".join(str(text).split())
    return compact[-limit:]
