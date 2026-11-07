"""Diagnose the two MSFT R&D lag-2 BT4 results.

The script reads the verified snapshot already on disk and re-runs only the
correlation block with the reviewed statistics. It does not fetch SEC data and
does not write the production tests.json; use the pipeline for that.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.stats.tests import _apply_correlation_holm, _correlation_family

ROOT = Path(__file__).resolve().parents[1]
FINANCIALS = ROOT / "web" / "public" / "data" / "financials.json"
MANIFEST = ROOT / "web" / "public" / "data" / "manifest.json"
EVIDENCE = ROOT / "docs" / "evidence" / "bt4_diagnostics.json"


class Metric:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.value = payload.get("value")
        self.unit = payload.get("unit", "")
        self.quality_flag = payload.get("quality_flag", "missing")
        self.derived = bool(payload.get("derived", False))
        self.derivation_method = payload.get("derivation_method")
        self.components = payload.get("components", [])


def load_rows() -> list[dict[str, Any]]:
    payload = json.loads(FINANCIALS.read_text(encoding="utf-8"))
    rows = []
    for row in payload["quarters"]:
        if row.get("ticker") != "MSFT":
            continue
        rows.append(
            {
                "ticker": row["ticker"],
                "calendar_key": row["calendar_key"],
                "period_end": row["period_end"],
                "fiscal_year": row["fiscal_year"],
                "fiscal_quarter": row["fiscal_quarter"],
                "metrics": {
                    name: Metric(metric) for name, metric in row.get("metrics", {}).items()
                },
                "derived": row.get("derived_metrics", {}),
            }
        )
    return sorted(rows, key=lambda item: item["calendar_key"])


def main() -> int:
    rows = load_rows()
    common = {
        "bt_code": "BT4",
        "rows_by_ticker": {"MSFT": rows},
        "max_lag": 4,
        "alpha": 0.05,
        "quality_mode": "label_low",
        "fragility_max_n": 15,
        "permutation_iterations": 10000,
        "permutation_seed": 20261107,
    }
    results = _correlation_family(
        x_field="rd_growth_yoy",
        y_fields=["revenue_growth_yoy", "fcf_growth_yoy", "operating_margin"],
        **common,
    )
    results += _correlation_family(
        x_field="capex_growth_yoy",
        y_fields=["revenue_growth_yoy", "fcf_growth_yoy", "operating_margin"],
        **common,
    )
    _apply_correlation_holm(results, alpha=0.05, primary="bt", max_lag=4)
    selected = [
        item
        for item in results
        if item["ticker"] == "MSFT" and item["x"] == "rd_growth_yoy" and item["lag"] == 2
        and item["y"] in {"revenue_growth_yoy", "fcf_growth_yoy"}
    ]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload = {
        "source": "web/public/data/financials.json",
        "snapshot_version": manifest.get("snapshot_version"),
        "data_as_of": manifest.get("data_as_of"),
        "method": "reviewed BT4 correlation block; no live SEC fetch",
        "rows": selected,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    headers = [
        "y",
        "n_eff",
        "rho_main",
        "rho_level",
        "rho_diff",
        "p_raw",
        "p_adj_lag",
        "p_adj_bt",
        "fragile",
        "decision",
    ]
    print(" | ".join(headers))
    for item in selected:
        print(
            " | ".join(
                str(value)
                for value in (
                    item["y"],
                    item["n_effective"],
                    item["statistic"],
                    item.get("level_rho"),
                    item.get("difference_rho"),
                    item["p_value"],
                    item.get("p_adj_lag_family"),
                    item.get("p_adj_bt_family"),
                    item.get("fragile"),
                    item["decision"],
                )
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
