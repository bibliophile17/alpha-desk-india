"""Cross-event inference on CARs. Formulas are explicit; scipy only supplies distributions.

Same-day announcements share market/sector shocks, so event CARs are not
independent. The primary p-value is therefore DATE-CLUSTERED (cluster = day 0);
the plain t-test is reported alongside for comparison.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def mean_ci(x, level=0.95):
    x = np.asarray(x, float)
    n = len(x)
    se = x.std(ddof=1) / np.sqrt(n)
    crit = stats.t.ppf(0.5 + level / 2, n - 1)
    return x.mean() - crit * se, x.mean() + crit * se


def sign_test(x):
    """Share of positive CARs vs 50/50, exact binomial; zeros dropped."""
    x = np.asarray(x, float)
    x = x[x != 0]
    if len(x) == 0:
        return np.nan
    return float(stats.binomtest(int((x > 0).sum()), len(x), 0.5).pvalue)


def wilcoxon_test(x, min_nonzero=6):
    x = np.asarray(x, float)
    x = x[x != 0]
    if len(x) < min_nonzero:
        return np.nan
    return float(stats.wilcoxon(x).pvalue)


def clustered_mean_test(x, clusters, level=0.95) -> dict:
    """Mean CAR with cluster-robust SE.

    Var(mean) = G/(G-1) * sum_g (S_g)^2 / n^2, S_g = sum of (x_i - xbar) in cluster g,
    t with G-1 degrees of freedom. With every cluster of size 1 this equals the
    ordinary one-sample t-test.
    """
    x = np.asarray(x, float)
    codes, _ = pd.factorize(np.asarray(clusters))
    if (codes < 0).any():
        raise ValueError("missing cluster id")
    n, g = len(x), int(codes.max()) + 1
    res = {"n_clusters": g, "cluster_se": np.nan, "cluster_t": np.nan,
           "cluster_p": np.nan, "cluster_ci_low": np.nan, "cluster_ci_high": np.nan}
    if g < 2:
        return res
    xbar = x.mean()
    s_g = np.bincount(codes, weights=x - xbar)
    se = float(np.sqrt(g / (g - 1) * np.sum(s_g ** 2) / n ** 2))
    if se == 0:
        return res
    t = xbar / se
    crit = stats.t.ppf(0.5 + level / 2, g - 1)
    res.update(cluster_se=se, cluster_t=float(t),
               cluster_p=float(2 * stats.t.sf(abs(t), g - 1)),
               cluster_ci_low=float(xbar - crit * se),
               cluster_ci_high=float(xbar + crit * se))
    return res


def summarize(x, clusters=None, min_n=30, level=0.95) -> dict:
    x = np.asarray(x, float)
    finite = np.isfinite(x)
    cl = None if clusters is None else np.asarray(clusters)[finite]
    x = x[finite]
    n = len(x)
    keys = ["mean", "median", "sd", "pos_share", "t_stat", "t_p", "ci_low", "ci_high",
            "wilcoxon_p", "sign_p", "n_clusters", "cluster_se", "cluster_t",
            "cluster_p", "cluster_ci_low", "cluster_ci_high"]
    out = {"n": n, **{k: np.nan for k in keys}}
    if n < 3:
        out["label"] = f"insufficient (n={n})"
        return out
    sd = float(x.std(ddof=1))
    out.update(mean=float(x.mean()), median=float(np.median(x)), sd=sd,
               pos_share=float((x > 0).mean()))
    if sd > 0:
        t = stats.ttest_1samp(x, 0.0)
        lo, hi = mean_ci(x, level)
        out.update(t_stat=float(t.statistic), t_p=float(t.pvalue),
                   ci_low=float(lo), ci_high=float(hi))
    out["wilcoxon_p"] = wilcoxon_test(x)
    out["sign_p"] = sign_test(x)
    if cl is not None:
        out.update(clustered_mean_test(x, cl, level))
    out["label"] = "inferential" if n >= min_n else f"exploratory (n<{min_n})"
    return out


def holm_adjust(pvals):
    """Holm step-down adjustment for multiple testing; NaN stays NaN."""
    p = np.asarray(pvals, float)
    out = np.full(len(p), np.nan)
    ok = np.where(np.isfinite(p))[0]
    m = len(ok)
    running = 0.0
    for rank, i in enumerate(ok[np.argsort(p[ok])]):
        running = max(running, min(1.0, (m - rank) * p[i]))
        out[i] = running
    return out


def group_summary(df, group_col, car_col, cluster_col="day0", min_n=15) -> pd.DataFrame:
    rows = []
    d = df.copy()
    d[group_col] = d[group_col].fillna("Unknown")
    for g, sub in d.groupby(group_col):
        s = summarize(sub[car_col].to_numpy(), sub[cluster_col].to_numpy(), min_n=min_n)
        rows.append({group_col: g, **s})
    out = pd.DataFrame(rows)
    out["p_holm"] = np.nan
    inf = out["label"] == "inferential"
    if inf.any():
        out.loc[inf, "p_holm"] = holm_adjust(out.loc[inf, "cluster_p"].to_numpy())
    return out
