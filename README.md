# Alpha Desk India

Independent research project: how Nifty 100 stocks react to quarterly earnings
announcements (event study). Free tools and public data only. This is an
independent research project, not institutional research.

Status: Week 1, data feasibility. Nothing here yet supports research claims.

## Setup (Windows, PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Price probe (Week 1)

`python -m alphadesk.probe_prices` fetches ~3 years of daily prices (window
ends on today's Asia/Kolkata date, exclusive) for five Nifty stocks plus the
Nifty 50 and Nifty 100 indices from yfinance, runs validation checks, and
writes logs. It never drops, fills, or corrects data.

**Output** (`logs/price_probe/<UTC timestamp>/`, also uploaded as a GitHub
Actions artifact):

- `prices_<ticker>.csv`: the data exactly as fetched, in standard columns.
- `flags.csv`: every check result. `severity=review` needs manual
  inspection; `severity=info` only records a dividend or split.
- `summary.json`: run metadata, row counts and date ranges per ticker, and
  all failures by stage (`fetch`, `format`, `processing`, `unclassified`).

**Exit code:** 0 if every ticker succeeded, 1 otherwise. A failed fetch is
never treated as an empty dataset.

**Limitations of yfinance**

- It is an unofficial wrapper around Yahoo's endpoints: no SLA, it can break
  or change format without notice, and cloud IPs may be rate-limited or blocked.
- Historical values, especially adjusted prices, can be revised between
  downloads, so results are only reproducible from a saved raw snapshot.
- Corporate-action handling (splits, bonuses, dividends) is not guaranteed
  correct. The checks here are diagnostics, not proof of correct adjustment.
- Delisted and merged companies are generally unavailable, which contributes
  to survivorship bias.
- Index symbols (e.g. `^CNX100`) and Indian tickers can change or disappear.

## Project status

- Built and tested: price pipeline with validation, trading calendar, timestamp alignment, market-model event study, inference and placebo tests, scorecard, daily-note generator, paper and site generators, scheduled pipeline.
- Not yet done: no verified earnings-announcement dataset exists, so **no research results have been produced**. The paper and site show 'no results yet' until real announcements are added with scripts/add_event.py and validated.
- Known limitations: see docs/known_issues.md (survivorship bias, unofficial Yahoo prices, unverified calendar gaps).
