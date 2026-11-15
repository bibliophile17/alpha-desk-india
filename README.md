# ALPHA DESK INDIA

An independent, reproducible event study of how Nifty 100 stocks react to quarterly results announcements.
Free tools and public data only. This is an independent research project: it is not institutional research,
it uses no terminal or paid data, and nothing in it is investment advice.

**Status: pilot.** The pipeline runs end to end on real data, but the sample (13 events) is far too small to
support conclusions. See [`reports/research_note.md`](reports/research_note.md) for the full note.

## Research question

Do Nifty 100 stocks show significant abnormal returns after quarterly results announcements, does the effect
differ by sector, and does it persist over 1, 3 and 5 trading days?

## Motivation

Quarterly results are scheduled, company-specific information events, which makes them a standard setting for
event studies. Most published evidence is on other markets; this project builds the machinery to test the question
on Nifty 100 constituents with data anyone can obtain, and to do it in a way that another person can re-run. The aim is
a careful, honest piece of applied quantitative research, including being clear about what a small sample cannot show.

## Dataset and universe

- **Universe:** the current Nifty 100 constituents (NSE list, `data/raw/ind_nifty100list.csv`, 100 companies; built into `config/universe.csv`).
  Using today's constituents for past events introduces survivorship bias.
- **Prices:** daily, 2022-01-03 to 2026-11-13, from yfinance (unofficial). Stocks use dividend-adjusted closes; benchmark is the Nifty 100 price index (`^CNX100`).
  The trading calendar is built from observed Nifty 50 (`^NSEI`) sessions.
- **Announcements:** results announcements with an NSE filing timestamp and a source URL
  (`data/reference/earnings_announcements.csv`). The pilot has 13 events from 13 companies in 10 sectors,
  announced 2026-07-09 to 2026-07-31.
- **No analyst consensus** is used. The project measures reaction to the announcement, not to an earnings surprise.

## Methodology

1. **Event alignment.** Day 0 is the first session the market can react: before 09:15 IST is the same session, after 15:30 IST is the next session, weekends and holidays roll to the next session. Releases during market hours or with no recorded time are excluded from the primary study.
2. **Market model.** OLS of the stock's return on the benchmark's over sessions −130 to −11 (120 sessions, at least 100 usable). Other announcements' reaction days are removed from the estimation window.
3. **Abnormal returns.** AR = actual − (α + β × benchmark). CAR = sum of ARs over [0,+1], [0,+3], [0,+5] and, as robustness, [−1,+1].
4. **Tests.** t-test, Wilcoxon signed-rank, exact sign test and 95% confidence intervals. The primary p-value is date-clustered (cluster = day 0), because firms reporting on the same day share shocks.
5. **Placebo.** All event dates shifted by a common offset (±11 to ±50 sessions, 80 shifts); the observed mean CAR is compared with the placebo means.
6. **Thresholds.** Results need n ≥ 30 overall and n ≥ 15 per sector to be labelled inferential; otherwise they are labelled exploratory. Sector p-values are Holm-adjusted across inferential sectors only.

## Pilot results (exploratory)

13 events, 13 companies, 10 sectors, 9 distinct announcement dates.

| Window | Mean CAR | Median CAR | Clustered p | Wilcoxon p |
|---|---|---|---|---|
| [0,+1] | +0.281% | -0.209% | 0.801 | 0.893 |
| [0,+3] | +0.916% | -0.200% | 0.527 | 0.735 |
| [0,+5] | +0.722% | -0.516% | 0.648 | 0.946 |
| [-1,+1] | -0.323% | -0.730% | 0.716 | 0.735 |

- No window is statistically significant, and the median CAR is negative in all four windows.
- Sector samples (at most 2 events each) are too small for any sector comparison.
- With 13 events on 9 dates the confidence intervals are wide (for [0,+1]: -2.2% to +2.8%).
  **These results do not show that earnings announcements have no effect.** They show only that a single-season pilot cannot detect one.

## Data-quality controls

- **Prices:** checks for missing prices, duplicate dates, extreme returns, suspicious corporate-action adjustments, ticker inconsistencies, session mismatches and late-starting histories. Flagged observations are **logged, never dropped, filled or corrected** (`logs/`).
- **Failed downloads** are never treated as empty datasets; a run with failures exits non-zero.
- **Calendar:** sessions come from observed data; weekday gaps and weekend sessions are listed by `scripts/audit_calendar.py` for manual review against NSE circulars.
- **Events:** duplicates by company and quarter keep the earliest timestamp and log the rest; every row needs a source URL; `scripts/validate_announcements.py` flags unusable rows.
- **Missing values** stay missing: a missing price gives a missing return for that day, never zero.
- **Known open issues** are in [`docs/known_issues.md`](docs/known_issues.md).

## Project architecture

```
src/alphadesk/   prices, validate, tradingcalendar, announcements, eventstudy, inference, placebo,
                 pricefiles, scorecard, notes, store, paper, site
scripts/         fetch_prices, build_universe, import_nse_bulk, add_event, validate_announcements,
                 run_event_study, audit_calendar, compare_index, corporate_action_report,
                 build_paper, build_site, update_status, scorecard, daily_note, build_database
config/          universe.csv, site_config.json
data/reference/  announcements, NSE filing export, calendar audit, holiday list
reports/         event_study/ (CSV and JSON outputs), research_note.md
site/            generated static website
tests/           unit tests (market model, inference, placebo, calendar, alignment, scorecard, site)
.github/workflows/  pipeline.yml (scheduled build and Pages deploy), source_check.yml
```

## Reproducibility

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m pytest -q
python scripts\build_universe.py data\raw\ind_nifty100list.csv
python scripts\fetch_prices.py --universe config\universe.csv --start 2022-01-01
python scripts\validate_announcements.py
python scripts\run_event_study.py --events data\reference\earnings_announcements.csv --prices-dir data\raw\prices --out reports\event_study
python scripts\build_site.py --outputs reports\event_study
```

Each run records library versions, the SHA-256 of the events file and a digest of the price files in `run_metadata.json`.
yfinance values can be revised between downloads, so exact reproduction needs the saved price snapshot.
Pilot run: Python 3.11.3, pandas 3.1.1, numpy 2.4.6, scipy 1.17.1.

## Limitations

- Single reporting season, 13 events, 9 independent dates: very low power, and market-wide moves in the period affect every event.
- Survivorship bias from using current constituents.
- yfinance is unofficial; adjustments were diagnosed against Yahoo itself, not reconciled with NSE corporate actions.
- Calendar gaps and benchmark gaps are logged but not yet verified against official sources. Gaps are excluded, never filled.
- Price-index benchmark against dividend-adjusted stock prices (small mismatch); Nifty 50 robustness run not yet done.
- NSE time-source labels in the events file are not yet documented, and a few events link to the NSE announcements page rather than the individual filing.
- Confounding news, four overlapping windows, daily closing prices only.
- yfinance limitations: no SLA, cloud IPs may be rate-limited, history can be revised, delisted companies are largely unavailable, and index or ticker symbols can change.

## Future research

More quarters and years (so n clears the thresholds and independent dates multiply), reconciliation with NSE data,
alternative benchmarks and estimation windows, consensus-based surprise measures if a free source exists, and sector
comparisons once sector samples allow them.

## Website and automation

`scripts/build_site.py` builds a static site from the saved outputs. `.github/workflows/pipeline.yml` runs the tests, refreshes
prices, rebuilds the site and deploys it to GitHub Pages; if the refresh fails, the site says so and keeps the last good date.
