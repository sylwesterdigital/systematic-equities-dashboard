# Systematic Equities — Minimal Flask Dashboard

**Monolithic Flask + Jinja** app for a simple research → portfolio → results loop in **systematic equities**.  
Upload long-format price data, configure a few parameters, run an **equal-weight long/short momentum** backtest with a basic turnover cost, and view an SVG equity curve plus key metrics.

> No third-party app builders. Dependencies: `flask`, `pandas`, `numpy`.

##Basic Layout

![SED-c_LOOP_FOREVER](https://github.com/user-attachments/assets/c4fe4606-87de-4eb0-9d2e-8f88f2fdbd8a)

---

## Features
- CSV upload (**long format**): `date,ticker,close,volume`
- L/S momentum signal: (close[t-gap] / close[t-gap-win] − 1)
- Dollar-neutral, equal-weight, per-name cap
- Turnover cost in bps
- Equity curve (SVG, no JS libs) and core metrics (CAGR, Sharpe, max DD, hit rate, avg turnover)
- Downloadable run CSV (date, daily_pnl, equity)

---

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install flask pandas numpy

python app.py
# open http://127.0.0.1:5000
````

Upload a CSV or click **“Download sample CSV”** to inspect the required schema.

---

## Data format (required)

```csv
date,ticker,close,volume
2024-01-02,AAPL,185.60,51147000
2024-01-02,MSFT,374.50,19233000
...
```

* Dates should be trading days; app sorts and groups by `ticker`.
* Multiple tickers and dates supported; the app computes returns per ticker.

---

## Parameters (UI)

* **Start / End**: date range filter
* **Momentum window (days)**: lookback for momentum
* **Gap (days)**: skip recent days (avoid short-term reversal)
* **Quantile (%)**: top/bottom slice for long/short baskets
* **Max position**: per-name cap (absolute)
* **Turnover cost (bps)**: cost per unit of turnover ∑|Δw|

---

## Outputs

* **Equity curve** (SVG)
* **Metrics**: CAGR, Ann. Vol, Sharpe, Max Drawdown, Hit Rate, Avg Turnover
* **Run CSV** (`/runs/equity_<id>.csv`): `date,daily_pnl,equity`

---

## Project structure

```
app.py
templates/
  base.html
  index.html
  results.html
data/          # uploaded dataset stored as prices.csv
runs/          # per-run equity exports
```

---

## Roadmap (optional)

* Sector/β neutrality constraints
* Basic execution simulator (TWAP/VWAP; arrival slippage)
* TCA summary (arrival vs realized)
* Config export/import (YAML)
* Light tests (pytest) for signal/weights

---

## License: 
