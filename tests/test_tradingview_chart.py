import pandas as pd

from trend_system.interfaces.streamlit.shared.tradingview_chart import build_lightweight_chart_payload


def test_build_lightweight_chart_payload_serializes_requested_series():
    frame = pd.DataFrame(
        {
            "equity": [100000.0, 101500.0],
            "buy_hold_equity": [100000.0, 100500.0],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )
    frame.index.name = "date"

    payload = build_lightweight_chart_payload(
        frame,
        ["equity", "buy_hold_equity"],
        label_resolver=lambda series: series.upper(),
        line_styles={"buy_hold_equity": "dashed"},
    )

    assert [series["key"] for series in payload] == ["equity", "buy_hold_equity"]
    assert payload[0]["label"] == "EQUITY"
    assert payload[1]["style"] == "dashed"
    assert payload[0]["points"][0] == {"time": "2026-01-01", "value": 100000.0}


def test_build_lightweight_chart_payload_skips_empty_series():
    frame = pd.DataFrame(
        {
            "equity": [None, None],
            "buy_hold_equity": [100000.0, 100500.0],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )

    payload = build_lightweight_chart_payload(
        frame,
        ["equity", "buy_hold_equity"],
        label_resolver=lambda series: series,
    )

    assert [series["key"] for series in payload] == ["buy_hold_equity"]
