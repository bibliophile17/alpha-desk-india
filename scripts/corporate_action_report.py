"""Print recorded splits/dividends and the price data around each split. Read-only."""
from pathlib import Path

import pandas as pd

latest = sorted(p for p in Path("logs/price_probe").iterdir() if p.is_dir())[-1]
print("Using", latest)

for f in sorted(latest.glob("prices_*.NS.csv")):
    d = pd.read_csv(f, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    d["close_ret"] = d["close"].pct_change()
    d["factor"] = d["adj_close"] / d["close"]
    d["div_yield"] = d["dividends"] / d["close"].shift(1)

    print("\n" + "=" * 70)
    print(d["ticker"].iloc[0])
    splits = d[(d["split_ratio"] > 0) & (d["split_ratio"] != 1)]
    divs = d[d["dividends"] > 0]
    print(f"{len(splits)} split/bonus rows, {len(divs)} dividend rows")
    print(divs[["date", "dividends", "div_yield"]].to_string(index=False))

    for i in splits.index:
        print(f"\nWindow around split on {d.at[i, 'date'].date()}, "
              f"ratio {d.at[i, 'split_ratio']}")
        print(d.loc[max(0, i - 3):i + 3,
                    ["date", "close", "adj_close", "close_ret", "factor"]]
              .to_string(index=False))