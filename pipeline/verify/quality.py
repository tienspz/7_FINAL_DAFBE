"""Quality report generation."""

from __future__ import annotations

from typing import Any

from pipeline.config import Settings
from pipeline.preprocess.calendar import CalendarQuarter


CORE_METRICS = ["revenue", "operating_income", "net_income", "rd_expense", "capex", "cfo"]


def build_quality_report(
    *,
    settings: Settings,
    quarters: list[CalendarQuarter],
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    facts: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    snapshot_version: str,
) -> dict[str, Any]:
    expected_keys = [quarter.key for quarter in quarters]
    companies: list[dict[str, Any]] = []
    total_present = 0
    total_missing = 0
    total_low = 0
    total_verified = 0
    total_metrics = 0

    for ticker, rows in rows_by_ticker.items():
        by_key = {row["calendar_key"]: row for row in rows}
        quarter_reports: list[dict[str, Any]] = []
        for key in expected_keys:
            row = by_key.get(key)
            if not row:
                quarter_reports.append(
                    {
                        "calendar_key": key,
                        "period_end": None,
                        "metrics": {},
                        "missing": True,
                    }
                )
                total_missing += 1
                continue
            total_present += 1
            metrics_report: dict[str, Any] = {}
            for metric_name, metric in row["metrics"].items():
                total_metrics += 1
                if metric.quality_flag == "missing":
                    total_missing += 1
                elif metric.quality_flag == "low":
                    total_low += 1
                if metric.verified:
                    total_verified += 1
                metrics_report[metric_name] = metric.to_dict()
            quarter_reports.append(
                {
                    "calendar_key": key,
                    "period_end": row["period_end"],
                    "fiscal_year": row["fiscal_year"],
                    "fiscal_quarter": row["fiscal_quarter"],
                    "metrics": metrics_report,
                }
            )
        companies.append({"ticker": ticker, "quarters": quarter_reports})

    tag_switch = [
        {
            "ticker": fact["ticker"],
            "calendar_key": fact["calendar_key"],
            "metric": fact["metric"],
            "old_tag": fact["xbrl_tag"],
        }
        for fact in facts
        if fact.get("is_original") and fact.get("metric") == "revenue"
    ]
    # Only keep the transition points where the tag actually changes.
    switches: list[dict[str, Any]] = []
    for ticker in rows_by_ticker:
        prior_tag = None
        for row in sorted(rows_by_ticker[ticker], key=lambda item: item["calendar_key"]):
            metric = row["metrics"].get("revenue")
            if not metric or not metric.xbrl_tag:
                continue
            if prior_tag and metric.xbrl_tag != prior_tag:
                switches.append(
                    {
                        "ticker": ticker,
                        "calendar_key": row["calendar_key"],
                        "old_tag": prior_tag,
                        "new_tag": metric.xbrl_tag,
                    }
                )
            prior_tag = metric.xbrl_tag

    segment_breaks = [
        {
            "ticker": row["ticker"],
            "calendar_key": row["calendar_key"],
            "segment_scheme": row["segment_scheme"],
            "comparable": row["comparable"],
        }
        for row in segment_rows
        if not row.get("comparable", True)
    ]

    restatements = [
        {
            "ticker": fact["ticker"],
            "metric": fact["metric"],
            "tag": fact["xbrl_tag"],
            "period_end": fact["period_end"],
            "accession_number": fact["accession_number"],
            "delta": fact.get("restatement_delta"),
        }
        for fact in facts
        if fact.get("is_restated")
    ]

    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "summary": {
            "companies": list(rows_by_ticker.keys()),
            "quarters_expected_per_company": len(expected_keys),
            "quarters_expected_total": len(expected_keys) * len(rows_by_ticker),
            "quarters_present": total_present,
            "missing_metric_cells": total_missing,
            "low_metric_cells": total_low,
            "verified_ratio": round(total_verified / total_metrics, 6) if total_metrics else 0.0,
        },
        "companies": companies,
        "tag_switch": switches,
        "segment_break": segment_breaks,
        "restatements": restatements,
        "notes": [
            "n is small: 19 calendar quarters; lag analyses have 11-15 observations.",
            "Derived Q4 values and YTD differences are marked quality_flag=low.",
            "No AI event is included unless it has been reviewed and verified.",
        ],
    }
