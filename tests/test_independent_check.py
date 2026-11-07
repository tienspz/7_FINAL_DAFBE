from scripts.independent_check import raw_p_value


def test_raw_p_value_supports_legacy_schema():
    assert raw_p_value({"p_value": 0.125}, "1.1") == 0.125


def test_raw_p_value_prefers_machine_readable_value():
    assert raw_p_value(
        {"p_value": "<0.001", "p_value_raw": 0.0005},
        "1.2",
    ) == 0.0005
    assert raw_p_value({"p_value": "<0.001"}, "1.2") is None
