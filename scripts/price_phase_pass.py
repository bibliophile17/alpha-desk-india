"""One focused pass over the open price-phase items. Read-only. Paste the output back.

  python scripts/price_phase_pass.py
"""
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 90)
runs = sorted(p for p in Path("logs/price_probe").iterdir() if p.is_dir())
latest = runs[-1]
print("Using", latest)

fl = pd.read_csv(latest / "flags.csv")
rev = fl[fl["severity"] == "review"]
print("\n== REVIEW FLAGS (stock extra-session dates and Nifty 100 gaps) ==")
print(rev[["ticker", "date", "check", "detail"]].to_string(index=False))

itc = pd.read_csv(latest / "prices_ITC.NS.csv", parse_dates=["date"]).sort_values("date")
itc["adj_ret"] = itc["adj_close"].pct_change()
w = itc[(itc["date"] >= "2024-12-30") & (itc["date"] <= "2025-02-05")]
print("\n== ITC 2024-12-30..2025-02-05 (demerger check) ==")
print(w[["date", "close", "adj_close", "adj_ret", "dividends", "split_ratio"]].to_string(index=False))
print("largest |adj_ret| in window:", w.loc[w["adj_ret"].abs().idxmax(), ["date", "adj_ret"]].to_dict())

raw = sorted(Path("data/raw").glob("*.csv")) if Path("data/raw").exists() else []
print("\n== official index CSVs in data/raw ==", [p.name for p in raw] or "NONE (comparison not possible yet)")
