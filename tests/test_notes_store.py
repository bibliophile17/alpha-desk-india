import numpy as np
import pandas as pd
import pytest

from alphadesk.notes import market_snapshot, publish_problems, render_note
from alphadesk.tradingcalendar import TradingCalendar

DATES = pd.bdate_range("2024-01-01", periods=30)
CAL = TradingCalendar(DATES)


def frame(vals, cols=("close",)):
    df = pd.DataFrame({"date": DATES, "retrieved_at": "2024-02-12T00:00:00+00:00"})
    for c in cols:
        df[c] = vals
    return df


def frames():
    base = np.full(30, 100.0)
    up, dn = base.copy(), base.copy()
    up[-1], dn[-1] = 110.0, 95.0
    idx = base.copy()
    idx[-1], idx[-6] = 102.0, 100.0
    return {"^NSEI": frame(idx), "^CNX100": frame(idx),
            "AAA.NS": frame(up, ("close", "adj_close")), "BBB.NS": frame(dn, ("close", "adj_close")),
            "CCC.NS": frame(up, ("close", "adj_close")).iloc[:-1]}        # stale: lacks last session


UNI = pd.DataFrame({"ticker": ["AAA.NS", "BBB.NS", "CCC.NS"], "sector": ["IT", "IT", "Banks"]})


def test_snapshot_values_and_stale_stock_not_filled():
    snap = market_snapshot(frames(), CAL, UNI)
    nifty = snap["indices"][0]
    assert nifty["available"] and nifty["chg_1d"] == pytest.approx(0.02) and nifty["chg_5d"] == pytest.approx(0.02)
    assert snap["missing_stocks"] == ["CCC.NS"]
    it = snap["sectors"].set_index("sector").loc["IT"]
    assert it["mean"] == pytest.approx((0.10 - 0.05) / 2) and it["count"] == 2
    assert "Banks" not in set(snap["sectors"]["sector"])


def test_missing_index_day_is_reported_not_filled():
    f = frames()
    f["^CNX100"] = f["^CNX100"].iloc[:-1]
    snap = market_snapshot(f, CAL, UNI)
    assert not snap["indices"][1]["available"]
    assert "not available" in render_note(snap)


def test_draft_cannot_be_published_until_author_writes_it():
    snap = market_snapshot(frames(), CAL, UNI)
    text = render_note(snap)
    assert "status: DRAFT" in text and "TODO(author)" in text
    probs = publish_problems(text, snap["asof"], CAL.last)
    assert any("TODO(author)" in p for p in probs)
    filled = text.replace("TODO(author)", "written")
    assert publish_problems(filled, snap["asof"], CAL.last) == []
    stale = publish_problems(filled, CAL.offset(CAL.last, -1), CAL.last)
    assert any("stale" in p for p in stale)


def test_announcements_for_the_day_are_listed():
    ann = pd.DataFrame({"ticker": ["AAA.NS"], "fiscal_quarter": ["Q2"], "announce_date": [CAL.last],
                        "announce_time": ["16:05"], "source_url": ["https://example.invalid/filing"]})
    assert "AAA.NS Q2" in render_note(market_snapshot(frames(), CAL, UNI, ann))


def test_store_roundtrip(tmp_path):
    pytest.importorskip("duckdb")
    pytest.importorskip("pyarrow")
    import duckdb
    from alphadesk.store import build_database
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", None, "z"]})
    counts = build_database(tmp_path / "t.duckdb", {"demo": df}, tmp_path / "pq")
    assert counts == {"demo": 3} and (tmp_path / "pq" / "demo.parquet").exists()
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    assert con.execute("SELECT SUM(a) FROM demo").fetchone()[0] == 6
    con.close()
    with pytest.raises(ValueError):
        build_database(tmp_path / "t.duckdb", {"bad name": df})
