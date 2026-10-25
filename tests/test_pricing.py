import numpy as np
import pytest

from motas import pricing


def synthetic(n=30, seed=0, noise=0.03):
    """Market with known effects: -4% per 10k km, -6% per year."""
    rng = np.random.default_rng(seed)
    km = rng.uniform(0, 60, n)          # thousands
    age = rng.uniform(0, 7, n)
    log_price = np.log(7000) + np.log(0.96) * km / 10 + np.log(0.94) * age + rng.normal(0, noise, n)
    return {"log_price": log_price, "km": km, "age": age,
            "gen": (age < 2).astype(float), "dealer": rng.integers(0, 2, n).astype(float)}


def test_recovers_known_effects():
    data = synthetic(n=60)
    model = pricing.fit(data, np.ones(60, bool))
    assert "km" in model.features and "age" in model.features
    assert model.effect_pct("km", 10) == pytest.approx(-4, abs=0.6)
    assert model.effect_pct("age", 1) == pytest.approx(-6, abs=0.8)
    assert model.loo_median_abs_pct < 3.5


def test_prefers_simple_model_when_extra_features_do_not_help():
    model = pricing.fit(synthetic(n=60), np.ones(60, bool))
    assert model.features == ("km", "age")


def test_too_few_listings():
    data = {k: v[:5] for k, v in synthetic().items()}
    assert pricing.fit(data, np.ones(5, bool)) is None


def test_binary_feature_needs_both_groups():
    data = synthetic(n=40)
    data["dealer"][:] = 1
    model = pricing.fit(data, np.ones(40, bool))
    assert ("km", "age", "dealer") not in model.candidates


def test_listing_never_values_itself():
    data = synthetic(n=30)
    data["log_price"][0] += 0.25            # one bike asks ~28% too much
    model = pricing.fit(data, np.ones(30, bool))
    val = pricing.value_all(model, data)[0]
    assert np.exp(data["log_price"][0]) > val.high
    assert val.verdict == "Overpriced"


def test_outlier_is_dropped_from_fit_but_still_valued():
    data = synthetic(n=30, noise=0.02)
    data["log_price"][3] -= 0.4             # far too cheap
    model = pricing.fit(data, np.ones(30, bool))
    assert model.outliers == [3]
    assert 3 not in model.fit_rows
    assert pricing.value_all(model, data)[3].verdict == "Great price"


def test_rows_outside_fit_set_are_valued():
    data = synthetic(n=30)
    in_fit = np.ones(30, bool)
    in_fit[:4] = False
    model = pricing.fit(data, in_fit)
    assert not set(range(4)) & set(model.fit_rows)
    assert len(pricing.value_all(model, data)) == 30


def test_verdict_bands_follow_percentile():
    assert pricing.verdict_for(0.05) == "Great price"
    assert pricing.verdict_for(0.2) == "Good price"
    assert pricing.verdict_for(0.5) == "Fair price"
    assert pricing.verdict_for(0.8) == "High price"
    assert pricing.verdict_for(0.95) == "Overpriced"
    assert pricing.verdict_for(1.0) == "Overpriced"


def test_interval_contains_expected_and_matches_coverage():
    data = synthetic(n=200, seed=1)
    model = pricing.fit(data, np.ones(200, bool))
    vals = pricing.value_all(model, data)
    assert all(v.low < v.expected < v.high for v in vals)
    inside = np.mean([v.low <= np.exp(y) <= v.high for v, y in zip(vals, data["log_price"])])
    assert inside == pytest.approx(pricing.INTERVAL, abs=0.07)


def test_effect_range_brackets_estimate():
    model = pricing.fit(synthetic(n=60), np.ones(60, bool))
    lo, hi = model.effect_range_pct("km", 10)
    assert lo < model.effect_pct("km", 10) < hi
    assert model.effect_range_pct("dealer") is None
