from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.http import CachedHttpClient, sec_user_agent


class FakeResponse:
    status_code = 200
    headers = {"Content-Type": "application/json"}
    content = b'{"value":1}'


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = 0

    def get(self, url: str, timeout: int):
        self.calls += 1
        return FakeResponse()


def test_client_reuses_cache_within_max_age(tmp_path: Path):
    session = FakeSession()
    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        user_agent="test",
        session=session,
    )
    url = "https://data.sec.gov/test.json"

    client.get(url)
    client.get(url, max_age_seconds=3600)

    assert session.calls == 1


def test_client_refetches_expired_cache(tmp_path: Path):
    session = FakeSession()
    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        user_agent="test",
        session=session,
    )
    url = "https://data.sec.gov/test.json"
    client.get(url)
    client._index[url]["fetched_at"] = "2000-01-01T00:00:00Z"

    client.get(url, max_age_seconds=3600)

    assert session.calls == 2


def test_sec_user_agent_requires_project_contact(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    with pytest.raises(RuntimeError, match="real contact address"):
        sec_user_agent()


def test_sec_user_agent_uses_configured_value(monkeypatch: pytest.MonkeyPatch):
    # Build the fixture at runtime so no literal address is stored in the repo.
    contact = "@".join(["owner", "example.org"])
    value = f"AICOR research project (contact: {contact})"
    monkeypatch.setenv("SEC_USER_AGENT", value)

    assert sec_user_agent() == value
