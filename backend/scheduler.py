"""Background freshness loop.

Every tick the scheduler rereads the manifest, announces a new snapshot, and
starts one refresh when the snapshot is stale or missing. It never starts a
second refresh while one is running, and it never writes data itself.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

from backend.runner import RefreshController
from backend.snapshot import SnapshotStore, snapshot_event


class FreshnessScheduler(threading.Thread):
    """Daemon thread that keeps the published dashboard current."""

    def __init__(
        self,
        *,
        store: SnapshotStore,
        runner: RefreshController,
        interval_seconds: int,
        stale_after_seconds: int,
        on_event: Callable[[str, dict[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name="aicor-freshness-scheduler", daemon=True)
        self._store = store
        self._runner = runner
        self._interval = max(1, int(interval_seconds))
        self._stale_after = max(1, int(stale_after_seconds))
        self._on_event = on_event
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_signature: tuple[int, int] | None = None
        self._last_decision: dict[str, Any] = {
            "action": "idle",
            "reason": "scheduler not started",
        }

    @property
    def interval_seconds(self) -> int:
        return self._interval

    def last_decision(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_decision)

    def tick(self) -> dict[str, Any]:
        """Run one freshness evaluation and return the decision."""
        snapshot = self._store.load()

        if snapshot.available and snapshot.signature is not None:
            with self._lock:
                changed = (
                    self._last_signature is not None
                    and snapshot.signature != self._last_signature
                )
                if snapshot.signature != self._last_signature:
                    self._last_signature = snapshot.signature
                    publish = True
                else:
                    publish = False
            if publish:
                self._emit(
                    "snapshot",
                    snapshot_event(
                        snapshot.freshness(
                            self._stale_after, now=self._clock()
                        ),
                        changed=changed,
                    ),
                )

        if not snapshot.available:
            decision = self._trigger("missing-snapshot")
        else:
            age = snapshot.age_seconds(self._clock())
            if age is None:
                decision = self._trigger("missing-generated-at")
            elif age <= self._stale_after:
                decision = {
                    "action": "none",
                    "reason": "fresh",
                    "age_seconds": int(age),
                }
            else:
                decision = self._trigger("stale-snapshot")

        with self._lock:
            self._last_decision = decision
        return decision

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as error:  # keep the loop alive across bad snapshots
                self._emit("scheduler_error", {"error": type(error).__name__})
            self._stop.wait(self._interval)

    def stop(self, timeout: float | None = 5.0) -> None:
        self._stop.set()
        if self.is_alive():
            self.join(timeout)

    def _trigger(self, reason: str) -> dict[str, Any]:
        if self._runner.running:
            return {"action": "wait", "reason": "refresh-in-flight"}
        status, payload = self._runner.trigger(reason)
        if status == 202:
            return {
                "action": "triggered",
                "reason": reason,
                "job_id": (payload.get("refresh") or {}).get("job_id"),
            }
        return {"action": "conflict", "reason": reason}

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event, payload)
        except Exception:
            pass
