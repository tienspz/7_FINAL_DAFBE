"""End-to-end data pipeline CLI.

Usage:
    python -m pipeline.run --mode full
    python -m pipeline.run --mode incremental --refresh
    python -m pipeline.run --mode full --skip-segments --skip-stats
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.config import get_settings
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
from pipeline.http import CachedHttpClient, sec_user_agent
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
from pipeline.preprocess.calendar import analysis_quarters
from pipeline.preprocess.facts import build_company_quarters
from pipeline.preprocess.prices import build_price_analytics, normalize_prices
from pipeline.preprocess.segments import build_segment_table
from pipeline.stats.tests import run_all_tests
from pipeline.util import to_million, utc_now_iso, write_json
from pipeline.verify.links import (
    run_negative_checks,
    verify_concepts,
    verify_filing_indexes,
    verify_price_evidence,
)
from pipeline.verify.quality import build_quality_report
from pipeline.verify.reconcile import reconcile_financials, reconcile_prices, reconcile_segments


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if fieldnames:
        names = list(fieldnames)
    else:
        names = []
        for row in rows:
            for key in row:
                if key not in names:
                    names.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


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
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as connection:
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
    run_id = run_id.replace("Z", "Z")
    log(f"start {run_id} mode={args.mode}")

    for directory in [settings.raw_dir, settings.verified_dir, settings.snapshot_dir, settings.web_data_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    sec_client = CachedHttpClient(
        cache_dir=settings.raw_dir / "_cache",
        user_agent=sec_user_agent(),
        min_delay_seconds=0.2,
    )
    yahoo_client = CachedHttpClient(
        cache_dir=settings.raw_dir / "_cache",
        user_agent=sec_user_agent(),
        min_delay_seconds=1.0,
    )

    # 1) SEC submissions and filings.
    all_filings: list[Filing] = []
    filing_rows_data: list[dict[str, Any]] = []
    for ticker, cik in CIKS.items():
        log(f"SEC submissions {ticker}")
        response = sec_client.get(submissions_url(cik), refresh=args.refresh)
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
    write_csv(settings.raw_dir / "sec" / "filings.csv", filing_rows_data)

    # 2) SEC companyfacts -> mapped facts.
    all_facts: list[RawFact] = []
    for ticker, cik in CIKS.items():
        log(f"SEC companyfacts {ticker}")
        response = sec_client.get(companyfacts_url(cik), refresh=args.refresh)
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
    all_facts = mark_originals(
        all_facts,
        min_usd=settings.thresholds["quality"]["restatement_min_usd"],
        min_eps=settings.thresholds["quality"]["restatement_min_eps"],
    )
    facts_rows = [fact.as_row() for fact in all_facts]
    write_csv(settings.raw_dir / "sec" / "facts.csv", facts_rows)
    log(f"facts.csv: {len(facts_rows)} rows")

    # 3) Prices.
    log("prices yfinance")
    analysis = settings.thresholds["analysis"]
    price_start = date.fromisoformat(analysis["price_history_start"])
    price_end = date.today()
    price_bundle = fetch_prices(
        tickers=PRICE_TICKERS,
        start=price_start,
        end=price_end,
        raw_dir=settings.raw_dir,
        as_of=price_end.isoformat(),
        refresh=args.refresh,
    )
    prices_by_ticker = {
        ticker: normalize_prices(group)
        for ticker, group in price_bundle.prices.groupby("ticker")
    }
    log(f"prices: {len(price_bundle.prices)} rows across {len(prices_by_ticker)} tickers")

    # 4) Segments.
    segment_rows: list[dict[str, Any]] = []
    if not args.skip_segments:
        segment_filing_rows: list[dict[str, Any]] = []
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
        write_csv(settings.raw_dir / "sec" / "segments.csv", segment_rows)

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
    data_as_of = max(
        frame["trade_date"].max().isoformat()
        for frame in prices_by_ticker.values()
        if not frame.empty
    )
    price_end_date = date.fromisoformat(data_as_of)
    price_analytics: dict[str, Any] = {}
    for ticker, frame in prices_by_ticker.items():
        price_analytics[ticker] = build_price_analytics(
            ticker=ticker,
            frame=frame,
            quarters=[quarter.key for quarter in quarters],
            price_start=price_start,
            price_end=price_end_date,
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
                flat[f"{metric_name}_accession_number"] = metric.accession_number
                flat[f"{metric_name}_xbrl_tag"] = metric.xbrl_tag
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
        stats_payload = run_all_tests(
            rows_by_ticker=rows_by_ticker,
            price_analytics=price_analytics,
            tickers=["MSFT", "GOOGL"],
            alpha=settings.thresholds["stats"]["alpha"],
            max_lag=settings.thresholds["stats"]["max_lag"],
        )
        log(f"  {len(stats_payload.get('results', []))} test results")

    # 10) Verification reports.
    log("verify links")
    link_items = verify_filing_indexes(
        client=sec_client,
        filings=[
            {
                "source_url": filing.source_url,
                "accession_number": filing.accession_number,
                "report_date": filing.report_date,
            }
            for filing in all_filings
        ],
    )
    link_items.extend(verify_concepts(client=sec_client, facts=facts_rows))
    link_items.extend(verify_price_evidence(client=yahoo_client, prices_by_ticker=prices_by_ticker))
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
    checks.extend(reconcile_prices(price_analytics=price_analytics, settings=settings))
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
        },
        link_report=link_report,
        quality_report=quality_report,
        source_versions={
            "yfinance": "1.7.0",
            "pandas": pd.__version__,
            "python": sys.version.split()[0],
        },
    )
    write_json(settings.web_data_dir / "manifest.json", manifest)
    write_json(settings.verified_dir / "manifest.json", manifest)

    # 13) SQLite handoff and processed price CSV.
    log("write sqlite + processed price CSV")
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
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
