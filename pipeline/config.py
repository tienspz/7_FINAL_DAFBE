"""Configuration loading and project paths."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
VERIFIED_DIR = DATA_DIR / "verified"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
DB_DIR = DATA_DIR / "db"
WEB_DATA_DIR = PROJECT_ROOT / "web" / "public" / "data"


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config {path} must contain a mapping")
    return data


@dataclass(frozen=True)
class Settings:
    concept_map: dict[str, Any]
    segment_map: dict[str, Any]
    source_registry: dict[str, Any]
    allowlist: dict[str, Any]
    thresholds: dict[str, Any]
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    raw_dir: Path = RAW_DIR
    verified_dir: Path = VERIFIED_DIR
    snapshot_dir: Path = SNAPSHOT_DIR
    web_data_dir: Path = WEB_DATA_DIR

    @property
    def allowed_domains(self) -> list[str]:
        return list(self.allowlist.get("allowed_domains", []))

    @property
    def companies(self) -> dict[str, Any]:
        return self.concept_map["companies"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        concept_map=load_yaml("concept_map.yaml"),
        segment_map=load_yaml("segment_map.yaml"),
        source_registry=load_yaml("source_registry.yaml"),
        allowlist=load_yaml("allowlist.yaml"),
        thresholds=load_yaml("thresholds.yaml"),
    )
