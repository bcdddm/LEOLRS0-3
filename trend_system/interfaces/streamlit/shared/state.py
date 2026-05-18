from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st
import toml


def fingerprint(settings: dict[str, Any], extras: dict[str, str]) -> str:
    payload = toml.dumps({"settings": _model_settings(settings), "extras": extras})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_stale(session_key: str, settings: dict[str, Any], extras: dict[str, str]) -> bool:
    saved = st.session_state.get(session_key)
    return bool(saved and saved != fingerprint(settings, extras))


def local_today(tz_name: str) -> date:
    try:
        timezone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    return datetime.now(tz=timezone).date()


def sync_date_input_default(
    widget_key: str,
    anchor_key: str,
    *,
    tz_name: str,
    lookback_days: int = 420,
) -> date:
    today = local_today(tz_name)
    default_value = today - timedelta(days=lookback_days)
    previous_anchor = st.session_state.get(anchor_key)

    if isinstance(previous_anchor, datetime):
        previous_anchor = previous_anchor.date()
    elif isinstance(previous_anchor, str):
        try:
            previous_anchor = date.fromisoformat(previous_anchor)
        except ValueError:
            previous_anchor = None

    if previous_anchor != today:
        previous_default = (
            previous_anchor - timedelta(days=lookback_days)
            if isinstance(previous_anchor, date)
            else None
        )
        current_value = st.session_state.get(widget_key)
        if current_value is None or previous_default is None or current_value == previous_default:
            st.session_state[widget_key] = default_value
        st.session_state[anchor_key] = today

    return default_value


def model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    model_settings = deepcopy(settings)
    model_settings.get("backtest", {}).pop("show_leveraged_buy_hold", None)
    model_settings.get("backtest", {}).pop("show_ma120_timing", None)
    model_settings.get("backtest", {}).pop("show_leveraged_ma120_timing", None)
    return model_settings


def _model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return model_settings(settings)
