from __future__ import annotations

from trend_system.interfaces.streamlit.page_contracts import StreamlitPageContext, StreamlitPageSpec
from trend_system.interfaces.streamlit.pages.future_module_page import render_future_module_page


def build_page_specs(
    *,
    daily_renderer,
    market_health_renderer,
    backtest_renderer,
    settings_renderer,
) -> list[StreamlitPageSpec]:
    return [
        StreamlitPageSpec(
            key="daily",
            title_zh="今日信号",
            title_en="Daily Signal",
            renderer=lambda context: daily_renderer(context.settings),
            notes="Shell route to the daily page renderer.",
        ),
        StreamlitPageSpec(
            key="market_health",
            title_zh="市场健康度",
            title_en="Market Health",
            renderer=lambda context: market_health_renderer(context.settings),
            notes="Shell route to the market health page renderer.",
        ),
        StreamlitPageSpec(
            key="backtest",
            title_zh="回测",
            title_en="Backtest",
            renderer=lambda context: backtest_renderer(context.settings),
            notes="Shell route to the backtest page renderer.",
        ),
        StreamlitPageSpec(
            key="settings",
            title_zh="设置总览",
            title_en="Settings Overview",
            renderer=lambda context: settings_renderer(context.settings, context.config_path),
            notes="Shell route to the settings page renderer.",
        ),
        StreamlitPageSpec(
            key="future_module",
            title_zh="预留模块",
            title_en="Reserved Module",
            renderer=render_future_module_page,
            enabled=False,
            notes="Reserved slot for the next standalone module. Enable only when its service contract is ready.",
        ),
    ]


def enabled_page_specs(specs: list[StreamlitPageSpec]) -> list[StreamlitPageSpec]:
    return [spec for spec in specs if spec.enabled]


def page_map_by_title(
    specs: list[StreamlitPageSpec],
    *,
    language: str,
) -> dict[str, StreamlitPageSpec]:
    return {spec.title(language): spec for spec in enabled_page_specs(specs)}


def build_page_context(settings: dict, language: str, config_path: str) -> StreamlitPageContext:
    return StreamlitPageContext(
        settings=settings,
        language=language,
        config_path=config_path,
    )
