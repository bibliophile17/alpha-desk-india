import numpy as np
import pandas as pd
import pytest

from alphadesk.announcements import (add_performance_proxy, align_events, classify,
                                     parse_time, yoy_growth)
from alphadesk.tradingcalendar import CalendarError, TradingCalendar, audit_calendar

# Jan-Feb 2024 weekdays minus Fri 2024-01-26 (a holiday); Sat 13 Jan is not a session.
DATES = [d for d in pd.bdate_range("2024-01-01", "2024-02-29") if d != pd.Timestamp("2024-01-26")]
CAL = TradingCalendar(DATES)
T = pd.Timestamp


def test_calendar_navigation():
    assert CAL.next_session_on_or_after("2024-01-13") == T("2024-01-15")
    assert CAL.next_session_on_or_after("2024-01-10") == T("2024-01-10")
    assert CAL.next_session_after("2024-01-10") == T("2024-01-11")
    assert CAL.next_session_after("2024-01-25") == T("2024-01-29")   # holiday skipped
    assert CAL.offset("2024-01-25", 1) == T("2024-01-29")
    assert CAL.offset("2024-01-29", -1) == T("2024-01-25")


def test_calendar_refuses_to_guess():
    with pytest.raises(CalendarError):
        CAL.next_session_on_or_after("2024-03-05")
    with pytest.raises(CalendarError):
        CAL.next_session_on_or_after("2023-12-30")
    with pytest.raises(CalendarError):
        CAL.index_of("2024-01-26")


def test_audit_flags_unexplained_gap_and_listed_holiday(tmp_path):
    a = audit_calendar(CAL)
    assert (a["item"] == "unexplained_weekday_gap").sum() == 1
    h = tmp_path / "h.csv"
    pd.DataFrame({"date": ["2024-01-26"], "description": ["Republic Day"],
                  "source_url": ["x"]}).to_csv(h, index=False)
    assert list(audit_calendar(CAL, h)["item"]) == ["confirmed_holiday"]


@pytest.mark.parametrize("date,time_,cls,day0,ok", [
    ("2024-01-10", "08:30", "pre_market", "2024-01-10", True),
    ("2024-01-10", "09:14", "pre_market", "2024-01-10", True),
    ("2024-01-10", "09:15", "during_market_hours", None, False),
    ("2024-01-10", "15:30", "during_market_hours", None, False),
    ("2024-01-10", "15:31", "after_market", "2024-01-11", True),
    ("2024-01-12", "16:00", "after_market", "2024-01-15", True),        # Fri -> Mon
    ("2024-01-13", "11:00", "non_session_day", "2024-01-15", True),     # Saturday
    ("2024-01-26", "10:00", "non_session_day", "2024-01-29", True),     # holiday
    ("2024-01-25", "17:00", "after_market", "2024-01-29", True),        # next day is holiday
])
def test_classification(date, time_, cls, day0, ok):
    c, d0, elig, _ = classify(date, time_, CAL)
    assert c == cls and elig == ok
    if day0 is None:
        assert pd.isna(d0)
    else:
        assert d0 == T(day0)


def test_unknown_time_excluded_on_trading_day_but_not_weekend():
    assert classify("2024-01-10", None, CAL)[2] is False
    assert classify("2024-01-10", float("nan"), CAL)[0] == "unknown_time"
    assert classify("2024-01-13", None, CAL)[2] is True


def test_parse_time():
    assert parse_time("9:15").hour == 9
    assert parse_time(None) is None
    with pytest.raises(ValueError):
        parse_time("quarter past nine")


def _events(rows):
    cols = ["ticker", "company", "sector", "fiscal_quarter", "announce_date",
            "announce_time", "time_source", "revenue", "pat", "eps", "prior_revenue",
            "prior_pat", "prior_eps", "source_url", "retrieved_at"]
    df = pd.DataFrame(rows, columns=["ticker", "fiscal_quarter", "announce_date", "announce_time"])
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    return df[cols]


def test_duplicates_keep_earliest_and_are_logged():
    df = _events([("A.NS", "Q2", "2024-01-10", "16:00"),
                  ("A.NS", "Q2", "2024-01-10", "08:00"),
                  ("A.NS", "Q2", "2024-01-11", "08:00"),
                  ("B.NS", "Q2", "2024-01-10", "08:00")])
    ev, dropped = align_events(df, CAL)
    assert len(ev) == 2 and len(dropped) == 2
    a = ev[ev["ticker"] == "A.NS"].iloc[0]
    assert a["announce_time"] == "08:00" and a["announce_date"] == T("2024-01-10")


def test_out_of_range_event_is_excluded_not_crashed():
    ev, _ = align_events(_events([("A.NS", "Q3", "2024-06-01", "08:00")]), CAL)
    assert ev.loc[0, "timing_class"] == "calendar_out_of_range"
    assert not ev.loc[0, "eligible_primary"]


def test_missing_required_fields_raise():
    df = _events([("A.NS", None, "2024-01-10", "08:00")])
    with pytest.raises(ValueError):
        align_events(df, CAL)


def test_yoy_only_when_comparable():
    g = yoy_growth(pd.Series([120, 50, 10, np.nan]), pd.Series([100, 0, -20, 5]))
    assert g.iloc[0] == pytest.approx(0.2)
    assert g.iloc[1:].isna().all()
    d = add_performance_proxy(pd.DataFrame({"revenue": [110], "prior_revenue": [100],
                                            "pat": [5], "prior_pat": [-1]}))
    assert d.loc[0, "rev_yoy"] == pytest.approx(0.1) and np.isnan(d.loc[0, "pat_yoy"])
