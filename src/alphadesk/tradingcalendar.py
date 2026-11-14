"""Trading calendar built from OBSERVED exchange sessions, never assumed.

Calendar days and trading days are not interchangeable: the event study counts
in sessions (-130, -11, +5 ...), so every offset goes through this class.
The calendar refuses to answer outside the range it has evidence for.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


class CalendarError(Exception):
    pass


class TradingCalendar:
    def __init__(self, sessions):
        s = pd.DatetimeIndex(pd.to_datetime(list(sessions))).normalize()
        s = s.unique().sort_values()
        if len(s) == 0:
            raise CalendarError("no sessions supplied")
        self.sessions = s
        self._pos = {d: i for i, d in enumerate(s)}

    @classmethod
    def from_price_csv(cls, path):
        """Sessions = dates present in a saved index price file (e.g. ^NSEI)."""
        df = pd.read_csv(path, parse_dates=["date"])
        return cls(df["date"].dropna())

    @property
    def first(self):
        return self.sessions[0]

    @property
    def last(self):
        return self.sessions[-1]

    def is_session(self, d) -> bool:
        return pd.Timestamp(d).normalize() in self._pos

    def index_of(self, d) -> int:
        d = pd.Timestamp(d).normalize()
        if d not in self._pos:
            raise CalendarError(f"{d.date()} is not a known session")
        return self._pos[d]

    def session_at(self, i: int):
        if i < 0 or i >= len(self.sessions):
            raise CalendarError(f"session index {i} outside calendar")
        return self.sessions[i]

    def offset(self, d, n: int):
        """The session n sessions after (or before, if n<0) session d."""
        return self.session_at(self.index_of(d) + n)

    def _check_range(self, d):
        if d < self.first or d > self.last:
            raise CalendarError(
                f"{d.date()} outside known sessions "
                f"{self.first.date()}..{self.last.date()}; refusing to guess")

    def next_session_on_or_after(self, d):
        d = pd.Timestamp(d).normalize()
        self._check_range(d)
        return self.sessions[self.sessions.searchsorted(d, side="left")]

    def next_session_after(self, d):
        d = pd.Timestamp(d).normalize()
        self._check_range(d)
        i = self.sessions.searchsorted(d, side="right")
        if i >= len(self.sessions):
            raise CalendarError(f"no known session after {d.date()}")
        return self.sessions[i]


def audit_calendar(cal: TradingCalendar, holidays_csv=None) -> pd.DataFrame:
    """Rows needing manual review. holidays_csv: date, description, source_url."""
    hol = set()
    if holidays_csv and Path(holidays_csv).exists():
        h = pd.read_csv(holidays_csv, parse_dates=["date"])
        hol = set(h["date"].dt.normalize())
    rows = []
    for d in pd.bdate_range(cal.first, cal.last):
        if not cal.is_session(d):
            item = "confirmed_holiday" if d in hol else "unexplained_weekday_gap"
            rows.append({"date": d.date(), "weekday": d.day_name(), "item": item})
    for d in cal.sessions:
        if d.weekday() >= 5:
            rows.append({"date": d.date(), "weekday": d.day_name(),
                         "item": "weekend_session"})
        if d in hol:
            rows.append({"date": d.date(), "weekday": d.day_name(),
                         "item": "holiday_listed_but_traded"})
    return pd.DataFrame(rows, columns=["date", "weekday", "item"])
