"""Quality report generation."""

from __future__ import annotations

from typing import Any

from pipeline.config import Settings
from pipeline.preprocess.calendar import CalendarQuarter
from pipeline.util import to_million

CORE_METRICS = ["revenue", "operating_income", "net_income", "rd_expense", "capex", "cfo"]
BRIDGE_METRICS = (
    "operating_income",
    "nonoperating_income",
    "pretax_income",
    "income_tax_expense",
    "net_income",
    "unrealized_equity_gains",
)


def _pick_quarter_fact(
    facts: list[dict[str, Any]], *, ticker: str, metric: str, calendar_key: str
) -> dict[str, Any] | None:
    candidates = [
        fact
        for fact in facts
        if fact.get("ticker") == ticker
        and fact.get("metric") == metric
        and fact.get("calendar_key") == calendar_key
        and fact.get("period_type") == "quarter"
        and fact.get("is_original")
        and fact.get("verified") is True
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda fact: (fact.get("filed_date", ""), fact.get("accession_number", "")),
    )[0]


def _bridge_value(
    facts: list[dict[str, Any]], *, ticker: str, metric: str, calendar_key: str
) -> dict[str, Any] | None:
    fact = _pick_quarter_fact(facts, ticker=ticker, metric=metric, calendar_key=calendar_key)
    if fact is None:
        return None
    return {
        "value_musd": to_million(fact.get("value_usd")),
        "fact_id": fact.get("fact_id"),
        "source_url": fact.get("source_url"),
        "evidence_url": fact.get("evidence_url"),
        "accession_number": fact.get("accession_number"),
        "xbrl_tag": fact.get("xbrl_tag"),
        "response_sha256": fact.get("response_sha256"),
    }


def build_net_income_bridge(
    *,
    facts: list[dict[str, Any]],
    expected_keys: list[str],
    settings: Settings,
) -> dict[str, Any]:
    """Bridge reported net income to operating income for every ticker with
    diagnostic XBRL tags. Nothing is inferred: a missing fact stays missing."""
    threshold = float(
        settings.thresholds.get("quality", {}).get("nonoperating_share_threshold", 0.10)
    )
    companies: list[dict[str, Any]] = []
    for ticker in sorted({fact.get("ticker") for fact in facts if fact.get("ticker")}):
        diagnostics = settings.concept_map.get("diagnostic_tags", {}).get(ticker, {})
        if "nonoperating_income" not in diagnostics:
            continue
        quarters: list[dict[str, Any]] = []
        for key in expected_keys:
            values = {
                metric: _bridge_value(facts, ticker=ticker, metric=metric, calendar_key=key)
                for metric in BRIDGE_METRICS
            }
            if not any(values.values()):
                continue
            operating = values.get("operating_income") or {}
            nonoperating = values.get("nonoperating_income") or {}
            pretax = values.get("pretax_income") or {}
            operating_value = operating.get("value_musd")
            nonoperating_value = nonoperating.get("value_musd")
            pretax_value = pretax.get("value_musd")
            share = (
                nonoperating_value / pretax_value
                if nonoperating_value is not None
                and pretax_value not in (None, 0)
                else None
            )
            quarters.append(
                {
                    "calendar_key": key,
                    "operating_income_musd": operating_value,
                    "nonoperating_income_musd": nonoperating_value,
                    "pretax_income_musd": pretax_value,
                    "income_tax_expense_musd": (values.get("income_tax_expense") or {}).get("value_musd"),
                    "net_income_musd": (values.get("net_income") or {}).get("value_musd"),
                    "unrealized_equity_gains_musd": (values.get("unrealized_equity_gains") or {}).get("value_musd"),
                    "nonoperating_share_of_pretax": share,
                    "one_off_flag": bool(share is not None and abs(share) >= threshold),
                    "evidence": {
                        name: value
                        for name, value in values.items()
                        if value
                    },
                }
            )
        companies.append(
            {
                "ticker": ticker,
                "threshold": threshold,
                "quarters": quarters,
                "note": (
                    "Non-operating income includes gains/losses on equity investments. "
                    "A quarter is flagged when its absolute non-operating income is at least "
                    f"{threshold:.0%} of pre-tax income; all values are SEC XBRL facts."
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "definition": (
            "Net income = operating income + non-operating income - income tax expense "
            "(plus/minus other items reported by the company). The bridge is built only from "
            "reported SEC facts."
        ),
        "companies": companies,
    }


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
    excluded_quarters: list[dict[str, Any]] = []
    derived_quarters: list[dict[str, Any]] = []
    total_present = 0
    total_missing = 0
    total_low = 0
    total_verified = 0
    total_metrics = 0
    quality_mode = settings.thresholds.get("quality", {}).get("stats_quality_mode", "exclude_low")

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
            bad_metrics: list[dict[str, Any]] = []
            derived_metrics: list[dict[str, Any]] = []
            for metric_name, metric in row["metrics"].items():
                total_metrics += 1
                if metric.quality_flag == "missing":
                    total_missing += 1
                elif metric.quality_flag == "low":
                    total_low += 1
                if metric.verified:
                    total_verified += 1
                metrics_report[metric_name] = metric.to_dict()
                if metric.value is not None and metric.quality_flag != "ok":
                    bad_metrics.append(
                        {
                            "metric": metric_name,
                            "quality_flag": metric.quality_flag,
                            "reason": metric.reason,
                        }
                    )
                if metric.derived and metric.value is not None:
                    value = to_million(metric.value) if metric.unit == "USD" else metric.value
                    roles = {
                        component.get("role"): component.get("value")
                        for component in metric.components
                        if component.get("value") is not None
                    }
                    identity_residual = None
                    method = metric.derivation_method or ""
                    if method.startswith("YTD") and roles.get("ytd") is not None:
                        others = sum(
                            component_value
                            for role, component_value in roles.items()
                            if role != "ytd"
                        )
                        identity_residual = abs(roles["ytd"] - (others + value))
                    elif method.startswith("FY") and roles.get("annual") is not None:
                        others = sum(
                            component_value
                            for role, component_value in roles.items()
                            if role != "annual"
                        )
                        identity_residual = abs(roles["annual"] - (others + value))
                    derived_metrics.append(
                        {
                            "metric": metric_name,
                            "value_musd": value,
                            "derivation_method": metric.derivation_method,
                            "quality_flag": metric.quality_flag,
                            "identity_residual_musd": identity_residual,
                            "identity_ok": (
                                None
                                if identity_residual is None
                                else identity_residual <= 0.01
                            ),
                            "components": metric.components,
                        }
                    )
            if bad_metrics:
                excluded_quarters.append(
                    {
                        "ticker": ticker,
                        "calendar_key": key,
                        "period_end": row["period_end"],
                        "metrics": bad_metrics,
                    }
                )
            if derived_metrics:
                derived_quarters.append(
                    {
                        "ticker": ticker,
                        "calendar_key": key,
                        "fiscal_year": row["fiscal_year"],
                        "fiscal_quarter": row["fiscal_quarter"],
                        "period_end": row["period_end"],
                        "metrics": derived_metrics,
                    }
                )
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
            "segment_name": row["segment_name"],
            "comparable": row["comparable"],
            "derived": row.get("derived", False),
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

    bridge = build_net_income_bridge(
        facts=facts,
        expected_keys=expected_keys,
        settings=settings,
    )

    return {
        "schema_version": "1.0",
        "snapshot_version": snapshot_version,
        "quality_mode": quality_mode,
        "summary": {
            "companies": list(rows_by_ticker.keys()),
            "quarters_expected_per_company": len(expected_keys),
            "quarters_expected_total": len(expected_keys) * len(rows_by_ticker),
            "quarters_present": total_present,
            "missing_metric_cells": total_missing,
            "low_metric_cells": total_low,
            "excluded_quarters": len(excluded_quarters),
            "verified_ratio": round(total_verified / total_metrics, 6) if total_metrics else 0.0,
        },
        "companies": companies,
        # Every quarter with a non-ok metric, independent of the stats mode.
        "excluded_quarters": excluded_quarters,
        "derived_quarters": derived_quarters,
        "net_income_bridge": bridge,
        "tag_switch": switches,
        "segment_break": segment_breaks,
        "restatements": restatements,
        "notes": [
            "n is small: 19 calendar quarters; lag analyses have 11-15 observations before quality filtering.",
            "Derived Q4 values and YTD differences are marked quality_flag=low and listed in derived_quarters with their components.",
            "Mode A (exclude_low) removes non-ok quarters from hypothesis tests and lists them in tests.json excluded_quarters; mode B keeps them with labels.",
            "The net-income bridge uses only reported SEC facts; non-operating equity gains are not treated as operating performance.",
            "No AI event is included unless it has been reviewed and verified.",
        ],
    }
