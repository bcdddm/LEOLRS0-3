from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd
import streamlit as st

from trend_system.interfaces.streamlit.components import render_info_panel, render_section_head
from trend_system.interfaces.streamlit.shared.preparing import render_preparing
from trend_system.interfaces.streamlit.shared.session_state import SessionKeys
from trend_system.models import HealthcheckRequest
from trend_system.services.healthcheck_service import run_healthcheck


@dataclass(frozen=True)
class MarketHealthPageDeps:
    as_settings: Callable[[dict[str, Any]], Any]
    cached_prices: Callable[[tuple[str, ...], str, str | None, bool], dict[str, pd.DataFrame]]
    tr: Callable[[str, str, str], str]
    aligned_button: Callable[..., bool]
    disabled_pdf_button: Callable[[str, str, str], None]
    pdf_download_button: Callable[..., None]
    build_pdf_report: Callable[..., bytes]
    strategy_summary_rows: Callable[[dict[str, Any], str], list[tuple[str, str]]]
    pdf_filename: Callable[[str, dict[str, Any]], str]
    zoomable_line_chart: Callable[..., None]


def render_market_health_page(
    settings: dict[str, Any],
    language: str,
    *,
    deps: MarketHealthPageDeps,
) -> None:
    tr = deps.tr
    st.subheader(tr(language, "市场健康度", "Market Health"))
    render_info_panel(
        st,
        tr(
            language,
            "这个页面把高杠杆是否可用拆成独立的市场健康度判断：只有趋势结构修复后，才允许系统重新进入进攻模式。",
            "This page separates leveraged exposure permission into a market-health check: the system only returns to offensive mode after the trend structure repairs.",
        ),
        title=tr(language, "市场健康度说明", "Market Health Note"),
    )
    cols = st.columns([1, 1, 1])
    start = cols[0].date_input(
        tr(language, "健康度数据起始日期", "Health data start date"),
        value=date.today() - timedelta(days=420),
        key="market_health_start",
    )
    run = deps.aligned_button(
        cols[1],
        tr(language, "更新市场健康度", "Update market health"),
        type="primary",
        use_container_width=True,
    )
    primary = settings["signals"]["primary"]
    should_prepare = run or SessionKeys.MARKET_HEALTH_PRICE not in st.session_state
    if should_prepare:
        preparing = st.empty()
        render_preparing(
            preparing,
            language,
            title=tr(language, "准备中", "Preparing"),
            detail=tr(language, "正在读取价格历史并校验市场健康结构。", "Reading price history and checking market-health structure."),
        )
        price_loader = lambda symbol_list, start, end=None, auto_adjust=True: deps.cached_prices(
            tuple(symbol_list),
            str(start),
            end,
            auto_adjust,
        )
        try:
            result = run_healthcheck(
                HealthcheckRequest(settings=deps.as_settings(settings), start=start),
                price_loader=price_loader,
            )
        except RuntimeError as exc:
            preparing.empty()
            st.error(f"{tr(language, '市场健康度计算失败。', 'Market health calculation failed.')}\n\n`{exc}`")
            st.session_state.pop(SessionKeys.MARKET_HEALTH_PRICE, None)
            _market_health_strategy_notes(language, tr)
            return
        st.session_state[SessionKeys.MARKET_HEALTH_PRICE] = result.price
        st.session_state[SessionKeys.MARKET_HEALTH_SYMBOL] = result.symbol
        st.session_state[SessionKeys.MARKET_HEALTH_DISPLAY_START] = start
        preparing.empty()

    price = st.session_state[SessionKeys.MARKET_HEALTH_PRICE]
    ma120 = price.rolling(120, min_periods=1).mean()
    ma200 = price.rolling(200, min_periods=1).mean()
    latest_price = float(price.iloc[-1])
    latest_ma120 = float(ma120.iloc[-1])
    latest_ma200 = float(ma200.iloc[-1])
    slow_decline = latest_ma120 < latest_ma200
    healthy = latest_ma120 > latest_ma200
    stage = _health_stage_label(language, slow_decline, healthy, tr)

    health_rows = [
        (tr(language, "标的", "Symbol"), primary),
        (tr(language, "最新日期", "Latest date"), str(price.index[-1].date())),
        (tr(language, "最新价格", "Latest price"), f"{latest_price:,.2f}"),
        ("MA120", f"{latest_ma120:,.2f}"),
        ("MA200", f"{latest_ma200:,.2f}"),
        (tr(language, "健康阶段", "Health stage"), stage),
        (tr(language, "是否阴跌", "Slow decline"), tr(language, "是", "Yes") if slow_decline else tr(language, "否", "No")),
    ]
    deps.pdf_download_button(
        language,
        tr(language, "打印/下载市场健康度 PDF", "Print/Download Market Health PDF"),
        deps.build_pdf_report(
            tr(language, "市场健康度", "Market Health"),
            settings,
            language,
            sections=[
                (tr(language, "健康度摘要", "Health Summary"), health_rows),
                (tr(language, "策略信息", "Strategy Information"), deps.strategy_summary_rows(settings, language)),
            ],
            notes=_market_health_note_lines(language),
        ),
        deps.pdf_filename("market-health", settings),
        key="market_health_pdf_download",
    )
    metric_cols = st.columns(4)
    metric_cols[0].metric(primary, f"{latest_price:,.2f}")
    metric_cols[1].metric("MA120", f"{latest_ma120:,.2f}")
    metric_cols[2].metric("MA200", f"{latest_ma200:,.2f}")
    metric_cols[3].metric(tr(language, "健康阶段", "Health stage"), stage)
    if slow_decline:
        st.warning(
            tr(
                language,
                "市场健康度警告：120 日均线低于 200 日均线，视为（阴跌）状态。策略最高只允许 100% 等效仓位，不使用 3 倍杠杆。",
                "Market health warning: the 120-day MA is below the 200-day MA, treated as slow-decline state. The strategy allows at most 100% equivalent exposure and does not use 3x leverage.",
            )
        )
    else:
        st.success(
            tr(
                language,
                "市场健康度未处于（阴跌）状态；高仓位仍需继续通过趋势、VIX 和回撤模块确认。",
                "Market health is not in slow-decline state; high exposure still needs confirmation from trend, VIX, and drawdown modules.",
            )
        )

    display_start = pd.Timestamp(st.session_state.get(SessionKeys.MARKET_HEALTH_DISPLAY_START, start))
    display_price = price.loc[price.index >= display_start]
    display_ma120 = ma120.loc[ma120.index >= display_start]
    display_ma200 = ma200.loc[ma200.index >= display_start]
    health_frame = pd.DataFrame(
        {
            "price": display_price,
            "ma120": display_ma120,
            "ma200": display_ma200,
        }
    ).tail(260)
    health_frame.index.name = "date"
    deps.zoomable_line_chart(
        health_frame.rename(columns={"price": "health_price", "ma120": "health_ma120", "ma200": "health_ma200"}),
        ["health_price", "health_ma120", "health_ma200"],
        tr(language, "市场健康度曲线", "Market health chart"),
        key="market_health_chart",
        language=language,
    )
    _market_health_strategy_notes(language, tr)


def _market_health_strategy_notes(language: str, tr: Callable[[str, str, str], str]) -> None:
    render_section_head(st, tr(language, "操作纪律", "Operating Rules"), tone="prussian")
    render_info_panel(st, _market_health_note_lines(language), title=tr(language, "操作记录", "Operating Log"))


def _market_health_note_lines(language: str) -> list[str]:
    if language == "en":
        return [
            "1. Normal market: trend and VIX modules may allow high exposure or leverage.",
            "2. Warning phase: price or short MAs may look fine, but if 120MA < 200MA, slow-decline state is not over; cap at 100% and avoid 3x leverage.",
            "3. Recovery phase: only unlock after 120MA > 200MA, then let trend, VIX, and drawdown modules restore high exposure gradually.",
            "4. False-trigger guard: no high leverage while the market has not made new highs for a long time or while 120/200 has not repaired.",
        ]
    return [
        "1. 正常市场：允许按趋势和 VIX 模块加到高仓位或杠杆。",
        "2. 预警期：价格或短均线看起来还不错，但 120MA < 200MA，视为（阴跌）尚未结束；最高只允许 100%，不使用 3 倍杠杆。",
        "3. 恢复期：只有当 120MA > 200MA 后，才解除（阴跌）锁定，再允许系统根据趋势、VIX、回撤逐步恢复高仓位。",
        "4. 防误触：长期不创新高或 120/200 未修复时，都不碰高杠杆。",
    ]


def _health_stage_label(
    language: str,
    slow_decline: bool,
    healthy: bool,
    tr: Callable[[str, str, str], str],
) -> str:
    if slow_decline:
        return tr(language, "预警期：（阴跌）尚未结束", "Warning: slow-decline state is not over")
    if healthy:
        return tr(language, "恢复期：结构已修复", "Recovery: structure has repaired")
    return tr(language, "中性：120/200 均线接近", "Neutral: 120/200 MAs are close")
