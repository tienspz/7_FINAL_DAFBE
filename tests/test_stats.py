"""Statistical test helper tests."""

import json

import numpy as np
import pandas as pd

from pipeline.stats.tests import _adf, bt1_excess_returns, holm_adjust
from pipeline.util import json_safe


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
