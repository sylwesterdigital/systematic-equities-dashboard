# Systematic Equities — Minimal Flask + Plotly Dashboard

Small, hackable dashboard for a **research → portfolio → results** loop in systematic equities.

* Upload a long-format prices CSV, or tick **Use sample data**.
* Run a simple **long/short momentum** backtest with turnover costs.
* See an interactive **Plotly** equity curve + key metrics.
* Every run is **snapshotted locally** (IndexedDB) so you can restore the **exact** chart (same window/zoom and metrics) from the **Previous Runs** drawer.

> No heavy frameworks. Dependencies: `flask`, `pandas`, `numpy` (frontend uses pinned Plotly CDN).

---

## Demo layout

![loop](https://github.com/user-attachments/assets/c4fe4606-87de-4eb0-9d2e-8f88f2fdbd8a)

---

## Features

* **CSV upload (long format)**: `date,ticker,close,volume`
* **Momentum signal**: $(P_{t-\text{gap}} / P_{t-\text{gap}-\text{win}}) - 1$
* **Dollar-neutral baskets**: equal-weight long/short by quantile, per-name cap
* **Transaction cost** in bps on turnover $\sum |\Delta w|$
* **Interactive equity curve** (Plotly 2.29.1), range selector, slider, zoom/pan, **custom fullscreen**
* **Run metrics**: CAGR, Annualized Vol, Sharpe, Max DD, Hit Rate, Avg Turnover
* **History drawer (IndexedDB)**: click to restore **identical** chart & params
* **Exports**: per-run CSV (`date,daily_pnl,equity`)
* **UX niceties**: blocking overlay + cancel, graceful errors

---

## Quickstart

```bash
# 1) Clone
git clone git@github.com:sylwesterdigital/systematic-equities-dashboard.git
cd systematic-equities-dashboard

# 2) Python 3.10+ virtual env
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

# 3) Install deps
python -m pip install --upgrade pip
pip install flask pandas numpy

# 4) Run
python app.py
# open http://127.0.0.1:5000
```

**Tip:** In the UI you can click **Download sample CSV** or tick **Use sample data** to ignore any uploaded/cached file.

---

## Data format

```csv
date,ticker,close,volume
2024-01-02,AAPL,185.60,51147000
2024-01-02,MSFT,374.50,19233000
...
```

* `date` must be parseable (ISO `YYYY-MM-DD` recommended).
* Multiple tickers supported. Returns are computed **per ticker**.

---

## Parameters (UI)

* **Start / End**: date filter applied **before** signal/weights
* **Momentum window (days)**: lookback length
* **Gap (days)**: skip the most recent `gap` days
* **Quantile (%)**: top/bottom slice for L/S baskets
* **Max position**: per-name absolute cap
* **Turnover cost (bps)**: cost per unit turnover

---

## Outputs

* **Equity curve** (Plotly, with range buttons + slider, custom fullscreen)
* **Metrics**: CAGR, Ann. Vol, Sharpe, Max DD, Hit Rate, Avg Turnover
* **Download**: `/runs/equity_<run_id>.csv` with `date,daily_pnl,equity`

**History drawer:** Every run stores `{ x, y, window:[start,end], params, metrics, run_id, data_source, when }`.
Click an item to render that snapshot **1:1** (no server call, no re-autorange).

---

## How it works

* **Backend (`app.py`)**

  * Loads uploaded CSV into `data/prices.csv`, or generates a sample.
  * Computes momentum signal → quantile baskets → capped, balanced weights.
  * Applies turnover cost in **bps** to daily PnL; builds cumulative equity.
  * Returns metrics, chart arrays, and the **effective window** actually used.
  * Writes each run’s equity to `runs/equity_<id>.csv` for download.

* **Frontend (`templates/index.html`)**

  * Single template with inline CSS + JS.
  * **Pinned Plotly**: `https://cdn.plot.ly/plotly-2.29.1.min.js` (avoid “latest” warning).
  * Styled range selector (readable on dark bg) and explicit fullscreen icon.
  * **IndexedDB** stores the exact render payload so history restores perfectly.

---

## Project structure

```
app.py
templates/
  index.html       # UI + Plotly + history drawer + overlay
data/              # uploaded dataset stored as prices.csv
runs/              # per-run equity exports
```

---

## FAQ / Troubleshooting

**Why does a restored history run keep the same time window?**
The backend returns the **effective window** (post-filter) and the frontend locks Plotly’s `xaxis.range` to `[start, end]` from that snapshot.

**Plotly warns “plotly-latest.js is not latest”.**
We intentionally pin to **2.29.1**:

```html
<script src="https://cdn.plot.ly/plotly-2.29.1.min.js"></script>
```

No “latest” CDN foot-guns.

**IndexedDB: “The database connection is closing.”**
The app re-opens as needed and avoids closing during active transactions. If you still see this (tab suspended / dev tools throttling), close the drawer, wait a second, reopen it, or reload the page. History data is local and will reload.

**How do I force the sample instead of a cached upload?**
Tick **Use sample data** in the sidebar; the server ignores any uploaded/cached file for that run.

---

## Roadmap (nice next steps)

* Walk-forward / expanding windows; parameter grid search
* Multi-factor blending + basic risk targeting
* Sector/β neutrality; borrow costs
* Background jobs (RQ/Celery) + progress stream (SSE/WebSocket)
* Server-side persistence (SQLite/Postgres) alongside IndexedDB
* Light tests for signal/weights with `pytest`

---

## License

MIT (or your preferred OSS license).

