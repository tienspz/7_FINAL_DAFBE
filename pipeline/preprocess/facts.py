"""Quarterly fact selection, YTD conversion, Q4 derivation, and wide table."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from pipeline.config import Settings
from pipeline.preprocess.calendar import CalendarQuarter
from pipeline.util import fiscal_info, parse_date, quarter_end, quarter_key, safe_float, to_million


@dataclass
class MetricValue:
    value: float | None
    unit: str
    source_url: str | None = None
    accession_number: str | None = None
    xbrl_tag: str | None = None
    form: str | None = None
    filed_date: str | None = None
    period_end: str | None = None
    derived: bool = False
    verified: bool = False
    quality_flag: str = "missing"
    reason: str = ""
    tag_switch: bool = False
    reported_value: float | None = None
    split_adjustment: float | None = None
    components: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": to_million(self.value) if self.unit == "USD" else self.value,
            "unit": "million USD" if self.unit == "USD" else self.unit,
            "source_url": self.source_url,
            "accession_number": self.accession_number,
            "xbrl_tag": self.xbrl_tag,
            "form": self.form,
            "filed_date": self.filed_date,
            "period_end": self.period_end,
            "derived": self.derived,
            "verified": self.verified,
            "quality_flag": self.quality_flag,
            "reason": self.reason,
            "tag_switch": self.tag_switch,
            "reported_value": to_million(self.reported_value) if self.unit == "USD" else self.reported_value,
            "split_adjustment": self.split_adjustment,
            "components": self.components,
        }


def _select_original(subset: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [fact for fact in subset if fact.get("is_original")]


def _sorted_by_filing(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(facts, key=lambda fact: (fact.get("filed_date", ""), fact.get("accession_number", ""), fact.get("fact_id", "")))


def _metric_facts(
    facts: list[dict[str, Any]],
    *,
    ticker: str,
    metric: str,
) -> list[dict[str, Any]]:
    return _select_original(
        fact
        for fact in facts
        if fact.get("ticker") == ticker and fact.get("metric") == metric
    )


def _choose_fact(facts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not facts:
        return None
    return _sorted_by_filing(facts)[0]


def _direct_quarter(facts: list[dict[str, Any]], qkey: str) -> dict[str, Any] | None:
    return _choose_fact([fact for fact in facts if fact.get("period_type") == "quarter" and fact.get("calendar_key") == qkey])


def _ytd_quarter(facts: list[dict[str, Any]], qkey: str) -> dict[str, Any] | None:
    return _choose_fact([fact for fact in facts if fact.get("period_type") == "ytd" and fact.get("calendar_key") == qkey])


def _annual_quarter(facts: list[dict[str, Any]], qkey: str) -> dict[str, Any] | None:
    return _choose_fact([fact for fact in facts if fact.get("period_type") == "annual" and fact.get("calendar_key") == qkey])


def _fact_metadata(fact: dict[str, Any], *, derived: bool, quality: str, reason: str) -> MetricValue:
    return MetricValue(
        value=safe_float(fact.get("value_usd")),
        unit=fact.get("unit", "USD"),
        source_url=fact.get("source_url"),
        accession_number=fact.get("accession_number"),
        xbrl_tag=fact.get("xbrl_tag"),
        form=fact.get("form"),
        filed_date=fact.get("filed_date"),
        period_end=fact.get("period_end"),
        derived=derived,
        verified=bool(fact.get("source_url") and fact.get("accession_number")),
        quality_flag=quality,
        reason=reason,
    )


def _missing(unit: str, reason: str) -> MetricValue:
    return MetricValue(value=None, unit=unit, quality_flag="missing", reason=reason)


def _previous_quarter(qkey: str) -> str:
    year, q = qkey.split("-Q")
    q_num = int(q)
    if q_num == 1:
        return f"{int(year) - 1}-Q4"
    return f"{year}-Q{q_num - 1}"


def _flow_value(
    facts: list[dict[str, Any]],
    *,
    ticker: str,
    metric: str,
    qkey: str,
    memo: dict[str, MetricValue],
    settings: Settings,
    depth: int = 0,
) -> MetricValue:
    if qkey in memo:
        return memo[qkey]
    if depth > 3:
        return _missing("USD", "recursion limit while converting YTD")
    fiscal_quarter = int(fiscal_info(ticker, quarter_end(qkey))[1][1])

    def adjusted(value: MetricValue) -> MetricValue:
        return _apply_split_adjustment(value, ticker=ticker, metric=metric, settings=settings)

    direct = _direct_quarter(facts, qkey)
    if direct is not None:
        memo[qkey] = adjusted(_fact_metadata(direct, derived=False, quality="ok", reason=""))
        return memo[qkey]

    if fiscal_quarter == 1:
        ytd = _ytd_quarter(facts, qkey)
        if ytd is not None:
            memo[qkey] = adjusted(_fact_metadata(ytd, derived=False, quality="ok", reason="Q1 YTD equals the quarter"))
            return memo[qkey]
        memo[qkey] = _missing("USD", "no Q1 fact")
        return memo[qkey]

    if fiscal_quarter in (2, 3):
        ytd = _ytd_quarter(facts, qkey)
        if ytd is None:
            memo[qkey] = _missing("USD", f"no direct or YTD fact for {qkey}")
            return memo[qkey]
        prev1 = _previous_quarter(qkey)
        q1 = _flow_value(facts, ticker=ticker, metric=metric, qkey=prev1, memo=memo, settings=settings, depth=depth + 1)
        if fiscal_quarter == 2:
            if q1.value is None:
                memo[qkey] = _missing("USD", "cannot convert YTD: prior quarter missing")
            else:
                value = safe_float(ytd.get("value_usd")) - q1.value
                memo[qkey] = _fact_metadata(ytd, derived=True, quality="low", reason="YTD Q2 minus Q1")
                memo[qkey].value = value
                memo[qkey] = adjusted(memo[qkey])
            return memo[qkey]
        prev2 = _previous_quarter(prev1)
        q2 = _flow_value(facts, ticker=ticker, metric=metric, qkey=prev2, memo=memo, settings=settings, depth=depth + 1)
        if q1.value is None or q2.value is None:
            memo[qkey] = _missing("USD", "cannot convert YTD: prior quarters missing")
        else:
            value = safe_float(ytd.get("value_usd")) - q1.value - q2.value
            memo[qkey] = _fact_metadata(ytd, derived=True, quality="low", reason="YTD Q3 minus Q1 and Q2")
            memo[qkey].value = value
            memo[qkey] = adjusted(memo[qkey])
        return memo[qkey]

    # Fiscal Q4: annual minus fiscal Q1..Q3.
    annual = _annual_quarter(facts, qkey)
    if annual is None:
        memo[qkey] = _missing("USD", f"no 10-K annual fact for {qkey}")
        return memo[qkey]
    prev1 = _previous_quarter(qkey)  # fiscal Q3
    prev2 = _previous_quarter(prev1)  # fiscal Q2
    prev3 = _previous_quarter(prev2)  # fiscal Q1
    q1 = _flow_value(facts, ticker=ticker, metric=metric, qkey=prev3, memo=memo, settings=settings, depth=depth + 1)
    q2 = _flow_value(facts, ticker=ticker, metric=metric, qkey=prev2, memo=memo, settings=settings, depth=depth + 1)
    q3 = _flow_value(facts, ticker=ticker, metric=metric, qkey=prev1, memo=memo, settings=settings, depth=depth + 1)
    annual_value = safe_float(annual.get("value_usd"))
    if annual_value is None:
        memo[qkey] = _missing("USD", "annual fact has no value")
        return memo[qkey]
    if q1.value is None or q2.value is None or q3.value is None:
        memo[qkey] = _missing("USD", "cannot derive Q4: fiscal Q1-Q3 incomplete")
        return memo[qkey]
    derived_value = annual_value - q1.value - q2.value - q3.value
    residual = abs((q1.value + q2.value + q3.value + derived_value) - annual_value) / abs(annual_value) if annual_value else 0.0
    if residual > 0.02:
        memo[qkey] = _missing("USD", f"Q4 residual {residual:.4%} exceeds 2%")
        return memo[qkey]
    quality = "ok" if residual <= 0.005 else "low"
    memo[qkey] = _fact_metadata(
        annual,
        derived=True,
        quality=quality,
        reason=f"Q4 = FY annual - Q1..Q3 (residual {residual:.4%})",
    )
    memo[qkey].value = derived_value
    memo[qkey] = adjusted(memo[qkey])
    memo[qkey].components = [
        {"fact_id": q1.xbrl_tag, "value": q1.value},
        {"fact_id": q2.xbrl_tag, "value": q2.value},
        {"fact_id": q3.xbrl_tag, "value": q3.value},
    ]
    return memo[qkey]


def _instant_value(
    facts: list[dict[str, Any]],
    *,
    qkey: str,
    quarter_end: date,
) -> MetricValue:
    candidates = [
        fact
        for fact in facts
        if fact.get("period_type") == "instant" and fact.get("calendar_key") == qkey
    ]
    if not candidates:
        return _missing("USD", f"no balance-sheet fact for {qkey}")
    candidates = sorted(
        candidates,
        key=lambda fact: (
            abs((parse_date(fact.get("period_end")) - quarter_end).days) if parse_date(fact.get("period_end")) else 999,
            fact.get("filed_date", ""),
            fact.get("accession_number", ""),
        ),
    )
    return _fact_metadata(candidates[0], derived=False, quality="ok", reason="")


def _sum_values(values: list[MetricValue], *, unit: str = "USD") -> MetricValue | None:
    if not values or any(value.value is None for value in values):
        return None
    total = sum(value.value for value in values if value.value is not None)
    first = values[0]
    return MetricValue(
        value=total,
        unit=unit,
        source_url=first.source_url,
        accession_number=first.accession_number,
        xbrl_tag="+".join(filter(None, [value.xbrl_tag for value in values])),
        form=first.form,
        filed_date=first.filed_date,
        period_end=first.period_end,
        derived=any(value.derived for value in values),
        verified=all(value.verified for value in values),
        quality_flag="low" if any(value.quality_flag == "low" for value in values) else "ok",
        reason="sum of components",
        components=[value.to_dict() for value in values],
    )


def _apply_split_adjustment(
    metric_value: MetricValue,
    *,
    ticker: str,
    metric: str,
    settings: Settings,
) -> MetricValue:
    """Restate a per-share metric onto the current share basis.

    The rule lives in ``concept_map.split_adjustments`` and only applies when
    the fact's period end is strictly before ``adjust_period_end_before``.
    ``reported_value`` keeps the as-filed number so traceability is preserved.
    """
    rule = (
        settings.concept_map.get("split_adjustments", {})
        .get(ticker, {})
        .get(metric)
    )
    if not rule or metric_value.value is None or metric_value.split_adjustment is not None:
        return metric_value
    cutoff = parse_date(rule.get("adjust_period_end_before"))
    period_end = parse_date(metric_value.period_end)
    ratio = safe_float(rule.get("ratio"))
    if cutoff is None or period_end is None or ratio is None or ratio <= 0:
        return metric_value
    if period_end >= cutoff:
        return metric_value
    metric_value.reported_value = metric_value.value
    metric_value.value = metric_value.value / ratio
    metric_value.split_adjustment = ratio
    metric_value.quality_flag = "low"
    note = f"split-adjusted {ratio:g}:1 from reported {metric_value.reported_value:.4g}"
    metric_value.reason = (metric_value.reason + "; " if metric_value.reason else "") + note
    return metric_value


def build_company_quarters(
    *,
    ticker: str,
    facts: list[dict[str, Any]],
    settings: Settings,
    quarters: list[CalendarQuarter],
) -> list[dict[str, Any]]:
    definitions = settings.companies[ticker]
    out: list[dict[str, Any]] = []
    for quarter in quarters:
        metrics: dict[str, MetricValue] = {}
        for metric, definition in definitions.items():
            metric_facts = _metric_facts(facts, ticker=ticker, metric=metric)
            if definition.get("kind") == "instant":
                if definition.get("aggregation") == "sum":
                    component_values: list[MetricValue] = []
                    for tag_spec in definition.get("tags", []):
                        tag = tag_spec["tag"] if isinstance(tag_spec, dict) else str(tag_spec)
                        component_facts = [fact for fact in metric_facts if fact.get("xbrl_tag") == tag]
                        component_values.append(_instant_value(component_facts, qkey=quarter.key, quarter_end=quarter.end))
                    summed = _sum_values(component_values)
                    if summed is None:
                        fallback = definition.get("fallback_tags", [])
                        fallback_value: MetricValue | None = None
                        for tag_spec in fallback:
                            tag = tag_spec["tag"] if isinstance(tag_spec, dict) else str(tag_spec)
                            fallback_facts = [fact for fact in metric_facts if fact.get("xbrl_tag") == tag]
                            candidate = _instant_value(fallback_facts, qkey=quarter.key, quarter_end=quarter.end)
                            if candidate.value is not None:
                                candidate.quality_flag = "low"
                                candidate.reason = "fallback total-debt tag used"
                                fallback_value = candidate
                                break
                        metrics[metric] = fallback_value or _missing(definition["unit"], "total-debt components missing")
                    else:
                        metrics[metric] = summed
                else:
                    metrics[metric] = _instant_value(metric_facts, qkey=quarter.key, quarter_end=quarter.end)
            else:
                memo: dict[str, MetricValue] = {}
                value = _flow_value(
                    metric_facts,
                    ticker=ticker,
                    metric=metric,
                    qkey=quarter.key,
                    memo=memo,
                    settings=settings,
                )
                if value.quality_flag == "missing":
                    metrics[metric] = _missing(definition["unit"], value.reason)
                else:
                    metrics[metric] = value

        # Restate per-share metrics reported before a stock split.
        for metric_name, metric_value in metrics.items():
            metrics[metric_name] = _apply_split_adjustment(
                metric_value,
                ticker=ticker,
                metric=metric_name,
                settings=settings,
            )

        # Record the first quarter where a metric's tag changes from the prior quarter.
        for metric, value in metrics.items():
            prior_key = _previous_quarter(quarter.key)
            if not out:
                continue
            prior = next((row for row in out if row["calendar_key"] == prior_key), None)
            if not prior:
                continue
            prior_value = prior["metrics"].get(metric)
            if (
                prior_value
                and value.xbrl_tag
                and prior_value.xbrl_tag
                and value.xbrl_tag != prior_value.xbrl_tag
                and value.value is not None
            ):
                value.tag_switch = True
                if value.quality_flag == "ok":
                    value.quality_flag = "low"
                    value.reason = (value.reason + "; " if value.reason else "") + "XBRL tag switch"

        actual_end = next((value.period_end for value in metrics.values() if value.period_end), quarter.end.isoformat())
        from pipeline.preprocess.calendar import fiscal_fields

        fiscal = fiscal_fields(ticker, parse_date(actual_end))
        out.append(
            {
                "ticker": ticker,
                "calendar_key": quarter.key,
                "period_end": actual_end,
                "fiscal_year": fiscal["fiscal_year"],
                "fiscal_quarter": fiscal["fiscal_quarter"],
                "period_end_offset_days": fiscal["period_end_offset_days"],
                "metrics": metrics,
            }
        )
    return out
