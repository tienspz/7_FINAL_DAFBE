"""End-to-end data pipeline CLI.

Usage:
    python -m pipeline.run --mode full
    python -m pipeline.run --mode incremental --refresh
    python -m pipeline.run --mode full --skip-segments --skip-stats
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.config import get_settings
from pipeline.crawlers.ai_events import build_verified_events, load_ai_event_seeds
from pipeline.crawlers.alphavantage import fetch_adjusted_closes
from pipeline.crawlers.nasdaq import (
    BROWSER_USER_AGENT,
    fetch_secondary_closes,
)
from pipeline.crawlers.prices import PRICE_TICKERS, fetch_prices
from pipeline.crawlers.sec import (
    CIKS,
    Filing,
    RawFact,
    SegmentFact,
    collect_filings,
    companyfacts_url,
    extract_facts,
    fetch_segment_facts,
    mark_originals,
    recent_filings,
    submissions_url,
)
from pipeline.http import (
    CachedHttpClient,
    MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
    sec_user_agent,
)
from pipeline.metrics.formulas import enrich_company_rows
from pipeline.preprocess.build_outputs import (
    build_ai_analysis,
    build_decision,
    build_financials,
    build_investor,
    build_manifest,
    build_methodology,
    build_overview,
    next_snapshot_version,
    write_price_files,
)
from pipeline.preprocess.export_csv import export_json_tables_to_csv
from pipeline.preprocess.calendar import analysis_quarters
from pipeline.preprocess.facts import build_company_quarters
from pipeline.preprocess.prices import (
    adjusted_close_selfcheck,
    build_price_analytics,
    normalize_prices,
)
from pipeline.preprocess.segments import build_segment_table
from pipeline.stats.tests import present_p_values, run_all_tests
from pipeline.sync import SyncLog, archive_raw_file, raw_file_manifest
from pipeline.util import atomic_write_text, to_million, utc_now_iso, write_json
from pipeline.verify.links import (
    run_negative_checks,
    verify_concepts,
    verify_filing_indexes,
    verify_price_evidence,
)
from pipeline.verify.quality import build_quality_report
from pipeline.verify.reconcile import (
    reconcile_adjusted_selfcheck,
    reconcile_financials,
    reconcile_prices,
    reconcile_segments,
)


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        atomic_write_text(path, "")
        return
    if fieldnames:
        names = list(fieldnames)
    else:
        names = []
        for row in rows:
            for key in row:
                if key not in names:
                    names.append(key)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=names,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, buffer.getvalue())


def original_fact_filing_references(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    references: dict[str, dict[str, Any]] = {}
    for fact in facts:
        if not fact.get("is_original"):
            continue
        url = fact["source_url"]
        references.setdefault(
            url,
            {
                "source_url": url,
                "accession_number": fact.get("accession_number"),
                "report_date": fact.get("period_end"),
            },
        )
    return list(references.values())


def filing_rows(filings: list[Filing], run_id: str, http_status: int, fetched_at: str, sha: str) -> list[dict[str, Any]]:
    return [
        {
            "run_id": run_id,
            "cik": filing.cik,
            "ticker": filing.ticker,
            "company_name": "Microsoft Corp" if filing.ticker == "MSFT" else "Alphabet Inc.",
            "accession_number": filing.accession_number,
            "form": filing.form,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "primary_document": filing.primary_document,
            "is_amendment": filing.form.endswith("/A"),
            "source_url": filing.source_url,
            "evidence_url": submissions_url(filing.cik),
            "http_status": http_status,
            "fetched_at": fetched_at,
            "response_sha256": sha,
            "parser_version": "1.0.0",
        }
        for filing in filings
    ]


def build_sqlite(
    *,
    db_path: Path,
    facts_rows: list[dict[str, Any]],
    filing_rows_data: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    financial_rows: list[dict[str, Any]],
    prices: pd.DataFrame,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{db_path.name}.",
        suffix=".tmp",
        dir=db_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            with connection:
                if facts_rows:
                    pd.DataFrame(facts_rows).to_sql("facts", connection, index=False)
                if filing_rows_data:
                    pd.DataFrame(filing_rows_data).to_sql("filings", connection, index=False)
                if segment_rows:
                    pd.DataFrame(segment_rows).to_sql("segments", connection, index=False)
                if financial_rows:
                    pd.DataFrame(financial_rows).to_sql("company_financials", connection, index=False)
                if not prices.empty:
                    prices.to_sql("prices", connection, index=False)
        finally:
            connection.close()
        os.replace(temporary_path, db_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AICOR raw + preprocess pipeline")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full")
    parser.add_argument("--refresh", action="store_true", help="Ignore the HTTP cache and refetch sources")
    parser.add_argument("--skip-segments", action="store_true")
    parser.add_argument("--segment-limit", type=int, default=0, help="0 means all 10-Q/10-K filings")
    parser.add_argument("--skip-stats", action="store_true")
    parser.add_argument("--skip-negative", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    run_id = "run_" + utc_now_iso().replace("-", "").replace(":", "").replace("T", "T")
    run_id += "_" + uuid.uuid4().hex[:8]
    log(f"start {run_id} mode={args.mode}")

    for directory in [settings.raw_dir, settings.verified_dir, settings.snapshot_dir, settings.web_data_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    sync_log = SyncLog(settings.verified_dir / "sync_log.jsonl", run_id=run_id)
    archived_raw_paths: list[Path] = []

    sec_client = CachedHttpClient(
        cache_dir=settings.raw_dir / "_cache",
        user_agent=sec_user_agent(),
        min_delay_seconds=0.2,
        allowed_domains=settings.allowed_domains,
        enforce_allowlist=True,
    )
    yahoo_client = CachedHttpClient(
        cache_dir=settings.raw_dir / "_cache",
        user_agent=sec_user_agent(),
        min_delay_seconds=1.0,
        allowed_domains=settings.allowed_domains,
        enforce_allowlist=True,
    )
    # Nasdaq and the official AI blogs reject the SEC User-Agent.
    browser_client = CachedHttpClient(
        cache_dir=settings.raw_dir / "_cache",
        user_agent=BROWSER_USER_AGENT,
        min_delay_seconds=1.0,
        allowed_domains=settings.allowed_domains,
        enforce_allowlist=True,
        redact_query_keys=("apikey",),
    )

    # 1) SEC submissions and filings.
    all_filings: list[Filing] = []
    filing_rows_data: list[dict[str, Any]] = []
    with sync_log.source("sec_submissions") as source_sync:
        for ticker, cik in CIKS.items():
            log(f"SEC submissions {ticker}")
            response = sec_client.get(
                submissions_url(cik),
                refresh=args.refresh,
                max_age_seconds=MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
            )
            payload = response.json()
            filings = collect_filings(
                client=sec_client,
                submissions=payload,
                ticker=ticker,
                since="2021-01-01",
            )
            all_filings.extend(filings)
            filing_rows_data.extend(
                filing_rows(filings, run_id, response.status, response.fetched_at, response.sha256)
            )
            log(f"  {len(filings)} 10-Q/10-K filings")
        filings_path = settings.raw_dir / "sec" / "filings.csv"
        write_csv(filings_path, filing_rows_data)
        archived_raw_paths.append(archive_raw_file(settings.raw_dir, run_id, filings_path))
        source_sync.records_added = len(filing_rows_data)

    # 2) SEC companyfacts -> mapped facts.
    all_facts: list[RawFact] = []
    with sync_log.source("sec_companyfacts") as source_sync:
        for ticker, cik in CIKS.items():
            log(f"SEC companyfacts {ticker}")
            response = sec_client.get(
                companyfacts_url(cik),
                refresh=args.refresh,
                max_age_seconds=MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
            )
            facts = extract_facts(
                ticker=ticker,
                companyfacts=response.json(),
                settings=settings,
                run_id=run_id,
                http_status=response.status,
                fetched_at=response.fetched_at,
                response_sha256=response.sha256,
            )
            all_facts.extend(facts)
            log(f"  {len(facts)} mapped facts")
        source_sync.records_added = len(all_facts)
    all_facts = mark_originals(
        all_facts,
        min_usd=settings.thresholds["quality"]["restatement_min_usd"],
        min_eps=settings.thresholds["quality"]["restatement_min_eps"],
    )

    with sync_log.source("sec_fact_verification") as source_sync:
        fact_rows = [fact.as_row() for fact in all_facts]
        filing_references = {
            filing.source_url: {
                "source_url": filing.source_url,
                "accession_number": filing.accession_number,
                "report_date": filing.report_date,
            }
            for filing in all_filings
        }
        for item in original_fact_filing_references(fact_rows):
            filing_references.setdefault(item["source_url"], item)
        filing_verification_items = verify_filing_indexes(
            client=sec_client,
            filings=list(filing_references.values()),
        )
        filing_status = {
            item["url"]: item["result"] == "ok" for item in filing_verification_items
        }
        concept_verification_items = verify_concepts(
            client=sec_client,
            facts=fact_rows,
            refresh=args.refresh,
        )
        concept_status = {
            item["fact_id"]: item for item in concept_verification_items if item.get("fact_id")
        }
        for fact in all_facts:
            if not fact.is_original:
                fact.verification_reason = "not selected: not the first-filed fact"
                continue
            concept_result = concept_status.get(fact.fact_id)
            filing_verified = filing_status.get(fact.source_url, False)
            concept_verified = bool(concept_result and concept_result["result"] == "ok")
            fact.verified = filing_verified and concept_verified
            reasons = []
            if not filing_verified:
                reasons.append("filing index verification failed")
            if not concept_verified:
                reasons.append(
                    concept_result["reason"] if concept_result else "XBRL fact verification missing"
                )
            fact.verification_reason = "; ".join(reasons)
            if fact.verified:
                fact.verification_reason = ""
        verified_originals = sum(fact.is_original and fact.verified for fact in all_facts)
        original_count = sum(fact.is_original for fact in all_facts)
        source_sync.records_added = len(concept_verification_items)
        if verified_originals != original_count:
            source_sync.mark_partial(
                f"{original_count - verified_originals}/{original_count} original facts failed verification"
            )

    facts_rows = [fact.as_row() for fact in all_facts]
    facts_path = settings.raw_dir / "sec" / "facts.csv"
    write_csv(facts_path, facts_rows)
    archived_raw_paths.append(archive_raw_file(settings.raw_dir, run_id, facts_path))
    log(f"facts.csv: {len(facts_rows)} rows")

    # 3) Prices.
    log("prices yfinance")
    analysis = settings.thresholds["analysis"]
    price_start = date.fromisoformat(analysis["price_history_start"])
    price_end = date.today()
    with sync_log.source("yahoo_prices") as source_sync:
        price_bundle = fetch_prices(
            tickers=PRICE_TICKERS,
            start=price_start,
            end=price_end,
            raw_dir=settings.raw_dir,
            as_of=price_end.isoformat(),
            refresh=args.refresh,
            max_age_seconds=MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
        )
        price_artifacts = {
            price_bundle.combined_path,
            *price_bundle.ticker_paths.values(),
            settings.raw_dir / "prices" / "corporate_actions.csv",
        }
        for path in sorted(price_artifacts):
            archived_raw_paths.append(archive_raw_file(settings.raw_dir, run_id, path))
        source_sync.records_added = len(price_bundle.prices)
    prices_by_ticker = {
        ticker: normalize_prices(group)
        for ticker, group in price_bundle.prices.groupby("ticker")
    }
    log(f"prices: {len(price_bundle.prices)} rows across {len(prices_by_ticker)} tickers")
    data_as_of = max(
        frame["trade_date"].max().isoformat()
        for frame in prices_by_ticker.values()
        if not frame.empty
    )
    price_end_date = date.fromisoformat(data_as_of)

    # 3b) Secondary unadjusted close (Nasdaq, CR-13 approved).
    log("secondary closes nasdaq")
    with sync_log.source("nasdaq_secondary_close") as source_sync:
        secondary = fetch_secondary_closes(
            client=browser_client,
            tickers=PRICE_TICKERS,
            start=price_end_date - timedelta(days=90),
            end=price_end_date,
            raw_dir=settings.raw_dir,
            refresh=args.refresh,
        )
        for artifact in secondary["artifacts"].values():
            path = settings.project_root / artifact["path"]
            archived_raw_paths.append(archive_raw_file(settings.raw_dir, run_id, path))
        source_sync.records_added = sum(len(rows) for rows in secondary["rows_by_ticker"].values())
        if secondary["errors"]:
            source_sync.mark_partial(json.dumps(secondary["errors"], sort_keys=True))
    log(
        f"  {len(secondary['rows_by_ticker'])} tickers reconciled, "
        f"{len(secondary['errors'])} unavailable"
    )

    # 3c) Conditional adjusted-close cross-check (Alpha Vantage, real key only).
    log("adjusted close alphavantage")
    with sync_log.source("alphavantage_adjusted_close") as source_sync:
        adjusted = fetch_adjusted_closes(
            client=browser_client,
            tickers=["MSFT", "GOOGL"],
            raw_dir=settings.raw_dir,
            as_of=data_as_of,
            refresh=args.refresh,
        )
        for artifact in adjusted["artifacts"].values():
            path = settings.project_root / artifact["path"]
            archived_raw_paths.append(archive_raw_file(settings.raw_dir, run_id, path))
        source_sync.records_added = sum(len(rows) for rows in adjusted["rows_by_ticker"].values())
        if not adjusted["available"]:
            source_sync.mark_partial(adjusted["reason"])
        elif adjusted["errors"]:
            source_sync.mark_partial(json.dumps(adjusted["errors"], sort_keys=True))
    log("  available" if adjusted["available"] else f"  unverified: {adjusted['reason']}")

    # 3d) CR-14 AI events: official pages only, quote + date verified.
    log("AI event verification")
    with sync_log.source("official_ai_events") as source_sync:
        ai_events, ai_event_report = build_verified_events(
            client=browser_client,
            seeds=load_ai_event_seeds(settings),
        )
        source_sync.records_added = len(ai_events)
        if ai_event_report["rejected"]:
            source_sync.mark_partial(f"{ai_event_report['rejected']} AI event seeds rejected")
    write_json(settings.verified_dir / "ai_events_report.json", ai_event_report)
    log(
        f"  {ai_event_report['verified']}/{ai_event_report['total_seeds']} events verified, "
        f"{ai_event_report['rejected']} rejected"
    )

    # 4) Segments.
    segment_rows: list[dict[str, Any]] = []
    if not args.skip_segments:
        with sync_log.source("sec_segments") as source_sync:
            for ticker in PRICE_TICKERS[:2]:
                ticker_filings = [
                    filing
                    for filing in all_filings
                    if filing.ticker == ticker and filing.form in {"10-Q", "10-K"}
                ]
                ticker_filings.sort(key=lambda filing: filing.report_date)
                if args.segment_limit:
                    ticker_filings = ticker_filings[-args.segment_limit :]
                log(f"segments {ticker}: {len(ticker_filings)} filings")
                segment_facts = fetch_segment_facts(
                    client=sec_client,
                    settings=settings,
                    ticker=ticker,
                    filings=ticker_filings,
                    run_id=run_id,
                )
                segment_rows.extend(fact.as_row() for fact in segment_facts)
                log(f"  {len(segment_facts)} segment facts")
            segments_path = settings.raw_dir / "sec" / "segments.csv"
            write_csv(segments_path, segment_rows)
            archived_raw_paths.append(archive_raw_file(settings.raw_dir, run_id, segments_path))
            source_sync.records_added = len(segment_rows)

    raw_run_directory = settings.raw_dir / "runs" / run_id
    write_json(raw_run_directory / "manifest.json", raw_file_manifest(run_id, archived_raw_paths, settings.raw_dir))

    # 5) Preprocess quarterly financials.
    log("preprocess financials")
    quarters = analysis_quarters(settings)
    rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for ticker in ["MSFT", "GOOGL"]:
        rows = build_company_quarters(
            ticker=ticker,
            facts=facts_rows,
            settings=settings,
            quarters=quarters,
        )
        rows_by_ticker[ticker] = rows
        log(f"  {ticker}: {len(rows)} quarters")

    # 6) Price analytics and derived metrics.
    log("price analytics")
    analysis_start = date(
        int(analysis["start_year"]),
        (int(analysis["start_quarter"]) - 1) * 3 + 1,
        1,
    )
    price_analytics: dict[str, Any] = {}
    for ticker, frame in prices_by_ticker.items():
        price_analytics[ticker] = build_price_analytics(
            ticker=ticker,
            frame=frame,
            quarters=[quarter.key for quarter in quarters],
            price_start=price_start,
            price_end=price_end_date,
            analysis_start=analysis_start,
            as_of=price_end_date,
        )
    for ticker, rows in rows_by_ticker.items():
        enrich_company_rows(ticker=ticker, rows=rows, price_analytics=price_analytics[ticker])

    # 7) Segment table.
    segment_table: list[dict[str, Any]] = []
    if segment_rows:
        segment_table = build_segment_table(
            segment_facts=segment_rows,
            quarters=quarters,
            consolidated_rows=[row for rows in rows_by_ticker.values() for row in rows],
            settings=settings,
        )
        write_csv(settings.verified_dir / "segment_financials.csv", segment_table)

    # 8) Wide table CSV.
    financial_rows: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        for row in rows:
            flat: dict[str, Any] = {
                "ticker": ticker,
                "calendar_key": row["calendar_key"],
                "period_end": row["period_end"],
                "fiscal_year": row["fiscal_year"],
                "fiscal_quarter": row["fiscal_quarter"],
            }
            for metric_name, metric in row["metrics"].items():
                flat[metric_name] = to_million(metric.value) if metric.unit == "USD" else metric.value
                flat[f"{metric_name}_quality"] = metric.quality_flag
                flat[f"{metric_name}_source_url"] = metric.source_url
                flat[f"{metric_name}_evidence_url"] = metric.evidence_url
                flat[f"{metric_name}_accession_number"] = metric.accession_number
                flat[f"{metric_name}_xbrl_tag"] = metric.xbrl_tag
                flat[f"{metric_name}_fact_id"] = metric.fact_id
                flat[f"{metric_name}_response_sha256"] = metric.response_sha256
                flat[f"{metric_name}_fetched_at"] = metric.fetched_at
                flat[f"{metric_name}_verified"] = metric.verified
                flat[f"{metric_name}_derived"] = metric.derived
                flat[f"{metric_name}_derivation_method"] = metric.derivation_method
                if metric.reported_value is not None:
                    flat[f"{metric_name}_reported_value"] = (
                        to_million(metric.reported_value) if metric.unit == "USD" else metric.reported_value
                    )
                if metric.split_adjustment is not None:
                    flat[f"{metric_name}_split_adjustment"] = metric.split_adjustment
            flat["derived_metrics_json"] = json.dumps(row.get("derived", {}), ensure_ascii=False)
            financial_rows.append(flat)
    write_csv(settings.verified_dir / "company_financials.csv", financial_rows)

    # 9) Statistical tests.
    stats_payload: dict[str, Any] = {"schema_version": "1.0", "results": [], "warnings": ["not run"]}
    if not args.skip_stats:
        log("statistical tests BT1-BT5")
        stats_config = settings.thresholds["stats"]
        quality_config = settings.thresholds["quality"]
        quality_letter = str(quality_config.get("quality_mode_primary", "B")).upper()
        quality_mode = "label_low" if quality_letter == "B" else "exclude_low"
        one_off_quarters = {
            ticker: {
                item["calendar_key"]: item.get("reason", "one-off quarter")
                for item in items
            }
            for ticker, items in quality_config.get("net_income_one_off_quarters", {}).items()
        }
        stats_payload = run_all_tests(
            rows_by_ticker=rows_by_ticker,
            price_analytics=price_analytics,
            tickers=["MSFT", "GOOGL"],
            alpha=stats_config["alpha"],
            max_lag=stats_config["max_lag"],
            quality_mode=quality_mode,
            quality_mode_primary=quality_letter,
            bt1_start=stats_config.get("bt1_start", analysis_start.isoformat()),
            bt1_end=data_as_of,
            one_off_quarters=one_off_quarters or None,
            comparison_modes=tuple(quality_config.get("stats_quality_modes", ["exclude_low", "label_low"])),
            holm_primary=stats_config.get("holm_primary", "bt"),
            fragility_max_n=int(stats_config.get("fragility_max_n", 15)),
            permutation_iterations=int(stats_config.get("permutation_iterations", 10000)),
            permutation_seed=int(stats_config.get("permutation_seed", 20261107)),
            bt3_bootstrap_iterations=int(stats_config.get("bt3_bootstrap_iterations", 1000)),
            bt3_block_length=int(stats_config.get("bt3_block_length", 4)),
            bt3_bootstrap_seed=int(stats_config.get("bt3_bootstrap_seed", 20261107)),
        )
        stats_payload = present_p_values(stats_payload)
        log(
            f"  {len(stats_payload.get('results', []))} test results, quality_mode={quality_mode}"
        )

    # 10) Verification reports.
    log("verify links")
    link_items = [*filing_verification_items, *concept_verification_items]
    with sync_log.source("yahoo_price_evidence") as source_sync:
        price_verification_items = verify_price_evidence(
            client=yahoo_client,
            prices_by_ticker=prices_by_ticker,
            refresh=args.refresh,
        )
        link_items.extend(price_verification_items)
        source_sync.records_added = len(price_verification_items)
        failed_price_checks = sum(item["result"] != "ok" for item in price_verification_items)
        if failed_price_checks:
            source_sync.mark_partial(f"{failed_price_checks} Yahoo price evidence checks did not pass")
    negative_items = [] if args.skip_negative else run_negative_checks(sec_client)
    link_report = {
        "schema_version": "1.0",
        "checked_at": utc_now_iso(),
        "summary": {
            "total": len(link_items),
            "ok": sum(1 for item in link_items if item["result"] == "ok"),
            "broken": sum(1 for item in link_items if item["result"] == "broken"),
            "blocked": sum(1 for item in link_items if item["result"] == "blocked"),
            "soft404": sum(1 for item in link_items if item["result"] == "soft404"),
            "low": sum(1 for item in link_items if item["result"] == "low"),
            "pending": sum(1 for item in link_items if item["result"] == "pending"),
        },
        "items": link_items,
        "negative_checks": negative_items,
    }
    write_json(settings.verified_dir / "link_report.json", link_report)

    log("reconcile")
    checks = reconcile_financials(
        rows_by_ticker=rows_by_ticker,
        facts=facts_rows,
        settings=settings,
        snapshot_date=date.today(),
    )
    checks.extend(reconcile_segments(segment_rows=segment_table, settings=settings))
    checks.extend(
        reconcile_prices(
            price_analytics=price_analytics,
            settings=settings,
            prices_by_ticker=prices_by_ticker,
            secondary=secondary,
            adjusted=adjusted,
        )
    )
    adjusted_selfchecks = {
        ticker: adjusted_close_selfcheck(prices_by_ticker[ticker])
        for ticker in ("MSFT", "GOOGL")
        if ticker in prices_by_ticker
    }
    checks.extend(
        reconcile_adjusted_selfcheck(selfchecks=adjusted_selfchecks, settings=settings)
    )
    reconcile_report = {
        "schema_version": "1.0",
        "checked_at": utc_now_iso(),
        "summary": {
            "total": len(checks),
            "ok": sum(1 for check in checks if check["status"] == "ok"),
            "low": sum(1 for check in checks if check["status"] == "low"),
            "fail": sum(1 for check in checks if check["status"] == "fail"),
            "pending": sum(1 for check in checks if check["status"] == "pending"),
            "unverified": sum(1 for check in checks if check["status"] == "unverified"),
        },
        "checks": checks,
    }
    write_json(settings.verified_dir / "reconcile_report.json", reconcile_report)

    # 11) Quality report.
    log("quality report")
    snapshot_version = next_snapshot_version(settings.web_data_dir, data_as_of)
    quality_report = build_quality_report(
        settings=settings,
        quarters=quarters,
        rows_by_ticker=rows_by_ticker,
        facts=facts_rows,
        segment_rows=segment_table,
        snapshot_version=snapshot_version,
    )
    write_json(settings.verified_dir / "quality_report.json", quality_report)
    evidence_dir = settings.project_root / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        evidence_dir / "quality_evidence.json",
        {
            "generated_at": utc_now_iso(),
            "run_id": run_id,
            "snapshot_version": snapshot_version,
            "data_as_of": data_as_of,
            "quality_mode": quality_report["quality_mode"],
            "excluded_quarters": quality_report["excluded_quarters"],
            "derived_quarters": quality_report["derived_quarters"],
            "net_income_bridge": quality_report["net_income_bridge"],
        },
    )

    # 12) Dashboard JSON.
    log(f"build outputs snapshot={snapshot_version}")
    generated_at = utc_now_iso()
    outputs: dict[str, Any] = {}
    outputs["financials.json"] = build_financials(
        rows_by_ticker=rows_by_ticker,
        segment_rows=segment_table,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
    )
    outputs["overview.json"] = build_overview(
        rows_by_ticker=rows_by_ticker,
        price_analytics=price_analytics,
        prices_by_ticker=prices_by_ticker,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
        data_as_of=data_as_of,
    )
    outputs["investor.json"] = build_investor(
        price_analytics=price_analytics,
        tests=stats_payload,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
    )
    outputs["ai_analysis.json"] = build_ai_analysis(
        rows_by_ticker=rows_by_ticker,
        tests=stats_payload,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
        events=ai_events,
    )
    outputs["decision.json"] = build_decision(
        rows_by_ticker=rows_by_ticker,
        price_analytics=price_analytics,
        settings=settings,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
    )
    outputs["methodology.json"] = build_methodology(
        settings=settings,
        quality_report=quality_report,
        link_report=link_report,
        reconcile_report=reconcile_report,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
    )
    outputs["tests.json"] = {
        **stats_payload,
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
    }

    for name, payload in outputs.items():
        write_json(settings.web_data_dir / name, payload)
    price_files = write_price_files(
        web_data_dir=settings.web_data_dir,
        prices_by_ticker=prices_by_ticker,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
    )

    all_files = list(outputs.keys()) + price_files
    manifest = build_manifest(
        web_data_dir=settings.web_data_dir,
        files=all_files,
        snapshot_version=snapshot_version,
        generated_at=generated_at,
        data_as_of=data_as_of,
        latest_quarter=max(row["calendar_key"] for rows in rows_by_ticker.values() for row in rows),
        row_counts={
            "filings": len(filing_rows_data),
            "facts": len(facts_rows),
            "prices": len(price_bundle.prices),
            "segments": len(segment_rows),
            "financial_quarters": len(financial_rows),
            "ai_events": len(ai_events),
        },
        link_report=link_report,
        quality_report=quality_report,
        source_versions={
            "yfinance": "1.7.0",
            "pandas": pd.__version__,
            "python": sys.version.split()[0],
        },
    )
    manifest["run_id"] = run_id
    write_json(settings.web_data_dir / "manifest.json", manifest)
    write_json(settings.verified_dir / "manifest.json", manifest)

    log("export dashboard JSON tables to DataProcessedView")
    export_json_tables_to_csv(
        source_dir=settings.web_data_dir,
        output_dir=settings.project_root / "DataProcessedView",
    )

    # 13) SQLite handoff and processed price CSV.
    log("write sqlite + processed price CSV")
    with sync_log.source("dashboard_handoff") as source_sync:
        write_csv(
            settings.verified_dir / "prices_processed.csv",
            price_bundle.prices.to_dict(orient="records"),
        )
        build_sqlite(
            db_path=settings.data_dir / "db" / "aicor.sqlite",
            facts_rows=facts_rows,
            filing_rows_data=filing_rows_data,
            segment_rows=segment_rows,
            financial_rows=financial_rows,
            prices=price_bundle.prices,
        )
        source_sync.records_added = len(financial_rows) + len(price_bundle.prices)
    with sync_log.source("pipeline_complete") as source_sync:
        source_sync.records_added = len(all_files)

    log("done")
    print(
        json.dumps(
            {
                "snapshot_version": snapshot_version,
                "data_as_of": data_as_of,
                "facts": len(facts_rows),
                "filings": len(filing_rows_data),
                "prices": len(price_bundle.prices),
                "segments": len(segment_rows),
                "quarters": len(financial_rows),
                "link_report": link_report["summary"],
                "quality": quality_report["summary"],
                "reconcile": reconcile_report["summary"],
                "tests": len(stats_payload.get("results", [])),
                "quality_mode": stats_payload.get("quality_mode"),
                "excluded_quarter_groups": len(quality_report.get("excluded_quarters", [])),
                "derived_quarters": len(quality_report.get("derived_quarters", [])),
                "adjusted_close_selfcheck": {
                    ticker: result.get("max_relative_difference")
                    for ticker, result in adjusted_selfchecks.items()
                },
                "secondary_close": {
                    ticker: next(
                        (check["status"] for check in checks if check["check"] == "secondary_close" and check.get("ticker") == ticker),
                        "missing",
                    )
                    for ticker in PRICE_TICKERS
                },
                "adjusted_close": {
                    ticker: next(
                        (check["status"] for check in checks if check["check"] == "secondary_adjusted_close" and check.get("ticker") == ticker),
                        "missing",
                    )
                    for ticker in ("MSFT", "GOOGL")
                },
                "ai_events": len(ai_events),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
