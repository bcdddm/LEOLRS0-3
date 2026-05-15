from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

import streamlit as st
import toml


def fingerprint(settings: dict[str, Any], extras: dict[str, str]) -> str:
    payload = toml.dumps({"settings": _model_settings(settings), "extras": extras})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_stale(session_key: str, settings: dict[str, Any], extras: dict[str, str]) -> bool:
    saved = st.session_state.get(session_key)
    return bool(saved and saved != fingerprint(settings, extras))


def model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    model_settings = deepcopy(settings)
    model_settings.get("backtest", {}).pop("show_leveraged_buy_hold", None)
    model_settings.get("backtest", {}).pop("show_ma120_timing", None)
    model_settings.get("backtest", {}).pop("show_leveraged_ma120_timing", None)
    return model_settings


def _model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return model_settings(settings)
