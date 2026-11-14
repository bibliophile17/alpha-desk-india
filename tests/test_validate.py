import numpy as np
import pandas as pd

from alphadesk.validate import check_corporate_actions, check_missing_sessions

EVENT = 15


def make_df(n=30, price=100.0):
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "ticker": "TEST.NS", "open": price, "high": price, "low": price,
        "close": price, "adj_close": price, "volume": 1000,
        "dividends": 0.0, "split_ratio": 0.0,
    })


def checks(flags, severity=None):
    return {f["check"] for f in flags
            if severity is None or f["severity"] == severity}


def test_unadjusted_split_is_flagged():
    df = make_df()
    idx = np.arange(len(df))
    df["close"] = np.where(idx < EVENT, 100.0, 50.0)   # raw price halves
    df["adj_close"] = df["close"]
    df.loc[EVENT, "split_ratio"] = 2.0
    assert "split_diagnostic_unadjusted_pattern" in checks(check_corporate_actions(df, "TEST.NS"))


def test_correctly_adjusted_split_is_not_flagged():
    df = make_df(price=50.0)                           # continuous series
    df.loc[EVENT, "split_ratio"] = 2.0
    assert checks(check_corporate_actions(df, "TEST.NS"), "review") == set()


def test_reflected_dividend_passes():
    df = make_df()
    idx = np.arange(len(df))
    df["adj_close"] = np.where(idx < EVENT, 99.0, 100.0)  # 1% dividend reflected
    df.loc[EVENT, "dividends"] = 1.0
    assert checks(check_corporate_actions(df, "TEST.NS"), "review") == set()


def test_unreflected_dividend_is_flagged():
    df = make_df()
    df.loc[EVENT, "dividends"] = 1.0                   # adj_close == close
    assert "dividend_adjustment_mismatch" in checks(check_corporate_actions(df, "TEST.NS"))


def test_small_unreflected_dividend_is_flagged():
    # 0.15% yield: the old absolute tolerance of 0.2% would have missed this.
    df = make_df()
    df.loc[EVENT, "dividends"] = 0.15
    assert "dividend_adjustment_mismatch" in checks(check_corporate_actions(df, "TEST.NS"))


def test_tiny_dividend_is_untestable_not_flagged():
    df = make_df()
    df.loc[EVENT, "dividends"] = 0.02                  # 0.02% yield
    flags = check_corporate_actions(df, "TEST.NS")
    assert "dividend_untestable" in checks(flags, "info")
    assert checks(flags, "review") == set()


def test_extra_and_missing_sessions_are_flagged():
    df = make_df(n=10)
    dates = list(df["date"])
    benchmark = (set(dates) - {dates[3]}) | {pd.Timestamp("2024-01-06")}
    flags = check_missing_sessions(df, "TEST.NS", benchmark)
    got = {(f["check"], f["date"]) for f in flags}
    assert got == {("extra_session", dates[3]),
                   ("missing_session", pd.Timestamp("2024-01-06"))} 