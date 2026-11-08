import json
from pathlib import Path

import pytest

from pipeline.config import load_yaml
from scripts.rebuild_stats import build_statistics_snapshot, refresh_snapshot


ROOT = Path(__file__).resolve().parents[1]


def quick_thresholds():
    thresholds = load_yaml("thresholds.yaml")
    thresholds["stats"]["permutation_iterations"] = 20
    thresholds["stats"]["bt3_bootstrap_iterations"] = 20
    return thresholds


def test_offline_refresh_repairs_checked_in_statistics_contract(tmp_path):
    source = ROOT / "web" / "public" / "data"
    for name in ("manifest.json", "financials.json", "investor.json"):
        (tmp_path / name).write_bytes((source / name).read_bytes())

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    result = build_statistics_snapshot(tmp_path, quick_thresholds())

    assert result["snapshot_version"] == manifest["snapshot_version"]
    assert result["generated_at"] == manifest["generated_at"]
    assert result["schema_version"] == "1.2"
    assert result["quality_mode"] == "label_low"
    assert result["quality_mode_primary"] == "B"
    assert len(result["results"]) == 79
    assert len(result["quality_mode_comparison"]) == 77
    assert all(
        row.get("p_value_raw") is not None and row.get("p_value_display") is not None
        for row in result["results"]
        if row.get("p_value") is not None
    )


def test_offline_refresh_updates_both_manifests_and_is_repeatable(tmp_path, monkeypatch):
    source = ROOT / "web" / "public" / "data"
    for name in ("manifest.json", "financials.json", "investor.json"):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    verified_dir = tmp_path / "verified"
    verified_dir.mkdir()
    (verified_dir / "manifest.json").write_bytes((source / "manifest.json").read_bytes())
    from scripts import rebuild_stats

    monkeypatch.setattr(
        rebuild_stats,
        "build_statistics_snapshot",
        lambda *_args, **_kwargs: {
            "schema_version": "1.2",
            "snapshot_version": "v20261106.3",
            "generated_at": "2026-11-07T07:45:34Z",
            "results": [],
        },
    )

    first = refresh_snapshot(tmp_path, verified_dir, quick_thresholds())
    first_stats = (tmp_path / "tests.json").read_bytes()
    first_manifest = (tmp_path / "manifest.json").read_bytes()
    second = refresh_snapshot(tmp_path, verified_dir, quick_thresholds())

    assert first["checksums"] == second["checksums"]
    assert (tmp_path / "tests.json").read_bytes() == first_stats
    assert (tmp_path / "manifest.json").read_bytes() == first_manifest
    assert json.loads((verified_dir / "manifest.json").read_text(encoding="utf-8")) == second


def test_offline_refresh_rejects_mixed_snapshot_inputs(tmp_path):
    source = ROOT / "web" / "public" / "data"
    for name in ("manifest.json", "financials.json", "investor.json"):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    investor_path = tmp_path / "investor.json"
    investor = json.loads(investor_path.read_text(encoding="utf-8"))
    investor["snapshot_version"] = "stale"
    investor_path.write_text(json.dumps(investor), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        build_statistics_snapshot(tmp_path)
