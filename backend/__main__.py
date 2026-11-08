"""Run the AICOR backend: HTTP API, SSE stream, and freshness scheduler.

Usage:
    python -m backend
    python -m backend --port 8000 --no-auto-refresh
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
from dataclasses import replace
from pathlib import Path

from backend.events import EventBroker
from backend.runner import RefreshRunner, build_dispatcher, build_post_refresh
from backend.scheduler import FreshnessScheduler
from backend.server import create_server
from backend.settings import BackendConfig, load_backend_config
from backend.snapshot import SnapshotStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend",
        description="AICOR dashboard backend: API, SSE, and auto-refresh",
    )
    parser.add_argument("--host", help="bind address (default: AICOR_HOST)")
    parser.add_argument("--port", type=int, help="bind port (default: AICOR_PORT)")
    parser.add_argument(
        "--data-dir", help="dashboard data directory (default: AICOR_DATA_DIR)"
    )
    parser.add_argument(
        "--stale-after",
        type=int,
        help="seconds before a snapshot counts as stale",
    )
    parser.add_argument(
        "--refresh-interval",
        type=int,
        help="seconds between freshness checks",
    )
    parser.add_argument(
        "--no-auto-refresh",
        action="store_true",
        help="serve data and API without the background scheduler",
    )
    args = parser.parse_args(argv)

    overrides: dict[str, object] = {}
    if args.host:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.data_dir:
        overrides["data_dir"] = Path(args.data_dir).expanduser()
    if args.stale_after is not None:
        overrides["stale_after_seconds"] = max(1, args.stale_after)
    if args.refresh_interval is not None:
        overrides["refresh_interval_seconds"] = max(1, args.refresh_interval)
    if args.no_auto_refresh:
        overrides["auto_refresh"] = False

    config = replace(load_backend_config(), **overrides)
    server, runner, broker, target = build_runtime(config)

    scheduler: FreshnessScheduler | None = None
    if config.auto_refresh:
        scheduler = FreshnessScheduler(
            store=server.store,
            runner=runner,
            interval_seconds=config.refresh_interval_seconds,
            stale_after_seconds=config.stale_after_seconds,
            on_event=broker.publish,
        )
        server.scheduler = scheduler
        scheduler.start()

    snapshot = server.store.load()
    startup = {
        "service": "aicor-backend",
        "listen": f"http://{config.host}:{server.server_address[1]}",
        "refresh_mode": target,
        "auto_refresh": config.auto_refresh,
        "refresh_interval_seconds": config.refresh_interval_seconds,
        "stale_after_seconds": config.stale_after_seconds,
        "refresh_endpoint_enabled": bool(config.cron_secret),
        "snapshot": snapshot.freshness(config.stale_after_seconds),
    }
    print(json.dumps(startup, ensure_ascii=False), flush=True)

    install_signal_handlers(server)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if scheduler is not None:
            scheduler.stop()
        runner.stop()
        server.server_close()
        print(json.dumps({"service": "aicor-backend", "event": "stopped"}), flush=True)
    return 0


def build_runtime(config: BackendConfig):
    """Wire the store, broker, refresh runner and HTTP server."""
    store = SnapshotStore(config.data_dir)
    broker = EventBroker()
    dispatcher, target = build_dispatcher(config)
    runner = RefreshRunner(
        dispatcher=dispatcher,
        target=target,
        on_event=broker.publish,
        snapshot_reader=lambda: store.load().freshness(config.stale_after_seconds),
        post_refresh=build_post_refresh(config),
    )
    server = create_server(
        config=config, store=store, runner=runner, broker=broker
    )
    return server, runner, broker, target


def install_signal_handlers(server) -> None:
    """Shut down cleanly on SIGTERM/SIGINT (Docker stop, systemd, Ctrl+C)."""

    def request_shutdown(signum, frame) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    for name in ("SIGTERM", "SIGINT"):
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            signal.signal(number, request_shutdown)
        except (ValueError, OSError):
            continue


if __name__ == "__main__":
    raise SystemExit(main())
