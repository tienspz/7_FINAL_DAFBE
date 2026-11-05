"""Small shared helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def json_safe(value: Any) -> Any:
    """Convert numpy/pandas scalars into plain JSON-compatible values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        try:
            return json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return json_safe(value.tolist())
        except (TypeError, ValueError):
            pass
    return str(value)


def sha256_json(value: Any) -> str:
    return sha256_text(
        json.dumps(json_safe(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def quarter_key(value: date | str) -> str:
    if isinstance(value, str):
        value = parse_date(value)
    if value is None:
        raise ValueError("Cannot derive a quarter from an empty date")
    return f"{value.year}-Q{((value.month - 1) // 3) + 1}"


def quarter_start(key: str) -> date:
    year, q = key.split("-Q")
    month = (int(q) - 1) * 3 + 1
    return date(int(year), month, 1)


def quarter_end(key: str) -> date:
    start = quarter_start(key)
    if start.month == 10:
        return date(start.year, 12, 31)
    if start.month == 7:
        return date(start.year, 9, 30)
    if start.month == 4:
        return date(start.year, 6, 30)
    return date(start.year, 3, 31)


def iter_quarters(start_year: int, start_quarter: int, end_year: int, end_quarter: int) -> list[str]:
    out: list[str] = []
    year, q = start_year, start_quarter
    while (year, q) <= (end_year, end_quarter):
        out.append(f"{year}-Q{q}")
        q += 1
        if q == 5:
            year += 1
            q = 1
    return out


def fiscal_info(ticker: str, period_end: date) -> tuple[int, str]:
    """Return (fiscal_year, fiscal_quarter) for a period end date.

    MSFT has a June fiscal year end; GOOGL uses the calendar year.
    """
    if ticker.upper() == "MSFT":
        month = period_end.month
        if month >= 7:
            return period_end.year + 1, {7: "Q1", 8: "Q1", 9: "Q1", 10: "Q2", 11: "Q2", 12: "Q2"}[month]
        return period_end.year, {1: "Q3", 2: "Q3", 3: "Q3", 4: "Q4", 5: "Q4", 6: "Q4"}[month]
    return period_end.year, f"Q{((period_end.month - 1) // 3) + 1}"


def duration_days(start: date | None, end: date | None) -> int | None:
    if start is None or end is None:
        return None
    return (end - start).days + 1


def to_million(value: float | None) -> float | None:
    return None if value is None else round(value / 1_000_000.0, 3)


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def clean_member(value: str) -> str:
    return value.split(":")[-1]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Pin LF so Windows local runs and the Linux CI bot produce identical files.
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def write_json(path: Path, value: Any) -> None:
    payload = json.dumps(json_safe(value), ensure_ascii=False, indent=2, sort_keys=False)
    atomic_write_text(path, payload + "\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_accession(accession: str) -> str:
    return re.sub(r"[^0-9]", "", accession)
