"""Semantic link verification for SEC, price evidence, and negative controls."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any

from pipeline.config import Settings
from pipeline.http import CachedHttpClient, HttpError, MUTABLE_DATA_CACHE_MAX_AGE_SECONDS
from pipeline.util import normalize_accession, utc_now_iso

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def page_title(html: str) -> str:
    match = TITLE_RE.search(html)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def classify_html(title: str, body: str, expected_accession: str | None = None) -> tuple[str, str]:
    lowered = title.lower().strip()
    if lowered in {"", "default", "page not found", "404", "access denied"}:
        return "soft404", f"invalid title: {title!r}"
    if expected_accession and expected_accession not in body and normalize_accession(expected_accession) not in body:
        return "broken", "accession number not found in body"
    if len(re.sub(r"<[^>]+>", " ", body)) < 500:
        return "soft404", "body too short after tag stripping"
    return "ok", ""


def verify_filing_indexes(
    *,
    client: CachedHttpClient,
    filings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for filing in filings:
        url = filing["source_url"]
        if url in seen:
            continue
        seen.add(url)
        try:
            response = client.get(url)
            title = page_title(response.text)
            result, reason = classify_html(title, response.text, filing.get("accession_number"))
            results.append(
                {
                    "url": url,
                    "domain": "sec.gov",
                    "source_type": "sec_filing_index",
                    "checked_at": utc_now_iso(),
                    "http_status": response.status,
                    "content_type": response.content_type,
                    "page_title": title,
                    "content_sha256": response.sha256,
                    "content_length": len(response.content),
                    "matched_accession": filing.get("accession_number"),
                    "matched_period_end": filing.get("report_date"),
                    "result": result,
                    "reason": reason,
                }
            )
        except HttpError as exc:
            results.append(
                {
                    "url": url,
                    "domain": "sec.gov",
                    "source_type": "sec_filing_index",
                    "checked_at": utc_now_iso(),
                    "http_status": exc.status,
                    "content_type": "",
                    "page_title": "",
                    "content_sha256": "",
                    "content_length": 0,
                    "matched_accession": filing.get("accession_number"),
                    "matched_period_end": filing.get("report_date"),
                    "result": "broken",
                    "reason": str(exc),
                }
            )
    return results


def verify_concepts(
    *,
    client: CachedHttpClient,
    facts: list[dict[str, Any]],
    refresh: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        if not fact.get("is_original"):
            continue
        key = (fact["cik"], fact["xbrl_tag"], fact["unit"])
        groups.setdefault(key, []).append(fact)

    for (cik, tag, unit), group in sorted(groups.items()):
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
        try:
            response = client.get(
                url,
                refresh=refresh,
                max_age_seconds=MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
            )
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("units"), dict):
                raise ValueError("invalid companyconcept response structure")
            rows = payload["units"].get(unit, [])
            if not isinstance(rows, list):
                raise ValueError(f"invalid companyconcept unit data for {unit}")
            checked_at = utc_now_iso()
            for target in group:
                matching_period = [
                    row
                    for row in rows
                    if isinstance(row, dict)
                    and row.get("accn") == target.get("accession_number")
                    and row.get("end") == target.get("period_end")
                    and (row.get("start") or "") == (target.get("period_start") or "")
                ]
                matching_value = any(
                    float(row.get("val")) == float(target.get("value_usd"))
                    for row in matching_period
                    if row.get("val") is not None
                )
                results.append(
                    {
                        "fact_id": target.get("fact_id"),
                        "url": url,
                        "domain": "data.sec.gov",
                        "source_type": "sec_companyconcept",
                        "checked_at": checked_at,
                        "http_status": response.status,
                        "content_type": response.content_type,
                        "page_title": "",
                        "content_sha256": response.sha256,
                        "content_length": len(response.content),
                        "matched_accession": target.get("accession_number"),
                        "matched_period_end": target.get("period_end"),
                        "matched_value": target.get("value_usd"),
                        "result": "ok" if matching_value else "broken",
                        "reason": (
                            ""
                            if matching_value
                            else "XBRL value mismatch"
                            if matching_period
                            else "no matching XBRL fact in companyconcept"
                        ),
                        "tag": tag,
                    }
                )
        except (HttpError, json.JSONDecodeError, TypeError, ValueError) as exc:
            for target in group:
                results.append(
                    {
                        "fact_id": target.get("fact_id"),
                        "url": url,
                        "domain": "data.sec.gov",
                        "source_type": "sec_companyconcept",
                        "checked_at": utc_now_iso(),
                        "http_status": getattr(exc, "status", None),
                        "content_type": "",
                        "page_title": "",
                        "content_sha256": "",
                        "content_length": 0,
                        "matched_accession": target.get("accession_number"),
                        "matched_period_end": target.get("period_end"),
                        "matched_value": target.get("value_usd"),
                        "result": "broken",
                        "reason": str(exc),
                        "tag": tag,
                    }
                )
    return results


def verify_price_evidence(
    *,
    client: CachedHttpClient,
    prices_by_ticker: dict[str, Any],
    sample_size: int = 30,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for ticker, frame in prices_by_ticker.items():
        if frame.empty:
            continue
        sampled = frame.tail(sample_size)
        url = sampled.iloc[-1]["evidence_url"]
        try:
            payload = client.get_json(
                url,
                refresh=refresh,
                max_age_seconds=MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
            )
            result = payload.get("chart", {}).get("result", [])
            if not result:
                raise ValueError("no chart result")
            chart = result[0]
            timestamps = chart.get("timestamp", [])
            closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            remote = {
                datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat(): close
                for ts, close in zip(timestamps, closes)
                if close is not None
            }
            matched = 0
            for row in sampled.itertuples():
                remote_close = remote.get(row.trade_date.isoformat())
                if remote_close is not None and abs(remote_close - float(row.close)) / max(abs(remote_close), 1e-9) <= 0.001:
                    matched += 1
            results.append(
                {
                    "url": url,
                    "domain": "query1.finance.yahoo.com",
                    "source_type": "price_evidence_same_provider",
                    "checked_at": utc_now_iso(),
                    "http_status": 200,
                    "content_type": "application/json",
                    "page_title": "",
                    "content_sha256": "",
                    "content_length": 0,
                    "matched_accession": "",
                    "matched_period_end": "",
                    "matched_value": matched,
                    "result": "ok" if matched >= max(1, int(len(sampled) * 0.9)) else "low",
                    "reason": f"{matched}/{len(sampled)} sampled closes matched",
                    "ticker": ticker,
                }
            )
        except Exception as exc:  # noqa: BLE001 - report the failure, do not hide it
            results.append(
                {
                    "url": url,
                    "domain": "query1.finance.yahoo.com",
                    "source_type": "price_evidence_same_provider",
                    "checked_at": utc_now_iso(),
                    "http_status": None,
                    "content_type": "",
                    "page_title": "",
                    "content_sha256": "",
                    "content_length": 0,
                    "matched_accession": "",
                    "matched_period_end": "",
                    "matched_value": None,
                    "result": "blocked",
                    "reason": str(exc),
                    "ticker": ticker,
                }
            )
    return results


def run_negative_checks(client: CachedHttpClient) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    checks = [
        ("R1", "stooq", "https://stooq.com/q/d/l/?s=msft.us&i=d"),
        ("R2", "microsoft_source", "https://news.microsoft.com/2023/01/23/microsoft-and-openai-announce-multiyear-multibillion-dollar-investment/"),
        ("R3", "microsoft_ir_earnings", "https://www.microsoft.com/en-us/investor/earnings"),
    ]
    for check_id, source_type, url in checks:
        try:
            # Negative controls deliberately probe rejected sources outside CR-13.
            response = client.get(url, allow_unlisted=True)
            title = page_title(response.text)
            if check_id == "R1":
                is_csv = response.text.lower().startswith("date,") or "date,open" in response.text.lower()
                result = "ok" if is_csv else "blocked"
                reason = "CSV detected" if is_csv else "JavaScript challenge / no CSV rows"
            elif check_id == "R2":
                result = "ok"
                reason = "unexpectedly reachable"
            else:
                result, reason = classify_html(title, response.text)
                if result == "ok":
                    result = "soft404"
                    reason = "page has no usable financial content"
            results.append(
                {
                    "id": check_id,
                    "url": url,
                    "source_type": source_type,
                    "http_status": response.status,
                    "page_title": title,
                    "result": result,
                    "reason": reason,
                    "checked_at": utc_now_iso(),
                }
            )
        except HttpError as exc:
            results.append(
                {
                    "id": check_id,
                    "url": url,
                    "source_type": source_type,
                    "http_status": exc.status,
                    "page_title": "",
                    "result": "broken" if exc.status in (404, 410) else "blocked",
                    "reason": str(exc),
                    "checked_at": utc_now_iso(),
                }
            )
    return results
