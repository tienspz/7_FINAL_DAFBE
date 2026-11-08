"""Checked-in deployment artifacts are complete enough for an operator."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_keeps_data_and_logs_and_binds_loopback():
    document = yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    backend = document["services"]["backend"]

    assert backend["ports"] == ["127.0.0.1:8000:8000"]
    assert backend["env_file"] == [".env"]
    assert backend["healthcheck"]["test"][0] == "CMD"
    assert backend["restart"] == "unless-stopped"
    assert "aicor-snapshot:/app/web/public/data" in backend["volumes"]
    assert "aicor-pipeline-data:/app/data" in backend["volumes"]
    assert "aicor-logs:/app/logs" in backend["volumes"]
    assert set(document["volumes"]) >= {
        "aicor-snapshot",
        "aicor-pipeline-data",
        "aicor-logs",
    }


def test_nginx_proxies_sse_without_buffering_and_terminates_tls():
    text = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")

    for token in (
        "ssl_certificate",
        "location = /api/events",
        "proxy_buffering off",
        "proxy_cache off",
        "proxy_read_timeout 1h",
        "limit_req_zone",
        "gzip on",
        "return 301 https://",
    ):
        assert token in text
    # SSE must never be gzipped by the proxy.
    assert "text/event-stream" not in text.split("gzip_types", 1)[1].split(";", 1)[0]


def test_caddy_proxies_sse_without_buffering():
    text = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    for token in (
        "aicor.example.com",
        "encode gzip",
        "path /api/events",
        "flush_interval -1",
        "reverse_proxy 127.0.0.1:8000",
        "Strict-Transport-Security",
    ):
        assert token in text


def test_deploy_readme_lists_operator_inputs_and_smoke_tests():
    text = (ROOT / "deploy" / "README.md").read_text(encoding="utf-8")

    for token in (
        "CRON_SECRET",
        "AICOR_ALLOWED_ORIGINS",
        "SEC_USER_AGENT",
        "GITHUB_TOKEN_DISPATCH",
        "AICOR_POST_REFRESH_COMMAND",
        "snapshot_changed=false",
        "If-None-Match",
        "/api/events",
        "docker compose up -d",
    ):
        assert token in text
