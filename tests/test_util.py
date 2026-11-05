"""Shared utility and JSON serialization tests."""

import json
from datetime import date

import numpy as np

from pipeline.util import json_safe, read_json, write_json


def test_json_safe_handles_numpy_and_dates():
    value = {
        "flag": np.bool_(False),
        "float": np.float64(1.25),
        "int": np.int64(3),
        "array": np.array([1.0, 2.0]),
        "date": date(2026, 11, 5),
        "nan": float("nan"),
    }
    assert json_safe(value) == {
        "flag": False,
        "float": 1.25,
        "int": 3,
        "array": [1.0, 2.0],
        "date": "2026-11-05",
        "nan": None,
    }


def test_write_json_is_atomic_and_serializable(tmp_path):
    path = tmp_path / "payload.json"
    write_json(path, {"stationary": np.bool_(True), "p_value": np.float64(0.01)})
    assert read_json(path) == {"stationary": True, "p_value": 0.01}
    assert json.loads(path.read_text(encoding="utf-8")) == {"stationary": True, "p_value": 0.01}
