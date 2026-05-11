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


def trade_timeline_items(
    settings_raw: dict,
    now: datetime | None = None,
    transition: str | None = None,
) -> list[TradeTimelineItem]:
    """Return trade timeline items for the given settings and transition direction.

    transition:
      "1x_to_3x" — sell NZ S&P500 at NZX close, buy SPXL at US open
      "3x_to_1x" — sell SPXL at US close, buy NZ S&P500 at NZX open
      None        — no leverage change; only the next_session item is returned
    """
    home_timezone = ZoneInfo(settings_raw["profile"]["home_timezone"])
    if now is None:
        now = datetime.now(tz=home_timezone)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=home_timezone)
    else:
        now = now.astimezone(home_timezone)

    us_open, us_close = market_window(settings_raw, "us").relevant_local_trading_window(now)
    _, nzx_close = market_window(settings_raw, "nzx").relevant_local_trading_window(now)
    # For 3x→1x the NZX buy must happen after US close, so find the NZX session
    # that opens after us_close rather than the one nearest to now.
    nzx_open_after_us_close, _ = market_window(settings_raw, "nzx").relevant_local_trading_window(us_close)

    items: list[TradeTimelineItem] = [
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

    if transition == "1x_to_3x":
        items += [
            TradeTimelineItem(
                strategy_key="nz_close_us_open",
                strategy_label_zh="NZ Close / US Open",
                strategy_label_en="NZ Close / US Open",
                action_zh="NZX 收盘前，卖出本地 S&P 500（如 USF.NZX）",
                action_en="Before the NZX close, sell the local S&P 500 holding (e.g. USF.NZX)",
                deadline=nzx_close,
                market_label="NZX",
            ),
            TradeTimelineItem(
                strategy_key="nz_close_us_open",
                strategy_label_zh="NZ Close / US Open",
                strategy_label_en="NZ Close / US Open",
                action_zh="美股开盘前，挂单买入 3 倍杠杆资产（SPXL）",
                action_en="Before the US open, place the 3x leveraged asset buy order (SPXL)",
                deadline=us_open,
                market_label="US",
            ),
        ]
    elif transition == "3x_to_1x":
        items += [
            TradeTimelineItem(
                strategy_key="nz_close_us_open",
                strategy_label_zh="NZ Close / US Open",
                strategy_label_en="NZ Close / US Open",
                action_zh="美股收盘前，卖出 3 倍杠杆资产（SPXL）",
                action_en="Before the US close, sell the 3x leveraged asset (SPXL)",
                deadline=us_close,
                market_label="US",
            ),
            TradeTimelineItem(
                strategy_key="nz_close_us_open",
                strategy_label_zh="NZ Close / US Open",
                strategy_label_en="NZ Close / US Open",
                action_zh="NZX 开盘前，挂单买入本地 S&P 500（如 USF.NZX）",
                action_en="Before the NZX open, place the local S&P 500 buy order (e.g. USF.NZX)",
                deadline=nzx_open_after_us_close,
                market_label="NZX",
            ),
        ]

    return sorted(items, key=lambda item: item.deadline)
