"""Guard against personal data leaking into generated, tracked artifacts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SCAN_PATHS = [
    ROOT / "docs" / "evidence",
    ROOT / "data" / "verified",
    ROOT / "data" / "raw",
    ROOT / "web" / "public" / "data",
    ROOT / "DataProcessedView",
    ROOT / "config",
    ROOT / "README.md",
]
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".zip",
    ".gz",
    ".sqlite",
}


def _text_files(path: Path):
    if path.is_file():
        if path.suffix.lower() not in SKIP_SUFFIXES:
            yield path
        return
    for candidate in path.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() not in SKIP_SUFFIXES:
            yield candidate


def _masked(value: str) -> str:
    local, _, domain = value.partition("@")
    domain_parts = domain.split(".")
    return (
        (local[:2] + "***" if len(local) > 2 else "***")
        + "@"
        + (domain_parts[0][:1] + "***" if domain_parts and domain_parts[0] else "***")
        + (("." + domain_parts[-1]) if len(domain_parts) > 1 else "")
    )


def test_no_email_addresses_in_generated_outputs() -> None:
    offenders: list[str] = []
    for root in SCAN_PATHS:
        for path in _text_files(root):
            try:
                if path.stat().st_size > 8_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in EMAIL_PATTERN.finditer(text):
                offenders.append(
                    f"{path.relative_to(ROOT).as_posix()}: {_masked(match.group(0))}"
                )
    assert not offenders, "Email-like values found in generated artifacts: " + "; ".join(
        offenders[:20]
    )


def test_acceptance_environment_does_not_store_user_agent_value() -> None:
    path = ROOT / "docs" / "evidence" / "acceptance_2026-11-06.json"
    if not path.exists():
        return
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    environment = payload.get("environment", {})
    assert "sec_user_agent_configured" in environment
    assert "sec_user_agent" not in environment
    assert "user_agent" not in environment
