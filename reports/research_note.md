# Pilot research note: market reactions to quarterly results, Nifty 100

**Status: exploratory pilot. This note reports what a small first sample shows. It does not establish whether earnings announcements move Nifty 100 prices.**

Author: Renuka Somwanshi (independent research project; not institutional research; not investment advice).
Code and data pipeline: [github.com/bibliophile17/alpha-desk-india](https://github.com/bibliophile17/alpha-desk-india).
Numbers below are copied programmatically from `reports/event_study/` (run at 2026-11-15T02:56:55 UTC, events file SHA-256 `0537e6c173ef8fe5…`).

## 1. Research question

Do Nifty 100 stocks show significant abnormal returns after quarterly results announcements, does the effect differ by sector, and does it persist over 1, 3 and 5 trading days?

An abnormal return is the part of a stock's return that a simple market model does not explain. If results announcements carry news, abnormal returns should be non-zero on average around the announcement. This pilot checks whether the pipeline can answer that question and what a first sample looks like.

## 2. Summary of the pilot

- **Sample:** 13 announcements by 13 companies in 10 sectors, announced between 2026-07-09 and 2026-07-31 (one reporting season). They fall on 9 distinct announcement dates (day 0).
- **Mean cumulative abnormal return (CAR):** +0.281% over [0,+1], +0.916% over [0,+3], +0.722% over [0,+5] and -0.323% over [-1,+1].
- **Median CAR is negative in all four windows** ([0,+1]: -0.209%, [0,+3]: -0.200%, [0,+5]: -0.516%, [-1,+1]: -0.730%). Only 6 of 13 events have a positive CAR over [0,+1].
- **No statistically significant result.** Date-clustered p-values are 0.801 ([0,+1]), 0.527 ([0,+3]), 0.648 ([0,+5]), 0.716 ([-1,+1]).
- **Sector comparison is not possible.** No sector has more than 2 events; the study requires 15 per sector.
- **All results are exploratory** (n = 13 is below the 30 required for an inferential label).

## 3. Data

- **Universe:** the current Nifty 100 constituent list from NSE (`data/raw/ind_nifty100list.csv`, 100 companies). Using today's list for past events creates survivorship bias.
- **Prices:** daily prices from yfinance (an unofficial Yahoo Finance wrapper), 2022-01-03 to 2026-11-13. Stock returns use dividend-adjusted closes; the benchmark is the Nifty 100 price index (`^CNX100`). The trading calendar is built from observed Nifty 50 (`^NSEI`) session dates.
- **Announcements:** 13 results announcements from NSE corporate-filing records for quarters ending 30 June 2026. Each row has a source URL and a recorded timestamp (time sources recorded as: 7 × `nse_broadcast_time`, 6 × `nse_filing_timestamp`). Three rows carry a link to the NSE announcements page for the symbol rather than to the individual filing. No analyst consensus is used, so nothing here measures an *earnings surprise*.
- **Timing of events:** 12 announcements were released after the 15:30 IST close, so day 0 is the next trading session. 1 was released on a non-trading day (Saturday) and also rolls to the next session. None fell inside market hours, which the primary study would exclude.

## 4. Method

**Event alignment.** Day 0 is the first session in which the market can react. Announcements before 09:15 IST count on the same session; after 15:30 IST, on the next; weekend and holiday announcements roll to the next session. Releases between 09:15 and 15:30 and releases with no recorded time are excluded from the primary study, because daily closes cannot isolate an intraday reaction. Sessions come from observed data, never inferred from calendar days.

**Market model.** For each event, R(i,t) = α + β·R(m,t) + ε is estimated by ordinary least squares over sessions −130 to −11 relative to day 0 (120 sessions; at least 100 usable). The window stops ten sessions before the event so the announcement cannot influence the fitted α and β. Reaction days (−1 to +5) of the same company's other announcements are removed from its estimation window. Missing prices give missing returns; nothing is filled or set to zero. Here 12 of 13 events used 120 estimation days and the minimum was 118; estimated betas range from 0.10 to 1.49.

**Abnormal returns.** AR(t) = R(i,t) − (α̂ + β̂·R(m,t)). CAR over a window is the sum of daily ARs. Windows: [0,+1], [0,+3], [0,+5] and, as a robustness window, [−1,+1]. The windows overlap, so their results are not independent.

**Tests.** For each window the mean CAR is tested with a one-sample t-test, a Wilcoxon signed-rank test and an exact sign test. Because companies reporting on the same date share market and sector shocks, the primary p-value is **date-clustered** (cluster = day 0, G−1 degrees of freedom, with G = 9 clusters here). With few clusters even this p-value is unreliable. Samples below 30 events overall (15 per sector) are labelled exploratory.

**Placebo analysis.** All event dates are shifted by the same offset (±11 to ±50 sessions; 80 shifts), the whole pipeline is re-run, and the observed mean CAR is compared with the 80 placebo means (two-sided empirical p). It preserves same-day clustering but not within-company time dependence.

## 5. Results

### 5.1 Overall

| Window | n | Date clusters | Mean CAR | Median CAR | % positive | 95% CI (clustered) | Clustered p | t-test p | Wilcoxon p | Sign p |
|---|---|---|---|---|---|---|---|---|---|---|
| [0,+1] | 13 | 9 | +0.281% | -0.209% | 46.2% | [-2.20%, +2.77%] | 0.801 | 0.781 | 0.893 | 1.000 |
| [0,+3] | 13 | 9 | +0.916% | -0.200% | 46.2% | [-2.28%, +4.11%] | 0.527 | 0.488 | 0.735 | 1.000 |
| [0,+5] | 13 | 9 | +0.722% | -0.516% | 46.2% | [-2.79%, +4.24%] | 0.648 | 0.612 | 0.946 | 1.000 |
| [-1,+1] | 13 | 9 | -0.323% | -0.730% | 46.2% | [-2.30%, +1.66%] | 0.716 | 0.733 | 0.735 | 1.000 |

All four rows are labelled *exploratory (n<30)*. The 95% confidence interval for the [0,+1] mean CAR runs from -2.20% to +2.77%: it includes zero and spans roughly -2% to +3%. The sample is too small to distinguish "no effect" from "an effect of a few percent".

Means and medians disagree in sign in 3 of 4 windows: a few large positive reactions pull the mean above the median. The two largest [0,+3] CARs are INFY (+10.46%) and TCS (+8.15%). With 13 events, individual stocks can dominate a mean.

### 5.2 Average abnormal return by event day

| Day | Mean AR | n |
|---|---|---|
| -1 | -0.605% | 13 |
| +0 | -0.122% | 13 |
| +1 | +0.404% | 13 |
| +2 | +0.298% | 13 |
| +3 | +0.336% | 13 |
| +4 | -0.089% | 13 |
| +5 | -0.104% | 13 |

Day −1 is negative on average. With 13 events this is descriptive only, and no inference is drawn from it.

### 5.3 Event-level results

| Ticker | Sector | Quarter | Announced (IST) | Timing | Day 0 | Beta | CAR [0,+1] | CAR [0,+3] | CAR [0,+5] | CAR [-1,+1] |
|---|---|---|---|---|---|---|---|---|---|---|
| TCS | Information Technology | Q1FY27 | 2026-07-09 18:36:12 | after_market | 2026-07-10 | 0.69 | +6.32% | +8.15% | +11.86% | +5.95% |
| RELIANCE | Oil Gas & Consumable Fuels | Q1FY27 | 2026-07-17 19:49:06 | after_market | 2026-07-20 | 0.80 | -1.34% | -2.50% | -2.16% | +0.44% |
| HDFCBANK | Financial Services | Q1FY27 | 2026-07-18 14:22:30 | non_session_day | 2026-07-20 | 1.23 | -6.68% | -6.74% | -8.34% | -6.25% |
| INFY | Information Technology | Q1FY27 | 2026-07-23 17:44:46 | after_market | 2026-07-24 | 0.50 | +3.33% | +10.46% | +8.48% | +3.45% |
| NTPC | Power | Q1FY27 | 2026-07-24 19:43:51 | after_market | 2026-07-27 | 0.49 | -1.48% | -1.88% | -1.21% | -1.75% |
| COALINDIA | Oil Gas & Consumable Fuels | Q1FY27 | 2026-07-27 17:50:27 | after_market | 2026-07-28 | 0.10 | -4.22% | -2.00% | -1.32% | -4.33% |
| HINDUNILVR | Fast Moving Consumer Goods | Q1FY27 | 2026-07-28 19:41:55 | after_market | 2026-07-29 | 0.71 | +3.44% | +3.57% | +1.58% | -3.37% |
| LT | Construction | Q1FY27 | 2026-07-28 18:19:59 | after_market | 2026-07-29 | 1.49 | +0.71% | -0.20% | +1.25% | +1.57% |
| ASIANPAINT | Consumer Durables | Q1FY27 | 2026-07-29 18:54:19 | after_market | 2026-07-30 | 0.99 | -1.12% | -1.01% | -1.90% | -1.34% |
| TATASTEEL | Metals & Mining | Q1FY27 | 2026-07-30 19:56:10 | after_market | 2026-07-31 | 1.13 | -0.21% | +1.31% | -1.51% | -0.73% |
| ABB | Capital Goods | Q2FY26 | 2026-07-31 17:24:06 | after_market | 2026-08-03 | 1.05 | +3.85% | +3.32% | +2.67% | +2.85% |
| ITC | Fast Moving Consumer Goods | Q1FY27 | 2026-07-31 17:23:53 | after_market | 2026-08-03 | 0.64 | +2.40% | +1.39% | +0.49% | +0.76% |
| MARUTI | Automobile and Auto Components | Q1FY27 | 2026-07-31 18:27:08 | after_market | 2026-08-03 | 1.15 | -1.34% | -1.95% | -0.52% | -1.46% |

### 5.4 Sectors

Sector results are produced by the pipeline but are not interpretable: every sector has 2 or fewer events and is labelled *insufficient*.

| Sector | Events |
|---|---|
| Information Technology | 2 |
| Fast Moving Consumer Goods | 2 |
| Oil Gas & Consumable Fuels | 2 |
| Automobile and Auto Components | 1 |
| Capital Goods | 1 |
| Construction | 1 |
| Financial Services | 1 |
| Consumer Durables | 1 |
| Metals & Mining | 1 |
| Power | 1 |

### 5.5 Placebo

| Window | Observed mean CAR | Placebo mean | Placebo s.d. | Shifts | Two-sided p |
|---|---|---|---|---|---|
| [0,+1] | +0.281% | -0.166% | 0.464% | 80 | 0.568 |
| [0,+3] | +0.916% | -0.324% | 0.547% | 80 | 0.173 |
| [0,+5] | +0.722% | -0.487% | 0.709% | 80 | 0.383 |
| [-1,+1] | -0.323% | -0.243% | 0.507% | 80 | 0.605 |

All four empirical two-sided placebo p-values are above 0.05 (smallest: 0.173). The placebo comparison gives no evidence that the observed means are unusual relative to arbitrary dates, which is consistent with the clustered tests.

## 6. Interpretation

The pilot **detects no statistically significant abnormal return** around results announcements, in any window, under any of the tests. That is a statement about this sample, not about the market. With 13 events on 9 dates in one reporting season, the clustered standard error for [0,+1] is 1.08 percentage points, so only a large effect could have been detected. The result is therefore **not evidence that earnings announcements have no effect**.

What the pilot does show is that the pipeline runs end to end on real data: NSE timestamps align to sessions, estimation windows are complete, benchmark gaps did not void any event windows (all 13 events have status `ok`), and the statistics and placebo behave as designed.

## 7. Limitations

- **Small, single-season sample.** 13 events, 9 dates, announced between 2026-07-09 and 2026-07-31. Cross-sectional dependence is large relative to the number of independent dates, and any market-wide move during this period affects every event.
- **Survivorship bias.** The universe is today's Nifty 100, not historical membership.
- **Unofficial price data.** yfinance values can be revised, and split/dividend adjustments were diagnosed against Yahoo itself rather than reconciled with NSE corporate actions. Calendar gaps (70 weekday gaps in `^NSEI`, 6 sessions missing from `^CNX100`) are logged in `docs/known_issues.md` and have not been verified against NSE circulars. Gaps are excluded, never filled.
- **Benchmark.** A price index is used against dividend-adjusted stock prices, a small mismatch (roughly the dividend yield). Nifty 50 as an alternative benchmark has not been run.
- **Timing provenance.** Timestamps come from NSE filing records. Two time-source labels are used and their difference is not yet documented in the project files; three events link to the NSE announcements page rather than the individual filing.
- **No consensus data.** The study measures reaction to the announcement, not to a surprise relative to expectations.
- **Confounding.** Other company, sector and market news in the same window is not separated from the results.
- **Multiple windows.** Four overlapping windows are examined; unadjusted p-values would overstate evidence if any had been small.
- **Daily data.** Closing prices cannot show intraday reactions, and late-session releases are not modelled.

## 8. Next steps

1. Extend the sample across several quarters (and historical years) so that n clears the 30-event threshold and the number of independent dates is much larger.
2. Reconcile prices and corporate actions with NSE data and verify calendar gaps against NSE circulars.
3. Run the Nifty 50 benchmark and alternative estimation windows as robustness checks.
4. Document the NSE time-source labels and link every event to its individual filing.
5. Consider consensus-based surprise measures if a free source can be found.

## 9. Reproduce

```powershell
python scripts\fetch_prices.py --universe config\universe.csv --start 2022-01-01
python scripts\validate_announcements.py
python scripts\run_event_study.py --events data\reference\earnings_announcements.csv --prices-dir data\raw\prices --out reports\event_study
```

Run metadata (Python 3.11.3, pandas 3.1.1, numpy 2.4.6, scipy 1.17.1, estimation window (-130, -11), benchmark `^CNX100`, returns `adj_close`) is in `reports/event_study/run_metadata.json`.
