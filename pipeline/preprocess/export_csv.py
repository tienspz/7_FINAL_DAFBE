"""Export record arrays from dashboard JSON files as Excel-friendly CSV tables."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Iterator

from pipeline.util import atomic_write_text, read_json, write_json

_MANIFEST_NAME = "_manifest.json"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


def _tables(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], list[dict[str, Any]]]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            if isinstance(child, list) and child and all(isinstance(row, dict) for row in child):
                yield child_path, child
            else:
                yield from _tables(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _tables(child, (*path, str(index)))


def _flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def visit(value: dict[str, Any], prefix: str = "") -> None:
        for key, child in value.items():
            column = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, dict):
                visit(child, column)
            elif isinstance(child, list):
                flattened[column] = json.dumps(child, ensure_ascii=False, separators=(",", ":"))
            else:
                flattened[column] = child

    visit(record)
    return flattened


def _csv_text(rows: list[dict[str, Any]], ticker: Any = None) -> str:
    flattened_rows: list[dict[str, Any]] = []
    fieldnames: list[str] = []
    for row in rows:
        flattened = _flatten_record(row)
        if ticker is not None:
            flattened.setdefault("ticker", ticker)
        if "ticker" in flattened:
            flattened = {"ticker": flattened.pop("ticker"), **flattened}
        flattened_rows.append(flattened)
        for name in flattened:
            if name not in fieldnames:
                fieldnames.append(name)

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in flattened_rows:
        safe_row = {
            key: ("'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
            for key, value in row.items()
        }
        writer.writerow(safe_row)
    return "\ufeff" + buffer.getvalue()


def _output_path(source_relative: Path, table_path: tuple[str, ...]) -> Path:
    safe_table = "__".join(_SAFE_NAME.sub("_", part).strip("_") for part in table_path)
    if not safe_table:
        safe_table = "rows"
    return source_relative.with_name(f"{source_relative.stem}__{safe_table}.csv")


def export_json_tables_to_csv(source_dir: Path, output_dir: Path) -> list[str]:
    """Write all non-empty arrays of records under source_dir to output_dir."""
    source_dir = source_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / _MANIFEST_NAME
    previous_manifest = read_json(manifest_path) if manifest_path.exists() else {}
    if not isinstance(previous_manifest, dict):
        raise ValueError(f"Invalid generated-file manifest: {manifest_path}")
    previous_files = previous_manifest.get("generated_files", [])
    if not isinstance(previous_files, list) or not all(isinstance(name, str) for name in previous_files):
        raise ValueError(f"Invalid generated-file manifest: {manifest_path}")

    generated: dict[str, str] = {}
    for source_path in sorted(source_dir.rglob("*.json")):
        document = read_json(source_path)
        if not isinstance(document, (dict, list)):
            continue
        source_relative = source_path.relative_to(source_dir)
        ticker = document.get("ticker") if isinstance(document, dict) else None
        for table_path, rows in _tables(document):
            relative_output = _output_path(source_relative, table_path)
            relative_name = relative_output.as_posix()
            if relative_name in generated:
                raise ValueError(f"Multiple JSON tables map to the same CSV: {relative_name}")
            generated[relative_name] = _csv_text(rows, ticker=ticker)

    for relative_name, content in generated.items():
        output_path = output_dir / Path(relative_name)
        atomic_write_text(output_path, content)

    generated_names = sorted(generated)
    for old_name in previous_files:
        old_relative = Path(old_name)
        if old_relative.is_absolute() or ".." in old_relative.parts or old_relative.suffix.lower() != ".csv":
            raise ValueError(f"Invalid generated CSV path in manifest: {old_name}")
        if old_name not in generated_names:
            stale_path = output_dir / old_relative
            if stale_path.is_file():
                stale_path.unlink()

    write_json(manifest_path, {"generated_files": generated_names})
    return generated_names
