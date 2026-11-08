"""CR-14 AI event verification tests."""

from pipeline.crawlers.ai_events import build_verified_events, page_published_date, verify_event


class StubResponse:
    def __init__(self, body: str):
        self._body = body
        self.status = 200
        self.content = body.encode("utf-8")
        self.content_type = "text/html"
        self.sha256 = "b" * 64
        self.fetched_at = "2026-11-05T00:00:00Z"
        self.url = "https://blog.google/example"

    @property
    def text(self) -> str:
        return self._body


class StubClient:
    def __init__(self, body: str):
        self.body = body

    def get(self, url: str, **_: object) -> StubResponse:
        return StubResponse(self.body)


SEED = {
    "id": "googl-gemini-1-0",
    "ticker": "GOOGL",
    "title": "Introducing Gemini",
    "category": "model_launch",
    "published_date": "2023-12-06",
    "source_url": "https://blog.google/innovation-and-ai/technology/ai/google-gemini-ai/",
    "evidence_quote": "Today, we're a step closer to this vision as we introduce Gemini, the most capable and general model we've ever built.",
}

GOOD_HTML = """
<html><head>
<meta property="article:published_time" content="2023-12-06T08:00:00Z">
<title>Introducing Gemini</title></head>
<body><p>Today, we\u2019re a step closer to this vision as we introduce <a href="#">Gemini</a>
, the most capable and general model we\u2019ve ever built.</p></body></html>
"""


def test_page_published_date_reads_meta_tag():
    assert page_published_date(GOOD_HTML) == "2023-12-06"
    assert page_published_date("<html><head></head><body></body></html>") is None


def test_verify_event_accepts_matching_quote_and_date():
    event, failed = verify_event(StubClient(GOOD_HTML), SEED)
    assert failed == []
    assert event["review_status"] == "verified"
    assert event["checks"] == {"quote_present": True, "published_date_matches": True}
    assert event["content_sha256"] == "b" * 64


def test_verify_event_rejects_missing_quote_and_wrong_date():
    body = GOOD_HTML.replace("a step closer to this vision", "a completely different claim").replace(
        "2023-12-06T08:00:00Z", "2024-01-01T08:00:00Z"
    )
    event, failed = verify_event(StubClient(body), SEED)
    assert event["review_status"] == "rejected"
    assert any("quote" in reason for reason in failed)
    assert any("published date" in reason for reason in failed)

    verified, report = build_verified_events(client=StubClient(body), seeds=[SEED])
    assert verified == []
    assert report["verified"] == 0
    assert report["rejected"] == 1
