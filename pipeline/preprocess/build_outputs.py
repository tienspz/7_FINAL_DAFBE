"""Build dashboard JSON contracts and the manifest."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.config import Settings
from pipeline.preprocess.prices import normalized_series
from pipeline.util import sha256_bytes, to_million, utc_now_iso, write_json


def next_snapshot_version(web_data_dir: Path, as_of: str) -> str:
    manifest_path = web_data_dir / "manifest.json"
    prefix = f"v{as_of.replace('-', '')}."
    if not manifest_path.exists():
        return prefix + "1"
    try:
        current = json.loads(manifest_path.read_text(encoding="utf-8")).get("snapshot_version", "")
    except json.JSONDecodeError:
        return prefix + "1"
    if current.startswith(prefix):
        try:
            return prefix + str(int(current.split(".")[-1]) + 1)
        except ValueError:
            pass
    return prefix + "1"


def _latest_quarter(rows_by_ticker: dict[str, list[dict[str, Any]]]) -> str:
    keys = [row["calendar_key"] for rows in rows_by_ticker.values() for row in rows]
    return max(keys) if keys else ""


def _metric_output(metric: Any) -> dict[str, Any]:
    return metric.to_dict() if hasattr(metric, "to_dict") else metric


def build_financials(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    segment_rows: list[dict[str, Any]],
    snapshot_version: str,
    generated_at: str,
) -> dict[str, Any]:
    quarters: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        for row in rows:
            quarters.append(
                {
                    "ticker": ticker,
                    "calendar_key": row["calendar_key"],
                    "period_end": row["period_end"],
                    "fiscal_year": row["fiscal_year"],
                    "fiscal_quarter": row["fiscal_quarter"],
                    "metrics": {name: _metric_output(metric) for name, metric in row["metrics"].items()},
                    "derived_metrics": row.get("derived", {}),
                }
            )
    quarters.sort(key=lambda item: (item["ticker"], item["calendar_key"]))
    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "companies": list(rows_by_ticker.keys()),
        "quarters": quarters,
        "segments": segment_rows,
    }


def build_overview(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    price_analytics: dict[str, Any],
    prices_by_ticker: dict[str, Any],
    snapshot_version: str,
    generated_at: str,
    data_as_of: str,
) -> dict[str, Any]:
    kpis: dict[str, Any] = {}
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: row["calendar_key"])
        latest = ordered[-1] if ordered else None
        revenue_metric = latest["metrics"].get("revenue") if latest else None
        derived = latest.get("derived", {}) if latest else {}
        kpis[ticker] = {
            "stock_return_1y": price_analytics.get(ticker, {}).get("roi_1y"),
            "revenue_growth_latest": derived.get("revenue_growth_yoy"),
            "operating_margin_latest": derived.get("operating_margin"),
            "fcf_margin_latest": derived.get("fcf_margin"),
            "latest_quarter": latest["calendar_key"] if latest else None,
            "period_end": latest["period_end"] if latest else None,
            "revenue_source_url": revenue_metric.source_url if revenue_metric else None,
            "revenue_accession_number": revenue_metric.accession_number if revenue_metric else None,
        }

    end = date.fromisoformat(data_as_of)
    start = date(end.year - 1, end.month, end.day)
    normalized = {
        ticker: normalized_series(frame, start, end)
        for ticker, frame in prices_by_ticker.items()
    }
    comparison: dict[str, Any] = {}
    for ticker, rows in rows_by_ticker.items():
        comparison[ticker] = [
            {
                "calendar_key": row["calendar_key"],
                "revenue_growth_yoy": row["derived"].get("revenue_growth_yoy"),
                "operating_margin": row["derived"].get("operating_margin"),
                "fcf_margin": row["derived"].get("fcf_margin"),
            }
            for row in sorted(rows, key=lambda item: item["calendar_key"])
        ]
    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "latest_quarter": _latest_quarter(rows_by_ticker),
        "kpis": kpis,
        "normalized_prices": normalized,
        "business_comparison": comparison,
    }


def build_investor(
    *,
    price_analytics: dict[str, Any],
    tests: dict[str, Any],
    snapshot_version: str,
    generated_at: str,
) -> dict[str, Any]:
    bt1 = [result for result in tests.get("results", []) if result.get("bt_code") == "BT1"]
    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "benchmarks": ["SPY", "QQQ"],
        "price_files": {ticker: f"prices/{ticker}.json" for ticker in price_analytics},
        "roi_windows": {
            ticker: {
                "roi_1y": analytics.get("roi_1y"),
                "roi_3y": analytics.get("roi_3y"),
                "roi_5y": analytics.get("roi_5y"),
                "annualized_volatility": analytics.get("annualized_volatility"),
                "max_drawdown": analytics.get("max_drawdown"),
            }
            for ticker, analytics in price_analytics.items()
        },
        "monthly_returns": {
            ticker: analytics.get("monthly_returns", [])
            for ticker, analytics in price_analytics.items()
        },
        "quarterly_returns": {
            ticker: analytics.get("quarterly_returns", [])
            for ticker, analytics in price_analytics.items()
        },
        "quarter_end_prices": {
            ticker: analytics.get("quarter_end", {})
            for ticker, analytics in price_analytics.items()
        },
        "excess_return_tests": bt1,
        "calculator_note": "Calculator uses split-adjusted close plus dividends; charts use adjusted close. Do not add dividends twice.",
    }


def build_ai_analysis(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    tests: dict[str, Any],
    snapshot_version: str,
    generated_at: str,
) -> dict[str, Any]:
    correlations = [
        result
        for result in tests.get("results", [])
        if result.get("bt_code") in {"BT4", "BT5"}
    ]
    indicators: dict[str, Any] = {}
    for ticker, rows in rows_by_ticker.items():
        indicators[ticker] = [
            {
                "calendar_key": row["calendar_key"],
                "rd_growth_yoy": row["derived"].get("rd_growth_yoy"),
                "capex_growth_yoy": row["derived"].get("capex_growth_yoy"),
                "revenue_growth_yoy": row["derived"].get("revenue_growth_yoy"),
                "fcf_growth_yoy": row["derived"].get("fcf_growth_yoy"),
                "operating_margin": row["derived"].get("operating_margin"),
                "stock_return_quarter": row["derived"].get("stock_return_quarter"),
            }
            for row in sorted(rows, key=lambda item: item["calendar_key"])
        ]
    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "label_definitions": {
            "Reported": "Value taken directly from an SEC filing.",
            "Proxy": "R&D or CapEx used as a company-level proxy for AI investment; not AI-specific spend.",
            "Estimated": "Not used in the MVP.",
        },
        "correlations": correlations,
        "indicators": indicators,
        "events": [],
        "event_empty_state": "Chưa có sự kiện AI nào được kiểm chứng. Không hiển thị sự kiện mẫu.",
        "warnings": [
            "n = 11-15 at lags 0-4; results are reference only.",
            "Correlation does not imply causation.",
        ],
    }


def _status_for(row: dict[str, Any], thresholds: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    derived = row.get("derived", {})
    positive = 0
    negative = 0
    if (derived.get("revenue_growth_yoy") or 0) >= thresholds.get("revenue_growth_positive", 0.10):
        positive += 1
        reasons.append("Revenue growth above threshold")
    else:
        negative += 1
        reasons.append("Revenue growth below threshold")
    if (derived.get("operating_margin") or 0) >= thresholds.get("operating_margin_positive", 0.20):
        positive += 1
    if (derived.get("fcf_margin") or 0) >= thresholds.get("fcf_margin_positive", 0.15):
        positive += 1
    if (derived.get("capex_intensity") or 0) > thresholds.get("capex_intensity_caution", 0.25):
        negative += 1
        reasons.append("CapEx intensity is high")
    if (derived.get("pe_trailing") or 0) > thresholds.get("pe_caution", 35):
        negative += 1
        reasons.append("Trailing P/E is high")
    if positive > negative:
        return "Tích cực", reasons
    if negative > positive:
        return "Cần thận trọng", reasons
    return "Trung lập", reasons


def build_decision(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    price_analytics: dict[str, Any],
    settings: Settings,
    snapshot_version: str,
    generated_at: str,
) -> dict[str, Any]:
    decision_thresholds = settings.thresholds.get("decision", {})
    comparison: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: row["calendar_key"])
        latest = ordered[-1]
        derived = latest["derived"]
        status, reasons = _status_for(latest, decision_thresholds)
        comparison.append(
            {
                "ticker": ticker,
                "calendar_key": latest["calendar_key"],
                "period_end": latest["period_end"],
                "stock_return_quarter": derived.get("stock_return_quarter"),
                "revenue_growth_yoy": derived.get("revenue_growth_yoy"),
                "operating_margin": derived.get("operating_margin"),
                "fcf_growth_yoy": derived.get("fcf_growth_yoy"),
                "rd_intensity": derived.get("rd_intensity"),
                "capex_intensity": derived.get("capex_intensity"),
                "eps_trailing_4q": derived.get("eps_trailing_4q"),
                "pe_trailing": derived.get("pe_trailing"),
                "annualized_volatility": price_analytics.get(ticker, {}).get("annualized_volatility"),
                "max_drawdown": price_analytics.get(ticker, {}).get("max_drawdown"),
                "status": status,
                "reasons": reasons,
                "not_investment_advice": True,
            }
        )
    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "thresholds_version": settings.thresholds.get("version", "1.0"),
        "comparison": comparison,
        "disclaimer": "Không phải khuyến nghị đầu tư. Chỉ hiển thị dữ liệu và tiêu chí định lượng.",
    }


def build_methodology(
    *,
    settings: Settings,
    quality_report: dict[str, Any],
    link_report: dict[str, Any],
    reconcile_report: dict[str, Any],
    snapshot_version: str,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "formulas": {
            "revenue_growth_yoy": "(Revenue_t - Revenue_t-4) / Revenue_t-4",
            "operating_margin": "Operating Income / Revenue",
            "net_profit_margin": "Net Income / Revenue",
            "rd_intensity": "R&D / Revenue",
            "capex_intensity": "CapEx / Revenue",
            "fcf": "CFO - CapEx",
            "fcf_margin": "FCF / Revenue",
            "roe": "Net Income / Average Equity",
            "tax_rate": "Income Tax Expense / Pretax Income, clamped [0, 0.5]",
            "nopat": "Operating Income * (1 - Tax Rate)",
            "invested_capital": "Total Debt + Total Equity - Cash & Short-term Investments",
            "roic": "NOPAT / Average Invested Capital",
            "eps_trailing_4q": "Sum of diluted EPS over four quarters",
            "pe_trailing": "Quarter-end price / trailing four-quarter EPS",
            "quarterly_return": "Adjusted close at quarter end / prior quarter end - 1",
        },
        "sources": settings.source_registry.get("sources", []),
        "negative_sources": settings.source_registry.get("negative_sources", []),
        "quality_report_summary": quality_report.get("summary", {}),
        "link_report_summary": link_report.get("summary", {}),
        "reconcile_summary": reconcile_report.get("summary", {}),
        "limitations": [
            "yfinance is an unofficial source; version and output format must be pinned.",
            "Nasdaq API and Alpha Vantage are outside the current CR-13 allowlist; secondary price checks are pending.",
            "Adjusted-close cross-source verification is unverified until a real Alpha Vantage key is available.",
            "MSFT changed its segment structure in 2026-Q3; old and new segments are not directly comparable.",
            "GOOGL revenue changed XBRL tags at 2025-Q2; the switch is recorded in tag_switch.",
            "n is small: 19 quarters; YoY leaves 15 and lag 4 leaves 11.",
            "No AI event is included unless reviewed and verified.",
        ],
    }


def build_manifest(
    *,
    web_data_dir: Path,
    files: list[str],
    snapshot_version: str,
    generated_at: str,
    data_as_of: str,
    latest_quarter: str,
    row_counts: dict[str, int],
    link_report: dict[str, Any],
    quality_report: dict[str, Any],
    source_versions: dict[str, str],
) -> dict[str, Any]:
    checksums: dict[str, str] = {}
    for name in files:
        path = web_data_dir / name
        if path.exists():
            checksums[name] = "sha256:" + sha256_bytes(path.read_bytes())
    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "latest_quarter": latest_quarter,
        "companies": ["MSFT", "GOOGL"],
        "files": {name.replace(".json", ""): name for name in files},
        "row_counts": row_counts,
        "source_versions": source_versions,
        "link_report_summary": link_report.get("summary", {}),
        "quality_summary": quality_report.get("summary", {}),
        "checksums": checksums,
    }


def write_price_files(
    *,
    web_data_dir: Path,
    prices_by_ticker: dict[str, Any],
    snapshot_version: str,
    generated_at: str,
) -> list[str]:
    files: list[str] = []
    for ticker, frame in prices_by_ticker.items():
        rows = [
            {
                "date": row.trade_date.isoformat(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "adj_close": float(row.adj_close),
                "volume": float(row.volume),
                "dividends": float(row.dividends),
                "stock_splits": float(row.stock_splits),
            }
            for row in frame.itertuples()
        ]
        payload = {
            "schema_version": "1.0",
            "snapshot_version": snapshot_version,
            "generated_at": generated_at,
            "ticker": ticker,
            "source_url": frame.iloc[0]["source_url"] if not frame.empty else None,
            "evidence_url": frame.iloc[0]["evidence_url"] if not frame.empty else None,
            "rows": rows,
        }
        name = f"prices/{ticker}.json"
        write_json(web_data_dir / name, payload)
        files.append(name)
    return files
