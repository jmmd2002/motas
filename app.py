"""Motas: which used Honda NX500 / CB500X should I buy?

Run: streamlit run app.py
"""

from datetime import date, datetime
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from motas import analysis, db, geo, signals, standvirtual
from motas.collect import collect
from motas.families import NX500
from motas.pricing import INTERVAL

FAMILY = NX500

# Status palette: verdicts are states, so they use status colours, always
# paired with a text label.
GOOD, NEUTRAL, SERIOUS, CRITICAL = "#0ca30c", "#8a8984", "#ec835a", "#d03b3b"
VERDICT_STYLE = {
    "Great price": (GOOD, "▼▼"),
    "Good price": (GOOD, "▼"),
    "Fair price": (NEUTRAL, "●"),
    "High price": (SERIOUS, "▲"),
    "Overpriced": (CRITICAL, "▲▲"),
    "Check first": (CRITICAL, "!"),
    "Not enough data": (NEUTRAL, "?"),
}
CHART_GROUP = {
    "Great price": ("Below market", GOOD), "Good price": ("Below market", GOOD),
    "Fair price": ("At market", NEUTRAL),
    "High price": ("Above market", CRITICAL), "Overpriced": ("Above market", CRITICAL),
    "Check first": ("Check first", CRITICAL),
}
SIGNAL_ICON = {signals.RED: "⛔", signals.AMBER: "⚠️", signals.GREEN: "✅"}

st.set_page_config(page_title="Motas: NX500 / CB500X", page_icon="🏍️", layout="wide")
st.markdown("""
<style>
.badge {display:inline-block;padding:2px 10px;border-radius:999px;font-weight:600;
        font-size:0.85rem;color:#fff;white-space:nowrap}
.muted {opacity:0.7;font-size:0.9rem}
.price {font-size:1.6rem;font-weight:700;line-height:1.1}
</style>
""", unsafe_allow_html=True)


def eur(x) -> str:
    return f"€{x:,.0f}".replace(",", " ")


def badge(verdict: str) -> str:
    color, icon = VERDICT_STYLE.get(verdict, (NEUTRAL, ""))
    return f'<span class="badge" style="background:{color}">{icon} {escape(verdict)}</span>'


def effect_note(model, feature: str, delta: float) -> str:
    lo, hi = sorted(model.effect_range_pct(feature, delta))
    return f"{INTERVAL:.0%} confidence range: {lo:+.1f}% to {hi:+.1f}%."


@st.cache_resource
def connection():
    return db.connect()


@st.cache_data(show_spinner=False)
def load(run_marker: str | None, home: tuple[float, float]) -> analysis.Market:
    conn = connection()
    listings = db.active_listings(conn, FAMILY.key)
    history = db.price_history(conn, [l["id"] for l in listings])
    return analysis.analyze(listings, history, FAMILY, date.today(), home)


conn = connection()

# --- sidebar: the buyer's situation --------------------------------------
with st.sidebar:
    st.header("Your search")
    place = st.selectbox("You are near", list(geo.PLACES), index=list(geo.PLACES).index("Lisboa"))
    home = geo.PLACES[place]

    last = db.last_run(conn, FAMILY.key)
    if last:
        st.caption(f"Data updated {datetime.fromisoformat(last).astimezone():%d %b %Y, %H:%M}")
    if st.button("Refresh listings", width="stretch"):
        with st.status("Fetching listings from Standvirtual…") as status:
            try:
                n = collect(FAMILY, conn, progress=lambda msg: status.update(label=msg))
                status.update(label=f"Found {n} listings", state="complete")
                load.clear()
                last = db.last_run(conn, FAMILY.key)
            except (standvirtual.SourceError, OSError) as e:
                status.update(label=f"Refresh failed: {e}", state="error")

if not last:
    st.title("Honda NX500 / CB500X")
    st.info("No data yet. Press **Refresh listings** in the sidebar to fetch the current market.")
    st.stop()

market = load(last, home)
table, model = market.table, market.model

with st.sidebar:
    budget = st.slider("Budget", 0, int(table["price"].max() // 250 + 1) * 250,
                       int(table["price"].max() // 250 + 1) * 250, step=250, format="€%d")
    max_km = st.slider("Max km", 0, int(table["km"].max() // 5000 + 1) * 5000,
                       int(table["km"].max() // 5000 + 1) * 5000, step=5000)
    gens = st.multiselect("Model", [FAMILY.current_gen, FAMILY.previous_gen],
                          default=[FAMILY.current_gen, FAMILY.previous_gen],
                          help=f"The {FAMILY.current_gen} ({FAMILY.current_gen_year}–) replaced the "
                               f"{FAMILY.previous_gen}: same engine and frame, updated electronics.")
    max_dist = st.slider("Max distance (straight line)", 50, 1000, 1000, step=50, format="%d km")

view = table[(table["price"] <= budget) & (table["km"] <= max_km) & table["generation"].isin(gens)
             & (table["distance_km"].isna() | (table["distance_km"] <= max_dist))]

# --- header: what the market says ----------------------------------------
st.title("Honda NX500 / CB500X in Portugal")

if model is None:
    st.warning("Fewer than 6 comparable listings, so there is not enough data for a reliable "
               "valuation yet. Listings are shown by price.")
else:
    typical = float(table["expected"].median())
    km_pct = model.effect_pct("km", 10)
    age_pct = model.effect_pct("age", 1)
    cols = st.columns(4)
    cols[0].metric("Listings", f"{len(view)} of {len(table)}",
                   help="Used bikes matching your filters, out of all active listings.")
    cols[1].metric("Each 10 000 km", f"{km_pct:+.1f}%", f"≈ {eur(abs(typical * km_pct / 100))}",
                   delta_color="off", delta_arrow="off",
                   help="Effect on market price, at equal age. " + effect_note(model, "km", 10))
    if age_pct is not None:
        cols[2].metric("Each year of age", f"{age_pct:+.1f}%", f"≈ {eur(abs(typical * age_pct / 100))}",
                       delta_color="off", delta_arrow="off",
                       help="Effect on market price, at equal km. " + effect_note(model, "age", 1))
    if len(market.new):
        cols[3].metric("New, from a dealer", eur(market.new["price"].min()),
                       help="Cheapest new bike currently listed: the ceiling for any used one.")
    st.caption(f"Fair prices come from {model.n} comparable listings. Each bike is valued by a model "
               f"that never saw it; on that test, valuations are typically within "
               f"±{model.loo_median_abs_pct:.1f}%. The range shown is where {INTERVAL:.0%} of "
               f"comparable bikes would be priced.")

# --- chart: asking price vs fair price -----------------------------------
if model is not None and len(view):
    fig = go.Figure()
    for _, r in view.iterrows():
        fig.add_trace(go.Scatter(x=[r["km"], r["km"]], y=[r["expected"], r["price"]], mode="lines",
                                 line=dict(color="rgba(138,137,132,0.6)", width=2),
                                 hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=view["km"], y=view["expected"], mode="markers", name="Fair price",
        marker=dict(size=9, color="rgba(0,0,0,0)", line=dict(color=NEUTRAL, width=2)),
        hovertemplate="Fair price %{y:,.0f} €<extra></extra>"))
    for group, color in dict(CHART_GROUP.values()).items():
        g = view[view["verdict"].map(lambda v: CHART_GROUP.get(v, ("", ""))[0]) == group]
        if g.empty:
            continue
        fig.add_trace(go.Scatter(
            x=g["km"], y=g["price"], mode="markers", name=group,
            marker=dict(size=12, color=color, line=dict(color="white", width=2)),
            customdata=g[["title", "verdict", "expected", "reg_year", "region"]].to_numpy(),
            hovertemplate="<b>%{customdata[0]}</b> (%{customdata[3]}, %{customdata[4]})<br>"
                          "Asking %{y:,.0f} € · fair %{customdata[2]:,.0f} €<br>"
                          "%{customdata[1]}<extra></extra>"))
    fig.update_layout(
        height=380, margin=dict(l=0, r=0, t=30, b=0),
        title=dict(text="Asking price vs fair price, by km", font=dict(size=15)),
        xaxis=dict(title="km", tickformat=",", gridcolor="rgba(128,128,128,0.15)", zeroline=False),
        yaxis=dict(title="€", tickformat=",", gridcolor="rgba(128,128,128,0.15)", zeroline=False),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom"),
        hoverlabel=dict(namelength=-1), separators=". ",
    )
    st.plotly_chart(fig, width="stretch")

# --- ranking -------------------------------------------------------------
st.subheader("Best value first")
if view.empty:
    st.info("No listings match your filters.")

for _, r in view.iterrows():
    with st.container(border=True):
        img, info, facts = st.columns([1.1, 1.6, 1.6])
        if r["photo_url"]:
            img.image(r["photo_url"], width="stretch")

        reg = f"{int(r['reg_month']):02d}/{int(r['reg_year'])}" if pd.notna(r["reg_month"]) \
            else str(int(r["reg_year"]))
        info.markdown(f"**{escape(r['generation'])}** · {reg} · {int(r['km']):,} km".replace(",", " "))
        info.markdown(f'<div class="price">{eur(r["price"])}</div>', unsafe_allow_html=True)
        if model is not None:
            diff = r["vs_expected"]
            info.markdown(
                f'{badge(r["verdict"])}&nbsp; <span class="muted">'
                f'{eur(abs(diff))} {"below" if diff < 0 else "above"} fair price {eur(r["expected"])}'
                f'<br>Fair range {eur(r["low"])} – {eur(r["high"])}</span>',
                unsafe_allow_html=True)
        info.markdown(f"[Open listing ↗]({r['url']})")

        where = escape(", ".join(x for x in (r["city"], r["region"]) if x))
        dist = f" · ~{r['distance_km']:.0f} km away" if pd.notna(r["distance_km"]) else ""
        seller = "Private seller" if r["seller_type"] == "private" else escape(r["seller_name"] or "Dealer")
        lines = [f"{seller}", f"{where}{dist}"]
        if pd.notna(r["owners"]):
            lines.append(f"{int(r['owners'])} previous owner{'s' if r['owners'] != 1 else ''}")
        if pd.notna(r["days_listed"]):
            lines.append(f"Listed {int(r['days_listed'])} days ago")
        facts.markdown('<span class="muted">' + "<br>".join(lines) + "</span>", unsafe_allow_html=True)
        for level, text in r["signals"]:
            facts.markdown(f"{SIGNAL_ICON[level]} {escape(text)}")

        with st.expander("Equipment and description"):
            if r["features"]:
                st.markdown("**Equipment:** " + escape(", ".join(r["features"])))
            st.text(r["description"] or "No description.")

if len(market.new):
    with st.expander(f"New bikes from dealers ({len(market.new)})"):
        for _, r in market.new.iterrows():
            st.markdown(f"[{escape(r['title'])}]({r['url']}): **{eur(r['price'])}**, "
                        f"{escape(r['seller_name'] or 'dealer')}, {escape(r['region'] or '')}")

with st.expander("How the fair price is calculated"):
    st.markdown(f"""
- **Data:** every active {FAMILY.current_gen} and {FAMILY.previous_gen} listing on Standvirtual
  (where OLX Portugal's motorcycle ads live). Both share engine and frame, so they are priced together.
- **Model:** log-linear regression of asking price on km and age; the generation and seller type are
  added only if they make held-out predictions better. Several candidate models are compared by
  leave-one-out cross-validation, and the simplest one that is as good as the best is used.
- **Fair price:** each listing is valued by the model refitted *without* that listing, so a listing
  can never pull its own fair price towards its asking price.
- **Left out of the model:** listings with deal-breaking signals, the more expensive copy of a
  duplicated listing, new bikes, and statistical outliers (which are still valued and flagged).
- **Verdict:** where the asking price falls in the distribution of prices for comparable bikes:
  lowest 10% → *Great*, 10–30% → *Good*, 30–70% → *Fair*, 70–90% → *High*, top 10% → *Overpriced*.
- **Limits:** these are asking prices, not sale prices, and condition beyond what the listing states
  (tyres, chain, crash damage) is not known until you see the bike.
""")
    if model is not None:
        st.caption("Candidate models (LOO error, log scale): " + "; ".join(
            f"{' + '.join(f)}: {s:.4f}" for f, s in model.candidates.items())
            + f". Chosen: {' + '.join(model.features)}.")
