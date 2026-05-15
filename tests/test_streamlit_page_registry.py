from __future__ import annotations

from trend_system.interfaces.streamlit.page_registry import build_page_context, build_page_specs, page_map_by_title


def test_page_registry_routes_renderers_with_expected_arguments():
    calls: list[tuple] = []

    def daily(settings):
        calls.append(("daily", settings))

    def market_health(settings):
        calls.append(("market_health", settings))

    def backtest(settings):
        calls.append(("backtest", settings))

    def settings(settings, config_path):
        calls.append(("settings", settings, config_path))

    shared_settings = {"ui": {"language": "zh"}}
    specs = build_page_specs(
        daily_renderer=daily,
        market_health_renderer=market_health,
        backtest_renderer=backtest,
        settings_renderer=settings,
    )
    context = build_page_context(shared_settings, "zh", "config/settings.toml")

    for spec in specs:
        if spec.enabled:
            spec.renderer(context)

    assert calls == [
        ("daily", shared_settings),
        ("market_health", shared_settings),
        ("backtest", shared_settings),
        ("settings", shared_settings, "config/settings.toml"),
    ]


def _noop_daily(settings):
    del settings


def _noop_market_health(settings):
    del settings


def _noop_backtest(settings):
    del settings


def _noop_settings(settings, config_path):
    del settings, config_path


def test_page_registry_exposes_enabled_pages_only():
    specs = build_page_specs(
        daily_renderer=_noop_daily,
        market_health_renderer=_noop_market_health,
        backtest_renderer=_noop_backtest,
        settings_renderer=_noop_settings,
    )

    pages = page_map_by_title(specs, language="zh")

    assert "今日信号" in pages
    assert "市场健康度" in pages
    assert "回测" in pages
    assert "设置总览" in pages
    assert "预留模块" not in pages


def test_page_context_carries_shared_shell_state():
    context = build_page_context({"ui": {"language": "zh"}}, "zh", "config/settings.toml")

    assert context.language == "zh"
    assert context.config_path == "config/settings.toml"
