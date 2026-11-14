import json
import os
import shutil
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from alphadesk.scorecard import (NotDue, classify_outcome, create_thesis, evaluate_thesis,
                                 reference_session, render_markdown, summarize_outcomes)
from alphadesk.tradingcalendar import TradingCalendar

IST = ZoneInfo("Asia/Kolkata")
DATES = pd.bdate_range("2024-01-01", periods=60)
CAL = TradingCalendar(DATES)
T = pd.Timestamp
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def dt(s):
    return datetime.fromisoformat(s).replace(tzinfo=IST)


def test_reference_session_rules():
    assert reference_session(dt("2024-01-10T10:00:00"), CAL) == T("2024-01-09")   # before close
    assert reference_session(dt("2024-01-10T15:30:00"), CAL) == T("2024-01-09")   # at close: not yet
    assert reference_session(dt("2024-01-10T18:00:00"), CAL) == T("2024-01-10")   # after close
    assert reference_session(dt("2024-01-13T12:00:00"), CAL) == T("2024-01-12")   # Saturday
    assert reference_session(dt("2024-01-15T09:00:00"), CAL) == T("2024-01-12")   # Monday pre-open


@pytest.mark.parametrize("direction,measured,min_move,expected", [
    ("up", 0.05, 0.03, "success"), ("up", 0.02, 0.03, "inconclusive"),
    ("up", -0.05, 0.03, "failed"), ("up", -0.02, 0.03, "inconclusive"),
    ("down", -0.05, 0.03, "success"), ("down", 0.05, 0.03, "failed"),
    ("up", 0.0, 0.0, "inconclusive"), ("up", 0.001, 0.0, "success"), ("down", 0.001, 0.0, "failed"),
])
def test_outcome_rule(direction, measured, min_move, expected):
    assert classify_outcome(direction, measured, min_move) == expected


def prices(ev_value=105.0, ev_idx=None):
    s = pd.Series(100.0, index=DATES)
    s[CAL.offset("2024-01-10", 3)] = ev_value
    return s


def git(cwd, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def make(tmp_path, direction="up", min_move=0.03, benchmark=None, commit_at="2024-01-10T19:00:00+05:30"):
    git(tmp_path, "init", "-q")
    path = create_thesis(tmp_path, ticker="AAA.NS", direction=direction, horizon_sessions=3,
                         min_move=min_move, thesis="x", evidence=["src: filing"], invalidation="y",
                         close_series=prices(), cal=CAL, benchmark=benchmark,
                         now=dt("2024-01-10T18:00:00"))
    if commit_at:
        git(tmp_path, "add", path.name)
        git(tmp_path, "commit", "-q", "-m", "thesis", date=commit_at)
    return path


def test_thesis_is_write_once_and_ids_do_not_collide(tmp_path):
    kw = dict(ticker="AAA.NS", direction="up", horizon_sessions=3, min_move=0.03, thesis="x",
              evidence=["e"], invalidation="y", close_series=prices(), cal=CAL, now=dt("2024-01-10T18:00:00"))
    p1, p2 = create_thesis(tmp_path, **kw), create_thesis(tmp_path, **kw)
    assert p1 != p2 and json.loads(p1.read_text())["reference_session"] == "2024-01-10"
    assert "SUCCESS if" in json.loads(p1.read_text())["success_rule"]


def test_missing_reference_price_blocks_publication(tmp_path):
    s = prices()
    s[T("2024-01-10")] = np.nan
    with pytest.raises(ValueError):
        create_thesis(tmp_path, ticker="AAA.NS", direction="up", horizon_sessions=3, min_move=0.03,
                      thesis="x", evidence=["e"], invalidation="y", close_series=s, cal=CAL,
                      now=dt("2024-01-10T18:00:00"))


@needs_git
def test_valid_success_and_failure(tmp_path):
    o = evaluate_thesis(make(tmp_path), CAL, prices(105.0))
    assert o["result"] == "success" and o["measured_return"] == pytest.approx(0.05)
    assert o["evaluation_session"] == "2024-01-15" and not o["modified_after_first_commit"]


@needs_git
def test_down_thesis_fails_when_price_rises(tmp_path):
    assert evaluate_thesis(make(tmp_path, direction="down"), CAL, prices(105.0))["result"] == "failed"


@needs_git
def test_benchmark_excess_return_used(tmp_path):
    bench = pd.Series(100.0, index=DATES)
    bench[CAL.offset("2024-01-10", 3)] = 104.0                 # excess = 5% - 4% = 1% < 3%
    o = evaluate_thesis(make(tmp_path, benchmark="^CNX100"), CAL, prices(105.0), bench)
    assert o["measured_return"] == pytest.approx(0.01) and o["result"] == "inconclusive"


@needs_git
def test_commit_after_horizon_start_is_invalid(tmp_path):
    o = evaluate_thesis(make(tmp_path, commit_at="2024-01-11T10:00:00+05:30"), CAL, prices(105.0))
    assert o["result"] == "invalid_committed_after_horizon_start" and o["rule_result_if_valid"] == "success"


@needs_git
def test_uncommitted_thesis_is_invalid(tmp_path):
    assert evaluate_thesis(make(tmp_path, commit_at=None), CAL, prices(105.0))["result"] == "invalid_not_committed"


@needs_git
def test_edit_after_commit_is_ignored_and_flagged(tmp_path):
    path = make(tmp_path)
    t = json.loads(path.read_text())
    t["min_move"] = 0.0                                          # hindsight edit
    t["direction"] = "down"
    path.write_text(json.dumps(t, indent=2) + "\n")
    o = evaluate_thesis(path, CAL, prices(105.0))
    assert o["modified_after_first_commit"] and o["direction"] == "up" and o["result"] == "success"


@needs_git
def test_not_due_and_missing_prices(tmp_path):
    path = make(tmp_path)
    short = TradingCalendar(DATES[:12])                          # calendar ends 2024-01-16; horizon session 2024-01-15 is covered, so due
    assert evaluate_thesis(path, short, prices(105.0))["result"] == "success"
    with pytest.raises(NotDue):
        evaluate_thesis(path, TradingCalendar(DATES[:8]), prices(105.0))   # calendar ends 01-10
    s = prices(105.0)
    s[CAL.offset("2024-01-10", 3)] = np.nan
    with pytest.raises(NotDue):
        evaluate_thesis(path, CAL, s)


def test_summary_counts_and_small_sample_warning():
    mk = lambda r, m, d="up": {"id": r, "ticker": "A", "direction": d, "result": r,
                              "measured_return": m, "signed_return": m if d == "up" else -m,
                              "evaluation_session": "2024-02-01"}
    outs = [mk("success", 0.05), mk("failed", -0.04), mk("inconclusive", 0.01),
            {**mk("invalid_not_committed", 0.5), "result": "invalid_not_committed"}]
    s = summarize_outcomes(outs)
    assert (s["valid_evaluated"], s["successful"], s["failed"], s["inconclusive"],
            s["invalid_or_unverified"]) == (3, 1, 1, 1, 1)
    assert s["hit_rate_decisive"] == pytest.approx(0.5) and s["hit_rate_all_valid"] == pytest.approx(1 / 3)
    assert "NOT evidence of skill" in s["sample_note"]
    assert "Failed hypotheses" in render_markdown(s, outs) and "- A" not in render_markdown(s, [])
