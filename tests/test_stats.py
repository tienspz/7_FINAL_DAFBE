"""Statistical test helper tests."""

import json

import numpy as np
import pandas as pd

from pipeline.stats.tests import (
    _adf,
    _apply_correlation_holm,
    _correlation_family,
    _holm_family_size,
    _metric_identity_ok,
    _quality_problem,
    bt1_excess_returns,
    bt2_paired_growth,
    bt3_trend,
    holm_adjust,
    present_p_values,
    run_all_tests,
)
from pipeline.util import json_safe
from tests.helpers import make_metric


def test_holm_adjustment_is_monotone_and_bounded():
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == [0.03, 0.06, 0.06]
    assert holm_adjust([]) == []


def test_adf_result_is_json_serializable():
    series = pd.Series(np.linspace(1.0, 20.0, 20))
    result = _adf(series)
    json.dumps(result)
    if result["stationary"] is not None:
        assert isinstance(result["stationary"], bool)


def test_json_safe_converts_numpy_scalars():
    assert json_safe(np.bool_(True)) is True
    assert json_safe(np.float64(1.5)) == 1.5
    assert json_safe(np.int64(7)) == 7
    assert json_safe(np.array([1, 2])) == [1, 2]
    assert json_safe(float("nan")) is None


def test_bt1_excess_return_family():
    dates = [f"2025-{month:02d}-28" for month in range(1, 13)]
    analytics = {
        "MSFT": {"monthly_returns": [{"trade_date": d, "return": 0.02} for d in dates]},
        "SPY": {"monthly_returns": [{"trade_date": d, "return": 0.01} for d in dates]},
    }
    results = bt1_excess_returns(price_analytics=analytics, tickers=["MSFT"], benchmark="SPY", alpha=0.05)
    assert len(results) == 1
    assert results[0]["n"] == 12
    assert results[0]["mean_excess_return"] > 0
    assert results[0]["bt_code"] == "BT1"


def make_rows(values, *, capex_quality="ok"):
    keys = [f"{2022 + index // 4}-Q{index % 4 + 1}" for index in range(len(values))]
    rows = []
    for index, (key, value) in enumerate(zip(keys, values)):
        rows.append(
            {
                "ticker": "MSFT",
                "calendar_key": key,
                "metrics": {
                    "revenue": make_metric(1000.0 + index),
                    "operating_income": make_metric(200.0 + index),
                    "net_income": make_metric(100.0 + index),
                    "rd_expense": make_metric(50.0 + index),
                    "capex": make_metric(40.0 + index, quality=capex_quality),
                    "cfo": make_metric(80.0 + index),
                },
                "derived": {
                    "revenue_growth_yoy": value,
                    "net_income_growth_yoy": value,
                    "rd_growth_yoy": value,
                    "capex_growth_yoy": value,
                    "fcf_growth_yoy": value,
                    "operating_margin": 0.2,
                    "rd_intensity": 0.05 + index * 0.001,
                    "capex_intensity": 0.04 + index * 0.001,
                    "stock_return_quarter": value,
                },
            }
        )
    return rows


def test_bt2_uses_wilcoxon_when_shapiro_rejects_normality():
    differences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 10.0]
    rows_a = make_rows(differences)
    rows_b = make_rows([0.0] * len(differences))
    results = bt2_paired_growth(
        rows_by_ticker={"MSFT": rows_a, "GOOGL": rows_b},
        tickers=["MSFT", "GOOGL"],
        alpha=0.05,
    )
    revenue = results[0]
    assert revenue["shapiro_p_value"] < 0.05
    assert revenue["test_used"] == "wilcoxon_signed_rank"
    assert revenue["wilcoxon_p_value"] is not None
    assert revenue["t_p_value"] is not None


def test_bt2_one_off_variant_lists_excluded_quarters():
    values = [0.1 * index for index in range(10)]
    rows_a = make_rows(values)
    rows_b = make_rows(values)
    results = bt2_paired_growth(
        rows_by_ticker={"MSFT": rows_a, "GOOGL": rows_b},
        tickers=["MSFT", "GOOGL"],
        alpha=0.05,
        one_off_quarters={"GOOGL": {"2023-Q2": "non-operating gain"}},
        label_suffix=" (excl. one-off quarters)",
    )
    variant = next(result for result in results if "excl." in result["test_name"])
    # 2023-Q2 and its YoY base 2022-Q2 are both removed, so 8 of 10 pairs remain.
    assert variant["n"] == 8
    assert any(
        item["calendar_key"] == "2023-Q2" for item in variant["excluded_quarters"]
    )


def test_bt3_excludes_low_quality_quarters_in_mode_a_and_keeps_them_in_mode_b():
    values = [0.04 + index * 0.001 for index in range(19)]
    rows = {"MSFT": make_rows(values, capex_quality="low")}
    excluded = bt3_trend(rows_by_ticker=rows, alpha=0.05, quality_mode="exclude_low")
    capex = next(result for result in excluded if "capex_intensity" in result["test_name"])
    assert capex["n"] == 0
    assert capex["decision"] == "insufficient_data"
    assert len(capex["excluded_quarters"]) == 19

    labelled = bt3_trend(rows_by_ticker=rows, alpha=0.05, quality_mode="label_low")
    capex_labelled = next(result for result in labelled if "capex_intensity" in result["test_name"])
    assert capex_labelled["n"] == 19
    assert capex_labelled["p_value"] is not None


def test_correlation_family_first_differences_nonstationary_series_and_holm_group():
    values = [100.0 + index * index for index in range(19)]
    rows = make_rows(values)
    for index, row in enumerate(rows):
        row["derived"]["revenue_growth_yoy"] = values[index] * 1.3 + (-20.0 if index % 2 else 20.0)
    results = _correlation_family(
        bt_code="BT4",
        rows_by_ticker={"MSFT": rows},
        x_field="capex_growth_yoy",
        y_fields=["revenue_growth_yoy"],
        max_lag=0,
        alpha=0.05,
        quality_mode="label_low",
    )
    result = results[0]
    assert result["transformation"] == "first_difference"
    assert result["n_effective"] == len(values) - 1
    assert result["adf"]["x"]["level_stationary"] is False
    assert result["p_adjusted"] is not None
    assert "Lag family=MSFT|capex_growth_yoy|revenue_growth_yoy|lags0-0" in result["note"]
    assert result["p_adj_lag_family"] is not None


def test_holm_bt_family_uses_declared_family_size():
    # Two x variables x three y variables x five lags = 30 BT4 tests.
    items = []
    for x_field in ("x1", "x2"):
        for y_field in ("y1", "y2", "y3"):
            for lag in range(5):
                items.append(
                    {
                        "ticker": "MSFT",
                        "bt_code": "BT4",
                        "x": x_field,
                        "y": y_field,
                        "lag": lag,
                        "p_value": 0.01,
                        "p_adj_lag_family": None,
                        "p_adj_bt_family": None,
                        "fragile": False,
                        "note": "",
                    }
                )
    _apply_correlation_holm(items, alpha=0.05, primary="bt", max_lag=4)
    assert all(item["p_adj_bt_family"] is not None for item in items)
    assert items[0]["holm_family_bt_size"] == 30
    assert _holm_family_size([0.01], 30) == [0.3]


def test_presentation_separates_raw_and_display_p_values():
    payload = {
        "results": [
            {
                "p_value": 0.00001,
                "p_adjusted": 0.02,
                "trend_on_level": {"p_value": 0.0002},
            }
        ],
        "quality_mode_comparison": [],
    }
    present_p_values(payload)
    result = payload["results"][0]
    assert result["p_value"] == "< 0.001"
    assert result["p_value_raw"] == 0.00001
    assert result["p_adjusted"] == "0.02"
    assert result["trend_on_level"]["p_value"] == "< 0.001"


def test_mode_b_keeps_only_identity_verified_derived_low_metrics():
    values = [0.04 + index * 0.001 for index in range(8)]
    row = make_rows(values)[0]
    capex = make_metric(6_828_000_000.0, quality="low", derived=True)
    capex.derivation_method = "YTD Q2 - Q1"
    capex.components = [
        {"role": "ytd", "value": 16614.0},
        {"role": "prior_quarter", "value": 9786.0},
    ]
    row["metrics"]["capex"] = capex
    assert _metric_identity_ok(capex) is True
    assert _quality_problem(row, "capex_intensity", "label_low") is None
    assert _quality_problem(row, "capex_intensity", "exclude_low") is not None

    other = make_metric(40.0, quality="low")
    row["metrics"]["capex"] = other
    assert _quality_problem(row, "capex_intensity", "label_low") is not None


def test_bt3_reports_trend_and_drift_with_display_p_values():
    rows = make_rows([0.04 + index * 0.002 for index in range(19)])
    result = next(
        item
        for item in bt3_trend(
            rows_by_ticker={"MSFT": rows},
            alpha=0.05,
            bootstrap_iterations=20,
        )
        if "rd_intensity" in item["test_name"]
    )
    assert result["trend_on_level"]["n"] == 19
    assert result["drift_on_difference"]["n"] == 18
    present_p_values({"results": [result], "quality_mode_comparison": []})
    assert result["p_value_raw"] == result["trend_on_level"]["p_value_raw"]
    assert result["trend_on_level"]["p_value_display"] is not None


def test_run_all_tests_exposes_both_modes_and_two_holm_families():
    rows = make_rows([0.04 + index * 0.002 for index in range(19)])
    payload = run_all_tests(
        rows_by_ticker={"MSFT": rows, "GOOGL": rows},
        price_analytics={},
        tickers=["MSFT", "GOOGL"],
        alpha=0.05,
        max_lag=0,
        quality_mode="label_low",
        quality_mode_primary="B",
        permutation_iterations=20,
        bt3_bootstrap_iterations=10,
    )
    assert payload["quality_mode"] == "label_low"
    assert payload["quality_mode_primary"] == "B"
    for result in payload["results"]:
        if result["bt_code"] in {"BT2", "BT3", "BT4", "BT5"}:
            assert result["mode_A_n"] is not None
            assert result["mode_B_n"] is not None
        if result["bt_code"] in {"BT4", "BT5"} and result["p_value"] is not None:
            assert result["p_adj_lag_family"] is not None
            assert result["p_adj_bt_family"] is not None
