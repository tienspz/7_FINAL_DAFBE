"""SEC crawler parsing tests."""

from pipeline.config import get_settings
from pipeline.crawlers.sec import (
    _recent_block,
    extract_facts,
    find_instance_file,
    mark_originals,
)
from pipeline.util import utc_now_iso

from tests.helpers import make_fact


def companyfacts(rows_by_tag: dict[str, list[dict]]) -> dict:
    return {
        "facts": {
            "us-gaap": {
                tag: {"units": {"USD": rows}}
                for tag, rows in rows_by_tag.items()
            }
        }
    }


def test_googl_tag_validity_switches_at_2025_q2():
    settings = get_settings()
    old_tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    payload = companyfacts(
        {
            old_tag: [
                {"start": "2025-01-01", "end": "2025-03-31", "val": 100, "form": "10-Q", "filed": "2025-04-25", "accn": "a1"},
                {"start": "2025-04-01", "end": "2025-06-30", "val": 110, "form": "10-Q", "filed": "2025-07-24", "accn": "a2"},
            ],
            "Revenues": [
                {"start": "2025-01-01", "end": "2025-03-31", "val": 100, "form": "10-Q", "filed": "2025-04-25", "accn": "a3"},
                {"start": "2025-04-01", "end": "2025-06-30", "val": 110, "form": "10-Q", "filed": "2025-07-24", "accn": "a4"},
            ],
        }
    )

    facts = extract_facts(
        ticker="GOOGL",
        companyfacts=payload,
        settings=settings,
        run_id="test",
        http_status=200,
        fetched_at=utc_now_iso(),
        response_sha256="sha",
    )
    revenue = [fact for fact in facts if fact.metric == "revenue"]
    assert sorted((fact.period_end, fact.xbrl_tag) for fact in revenue) == [
        ("2025-03-31", old_tag),
        ("2025-06-30", "Revenues"),
    ]


def test_msft_june_year_end_fact_is_fiscal_q4():
    settings = get_settings()
    payload = companyfacts(
        {
            "RevenueFromContractWithCustomerExcludingAssessedTax": [
                {"start": "2025-07-01", "end": "2026-06-30", "val": 500, "form": "10-K", "filed": "2026-07-29", "accn": "a1"},
            ]
        }
    )
    facts = extract_facts(
        ticker="MSFT",
        companyfacts=payload,
        settings=settings,
        run_id="test",
        http_status=200,
        fetched_at=utc_now_iso(),
        response_sha256="sha",
    )
    revenue = [fact for fact in facts if fact.metric == "revenue"]
    assert len(revenue) == 1
    assert revenue[0].fiscal_year == 2026
    assert revenue[0].fiscal_period == "Q4"
    assert revenue[0].period_type == "annual"


def test_mark_originals_detects_restatement_and_duplicate():
    rows = [
        make_fact(
            ticker="MSFT",
            metric="revenue",
            tag="Revenue",
            start="2024-07-01",
            end="2024-09-30",
            period_type="quarter",
            value=100.0,
            filed="2024-10-30",
            accession="a1",
            fact_id="f1",
        ),
        make_fact(
            ticker="MSFT",
            metric="revenue",
            tag="Revenue",
            start="2024-07-01",
            end="2024-09-30",
            period_type="quarter",
            value=105.0,
            filed="2025-10-30",
            accession="a2",
            fact_id="f2",
        ),
        make_fact(
            ticker="MSFT",
            metric="revenue",
            tag="Revenue",
            start="2024-07-01",
            end="2024-09-30",
            period_type="quarter",
            value=100.0,
            filed="2025-10-30",
            accession="a3",
            fact_id="f3",
        ),
    ]
    from pipeline.crawlers.sec import RawFact

    raw = []
    for row in rows:
        raw.append(
            RawFact(
                run_id="test",
                fact_id=row["fact_id"],
                cik="0000789019",
                ticker=row["ticker"],
                taxonomy="us-gaap",
                xbrl_tag=row["xbrl_tag"],
                unit=row["unit"],
                period_start=row["period_start"],
                period_end=row["period_end"],
                value_raw=row["value_usd"],
                value_usd=row["value_usd"],
                form=row["form"],
                fiscal_year=2025,
                fiscal_period="Q1",
                filed_date=row["filed_date"],
                accession_number=row["accession_number"],
                frame="",
                source_url=row["source_url"],
                evidence_url="",
                http_status=200,
                fetched_at="",
                response_sha256="",
                parser_version="1.0.0",
                metric=row["metric"],
                component="revenue",
                duration_days=90,
                period_type=row["period_type"],
                calendar_key=row["calendar_key"],
            )
        )
    marked = mark_originals(raw, min_usd=1.0)
    assert marked[0].is_original is True
    assert marked[1].is_restated is True
    assert marked[1].restatement_delta == 5.0
    assert marked[2].is_duplicate is True


def test_recent_block_accepts_archive_payload_shape():
    payload = {
        "accessionNumber": ["a1"],
        "form": ["10-Q"],
        "filingDate": ["2022-04-01"],
        "reportDate": ["2022-03-31"],
        "primaryDocument": ["doc.htm"],
    }
    assert _recent_block(payload) is payload


def test_find_instance_file_prefers_htm_instance():
    index = {
        "directory": {
            "item": [
                {"name": "doc.htm"},
                {"name": "msft-20260930_htm.xml"},
                {"name": "msft-20260930_cal.xml"},
            ]
        }
    }
    assert find_instance_file(index) == "msft-20260930_htm.xml"
