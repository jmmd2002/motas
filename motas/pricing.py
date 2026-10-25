"""Market-value model: what should this bike cost, given km and age?

log(price) = b0 + b_km*km + b_age*age [+ generation] [+ dealer]

Log price because bikes lose a roughly constant *percentage* per km and per
year. Markets for one model are small (often < 30 listings), so:
  * the candidate feature sets are compared by leave-one-out cross-validation
    and the simplest one that predicts (nearly) as well as the best wins;
  * every listing is valued by a model fitted WITHOUT it, so a listing can
    never pull the "fair price" towards its own asking price;
  * gross outliers (|externally studentized residual| > 3) are dropped from
    the fit once and reported, not silently kept;
  * each valuation carries an 80% prediction interval, and the verdict comes
    from where the asking price falls inside that predictive distribution.
"""

from dataclasses import dataclass, field

import numpy as np
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.outliers_influence import OLSInfluence

FEATURE_LABELS = {"km": "km", "age": "age", "gen": "generation", "dealer": "dealer vs private"}
CANDIDATES = (("km",), ("km", "age"), ("km", "age", "gen"), ("km", "age", "dealer"))
# A richer model must beat the simplest-adequate one by more than this (relative
# LOO log-RMSE) to be chosen.
SIMPLICITY_TOLERANCE = 0.02
MIN_OBS_PER_PARAM = 4
MIN_LISTINGS = 6
OUTLIER_T = 3.0
INTERVAL = 0.80

# (upper bound of the price's percentile in the predictive distribution, verdict)
VERDICTS = (
    (0.10, "Great price"),
    (0.30, "Good price"),
    (0.70, "Fair price"),
    (0.90, "High price"),
    (1.01, "Overpriced"),
)


def verdict_for(percentile: float) -> str:
    return next(v for bound, v in VERDICTS if percentile < bound)


@dataclass
class Valuation:
    expected: float
    low: float           # 80% prediction interval
    high: float
    percentile: float    # where the asking price sits in the predictive distribution
    verdict: str


@dataclass
class Model:
    features: tuple[str, ...]
    params: np.ndarray
    n: int
    loo_median_abs_pct: float   # typical error of a held-out prediction, %
    candidates: dict[tuple[str, ...], float]   # LOO log-RMSE per feature set
    conf_int: np.ndarray | None = None   # INTERVAL confidence bounds per param, shape (k, 2)
    fit_rows: list[int] = field(default_factory=list)   # rows the model was fitted on
    outliers: list[int] = field(default_factory=list)   # rows dropped as outliers

    def effect_pct(self, feature: str, delta: float = 1.0) -> float | None:
        """Price change (%) for +delta of a feature, or None if not in the model."""
        if feature not in self.features:
            return None
        b = self.params[1 + self.features.index(feature)]
        return (np.exp(b * delta) - 1) * 100

    def effect_range_pct(self, feature: str, delta: float = 1.0) -> tuple[float, float] | None:
        """INTERVAL confidence range of effect_pct."""
        if feature not in self.features or self.conf_int is None:
            return None
        lo, hi = self.conf_int[1 + self.features.index(feature)]
        return (np.exp(lo * delta) - 1) * 100, (np.exp(hi * delta) - 1) * 100


def _design(data: dict[str, np.ndarray], feats: tuple[str, ...]) -> np.ndarray:
    n = len(data["log_price"])
    return np.column_stack([np.ones(n), *(data[f] for f in feats)])


def _usable(data: dict[str, np.ndarray], feats: tuple[str, ...]) -> bool:
    n = len(data["log_price"])
    if n < MIN_OBS_PER_PARAM * (len(feats) + 1):
        return False
    # A binary feature needs at least 2 listings on each side to be estimable.
    return all(2 <= data[f].sum() <= n - 2 for f in feats if f in ("gen", "dealer"))


def _predict(X_train, y_train, x_new) -> tuple[float, float, int]:
    """Mean and predictive standard error (log scale) and residual dof."""
    fit = sm.OLS(y_train, X_train).fit()
    pred = fit.get_prediction(x_new.reshape(1, -1))
    se = float(np.sqrt(pred.se_mean[0] ** 2 + fit.scale))
    return float(pred.predicted_mean[0]), se, int(fit.df_resid)


def _loo(X: np.ndarray, y: np.ndarray) -> list[tuple[float, float, int]]:
    idx = np.arange(len(y))
    return [_predict(X[idx != i], y[idx != i], X[i]) for i in idx]


def _valuation(price: float, mean: float, se: float, dof: int) -> Valuation:
    t = stats.t(dof)
    z = t.ppf(0.5 + INTERVAL / 2)
    pct = float(t.cdf((np.log(price) - mean) / se))
    return Valuation(
        expected=float(np.exp(mean)),
        low=float(np.exp(mean - z * se)),
        high=float(np.exp(mean + z * se)),
        percentile=pct,
        verdict=verdict_for(pct),
    )


def fit(data: dict[str, np.ndarray], in_fit: np.ndarray) -> Model | None:
    """Choose and fit the model on the rows where `in_fit` is True.

    `data` holds equal-length arrays: log_price, km (thousands), age (years),
    gen (0/1), dealer (0/1). Returned row indices refer to `data`.
    """
    rows = np.where(in_fit)[0]
    sub = {k: v[rows] for k, v in data.items()}
    y = sub["log_price"]
    if len(y) < MIN_LISTINGS:
        return None

    scores = {}
    for feats in CANDIDATES:
        if _usable(sub, feats):
            X = _design(sub, feats)
            errs = [y[i] - m for i, (m, _, _) in enumerate(_loo(X, y))]
            scores[feats] = float(np.sqrt(np.mean(np.square(errs))))
    if not scores:
        return None
    best = min(scores.values())
    # Candidates are ordered simplest first.
    feats = next(f for f in scores if scores[f] <= best * (1 + SIMPLICITY_TOLERANCE))

    X = _design(sub, feats)
    t_ext = OLSInfluence(sm.OLS(y, X).fit()).resid_studentized_external
    bad = np.abs(t_ext) > OUTLIER_T
    final = sm.OLS(y[~bad], X[~bad]).fit()

    loo = _loo(X[~bad], y[~bad])
    abs_pct = [abs(np.exp(yi - m) - 1) * 100 for yi, (m, _, _) in zip(y[~bad], loo)]
    return Model(features=feats, params=final.params, n=int((~bad).sum()),
                 conf_int=final.conf_int(alpha=1 - INTERVAL),
                 loo_median_abs_pct=float(np.median(abs_pct)), candidates=scores,
                 fit_rows=[int(r) for r in rows[~bad]], outliers=[int(r) for r in rows[bad]])


def value_all(model: Model, data: dict[str, np.ndarray]) -> list[Valuation]:
    """Value every row out of sample: a row in the fit set is valued by the
    model refitted without it; any other row by the model as fitted."""
    X = _design(data, model.features)
    y = data["log_price"]
    fit_rows = np.array(model.fit_rows)
    out = []
    for r in range(len(y)):
        train = fit_rows[fit_rows != r]
        mean, se, dof = _predict(X[train], y[train], X[r])
        out.append(_valuation(float(np.exp(y[r])), mean, se, dof))
    return out
