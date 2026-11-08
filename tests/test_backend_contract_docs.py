"""The checked-in HTTP/SSE contract stays parseable and complete."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

DOCS = Path(__file__).resolve().parents[1] / "docs" / "api"


def test_openapi_documents_every_http_route():
    document = yaml.safe_load((DOCS / "openapi.yaml").read_text(encoding="utf-8"))

    assert document["openapi"].startswith("3.1")
    paths = document["paths"]
    for path in (
        "/",
        "/api/health",
        "/api/manifest",
        "/api/latest",
        "/api/data/{key}",
        "/api/events",
        "/api/refresh",
    ):
        assert path in paths

    assert set(paths["/api/refresh"]) >= {"get", "post"}
    assert set(paths["/api/health"]["get"]["responses"]) >= {"200", "503"}
    assert "304" in paths["/api/manifest"]["get"]["responses"]
    assert "304" in paths["/api/data/{key}"]["get"]["responses"]
    assert "502" in paths["/api/data/{key}"]["get"]["responses"]
    assert "503" in paths["/api/events"]["get"]["responses"]
    assert "text/event-stream" in paths["/api/events"]["get"]["responses"]["200"][
        "content"
    ]
    for method in ("get", "post"):
        assert paths["/api/refresh"][method]["security"] == [
            {"CronBearer": []},
            {"CronHeader": []},
        ]
    security_schemes = document["components"]["securitySchemes"]
    assert security_schemes["CronBearer"]["scheme"] == "bearer"
    assert security_schemes["CronHeader"]["name"] == "X-Cron-Secret"


def test_openapi_schemas_cover_the_wire_contract():
    document = yaml.safe_load((DOCS / "openapi.yaml").read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]

    for name in (
        "Freshness",
        "RefreshState",
        "Manifest",
        "HealthResponse",
        "LatestResponse",
        "RefreshAccepted",
        "RefreshConflict",
        "ErrorResponse",
    ):
        assert name in schemas

    freshness = schemas["Freshness"]["properties"]
    for field in (
        "available",
        "snapshot_version",
        "generated_at",
        "age_seconds",
        "stale",
        "checksum_ok",
        "problems",
    ):
        assert field in freshness

    refresh = schemas["RefreshState"]["properties"]
    assert refresh["snapshot_changed"]["type"] == ["boolean", "null"]
    assert schemas["PublicConfig"]["properties"]["post_refresh_configured"]


def test_sse_schema_defines_one_snapshot_envelope():
    schema = json.loads(
        (DOCS / "sse-events.schema.json").read_text(encoding="utf-8")
    )
    definitions = schema["$defs"]

    for name in (
        "Freshness",
        "RefreshState",
        "SnapshotEvent",
        "ReadyEvent",
        "RefreshEvent",
        "RefreshFinishedEvent",
        "SchedulerErrorEvent",
        "SseEvent",
    ):
        assert name in definitions

    snapshot_event = definitions["SnapshotEvent"]
    assert set(snapshot_event["required"]) == {"snapshot", "changed"}
    assert snapshot_event["properties"]["snapshot"]["$ref"] == "#/$defs/Freshness"
    assert definitions["RefreshState"]["properties"]["snapshot_changed"][
        "type"
    ] == ["boolean", "null"]
    assert "snapshot" in definitions["ReadyEvent"]["required"]
    assert "heartbeat_seconds" in definitions["ReadyEvent"]["required"]


def test_typescript_types_match_the_documented_events():
    text = (DOCS / "types.ts").read_text(encoding="utf-8")

    for token in (
        "export interface Freshness",
        "export interface RefreshState",
        "export interface SnapshotEvent",
        "export interface ReadyEvent",
        "export type BackendEvent",
        'event: "snapshot"; data: SnapshotEvent',
        'event: "refresh_finished"; data: RefreshFinishedEvent',
        "snapshot_changed",
        "snapshotVersionOf",
    ):
        assert token in text


def test_api_readme_documents_the_consistency_protocol():
    text = (DOCS / "README.md").read_text(encoding="utf-8")

    for token in (
        "snapshot.snapshot_version",
        "changed=false",
        "AICOR_POST_REFRESH_COMMAND",
        "Vary: Accept-Encoding",
        "If-None-Match",
        "text/event-stream",
        "Authorization: Bearer <CRON_SECRET>",
    ):
        assert token in text
