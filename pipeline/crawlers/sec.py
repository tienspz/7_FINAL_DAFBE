"""SEC EDGAR crawlers."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from pipeline.config import Settings
from pipeline.http import CachedHttpClient
from pipeline.util import (
    clean_member,
    duration_days,
    fiscal_info,
    normalize_accession,
    parse_date,
    quarter_key,
    safe_float,
    sha256_json,
)

CIKS = {
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
}
ALLOWED_FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}
SEGMENT_AXIS = "StatementBusinessSegmentsAxis"
SEGMENT_REVENUE_TAGS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
}
SEGMENT_OPERATING_INCOME_TAGS = {"OperatingIncomeLoss"}


def filing_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{normalize_accession(accession)}/"


def concept_url(cik: str, tag: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"


def companyfacts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


@dataclass
class Filing:
    ticker: str
    cik: str
    accession_number: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str
    source_url: str

    @property
    def accession_nodash(self) -> str:
        return normalize_accession(self.accession_number)


@dataclass
class RawFact:
    run_id: str
    fact_id: str
    cik: str
    ticker: str
    taxonomy: str
    xbrl_tag: str
    unit: str
    period_start: str
    period_end: str
    value_raw: float
    value_usd: float
    form: str
    fiscal_year: int
    fiscal_period: str
    filed_date: str
    accession_number: str
    frame: str
    source_url: str
    evidence_url: str
    http_status: int
    fetched_at: str
    response_sha256: str
    parser_version: str
    metric: str
    component: str
    duration_days: int | None
    period_type: str
    calendar_key: str
    is_original: bool = False
    is_restated: bool = False
    is_duplicate: bool = False
    verified: bool = False
    verification_reason: str = "not verified"
    restatement_of_fact_id: str = ""
    restatement_delta: float | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "fact_id": self.fact_id,
            "cik": self.cik,
            "ticker": self.ticker,
            "taxonomy": self.taxonomy,
            "xbrl_tag": self.xbrl_tag,
            "unit": self.unit,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "value_raw": self.value_raw,
            "value_usd": self.value_usd,
            "form": self.form,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "filed_date": self.filed_date,
            "accession_number": self.accession_number,
            "frame": self.frame,
            "source_url": self.source_url,
            "evidence_url": self.evidence_url,
            "http_status": self.http_status,
            "fetched_at": self.fetched_at,
            "response_sha256": self.response_sha256,
            "parser_version": self.parser_version,
            "metric": self.metric,
            "component": self.component,
            "duration_days": self.duration_days,
            "period_type": self.period_type,
            "calendar_key": self.calendar_key,
            "is_original": self.is_original,
            "is_restated": self.is_restated,
            "is_duplicate": self.is_duplicate,
            "verified": self.verified,
            "verification_reason": self.verification_reason,
            "restatement_of_fact_id": self.restatement_of_fact_id,
            "restatement_delta": self.restatement_delta,
        }


@dataclass
class SegmentFact:
    run_id: str
    cik: str
    ticker: str
    accession_number: str
    period_start: str
    period_end: str
    segment_scheme: str
    segment_name: str
    segment_member: str
    metric: str
    value_usd: float
    dimensions_json: str
    source_url: str
    evidence_url: str
    fetched_at: str
    response_sha256: str
    parser_version: str
    form: str = ""
    filed_date: str = ""
    fiscal_year: int = 0
    fiscal_period: str = ""
    calendar_key: str = ""
    period_type: str = ""
    derived: bool = False
    comparable: bool = True

    def as_row(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cik": self.cik,
            "ticker": self.ticker,
            "accession_number": self.accession_number,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "segment_scheme": self.segment_scheme,
            "segment_name": self.segment_name,
            "segment_member": self.segment_member,
            "metric": self.metric,
            "value_usd": self.value_usd,
            "dimensions_json": self.dimensions_json,
            "source_url": self.source_url,
            "evidence_url": self.evidence_url,
            "fetched_at": self.fetched_at,
            "response_sha256": self.response_sha256,
            "parser_version": self.parser_version,
            "form": self.form,
            "filed_date": self.filed_date,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "calendar_key": self.calendar_key,
            "period_type": self.period_type,
            "derived": self.derived,
            "comparable": self.comparable,
        }


def _recent_block(payload: dict[str, Any]) -> dict[str, Any]:
    filings = payload.get("filings", {})
    if "recent" in filings:
        return filings["recent"]
    if "accessionNumber" in filings:
        return filings
    if "accessionNumber" in payload:
        return payload
    return {}


def recent_filings(submissions: dict[str, Any], ticker: str, since: str = "2021-01-01") -> list[Filing]:
    cik = CIKS[ticker]
    recent = _recent_block(submissions)
    keys = ["accessionNumber", "form", "filingDate", "reportDate", "primaryDocument"]
    columns = [recent.get(key, []) for key in keys]
    length = max((len(column) for column in columns), default=0)
    out: list[Filing] = []
    for index in range(length):
        accession = columns[0][index] if index < len(columns[0]) else ""
        form = columns[1][index] if index < len(columns[1]) else ""
        filing_date = columns[2][index] if index < len(columns[2]) else ""
        report_date = columns[3][index] if index < len(columns[3]) else ""
        primary_document = columns[4][index] if index < len(columns[4]) else ""
        if form not in ALLOWED_FORMS:
            continue
        if filing_date < since:
            continue
        out.append(
            Filing(
                ticker=ticker,
                cik=cik,
                accession_number=accession,
                form=form,
                filing_date=filing_date,
                report_date=report_date,
                primary_document=primary_document,
                source_url=filing_url(cik, accession),
            )
        )
    return out


def collect_filings(
    *,
    client: CachedHttpClient,
    submissions: dict[str, Any],
    ticker: str,
    since: str = "2021-01-01",
) -> list[Filing]:
    """Merge the recent block with older submissions archive files."""
    out = recent_filings(submissions, ticker, since)
    for file_info in submissions.get("filings", {}).get("files", []):
        if file_info.get("filingTo", "") < since:
            continue
        url = f"https://data.sec.gov/submissions/{file_info['name']}"
        payload = client.get_json(url)
        out.extend(recent_filings(payload, ticker, since))
    deduped: dict[str, Filing] = {filing.accession_number: filing for filing in out}
    return sorted(deduped.values(), key=lambda filing: (filing.report_date, filing.filing_date))


def _period_type(duration: int | None) -> str:
    if duration is None:
        return "instant"
    if 60 <= duration <= 105:
        return "quarter"
    if 150 <= duration <= 290:
        return "ytd"
    if 330 <= duration <= 380:
        return "annual"
    return "other"


def extract_facts(
    *,
    ticker: str,
    companyfacts: dict[str, Any],
    settings: Settings,
    run_id: str,
    http_status: int,
    fetched_at: str,
    response_sha256: str,
    parser_version: str = "1.0.0",
) -> list[RawFact]:
    cik = CIKS[ticker]
    metrics = dict(settings.companies[ticker])
    # Diagnostic tags stay out of the dashboard metric contract but are
    # extracted for the net-income bridge and other evidence checks.
    metrics.update(settings.concept_map.get("diagnostic_tags", {}).get(ticker, {}))
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    out: list[RawFact] = []
    seen: set[tuple[Any, ...]] = set()

    for metric, definition in metrics.items():
        unit = definition["unit"]
        tag_specs = list(definition.get("tags", [])) + list(definition.get("fallback_tags", []))
        for tag_spec in tag_specs:
            tag = tag_spec["tag"] if isinstance(tag_spec, dict) else str(tag_spec)
            if tag not in gaap:
                continue
            units = gaap[tag].get("units", {})
            if unit not in units:
                continue
            for row in units[unit]:
                form = row.get("form", "")
                if form not in ALLOWED_FORMS:
                    continue
                start = parse_date(row.get("start"))
                end = parse_date(row.get("end"))
                if end is None:
                    continue
                value = safe_float(row.get("val"))
                if value is None:
                    continue

                # Period-aware tag validity for switches such as GOOGL revenue.
                if isinstance(tag_spec, dict):
                    valid_from = parse_date(tag_spec.get("valid_from"))
                    valid_to = parse_date(tag_spec.get("valid_to"))
                    if valid_from and end < valid_from:
                        continue
                    if valid_to and end > valid_to:
                        continue

                duration = duration_days(start, end)
                ptype = _period_type(duration)
                if ptype == "other":
                    continue
                fy, fq = fiscal_info(ticker, end)
                accession = row.get("accn", "")
                key = (tag, unit, row.get("start"), row.get("end"), accession, value)
                if key in seen:
                    continue
                seen.add(key)
                fact_id = sha256_json(list(key))[:32]
                component = tag if definition.get("aggregation") == "sum" else metric
                out.append(
                    RawFact(
                        run_id=run_id,
                        fact_id=fact_id,
                        cik=cik,
                        ticker=ticker,
                        taxonomy="us-gaap",
                        xbrl_tag=tag,
                        unit=unit,
                        period_start=row.get("start", "") or "",
                        period_end=row.get("end", "") or "",
                        value_raw=value,
                        value_usd=value,
                        form=form,
                        fiscal_year=fy,
                        fiscal_period=fq,
                        filed_date=row.get("filed", "") or "",
                        accession_number=accession,
                        frame=row.get("frame", "") or "",
                        source_url=filing_url(cik, accession),
                        evidence_url=concept_url(cik, tag),
                        http_status=http_status,
                        fetched_at=fetched_at,
                        response_sha256=response_sha256,
                        parser_version=parser_version,
                        metric=metric,
                        component=component,
                        duration_days=duration,
                        period_type=ptype,
                        calendar_key=quarter_key(end),
                    )
                )
    return out


def mark_originals(
    facts: Iterable[RawFact],
    *,
    min_usd: float = 1_000_000,
    min_eps: float = 0.01,
) -> list[RawFact]:
    """Mark the first filed fact for each period as original.

    Later facts with a material value difference are restatements; identical
    values are duplicates. Grouping includes the tag so a tag switch does not
    create a false restatement.
    """
    ordered = sorted(facts, key=lambda item: (item.filed_date, item.accession_number, item.fact_id))
    groups: dict[tuple[str, str, str, str, str], list[RawFact]] = {}
    for fact in ordered:
        key = (fact.cik, fact.xbrl_tag, fact.unit, fact.period_start, fact.period_end)
        groups.setdefault(key, []).append(fact)

    for group in groups.values():
        original = group[0]
        original.is_original = True
        threshold = min_eps if original.unit == "USD/shares" else min_usd
        for candidate in group[1:]:
            delta = candidate.value_usd - original.value_usd
            candidate.restatement_delta = delta
            if abs(delta) > threshold:
                candidate.is_restated = True
                candidate.restatement_of_fact_id = original.fact_id
            else:
                candidate.is_duplicate = True
    return ordered


def find_instance_file(index_json: dict[str, Any]) -> str:
    items = index_json.get("directory", {}).get("item", [])
    names = [item.get("name", "") for item in items if item.get("name")]
    for name in names:
        if name.endswith("_htm.xml"):
            return name
    for name in names:
        if name.endswith(".xml") and not name.endswith(("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            return name
    raise ValueError("No XBRL instance XML found in filing index")


def parse_segment_instance(
    *,
    xml_bytes: bytes,
    ticker: str,
    accession: str,
    form: str,
    filing_date: str,
    report_date: str,
    settings: Settings,
    run_id: str,
    source_url: str,
    evidence_url: str,
    fetched_at: str,
    response_sha256: str,
    parser_version: str = "1.0.0",
) -> list[SegmentFact]:
    cik = CIKS[ticker]
    root = ET.fromstring(xml_bytes)
    contexts: dict[str, tuple[str | None, str | None, dict[str, str]]] = {}
    for element in root.iter():
        if not element.tag.endswith("}context"):
            continue
        context_id = element.attrib.get("id", "")
        start: str | None = None
        end: str | None = None
        dimensions: dict[str, str] = {}
        for child in element.iter():
            if child.tag.endswith("}startDate"):
                start = (child.text or "").strip()
            elif child.tag.endswith("}endDate"):
                end = (child.text or "").strip()
            elif child.tag.endswith("}instant"):
                end = (child.text or "").strip()
            elif child.tag.endswith("}explicitMember"):
                dimension = child.attrib.get("dimension", "")
                dimensions[dimension] = (child.text or "").strip()
        contexts[context_id] = (start, end, dimensions)

    # Only consolidated segment contexts: exactly one dimension, the segment axis.
    segment_contexts: dict[str, tuple[str | None, str | None, dict[str, str]]] = {}
    for context_id, (start, end, dimensions) in contexts.items():
        if len(dimensions) != 1:
            continue
        only_dimension = next(iter(dimensions))
        if only_dimension.endswith(SEGMENT_AXIS):
            segment_contexts[context_id] = (start, end, dimensions)

    schemes = settings.segment_map["companies"].get(ticker, {}).get("schemes", {})
    fact_rows: list[SegmentFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    for element in root.iter():
        context_ref = element.attrib.get("contextRef")
        if context_ref not in segment_contexts:
            continue
        text = (element.text or "").strip()
        if not text:
            continue
        local_name = element.tag.split("}")[-1]
        if local_name in SEGMENT_REVENUE_TAGS:
            metric = "revenue"
        elif local_name in SEGMENT_OPERATING_INCOME_TAGS:
            metric = "operating_income"
        else:
            continue
        value = safe_float(text)
        if value is None:
            continue
        start, end, dimensions = segment_contexts[context_ref]
        if end is None:
            continue
        dimension_value = next(iter(dimensions.values()))
        member = clean_member(dimension_value)
        scheme_name = ""
        segment_name = member
        for candidate_scheme, scheme in schemes.items():
            if member in scheme.get("members", {}):
                scheme_name = candidate_scheme
                segment_name = scheme["members"][member]
                break
        if not scheme_name:
            continue
        key = (str(end), member, metric, accession)
        if key in seen:
            continue
        seen.add(key)
        duration = duration_days(parse_date(start), parse_date(end))
        ptype = _period_type(duration)
        fy, fq = fiscal_info(ticker, parse_date(end))
        fact_rows.append(
            SegmentFact(
                run_id=run_id,
                cik=cik,
                ticker=ticker,
                accession_number=accession,
                period_start=start or "",
                period_end=end,
                segment_scheme=scheme_name,
                segment_name=segment_name,
                segment_member=member,
                metric=metric,
                value_usd=value,
                dimensions_json=json.dumps(dimensions, ensure_ascii=False, sort_keys=True),
                source_url=source_url,
                evidence_url=evidence_url,
                fetched_at=fetched_at,
                response_sha256=response_sha256,
                parser_version=parser_version,
                form=form,
                filed_date=filing_date,
                fiscal_year=fy,
                fiscal_period=fq,
                calendar_key=quarter_key(parse_date(end)),
                period_type=ptype,
            )
        )
    return fact_rows


def fetch_segment_facts(
    *,
    client: CachedHttpClient,
    settings: Settings,
    ticker: str,
    filings: list[Filing],
    run_id: str,
    parser_version: str = "1.0.0",
) -> list[SegmentFact]:
    out: list[SegmentFact] = []
    for filing in filings:
        index_url = filing.source_url + "index.json"
        index_response = client.get(index_url)
        index_json = index_response.json()
        instance_name = find_instance_file(index_json)
        instance_url = filing.source_url + instance_name
        instance_response = client.get(instance_url)
        out.extend(
            parse_segment_instance(
                xml_bytes=instance_response.content,
                ticker=ticker,
                accession=filing.accession_number,
                form=filing.form,
                filing_date=filing.filing_date,
                report_date=filing.report_date,
                settings=settings,
                run_id=run_id,
                source_url=filing.source_url,
                evidence_url=instance_url,
                fetched_at=instance_response.fetched_at,
                response_sha256=instance_response.sha256,
                parser_version=parser_version,
            )
        )
    return out
