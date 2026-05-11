from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from trend_system.timezones import market_window


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


def trade_timeline_items(settings_raw: dict, now: datetime | None = None) -> list[TradeTimelineItem]:
    home_timezone = ZoneInfo(settings_raw["profile"]["home_timezone"])
    if now is None:
        now = datetime.now(tz=home_timezone)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=home_timezone)
    else:
        now = now.astimezone(home_timezone)

    us_open, _ = market_window(settings_raw, "us").relevant_local_trading_window(now)

    return [
        TradeTimelineItem(
            strategy_key="next_session",
            strategy_label_zh="Next Session",
            strategy_label_en="Next Session",
            action_zh="下个美股交易日开盘前，完成按信号买入/调仓",
            action_en="Before the next US open, complete signal-based buys/rebalance",
            deadline=us_open,
            market_label="US",
        ),
    ]
