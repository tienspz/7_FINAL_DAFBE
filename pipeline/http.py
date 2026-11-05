"""HTTP client with append-only SHA-256 response cache and polite retries."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from pipeline.util import sha256_bytes, utc_now_iso


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int | None, message: str):
        self.url = url
        self.status = status
        super().__init__(f"{url}: {message}")


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
    """

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        min_delay_seconds: float = 0.2,
        timeout_seconds: int = 90,
        session: requests.Session | None = None,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = cache_dir / "_index.jsonl"
        self.user_agent = user_agent
        self.min_delay_seconds = min_delay_seconds
        self.timeout_seconds = timeout_seconds
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

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_delay_seconds:
            time.sleep(self.min_delay_seconds - elapsed)

    def get(self, url: str, *, refresh: bool = False, timeout_seconds: int | None = None) -> HttpResponse:
        cached = self._index.get(url)
        if cached and not refresh:
            path = self.cache_dir / cached["sha256"]
            if path.exists():
                content = path.read_bytes()
                return HttpResponse(
                    url=url,
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
                    last_error = HttpError(url, response.status_code, "transient HTTP error")
                    continue
                if response.status_code >= 400:
                    raise HttpError(url, response.status_code, f"HTTP {response.status_code}")
                content = response.content
                digest = sha256_bytes(content)
                fetched_at = utc_now_iso()
                path = self.cache_dir / digest
                if not path.exists():
                    path.write_bytes(content)
                row = {
                    "url": url,
                    "sha256": digest,
                    "status": response.status_code,
                    "content_type": response.headers.get("Content-Type", ""),
                    "bytes": len(content),
                    "fetched_at": fetched_at,
                }
                self._append_index(row)
                self._index[url] = row
                return HttpResponse(
                    url=url,
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
        raise HttpError(url, None, f"request failed after retries: {last_error}")

    def get_json(self, url: str, *, refresh: bool = False) -> Any:
        return self.get(url, refresh=refresh).json()


def sec_user_agent() -> str:
    return os.environ.get(
        "SEC_USER_AGENT",
        "AICOR research project (student project; contact: aicor@example.com)",
    )
