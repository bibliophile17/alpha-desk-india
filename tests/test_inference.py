import numpy as np
import pandas as pd
import pytest
from scipy import stats

from alphadesk.inference import (clustered_mean_test, group_summary, holm_adjust,
                                 mean_ci, sign_test, summarize)


def test_sign_test_hand_example():
    # 3 positives of 4 non-zero: p = 2 * P(X>=3 | n=4, 0.5) = 2 * 5/16 = 0.625
    assert sign_test([1, 1, 1, -1, 0]) == pytest.approx(0.625)


def test_t_test_and_ci_match_scipy():
    x = np.array([0.02, -0.01, 0.015, 0.03, -0.005, 0.01, 0.02, 0.0, 0.012, 0.008])
    s = summarize(x, min_n=5)
    t = stats.ttest_1samp(x, 0)
    assert s["t_stat"] == pytest.approx(t.statistic) and s["t_p"] == pytest.approx(t.pvalue)
    lo, hi = mean_ci(x)
    assert lo < x.mean() < hi and s["ci_low"] == pytest.approx(lo)
    assert s["label"] == "inferential"


def test_cluster_test_with_singleton_clusters_equals_plain_t():
    rng = np.random.default_rng(3)
    x = rng.normal(0.01, 0.03, 40)
    c = clustered_mean_test(x, np.arange(40))
    t = stats.ttest_1samp(x, 0)
    assert c["cluster_t"] == pytest.approx(t.statistic) and c["cluster_p"] == pytest.approx(t.pvalue)


def test_clustering_widens_se_when_same_day_events_move_together():
    shock = np.repeat([0.03, -0.03, 0.02, -0.02, 0.01, -0.01], 5)   # 6 days x 5 events, identical within day
    x = shock + np.tile([0.001, -0.001, 0.0, 0.002, -0.002], 6)
    days = np.repeat(np.arange(6), 5)
    assert clustered_mean_test(x, days)["cluster_se"] > clustered_mean_test(x, np.arange(30))["cluster_se"]


def test_small_samples_are_labelled_exploratory_and_nan_dropped():
    s = summarize([0.01, 0.02, np.nan, 0.03, 0.04], min_n=30)
    assert s["n"] == 4 and s["label"].startswith("exploratory")
    assert summarize([0.01], min_n=30)["label"].startswith("insufficient")


def test_holm_hand_example():
    adj = holm_adjust([0.01, 0.04, 0.03, np.nan])
    assert adj[:3] == pytest.approx([0.03, 0.06, 0.06]) and np.isnan(adj[3])


def test_group_summary_applies_sample_thresholds():
    rng = np.random.default_rng(5)
    df = pd.DataFrame({"sector": ["IT"] * 20 + ["Banks"] * 5 + [None] * 3,
                       "car": rng.normal(0, 0.02, 28), "day0": np.arange(28)})
    g = group_summary(df, "sector", "car", min_n=15).set_index("sector")
    assert g.loc["IT", "label"] == "inferential" and not np.isnan(g.loc["IT", "p_holm"])
    assert g.loc["Banks", "label"].startswith("exploratory") and np.isnan(g.loc["Banks", "p_holm"])
    assert "Unknown" in g.index
