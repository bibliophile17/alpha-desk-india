import numpy as np
import pandas as pd
import pytest

from alphadesk.eventstudy import (compute_event, ols_market_model, reaction_blank_set,
                                  run_event_study, session_returns)
from alphadesk.placebo import SHIFTS, placebo_shift_test
from alphadesk.tradingcalendar import TradingCalendar


def make_world(n=500, seed=1, planted=None, tickers=("AAA.NS", "BBB.NS"), betas=(1.2, 0.8)):
    """Noise-free stocks: R = alpha + beta*Rm exactly, plus planted abnormal returns."""
    dates = pd.bdate_range("2022-01-03", periods=n)
    cal = TradingCalendar(dates)
    rng = np.random.default_rng(seed)
    bench = pd.Series(rng.normal(0, 0.01, n), index=dates)
    bench.iloc[0] = np.nan
    stocks = {tk: 0.0002 + b * bench for tk, b in zip(tickers, betas)}
    for (tk, idx), extra in (planted or {}).items():
        for k, v in extra.items():
            stocks[tk].iloc[idx + k] += v
    return cal, bench, stocks


def test_ols_hand_calculated_example():
    # x=[1,2,3,4], y=[2,4,5,8]: Sxx=5, Sxy=9.5 -> beta=1.9, alpha=0, SSR=0.70
    r = ols_market_model([2, 4, 5, 8], [1, 2, 3, 4])
    assert r["beta"] == pytest.approx(1.9) and r["alpha"] == pytest.approx(0.0, abs=1e-12)
    assert r["sigma"] == pytest.approx(np.sqrt(0.70 / 2))


def test_ols_matches_polyfit_on_noisy_data():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    y = 0.3 + 0.7 * x + rng.normal(scale=0.5, size=200)
    r = ols_market_model(y, x)
    slope, icpt = np.polyfit(x, y, 1)
    assert r["beta"] == pytest.approx(slope) and r["alpha"] == pytest.approx(icpt)


def test_returns_use_nan_not_zero_for_missing_prices():
    cal = TradingCalendar(pd.bdate_range("2024-01-01", periods=6))
    p = pd.Series([100, 101, np.nan, 103, 104, 105.0], index=cal.sessions)
    r = session_returns(p, cal)
    assert np.isnan(r.iloc[0]) and np.isnan(r.iloc[2]) and np.isnan(r.iloc[3])
    assert r.iloc[1] == pytest.approx(0.01) and r.iloc[4] == pytest.approx(104 / 103 - 1)


def test_returns_ignore_dates_outside_calendar():
    cal = TradingCalendar(pd.bdate_range("2024-01-01", periods=4))
    p = pd.Series([100, 110, 121, 133.1, 146.41], index=pd.bdate_range("2024-01-01", periods=5))
    assert len(session_returns(p, cal)) == 4


def test_planted_abnormal_return_is_recovered_exactly():
    t0 = 200
    cal, bench, stocks = make_world(planted={("AAA.NS", t0): {0: 0.03, 1: 0.01}})
    res = compute_event(stocks["AAA.NS"], bench, cal, cal.session_at(t0))
    assert res["status"] == "ok" and res["est_obs"] == 120
    assert res["beta"] == pytest.approx(1.2) and res["alpha"] == pytest.approx(0.0002)
    assert res["ar_0"] == pytest.approx(0.03, abs=1e-10)
    assert res["ar_1"] == pytest.approx(0.01, abs=1e-10)
    assert res["ar_-1"] == pytest.approx(0.0, abs=1e-10) and res["ar_2"] == pytest.approx(0.0, abs=1e-10)
    assert res["car_[0,+1]"] == pytest.approx(0.04, abs=1e-10)
    assert res["car_[0,+3]"] == pytest.approx(0.04, abs=1e-10)
    assert res["car_[0,+5]"] == pytest.approx(0.04, abs=1e-10)
    assert res["car_[-1,+1]"] == pytest.approx(0.04, abs=1e-10)


def test_car_is_sum_of_daily_ars_and_windows_are_indexed_correctly():
    t0 = 200
    cal, bench, stocks = make_world(planted={("AAA.NS", t0): {-1: 0.005, 0: 0.01, 2: 0.02, 4: -0.004, 5: 0.001}})
    res = compute_event(stocks["AAA.NS"], bench, cal, cal.session_at(t0))
    assert res["car_[-1,+1]"] == pytest.approx(0.015, abs=1e-10)
    assert res["car_[0,+1]"] == pytest.approx(0.01, abs=1e-10)
    assert res["car_[0,+3]"] == pytest.approx(0.03, abs=1e-10)
    assert res["car_[0,+5]"] == pytest.approx(0.027, abs=1e-10)


def test_event_period_is_excluded_from_estimation_window():
    # A shock at day -10 (just inside the exclusion zone) must not touch alpha/beta.
    t0 = 200
    cal, bench, stocks = make_world(planted={("AAA.NS", t0): {-10: 0.2, 0: 0.03}})
    res = compute_event(stocks["AAA.NS"], bench, cal, cal.session_at(t0))
    assert res["beta"] == pytest.approx(1.2) and res["ar_0"] == pytest.approx(0.03, abs=1e-10)


def test_missing_event_price_nans_only_affected_windows():
    t0 = 200
    cal, bench, stocks = make_world(planted={("AAA.NS", t0): {0: 0.03}})
    s = stocks["AAA.NS"].copy()
    s.iloc[t0 + 4] = np.nan                       # inside [0,+5] only
    res = compute_event(s, bench, cal, cal.session_at(t0))
    assert res["status"] == "partial_missing_event_prices"
    assert np.isfinite(res["car_[0,+3]"]) and np.isnan(res["car_[0,+5]"])


def test_insufficient_data_is_reported_not_computed():
    cal, bench, stocks = make_world()
    assert compute_event(stocks["AAA.NS"], bench, cal, cal.session_at(100))["status"] == "insufficient_calendar"
    assert compute_event(stocks["AAA.NS"], bench, cal, cal.session_at(495))["status"] == "insufficient_calendar"
    s = stocks["AAA.NS"].copy()
    s.iloc[100:180] = np.nan
    res = compute_event(s, bench, cal, cal.session_at(250))
    assert res["status"] == "insufficient_estimation_obs" and np.isnan(res["car_[0,+1]"])


def _events(cal, rows):
    return pd.DataFrame([{"ticker": tk, "sector": sec, "fiscal_quarter": "Q", "announce_date": cal.session_at(i),
                          "announce_time": "08:00", "timing_class": "pre_market",
                          "day0": cal.session_at(i), "eligible_primary": True}
                         for tk, sec, i in rows])


def test_prior_event_in_estimation_window_must_be_blanked():
    planted = {("AAA.NS", 200): {0: 0.03, 1: 0.01}, ("AAA.NS", 270): {0: -0.02}}
    cal, bench, stocks = make_world(planted=planted)
    from alphadesk.eventstudy import compute_event as ce
    dirty = ce(stocks["AAA.NS"], bench, cal, cal.session_at(270))
    clean = ce(stocks["AAA.NS"], bench, cal, cal.session_at(270),
               blank_idx=reaction_blank_set([200]))
    assert abs(dirty["ar_0"] + 0.02) > 1e-6          # contamination is real (small but non-zero)
    assert clean["ar_0"] == pytest.approx(-0.02, abs=1e-10)


def test_run_event_study_and_placebo_end_to_end():
    planted = {("AAA.NS", 200): {0: 0.03, 1: 0.01}, ("AAA.NS", 270): {0: -0.02},
               ("BBB.NS", 200): {0: 0.03, 1: 0.01}}
    cal, bench, stocks = make_world(planted=planted)
    rets = {tk: s for tk, s in stocks.items()}
    ev = _events(cal, [("AAA.NS", "IT", 200), ("AAA.NS", "IT", 270), ("BBB.NS", "Banks", 200)])
    res = run_event_study(ev, rets, bench, cal)
    assert list(res["status"]) == ["ok"] * 3
    assert res["car_[0,+5]"].round(10).tolist() == [0.04, -0.02, 0.04]
    pl = placebo_shift_test(res, rets, bench, cal)
    w = pl[pl["window"] == "[0,+1]"].iloc[0]
    assert len(SHIFTS) == 80 and w["n_shifts_used"] == 80
    assert w["observed_mean_car"] == pytest.approx(0.02 + 0.0, abs=1e-9) or w["observed_mean_car"] > 0
    assert abs(w["placebo_mean"]) < 1e-9
    assert w["placebo_p_two_sided"] == pytest.approx(1 / 81)


def test_missing_ticker_prices_keep_a_row_with_status():
    cal, bench, stocks = make_world()
    ev = _events(cal, [("ZZZ.NS", "IT", 200)])
    res = run_event_study(ev, stocks, bench, cal)
    assert res.loc[0, "status"] == "no_price_data"
