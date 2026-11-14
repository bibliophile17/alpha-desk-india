"""Convert the OFFICIAL Nifty 100 constituents CSV (download from niftyindices.com) into
config/universe.csv.  python scripts/build_universe.py data/raw/ind_nifty100list.csv

Expected columns: Company Name, Industry, Symbol (Series, ISIN Code optional).
These are CURRENT constituents: using them for a historical study carries
survivorship bias and must be disclosed.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

src = Path(sys.argv[1])
df = pd.read_csv(src)
df.columns = [c.strip() for c in df.columns]
need = ["Company Name", "Industry", "Symbol"]
if any(c not in df.columns for c in need):
    sys.exit(f"ERROR: expected columns {need}, found {list(df.columns)}")
uni = pd.DataFrame({
    "ticker": df["Symbol"].astype(str).str.strip() + ".NS",
    "company": df["Company Name"].str.strip(),
    "sector": df["Industry"].str.strip(),
    "isin": df["ISIN Code"] if "ISIN Code" in df.columns else "",
    "source_file": src.name,
    "retrieved_at": datetime.now(timezone.utc).isoformat(),
    "note": "current constituents; survivorship bias for historical use",
})
Path("config").mkdir(exist_ok=True)
uni.to_csv("config/universe.csv", index=False)
print(f"{len(uni)} constituents -> config/universe.csv (expect ~100)")
print(uni["sector"].value_counts().to_string())
