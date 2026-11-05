from pipeline.run import original_fact_filing_references


def test_original_fact_filing_references_include_historical_filings_once():
    facts = [
        {
            "is_original": True,
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/old/",
            "accession_number": "old-accession",
            "period_end": "2009-09-30",
        },
        {
            "is_original": True,
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/old/",
            "accession_number": "old-accession",
            "period_end": "2009-06-30",
        },
        {
            "is_original": False,
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/unneeded/",
            "accession_number": "unneeded-accession",
            "period_end": "2009-09-30",
        },
    ]

    assert original_fact_filing_references(facts) == [
        {
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/old/",
            "accession_number": "old-accession",
            "report_date": "2009-09-30",
        }
    ]
