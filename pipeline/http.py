"""HTTP client with CR-13 allowlist enforcement, append-only SHA-256 cache, and polite retries."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from pipeline.util import sha256_bytes, utc_now_iso


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int | None, message: str):
        self.url = url
        self.status = status
        super().__init__(f"{url}: {message}")


class AllowlistError(RuntimeError):
    """Raised when a crawler tries to call a domain outside the CR-13 allowlist."""

    def __init__(self, url: str, domain: str):
        self.url = url
        self.domain = domain
        super().__init__(f"{url}: domain {domain!r} is not in the CR-13 allowlist")


def url_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def domain_allowed(url: str, allowed_domains: Sequence[str]) -> bool:
    """True when the URL host equals or is a subdomain of an allowlisted domain.

    Entries without a dot (for example the ``yfinance`` library marker) are not
    domain names and can never match a host.
    """
    host = url_host(url)
    if not host:
        return False
    for entry in allowed_domains:
        domain = str(entry).strip().lower().lstrip(".")
        if "." not in domain:
            continue
        if host == domain or host.endswith("." + domain):
            return True
    return False


@dataclass
class HttpResponse:
    url: str
    status: int
    content_type: str
    content: bytes
    sha256: str
    fetched_at: str
    from_cache: bool = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content)


class CachedHttpClient:
    """Fetch URLs, store every response body by SHA-256, and reuse cache.

    The cache is append-only: `_index.jsonl` maps each URL to its latest
    known content hash. Existing cache files are never modified.

    When ``enforce_allowlist`` is true every request must target an allowlisted
    domain; ``get(..., allow_unlisted=True)`` is reserved for documented
    negative controls that must probe rejected sources.
    """

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        min_delay_seconds: float = 0.2,
        timeout_seconds: int = 90,
        session: requests.Session | None = None,
        allowed_domains: Sequence[str] | None = None,
        enforce_allowlist: bool = False,
        redact_query_keys: Sequence[str] = (),
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = cache_dir / "_index.jsonl"
        self.user_agent = user_agent
        self.min_delay_seconds = min_delay_seconds
        self.timeout_seconds = timeout_seconds
        self.allowed_domains = [str(domain) for domain in (allowed_domains or [])]
        self.enforce_allowlist = enforce_allowlist
        self.redact_query_keys = tuple(key.lower() for key in redact_query_keys)
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, text/html, application/xml, text/xml, */*",
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_request_at = 0.0
        self._index: dict[str, dict[str, Any]] = {}
        self._load_index()

    def _load_index(self) -> None:
        if not self.index_path.exists():
            return
        with self.index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("url"):
                    self._index[row["url"]] = row

    def _append_index(self, row: dict[str, Any]) -> None:
        with self.index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def _storage_url(self, url: str) -> str:
        """Mask secret query parameters before caching, logging, or reporting."""
        if not self.redact_query_keys:
            return url
        parts = urlsplit(url)
        if not parts.query:
            return url
        masked = [
            (key, "REDACTED" if key.lower() in self.redact_query_keys else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(masked), parts.fragment))

    def _assert_allowed(self, url: str, *, allow_unlisted: bool) -> None:
        if not self.enforce_allowlist or allow_unlisted:
            return
        if not domain_allowed(url, self.allowed_domains):
            raise AllowlistError(url, url_host(url))

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_delay_seconds:
            time.sleep(self.min_delay_seconds - elapsed)

    def get(
        self,
        url: str,
        *,
        refresh: bool = False,
        timeout_seconds: int | None = None,
        allow_unlisted: bool = False,
    ) -> HttpResponse:
        self._assert_allowed(url, allow_unlisted=allow_unlisted)
        storage_url = self._storage_url(url)
        cached = self._index.get(storage_url)
        if cached and not refresh:
            path = self.cache_dir / cached["sha256"]
            if path.exists():
                content = path.read_bytes()
                return HttpResponse(
                    url=storage_url,
                    status=int(cached.get("status", 200)),
                    content_type=cached.get("content_type", ""),
                    content=content,
                    sha256=cached["sha256"],
                    fetched_at=cached.get("fetched_at", ""),
                    from_cache=True,
                )

        last_error: Exception | None = None
        for attempt in range(3):
            self._wait()
            try:
                response = self.session.get(url, timeout=timeout_seconds or self.timeout_seconds)
                self._last_request_at = time.monotonic()
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    retry_after = response.headers.get("Retry-After")
                    sleep_for = float(retry_after) if retry_after and retry_after.isdigit() else (2**attempt)
                    time.sleep(max(sleep_for, 0.5))
                    last_error = HttpError(storage_url, response.status_code, "transient HTTP error")
                    continue
                if response.status_code >= 400:
                    raise HttpError(storage_url, response.status_code, f"HTTP {response.status_code}")
                content = response.content
                digest = sha256_bytes(content)
                fetched_at = utc_now_iso()
                path = self.cache_dir / digest
                if not path.exists():
                    path.write_bytes(content)
                row = {
                    "url": storage_url,
                    "sha256": digest,
                    "status": response.status_code,
                    "content_type": response.headers.get("Content-Type", ""),
                    "bytes": len(content),
                    "fetched_at": fetched_at,
                }
                self._append_index(row)
                self._index[storage_url] = row
                return HttpResponse(
                    url=storage_url,
                    status=response.status_code,
                    content_type=row["content_type"],
                    content=content,
                    sha256=digest,
                    fetched_at=fetched_at,
                )
            except HttpError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2**attempt)
        raise HttpError(storage_url, None, f"request failed after retries: {last_error}")

    def get_json(self, url: str, *, refresh: bool = False, allow_unlisted: bool = False) -> Any:
        return self.get(url, refresh=refresh, allow_unlisted=allow_unlisted).json()


def sec_user_agent() -> str:
    return os.environ.get(
        "SEC_USER_AGENT",
        "AICOR research project (student project; contact: aicor@example.com)",
    )
