"""CR-14 AI events: official sources only, verified before they are displayable.

Each curated seed names an official page, the exact quote that supports the
event, and the publication date. The pipeline re-reads the page, checks that the
quote is present in the rendered text, checks the page's own published date,
and records the response hash. Any failed check rejects the event, so the
dashboard never shows an unverified claim.

``entered_by`` / ``reviewed_by`` are explicit provenance strings. The review is
an automated evidence check, not a human editorial sign-off; this is recorded in
``review_method`` and surfaced in the methodology.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from pipeline.config import Settings
from pipeline.http import CachedHttpClient, HttpError
from pipeline.util import utc_now_iso

DATE_PATTERNS = (
    re.compile(
        r'<meta[^>]+(?:property|name)="(?:article:published_time|datePublished)"[^>]+content="([^"]+)"',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta[^>]+content="([^"]+)"[^>]+(?:property|name)="(?:article:published_time|datePublished)"',
        re.IGNORECASE,
    ),
)


def normalize_text(value: str) -> str:
    """Normalize HTML and typography so a quote can be matched literally."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    for source, target in (
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u00a0", " "),
    ):
        text = text.replace(source, target)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def page_published_date(html_text: str) -> str | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(html_text)
        if not match:
            continue
        raw = match.group(1).strip()
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
                return raw[:10]
    return None


def load_ai_event_seeds(settings: Settings) -> list[dict[str, Any]]:
    config = settings.ai_events or {}
    return list(config.get("events", []))


def verify_event(client: CachedHttpClient, seed: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fetch the official page and return the event plus a list of failed checks."""
    required = ("id", "ticker", "title", "category", "published_date", "source_url", "evidence_quote")
    missing = [field for field in required if not seed.get(field)]
    if missing:
        raise ValueError(f"event seed missing fields: {', '.join(missing)}")

    response = client.get(seed["source_url"])
    body = normalize_text(response.text)
    quote = normalize_text(seed["evidence_quote"])
    page_date = page_published_date(response.text)

    failed: list[str] = []
    if quote not in body:
        failed.append("evidence_quote not found verbatim in the official page text")
    if page_date is None:
        failed.append("official page has no machine-readable published date")
    elif page_date != seed["published_date"]:
        failed.append(f"published date mismatch: page={page_date} seed={seed['published_date']}")

    event = {
        "id": seed["id"],
        "ticker": seed["ticker"],
        "title": seed["title"],
        "category": seed["category"],
        "label": "Reported",
        "published_date": seed["published_date"],
        "page_published_date": page_date,
        "source_url": seed["source_url"],
        "evidence_quote": seed["evidence_quote"],
        "content_sha256": response.sha256,
        "http_status": response.status,
        "fetched_at": response.fetched_at,
        "entered_by": seed.get("entered_by", "curated:config/ai_events.yaml"),
        "reviewed_by": seed.get("reviewed_by", "pipeline.ai_events.autoverify@1.0"),
        "review_method": seed.get("review_method", "automated_evidence_check"),
        "checks": {
            "quote_present": quote in body,
            "published_date_matches": page_date == seed["published_date"],
        },
        "review_status": "rejected" if failed else "verified",
        "reason": "; ".join(failed),
    }
    return event, failed


def build_verified_events(
    *,
    client: CachedHttpClient,
    seeds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for seed in seeds:
        try:
            event, failed = verify_event(client, seed)
        except (HttpError, ValueError, KeyError, TypeError) as exc:
            rejected.append(
                {
                    "id": seed.get("id"),
                    "source_url": seed.get("source_url"),
                    "reason": f"{type(exc).__name__}: {exc}",
                    "review_status": "rejected",
                }
            )
            continue
        if failed:
            rejected.append(event)
        else:
            verified.append(event)
    verified.sort(key=lambda event: event["published_date"])
    report = {
        "schema_version": "1.0",
        "checked_at": utc_now_iso(),
        "total_seeds": len(seeds),
        "verified": len(verified),
        "rejected": len(rejected),
        "events": verified,
        "rejects": rejected,
        "review_method": "automated_evidence_check",
        "note": (
            "Quote presence and page publication date are checked against the official page; "
            "this is a machine evidence check, not a human editorial review."
        ),
    }
    return verified, report
