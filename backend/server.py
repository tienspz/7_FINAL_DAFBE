"""HTTP API and SSE stream for the AICOR dashboard.

Read-only towards published data. Freshness responses are always
``Cache-Control: no-store``; dataset responses carry an ``ETag`` so a client
revalidates instead of caching a stale snapshot.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from backend.events import EventBroker, Subscription
from backend.runner import (
    RefreshController,
    RefreshRunner,
    build_dispatcher,
    build_post_refresh,
)
from backend.settings import BackendConfig
from backend.snapshot import (
    SnapshotStore,
    expected_checksum_matches,
    snapshot_event,
)
from pipeline.util import utc_now_iso

DATA_PREFIX = "/api/data/"
COMPRESS_MIN_BYTES = 1024
UTC = utc_now_iso


class AicorHttpServer(ThreadingHTTPServer):
    """Threaded HTTP server carrying the backend services."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        config: BackendConfig,
        store: SnapshotStore,
        runner: RefreshController,
        broker: EventBroker,
    ) -> None:
        super().__init__(address, handler)
        self.config = config
        self.store = store
        self.runner = runner
        self.broker = broker
        self.scheduler: Any = None
        self.started_at = utc_now_iso()
        self.started_monotonic = time.monotonic()


class AicorRequestHandler(BaseHTTPRequestHandler):
    """Route dashboard API requests."""

    server: AicorHttpServer
    server_version = "AICORBackend/1.0"
    protocol_version = "HTTP/1.1"
    timeout = 30
    quiet = False
    _head_only = False

    def log_message(self, fmt: str, *args: Any) -> None:
        if not self.quiet:
            super().log_message(fmt, *args)

    # -- verbs ---------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802 - http.server contract
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Max-Age", "600")
        self._apply_cors()
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802 - http.server contract
        self._head_only = True
        route = urlsplit(self.path)
        if self._normalized_path(route.path) == "/api/refresh":
            # HEAD must never start a crawl.
            self._send_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "method_not_allowed"},
                extra={"Allow": "GET, POST, OPTIONS"},
            )
            return
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802 - http.server contract
        route = urlsplit(self.path)
        if self._normalized_path(route.path) == "/api/refresh":
            self._handle_refresh(route)
            return
        self._method_not_allowed("GET, HEAD, OPTIONS")

    def do_PUT(self) -> None:  # noqa: N802 - http.server contract
        self._method_not_allowed("GET, HEAD, POST, OPTIONS")

    def do_PATCH(self) -> None:  # noqa: N802 - http.server contract
        self._method_not_allowed("GET, HEAD, POST, OPTIONS")

    def do_DELETE(self) -> None:  # noqa: N802 - http.server contract
        self._method_not_allowed("GET, HEAD, POST, OPTIONS")

    def do_GET(self) -> None:  # noqa: N802 - http.server contract
        route = urlsplit(self.path)
        path = self._normalized_path(route.path)
        if path == "/api/health":
            self._handle_health()
        elif path == "/api/manifest":
            self._handle_manifest()
        elif path == "/api/latest":
            self._handle_latest()
        elif path == "/api/refresh":
            self._handle_refresh(route)
        elif path == "/api/events":
            self._handle_events()
        elif path == "/api/data" or path.startswith(DATA_PREFIX):
            self._handle_data(path)
        elif path == "/":
            self._handle_index()
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "path": path})

    @staticmethod
    def _normalized_path(raw: str) -> str:
        trimmed = (raw or "").rstrip("/")
        return trimmed or "/"

    # -- handlers ------------------------------------------------------

    def _handle_index(self) -> None:
        snapshot = self.server.store.load()
        self._send_json(
            HTTPStatus.OK,
            {
                "service": "aicor-backend",
                "time": UTC(),
                "snapshot_version": snapshot.version,
                "endpoints": {
                    "health": "/api/health",
                    "manifest": "/api/manifest",
                    "latest": "/api/latest",
                    "dataset": "/api/data/{key}",
                    "events": "/api/events",
                    "refresh": "GET|POST /api/refresh (CRON_SECRET)",
                },
                "datasets": sorted(snapshot.files),
            },
        )

    def _handle_health(self) -> None:
        snapshot = self.server.store.load()
        freshness = snapshot.freshness(self.server.config.stale_after_seconds)
        if not snapshot.available:
            status = HTTPStatus.SERVICE_UNAVAILABLE
            state = "unavailable"
        elif not freshness["checksum_ok"] or freshness["stale"]:
            status = HTTPStatus.OK
            state = "degraded"
        else:
            status = HTTPStatus.OK
            state = "ok"

        payload: dict[str, Any] = {
            "status": state,
            "service": "aicor-backend",
            "time": UTC(),
            "uptime": {
                "started_at": self.server.started_at,
                "uptime_seconds": int(
                    time.monotonic() - self.server.started_monotonic
                ),
            },
            "snapshot": freshness,
            "refresh": self.server.runner.status(),
            "events": {
                "subscribers": self.server.broker.subscribers(),
                "capacity": self.server.config.max_sse_subscribers,
            },
            "config": {
                "refresh_mode": self.server.config.refresh_mode,
                "stale_after_seconds": self.server.config.stale_after_seconds,
                "refresh_interval_seconds": self.server.config.refresh_interval_seconds,
                "refresh_endpoint_enabled": bool(self.server.config.cron_secret),
                "post_refresh_configured": bool(
                    self.server.config.post_refresh_command
                ),
            },
        }
        scheduler = getattr(self.server, "scheduler", None)
        if scheduler is not None:
            payload["scheduler"] = scheduler.last_decision()
        self._send_json(status, payload)

    def _handle_manifest(self) -> None:
        snapshot = self.server.store.load()
        if not snapshot.available:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "snapshot_unavailable", "problems": list(snapshot.problems)},
            )
            return
        etag = _etag(snapshot.manifest_bytes)
        if _etag_matches(self.headers.get("If-None-Match"), etag):
            self._send_not_modified(etag, vary_encoding=True)
            return
        self._send_bytes(
            HTTPStatus.OK,
            snapshot.manifest_bytes,
            content_type="application/json; charset=utf-8",
            etag=etag,
            cache_control="no-cache, must-revalidate",
            extra={"X-AICOR-Snapshot": snapshot.version or ""},
        )

    def _handle_latest(self) -> None:
        store = self.server.store
        snapshot = store.load()
        if not snapshot.available:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "snapshot_unavailable", "problems": list(snapshot.problems)},
            )
            return
        payload: dict[str, Any] = {
            "freshness": snapshot.freshness(self.server.config.stale_after_seconds),
            "manifest": snapshot.manifest,
        }
        for key in ("overview", "decision"):
            document = store.read_json(snapshot, key)
            if document is not None:
                payload[key] = document
        self._send_json(HTTPStatus.OK, payload)

    def _handle_data(self, path: str) -> None:
        key = unquote(path[len(DATA_PREFIX):]) if path.startswith(DATA_PREFIX) else ""
        store = self.server.store
        snapshot = store.load()
        resolved = store.dataset_entry(snapshot, key) if key else None
        if resolved is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "unknown_dataset", "datasets": sorted(snapshot.files)},
            )
            return

        name, file_path, expected = resolved
        try:
            body = file_path.read_bytes()
        except OSError:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "dataset_unreadable", "dataset": name},
            )
            return
        if not expected_checksum_matches(body, expected, name):
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "checksum_mismatch",
                    "dataset": name,
                    "detail": "served bytes do not match the manifest checksum",
                },
            )
            return

        etag = _etag(body)
        if _etag_matches(self.headers.get("If-None-Match"), etag):
            self._send_not_modified(etag, vary_encoding=True)
            return
        self._send_bytes(
            HTTPStatus.OK,
            body,
            content_type="application/json; charset=utf-8",
            etag=etag,
            cache_control="no-cache, must-revalidate",
            extra={"X-AICOR-Snapshot": snapshot.version or ""},
        )

    def _handle_events(self) -> None:
        if self.server.broker.subscribers() >= self.server.config.max_sse_subscribers:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "sse_capacity",
                    "limit": self.server.config.max_sse_subscribers,
                },
            )
            return
        self.close_connection = True
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self._apply_cors()
        self.end_headers()
        if self._head_only:
            return

        subscription = self.server.broker.subscribe()
        heartbeat = self.server.config.sse_heartbeat_seconds
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            snapshot = self.server.store.load()
            self._write_sse(
                "ready",
                {
                    "snapshot": snapshot.freshness(
                        self.server.config.stale_after_seconds
                    ),
                    "refresh": self.server.runner.status(),
                    "heartbeat_seconds": heartbeat,
                },
            )
            while True:
                message = subscription.get(timeout=heartbeat)
                if message is None:
                    # A slow client may have missed a snapshot event. Send the
                    # current state instead of a bodyless comment so it can
                    # recover without reconnecting.
                    current = self.server.store.load()
                    self._write_sse(
                        "snapshot",
                        snapshot_event(
                            current.freshness(
                                self.server.config.stale_after_seconds
                            ),
                            changed=False,
                        ),
                    )
                    continue
                if message["event"] == "snapshot":
                    payload = message["data"]
                    if "snapshot" not in payload:
                        payload = snapshot_event(
                            payload, changed=bool(payload.get("changed"))
                        )
                    self._write_sse("snapshot", payload)
                    continue
                self._write_sse(message["event"], message["data"])
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass
        finally:
            self.server.broker.unsubscribe(subscription)

    def _handle_refresh(self, route: Any) -> None:
        refusal = self._refresh_refusal()
        if refusal is not None:
            status, payload = refusal
            self._send_json(status, payload)
            return
        reason = (parse_qs(route.query).get("reason") or ["api"])[0]
        status, payload = self.server.runner.trigger(reason)
        self._send_json(status, payload)

    def _refresh_refusal(self) -> tuple[int, dict[str, Any]] | None:
        secret = self.server.config.cron_secret
        if not secret:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "refresh_disabled",
                "detail": "CRON_SECRET is not configured on the backend",
            }
        authorization = self.headers.get("Authorization", "")
        bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        candidates = (bearer, self.headers.get("X-Cron-Secret", ""))
        if any(value and hmac.compare_digest(value, secret) for value in candidates):
            return None
        return HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"}

    # -- responses -----------------------------------------------------

    def _write_sse(self, event: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _method_not_allowed(self, allow: str) -> None:
        self._send_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "method_not_allowed"},
            extra={"Allow": allow},
        )

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        *,
        etag: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self._send_bytes(
            status,
            body,
            content_type="application/json; charset=utf-8",
            etag=etag,
            cache_control="no-store",
            extra=extra,
        )

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str,
        etag: str | None = None,
        cache_control: str = "no-store",
        extra: dict[str, str] | None = None,
    ) -> None:
        compressible = len(body) >= COMPRESS_MIN_BYTES
        encoding = "gzip" if compressible and self._accepts_gzip() else None
        payload = (
            gzip.compress(body, compresslevel=6, mtime=0)
            if encoding == "gzip"
            else body
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        if compressible:
            self.send_header("Vary", "Accept-Encoding")
        if encoding:
            self.send_header("Content-Encoding", encoding)
        if etag:
            self.send_header("ETag", etag)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self._apply_cors()
        self.end_headers()
        if not self._head_only:
            self.wfile.write(payload)

    def _accepts_gzip(self) -> bool:
        """Parse Accept-Encoding with explicit gzip/wildcard precedence."""
        header = self.headers.get("Accept-Encoding", "")
        gzip_q: float | None = None
        wildcard_q: float | None = None
        for item in header.split(","):
            name, _, params = item.strip().partition(";")
            name = name.strip().lower()
            if name not in {"gzip", "*"}:
                continue
            quality = 1.0
            for param in params.split(";"):
                key, _, value = param.strip().partition("=")
                if key.lower() == "q":
                    try:
                        quality = float(value)
                    except ValueError:
                        quality = 0.0
            if name == "gzip":
                gzip_q = quality
            else:
                wildcard_q = quality
        if gzip_q is not None:
            return gzip_q > 0
        return wildcard_q is not None and wildcard_q > 0

    def _send_not_modified(self, etag: str, *, vary_encoding: bool = False) -> None:
        self.send_response(HTTPStatus.NOT_MODIFIED)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        if vary_encoding:
            self.send_header("Vary", "Accept-Encoding")
        self._apply_cors()
        self.end_headers()

    def _apply_cors(self) -> None:
        origin = (self.headers.get("Origin") or "").rstrip("/")
        allowed = self.server.config.cors_origins
        if origin and ("*" in allowed or origin in allowed):
            self.send_header(
                "Access-Control-Allow-Origin", "*" if "*" in allowed else origin
            )
        if "*" not in allowed:
            # The response varies by Origin even when this particular origin
            # is absent or disallowed; shared caches must not reuse it.
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, X-Cron-Secret, Content-Type, If-None-Match",
        )
        self.send_header("Access-Control-Expose-Headers", "ETag, X-AICOR-Snapshot")


def _etag(body: bytes) -> str:
    # Weak validator: the identity and gzip representations are semantically
    # equivalent and may share the same ETag.
    return 'W/"' + hashlib.sha256(body).hexdigest() + '"'


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    target = etag[2:] if etag.startswith("W/") else etag
    for item in header.split(","):
        candidate = item.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == target:
            return True
    return False


def create_server(
    *,
    config: BackendConfig,
    store: SnapshotStore | None = None,
    runner: RefreshController | None = None,
    broker: EventBroker | None = None,
    quiet: bool = False,
) -> AicorHttpServer:
    """Build an HTTP server bound to ``config.host``/``config.port``."""
    resolved_store = store or SnapshotStore(config.data_dir)
    resolved_broker = broker or EventBroker()
    if runner is None:
        dispatcher, target = build_dispatcher(config)
        runner = RefreshRunner(
            dispatcher=dispatcher,
            target=target,
            on_event=resolved_broker.publish,
            snapshot_reader=lambda: resolved_store.load().freshness(
                config.stale_after_seconds
            ),
            post_refresh=build_post_refresh(config),
        )
    handler: type[BaseHTTPRequestHandler] = AicorRequestHandler
    if quiet:
        handler = type(
            "QuietAicorRequestHandler",
            (AicorRequestHandler,),
            {"quiet": True},
        )
    return AicorHttpServer(
        (config.host, config.port),
        handler,
        config=config,
        store=resolved_store,
        runner=runner,
        broker=resolved_broker,
    )
