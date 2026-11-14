"""Compare Yahoo's Nifty 100 series with an official CSV downloaded by hand.
Usage: python scripts\\compare_index.py <official.csv> <prices_IDX_CNX100.csv>"""
import sys

import pandas as pd

off = pd.read_csv(sys.argv[1])
off.columns = [c.strip() for c in off.columns]
print("official columns:", list(off.columns))

o = pd.Series(
    pd.to_numeric(off["Close"], errors="coerce").to_numpy(),
    index=pd.to_datetime(off["Date"].astype(str).str.strip(), dayfirst=True),
).sort_index()
yh = pd.read_csv(sys.argv[2], parse_dates=["date"])
y = yh.set_index("date")["close"].sort_index()

print("non-numeric official closes:", int(o.isna().sum()))
lo, hi = max(o.index.min(), y.index.min()), min(o.index.max(), y.index.max())
o, y = o[lo:hi], y[lo:hi]
print(f"overlap {lo.date()} to {hi.date()}: official {len(o)} rows, yahoo {len(y)} rows")

only_off = sorted(set(o.index) - set(y.index))
only_yh = sorted(set(y.index) - set(o.index))
print("\nIn official, missing from Yahoo:", [d.date().isoformat() for d in only_off])
print("In Yahoo, missing from official:", [d.date().isoformat() for d in only_yh])

common = o.index.intersection(y.index)
rel = (y[common] / o[common] - 1).abs()
print("\nRelative close difference on common dates:")
print(rel.describe())
print("\nDates differing by more than 0.1%:")
print(rel[rel > 0.001])