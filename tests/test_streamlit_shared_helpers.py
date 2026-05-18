from __future__ import annotations

import json
from pathlib import Path
import re

from trend_system.interfaces.streamlit.shared.release_notes import (
    release_notes_path,
    release_notes_text,
)
from trend_system.interfaces.streamlit.shared.cobe_globe import (
    MARKET_REGION_SAMPLES,
    build_cobe_globe_html,
)
from trend_system.interfaces.streamlit.shared.preparing import preparing_markup
from trend_system.interfaces.streamlit.shared.state import fingerprint
from trend_system.interfaces.streamlit.shared.text import option_index, tr


def test_shared_text_helpers_cover_translation_and_fallback_index():
    assert tr("en", "中文", "English") == "English"
    assert tr("zh", "中文", "English") == "中文"
    assert option_index(["a", "b"], "b") == 1
    assert option_index(["a", "b"], "missing") == 0


def test_preparing_markup_uses_translated_title_and_theme_classes():
    markup = preparing_markup("zh")

    assert "准备中" in markup
    assert "leolrs-dot-blue" in markup
    assert "leolrs-dot-green" in markup
    assert "leolrs-dot-red" in markup


def test_shared_release_notes_prefers_english_when_available(tmp_path: Path):
    zh = tmp_path / "CHANGELOG.md"
    en = tmp_path / "CHANGELOG.en.md"
    zh.write_text("中文日志", encoding="utf-8")
    en.write_text("English log", encoding="utf-8")

    assert release_notes_path("en", changelog_path=zh, changelog_en_path=en) == en
    assert release_notes_text("en", changelog_path=zh, changelog_en_path=en) == "English log"


def test_shared_release_notes_falls_back_to_default_file(tmp_path: Path):
    zh = tmp_path / "CHANGELOG.md"
    en = tmp_path / "CHANGELOG.en.md"
    zh.write_text("中文日志", encoding="utf-8")

    assert release_notes_path("en", changelog_path=zh, changelog_en_path=en) == zh
    assert release_notes_text("en", changelog_path=zh, changelog_en_path=en) == "中文日志"


def test_fingerprint_ignores_chart_only_backtest_toggles():
    base = {
        "backtest": {
            "show_leveraged_buy_hold": True,
            "show_ma120_timing": True,
            "show_leveraged_ma120_timing": False,
            "execution_timing": "next_session",
        },
        "ui": {"language": "zh"},
    }
    changed = {
        "backtest": {
            "show_leveraged_buy_hold": False,
            "show_ma120_timing": False,
            "show_leveraged_ma120_timing": True,
            "execution_timing": "next_session",
        },
        "ui": {"language": "zh"},
    }

    assert fingerprint(base, {"start": "2026-01-01"}) == fingerprint(changed, {"start": "2026-01-01"})


def test_cobe_globe_uses_low_contrast_region_blocks():
    markup = build_cobe_globe_html({"us", "asia"}, theme="dark", size=720)
    config_match = re.search(r"const config = (\{.*?\});", markup, re.S)

    assert config_match
    config = json.loads(config_match.group(1))
    assert config["width"] == 1440
    assert config["height"] == 1440
    assert config["dark"] == 1
    assert config["mapBrightness"] >= 1.0
    assert config["diffuse"] >= 0.75
    assert config["baseColor"][0] > 0.9
    assert config["glowColor"][2] > 0.1
    assert len(config["markers"]) == len(MARKET_REGION_SAMPLES["us"]) + len(MARKET_REGION_SAMPLES["asia"])
    assert {marker["size"] for marker in config["markers"]} == {0.11}
