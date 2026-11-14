"""Static site generator. Pure Python, no JS required. Reads saved outputs only:
nothing is fetched or invented here, and missing data renders as an explicit notice."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from alphadesk import paper
from alphadesk.paper import esc
from alphadesk.scorecard import summarize_outcomes

DEFAULT_CFG = {"site_title": "Alpha Desk India", "author": "Renuka Somwanshi",
               "repo_url": "https://github.com/bibliophile17/alpha-desk-india"}
NAV = [("index", "Home"), ("research", "Research"), ("methodology", "Methodology"),
       ("market-monitor", "Market Monitor"), ("daily-notes", "Daily Notes"),
       ("scorecard", "Scorecard"), ("data-sources", "Data & Sources"), ("about", "About")]
CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--mut:#555;--line:#d9d9d9;--acc:#1f5fa8;--warn:#fff3cd}
@media(prefers-color-scheme:dark){:root{--bg:#14171a;--fg:#e8e8e8;--mut:#a0a0a0;--line:#333;--acc:#7db4f0;--warn:#4a3d10}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,Segoe UI,Arial,sans-serif}
header,main,footer{max-width:980px;margin:0 auto;padding:12px 16px}
nav{display:flex;flex-wrap:wrap;gap:4px 14px;border-bottom:1px solid var(--line);padding-bottom:8px}
nav a{color:var(--acc);text-decoration:none}nav a[aria-current=page]{font-weight:700;border-bottom:2px solid var(--acc)}
h1{font-size:1.6rem;margin:.6em 0 .3em}h2{font-size:1.25rem;margin:1.4em 0 .3em}h3{font-size:1.05rem}
.banner{background:var(--warn);border-left:4px solid #e0a800;padding:8px 12px;margin:10px 0}
.scroll{overflow-x:auto}table{border-collapse:collapse;font-size:.88rem;min-width:100%}
th,td{border:1px solid var(--line);padding:4px 8px;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
.muted{color:var(--mut)}.chart{width:100%;max-width:560px}.bar{fill:var(--acc)}.axis{stroke:var(--mut)}.lbl{font:10px sans-serif;fill:var(--fg)}
details{border:1px solid var(--line);padding:6px 10px;margin:8px 0}footer{color:var(--mut);font-size:.85rem;border-top:1px solid var(--line);margin-top:24px}
"""


def md_to_html(md: str) -> str:
    """Tiny, escaping Markdown subset: front matter, headings, lists, quotes, bold, code, http links."""
    lines = md.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), 0)
        lines = lines[end + 1:]

    def inline(s):
        s = esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        return re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', s)

    out, para, in_list = [], [], False

    def flush():
        nonlocal para, in_list
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        m = re.match(r"^(#{1,4}) (.*)", line)
        if m:
            flush()
            lv = len(m.group(1)) + 1
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>")
        elif line.startswith("- "):
            if para:
                flush()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
        elif line.startswith("> "):
            flush()
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif not line.strip():
            flush()
        else:
            if in_list:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


def layout(title, body, active, cfg, banners=(), generated=None) -> str:
    nav = "".join(f'<a href="{s}.html"{" aria-current=page" if s == active else ""}>{esc(l)}</a>' for s, l in NAV)
    ban = "".join(f'<div class="banner" role="status">{esc(b)}</div>' for b in banners)
    g = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)} | {esc(cfg["site_title"])}</title><style>{CSS}</style></head><body>'
            f'<header><strong>{esc(cfg["site_title"])}</strong><nav>{nav}</nav></header><main>{ban}{body}</main>'
            f'<footer>Independent research project; not institutional research and not investment advice. '
            f'Page generated {esc(g)} (UTC). Pipeline schedules may be delayed.</footer></body></html>')


def update_status(path, ok: bool, reason, latest_session, now=None) -> dict:
    """Keep the last successful update; record failures without erasing it."""
    p = Path(path)
    st = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    if ok:
        st.update(last_successful_update_utc=stamp, latest_session=latest_session, last_failure=None)
    else:
        st.setdefault("last_successful_update_utc", None)
        st.setdefault("latest_session", None)
        st["last_failure"] = {"utc": stamp, "reason": reason or "unknown"}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=2), encoding="utf-8")
    return st


def _read_notes(notes_dir):
    notes = []
    for f in sorted(Path(notes_dir).glob("*.md"), reverse=True) if Path(notes_dir).exists() else []:
        text = f.read_text(encoding="utf-8")
        d = re.search(r"^date: (\S+)", text, re.M)
        pub = re.search(r"^published_at_utc: (\S+)", text, re.M)
        notes.append({"date": d.group(1) if d else f.stem, "published": pub.group(1) if pub else "",
                      "slug": f"note-{f.stem}", "text": text})
    return notes


def _banners(status, notes, refresh_ok):
    b = []
    lf, ok_at = (status or {}).get("last_failure"), (status or {}).get("last_successful_update_utc")
    if not refresh_ok or lf:
        reason = (lf or {}).get("reason", "see the pipeline log")
        b.append(f"Data refresh failed: {reason}. Showing the last successful update "
                 f"({ok_at or 'none recorded'}); nothing below is newer than that.")
    sess = (status or {}).get("latest_session")
    if sess and (not notes or notes[0]["date"] < sess):
        b.append(f"No new note today. Latest published note: {notes[0]['date'] if notes else 'none'}; "
                 f"latest market session in the data: {sess}.")
    return b


def _research_body(out_dir):
    data, missing = paper.load_outputs(out_dir)
    if data is None:
        return None, "<p>No event-study results have been published yet. The study has not been run on real data.</p>"
    ov, se, pl, pr, m = data["overall"], data["sector"], data["placebo"], data["profile"], data["meta"]
    prim = ov[ov["window"] == paper.PRIMARY].iloc[0]
    html = (f"<p class='muted'>Run {esc(m['run_at_utc'])} &middot; benchmark {esc(m['benchmark'])} &middot; "
            f"{esc(m['price_col'])} returns &middot; n and clusters shown with every result.</p>"
            f"<h2>Overall</h2>{paper.overall_table(ov)}<h2>Average abnormal return by event day</h2>{paper.ar_svg(pr)}"
            f"<h2>By sector</h2>{paper.sector_table(se)}<h2>Placebo (common shifts)</h2>{paper.placebo_table(pl)}")
    return prim, html


def _scorecard_body(theses_dir, outcomes_dir):
    outs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(outcomes_dir).glob("*.json"))] \
        if Path(outcomes_dir).exists() else []
    done = {o["id"] for o in outs}
    open_t = []
    for p in sorted(Path(theses_dir).glob("*.json")) if Path(theses_dir).exists() else []:
        t = json.loads(p.read_text(encoding="utf-8"))
        if t.get("id") not in done:
            open_t.append(t)
    h = ["<p>Theses are timestamped, committed to the public repository before their horizon starts, and never edited. "
         "Failed theses stay visible.</p>"]
    if outs:
        s = summarize_outcomes(outs)
        f = lambda v: "n/a" if v is None else f"{v:.1%}"
        h.append(paper.table_html(
            ["Evaluated", "Valid", "Successful", "Failed", "Inconclusive", "Invalid/unverified",
             "Hit rate (decisive)", "Hit rate (all valid)", "Avg direction-adj. return", "Period"],
            [[s["total_theses_evaluated"], s["valid_evaluated"], s["successful"], s["failed"], s["inconclusive"],
              s["invalid_or_unverified"], f(s["hit_rate_decisive"]), f(s["hit_rate_all_valid"]),
              f(s["avg_direction_adjusted_return"]), " to ".join(s["evaluation_period"])]]))
        h.append(f"<p class='banner'>{esc(s['sample_note'])}</p><h2>All outcomes</h2>")
        h.append(paper.table_html(["Id", "Ticker", "Direction", "Result", "Measured return", "Evaluated on"],
                                  [[o["id"], o["ticker"], o["direction"], o["result"],
                                    f"{o['measured_return']:+.2%}", o["evaluation_session"]]
                                   for o in sorted(outs, key=lambda o: o["evaluation_session"], reverse=True)]))
        failed = [o for o in outs if o["result"] == "failed"]
        h.append("<h2>Failed hypotheses</h2>" + ("<ul>" + "".join(
            f"<li>{esc(o['id'])}: {esc(o['ticker'])} {esc(o['direction'])}, measured {o['measured_return']:+.2%}</li>"
            for o in failed) + "</ul>" if failed else "<p>None yet.</p>"))
    else:
        h.append("<p>No theses have been evaluated yet.</p>")
    h.append("<h2>Open theses (not yet evaluated)</h2>")
    if open_t:
        for t in open_t:
            h.append(f"<details><summary>{esc(t['id'])}: {esc(t['ticker'])} {esc(t['direction'])} over "
                     f"{esc(t['horizon_sessions'])} sessions (published {esc(t['published_at'])})</summary>"
                     f"<p>{esc(t['thesis'])}</p><p><b>Success rule:</b> {esc(t['success_rule'])}</p>"
                     f"<p><b>Evidence:</b></p><ul>{''.join(f'<li>{esc(e)}</li>' for e in t['evidence'])}</ul>"
                     f"<p><b>Invalidation:</b> {esc(t['invalidation'])}</p></details>")
    else:
        h.append("<p>None.</p>")
    return "".join(h)


def _market_body(prices_dir, universe_path, refresh_ok):
    if not refresh_ok or not prices_dir or not Path(prices_dir).exists():
        return "<p>No market snapshot: the latest data refresh did not complete, and stale data is not shown as fresh.</p>"
    from alphadesk.notes import market_snapshot
    from alphadesk.pricefiles import load_price_frames, series_of
    from alphadesk.tradingcalendar import TradingCalendar
    try:
        frames = load_price_frames(prices_dir)
        cal = TradingCalendar(series_of(frames, "^NSEI", "close").dropna().index)
        uni = pd.read_csv(universe_path) if universe_path and Path(universe_path).exists() else None
        s = market_snapshot(frames, cal, uni)
    except Exception as exc:                                    # never publish a half-built snapshot
        return f"<p>No market snapshot: {esc(type(exc).__name__)}: {esc(exc)}</p>"
    rows = [[r["index"], f"{r['close']:,.2f}", f"{r['chg_1d']:+.2%}", f"{r['chg_5d']:+.2%}", r["retrieved_at"]]
            if r["available"] else [r["index"], "not available", "", "", ""] for r in s["indices"]]
    h = [f"<p>Market data as of the <b>{s['asof'].date()}</b> close (end-of-day, yfinance, unofficial).</p>",
         paper.table_html(["Index", "Close", "1 session", "5 sessions", "Retrieved (UTC)"], rows)]
    if len(s["sectors"]):
        h.append("<h2>Equal-weighted sector moves (universe stocks; not official sector indices)</h2>")
        h.append(paper.table_html(["Sector", "1-session return", "Stocks"],
                                  [[r.sector, f"{r.mean:+.2%}", int(r.count)] for r in s["sectors"].itertuples()]))
    if len(s["moves"]):
        mv = s["moves"]
        h.append("<h2>Largest moves</h2>" + paper.table_html(
            ["Ticker", "Sector", "1-session return"],
            [[r.ticker, r.sector, f"{r.ret_1d:+.2%}"] for r in list(mv.nlargest(5, "ret_1d").itertuples())
             + list(mv.nsmallest(5, "ret_1d").itertuples())]))
    if s["missing_stocks"]:
        h.append(f"<p class='muted'>No usable prices for the last two sessions: {esc(', '.join(s['missing_stocks']))}</p>")
    return "".join(h)


def _sources_body(ctx, status):
    h = ["<h2>Sources</h2><ul><li>Prices: yfinance (unofficial; end-of-day).</li>"
         "<li>Universe: current Nifty 100 constituents (survivorship bias for historical use).</li>"
         "<li>Announcements: from the curated file or probed source recorded with each event.</li>"
         "<li>Trading sessions: observed exchange dates; holiday list reviewed manually.</li></ul>"]
    st = status or {}
    h.append(f"<h2>Update status</h2><p>Last successful update: {esc(st.get('last_successful_update_utc') or 'none recorded')}"
             f"; latest session: {esc(st.get('latest_session') or 'n/a')}."
             + (f" Last failure: {esc(st['last_failure']['utc'])}: {esc(st['last_failure']['reason'])}" if st.get("last_failure") else "")
             + "</p>")
    logd = Path(ctx.get("fetch_log_dir", "logs/fetch_prices"))
    runs = sorted(p for p in logd.iterdir() if p.is_dir()) if logd.exists() else []
    if runs and (runs[-1] / "summary.json").exists():
        s = json.loads((runs[-1] / "summary.json").read_text(encoding="utf-8"))
        h.append(f"<h2>Coverage (latest local fetch)</h2><p>{s['succeeded']} of {s['requested']} symbols downloaded; "
                 f"{len(s['failures'])} failures; review flags by check: {esc(json.dumps(s.get('review_flags_by_check', {})))}.</p>")
    ki = Path(ctx.get("known_issues", "docs/known_issues.md"))
    if ki.exists():
        h.append("<h2>Known issues and defaults</h2>" + md_to_html(ki.read_text(encoding="utf-8")))
    return "".join(h)


def build_site(out_dir, ctx: dict) -> list:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = {**DEFAULT_CFG, **ctx.get("cfg", {})}
    status = json.loads(Path(ctx["status_path"]).read_text(encoding="utf-8")) \
        if ctx.get("status_path") and Path(ctx["status_path"]).exists() else {}
    refresh_ok = ctx.get("refresh_ok", True)
    notes = _read_notes(ctx.get("notes_dir", "notes/published"))
    banners = _banners(status, notes, refresh_ok)
    prim, research_html = _research_body(ctx.get("outputs_dir", "outputs/event_study"))
    gen = ctx.get("generated")
    pages = {}

    if prim is not None:
        head = (f"<p>Latest study run: mean CAR {esc(paper.PRIMARY)} = <b>{paper.pct(prim['mean'])}</b> "
                f"(n = {paper.cnt(prim['n'])}; {esc(paper.verdict(prim))}).</p>")
    else:
        head = "<p>No study results yet.</p>"
    latest = (f"<p>Latest note: <a href='{notes[0]['slug']}.html'>{esc(notes[0]['date'])}</a></p>"
              if notes else "<p>No published notes yet.</p>")
    pages["index"] = ("Home", f"<h1>{esc(cfg['site_title'])}</h1><p>An independent, reproducible study of how Nifty 100 "
                      "stocks react to quarterly results announcements, with timestamped, publicly recorded theses. "
                      "The research paper is the main deliverable; this site is its public interface.</p>"
                      f"<h2>Latest research</h2>{head}<h2>Latest market note</h2>{latest}")
    pages["research"] = ("Research", "<h1>Research</h1><p>Do Nifty 100 stocks show significant abnormal returns after "
                         "quarterly results announcements, does the effect differ by sector, and does it persist over "
                         "1, 3 and 5 trading days?</p>" + research_html +
                         (f"<p><a href='paper.html'>Read the paper</a></p>" if (out / "paper.html").exists() or ctx.get("paper_present") else ""))
    pages["methodology"] = ("Methodology", f"<h1>Methodology</h1>{paper.METHOD_HTML}<h2>Limitations</h2>{paper.LIMITS_HTML}")
    pages["market-monitor"] = ("Market Monitor", "<h1>Market Monitor</h1>" + _market_body(
        ctx.get("prices_dir"), ctx.get("universe"), refresh_ok))
    if notes:
        lst = "<ul>" + "".join(f"<li><a href='{n['slug']}.html'>{esc(n['date'])}</a> "
                               f"<span class='muted'>published {esc(n['published'])}</span></li>" for n in notes) + "</ul>"
    else:
        lst = "<p>No published notes yet.</p>"
    pages["daily-notes"] = ("Daily Notes", f"<h1>Daily Notes</h1>{lst}")
    pages["scorecard"] = ("Scorecard", "<h1>Scorecard</h1>" + _scorecard_body(
        ctx.get("theses_dir", "theses"), ctx.get("outcomes_dir", "theses/outcomes")))
    pages["data-sources"] = ("Data & Sources", "<h1>Data &amp; Sources</h1>" + _sources_body(ctx, status))
    pages["about"] = ("About", f"<h1>About</h1><p>Author: {esc(cfg['author'])}. This is an independent research project "
                      "to demonstrate research and quantitative skills. It claims no professional trading experience, "
                      "institutional coverage or terminal data access, and nothing here is investment advice.</p>"
                      f"<p>Code and data pipeline: <a href='{esc(cfg['repo_url'])}'>{esc(cfg['repo_url'])}</a></p>")
    written = []
    for slug, (title, body) in pages.items():
        (out / f"{slug}.html").write_text(layout(title, body, slug, cfg, banners, gen), encoding="utf-8")
        written.append(f"{slug}.html")
    for n in notes:
        (out / f"{n['slug']}.html").write_text(layout(f"Note {n['date']}", md_to_html(n["text"]), "daily-notes",
                                                      cfg, banners, gen), encoding="utf-8")
        written.append(f"{n['slug']}.html")
    return written
