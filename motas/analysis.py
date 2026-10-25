"""Turn stored listings into a decision table: value, verdict and signals."""

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

from . import geo, pricing, signals
from .families import Family


@dataclass
class Market:
    table: pd.DataFrame          # one row per used listing, best deals first
    new: pd.DataFrame            # new bikes from dealers (price reference)
    model: pricing.Model | None


def _age_years(row, today: date) -> float | None:
    if row["condition"] == "new":
        return 0.0
    if not row["reg_year"]:
        return None
    reg = date(int(row["reg_year"]), int(row["reg_month"] or 7), 1)
    return max((today - reg).days / 365.25, 0.0)


def _days_since(iso: str | None, today: date) -> int | None:
    if not iso:
        return None
    return (today - datetime.fromisoformat(iso).date()).days


def analyze(listings: list[dict], history: dict[str, list[tuple[str, int]]],
            family: Family, today: date, home: tuple[float, float] | None = None) -> Market:
    df = pd.DataFrame(listings)
    if df.empty:
        return Market(df, df, None)
    df = df[df["price"].notna()].copy()

    df["age"] = df.apply(_age_years, axis=1, today=today)
    df["days_listed"] = df["listed_at"].apply(_days_since, today=today)
    df["price_drop"] = [
        max(history.get(i, [(None, p)])[0][1] - p, 0) or None
        for i, p in zip(df["id"], df["price"])
    ]
    df["distance_km"] = [
        geo.distance_km(home, (la, lo)) if home and pd.notna(la) and pd.notna(lo) else None
        for la, lo in zip(df["lat"], df["lon"])
    ]

    extra: dict[str, list[tuple[str, str]]] = {i: [] for i in df["id"]}

    # The previous-generation name on a bike registered after the new
    # generation launched is almost always a mislabelled current-gen bike.
    mislabel = (df["generation"] == family.previous_gen) & (df["reg_year"] >= family.current_gen_year)
    for i, y in zip(df.loc[mislabel, "id"], df.loc[mislabel, "reg_year"]):
        extra[i].append((signals.AMBER, f"Listed as {family.previous_gen} but first registered "
                                        f"{int(y)}; {family.current_gen} replaced it in "
                                        f"{family.current_gen_year}. Confirm the model."))
    df.loc[mislabel, "generation"] = family.current_gen

    # The same bike listed twice (identical km and registration month).
    df["duplicate_of_cheaper"] = False
    used = df[(df["condition"] != "new") & (df["km"] >= 100)]
    for _, grp in used.groupby(["km", "reg_year", "reg_month"]):
        if len(grp) < 2:
            continue
        grp = grp.sort_values("price")
        for i in grp["id"]:
            others = grp[grp["id"] != i]
            prices = ", ".join(f"€{int(p):,}" for p in others["price"])
            extra[i].append((signals.AMBER, f"Same bike seems to be listed again at {prices}"))
        df.loc[df["id"].isin(grp["id"].iloc[1:]), "duplicate_of_cheaper"] = True

    df["signals"] = [
        extra[r["id"]] + signals.listing_signals(r, r["age"], r["days_listed"], r["price_drop"])
        for r in df.to_dict("records")
    ]
    df["red_flag"] = df["signals"].apply(lambda s: any(level == signals.RED for level, _ in s))

    new = df[df["condition"] == "new"].sort_values("price")
    df = df[(df["condition"] != "new") & df["km"].notna() & df["age"].notna()].reset_index(drop=True)

    data = {
        "log_price": np.log(df["price"].to_numpy(float)),
        "km": df["km"].to_numpy(float) / 1000,
        "age": df["age"].to_numpy(float),
        "gen": (df["generation"] == family.current_gen).to_numpy(float),
        "dealer": (df["seller_type"] == "professional").to_numpy(float),
    }
    in_fit = (~df["red_flag"] & ~df["duplicate_of_cheaper"]).to_numpy()
    model = pricing.fit(data, in_fit) if len(df) else None

    # Row positions in the model refer to this order; record them as columns
    # before the table is re-sorted for display.
    df["outlier"] = df.index.isin(model.outliers) if model else False
    df["in_model"] = df.index.isin(model.fit_rows) if model else False
    if model:
        vals = pricing.value_all(model, data)
        df["expected"] = [v.expected for v in vals]
        df["low"] = [v.low for v in vals]
        df["high"] = [v.high for v in vals]
        df["percentile"] = [v.percentile for v in vals]
        df["verdict"] = [v.verdict for v in vals]
        df["vs_expected"] = df["price"] - df["expected"]
        # An outlier is kept out of the fit but keeps its verdict: a price far
        # below the market is what the buyer is looking for, as long as they
        # find out why.
        for r in np.where(df["outlier"])[0]:
            pct = (df.at[r, "price"] / df.at[r, "expected"] - 1) * 100
            side = "below" if pct < 0 else "above"
            df.at[r, "signals"] = [(signals.AMBER, f"Price is unusually far {side} similar bikes "
                                                   f"({pct:+.0f}%): ask the seller why")] + df.at[r, "signals"]
        df.loc[df["red_flag"], "verdict"] = "Check first"
        df = df.sort_values(["red_flag", "percentile"]).reset_index(drop=True)
    else:
        df["verdict"] = "Not enough data"
        df = df.sort_values("price").reset_index(drop=True)

    return Market(df, new, model)
