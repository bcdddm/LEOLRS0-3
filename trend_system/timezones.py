from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd


CALENDAR_NAMES = {
    "us": "XNYS",
    "asx": "XASX",
    "nzx": "XNZE",
}


@dataclass(frozen=True)
class MarketWindow:
    market: str
    market_timezone: str
    home_timezone: str
    regular_open: str
    regular_close: str
    calendar_name: str | None = None

    def local_window_for_date(self, market_date: datetime) -> tuple[datetime, datetime]:
        market_tz = ZoneInfo(self.market_timezone)
        home_tz = ZoneInfo(self.home_timezone)
        open_dt = datetime.combine(
            market_date.date(),
            _parse_hhmm(self.regular_open),
            tzinfo=market_tz,
        )
        close_dt = datetime.combine(
            market_date.date(),
            _parse_hhmm(self.regular_close),
            tzinfo=market_tz,
        )
        return open_dt.astimezone(home_tz), close_dt.astimezone(home_tz)

    def local_trading_window_for_session(self, session: pd.Timestamp) -> tuple[datetime, datetime]:
        calendar = self._calendar()
        home_tz = ZoneInfo(self.home_timezone)
        open_dt = calendar.session_open(session).to_pydatetime()
        close_dt = calendar.session_close(session).to_pydatetime()
        return open_dt.astimezone(home_tz), close_dt.astimezone(home_tz)

    def relevant_local_trading_window(self, now: datetime) -> tuple[datetime, datetime]:
        home_tz = ZoneInfo(self.home_timezone)
        if now.tzinfo is None:
            now = now.replace(tzinfo=home_tz)
        else:
            now = now.astimezone(home_tz)

        calendar = self._calendar()
        market_now = now.astimezone(ZoneInfo(self.market_timezone))
        market_date = pd.Timestamp(market_now.date())
        sessions = _candidate_sessions(calendar, market_date)
        windows = [self.local_trading_window_for_session(session) for session in sessions]

        for open_dt, close_dt in windows:
            if open_dt <= now <= close_dt:
                return open_dt, close_dt

        upcoming = [(open_dt, close_dt) for open_dt, close_dt in windows if open_dt > now]
        if upcoming:
            return min(upcoming, key=lambda pair: pair[0])
        return max(windows, key=lambda pair: pair[1])

    def _calendar(self):
        return xcals.get_calendar(self.calendar_name or CALENDAR_NAMES[self.market])


def market_window(settings_raw: dict, market: str) -> MarketWindow:
    profile = settings_raw["profile"]
    market_config = settings_raw["markets"][market]
    return MarketWindow(
        market=market,
        market_timezone=market_config["timezone"],
        home_timezone=profile["home_timezone"],
        regular_open=market_config["regular_open"],
        regular_close=market_config["regular_close"],
        calendar_name=market_config.get("calendar") or CALENDAR_NAMES.get(market),
    )


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _candidate_sessions(calendar, market_date: pd.Timestamp) -> list[pd.Timestamp]:
    previous_session = calendar.date_to_session(market_date, direction="previous")
    next_session = calendar.date_to_session(market_date, direction="next")
    candidates = [previous_session, next_session]

    for session in (previous_session, next_session):
        try:
            candidates.append(calendar.previous_session(session))
        except ValueError:
            pass
        try:
            candidates.append(calendar.next_session(session))
        except ValueError:
            pass

    return sorted(dict.fromkeys(candidates))
