from __future__ import annotations

from pathlib import Path

from trend_system.interfaces.streamlit.shared.release_notes import (
    release_notes_path,
    release_notes_text,
)
from trend_system.interfaces.streamlit.shared.state import fingerprint
from trend_system.interfaces.streamlit.shared.text import option_index, tr


def test_shared_text_helpers_cover_translation_and_fallback_index():
    assert tr("en", "中文", "English") == "English"
    assert tr("zh", "中文", "English") == "中文"
    assert option_index(["a", "b"], "b") == 1
    assert option_index(["a", "b"], "missing") == 0


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
