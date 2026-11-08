"""Rebuild snapshot statistics from verified dashboard data without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from pipeline.config import WEB_DATA_DIR, load_yaml
from pipeline.preprocess.facts import MetricValue
from pipeline.stats.tests import present_p_values, run_all_tests
from pipeline.util import atomic_write_text, sha256_bytes

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERIFIED_MANIFEST = PROJECT_ROOT / "data" / "verified" / "manifest.json"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _manifest_checksum(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n") if path.suffix.lower() == ".json" else path.read_bytes()
    return "sha256:" + sha256_bytes(content)


def _snapshot_inputs(web_data_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = _read_json(web_data_dir / "manifest.json")
    financials = _read_json(web_data_dir / "financials.json")
    investor = _read_json(web_data_dir / "investor.json")
    snapshot = manifest.get("snapshot_version")
    if not snapshot or not manifest.get("generated_at") or not manifest.get("data_as_of"):
        raise ValueError("Manifest is missing snapshot_version, generated_at, or data_as_of")

    checksums = manifest.get("checksums")
    if not isinstance(checksums, dict):
        raise ValueError("Manifest has no checksum mapping")
    for name in ("financials.json", "investor.json"):
        path = web_data_dir / name
        expected = checksums.get(name)
        if not path.is_file() or not expected or _manifest_checksum(path) != expected:
            raise ValueError(f"Input checksum is missing or invalid: {name}")

    for name, payload in (("financials.json", financials), ("investor.json", investor)):
        if payload.get("snapshot_version") != snapshot:
            raise ValueError(f"Input belongs to a different snapshot: {name}")
        if payload.get("generated_at") != manifest["generated_at"]:
            raise ValueError(f"Input generated_at does not match manifest: {name}")

    quarters = financials.get("quarters")
    if not isinstance(quarters, list) or not quarters:
        raise ValueError("financials.json has no quarterly rows")
    expected_quarters = manifest.get("row_counts", {}).get("financial_quarters")
    if expected_quarters is None or len(quarters) != expected_quarters:
        raise ValueError(
            f"Financial quarter count does not match manifest: "
            f"{len(quarters)} != {expected_quarters}"
        )
    keys = [(row.get("ticker"), row.get("calendar_key")) for row in quarters]
    if any(not ticker or not quarter for ticker, quarter in keys) or len(keys) != len(set(keys)):
        raise ValueError("financials.json has incomplete or duplicate ticker/quarter keys")
    return manifest, financials, investor


def _metric_value(data: dict[str, Any]) -> MetricValue:
    allowed = {item.name for item in fields(MetricValue)}
    if "value" not in data or not data.get("unit"):
        raise ValueError("Financial metric is missing value or unit")
    values = {key: value for key, value in data.items() if key in allowed}
    return MetricValue(**values)


def build_statistics_snapshot(
    web_data_dir: Path = WEB_DATA_DIR,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest, financials, investor = _snapshot_inputs(web_data_dir)
    config = thresholds if thresholds is not None else load_yaml("thresholds.yaml")
    quality = config["quality"]
    stats_config = config["stats"]

    rows_by_ticker: dict[str, list[dict[str, Any]]] = {"MSFT": [], "GOOGL": []}
    for source_row in financials["quarters"]:
        metrics = source_row.get("metrics")
        derived = source_row.get("derived_metrics")
        if not isinstance(metrics, dict) or not isinstance(derived, dict):
            raise ValueError(
                f"Financial row is missing metrics/derived_metrics: "
                f"{source_row.get('ticker')} {source_row.get('calendar_key')}"
            )
        ticker = source_row["ticker"]
        if ticker not in {"MSFT", "GOOGL"}:
            raise ValueError(f"Unexpected ticker in financial snapshot: {ticker}")
        if any(not isinstance(metric, dict) for metric in metrics.values()):
            raise ValueError(
                f"Financial row contains a malformed metric: "
                f"{ticker} {source_row.get('calendar_key')}"
            )
        rows_by_ticker[ticker].append(
            {
                **source_row,
                "metrics": {
                    name: _metric_value(metric)
                    for name, metric in metrics.items()
                },
                "derived": derived,
            }
        )
    if any(not rows for rows in rows_by_ticker.values()):
        raise ValueError("Financial snapshot must contain exactly MSFT and GOOGL")
    for rows in rows_by_ticker.values():
        rows.sort(key=lambda row: row["calendar_key"])

    monthly_returns = investor.get("monthly_returns")
    if not isinstance(monthly_returns, dict) or not monthly_returns:
        raise ValueError("investor.json has no monthly return series")
    if not {"MSFT", "GOOGL", "SPY", "QQQ"}.issubset(monthly_returns):
        raise ValueError("Investor snapshot is missing a stock or benchmark return series")
    price_analytics = {
        ticker: {"monthly_returns": returns}
        for ticker, returns in monthly_returns.items()
    }

    primary = str(quality.get("quality_mode_primary", "B")).upper()
    if primary not in {"A", "B"}:
        raise ValueError(f"Invalid quality_mode_primary: {primary}")
    one_off_quarters = {
        ticker: {
            item["calendar_key"]: item.get("reason", "one-off quarter")
            for item in items
        }
        for ticker, items in quality.get("net_income_one_off_quarters", {}).items()
    }
    payload = run_all_tests(
        rows_by_ticker=rows_by_ticker,
        price_analytics=price_analytics,
        tickers=["MSFT", "GOOGL"],
        alpha=stats_config["alpha"],
        max_lag=stats_config["max_lag"],
        quality_mode="label_low" if primary == "B" else "exclude_low",
        quality_mode_primary=primary,
        bt1_start=stats_config.get("bt1_start"),
        bt1_end=manifest["data_as_of"],
        one_off_quarters=one_off_quarters or None,
        comparison_modes=tuple(quality.get("stats_quality_modes", ["exclude_low", "label_low"])),
        holm_primary=stats_config.get("holm_primary", "bt"),
        fragility_max_n=int(stats_config.get("fragility_max_n", 15)),
        permutation_iterations=int(stats_config.get("permutation_iterations", 10000)),
        permutation_seed=int(stats_config.get("permutation_seed", 20261107)),
        bt3_bootstrap_iterations=int(stats_config.get("bt3_bootstrap_iterations", 1000)),
        bt3_block_length=int(stats_config.get("bt3_block_length", 4)),
        bt3_bootstrap_seed=int(stats_config.get("bt3_bootstrap_seed", 20261107)),
    )
    payload = present_p_values(payload)
    payload["snapshot_version"] = manifest["snapshot_version"]
    payload["generated_at"] = manifest["generated_at"]
    return payload


def refresh_snapshot(
    web_data_dir: Path = WEB_DATA_DIR,
    verified_dir: Path | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verified_manifest_path = (
        verified_dir / "manifest.json" if verified_dir is not None else VERIFIED_MANIFEST
    )
    manifest, _, _ = _snapshot_inputs(web_data_dir)
    verified_manifest = _read_json(verified_manifest_path)
    for field in ("snapshot_version", "run_id", "data_as_of", "generated_at"):
        if verified_manifest.get(field) != manifest.get(field):
            raise ValueError(f"Verified manifest does not match dashboard manifest: {field}")

    payload = build_statistics_snapshot(web_data_dir, thresholds)
    encoded_stats = _canonical_json_bytes(payload)
    updated_manifest = dict(manifest)
    checksums = dict(manifest["checksums"])
    checksums["tests.json"] = "sha256:" + hashlib.sha256(encoded_stats).hexdigest()
    updated_manifest["checksums"] = checksums
    encoded_manifest = _canonical_json_bytes(updated_manifest).decode("utf-8")

    atomic_write_text(web_data_dir / "tests.json", encoded_stats.decode("utf-8"))
    atomic_write_text(web_data_dir / "manifest.json", encoded_manifest)
    atomic_write_text(verified_manifest_path, encoded_manifest)
    return updated_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild statistics from the current verified snapshot without network access"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that the current statistics and manifest checksum match a fresh rebuild",
    )
    args = parser.parse_args(argv)

    stats_path = WEB_DATA_DIR / "tests.json"
    if args.check:
        payload = build_statistics_snapshot()
        current = _read_json(stats_path) if stats_path.exists() else None
        manifest = _read_json(WEB_DATA_DIR / "manifest.json")
        expected_checksum = "sha256:" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
        if current == payload and manifest.get("checksums", {}).get("tests.json") == expected_checksum:
            print(f"Statistics snapshot is current: {payload['snapshot_version']}")
            return 0
        print("Statistics snapshot is stale; run python -m scripts.rebuild_stats to refresh.", file=sys.stderr)
        return 1

    manifest = refresh_snapshot()
    payload = _read_json(stats_path)
    print(
        json.dumps(
            {
                "snapshot_version": payload["snapshot_version"],
                "schema_version": payload["schema_version"],
                "quality_mode": payload["quality_mode"],
                "results": len(payload.get("results", [])),
                "sensitivity_results": len(payload.get("quality_mode_comparison", [])),
                "manifest_checksum": manifest["checksums"]["tests.json"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
