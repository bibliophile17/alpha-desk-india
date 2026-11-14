"""Rebuild data/processed/alphadesk.duckdb (+ Parquet) from saved outputs.

  pip install duckdb pyarrow
  python scripts/build_database.py --prices-dir data/raw/prices
Binary outputs are gitignored; commit only the small CSV/JSON results.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from alphadesk.pricefiles import load_price_frames
from alphadesk.store import build_database

ap = argparse.ArgumentParser()
ap.add_argument("--prices-dir", default="data/raw/prices")
ap.add_argument("--results-dir", default="outputs/event_study")
ap.add_argument("--db", default="data/processed/alphadesk.duckdb")
a = ap.parse_args()

tables = {}
for name in ("events_aligned", "results_by_event", "summary_overall", "summary_by_sector",
             "placebo", "avg_ar_profile"):
    p = Path(a.results_dir) / f"{name}.csv"
    if p.exists():
        tables[name] = pd.read_csv(p)
frames = load_price_frames(a.prices_dir)
tables["prices"] = pd.concat([df.assign(symbol=tk) for tk, df in frames.items()], ignore_index=True)
if Path("config/universe.csv").exists():
    tables["universe"] = pd.read_csv("config/universe.csv")
outs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path("theses/outcomes").glob("*.json"))]
if outs:
    tables["thesis_outcomes"] = pd.DataFrame(outs)
counts = build_database(a.db, tables, Path(a.db).parent / "parquet")
for k, v in counts.items():
    print(f"{k}: {v} rows")
