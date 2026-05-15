from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from trend_system.timezones import market_window

NEXT_SESSION_MODE = "next_session"
NZ_CLOSE_US_OPEN_MODE = "nz_close_us_open"
SUPPORTED_TIMELINE_MODES = (
    NEXT_SESSION_MODE,
    NZ_CLOSE_US_OPEN_MODE,
)


@dataclass(frozen=True)
class TradeTimelineItem:
    strategy_key: str
    strategy_label_zh: str
    strategy_label_en: str
    action_zh: str
    action_en: str
    deadline: datetime
    market_label: str

    def strategy_label(self, language: str) -> str:
        return self.strategy_label_en if language == "en" else self.strategy_label_zh

    def action(self, language: str) -> str:
        return self.action_en if language == "en" else self.action_zh


def trade_timeline_items(
    settings_raw: dict,
    now: datetime | None = None,
    *,
    strategy_keys: set[str] | None = None,
) -> list[TradeTimelineItem]:
    home_timezone = ZoneInfo(settings_raw["profile"]["home_timezone"])
    if now is None:
        now = datetime.now(tz=home_timezone)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=home_timezone)
    else:
        now = now.astimezone(home_timezone)

    us_open, us_close = market_window(settings_raw, "us").relevant_local_trading_window(now)
    _, nzx_close = market_window(settings_raw, "nzx").relevant_local_trading_window(now)
    allowed_keys = _normalize_strategy_keys(strategy_keys)
    items = [
        TradeTimelineItem(
            strategy_key=NEXT_SESSION_MODE,
            strategy_label_zh="下一交易日",
            strategy_label_en="Next Session",
            action_zh="下个美股交易日开盘前，完成按信号买入/调仓",
            action_en="Before the next US open, complete signal-based buys/rebalance",
            deadline=us_open,
            market_label="US",
        ),
        TradeTimelineItem(
            strategy_key=NZ_CLOSE_US_OPEN_MODE,
            strategy_label_zh="NZ 盘末 / 美股开盘",
            strategy_label_en="NZ Close / US Open",
            action_zh="NZX 收盘前，处理本地 S&P 500 卖出或买回",
            action_en="Before the NZX close, handle local S&P 500 sell/buyback work",
            deadline=nzx_close,
            market_label="NZX",
        ),
        TradeTimelineItem(
            strategy_key=NZ_CLOSE_US_OPEN_MODE,
            strategy_label_zh="NZ 盘末 / 美股开盘",
            strategy_label_en="NZ Close / US Open",
            action_zh="美股开盘前，挂好 3 倍杠杆资产买单",
            action_en="Before the US open, place the 3x leveraged asset buy order",
            deadline=us_open,
            market_label="US",
        ),
        TradeTimelineItem(
            strategy_key=NZ_CLOSE_US_OPEN_MODE,
            strategy_label_zh="NZ 盘末 / 美股开盘",
            strategy_label_en="NZ Close / US Open",
            action_zh="美股收盘前，卖出美股 3 倍杠杆资产并准备买回 NZ 头寸",
            action_en="Before the US close, sell US 3x exposure and prepare the NZ buyback",
            deadline=us_close,
            market_label="US",
        ),
    ]
    if allowed_keys is not None:
        items = [item for item in items if item.strategy_key in allowed_keys]
    return sorted(items, key=lambda item: item.deadline)


def _normalize_strategy_keys(strategy_keys: set[str] | None) -> set[str] | None:
    if strategy_keys is None:
        return None
    normalized = {key for key in strategy_keys if key in SUPPORTED_TIMELINE_MODES}
    return normalized or {NEXT_SESSION_MODE}
