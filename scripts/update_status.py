"""Record the outcome of a data refresh in site_data/status.json (small, committed).

  python scripts/update_status.py --outcome success --prices-dir data/raw/prices
  python scripts/update_status.py --outcome failure
A failure never erases the last successful update.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from alphadesk.site import update_status

ap = argparse.ArgumentParser()
ap.add_argument("--outcome", required=True, choices=["success", "failure"])
ap.add_argument("--prices-dir", default="data/raw/prices")
ap.add_argument("--status", default="site_data/status.json")
ap.add_argument("--fetch-log-dir", default="logs/fetch_prices")
a = ap.parse_args()

session, reason = None, None
if a.outcome == "success":
    f = Path(a.prices_dir) / "prices_IDX_NSEI.csv"
    session = str(pd.read_csv(f, parse_dates=["date"])["date"].max().date())
else:
    logd = Path(a.fetch_log_dir)
    runs = sorted(p for p in logd.iterdir() if p.is_dir()) if logd.exists() else []
    if runs and (runs[-1] / "summary.json").exists():
        s = json.loads((runs[-1] / "summary.json").read_text(encoding="utf-8"))
        first = s["failures"][0] if s["failures"] else {}
        reason = (f"{len(s['failures'])} of {s['requested']} downloads failed; first: "
                  f"{first.get('ticker', '?')} [{first.get('stage', '?')}] {str(first.get('message', ''))[:120]}")
    else:
        reason = "price download step failed before producing a log (see the workflow log)"
print(json.dumps(update_status(a.status, a.outcome == "success", reason, session), indent=2))
