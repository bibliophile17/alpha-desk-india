"""Daily note DRAFT generator.

Automates only what can be verified from saved data: index snapshot, equal-weighted
sector moves, biggest movers, same-day results announcements. Interpretation is left
as TODO(author) blocks: a note cannot be published until the author writes them, and
never if the data is not from the latest session.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from alphadesk.tradingcalendar import TradingCalendar

TODO = "TODO(author)"


def _s(frames, tk, col):
    s = frames[tk].set_index("date")[col]
    s.index = pd.DatetimeIndex(s.index).normalize()
    return s


def market_snapshot(frames: dict, cal: TradingCalendar, universe=None, announcements=None) -> dict:
    asof, prev, five = cal.last, cal.offset(cal.last, -1), cal.offset(cal.last, -5)
    idx = []
    for tk, label in (("^NSEI", "Nifty 50"), ("^CNX100", "Nifty 100")):
        row = {"index": label, "ticker": tk, "available": False}
        if tk in frames:
            s = _s(frames, tk, "close")
            if all(d in s.index and pd.notna(s[d]) for d in (asof, prev, five)):
                row.update(available=True, close=float(s[asof]), chg_1d=float(s[asof] / s[prev] - 1),
                           chg_5d=float(s[asof] / s[five] - 1),
                           retrieved_at=str(frames[tk]["retrieved_at"].iloc[-1]))
        idx.append(row)

    sector_of = {} if universe is None else dict(zip(universe["ticker"], universe["sector"]))
    moves, missing = [], []
    for tk, df in frames.items():
        if tk.startswith("^"):
            continue
        s = _s(frames, tk, "adj_close")
        if asof in s.index and prev in s.index and pd.notna(s[asof]) and pd.notna(s[prev]):
            moves.append({"ticker": tk, "sector": sector_of.get(tk, "Unknown"),
                          "ret_1d": float(s[asof] / s[prev] - 1)})
        else:
            missing.append(tk)
    mv = pd.DataFrame(moves, columns=["ticker", "sector", "ret_1d"])
    sectors = (mv.groupby("sector")["ret_1d"].agg(["mean", "count"]).reset_index()
               .sort_values("mean", ascending=False) if len(mv) else pd.DataFrame())
    ev = pd.DataFrame()
    if announcements is not None and len(announcements):
        a = announcements.copy()
        a["announce_date"] = pd.to_datetime(a["announce_date"]).dt.normalize()
        ev = a[a["announce_date"] == asof]
    return {"asof": asof, "prev": prev, "indices": idx, "moves": mv, "sectors": sectors,
            "missing_stocks": missing, "events": ev}


def render_note(snap: dict, generated_at: datetime | None = None) -> str:
    g = (generated_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    asof = snap["asof"].date()
    L = ["---", f"date: {asof}", f"generated_at_utc: {g}", "status: DRAFT", "---", "",
         f"# Alpha Desk India: daily note for {asof}", "",
         "## 1. Verified facts (saved yfinance data; unofficial source, end-of-day only)", ""]
    for r in snap["indices"]:
        if r["available"]:
            L.append(f"- {r['index']} closed at {r['close']:,.2f} on {asof} "
                     f"({r['chg_1d']:+.2%} 1-session, {r['chg_5d']:+.2%} 5-session). "
                     f"Data retrieved {r['retrieved_at']}.")
        else:
            L.append(f"- {r['index']}: data not available for {asof} (not filled).")
    ev = snap["events"]
    if len(ev):
        for r in ev.itertuples():
            L.append(f"- Results announced: {r.ticker} {r.fiscal_quarter}, "
                     f"{r.announce_date.date()} {r.announce_time if pd.notna(r.announce_time) else 'time n/a'}"
                     f" (source: {r.source_url if pd.notna(r.source_url) else 'not recorded'}).")
    else:
        L.append("- No results announcements recorded for this date in the announcements file "
                 "(absence of a record is not evidence that none occurred).")
    L += ["", "## 2. Quantitative observations (calculated; equal-weighted, universe stocks only)", ""]
    mv = snap["moves"]
    if len(mv):
        for r in mv.nlargest(5, "ret_1d").itertuples():
            L.append(f"- Top gainer: {r.ticker} {r.ret_1d:+.2%} ({r.sector})")
        for r in mv.nsmallest(5, "ret_1d").itertuples():
            L.append(f"- Top decliner: {r.ticker} {r.ret_1d:+.2%} ({r.sector})")
        L.append("")
        L.append("Equal-weighted 1-session adjusted-close return by sector (not an official sector index):")
        L += [f"- {r.sector}: {r.mean:+.2%} (n={int(r.count)})" for r in snap["sectors"].itertuples()]
    if snap["missing_stocks"]:
        L.append(f"- No usable prices for the last two sessions: {', '.join(snap['missing_stocks'])}")
    L += ["", f"## 3. Observations to monitor (author must write 3-5; {TODO} blocks block publishing)", ""]
    for n in (1, 2, 3):
        L += [f"### Observation {n}",
              f"- What happened: {TODO}", f"- Evidence: {TODO}",
              f"- Why it may matter: {TODO}", f"- Stocks/sectors/instruments affected: {TODO}",
              f"- What would invalidate this interpretation: {TODO}", ""]
    L += ["## 4. Uncertainty and limitations", "",
          "- Prices come from yfinance (unofficial) and have not been reconciled with exchange data.",
          "- End-of-day closes cannot show intraday moves.", f"- {TODO} add any note-specific uncertainty.", ""]
    return "\n".join(L)


def publish_problems(text: str, snap_asof, latest_session) -> list:
    problems = []
    if TODO in text:
        problems.append(f"{text.count(TODO)} {TODO} blocks remain")
    if "status: DRAFT" not in text:
        problems.append("not a draft produced by this tool (status line missing)")
    if pd.Timestamp(snap_asof) != pd.Timestamp(latest_session):
        problems.append(f"note data is for {pd.Timestamp(snap_asof).date()} but latest session is "
                        f"{pd.Timestamp(latest_session).date()} (stale)")
    return problems
