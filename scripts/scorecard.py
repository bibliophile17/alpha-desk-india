"""Thesis scorecard CLI.

  new       publish a thesis file (then COMMIT AND PUSH IT IMMEDIATELY)
  evaluate  evaluate every due thesis that has no outcome yet (outcomes are write-once)
  summary   write outputs/scorecard/scorecard.{json,md}
"""
import argparse
import json
import sys
from pathlib import Path

from alphadesk.pricefiles import load_price_frames, series_of
from alphadesk.scorecard import (NotDue, create_thesis, evaluate_thesis, render_markdown,
                                 summarize_outcomes)
from alphadesk.tradingcalendar import TradingCalendar

THESES, OUTCOMES = Path("theses"), Path("theses/outcomes")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--ticker", required=True)
    n.add_argument("--direction", required=True, choices=["up", "down"])
    n.add_argument("--horizon", type=int, required=True, help="sessions")
    n.add_argument("--min-move", type=float, required=True, help="e.g. 0.03 for 3%%")
    n.add_argument("--benchmark", default=None, help="e.g. ^CNX100 for excess return")
    n.add_argument("--sector", default=None)
    n.add_argument("--thesis", required=True)
    n.add_argument("--evidence", action="append", required=True, help="repeat; include source")
    n.add_argument("--invalidation", required=True)
    for p in (n, sub.add_parser("evaluate")):
        p.add_argument("--prices-dir", default="data/raw/prices")
    sub.add_parser("summary")
    a = ap.parse_args()

    if a.cmd == "summary":
        outs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUTCOMES.glob("*.json"))]
        if not outs:
            print("no outcomes yet")
            return 0
        summ = summarize_outcomes(outs)
        out = Path("outputs/scorecard")
        out.mkdir(parents=True, exist_ok=True)
        (out / "scorecard.json").write_text(json.dumps({"summary": summ, "outcomes": outs}, indent=2))
        md = render_markdown(summ, outs)
        (out / "scorecard.md").write_text(md, encoding="utf-8")
        print(md)
        return 0

    frames = load_price_frames(a.prices_dir)
    cal = TradingCalendar(series_of(frames, "^NSEI", "close").dropna().index)
    if a.cmd == "new":
        path = create_thesis(THESES, ticker=a.ticker, direction=a.direction,
                             horizon_sessions=a.horizon, min_move=a.min_move, thesis=a.thesis,
                             evidence=a.evidence, invalidation=a.invalidation,
                             close_series=series_of(frames, a.ticker, "close"), cal=cal,
                             benchmark=a.benchmark, sector=a.sector)
        print(f"Created {path}\nNOW: git add {path}; git commit -m \"Publish thesis\"; git push")
        print("The outcome is invalid unless it is committed before the first horizon session opens.")
        return 0

    OUTCOMES.mkdir(parents=True, exist_ok=True)
    for p in sorted(THESES.glob("*.json")):
        if (OUTCOMES / p.name).exists():
            continue
        t = json.loads(p.read_text(encoding="utf-8"))
        try:
            bench = (series_of(frames, t["benchmark"], "close")
                     if t.get("benchmark") else None)
            o = evaluate_thesis(p, cal, series_of(frames, t["ticker"], "adj_close"), bench)
        except (NotDue, KeyError) as exc:
            print(f"SKIP {p.name}: {type(exc).__name__}: {exc}")
            continue
        with open(OUTCOMES / p.name, "x", encoding="utf-8") as fh:
            json.dump(o, fh, indent=2)
        print(f"EVALUATED {p.name}: {o['result']} ({o['measured_return']:+.2%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
