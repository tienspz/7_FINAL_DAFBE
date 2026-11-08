import csv
import json
from pathlib import Path

from pipeline.preprocess.export_csv import export_json_tables_to_csv


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_exports_record_arrays_with_flattened_fields_and_ticker(tmp_path: Path):
    source_dir = tmp_path / "web_data"
    output_dir = tmp_path / "DataProcessedView"
    source_dir.mkdir()
    (source_dir / "financials.json").write_text(
        json.dumps(
            {
                "ticker": "GOOGL",
                "quarters": [
                    {"calendar_key": "2026-Q1", "metrics": {"revenue": 100, "margin": 0.2}},
                    {"calendar_key": "2026-Q2", "metrics": {"revenue": 120, "margin": 0.25}},
                ],
            }
        ),
        encoding="utf-8",
    )

    generated = export_json_tables_to_csv(source_dir, output_dir)

    assert generated == ["financials__quarters.csv"]
    rows = _read_csv(output_dir / "financials__quarters.csv")
    assert rows == [
        {"ticker": "GOOGL", "calendar_key": "2026-Q1", "metrics.revenue": "100", "metrics.margin": "0.2"},
        {"ticker": "GOOGL", "calendar_key": "2026-Q2", "metrics.revenue": "120", "metrics.margin": "0.25"},
    ]


def test_refreshes_csv_and_removes_only_stale_generated_files(tmp_path: Path):
    source_dir = tmp_path / "web_data"
    output_dir = tmp_path / "DataProcessedView"
    source_dir.mkdir()
    source_path = source_dir / "prices" / "GOOGL.json"
    source_path.parent.mkdir()
    source_path.write_text(json.dumps({"ticker": "GOOGL", "rows": [{"date": "2026-01-01", "close": 10}]}))

    export_json_tables_to_csv(source_dir, output_dir)
    csv_path = output_dir / "prices" / "GOOGL__rows.csv"
    assert _read_csv(csv_path)[0]["close"] == "10"

    source_path.write_text(json.dumps({"ticker": "GOOGL", "rows": [{"date": "2026-01-01", "close": 11}]}))
    (output_dir / "keep.csv").write_text("user-owned\n", encoding="utf-8")
    assert export_json_tables_to_csv(source_dir, output_dir) == ["prices/GOOGL__rows.csv"]
    assert _read_csv(csv_path)[0]["close"] == "11"
    assert (output_dir / "keep.csv").exists()

    source_path.unlink()
    assert export_json_tables_to_csv(source_dir, output_dir) == []
    assert not csv_path.exists()
    assert (output_dir / "keep.csv").exists()


def test_escapes_excel_formula_strings_and_serializes_list_cells(tmp_path: Path):
    source_dir = tmp_path / "web_data"
    output_dir = tmp_path / "DataProcessedView"
    source_dir.mkdir()
    (source_dir / "events.json").write_text(
        json.dumps({"events": [{"title": "=HYPERLINK(\"https://example.com\")", "tags": ["AI", "Cloud"]}]})
    )

    export_json_tables_to_csv(source_dir, output_dir)
    rows = _read_csv(output_dir / "events__events.csv")

    assert rows[0]["title"] == '\'=HYPERLINK("https://example.com")'
    assert rows[0]["tags"] == '["AI","Cloud"]'
