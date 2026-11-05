"""Link classification, verification, and negative-control tests."""

from pipeline.verify.links import classify_html, page_title, verify_concepts


LONG_BODY = "<html><body><p>" + ("filed financial statement " * 40) + "</p></body></html>"


def test_valid_filing_page_requires_accession_and_content():
    result, reason = classify_html("EDGAR Filing Documents", LONG_BODY, "0000000000-25-000001")
    assert result == "broken"
    assert "accession number not found" in reason

    body = LONG_BODY.replace("</body>", "0000000000-25-000001</body>")
    result, reason = classify_html("EDGAR Filing Documents", body, "0000000000-25-000001")
    assert result == "ok"
    assert reason == ""


def test_soft404_titles_are_rejected():
    for title in ["", "Default", "Page not found", "404", "Access denied"]:
        result, _ = classify_html(title, LONG_BODY)
        assert result == "soft404", title


def test_short_body_is_rejected_even_with_good_title():
    result, reason = classify_html("EDGAR Filing Documents", "<html><body>ok</body></html>")
    assert result == "soft404"
    assert "body too short" in reason


def test_page_title_is_extracted_and_collapsed():
    html = "<html><head><title>  EDGAR   Filing  </title></head></html>"
    assert page_title(html) == "EDGAR Filing"


class FakeClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.urls: list[str] = []

    def get(self, url: str, **kwargs):
        self.urls.append(url)
        return FakeResponse(self.payload)


class FakeResponse:
    status = 200
    content_type = "application/json"
    content = b"{}"
    sha256 = "a" * 64

    def __init__(self, payload: dict):
        self.payload = payload

    def json(self):
        return self.payload


def _fact(fact_id: str, accession: str, period_end: str, value: float) -> dict:
    return {
        "fact_id": fact_id,
        "cik": "0000789019",
        "xbrl_tag": "Revenue",
        "unit": "USD",
        "accession_number": accession,
        "period_end": period_end,
        "value_usd": value,
        "is_original": True,
    }


def test_verify_concepts_checks_each_fact_in_a_tag_group():
    client = FakeClient(
        {
            "units": {
                "USD": [
                    {"accn": "a1", "end": "2025-03-31", "val": 100.0},
                    {"accn": "a2", "end": "2025-06-30", "val": 200.0},
                ]
            }
        }
    )
    facts = [
        _fact("f1", "a1", "2025-03-31", 100.0),
        _fact("f2", "a2", "2025-06-30", 201.0),
    ]

    results = verify_concepts(client=client, facts=facts)

    assert [result["fact_id"] for result in results] == ["f1", "f2"]
    assert [result["result"] for result in results] == ["ok", "broken"]
    assert results[1]["reason"] == "XBRL value mismatch"
    assert len(client.urls) == 1


def test_verify_concepts_requires_exact_accession_period_and_value():
    client = FakeClient(
        {"units": {"USD": [{"accn": "other", "end": "2025-03-31", "val": 100.0}]}}
    )
    result = verify_concepts(
        client=client,
        facts=[_fact("f1", "expected", "2025-03-31", 100.0)],
    )[0]

    assert result["result"] == "broken"
    assert result["reason"] == "no matching XBRL fact in companyconcept"
