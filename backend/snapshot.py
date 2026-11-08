"""Read the published dashboard snapshot and evaluate its freshness.

The backend is a consumer of ``web/public/data``: it never writes those files.
Every dataset it serves is checked against the SHA-256 recorded in
``manifest.json`` so a corrupt or half-published snapshot is refused instead of
shown as verified data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp as UTC; return ``None`` when unusable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_relative_name(name: Any) -> str | None:
    """Return a normalized relative path, or ``None`` for an unsafe manifest entry."""
    if not isinstance(name, str) or not name.strip():
        return None
    if name.startswith(("/", "\\")):
        return None
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def content_checksum(body: bytes, name: str) -> str:
    """SHA-256 of served bytes, matching the acceptance-check CRLF rule for JSON."""
    content = body.replace(b"\r\n", b"\n") if name.lower().endswith(".json") else body
    return hashlib.sha256(content).hexdigest()


def expected_digest(expected: str | None) -> str | None:
    if not expected:
        return None
    _, _, digest = str(expected).partition("sha256:")
    digest = digest or str(expected)
    return digest.strip().lower() or None


def expected_checksum_matches(body: bytes, expected: str | None, name: str) -> bool:
    digest = expected_digest(expected)
    if digest is None:
        return False
    return content_checksum(body, name) == digest


def file_checksum_matches(path: Path, expected: str | None, name: str) -> bool:
    digest = expected_digest(expected)
    if digest is None:
        return False
    try:
        return content_checksum(path.read_bytes(), name) == digest
    except OSError:
        return False


@dataclass(frozen=True)
class _ManifestCache:
    """Parsed, stat-keyed manifest content (integrity is never cached here)."""

    manifest_bytes: bytes
    manifest: dict[str, Any]
    files: dict[str, str]
    checksums: dict[str, str]
    version: str | None
    run_id: str | None
    generated_at: str | None
    data_as_of: str | None
    problems: tuple[str, ...]

    @classmethod
    def from_manifest(
        cls, manifest_bytes: bytes, manifest: dict[str, Any]
    ) -> "_ManifestCache":
        files: dict[str, str] = {}
        problems: list[str] = []
        raw_files = manifest.get("files")
        if isinstance(raw_files, dict):
            for key, name in raw_files.items():
                safe_name = safe_relative_name(name)
                if safe_name is None:
                    problems.append(f"unsafe dataset entry: {key}")
                    continue
                files[str(key)] = safe_name
        else:
            problems.append("manifest.json has no file index")

        checksums: dict[str, str] = {}
        raw_checksums = manifest.get("checksums")
        if isinstance(raw_checksums, dict):
            for name, checksum in raw_checksums.items():
                safe_name = safe_relative_name(name)
                if safe_name is not None and isinstance(checksum, str):
                    checksums[safe_name] = checksum

        return cls(
            manifest_bytes=manifest_bytes,
            manifest=manifest,
            files=files,
            checksums=checksums,
            version=_text(manifest.get("snapshot_version")),
            run_id=_text(manifest.get("run_id")),
            generated_at=_text(manifest.get("generated_at")),
            data_as_of=_text(manifest.get("data_as_of")),
            problems=tuple(problems),
        )


@dataclass(frozen=True)
class FileIntegrity:
    name: str
    exists: bool
    matches: bool
    size: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "exists": self.exists,
            "matches": self.matches,
            "size": self.size,
        }


@dataclass(frozen=True)
class Snapshot:
    """Immutable view of one published snapshot."""

    data_dir: Path
    available: bool = False
    manifest: dict[str, Any] = field(default_factory=dict)
    manifest_bytes: bytes = b""
    version: str | None = None
    run_id: str | None = None
    generated_at: str | None = None
    data_as_of: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    checksums: dict[str, str] = field(default_factory=dict)
    integrity: tuple[FileIntegrity, ...] = ()
    integrity_ok: bool = False
    problems: tuple[str, ...] = ()
    signature: tuple[int, int] | None = None

    @property
    def checksum_ok(self) -> bool:
        return self.available and self.integrity_ok

    def dataset(self, key: str) -> tuple[str, Path, str | None] | None:
        """Resolve a manifest dataset key (or raw filename) to a path."""
        name = self.files.get(key)
        if name is None and key in self.checksums:
            name = key
        if name is None:
            return None
        return name, self.data_dir / name, self.checksums.get(name)

    def age_seconds(self, now: datetime | None = None) -> float | None:
        generated = parse_timestamp(self.generated_at)
        if generated is None:
            return None
        reference = now or datetime.now(timezone.utc)
        return max(0.0, (reference - generated).total_seconds())

    def freshness(
        self, stale_after_seconds: int, now: datetime | None = None
    ) -> dict[str, Any]:
        age = self.age_seconds(now)
        # A missing or unparseable generated_at cannot prove freshness. Treat
        # it as stale so health degrades and the scheduler can recover.
        stale = bool(
            self.available
            and (age is None or age > max(0, int(stale_after_seconds)))
        )
        return {
            "available": self.available,
            "snapshot_version": self.version,
            "data_as_of": self.data_as_of,
            "generated_at": self.generated_at,
            "run_id": self.run_id,
            "age_seconds": None if age is None else int(age),
            "stale": stale,
            "stale_after_seconds": int(stale_after_seconds),
            "checksum_ok": self.checksum_ok,
            "file_count": len(self.files),
            "problems": list(self.problems),
        }

    def file_integrity(self, name: str) -> FileIntegrity | None:
        for item in self.integrity:
            if item.name == name:
                return item
        return None


def snapshot_event(freshness: dict[str, Any], *, changed: bool) -> dict[str, Any]:
    """Build the canonical SSE ``snapshot`` payload.

    Both the refresh runner and the freshness scheduler emit this shape so a
    browser can always read ``payload.snapshot`` regardless of the producer.
    """
    return {"snapshot": freshness, "changed": bool(changed)}


class SnapshotStore:
    """Load and cache snapshot metadata for the published dashboard directory."""

    def __init__(self, data_dir: Path, *, max_cache_entries: int = 256) -> None:
        self.data_dir = Path(data_dir)
        self._root = self.data_dir.resolve()
        self._max_cache_entries = max(1, max_cache_entries)
        self._integrity_cache: dict[tuple[str, int, int], bool] = {}
        # Parsed manifest is cached by stat signature; integrity is always
        # revalidated so a dataset tampered in place is still refused.
        self._manifest_key: tuple[int, int] | None = None
        self._manifest_value: _ManifestCache | None = None
        self._manifest_reads = 0

    @property
    def manifest_reads(self) -> int:
        """How many times the manifest body was read (cache observability)."""
        return self._manifest_reads

    def load(self) -> Snapshot:
        manifest_path = self.data_dir / MANIFEST_NAME
        try:
            stat = manifest_path.stat()
        except OSError:
            self._manifest_key = None
            self._manifest_value = None
            return Snapshot(
                data_dir=self.data_dir,
                problems=("manifest.json is missing",),
            )

        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self._manifest_value if signature == self._manifest_key else None
        if cached is None:
            try:
                manifest_bytes = manifest_path.read_bytes()
                self._manifest_reads += 1
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except (OSError, ValueError) as error:
                self._manifest_key = signature
                self._manifest_value = None
                return Snapshot(
                    data_dir=self.data_dir,
                    problems=(
                        f"manifest.json is unreadable: {type(error).__name__}",
                    ),
                    signature=signature,
                )

            if not isinstance(manifest, dict):
                self._manifest_key = signature
                self._manifest_value = None
                return Snapshot(
                    data_dir=self.data_dir,
                    problems=("manifest.json must contain an object",),
                    signature=signature,
                )

            cached = _ManifestCache.from_manifest(manifest_bytes, manifest)
            self._manifest_key = signature
            self._manifest_value = cached

        files = dict(cached.files)
        checksums = dict(cached.checksums)
        problems: list[str] = list(cached.problems)

        integrity: list[FileIntegrity] = []
        seen: set[str] = set()
        for name in files.values():
            if name in seen:
                continue
            seen.add(name)
            integrity.append(self._check_file(name, checksums.get(name), problems))

        if not integrity:
            problems.append("manifest.json lists no servable datasets")

        return Snapshot(
            data_dir=self.data_dir,
            available=True,
            manifest=dict(cached.manifest),
            manifest_bytes=cached.manifest_bytes,
            version=cached.version,
            run_id=cached.run_id,
            generated_at=cached.generated_at,
            data_as_of=cached.data_as_of,
            files=files,
            checksums=checksums,
            integrity=tuple(integrity),
            integrity_ok=not any(
                not item.exists or not item.matches for item in integrity
            ),
            problems=tuple(problems),
            signature=signature,
        )

    def dataset_entry(
        self, snapshot: Snapshot, key: str
    ) -> tuple[str, Path, str | None] | None:
        """Resolve a dataset key to a path that stays inside ``data_dir``."""
        resolved = snapshot.dataset(key)
        if resolved is None:
            return None
        name, path, expected = resolved
        contained = self._contained(path)
        if contained is None:
            return None
        return name, contained, expected

    def read_dataset(self, snapshot: Snapshot, key: str) -> bytes | None:
        """Read a dataset that is listed in the manifest and matches its checksum."""
        resolved = self.dataset_entry(snapshot, key)
        if resolved is None:
            return None
        name, path, expected = resolved
        try:
            body = path.read_bytes()
        except OSError:
            return None
        if not expected_checksum_matches(body, expected, name):
            return None
        return body

    def _contained(self, path: Path) -> Path | None:
        """Return the resolved path when it is inside the data directory."""
        try:
            candidate = Path(path).resolve()
            candidate.relative_to(self._root)
        except (OSError, ValueError):
            return None
        return candidate

    def read_json(self, snapshot: Snapshot, key: str) -> Any | None:
        body = self.read_dataset(snapshot, key)
        if body is None:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            return None

    def _check_file(
        self, name: str, expected: str | None, problems: list[str]
    ) -> FileIntegrity:
        path = self._contained(self.data_dir / name)
        if path is None:
            problems.append(f"{name} resolves outside the data directory")
            return FileIntegrity(name=name, exists=True, matches=False)
        try:
            stat = path.stat()
        except OSError:
            problems.append(f"{name} is missing")
            return FileIntegrity(name=name, exists=False, matches=False)

        if expected is None:
            problems.append(f"{name} has no manifest checksum")
            return FileIntegrity(
                name=name, exists=True, matches=False, size=stat.st_size
            )

        cache_key = (str(path), stat.st_mtime_ns, stat.st_size)
        matches = self._integrity_cache.get(cache_key)
        if matches is None:
            matches = file_checksum_matches(path, expected, name)
            self._remember(cache_key, matches)
        if not matches:
            problems.append(f"{name} does not match its manifest checksum")
        return FileIntegrity(
            name=name, exists=True, matches=matches, size=stat.st_size
        )

    def _remember(self, key: tuple[str, int, int], value: bool) -> None:
        if len(self._integrity_cache) >= self._max_cache_entries:
            self._integrity_cache.clear()
        self._integrity_cache[key] = value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
