"""Runtime configuration for the AICOR backend service.

All values come from the environment so the same code runs locally, in a
container, and next to a Vercel deployment. Secrets are read here but never
included in ``BackendConfig.public_dict``.
"""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "web" / "public" / "data"
DEFAULT_STALE_AFTER_SECONDS = 21600
DEFAULT_REFRESH_INTERVAL_SECONDS = 900
DEFAULT_REFRESH_TIMEOUT_SECONDS = 2100
DEFAULT_SSE_HEARTBEAT_SECONDS = 15
DEFAULT_MAX_SSE_SUBSCRIBERS = 128
DEFAULT_GITHUB_POLL_SECONDS = 20
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://localhost:3000")
DEFAULT_PIPELINE_COMMAND = (sys.executable, "-m", "pipeline.run", "--mode", "full")


@dataclass(frozen=True)
class BackendConfig:
    """Resolved backend settings."""

    data_dir: Path = DEFAULT_DATA_DIR
    host: str = "127.0.0.1"
    port: int = 8000
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS
    refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS
    refresh_timeout_seconds: int = DEFAULT_REFRESH_TIMEOUT_SECONDS
    sse_heartbeat_seconds: int = DEFAULT_SSE_HEARTBEAT_SECONDS
    max_sse_subscribers: int = DEFAULT_MAX_SSE_SUBSCRIBERS
    github_poll_seconds: int = DEFAULT_GITHUB_POLL_SECONDS
    log_dir: Path = DEFAULT_LOG_DIR
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    cron_secret: str | None = None
    auto_refresh: bool = True
    pipeline_command: tuple[str, ...] = DEFAULT_PIPELINE_COMMAND
    post_refresh_command: tuple[str, ...] | None = None
    github_repository: str | None = None
    github_token: str | None = None
    github_workflow: str = "hourly-crawl.yml"
    github_ref: str = "main"

    @property
    def refresh_mode(self) -> str:
        """How a refresh is executed: ``github`` dispatch or local pipeline."""
        return "github" if self.github_token and self.github_repository else "local"

    def public_dict(self) -> dict[str, object]:
        """Operational settings safe to print or return over HTTP."""
        return {
            "data_dir": str(self.data_dir),
            "host": self.host,
            "port": self.port,
            "stale_after_seconds": self.stale_after_seconds,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "refresh_timeout_seconds": self.refresh_timeout_seconds,
            "sse_heartbeat_seconds": self.sse_heartbeat_seconds,
            "max_sse_subscribers": self.max_sse_subscribers,
            "github_poll_seconds": self.github_poll_seconds,
            "log_dir": str(self.log_dir),
            "cors_origins": list(self.cors_origins),
            "auto_refresh": self.auto_refresh,
            "refresh_mode": self.refresh_mode,
            "refresh_endpoint_enabled": bool(self.cron_secret),
            "post_refresh_configured": bool(self.post_refresh_command),
        }


def _integer(
    env: Mapping[str, str], name: str, default: int, *, minimum: int = 1
) -> int:
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if value >= minimum else default


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _origins(env: Mapping[str, str]) -> tuple[str, ...]:
    raw = env.get("AICOR_ALLOWED_ORIGINS")
    if not raw:
        return DEFAULT_CORS_ORIGINS
    items = tuple(
        item.strip().rstrip("/") for item in str(raw).split(",") if item.strip()
    )
    return items or DEFAULT_CORS_ORIGINS


def _pipeline_command(env: Mapping[str, str]) -> tuple[str, ...]:
    raw = env.get("AICOR_PIPELINE_COMMAND")
    if not raw:
        return DEFAULT_PIPELINE_COMMAND
    parts = tuple(shlex.split(str(raw), posix=os.name != "nt"))
    return parts or DEFAULT_PIPELINE_COMMAND


def _optional_command(
    env: Mapping[str, str], name: str
) -> tuple[str, ...] | None:
    raw = env.get(name)
    if not raw or not str(raw).strip():
        return None
    parts = tuple(shlex.split(str(raw), posix=os.name != "nt"))
    return parts or None


def _optional(env: Mapping[str, str], name: str) -> str | None:
    raw = env.get(name)
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def load_backend_config(env: Mapping[str, str] | None = None) -> BackendConfig:
    """Build a :class:`BackendConfig` from environment variables."""
    values = os.environ if env is None else env
    data_dir = _optional(values, "AICOR_DATA_DIR")
    log_dir = _optional(values, "AICOR_LOG_DIR")
    return BackendConfig(
        data_dir=Path(data_dir).expanduser() if data_dir else DEFAULT_DATA_DIR,
        host=_optional(values, "AICOR_HOST") or "127.0.0.1",
        port=_integer(values, "AICOR_PORT", 8000, minimum=0),
        stale_after_seconds=_integer(
            values, "AICOR_STALE_AFTER_SECONDS", DEFAULT_STALE_AFTER_SECONDS
        ),
        refresh_interval_seconds=_integer(
            values, "AICOR_REFRESH_INTERVAL_SECONDS", DEFAULT_REFRESH_INTERVAL_SECONDS
        ),
        refresh_timeout_seconds=_integer(
            values, "AICOR_REFRESH_TIMEOUT_SECONDS", DEFAULT_REFRESH_TIMEOUT_SECONDS
        ),
        sse_heartbeat_seconds=_integer(
            values, "AICOR_SSE_HEARTBEAT_SECONDS", DEFAULT_SSE_HEARTBEAT_SECONDS
        ),
        max_sse_subscribers=_integer(
            values, "AICOR_MAX_SSE_SUBSCRIBERS", DEFAULT_MAX_SSE_SUBSCRIBERS
        ),
        github_poll_seconds=_integer(
            values, "AICOR_GITHUB_POLL_SECONDS", DEFAULT_GITHUB_POLL_SECONDS
        ),
        log_dir=Path(log_dir).expanduser() if log_dir else DEFAULT_LOG_DIR,
        cors_origins=_origins(values),
        cron_secret=_optional(values, "CRON_SECRET"),
        auto_refresh=_boolean(values, "AICOR_AUTO_REFRESH", True),
        pipeline_command=_pipeline_command(values),
        post_refresh_command=_optional_command(
            values, "AICOR_POST_REFRESH_COMMAND"
        ),
        github_repository=_optional(values, "AICOR_GITHUB_REPOSITORY"),
        github_token=_optional(values, "GITHUB_TOKEN_DISPATCH"),
        github_workflow=_optional(values, "AICOR_GITHUB_WORKFLOW") or "hourly-crawl.yml",
        github_ref=_optional(values, "AICOR_GITHUB_REF") or "main",
    )
