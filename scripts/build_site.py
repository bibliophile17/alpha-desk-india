"""Build the static site into site/.

  python scripts/build_site.py --prices-dir data/raw/prices
  python scripts/build_site.py --refresh-ok false      (after a failed data refresh)
"""
import argparse
import json
import shutil
from pathlib import Path

from alphadesk.site import build_site

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="site")
ap.add_argument("--prices-dir", default="data/raw/prices")
ap.add_argument("--outputs", default="outputs/event_study")
ap.add_argument("--status", default="site_data/status.json")
ap.add_argument("--refresh-ok", default="true", choices=["true", "false"])
a = ap.parse_args()

cfg = json.loads(Path("config/site_config.json").read_text(encoding="utf-8")) \
    if Path("config/site_config.json").exists() else {}
paper_html = Path("paper/paper.html")
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
if paper_html.exists():
    shutil.copy(paper_html, out / "paper.html")          # only the finished paper is published
written = build_site(out, {"cfg": cfg, "prices_dir": a.prices_dir, "outputs_dir": a.outputs,
                           "status_path": a.status, "universe": "config/universe.csv",
                           "refresh_ok": a.refresh_ok == "true", "paper_present": paper_html.exists()})
print(f"Wrote {len(written)} pages to {out}/ ; open {out / 'index.html'}")
