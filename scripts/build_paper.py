"""Build the research paper HTML from outputs/event_study (print to PDF from a browser).

  python scripts/build_paper.py --allow-draft      -> paper/paper_DRAFT.html
  python scripts/build_paper.py                    -> paper/paper.html (refuses while TODO(author) remains)
"""
import argparse
import json
import sys
from pathlib import Path

from alphadesk.paper import build_paper_html

ap = argparse.ArgumentParser()
ap.add_argument("--outputs", default="outputs/event_study")
ap.add_argument("--out-dir", default="paper")
ap.add_argument("--allow-draft", action="store_true")
a = ap.parse_args()

cfg = {}
if Path("config/site_config.json").exists():
    cfg = json.loads(Path("config/site_config.json").read_text(encoding="utf-8"))
try:
    html = build_paper_html(a.outputs, cfg.get("author", ""), cfg.get("repo_url", ""), a.allow_draft)
except (FileNotFoundError, ValueError) as exc:
    sys.exit(f"NOT BUILT: {exc}")
out = Path(a.out_dir)
out.mkdir(parents=True, exist_ok=True)
target = out / ("paper_DRAFT.html" if a.allow_draft else "paper.html")
target.write_text(html, encoding="utf-8")
print(f"Wrote {target}. Open it in a browser and use Print > Save as PDF (A4).")
