# Known issues and defaults (audit list)

Status: OPEN unless stated. Nothing here is silently fixed or filled.

## Data
1. **Nifty 100 gaps (yfinance `^CNX100`)**: 2024-01-01, 2024-02-19, 2025-01-01, 2025-02-01, 2026-01-01 absent while `^NSEI` has rows. Not verified against official Nifty Indices data. Effect on the study: a benchmark gap removes that day from estimation and voids any event window touching it (no filling).
2. **Stock extra session**: each of 5 sample stocks has 1 row more than `^NSEI`. The date has not been inspected (`extra_session` flag). Possible special session, or a gap in Yahoo's `^NSEI`.
3. **ITC demerger (early Jan 2025)**: Yahoo does not model demergers as far as known. Check for an unflagged price drop (`scripts/price_phase_pass.py`). Events near such dates need exclusion or adjustment.
4. **Corporate-action checks compare Yahoo with Yahoo.** All 31 dividends in 5 stocks were self-consistent; Yahoo split/dividend dates are NOT yet checked against NSE corporate actions. One bhavcopy close spot-check pending.
5. **Earlier unverified recollection**: an Infosys bonus in late 2024 was mentioned in conversation; the data shows no INFY split. Treat as unsupported unless NSE lists one.
6. **Universe = current Nifty 100 constituents** (survivorship bias). Historical membership not available free; disclose in the paper.
7. **Holiday CSV is empty** until manually reviewed against NSE circulars. The calendar itself is built from observed `^NSEI` sessions; weekend special sessions are possible and are listed by `audit_calendar.py`.
8. **Announcement source undecided.** No earnings dates/times collected yet; see decision in chat. Until then the engine runs only on tests (synthetic) and any curated CSV.
9. **Yahoo symbol quirks** for some Nifty 100 names (ticker changes, `&`, `-`): failures are logged by `fetch_prices.py`, not patched silently.

## Methodology defaults (reversible, chosen for speed)
- Stock returns: simple returns of `adj_close` (dividend-adjusted). Benchmark: price index close (small dividend-yield mismatch, ~1%/yr, disclosed). Ex-dividend dates inside event windows should be counted and reported with/without.
- Benchmark default Nifty 100 with gap exclusion; Nifty 50 as robustness check (to run).
- Estimation window [-130,-11], min 100 usable days. Other announcements' reaction days [-1,+5] are removed from a stock's estimation window.
- Announcements at 09:15-15:30 IST and with missing time on trading days are excluded from the primary study; exactly 15:30 counts as in-hours. Closing-price auction effects for 15:00-15:30 releases not modelled.
- Duplicate ticker+quarter: earliest timestamp kept, others logged. An earlier "board meeting intimation" row would wrongly win: curate input rows as results-release timestamps.
- Primary inference: date-clustered t (cluster = day 0, G-1 df). Plain t, Wilcoxon, sign test reported alongside. Few clusters (<~10) make cluster p-values unreliable.
- Placebo: all event dates shifted by the same offset (-50..+50 sessions, |shift|>10): 80 placebo means; two-sided empirical p. Cross-sectional correlation preserved; time-series dependence within a stock is not.
- Sector thresholds: n>=15 sector, n>=30 overall, otherwise "exploratory". Holm adjustment across inferential sectors only.

## Tooling
- GitHub Actions warning: `checkout@v4`, `setup-python@v5`, `upload-artifact@v4` target Node 20; bump after checking each action's releases.
