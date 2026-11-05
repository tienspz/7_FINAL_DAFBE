"""Segment table construction and Q4 derivation."""

from __future__ import annotations

from typing import Any

from pipeline.config import Settings
from pipeline.preprocess.calendar import CalendarQuarter
from pipeline.util import to_million


def _segments_by_key(facts: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        key = (fact["ticker"], fact["segment_scheme"], fact["segment_name"], fact["metric"])
        grouped.setdefault(key, []).append(fact)
    return grouped


def build_segment_table(
    *,
    segment_facts: list[dict[str, Any]],
    quarters: list[CalendarQuarter],
    consolidated_rows: list[dict[str, Any]],
    settings: Settings,
) -> list[dict[str, Any]]:
    grouped = _segments_by_key(segment_facts)
    output: list[dict[str, Any]] = []
    consolidated_by_quarter = {(row["ticker"], row["calendar_key"]): row for row in consolidated_rows}

    for (ticker, scheme, segment_name, metric), facts in grouped.items():
        by_quarter: dict[str, dict[str, Any]] = {}
        for fact in facts:
            if fact.get("period_type") == "quarter":
                by_quarter[fact["calendar_key"]] = fact
        annual_by_quarter = {
            fact["calendar_key"]: fact
            for fact in facts
            if fact.get("period_type") == "annual"
        }
        for quarter in quarters:
            fact = by_quarter.get(quarter.key)
            derived = False
            value = fact.get("value_usd") if fact else None
            source = fact
            if fact is None and quarter.key.endswith("Q4") and quarter.key in annual_by_quarter:
                annual = annual_by_quarter[quarter.key]
                components = [by_quarter.get(f"{quarter.key[:4]}-Q{q}") for q in (1, 2, 3)]
                if all(component is not None for component in components):
                    value = annual["value_usd"] - sum(component["value_usd"] for component in components if component)
                    derived = True
                    source = annual
            if value is None or source is None:
                continue
            output.append(
                {
                    "ticker": ticker,
                    "calendar_key": quarter.key,
                    "period_end": source["period_end"],
                    "segment_scheme": scheme,
                    "segment_name": segment_name,
                    "segment_member": source["segment_member"],
                    "metric": metric,
                    "value_musd": to_million(value),
                    "derived": derived,
                    "comparable": not (ticker == "MSFT" and scheme == "msft_new_2"),
                    "quality_flag": "low" if derived else "ok",
                    "source_url": source["source_url"],
                    "accession_number": source["accession_number"],
                    "form": source.get("form", ""),
                    "filed_date": source.get("filed_date", ""),
                    "evidence_url": source.get("evidence_url", ""),
                }
            )

    # Segment sum check against consolidated revenue / operating income.
    for row in output:
        consolidated = consolidated_by_quarter.get((row["ticker"], row["calendar_key"]))
        if not consolidated:
            continue
        metric_name = "revenue" if row["metric"] == "revenue" else "operating_income"
        consolidated_metric = consolidated["metrics"].get(metric_name)
        if not consolidated_metric or consolidated_metric.value is None:
            continue
        same_group = [
            candidate
            for candidate in output
            if candidate["ticker"] == row["ticker"]
            and candidate["calendar_key"] == row["calendar_key"]
            and candidate["segment_scheme"] == row["segment_scheme"]
            and candidate["metric"] == row["metric"]
        ]
        total = sum(candidate["value_musd"] for candidate in same_group if candidate["value_musd"] is not None)
        consolidated_musd = to_million(consolidated_metric.value)
        if consolidated_musd:
            row["segment_sum_musd"] = round(total, 3)
            row["consolidated_musd"] = consolidated_musd
            row["segment_sum_diff"] = round(abs(total - consolidated_musd) / abs(consolidated_musd), 6)
            if row["segment_sum_diff"] > settings.thresholds["quality"]["segment_sum_tolerance"]:
                row["quality_flag"] = "low"
                row["segment_sum_warning"] = "segment sum differs from consolidated total"
    return output
