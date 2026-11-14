"""Validation checks. Each returns a list of flag dicts. Nothing is removed,
filled or corrected: flags are prompts for manual review."""
from __future__ import annotations

import pandas as pd


def _flag(ticker, date, check, severity, detail):
    return {
        "ticker": ticker,
        "date": date,
        "check": check,
        "severity": severity,
        "detail": detail,
    }


def check_missing_or_invalid(df, ticker):
    flags = []

    for col in ("open", "high", "low", "close", "adj_close"):
        bad = df[df[col].isna()]
        flags += [
            _flag(ticker, r.date, "missing_price", "review", f"{col} is NaN")
            for r in bad.itertuples()
        ]

        nonpos = df[df[col] <= 0]
        flags += [
            _flag(ticker, r.date, "non_positive_price", "review", f"{col} <= 0")
            for r in nonpos.itertuples()
        ]

    return flags


def check_duplicate_dates(df, ticker):
    dup = df[df.duplicated("date", keep=False)]

    return [
        _flag(ticker, r.date, "duplicate_date", "review",
              "date appears more than once")
        for r in dup.itertuples()
    ]


def check_missing_sessions(df, ticker, benchmark_dates):
    """Compare against Nifty 50 sessions in BOTH directions.

    Benchmark has a row, this series does not -> missing_session (stock) or
    index_session_mismatch (index). This series has a row the benchmark does
    not -> extra_session. Nothing is removed or filled.
    """
    if df.empty:
        return []

    own = set(df["date"])
    lo, hi = df["date"].min(), df["date"].max()
    expected = {d for d in benchmark_dates if lo <= d <= hi}
    is_index = ticker.startswith("^")
    flags = []

    for d in sorted(expected - own):
        if is_index:
            flags.append(_flag(
                ticker, d, "index_session_mismatch", "review",
                "Nifty 50 has a row, but this index does not; "
                "verify against official index historical data."))
        else:
            flags.append(_flag(
                ticker, d, "missing_session", "review",
                "Nifty 50 traded, but stock has no row "
                "(trading halt or data gap?)"))

    for d in sorted(own - set(benchmark_dates)):
        flags.append(_flag(
            ticker, d, "extra_session", "review",
            "this series has a row on a date the Nifty 50 series does not "
            "(special session, or a gap in the Nifty 50 data?)"))

    return flags


def _split_near(d, idx, window=3):
    """True if a split/bonus is recorded within `window` rows of row idx."""
    lo = max(0, idx - window)
    hi = min(len(d) - 1, idx + window)

    seg = d.loc[lo:hi]

    return bool(
        ((seg["split_ratio"] > 0) & (seg["split_ratio"] != 1)).any()
    )


def check_extreme_returns(df, ticker, threshold=0.15):
    d = df.sort_values("date").reset_index(drop=True)
    ret = d["adj_close"].pct_change()

    flags = []

    for i in d.index[(ret.abs() > threshold).to_numpy()]:
        near = "yes" if _split_near(d, i) else "no"

        flags.append(
            _flag(
                ticker,
                d.at[i, "date"],
                "extreme_return",
                "review",
                f"adj_close return {ret[i]:.1%}; "
                f"split recorded within 3 rows: {near}"
            )
        )

    return flags


def check_corporate_actions(df, ticker, factor_tol=0.0005,
                            div_rel_tol=0.25, div_min_yield=0.0005):
    """DIAGNOSTICS, not proof. Close is (as far as we know) split-adjusted;
    Adj Close additionally reflects dividends. Flags prompt manual review.

    Dividend check: the recorded yield (dividend / prior close) must match the
    yield implied by the Adj Close / Close factor within div_rel_tol of the
    recorded yield, on the recorded row or one row either side (Yahoo's date
    alignment can differ by a session). Yields below div_min_yield are
    reported as untestable, because price rounding is the same size as the
    adjustment.
    """
    d = df.sort_values("date").reset_index(drop=True)
    flags = []

    close_ret = d["close"].pct_change()
    factor = d["adj_close"] / d["close"]

    has_split = (d["split_ratio"] > 0) & (d["split_ratio"] != 1)
    has_div = d["dividends"] > 0

    # 1. Splits: log each; look for the UNADJUSTED pattern on the day or +/-1 row.
    for i in d.index[has_split.to_numpy()]:
        ratio = d.at[i, "split_ratio"]

        flags.append(
            _flag(ticker, d.at[i, "date"], "split_recorded", "info",
                  f"split_ratio={ratio}")
        )

        implied = 1 / ratio - 1                      # e.g. -50% for a 2:1 split

        for j in range(max(0, i - 1), min(len(d) - 1, i + 1) + 1):
            if abs(close_ret[j] - implied) < 0.25 * abs(implied):
                flags.append(
                    _flag(
                        ticker,
                        d.at[j, "date"],
                        "split_diagnostic_unadjusted_pattern",
                        "review",
                        f"close return {close_ret[j]:.1%} resembles "
                        f"unadjusted drop {implied:.1%}; "
                        "may be coincidence, not proof"
                    )
                )
                break

    # 2. Dividends.
    for i in d.index[has_div.to_numpy()]:
        flags.append(
            _flag(ticker, d.at[i, "date"], "dividend_recorded", "info",
                  f"dividend={d.at[i, 'dividends']}")
        )

        if i == 0:
            continue

        expected = d.at[i, "dividends"] / d.at[i - 1, "close"]

        if pd.isna(expected):
            flags.append(
                _flag(ticker, d.at[i, "date"], "dividend_untestable", "review",
                      "prior close missing; cannot test")
            )
            continue

        if expected < div_min_yield:
            flags.append(
                _flag(
                    ticker, d.at[i, "date"], "dividend_untestable", "info",
                    f"recorded yield {expected:.3%} is below "
                    f"{div_min_yield:.3%}; too small to distinguish "
                    "from price rounding"
                )
            )
            continue

        implied = {
            j: 1 - factor[j - 1] / factor[j]
            for j in range(max(1, i - 1), min(len(d) - 1, i + 1) + 1)
        }
        best = min(implied, key=lambda j: abs(implied[j] - expected))

        if abs(implied[best] - expected) > div_rel_tol * expected:
            flags.append(
                _flag(
                    ticker,
                    d.at[i, "date"],
                    "dividend_adjustment_mismatch",
                    "review",
                    f"recorded yield {expected:.3%}; closest "
                    f"adjustment-implied yield {implied[best]:.3%} "
                    f"(rows {i - 1} to {i + 1})"
                )
            )

    # 3. Factor changes with no recorded event within +/-1 row.
    near_event = (
        (has_div | has_split)
        .astype(int)
        .rolling(3, center=True, min_periods=1)
        .max()
        .astype(bool)
    )

    change = factor.pct_change().abs()
    odd = d[(change > factor_tol) & ~near_event]

    flags += [
        _flag(
            ticker,
            r.date,
            "adjustment_factor_jump",
            "review",
            f"adj/close ratio moved {change[r.Index]:.4%}, "
            "no recorded action nearby"
        )
        for r in odd.itertuples()
    ]

    return flags


def check_ticker_consistency(
    df, ticker, requested_start, requested_end, max_gap_days=10
):
    flags = []

    is_index = ticker.startswith("^")

    if not is_index and not ticker.endswith(".NS"):
        flags.append(
            _flag(ticker, None, "ticker_suffix", "review",
                  "stock ticker does not end with .NS")
        )

    if (df["ticker"] != ticker).any():
        flags.append(
            _flag(ticker, None, "ticker_mismatch", "review",
                  "returned rows carry a different ticker")
        )

    if df.empty:
        flags.append(
            _flag(ticker, None, "empty_history", "review",
                  "no price observations returned")
        )
        return flags

    first = df["date"].min()
    last = df["date"].max()

    if first > pd.Timestamp(requested_start) + pd.Timedelta(days=max_gap_days):
        flags.append(
            _flag(
                ticker,
                first,
                "history_starts_late",
                "review",
                f"first row {first.date()}, requested {requested_start} "
                "(recent listing, ticker change, or data gap)"
            )
        )

    if last < pd.Timestamp(requested_end) - pd.Timedelta(days=max_gap_days):
        flags.append(
            _flag(
                ticker,
                last,
                "history_ends_early",
                "review",
                f"last row {last.date()} "
                "(delisting, ticker change, or stale data)"
            )
        )

    return flags


def run_all_checks(df, ticker, benchmark_dates, start, end):
    flags = []

    flags += check_missing_or_invalid(df, ticker)
    flags += check_duplicate_dates(df, ticker)

    if benchmark_dates is not None:
        flags += check_missing_sessions(df, ticker, benchmark_dates)

    flags += check_extreme_returns(df, ticker)
    flags += check_corporate_actions(df, ticker)
    flags += check_ticker_consistency(df, ticker, start, end)

    return flags