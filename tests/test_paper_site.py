import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alphadesk import paper
from alphadesk.paper import build_paper_html, load_outputs
from alphadesk.site import build_site, md_to_html, update_status

ROOT = Path(__file__).resolve().parents[1]
DATES = pd.bdate_range("2022-01-03", periods=420)


def _prices(d: Path, seed=7, n_stocks=40):
    d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    mkt = rng.normal(0, 0.008, len(DATES))
    def write(name, rets, idx):
        px = 100 * np.cumprod(1 + rets)
        df = pd.DataFrame({"date": DATES, "close": px, "retrieved_at": "2026-01-01T00:00:00+00:00"})
        if not idx:
            df["adj_close"] = px
        df.to_csv(d / name, index=False)
    write("prices_IDX_NSEI.csv", mkt, True)
    write("prices_IDX_CNX100.csv", mkt, True)
    for i in range(n_stocks):
        write(f"prices_S{i}.NS.csv", 1.0 * mkt + rng.normal(0, 0.01, len(DATES)), False)


def _events(path: Path, n_stocks=40):
    rows = []
    for i in range(n_stocks):
        rows.append({"ticker": f"S{i}.NS", "company": f"Co {i}", "sector": "IT" if i % 2 else "Banks",
                     "fiscal_quarter": "Q1FY23", "announce_date": str(DATES[200 + i].date()),
                     "announce_time": "08:30", "time_source": "test_fixture"})
    pd.DataFrame(rows).to_csv(path, index=False)


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    base = tmp_path_factory.mktemp("study")
    _prices(base / "prices")
    _events(base / "events.csv")
    out = base / "out"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/run_event_study.py"), "--events", str(base / "events.csv"),
                        "--prices-dir", str(base / "prices"), "--out", str(out), "--min-n-sector", "15"],
                       capture_output=True, text=True, cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stdout + r.stderr
    return base, out


def test_paper_uses_numbers_from_output_files(study):
    _, out = study
    html = build_paper_html(out, "A. Author", "https://example.org/repo", allow_draft=True)
    ov = pd.read_csv(out / "summary_overall.csv")
    prim = ov[ov["window"] == "[0,+1]"].iloc[0]
    assert f"{prim['mean']:+.2%}" in html
    assert f"{int(prim['n'])}" in html
    assert "A. Author" in html and "<svg" in html
    assert "survivorship" in html.lower()


def test_paper_refuses_to_finalise_with_todo(study):
    _, out = study
    with pytest.raises(ValueError, match="TODO"):
        build_paper_html(out)
    assert "TODO(author)" in build_paper_html(out, allow_draft=True)


def test_paper_missing_outputs_raise(tmp_path):
    assert load_outputs(tmp_path)[0] is None
    with pytest.raises(FileNotFoundError):
        build_paper_html(tmp_path, allow_draft=True)


def test_exploratory_labelling_follows_threshold(tmp_path, study):
    base, _ = study
    out = tmp_path / "o"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/run_event_study.py"), "--events", str(base / "events.csv"),
                        "--prices-dir", str(base / "prices"), "--out", str(out), "--min-n", "100"],
                       capture_output=True, text=True, cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stdout + r.stderr
    html = build_paper_html(out, allow_draft=True)
    assert "below the inferential threshold" in html and "Preliminary" in html


def test_html_escaping():
    assert "<script>" not in md_to_html("hello <script>alert(1)</script>")
    assert "<script>" not in paper.table_html(["a"], [["<script>x</script>"]])


def _ctx(study, tmp_path, **kw):
    _, out = study
    return {"outputs_dir": out, "notes_dir": tmp_path / "notes", "theses_dir": tmp_path / "theses",
            "outcomes_dir": tmp_path / "theses/outcomes", "status_path": tmp_path / "status.json",
            "prices_dir": None, **kw}


def test_site_builds_all_pages_with_results(study, tmp_path):
    written = build_site(tmp_path / "site", _ctx(study, tmp_path))
    for slug in ["index", "research", "methodology", "market-monitor", "daily-notes", "scorecard", "data-sources", "about"]:
        assert f"{slug}.html" in written
    research = (tmp_path / "site/research.html").read_text(encoding="utf-8")
    assert "Overall" in research and "<svg" in research
    assert "No theses have been evaluated yet" in (tmp_path / "site/scorecard.html").read_text(encoding="utf-8")


def test_site_without_results_shows_placeholders(tmp_path):
    ctx = {"outputs_dir": tmp_path / "none", "notes_dir": tmp_path / "n", "theses_dir": tmp_path / "t",
           "outcomes_dir": tmp_path / "t/o", "status_path": tmp_path / "s.json", "prices_dir": None}
    build_site(tmp_path / "site", ctx)
    assert "not been run on real data" in (tmp_path / "site/research.html").read_text(encoding="utf-8")
    assert "No published notes yet" in (tmp_path / "site/daily-notes.html").read_text(encoding="utf-8")


def test_failure_banner_and_no_stale_market_snapshot(study, tmp_path):
    update_status(tmp_path / "status.json", True, None, "2026-11-13")
    update_status(tmp_path / "status.json", False, "download failed", None)
    build_site(tmp_path / "site", _ctx(study, tmp_path, refresh_ok=False))
    idx = (tmp_path / "site/index.html").read_text(encoding="utf-8")
    assert "Data refresh failed" in idx and "download failed" in idx
    assert "No market snapshot" in (tmp_path / "site/market-monitor.html").read_text(encoding="utf-8")


def test_no_new_note_banner(study, tmp_path):
    update_status(tmp_path / "status.json", True, None, "2026-11-13")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/2026-11-12.md").write_text("---\ndate: 2026-11-12\n---\n# Note\nbody <b>x</b>", encoding="utf-8")
    build_site(tmp_path / "site", _ctx(study, tmp_path))
    assert "No new note today" in (tmp_path / "site/index.html").read_text(encoding="utf-8")
    page = (tmp_path / "site/note-2026-11-12.html").read_text(encoding="utf-8")
    assert "&lt;b&gt;" in page


def test_scorecard_shows_failed_and_open_theses_escaped(study, tmp_path):
    (tmp_path / "theses/outcomes").mkdir(parents=True)
    (tmp_path / "theses/outcomes/a.json").write_text(json.dumps({
        "id": "t1", "ticker": "AAA.NS", "direction": "up", "result": "failed", "measured_return": -0.04,
        "signed_return": -0.04, "evaluation_session": "2026-10-01"}), encoding="utf-8")
    (tmp_path / "theses/b.json").write_text(json.dumps({
        "id": "t2", "ticker": "BBB.NS", "direction": "down", "horizon_sessions": 5, "published_at": "2026-11-01",
        "thesis": "<script>bad()</script>", "success_rule": "rule", "evidence": ["e1"], "invalidation": "inv"}), encoding="utf-8")
    build_site(tmp_path / "site", _ctx(study, tmp_path))
    page = (tmp_path / "site/scorecard.html").read_text(encoding="utf-8")
    assert "Failed hypotheses" in page and "t1" in page and "-4.00%" in page
    assert "<script>" not in page and "&lt;script&gt;" in page


def test_update_status_semantics(tmp_path):
    p = tmp_path / "s.json"
    update_status(p, True, None, "2026-11-13")
    ok_at = json.loads(p.read_text())["last_successful_update_utc"]
    st = update_status(p, False, "boom", None)
    assert st["last_successful_update_utc"] == ok_at and st["latest_session"] == "2026-11-13"
    assert st["last_failure"]["reason"] == "boom"
    st = update_status(p, True, None, "2026-11-14")
    assert st["last_failure"] is None
