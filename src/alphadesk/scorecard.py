"""Timestamped research theses and hindsight-resistant evaluation.

Design rules
  * A thesis is one JSON file, created once (never overwritten) and committed to git.
  * The success rule is stored INSIDE the thesis at publication time.
  * Outcomes are separate files; the thesis file is never touched after publication.
  * Evaluation uses the FIRST committed version of the thesis, not the working copy.
  * If the first commit is later than the open of the first horizon session, or the
    file was never committed, the outcome is marked invalid (kept visible, excluded
    from the hit rate).
Limitation: commit timestamps are author-controlled; the strongest public evidence
is when the commit appears on GitHub. This check is necessary, not sufficient.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from alphadesk.announcements import MARKET_CLOSE, MARKET_OPEN
from alphadesk.tradingcalendar import CalendarError, TradingCalendar

IST = ZoneInfo("Asia/Kolkata")
REQUIRED = ["id", "published_at", "ticker", "direction", "horizon_sessions", "min_move",
            "reference_session", "reference_price", "thesis", "evidence", "invalidation",
            "success_rule"]
VALID_RESULTS = ("success", "failed", "inconclusive")


class NotDue(Exception):
    """Thesis cannot be evaluated yet (horizon not reached or prices missing)."""


def validate_thesis(t: dict) -> None:
    missing = [k for k in REQUIRED if k not in t]
    if missing:
        raise ValueError(f"thesis lacks fields {missing}")
    if t["direction"] not in ("up", "down"):
        raise ValueError("direction must be 'up' or 'down'")
    if not isinstance(t["horizon_sessions"], int) or t["horizon_sessions"] < 1:
        raise ValueError("horizon_sessions must be an integer >= 1")
    if not isinstance(t["min_move"], (int, float)) or t["min_move"] < 0:
        raise ValueError("min_move must be >= 0")
    if not isinstance(t["evidence"], list) or not t["evidence"]:
        raise ValueError("evidence must be a non-empty list (with sources)")
    if datetime.fromisoformat(t["published_at"]).tzinfo is None:
        raise ValueError("published_at must include a timezone offset")


def reference_session(published_at: datetime, cal: TradingCalendar) -> pd.Timestamp:
    """Last close already known at publication time (IST).

    Published after 15:30 on a session day -> that day's close; otherwise the
    previous completed session.
    """
    if published_at.tzinfo is None:
        raise ValueError("published_at must be timezone-aware")
    pub = published_at.astimezone(IST)
    d = pd.Timestamp(pub.date())
    if cal.is_session(d) and pub.time() > MARKET_CLOSE:
        return d
    i = cal.sessions.searchsorted(d, side="left") - 1
    if i < 0:
        raise CalendarError("no known session before publication date")
    return cal.sessions[i]


def success_rule_text(direction, min_move, benchmark, horizon, ref) -> str:
    basis = f"excess return versus {benchmark}" if benchmark else "return"
    return (f"Measured {basis} (adjusted close) from the {pd.Timestamp(ref).date()} close to the "
            f"close {horizon} sessions later. SUCCESS if the move is in the '{direction}' "
            f"direction and at least {min_move:.2%}; FAILED if it is against the thesis by at "
            f"least {min_move:.2%}; otherwise INCONCLUSIVE.")


def create_thesis(thesis_dir, *, ticker, direction, horizon_sessions, min_move, thesis,
                  evidence, invalidation, close_series, cal, benchmark=None,
                  sector=None, now=None) -> Path:
    now = now or datetime.now(IST)
    ref = reference_session(now, cal)
    s = close_series.copy()
    s.index = pd.DatetimeIndex(s.index).normalize()
    if ref not in s.index or pd.isna(s[ref]):
        raise ValueError(f"no close for {ticker} on reference session {ref.date()}")
    pub = now.astimezone(IST)
    t = {
        "id": "", "published_at": pub.isoformat(timespec="seconds"), "ticker": ticker,
        "sector": sector, "direction": direction, "horizon_sessions": int(horizon_sessions),
        "min_move": float(min_move), "benchmark": benchmark,
        "reference_session": str(ref.date()), "reference_price": float(s[ref]),
        "thesis": thesis, "evidence": list(evidence), "invalidation": invalidation,
        "success_rule": success_rule_text(direction, min_move, benchmark, horizon_sessions, ref),
    }
    d = Path(thesis_dir)
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", ticker).strip("_")
    seq = 1
    while (d / f"{pub:%Y%m%d}-{safe}-{seq}.json").exists():
        seq += 1
    t["id"] = f"{pub:%Y%m%d}-{safe}-{seq}"
    validate_thesis(t)
    with open(d / f"{t['id']}.json", "x", encoding="utf-8") as fh:     # never overwrite
        json.dump(t, fh, indent=2)
        fh.write("\n")
    return d / f"{t['id']}.json"


def git_first_version(path):
    """First committed version of a file: sha, author time, content, number of commits."""
    p = Path(path)
    try:
        log = subprocess.run(["git", "log", "--format=%H %aI", "--reverse", "--", p.name],
                             cwd=p.parent, capture_output=True, text=True, encoding="utf-8",
                             check=True).stdout.strip().splitlines()
        if not log:
            return None
        sha, ts = log[0].split(" ", 1)
        content = subprocess.run(["git", "show", f"{sha}:./{p.name}"], cwd=p.parent,
                                 capture_output=True, text=True, encoding="utf-8",
                                 check=True).stdout
        return {"sha": sha, "committed_at": datetime.fromisoformat(ts), "content": content,
                "n_commits": len(log)}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def classify_outcome(direction: str, measured: float, min_move: float) -> str:
    signed = measured if direction == "up" else -measured
    if signed > 0 and signed >= min_move:
        return "success"
    if signed < 0 and -signed >= min_move:
        return "failed"
    return "inconclusive"


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n")


def evaluate_thesis(path, cal: TradingCalendar, stock_adj: pd.Series,
                    bench_adj: pd.Series | None = None) -> dict:
    path = Path(path)
    current = _norm(path.read_text(encoding="utf-8"))
    first = git_first_version(path)
    t = json.loads(_norm(first["content"]) if first else current)
    validate_thesis(t)
    ref = pd.Timestamp(t["reference_session"])
    try:
        ev = cal.offset(ref, t["horizon_sessions"])
        first_h = cal.offset(ref, 1)
    except CalendarError as exc:
        raise NotDue(f"horizon not reached in known calendar: {exc}")

    def px(series, d):
        s = series.copy()
        s.index = pd.DatetimeIndex(s.index).normalize()
        if d not in s.index or pd.isna(s[d]):
            raise NotDue(f"missing price on {d.date()}")
        return float(s[d])

    ret = px(stock_adj, ev) / px(stock_adj, ref) - 1
    bret = None
    measured = ret
    if t.get("benchmark"):
        if bench_adj is None:
            raise NotDue(f"benchmark {t['benchmark']} prices not supplied")
        bret = px(bench_adj, ev) / px(bench_adj, ref) - 1
        measured = ret - bret

    result = classify_outcome(t["direction"], measured, t["min_move"])
    cutoff = datetime.combine(first_h.date(), MARKET_OPEN, tzinfo=IST)
    if first is None:
        result_final = "invalid_not_committed"
    elif first["committed_at"] > cutoff:
        result_final = "invalid_committed_after_horizon_start"
    else:
        result_final = result
    return {
        "id": t["id"], "ticker": t["ticker"], "sector": t.get("sector"),
        "direction": t["direction"], "result": result_final, "rule_result_if_valid": result,
        "reference_session": t["reference_session"], "evaluation_session": str(ev.date()),
        "stock_return": ret, "benchmark_return": bret, "measured_return": measured,
        "signed_return": measured if t["direction"] == "up" else -measured,
        "first_commit_sha": first["sha"] if first else None,
        "first_commit_at": first["committed_at"].isoformat() if first else None,
        "horizon_start_cutoff": cutoff.isoformat(),
        "modified_after_first_commit": bool(first and _norm(first["content"]) != current),
        "n_commits": first["n_commits"] if first else 0,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "success_rule": t["success_rule"],
    }


def summarize_outcomes(outcomes: list) -> dict:
    valid = [o for o in outcomes if o["result"] in VALID_RESULTS]
    s = sum(o["result"] == "success" for o in valid)
    f = sum(o["result"] == "failed" for o in valid)
    i = sum(o["result"] == "inconclusive" for o in valid)
    n = len(valid)
    note = ("Fewer than 30 valid theses: the hit rate is NOT evidence of skill."
            if n < 30 else
            "Compare the hit rate with the base rate of the market direction, not with 50%.")
    return {
        "total_theses_evaluated": len(outcomes), "valid_evaluated": n, "successful": s,
        "failed": f, "inconclusive": i, "invalid_or_unverified": len(outcomes) - n,
        "hit_rate_decisive": s / (s + f) if s + f else None,
        "hit_rate_all_valid": s / n if n else None,
        "avg_measured_return": float(np.mean([o["measured_return"] for o in valid])) if n else None,
        "avg_direction_adjusted_return": float(np.mean([o["signed_return"] for o in valid])) if n else None,
        "evaluation_period": [min(o["evaluation_session"] for o in outcomes),
                              max(o["evaluation_session"] for o in outcomes)] if outcomes else None,
        "sample_note": note,
    }


def render_markdown(summary: dict, outcomes: list) -> str:
    pct = lambda v: "n/a" if v is None else f"{v:.1%}"
    lines = ["# Research scorecard", "",
             f"Evaluated: **{summary['total_theses_evaluated']}** | valid: **{summary['valid_evaluated']}** "
             f"| successful: **{summary['successful']}** | failed: **{summary['failed']}** "
             f"| inconclusive: **{summary['inconclusive']}** | invalid/unverified: "
             f"**{summary['invalid_or_unverified']}**", "",
             f"Hit rate (decisive only): {pct(summary['hit_rate_decisive'])} | "
             f"hit rate (all valid): {pct(summary['hit_rate_all_valid'])} | "
             f"avg direction-adjusted return: {pct(summary['avg_direction_adjusted_return'])}",
             f"Evaluation period: {summary['evaluation_period']}", "",
             f"> {summary['sample_note']}", "", "## All outcomes", "",
             "| id | ticker | direction | result | measured return | evaluated on |", "|---|---|---|---|---|---|"]
    for o in sorted(outcomes, key=lambda o: o["evaluation_session"]):
        lines.append(f"| {o['id']} | {o['ticker']} | {o['direction']} | {o['result']} | "
                     f"{o['measured_return']:+.2%} | {o['evaluation_session']} |")
    lines += ["", "## Failed hypotheses (kept visible)", ""]
    failed = [o for o in outcomes if o["result"] == "failed"]
    lines += [f"- {o['id']}: {o['ticker']} {o['direction']}, measured {o['measured_return']:+.2%}"
              for o in failed] or ["- none yet"]
    return "\n".join(lines) + "\n"
