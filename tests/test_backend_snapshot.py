"""Snapshot loading, dataset resolution, and freshness evaluation."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from backend.snapshot import (
    SnapshotStore,
    expected_checksum_matches,
    safe_relative_name,
)
from tests.helpers import write_dashboard_snapshot


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def test_load_reports_published_snapshot(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())

    snapshot = SnapshotStore(root).load()

    assert snapshot.available is True
    assert snapshot.version == "v20261106.5"
    assert snapshot.data_as_of == "2026-11-06"
    assert snapshot.run_id == "run_20261107T122003Z_test"
    assert snapshot.checksum_ok is True
    assert snapshot.problems == ()
    assert snapshot.files["financials"] == "financials.json"
    assert snapshot.files["prices/MSFT"] == "prices/MSFT.json"
    assert snapshot.age_seconds() is not None
    assert snapshot.age_seconds() < 60


def test_dataset_resolution_and_read(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    store = SnapshotStore(root)
    snapshot = store.load()

    resolved = snapshot.dataset("overview")
    assert resolved is not None
    name, path, checksum = resolved
    assert name == "overview.json"
    assert path == root / "overview.json"
    assert checksum is not None and checksum.startswith("sha256:")

    body = store.read_dataset(snapshot, "overview")
    assert body is not None
    assert json.loads(body)["kpis"] == []
    assert store.read_dataset(snapshot, "unknown") is None
    assert store.read_json(snapshot, "unknown") is None


def test_missing_manifest_is_unavailable(tmp_path):
    snapshot = SnapshotStore(tmp_path / "empty").load()

    assert snapshot.available is False
    assert snapshot.checksum_ok is False
    freshness = snapshot.freshness(3600)
    assert freshness["available"] is False
    assert freshness["age_seconds"] is None
    assert freshness["problems"] == ["manifest.json is missing"]


def test_corrupt_manifest_is_unavailable(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "manifest.json").write_text("{not json", encoding="utf-8")

    snapshot = SnapshotStore(root).load()

    assert snapshot.available is False
    assert any("unreadable" in problem for problem in snapshot.problems)


def test_tampered_dataset_fails_checksum(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    target = root / "financials.json"
    target.write_bytes(b'{"schema_version": "1.0", "quarters": [1, 2]}\n')

    snapshot = SnapshotStore(root).load()

    assert snapshot.available is True
    assert snapshot.checksum_ok is False
    assert any("financials.json" in problem for problem in snapshot.problems)
    integrity = snapshot.file_integrity("financials.json")
    assert integrity is not None
    assert integrity.exists is True
    assert integrity.matches is False


def test_tampered_dataset_read_is_refused(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    target = root / "overview.json"
    target.write_bytes(b'{"schema_version": "1.0", "kpis": [1]}\n')

    store = SnapshotStore(root)
    snapshot = store.load()

    assert snapshot.checksum_ok is False
    assert store.read_dataset(snapshot, "overview") is None
    assert store.read_json(snapshot, "overview") is None


def test_missing_dataset_file_is_reported(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    (root / "prices" / "MSFT.json").unlink()

    snapshot = SnapshotStore(root).load()

    assert snapshot.checksum_ok is False
    assert "prices/MSFT.json is missing" in snapshot.problems


def test_unsafe_manifest_entries_are_ignored(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["evil"] = "../outside.json"
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    snapshot = SnapshotStore(root).load()

    assert "evil" not in snapshot.files
    assert snapshot.dataset("evil") is None
    assert any("unsafe dataset entry: evil" in problem for problem in snapshot.problems)


def test_freshness_age_and_stale_window(tmp_path):
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    generated = (now - timedelta(hours=10)).isoformat().replace("+00:00", "Z")
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=generated)

    snapshot = SnapshotStore(root).load()

    stale = snapshot.freshness(21600, now=now)
    assert stale["age_seconds"] == 36000
    assert stale["stale"] is True
    assert stale["stale_after_seconds"] == 21600

    relaxed = snapshot.freshness(86400, now=now)
    assert relaxed["stale"] is False


def test_future_timestamp_is_not_negative(tmp_path):
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    generated = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=generated)

    snapshot = SnapshotStore(root).load()

    assert snapshot.age_seconds(now) == 0.0
    assert snapshot.freshness(3600, now=now)["stale"] is False


def test_unparseable_timestamp_reports_unknown_age(tmp_path):
    root = write_dashboard_snapshot(
        tmp_path / "data", generated_at="not-a-timestamp"
    )

    snapshot = SnapshotStore(root).load()

    assert snapshot.available is True
    assert snapshot.age_seconds() is None
    freshness = snapshot.freshness(3600)
    assert freshness["age_seconds"] is None
    # An unknown age cannot prove freshness, so the snapshot is stale.
    assert freshness["stale"] is True


def test_manifest_is_parsed_once_per_stat_signature(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    store = SnapshotStore(root)

    first = store.load()
    second = store.load()

    assert store.manifest_reads == 1
    assert first.version == second.version == "v20261106.5"
    assert first.manifest_bytes == second.manifest_bytes

    write_dashboard_snapshot(
        root, generated_at=_now(), snapshot_version="v20261108.1"
    )
    manifest_path = root / "manifest.json"
    future = os.stat(manifest_path).st_mtime + 5
    os.utime(manifest_path, (future, future))

    third = store.load()

    assert store.manifest_reads == 2
    assert third.version == "v20261108.1"


def test_paths_outside_the_data_directory_are_rejected(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    store = SnapshotStore(root)

    assert store._contained(tmp_path / "outside.json") is None
    assert store._contained(root / "financials.json") is not None


def test_symlinked_dataset_never_escapes_the_data_directory(tmp_path):
    root = write_dashboard_snapshot(tmp_path / "data", generated_at=_now())
    outside = tmp_path / "outside.json"
    outside.write_bytes(b'{"escaped": true}\n')
    link = root / "escape.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("this platform does not allow creating symlinks")

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["escape"] = "escape.json"
    manifest["checksums"]["escape.json"] = "sha256:" + hashlib.sha256(
        outside.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    store = SnapshotStore(root)
    snapshot = store.load()

    assert any("outside" in problem for problem in snapshot.problems)
    assert snapshot.checksum_ok is False
    assert store.dataset_entry(snapshot, "escape") is None
    assert store.read_dataset(snapshot, "escape") is None


def test_checksum_helpers_normalize_json_newlines():
    digest = hashlib.sha256(b"{}\n").hexdigest()

    assert expected_checksum_matches(b"{}\n", f"sha256:{digest}", "data.json")
    assert expected_checksum_matches(b"{}\r\n", f"sha256:{digest}", "data.json")
    assert expected_checksum_matches(b"{}\n", digest, "data.json")
    assert not expected_checksum_matches(b"{}\n", None, "data.json")
    assert not expected_checksum_matches(b"{}\n", "sha256:" + "0" * 64, "data.json")


def test_safe_relative_name_rejects_escapes():
    assert safe_relative_name("../outside.json") is None
    assert safe_relative_name("/etc/passwd") is None
    assert safe_relative_name("prices/../../manifest.json") is None
    assert safe_relative_name("") is None
    assert safe_relative_name(None) is None
    assert safe_relative_name("prices\\MSFT.json") == "prices/MSFT.json"
