"""HTTP and SSE contract tests for the backend service."""

from __future__ import annotations

import gzip
import http.client
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.events import EventBroker
from backend.server import create_server
from backend.settings import BackendConfig
from tests.helpers import write_dashboard_snapshot


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._running = False
        self._status: dict = {"status": "idle", "job_id": None, "reason": ""}

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> dict:
        return self._status

    def trigger(self, reason: str) -> tuple[int, dict]:
        self.calls.append(reason)
        if self._running:
            return 409, {"status": "conflict", "refresh": self._status}
        self._running = True
        self._status = {"status": "running", "job_id": "job_fake", "reason": reason}
        return 202, {"status": "accepted", "refresh": self._status}


def _timestamp(hours_ago: float = 0.0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def start_service(
    data_dir: Path,
    *,
    cron_secret: str | None = "test-secret",
    stale_after_seconds: int = 3600,
    runner: FakeRunner | None = None,
    broker: EventBroker | None = None,
    max_sse_subscribers: int = 128,
    sse_heartbeat_seconds: int = 15,
    post_refresh_command: tuple[str, ...] | None = None,
) -> SimpleNamespace:
    config = BackendConfig(
        data_dir=data_dir,
        host="127.0.0.1",
        port=0,
        cron_secret=cron_secret,
        stale_after_seconds=stale_after_seconds,
        max_sse_subscribers=max_sse_subscribers,
        sse_heartbeat_seconds=sse_heartbeat_seconds,
        post_refresh_command=post_refresh_command,
        cors_origins=("http://localhost:5173",),
    )
    resolved_broker = broker or EventBroker()
    resolved_runner = runner or FakeRunner()
    server = create_server(
        config=config,
        runner=resolved_runner,
        broker=resolved_broker,
        quiet=True,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
    )
    thread.start()
    return SimpleNamespace(
        server=server,
        runner=resolved_runner,
        broker=resolved_broker,
        port=server.server_address[1],
        thread=thread,
        data_dir=data_dir,
    )


def stop_service(service: SimpleNamespace) -> None:
    service.server.shutdown()
    service.server.server_close()
    service.thread.join(timeout=5)


def request(port: int, path: str, *, method: str = "GET", headers=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", method=method, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def read_sse_event(response):
    event = None
    data_lines: list[str] = []
    while True:
        line = response.readline()
        if not line:
            raise AssertionError("SSE stream closed before an event arrived")
        text = line.decode("utf-8").rstrip("\r\n")
        if text == "":
            if event or data_lines:
                return event, "\n".join(data_lines)
            continue
        if text.startswith(":"):
            continue
        field, _, value = text.partition(":")
        value = value.lstrip(" ")
        if field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)


@pytest.fixture
def fresh_service(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    service = start_service(root)
    yield service
    stop_service(service)


def test_health_reports_fresh_snapshot(fresh_service):
    status, headers, body = request(fresh_service.port, "/api/health")
    payload = json.loads(body)

    assert status == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "aicor-backend"
    assert payload["snapshot"]["snapshot_version"] == "v20261106.5"
    assert payload["snapshot"]["data_as_of"] == "2026-11-06"
    assert payload["snapshot"]["checksum_ok"] is True
    assert payload["snapshot"]["stale"] is False
    assert payload["refresh"]["status"] == "idle"
    assert payload["events"]["subscribers"] == 0
    assert headers["Cache-Control"] == "no-store"


def test_health_degrades_when_snapshot_is_stale(tmp_path):
    root = write_dashboard_snapshot(
        tmp_path / "data", generated_at=_timestamp(hours_ago=3)
    )
    service = start_service(root, stale_after_seconds=3600)
    try:
        status, _, body = request(service.port, "/api/health")
        payload = json.loads(body)
    finally:
        stop_service(service)

    assert status == 200
    assert payload["status"] == "degraded"
    assert payload["snapshot"]["stale"] is True
    assert payload["snapshot"]["age_seconds"] >= 3600


def test_health_is_503_without_manifest(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    service = start_service(empty)
    try:
        status, _, body = request(service.port, "/api/health")
        payload = json.loads(body)
    finally:
        stop_service(service)

    assert status == 503
    assert payload["status"] == "unavailable"
    assert payload["snapshot"]["available"] is False


def test_manifest_supports_etag_revalidation(fresh_service):
    status, headers, body = request(fresh_service.port, "/api/manifest")
    manifest = json.loads(body)
    etag = headers["ETag"]

    assert status == 200
    assert manifest["snapshot_version"] == "v20261106.5"
    assert etag is not None
    assert headers["X-AICOR-Snapshot"] == "v20261106.5"

    status, headers, body = request(
        fresh_service.port, "/api/manifest", headers={"If-None-Match": etag}
    )
    assert status == 304
    assert body == b""


def test_dataset_is_served_after_checksum_verification(fresh_service):
    status, headers, body = request(fresh_service.port, "/api/data/financials")

    assert status == 200
    assert json.loads(body) == {"schema_version": "1.0", "quarters": []}
    assert headers["X-AICOR-Snapshot"] == "v20261106.5"
    assert "no-cache" in headers["Cache-Control"]

    status, _, body = request(fresh_service.port, "/api/data/prices/MSFT")
    assert status == 200
    assert json.loads(body)["rows"] == []


def test_tampered_dataset_is_refused(fresh_service):
    target = Path(fresh_service.data_dir) / "financials.json"
    target.write_bytes(b'{"schema_version": "1.0", "quarters": [1, 2]}\n')

    status, _, body = request(fresh_service.port, "/api/data/financials")

    assert status == 502
    assert json.loads(body)["error"] == "checksum_mismatch"


def test_unknown_and_unsafe_dataset_names_are_404(fresh_service):
    status, _, body = request(fresh_service.port, "/api/data/nope")
    assert status == 404
    assert json.loads(body)["error"] == "unknown_dataset"
    assert "financials" in json.loads(body)["datasets"]

    for path in (
        "/api/data/%2E%2E%2Fmanifest.json",
        "/api/data/prices/../../manifest.json",
    ):
        status, _, payload = request(fresh_service.port, path)
        assert status == 404
        assert json.loads(payload)["error"] == "unknown_dataset"


def test_cors_allows_only_configured_origins(fresh_service):
    status, headers, _ = request(
        fresh_service.port, "/api/health", headers={"Origin": "http://localhost:5173"}
    )
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"

    status, headers, _ = request(
        fresh_service.port, "/api/health", headers={"Origin": "https://evil.example"}
    )
    assert "Access-Control-Allow-Origin" not in headers


def test_options_preflight(fresh_service):
    status, headers, body = request(
        fresh_service.port,
        "/api/refresh",
        method="OPTIONS",
        headers={"Origin": "http://localhost:5173"},
    )

    assert status == 204
    assert body == b""
    assert "POST" in headers["Access-Control-Allow-Methods"]
    assert "X-Cron-Secret" in headers["Access-Control-Allow-Headers"]


def test_refresh_requires_the_configured_secret(fresh_service):
    assert request(fresh_service.port, "/api/refresh")[0] == 401
    assert (
        request(
            fresh_service.port, "/api/refresh", headers={"X-Cron-Secret": "wrong"}
        )[0]
        == 401
    )

    status, _, body = request(
        fresh_service.port,
        "/api/refresh?reason=vercel-cron",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert status == 202
    assert json.loads(body)["refresh"]["job_id"] == "job_fake"
    assert fresh_service.runner.calls == ["vercel-cron"]


def test_refresh_is_disabled_without_a_secret(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    service = start_service(root, cron_secret=None)
    try:
        status, _, body = request(
            service.port, "/api/refresh", headers={"X-Cron-Secret": "anything"}
        )
    finally:
        stop_service(service)

    assert status == 503
    assert json.loads(body)["error"] == "refresh_disabled"


def test_refresh_conflict_while_a_job_runs(fresh_service):
    fresh_service.runner._running = True

    status, _, body = request(
        fresh_service.port,
        "/api/refresh",
        headers={"X-Cron-Secret": "test-secret"},
    )

    assert status == 409
    assert json.loads(body)["status"] == "conflict"


def test_latest_includes_freshness_manifest_and_documents(fresh_service):
    status, headers, body = request(fresh_service.port, "/api/latest")
    payload = json.loads(body)

    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert payload["freshness"]["checksum_ok"] is True
    assert payload["manifest"]["snapshot_version"] == "v20261106.5"
    assert payload["overview"]["kpis"] == []
    assert payload["decision"]["companies"] == {}


def test_latest_omits_a_document_that_fails_its_checksum(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    (root / "overview.json").write_bytes(
        b'{"schema_version": "1.0", "kpis": [{"tampered": true}]}\n'
    )
    service = start_service(root)
    try:
        status, _, body = request(service.port, "/api/latest")
        payload = json.loads(body)
    finally:
        stop_service(service)

    assert status == 200
    assert payload["freshness"]["checksum_ok"] is False
    assert "overview" not in payload
    assert payload["decision"]["companies"] == {}


def test_events_stream_delivers_ready_and_published_snapshot(fresh_service):
    connection = http.client.HTTPConnection(
        "127.0.0.1", fresh_service.port, timeout=10
    )
    try:
        connection.request("GET", "/api/events")
        response = connection.getresponse()

        assert response.status == 200
        assert response.getheader("Content-Type").startswith("text/event-stream")

        event, data = read_sse_event(response)
        assert event == "ready"
        ready = json.loads(data)
        assert ready["snapshot"]["snapshot_version"] == "v20261106.5"
        assert ready["heartbeat_seconds"] == 15

        fresh_service.broker.publish(
            "snapshot",
            {
                "snapshot": {"snapshot_version": "v20261108.1", "stale": False},
                "changed": True,
            },
        )
        event, data = read_sse_event(response)
        assert event == "snapshot"
        payload = json.loads(data)
        assert payload["snapshot"]["snapshot_version"] == "v20261108.1"
        assert payload["changed"] is True
    finally:
        connection.close()


def test_events_normalizes_a_legacy_flat_snapshot_payload(fresh_service):
    connection = http.client.HTTPConnection(
        "127.0.0.1", fresh_service.port, timeout=10
    )
    try:
        connection.request("GET", "/api/events")
        response = connection.getresponse()
        assert response.status == 200
        assert read_sse_event(response)[0] == "ready"

        fresh_service.broker.publish(
            "snapshot", {"snapshot_version": "v20261108.1", "changed": True}
        )
        event, data = read_sse_event(response)
        payload = json.loads(data)
    finally:
        connection.close()

    assert event == "snapshot"
    assert payload["snapshot"]["snapshot_version"] == "v20261108.1"
    assert payload["changed"] is True


def test_events_heartbeat_publishes_the_current_snapshot(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    service = start_service(root, sse_heartbeat_seconds=1)
    connection = http.client.HTTPConnection("127.0.0.1", service.port, timeout=10)
    try:
        connection.request("GET", "/api/events")
        response = connection.getresponse()
        assert response.status == 200
        assert read_sse_event(response)[0] == "ready"

        # No broker message is published: the timeout path must send a
        # resynchronization snapshot rather than a bodyless comment.
        event, data = read_sse_event(response)
        payload = json.loads(data)
        assert event == "snapshot"
        assert payload["changed"] is False
        assert payload["snapshot"]["snapshot_version"] == "v20261106.5"
    finally:
        connection.close()
        stop_service(service)


def test_unknown_route_returns_404(fresh_service):
    status, _, body = request(fresh_service.port, "/api/unknown")

    assert status == 404
    assert json.loads(body)["error"] == "not_found"


def test_index_lists_endpoints_and_datasets(fresh_service):
    status, _, body = request(fresh_service.port, "/")
    payload = json.loads(body)

    assert status == 200
    assert payload["endpoints"]["events"] == "/api/events"
    assert "prices/MSFT" in payload["datasets"]


def test_head_mirrors_get_without_a_body(fresh_service):
    status, headers, body = request(
        fresh_service.port, "/api/manifest", method="HEAD"
    )

    assert status == 200
    assert body == b""
    assert int(headers["Content-Length"]) > 0
    assert headers["X-AICOR-Snapshot"] == "v20261106.5"


def _large_snapshot(tmp_path) -> tuple[Path, dict]:
    financials = {
        "schema_version": "1.0",
        "quarters": [{"value": "x" * 40, "index": index} for index in range(80)],
    }
    root = write_dashboard_snapshot(
        tmp_path / "data",
        generated_at=_timestamp(),
        documents={
            "financials.json": financials,
            "overview.json": {"schema_version": "1.0", "kpis": []},
            "decision.json": {"schema_version": "1.0", "companies": {}},
            "prices/MSFT.json": {"schema_version": "1.0", "rows": []},
        },
    )
    return root, financials


def test_large_dataset_is_gzipped_with_a_weak_etag(tmp_path):
    root, financials = _large_snapshot(tmp_path)
    service = start_service(root)
    try:
        status, headers, body = request(
            service.port,
            "/api/data/financials",
            headers={"Accept-Encoding": "gzip"},
        )
        etag = headers["ETag"]

        assert status == 200
        assert headers["Content-Encoding"] == "gzip"
        assert json.loads(gzip.decompress(body)) == financials
        assert etag.startswith('W/"')
        assert "Accept-Encoding" in headers.get_all("Vary")

        status, headers, body = request(
            service.port,
            "/api/data/financials",
            headers={"Accept-Encoding": "gzip", "If-None-Match": etag},
        )
        assert status == 304
        assert body == b""
        assert headers["ETag"] == etag
        assert "Accept-Encoding" in headers.get_all("Vary")

        # Strong and list forms of If-None-Match also revalidate a weak ETag.
        for candidate in (etag[2:], f'"other", {etag}'):
            status, _, _ = request(
                service.port,
                "/api/data/financials",
                headers={"If-None-Match": candidate},
            )
            assert status == 304
    finally:
        stop_service(service)


def test_large_dataset_is_identity_without_gzip_acceptance(tmp_path):
    root, financials = _large_snapshot(tmp_path)
    service = start_service(root)
    try:
        status, headers, body = request(
            service.port,
            "/api/data/financials",
            headers={"Accept-Encoding": "identity"},
        )

        assert status == 200
        assert "Content-Encoding" not in headers
        assert json.loads(body) == financials
        assert "Accept-Encoding" in headers.get_all("Vary")

        status, headers, body = request(
            service.port,
            "/api/data/financials",
            headers={"Accept-Encoding": "gzip;q=0"},
        )
        assert status == 200
        assert "Content-Encoding" not in headers
        assert json.loads(body) == financials
    finally:
        stop_service(service)


def test_head_mirrors_the_gzip_representation(tmp_path):
    root, _ = _large_snapshot(tmp_path)
    service = start_service(root)
    try:
        _, get_headers, _ = request(
            service.port,
            "/api/data/financials",
            headers={"Accept-Encoding": "gzip"},
        )
        status, head_headers, body = request(
            service.port,
            "/api/data/financials",
            method="HEAD",
            headers={"Accept-Encoding": "gzip"},
        )

        assert status == 200
        assert body == b""
        assert head_headers["Content-Encoding"] == "gzip"
        assert head_headers["Content-Length"] == get_headers["Content-Length"]
    finally:
        stop_service(service)


def test_cors_vary_is_sent_even_without_an_allowed_origin(fresh_service):
    status, headers, _ = request(
        fresh_service.port, "/api/health", headers={"Origin": "https://evil.example"}
    )
    assert status == 200
    assert "Access-Control-Allow-Origin" not in headers
    assert "Origin" in headers.get_all("Vary")

    status, headers, _ = request(fresh_service.port, "/api/health")
    assert status == 200
    assert "Origin" in headers.get_all("Vary")


def test_health_reports_post_refresh_configuration(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    service = start_service(root, post_refresh_command=("git", "pull"))
    try:
        status, _, body = request(service.port, "/api/health")
        payload = json.loads(body)
    finally:
        stop_service(service)

    assert status == 200
    assert payload["config"]["post_refresh_configured"] is True


def test_head_on_refresh_never_starts_a_job(fresh_service):
    status, headers, _ = request(
        fresh_service.port,
        "/api/refresh",
        method="HEAD",
        headers={"X-Cron-Secret": "test-secret"},
    )

    assert status == 405
    assert "POST" in headers["Allow"]
    assert fresh_service.runner.calls == []


def test_unsupported_method_returns_405_with_allow(fresh_service):
    status, headers, body = request(
        fresh_service.port, "/api/refresh", method="DELETE"
    )

    assert status == 405
    assert "GET" in headers["Allow"]
    assert "POST" in headers["Allow"]
    assert json.loads(body)["error"] == "method_not_allowed"


def test_health_reports_uptime_and_event_capacity(fresh_service):
    status, _, body = request(fresh_service.port, "/api/health")
    payload = json.loads(body)

    assert status == 200
    assert payload["uptime"]["uptime_seconds"] >= 0
    assert payload["uptime"]["started_at"]
    assert payload["events"]["capacity"] == 128


def test_events_refuses_new_subscribers_at_capacity(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_timestamp())
    service = start_service(root, max_sse_subscribers=1)
    connection = http.client.HTTPConnection("127.0.0.1", service.port, timeout=10)
    try:
        connection.request("GET", "/api/events")
        response = connection.getresponse()
        assert response.status == 200
        event, _ = read_sse_event(response)
        assert event == "ready"

        status, _, body = request(service.port, "/api/events")
        assert status == 503
        assert json.loads(body)["error"] == "sse_capacity"
        assert json.loads(body)["limit"] == 1
    finally:
        connection.close()
        stop_service(service)


def test_signal_handler_requests_a_graceful_shutdown():
    import signal

    from backend.__main__ import install_signal_handlers

    class FakeServer:
        def __init__(self) -> None:
            self.called = threading.Event()

        def shutdown(self) -> None:
            self.called.set()

    server = FakeServer()
    previous = {
        number: signal.getsignal(number)
        for number in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        install_signal_handlers(server)
        signal.raise_signal(signal.SIGTERM)
        assert server.called.wait(5) is True
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
