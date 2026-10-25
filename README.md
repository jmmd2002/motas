# Motas

Which used Honda NX500 / CB500X in Portugal is the best buy?

Motas collects every active listing, works out a fair price for each bike from
its km and age, and ranks the listings by how good the asking price is. It also
shows what else should change your decision: owners, service history,
duplicates, warranty, warning words in the description, distance, and how long
the bike has been listed.

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py          # then press "Refresh listings"
```

To collect without the UI (e.g. from cron): `.venv/bin/python -m motas.collect`.
To run the tests: `.venv/bin/python -m pytest`.

## How it works

| Module | Job |
|---|---|
| `motas/standvirtual.py` | Reads search and ad pages from Standvirtual, OLX Portugal's vehicle marketplace, using the JSON the pages embed. Waits 2 s between requests and only fetches paths that robots.txt allows. |
| `motas/families.py` | Decides which listings are NX500s or CB500Xs (titles are inconsistent: "Honda CB 500 XA", "Honda NX 2025", …). |
| `motas/db.py` | SQLite in `data/motas.db`: the current state of each listing, its price history, and sold or removed listings. |
| `motas/signals.py` | Structured and description-based signals (Portuguese keywords, negation-aware). |
| `motas/pricing.py` | Fair-price model; see the methodology below. |
| `motas/analysis.py` | Combines everything: duplicates, mislabelled generations, new-bike reference, verdicts. |
| `app.py` | Streamlit UI. |

**Pricing methodology.** The model is log-linear OLS: `log(price) ~ km + age [+ generation] [+ dealer]`.

- The feature set is chosen by leave-one-out cross-validation, and the simplest adequate model wins.
- Every listing is valued by a model fitted *without* it.
- Outliers (|externally studentized residual| > 3) are dropped from the fit but are still valued and flagged.
- The verdict comes from the asking price's percentile in the 80% predictive distribution.

## Before commercialising

- **Data rights.** Standvirtual/OLX terms restrict automated collection and
  commercial reuse of their listings. Robots.txt allows these pages, but that is
  not a licence. A paid product needs a data agreement (OLX Group has dealer and
  partner APIs) or a different source.
- **olx.pt itself** blocked every request from the development environment
  (HTTP 403), so it is not used directly. Most moto ads on OLX are mirrored from
  Standvirtual, but OLX-only private ads are currently missed.
- **Asking prices are not sale prices.** Listings that disappear are recorded
  (`active = 0`) and can later be used to estimate time to sell and real prices.
