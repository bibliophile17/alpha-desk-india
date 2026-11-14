"""Research paper builder. Every number comes from outputs/event_study files; nothing is typed in.

Static text (motivation, method, limitations) describes what the code does. The
interpretation section is left as TODO(author): the paper cannot be built as final
until the author writes it.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TODO = "TODO(author)"
PRIMARY = "[0,+1]"
OUT_FILES = ["run_metadata.json", "summary_overall.csv", "summary_by_sector.csv", "placebo.csv",
             "avg_ar_profile.csv", "results_by_event.csv", "events_aligned.csv"]


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def pct(v, signed=True) -> str:
    return "n/a" if v is None or pd.isna(v) else (f"{v:+.2%}" if signed else f"{v:.2%}")


def pv(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.3f}"


def cnt(v) -> str:
    return "n/a" if v is None or pd.isna(v) else str(int(v))


def load_outputs(d):
    d = Path(d)
    missing = [f for f in OUT_FILES if not (d / f).exists()]
    if missing:
        return None, missing
    data = {"meta": json.loads((d / "run_metadata.json").read_text(encoding="utf-8"))}
    for key, f in (("overall", "summary_overall"), ("sector", "summary_by_sector"),
                   ("placebo", "placebo"), ("profile", "avg_ar_profile"),
                   ("results", "results_by_event"), ("events", "events_aligned")):
        data[key] = pd.read_csv(d / f"{f}.csv")
    return data, []


def table_html(headers, rows) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def _ci(r):
    lo = r["cluster_ci_low"] if pd.notna(r.get("cluster_ci_low")) else r.get("ci_low")
    hi = r["cluster_ci_high"] if pd.notna(r.get("cluster_ci_high")) else r.get("ci_high")
    return "n/a" if pd.isna(lo) or pd.isna(hi) else f"[{lo:+.2%}, {hi:+.2%}]"


def overall_table(df) -> str:
    rows = [[r.window, cnt(r.n), cnt(r.n_clusters), pct(r["mean"]), pct(r["median"]),
             pct(r.pos_share, False), _ci(r), pv(r.t_p), pv(r.cluster_p), pv(r.wilcoxon_p),
             pv(r.sign_p), r.label] for _, r in df.iterrows()]
    return table_html(["Window", "n", "Date clusters", "Mean CAR", "Median", "% positive",
                       "95% CI (clustered)", "t p", "Clustered p", "Wilcoxon p", "Sign p", "Status"], rows)


def sector_table(df, window=None) -> str:
    d = df if window is None else df[df["window"] == window]
    if d.empty:
        return "<p>No sector results.</p>"
    rows = [[r.sector, r.window, cnt(r.n), cnt(r.n_clusters), pct(r["mean"]), pv(r.cluster_p),
             pv(r.p_holm), r.label] for _, r in d.iterrows()]
    return table_html(["Sector", "Window", "n", "Date clusters", "Mean CAR", "Clustered p",
                       "Holm-adjusted p", "Status"], rows)


def placebo_table(df) -> str:
    rows = [[r.window, pct(r.observed_mean_car), pct(r.placebo_mean), pct(r.placebo_sd, False),
             cnt(r.n_shifts_used), pv(r.placebo_p_two_sided)] for _, r in df.iterrows()]
    return table_html(["Window", "Observed mean CAR", "Placebo mean", "Placebo s.d.",
                       "Placebo shifts", "Two-sided p"], rows)


def ar_svg(profile) -> str:
    p = profile.dropna(subset=["mean_ar"])
    if p.empty:
        return ""
    W, H, pad = 560, 230, 40
    n = len(p)
    bw = (W - 2 * pad) / n
    m = max(float(p["mean_ar"].abs().max()), 1e-9)
    zero, scale = H / 2, (H / 2 - 38) / m
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Average abnormal return by event day" '
             f'class="chart"><title>Average abnormal return by event day</title>',
             f'<line x1="{pad}" y1="{zero}" x2="{W - pad}" y2="{zero}" class="axis"/>']
    for i, (k, v) in enumerate(zip(p["day"], p["mean_ar"])):
        h = abs(v) * scale
        x = pad + i * bw + bw * 0.18
        y = zero - h if v >= 0 else zero
        ty = y - 5 if v >= 0 else y + h + 14
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.64:.1f}" height="{max(h, 0.5):.1f}" class="bar"/>')
        parts.append(f'<text x="{x + bw * 0.32:.1f}" y="{ty:.1f}" text-anchor="middle" class="lbl">{v:+.2%}</text>')
        parts.append(f'<text x="{x + bw * 0.32:.1f}" y="{H - 8}" text-anchor="middle" class="lbl">{int(k):+d}</text>')
    return "".join(parts) + "</svg>"


def verdict(row, alpha=0.05) -> str:
    if not str(row["label"]).startswith("inferential"):
        return "descriptive only (sample below the inferential threshold)"
    use_cluster = pd.notna(row.get("cluster_p"))
    p = row["cluster_p"] if use_cluster else row["t_p"]
    kind = "date-clustered " if use_cluster else ""
    word = "distinguishable" if p < alpha else "not distinguishable"
    return f"{word} from zero at the 5% level ({kind}p = {pv(p)})"


METHOD_HTML = """
<h3>Event identification and timestamps</h3>
<p>Each quarterly-results announcement is assigned to day 0, the first session in which the market can react.
Announcements before 09:15 IST count on the same session; announcements after 15:30 IST count on the next session;
weekend and holiday announcements roll to the next session. Announcements released between 09:15 and 15:30, and
announcements with no recorded time on a trading day, are excluded from the primary study because daily closing
prices cannot isolate an intraday reaction. Sessions are taken from observed exchange data, never inferred from
calendar days. Duplicate company-quarter rows keep the earliest timestamp and the rest are logged.</p>
<h3>Market model</h3>
<p>Expected returns follow R<sub>i,t</sub> = &alpha;<sub>i</sub> + &beta;<sub>i</sub> R<sub>m,t</sub> + &epsilon;<sub>i,t</sub>,
estimated by ordinary least squares on sessions [-130, -11] relative to day 0 (120 sessions, at least 100 usable). The
estimation window ends ten sessions before the event so the event's own reaction cannot leak into &alpha; and &beta;.
Reaction days [-1, +5] of the same company's other announcements are removed from its estimation window. Abnormal
return is AR<sub>i,t</sub> = R<sub>i,t</sub> &minus; (&alpha;&#770;<sub>i</sub> + &beta;&#770;<sub>i</sub> R<sub>m,t</sub>);
cumulative abnormal return is CAR<sub>i</sub>[a,b] = &Sigma;<sub>t=a..b</sub> AR<sub>i,t</sub>. A single AR is one day's
surprise relative to the model; a CAR accumulates those daily surprises over the window. Returns are simple daily
returns of dividend-adjusted closes (stocks) and of the price-index close (benchmark). Missing prices give missing
returns; nothing is filled or set to zero.</p>
<h3>Event windows and tests</h3>
<p>CARs are computed over [0,+1], [0,+3], [0,+5] and, as a robustness window, [-1,+1]. The windows are nested and
overlapping, so their results are not independent. Across events we report a one-sample t-test (sensitive to outliers
and non-normality), a Wilcoxon signed-rank test (assumes a symmetric distribution), an exact sign test (ignores
magnitude) and 95% confidence intervals. Companies reporting on the same day share market and sector shocks, so the
primary p-value is date-clustered (cluster = day 0, G&minus;1 degrees of freedom); it is unreliable when the number of
date clusters is small. A common-shift placebo moves every event date by the same offset (&plusmn;11 to &plusmn;50
sessions, 80 shifts), re-runs the pipeline, and compares the real mean CAR with the 80 placebo means (two-sided empirical
p); it preserves same-day clustering but not within-company time-series dependence. Results need at least 30 events
overall and 15 per sector to be labelled inferential; otherwise they are descriptive. Sector p-values are Holm-adjusted
across inferential sectors only. Statistical significance is not economic significance and does not imply a profitable
trading strategy.</p>
"""

LIMITS_HTML = """
<ul>
<li><b>Survivorship bias.</b> The universe is the current Nifty 100 constituent list applied to history; it does not
represent past index membership.</li>
<li><b>Data source.</b> Prices come from yfinance, an unofficial wrapper; adjustments for splits, bonuses and dividends
were diagnosed but not independently reconciled with exchange data, and demergers and similar actions may not be modelled.</li>
<li><b>Benchmark gaps.</b> Where the benchmark series lacks a session, that day is dropped from estimation and any event
window touching it is voided rather than filled.</li>
<li><b>Announcement timing.</b> Day 0 depends on the recorded announcement time; closing-auction effects for releases near
15:30 are not modelled.</li>
<li><b>Confounding.</b> Market-wide, sector-wide and company-specific news in the same window is not separated from results.</li>
<li><b>Daily data.</b> Closing prices cannot isolate intraday reactions.</li>
<li><b>Multiple testing.</b> Four overlapping windows and several sectors are examined; unadjusted p-values overstate evidence.</li>
<li><b>Earnings measure.</b> No analyst consensus is used; this study measures reaction to the announcement, not to an earnings surprise.</li>
</ul>
<p>Future work: historical index membership, an official-data reconciliation of prices, consensus-based surprises,
intraday data, alternative benchmarks and estimation windows.</p>
"""


def build_paper_html(outputs_dir, author="", repo_url="", allow_draft=False, now=None) -> str:
    data, missing = load_outputs(outputs_dir)
    if data is None:
        raise FileNotFoundError(f"cannot build the paper without results; missing: {missing}")
    m, ov, se, pl, pr = data["meta"], data["overall"], data["sector"], data["placebo"], data["profile"]
    res, ev = data["results"], data["events"]
    ok = res[res["status"].isin(["ok", "partial_missing_event_prices"])]
    prim = ov[ov["window"] == PRIMARY].iloc[0]
    prim_pl = pl[pl["window"] == PRIMARY]
    n_companies = int(ok["ticker"].nunique())
    d0, d1 = pd.to_datetime(ok["announce_date"]).min().date(), pd.to_datetime(ok["announce_date"]).max().date()
    status_label = "Preliminary: " if not str(prim["label"]).startswith("inferential") else ""
    tcc = m.get("timing_class_counts", {})
    excl = {k: v for k, v in tcc.items() if k not in ("pre_market", "after_market", "non_session_day")}
    ts_counts = ev["time_source"].fillna("not recorded").value_counts().to_dict()
    guards = []
    if cnt(prim["n_clusters"]) != "n/a" and prim["n_clusters"] < 10:
        guards.append(f"Only {cnt(prim['n_clusters'])} distinct announcement dates: date-clustered p-values are unreliable.")
    if not str(prim["label"]).startswith("inferential"):
        guards.append(f"The overall sample (n = {cnt(prim['n'])}) is below the inferential threshold of "
                      f"{m['min_n_overall']}; results are descriptive.")
    p_pl = prim_pl["placebo_p_two_sided"].iloc[0] if len(prim_pl) else np.nan
    abstract = (
        f"{status_label}We study {cnt(prim['n'])} usable quarterly-results announcements by {n_companies} companies "
        f"({d0} to {d1}). Over the window {PRIMARY}, the mean cumulative abnormal return is {pct(prim['mean'])} "
        f"(95% CI {_ci(prim)}), {verdict(prim)}; the common-shift placebo two-sided p is {pv(p_pl)}. "
        f"Benchmark: {m['benchmark']}; returns: {m['price_col']}.")
    g = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    sec_win = se[se["window"] == PRIMARY] if len(se) else se
    body = f"""
<h1>Market Reactions to Quarterly Earnings Announcements in Indian Equities: Evidence from the Nifty 100</h1>
<p class="meta">{esc(author)} &middot; independent research, not institutional research or investment advice &middot; generated {esc(g)}{' &middot; <b>DRAFT</b>' if TODO in LIMITS_HTML or allow_draft else ''}</p>
<h2>Abstract</h2><p>{esc(abstract)}</p>
{''.join(f'<p class="warn">{esc(x)}</p>' for x in guards)}
<h2>1. Research question and motivation</h2>
<p>Do Nifty 100 stocks show significant abnormal returns after quarterly results announcements, does the effect differ by
sector, and does it persist over 1, 3 and 5 trading days? An event study isolates the part of a stock's return not
explained by the market, so the reaction to the announcement can be measured without attributing general market moves to it.</p>
<h2>2. Universe and data</h2>
<p>{cnt(m['events_loaded'])} announcement rows were loaded, {cnt(m['events_after_dedup'])} remained after de-duplication and
{cnt(m['events_eligible'])} were eligible after timestamp alignment; {cnt(prim['n'])} had complete price data for the primary window.
Excluded by timing class: {esc(json.dumps(excl)) if excl else 'none'}. Announcement time sources: {esc(json.dumps(ts_counts))}.
Prices: yfinance (saved CSVs); sessions: observed {esc(m['calendar'])} dates ({esc(m['calendar_range'][0])} to {esc(m['calendar_range'][1])}).</p>
<h2>3-5. Methodology</h2>{METHOD_HTML}
<h2>6. Overall results</h2>
<p>CAR by window; n is the number of events and clusters the number of distinct day-0 dates.</p>{overall_table(ov)}
<h3>Average abnormal return by event day</h3>{ar_svg(pr)}
<h2>7. Sector results ({esc(PRIMARY)})</h2>{sector_table(sec_win)}
<p>Sectors below {m['min_n_sector']} events are descriptive only.</p>
<h2>8. Robustness and placebo tests</h2>{placebo_table(pl)}
<p>This run uses benchmark {esc(m['benchmark'])}; alternative-benchmark and estimation-window sensitivity runs are not included here.</p>
<h2>9. Interpretation</h2>
<p>{TODO}: write what these results do and do not support, referring to sample sizes, clustering and the placebo
comparison above, and what would change your reading.</p>
<h2>10. Limitations and future research</h2>{LIMITS_HTML}
<h2>Reproducibility</h2>
<p>Run {esc(m['run_at_utc'])}; python {esc(m['python'])}, pandas {esc(m['pandas'])}, numpy {esc(m['numpy'])}, scipy {esc(m['scipy'])}.
Events file sha256 {esc(m['events_file_sha256'][:16])}; price files digest {esc(m['price_files_sha256'][:16])}.
Estimation window {esc(m['estimation_window'])}, minimum usable estimation days {m['min_est_obs']}.
{('Code: ' + esc(repo_url)) if repo_url else ''}</p>"""
    if TODO in body and not allow_draft:
        raise ValueError(f"{TODO} remains in the paper; write section 9 or build with --allow-draft")
    return PAPER_SHELL.replace("{{BODY}}", body)


PAPER_SHELL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Alpha Desk India research paper</title>
<style>
body{font:11pt/1.45 Georgia,serif;max-width:760px;margin:24px auto;padding:0 16px;color:#111}
h1{font-size:19pt;line-height:1.2}h2{font-size:13pt;margin:18px 0 4px}h3{font-size:11.5pt;margin:12px 0 2px}
.meta{color:#555;font-size:10pt}.warn{background:#fff3cd;padding:6px 10px;border-left:4px solid #e0a800}
table{border-collapse:collapse;font:9pt/1.3 Arial,sans-serif;width:100%}th,td{border:1px solid #bbb;padding:3px 5px;text-align:right}
th:first-child,td:first-child{text-align:left}.scroll{overflow-x:auto}.chart{width:100%;max-width:560px}
.bar{fill:#2b6cb0}.axis{stroke:#777}.lbl{font:10px Arial;fill:#222}
@media print{body{margin:0;max-width:none}@page{size:A4;margin:16mm}}
</style></head><body>{{BODY}}</body></html>"""
