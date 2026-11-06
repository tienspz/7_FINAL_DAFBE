"""Independent acceptance check for AICOR raw/preprocess outputs.

This script does two things:
1. Draws a deterministic, seeded sample of 10 displayed values from the
   dashboard JSON contracts and re-checks each value against its live source
   (SEC companyconcept, SEC XBRL instance, or Yahoo Finance chart API).
2. Checks the dashboard contracts, traceability, reconciliation, quality, and
   SQLite/CSV handoff artifacts.

Usage:
    python -m scripts.acceptance_check
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from pipeline.http import sec_user_agent

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "public" / "data"
VERIFIED_DIR = ROOT / "data" / "verified"
RAW_DIR = ROOT / "data" / "raw"
EVIDENCE_DIR = ROOT / "docs" / "evidence"
SEED = 20261104
CIKS = {"MSFT": "0000789019", "GOOGL": "0001652044"}
CORE_METRICS = ["revenue", "operating_income", "net_income", "rd_expense", "capex", "cfo"]
SEGMENT_TAGS = {
    "revenue": {"RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"},
    "operating_income": {"OperatingIncomeLoss"},
}
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json, application/xml, */*"})
LAST_REQUEST = 0.0


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def http_get(url: str) -> tuple[requests.Response, str, str]:
    global LAST_REQUEST
    SESSION.headers["User-Agent"] = sec_user_agent()
    elapsed = time.monotonic() - LAST_REQUEST
    if elapsed < 0.25:
        time.sleep(0.25 - elapsed)
    response = SESSION.get(url, timeout=90)
    LAST_REQUEST = time.monotonic()
    response.raise_for_status()
    return response, sha256_bytes(response.content), datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def quarter_end(key: str) -> date:
    year, quarter = key.split("-Q")
    month = int(quarter) * 3
    day = 31 if month in (3, 12) else 30
    return date(int(year), month, day)


def clean_member(value: str) -> str:
    return value.split(":")[-1]


def latest_completed_price_row(
    rows: list[dict[str, Any]], today: date | None = None
) -> dict[str, Any]:
    reference_date = today or date.today()
    completed = [
        row for row in rows if date.fromisoformat(row["date"]) < reference_date
    ]
    if not completed:
        raise ValueError("price history has no completed trading date")
    return max(completed, key=lambda row: row["date"])


def is_usable_financial(metric: dict[str, Any]) -> bool:
    split_adjusted = (
        metric.get("split_adjustment") is not None
        and metric.get("reported_value") is not None
    )
    return bool(
        metric.get("value") is not None
        and not metric.get("derived")
        and (metric.get("quality_flag") == "ok" or split_adjusted)
        and metric.get("accession_number")
        and metric.get("source_url")
        and metric.get("xbrl_tag")
        and "+" not in metric["xbrl_tag"]
        and metric.get("unit") in {"million USD", "USD/shares"}
        and metric.get("verified") is True
    )


def draw_samples(financials: dict[str, Any], rng: random.Random) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for ticker in ("MSFT", "GOOGL"):
        rows = [row for row in financials["quarters"] if row["ticker"] == ticker]
        core: dict[str, list[dict[str, Any]]] = {name: [] for name in CORE_METRICS}
        eps: list[dict[str, Any]] = []
        for row in rows:
            for name in CORE_METRICS:
                metric = row["metrics"].get(name)
                if metric and is_usable_financial(metric):
                    core[name].append(
                        {
                            "type": "financial",
                            "ticker": ticker,
                            "metric": name,
                            "calendar_key": row["calendar_key"],
                            "period_end": row["period_end"],
                            "displayed_value": metric["value"],
                            "displayed_unit": metric["unit"],
                            "accession_number": metric["accession_number"],
                            "xbrl_tag": metric["xbrl_tag"],
                            "source_url": metric["source_url"],
                        }
                    )
            metric = row["metrics"].get("eps_diluted")
            if metric and is_usable_financial(metric):
                eps.append(
                    {
                        "type": "financial",
                        "ticker": ticker,
                        "metric": "eps_diluted",
                        "calendar_key": row["calendar_key"],
                        "period_end": row["period_end"],
                        "displayed_value": metric["value"],
                        "displayed_unit": metric["unit"],
                        "accession_number": metric["accession_number"],
                        "xbrl_tag": metric["xbrl_tag"],
                        "source_url": metric["source_url"],
                        "reported_value": metric.get("reported_value"),
                        "split_adjustment": metric.get("split_adjustment"),
                    }
                )
        selected_metrics = rng.sample([name for name, items in core.items() if items], 2)
        for name in selected_metrics:
            samples.append(rng.choice(core[name]))
        samples.append(rng.choice(eps))

    segments = [
        row
        for row in financials["segments"]
        if row.get("value_musd") is not None
        and not row.get("derived")
        and row.get("accession_number")
        and row.get("evidence_url")
        and row.get("segment_member")
    ]
    for ticker in ("MSFT", "GOOGL"):
        picked = rng.choice([row for row in segments if row["ticker"] == ticker])
        samples.append(
            {
                "type": "segment",
                "ticker": ticker,
                "metric": picked["metric"],
                "calendar_key": picked["calendar_key"],
                "period_end": picked["period_end"],
                "segment_scheme": picked["segment_scheme"],
                "segment_name": picked["segment_name"],
                "segment_member": picked["segment_member"],
                "displayed_value": picked["value_musd"],
                "displayed_unit": "million USD",
                "accession_number": picked["accession_number"],
                "source_url": picked["source_url"],
                "evidence_url": picked["evidence_url"],
            }
        )

    for ticker in ("MSFT", "GOOGL"):
        price_payload = load_json(DATA_DIR / "prices" / f"{ticker}.json")
        last_row = latest_completed_price_row(price_payload["rows"])
        field = "close" if ticker == "MSFT" else "adj_close"
        samples.append(
            {
                "type": "price",
                "ticker": ticker,
                "metric": field,
                "trade_date": last_row["date"],
                "displayed_value": last_row[field],
                "displayed_unit": "USD/share",
                "source_url": price_payload["source_url"],
                "evidence_url": price_payload["evidence_url"],
            }
        )
    return samples


def verify_financial(sample: dict[str, Any]) -> dict[str, Any]:
    tag = sample["xbrl_tag"]
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{CIKS[sample['ticker']]}/us-gaap/{tag}.json"
    response, digest, fetched_at = http_get(url)
    payload = response.json()
    unit = "USD/shares" if sample["metric"] == "eps_diluted" else "USD"
    ratio = float(sample.get("split_adjustment") or 1.0)
    expected = sample["displayed_value"] * ratio if unit == "USD/shares" else sample["displayed_value"] * 1_000_000
    rows = payload.get("units", {}).get(unit, [])
    candidates = [
        row
        for row in rows
        if row.get("accn") == sample["accession_number"] and row.get("end") == sample["period_end"]
    ]
    if not candidates:
        return {**sample, "result": "fail", "reason": "accession/period not present in companyconcept", "source_url": url, "http_status": response.status_code, "response_sha256": digest, "fetched_at": fetched_at}
    row = min(candidates, key=lambda item: abs(float(item.get("val", 0)) - expected))
    source_value = float(row["val"])
    match = abs(source_value - expected) <= 0.01
    return {
        **sample,
        "result": "ok" if match else "fail",
        "reason": "" if match else "value mismatch",
        "source_url": url,
        "filing_url": sample["source_url"],
        "source_value_native": source_value,
        "source_value_display_unit": source_value if unit == "USD/shares" else round(source_value / 1_000_000, 3),
        "expected_source_value_native": expected,
        "difference": source_value - expected,
        "http_status": response.status_code,
        "response_sha256": digest,
        "fetched_at": fetched_at,
    }


def verify_segment(sample: dict[str, Any]) -> dict[str, Any]:
    response, digest, fetched_at = http_get(sample["evidence_url"])
    root = ET.fromstring(response.content)
    contexts: dict[str, tuple[str | None, str | None, dict[str, str]]] = {}
    for element in root.iter():
        if not element.tag.endswith("}context"):
            continue
        context_id = element.attrib.get("id", "")
        start = end = None
        dimensions: dict[str, str] = {}
        for child in element.iter():
            if child.tag.endswith("}startDate"):
                start = (child.text or "").strip()
            elif child.tag.endswith("}endDate"):
                end = (child.text or "").strip()
            elif child.tag.endswith("}instant"):
                end = (child.text or "").strip()
            elif child.tag.endswith("}explicitMember"):
                dimensions[child.attrib.get("dimension", "")] = (child.text or "").strip()
        contexts[context_id] = (start, end, dimensions)

    expected = sample["displayed_value"] * 1_000_000
    for element in root.iter():
        context_ref = element.attrib.get("contextRef")
        if context_ref not in contexts:
            continue
        _, end, dimensions = contexts[context_ref]
        if end != sample["period_end"] or len(dimensions) != 1:
            continue
        member = clean_member(next(iter(dimensions.values())))
        if member != sample["segment_member"]:
            continue
        local_name = element.tag.split("}")[-1]
        if local_name not in SEGMENT_TAGS.get(sample["metric"], set()):
            continue
        text = (element.text or "").strip()
        if not text:
            continue
        source_value = float(text)
        if abs(source_value - expected) <= 0.01:
            return {
                **sample,
                "result": "ok",
                "reason": "",
                "source_value_native": source_value,
                "source_value_display_unit": round(source_value / 1_000_000, 3),
                "http_status": response.status_code,
                "response_sha256": digest,
                "fetched_at": fetched_at,
            }
    return {**sample, "result": "fail", "reason": "segment fact not found in XBRL instance", "http_status": response.status_code, "response_sha256": digest, "fetched_at": fetched_at}


def verify_price(sample: dict[str, Any]) -> dict[str, Any]:
    response, digest, fetched_at = http_get(sample["evidence_url"])
    payload = response.json()
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    adjusted = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    source_value = None
    for index, timestamp in enumerate(timestamps):
        trade_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
        if trade_date != sample["trade_date"]:
            continue
        if sample["metric"] == "close":
            source_value = quote.get("close", [None])[index]
        else:
            source_value = adjusted[index] if index < len(adjusted) else None
        break
    if source_value is None:
        return {**sample, "result": "fail", "reason": "price date not found in Yahoo chart", "source_url": sample["evidence_url"], "http_status": response.status_code, "response_sha256": digest, "fetched_at": fetched_at}
    difference = abs(float(source_value) - float(sample["displayed_value"]))
    relative = difference / max(abs(float(source_value)), 1e-9)
    match = relative <= 0.001
    return {
        **sample,
        "result": "ok" if match else "fail",
        "reason": "" if match else "price differs by more than 0.1%",
        "source_url": sample["evidence_url"],
        "source_value_native": float(source_value),
        "difference": difference,
        "relative_difference": relative,
        "http_status": response.status_code,
        "response_sha256": digest,
        "fetched_at": fetched_at,
    }


def check(name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "result": "ok" if passed else "fail", "detail": detail}


def contract_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    required = [
        "manifest.json",
        "overview.json",
        "investor.json",
        "financials.json",
        "ai_analysis.json",
        "decision.json",
        "methodology.json",
        "tests.json",
        "prices/MSFT.json",
        "prices/GOOGL.json",
        "prices/SPY.json",
        "prices/QQQ.json",
    ]
    missing = [name for name in required if not (DATA_DIR / name).exists()]
    checks.append(check("dashboard_files", not missing, "missing: " + ", ".join(missing) if missing else "all present"))

    manifest = load_json(DATA_DIR / "manifest.json")
    snapshot = manifest.get("snapshot_version")
    metadata_ok = True
    metadata_detail: list[str] = []
    for name in required:
        if name == "manifest.json":
            continue
        obj = load_json(DATA_DIR / name)
        for field in ("schema_version", "snapshot_version", "generated_at"):
            if not obj.get(field):
                metadata_ok = False
                metadata_detail.append(f"{name}:{field}")
        if obj.get("snapshot_version") != snapshot:
            metadata_ok = False
            metadata_detail.append(f"{name}:snapshot_mismatch")
    checks.append(check("json_metadata", metadata_ok, ", ".join(metadata_detail) if metadata_detail else f"snapshot={snapshot}"))

    checksum_failures: list[str] = []
    for name, expected in manifest.get("checksums", {}).items():
        path = DATA_DIR / name
        if not path.exists():
            checksum_failures.append(f"{name}:missing")
            continue
        actual = "sha256:" + sha256_bytes(path.read_bytes())
        if actual != expected:
            checksum_failures.append(f"{name}:mismatch")
    checks.append(check("manifest_checksums", not checksum_failures, ", ".join(checksum_failures) if checksum_failures else f"{len(manifest.get('checksums', {}))} files"))

    financials = load_json(DATA_DIR / "financials.json")
    quarters = financials.get("quarters", [])
    per_ticker = {ticker: [row for row in quarters if row["ticker"] == ticker] for ticker in ("MSFT", "GOOGL")}
    expected_metrics = {
        "revenue", "operating_income", "net_income", "rd_expense", "capex", "cfo",
        "income_tax_expense", "pretax_income", "eps_diluted", "total_assets",
        "total_equity", "total_debt", "cash_and_st_investments",
    }
    traceability_ok = True
    traceability_detail: list[str] = []
    for ticker, rows in per_ticker.items():
        if len(rows) != 19:
            traceability_ok = False
            traceability_detail.append(f"{ticker}:quarters={len(rows)}")
        for row in rows:
            if set(row.get("metrics", {})) != expected_metrics:
                traceability_ok = False
                traceability_detail.append(f"{ticker}:{row['calendar_key']}:metrics")
            for name, metric in row.get("metrics", {}).items():
                if metric.get("value") is None or not metric.get("source_url") or not metric.get("accession_number") or not metric.get("xbrl_tag") or metric.get("verified") is not True:
                    traceability_ok = False
                    traceability_detail.append(f"{ticker}:{row['calendar_key']}:{name}:trace")
                if metric.get("quality_flag") == "missing":
                    traceability_ok = False
                    traceability_detail.append(f"{ticker}:{row['calendar_key']}:{name}:missing")
    checks.append(check("financials_38_quarters_with_traceability", len(quarters) == 38 and traceability_ok, ", ".join(traceability_detail[:8]) if traceability_detail else "38 quarters, 13 metrics, 0 missing"))
    keys = [(row["ticker"], row["calendar_key"]) for row in quarters]
    checks.append(check("financials_no_duplicate_quarters", len(keys) == len(set(keys)), f"{len(keys)} rows"))

    googl_eps = {
        row["calendar_key"]: row["metrics"]["eps_diluted"] for row in per_ticker["GOOGL"]
    }
    q1_eps = googl_eps.get("2022-Q1", {})
    adjusted_keys = {
        key for key, metric in googl_eps.items() if metric.get("split_adjustment") is not None
    }
    split_ok = (
        abs(float(q1_eps.get("value") or 0.0) - 1.231) <= 1e-9
        and abs(float(q1_eps.get("reported_value") or 0.0) - 24.62) <= 1e-9
        and float(q1_eps.get("split_adjustment") or 0.0) == 20.0
        and q1_eps.get("quality_flag") == "low"
        and adjusted_keys == {"2022-Q1"}
    )
    checks.append(
        check(
            "googl_pre_split_eps_adjustment",
            split_ok,
            f"adjusted={sorted(adjusted_keys)}, value={q1_eps.get('value')}, reported={q1_eps.get('reported_value')}",
        )
    )
    q4_googl = next(
        (row for row in per_ticker["GOOGL"] if row["calendar_key"] == "2022-Q4"),
        {},
    )
    q4_derived = q4_googl.get("derived_metrics", {})
    trailing_eps = q4_derived.get("eps_trailing_4q")
    trailing_pe = q4_derived.get("pe_trailing")
    trailing_ok = (
        trailing_eps is not None
        and abs(float(trailing_eps) - 4.56) <= 0.001
        and trailing_pe is not None
        and float(trailing_pe) > 0
    )
    checks.append(
        check(
            "googl_2022q4_trailing_eps",
            trailing_ok,
            f"eps_trailing_4q={trailing_eps}, pe_trailing={trailing_pe}",
        )
    )

    segments = financials.get("segments", [])
    segment_ok = bool(segments) and all(row.get("accession_number") and row.get("source_url") and row.get("evidence_url") for row in segments)
    checks.append(check("segment_contract", segment_ok, f"{len(segments)} segment rows"))
    schemes = {(row["ticker"], row["segment_scheme"]) for row in segments}
    checks.append(check("segment_schemes", schemes == {("MSFT", "msft_legacy_3"), ("MSFT", "msft_new_2"), ("GOOGL", "goog_3")}, str(sorted(schemes))))
    msft_new = [row for row in segments if row["ticker"] == "MSFT" and row["segment_scheme"] == "msft_new_2"]
    checks.append(check("msft_segment_break_not_comparable", bool(msft_new) and all(row["comparable"] is False for row in msft_new), f"{len(msft_new)} rows"))

    overview = load_json(DATA_DIR / "overview.json")
    checks.append(check("overview_contract", set(overview.get("kpis", {})) == {"MSFT", "GOOGL"} and overview.get("latest_quarter") == "2026-Q3" and set(overview.get("normalized_prices", {})) == {"MSFT", "GOOGL", "SPY", "QQQ"}, "kpis/normalized/latest_quarter"))

    investor = load_json(DATA_DIR / "investor.json")
    checks.append(check("investor_contract", set(investor.get("price_files", {})) == {"MSFT", "GOOGL", "SPY", "QQQ"} and investor.get("benchmarks") == ["SPY", "QQQ"] and len(investor.get("excess_return_tests", [])) == 2 and len(investor.get("monthly_returns", {})) == 4, "prices/benchmarks/returns"))

    ai = load_json(DATA_DIR / "ai_analysis.json")
    ai_events = ai.get("events") or []
    event_fields = (
        "id", "ticker", "published_date", "title", "category", "source_url",
        "evidence_quote", "content_sha256", "entered_by", "reviewed_by", "review_status",
    )
    events_ok = (
        bool(ai_events)
        and all(all(event.get(field) for field in event_fields) for event in ai_events)
        and all(event.get("review_status") == "verified" and event.get("http_status") == 200 for event in ai_events)
        and all(event.get("ticker") in {"MSFT", "GOOGL"} for event in ai_events)
    )
    empty_state_ok = (not ai_events and bool(ai.get("event_empty_state"))) or (bool(ai_events) and not ai.get("event_empty_state"))
    ai_ok = events_ok and empty_state_ok and "n = 11-15" in " ".join(ai.get("warnings", [])) and set(ai.get("label_definitions", {})) == {"Reported", "Proxy", "Estimated"} and len(ai.get("correlations", [])) == 70
    checks.append(check("ai_analysis_contract", ai_ok, f"{len(ai_events)} verified events, labels, 70 correlations"))

    decision = load_json(DATA_DIR / "decision.json")
    decision_ok = len(decision.get("comparison", [])) == 2 and all(row.get("not_investment_advice") is True for row in decision.get("comparison", [])) and "Không phải khuyến nghị" in decision.get("disclaimer", "")
    checks.append(check("decision_contract", decision_ok, "2 companies, disclaimer, no advice flag"))

    methodology = load_json(DATA_DIR / "methodology.json")
    limitations = " ".join(methodology.get("limitations", []))
    methodology_ok = len(methodology.get("formulas", {})) >= 15 and len(methodology.get("sources", [])) >= 17 and "MSFT changed" in limitations and "GOOGL revenue" in limitations and "n is small" in limitations
    checks.append(check("methodology_contract", methodology_ok, "formulas, sources, limitations"))

    tests = load_json(DATA_DIR / "tests.json")
    codes = {result.get("bt_code") for result in tests.get("results", [])}
    tests_ok = codes == {"BT1", "BT2", "BT3", "BT4", "BT5"} and len(tests.get("results", [])) == 78 and all(result.get("n") is not None and result.get("p_value") is not None and result.get("decision") for result in tests.get("results", [])) and all(result.get("p_adjusted") is not None for result in tests.get("results", []) if result.get("bt_code") in {"BT4", "BT5"})
    checks.append(check("bt1_bt5_contract", tests_ok, f"{len(tests.get('results', []))} results, codes={sorted(codes)}"))

    quality = load_json(VERIFIED_DIR / "quality_report.json")
    qsummary = quality.get("summary", {})
    quality_ok = qsummary.get("quarters_expected_total") == 38 and qsummary.get("quarters_present") == 38 and qsummary.get("missing_metric_cells") == 0 and qsummary.get("verified_ratio") == 1.0 and quality.get("tag_switch") and quality.get("segment_break")
    checks.append(check("quality_contract", quality_ok, json.dumps(qsummary, ensure_ascii=False)))
    checks.append(check("tag_switch_recorded", any(item.get("ticker") == "GOOGL" and item.get("calendar_key") == "2025-Q2" for item in quality.get("tag_switch", [])), "GOOGL 2025-Q2"))
    ai_report = load_json(VERIFIED_DIR / "ai_events_report.json")
    verified_events = ai_report.get("events", [])
    ai_evidence_ok = (
        quality.get("restatements") is not None
        and ai_report.get("verified") == len(ai_events)
        and len(verified_events) == len(ai_events)
        and all(re.fullmatch(r"[0-9a-f]{64}", event.get("content_sha256", "")) for event in verified_events)
        and all(event.get("checks", {}).get("quote_present") for event in verified_events)
        and all(event.get("checks", {}).get("published_date_matches") for event in verified_events)
    )
    checks.append(check("ai_event_evidence", ai_evidence_ok, f"verified={ai_report.get('verified')}, rejected={ai_report.get('rejected')}"))

    link = load_json(VERIFIED_DIR / "link_report.json")
    link_ok = (
        link.get("summary", {}).get("total", 0) >= 84
        and link.get("summary", {}).get("broken") == 0
        and link.get("summary", {}).get("ok", 0) > 0
    )
    negative = {item.get("id"): item.get("result") for item in link.get("negative_checks", [])}
    checks.append(check("link_report_contract", link_ok, json.dumps(link.get("summary", {}), ensure_ascii=False)))
    checks.append(check("negative_controls", negative == {"R1": "blocked", "R2": "broken", "R3": "soft404"}, str(negative)))

    reconcile = load_json(VERIFIED_DIR / "reconcile_report.json")
    rsummary = reconcile.get("summary", {})
    rchecks = reconcile.get("checks", [])
    q4 = [item for item in rchecks if item.get("check") == "q4_residual"]
    reconcile_ok = rsummary.get("fail") == 0 and len(q4) == 8 and all(item.get("status") == "ok" and item.get("residual", 1) <= 0.005 for item in q4)
    checks.append(check("reconcile_contract", reconcile_ok, json.dumps(rsummary, ensure_ascii=False)))

    secondary_checks = [item for item in rchecks if item.get("check") == "secondary_close"]
    secondary_ok = (
        len(secondary_checks) == 4
        and all(item.get("status") == "ok" for item in secondary_checks)
        and all(item.get("compared_days", 0) >= 30 for item in secondary_checks)
        and all(item.get("max_relative_difference", 1) <= 0.001 for item in secondary_checks)
        and all(item.get("response_sha256") for item in secondary_checks)
    )
    checks.append(check("secondary_close_contract", secondary_ok, "; ".join(f"{item.get('ticker')}={item.get('status')}" for item in secondary_checks)))

    adjusted_checks = [item for item in rchecks if item.get("check") == "secondary_adjusted_close"]
    adjusted_by_ticker = {item.get("ticker"): item for item in adjusted_checks}
    env_key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    key_present = bool(env_key) and env_key.lower() != "demo"
    if key_present:
        adjusted_ok = all(
            adjusted_by_ticker.get(ticker, {}).get("status") in {"ok", "low"}
            and adjusted_by_ticker.get(ticker, {}).get("response_sha256")
            for ticker in ("MSFT", "GOOGL")
        )
    else:
        adjusted_ok = len(adjusted_checks) == 4 and all(
            item.get("status") == "unverified" for item in adjusted_checks
        )
    checks.append(check("adjusted_close_contract", adjusted_ok, "; ".join(f"{item.get('ticker')}={item.get('status')}" for item in adjusted_checks)))
    allowlist = yaml.safe_load((ROOT / "config" / "allowlist.yaml").read_text(encoding="utf-8"))
    allowlist_ok = {"api.nasdaq.com", "blog.google", "alphavantage.co"}.issubset(
        set(allowlist.get("allowed_domains", []))
    )
    checks.append(
        check(
            "approved_allowlist_domains",
            allowlist_ok,
            f"{len(allowlist.get('allowed_domains', []))} domains, CR-13 additions approved",
        )
    )

    facts_path = RAW_DIR / "sec" / "facts.csv"
    facts_traceable = False
    if facts_path.exists():
        import csv

        with facts_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        facts_traceable = bool(rows) and all(
            row.get("source_url")
            and row.get("accession_number")
            and row.get("fetched_at")
            and row.get("response_sha256")
            and (
                row.get("is_original", "").lower() != "true"
                or row.get("verified", "").lower() == "true"
            )
            for row in rows
        )
    checks.append(check("raw_facts_traceability", facts_traceable, "source/accession/hash on every row; original facts verified"))

    run_id = manifest.get("run_id")
    run_manifest_path = RAW_DIR / "runs" / str(run_id) / "manifest.json" if run_id else None
    sync_log_path = VERIFIED_DIR / "sync_log.jsonl"
    audit_trail_ok = bool(run_manifest_path and run_manifest_path.exists() and sync_log_path.exists())
    audit_detail = []
    if audit_trail_ok:
        run_manifest = load_json(run_manifest_path)
        archived_files_ok = True
        for item in run_manifest.get("files", []):
            archived_path = RAW_DIR / item.get("path", "")
            if not archived_path.exists() or sha256_bytes(archived_path.read_bytes()) != item.get("sha256"):
                archived_files_ok = False
                audit_detail.append(f"archive:{item.get('path')}")
        sync_rows = [
            json.loads(line)
            for line in sync_log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        run_sync_rows = [item for item in sync_rows if item.get("run_id") == run_id]
        sync_ok = bool(run_sync_rows) and all(
            item.get("started_at") and item.get("finished_at") and item.get("source")
            and item.get("status") in {"success", "partial"}
            and isinstance(item.get("records_added"), int)
            for item in run_sync_rows
        )
        audit_trail_ok = run_manifest.get("run_id") == run_id and archived_files_ok and sync_ok
        if not archived_files_ok:
            audit_detail.append("archived raw file checksum mismatch")
        if not sync_ok:
            audit_detail.append("missing or failed source sync records")
    checks.append(
        check(
            "run_audit_trail",
            audit_trail_ok,
            "; ".join(audit_detail) if audit_detail else f"run_id={run_id}",
        )
    )

    cache_index = RAW_DIR / "_cache" / "_index.jsonl"
    cache_ok = cache_index.exists() and cache_index.read_text(encoding="utf-8").count("\n") >= 10
    checks.append(check("response_cache_present", cache_ok, str(cache_index)))

    actions_path = RAW_DIR / "prices" / "corporate_actions.csv"
    actions_ok = False
    if actions_path.exists():
        import csv

        with actions_path.open("r", encoding="utf-8", newline="") as handle:
            actions = list(csv.DictReader(handle))
        actions_ok = any(row.get("ticker") == "GOOGL" and row.get("action_date") == "2022-07-18" and row.get("action_type") == "split" and abs(float(row.get("value", 0)) - 20.0) < 1e-9 for row in actions)
    checks.append(check("googl_split_2022_07_18", actions_ok, "20:1 split recorded"))

    db_path = ROOT / "data" / "db" / "aicor.sqlite"
    db_ok = False
    db_detail = "missing"
    if db_path.exists():
        with sqlite3.connect(db_path) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("facts", "filings", "segments", "company_financials", "prices")
            }
        manifest_counts = manifest.get("row_counts", {})
        expected_counts = {
            "facts": manifest_counts.get("facts"),
            "filings": manifest_counts.get("filings"),
            "segments": manifest_counts.get("segments"),
            "company_financials": manifest_counts.get("financial_quarters"),
            "prices": manifest_counts.get("prices"),
        }
        db_ok = (
            all(counts.get(table) == value for table, value in expected_counts.items())
            and counts.get("company_financials") == 38
            and counts.get("prices", 0) > 0
        )
        db_detail = f"db={counts}, manifest={expected_counts}"
    checks.append(check("sqlite_handoff", db_ok, db_detail))

    total_bytes = sum(path.stat().st_size for path in DATA_DIR.rglob("*.json"))
    checks.append(check("web_data_size_under_5mb", total_bytes <= 5 * 1024 * 1024, f"{total_bytes} bytes"))

    max_price_date = max(
        load_json(DATA_DIR / "prices" / f"{ticker}.json")["rows"][-1]["date"]
        for ticker in ("MSFT", "GOOGL", "SPY", "QQQ")
    )
    checks.append(check("no_future_market_data", max_price_date <= manifest.get("data_as_of", ""), f"max_price_date={max_price_date}, data_as_of={manifest.get('data_as_of')}"))

    return checks


def main() -> int:
    for directory in (DATA_DIR, VERIFIED_DIR, RAW_DIR, EVIDENCE_DIR):
        if not directory.exists():
            print(f"Missing required directory: {directory}", file=sys.stderr)
            return 2

    financials = load_json(DATA_DIR / "financials.json")
    rng = random.Random(SEED)
    samples = draw_samples(financials, rng)
    verified_samples: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, start=1):
        sample_id = f"V{index:02d}"
        try:
            if sample["type"] == "financial":
                result = verify_financial(sample)
            elif sample["type"] == "segment":
                result = verify_segment(sample)
            else:
                result = verify_price(sample)
        except Exception as exc:  # noqa: BLE001 - acceptance must record, not crash
            result = {**sample, "result": "fail", "reason": f"{type(exc).__name__}: {exc}"}
        result["id"] = sample_id
        verified_samples.append(result)
        print(f"{sample_id} {result['type']:<9} {result['ticker']:<5} {result.get('metric', ''):<18} {result['result']:<4} {result.get('reason', '')}")

    matched = sum(1 for item in verified_samples if item["result"] == "ok")
    source_summary = {
        "total": len(verified_samples),
        "matched": matched,
        "failed": len(verified_samples) - matched,
        "passed": matched == len(verified_samples) == 10,
        "seed": SEED,
        "selection": "2 core financial + 1 EPS per company, 1 segment per company, 1 price per company",
    }

    checks = contract_checks()
    failed_checks = [item for item in checks if item["result"] != "ok"]
    contract_summary = {
        "total": len(checks),
        "passed": len(checks) - len(failed_checks),
        "failed": len(failed_checks),
        "passed_all": not failed_checks,
    }

    overall = "PASS" if source_summary["passed"] and contract_summary["passed_all"] else "FAIL"
    evidence = {
        "schema_version": "1.0",
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "snapshot_version": load_json(DATA_DIR / "manifest.json").get("snapshot_version"),
        "data_as_of": load_json(DATA_DIR / "manifest.json").get("data_as_of"),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "source_checks": source_summary,
        "samples": verified_samples,
        "contract_checks": contract_summary,
        "checks": checks,
        "overall": overall,
    }
    output_path = EVIDENCE_DIR / f"acceptance_{load_json(DATA_DIR / 'manifest.json').get('data_as_of')}.json"
    write_json(output_path, evidence)

    print()
    print(json.dumps({"source_checks": source_summary, "contract_checks": contract_summary, "overall": overall, "evidence": str(output_path)}, ensure_ascii=False, indent=2))
    if failed_checks:
        print("\nFailed contract checks:")
        for item in failed_checks:
            print(f"- {item['name']}: {item['detail']}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
