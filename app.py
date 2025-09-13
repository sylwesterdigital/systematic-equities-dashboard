# app.py
# Monolithic Flask + Jinja + Inline HTML prototype
# - Sidebar: upload + params
# - Main area: results (always visible)
# - Auto-run on CSV select
# - Blocking overlay + Cancel
# - Verbose logging

import os, io, uuid, math, logging, time
import datetime as dt
from typing import Optional, Dict

import numpy as np
import pandas as pd
from flask import Flask, request, render_template_string, send_file, jsonify, g

app = Flask(__name__)
app.secret_key = "change-me"

DATA_DIR = "data"
RUNS_DIR = "runs"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RUNS_DIR, exist_ok=True)
DATA_PATH = os.path.join(DATA_DIR, "prices.csv")

# ---------------- Logging ---------------- #
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)
log = logging.getLogger("sys-eq")

@app.before_request
def add_req_id():
    g.req_id = str(uuid.uuid4())[:8]
    log.info(f"[{g.req_id}] {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def after(resp):
    log.info(f"[{g.req_id}] status {resp.status_code}")
    return resp

# ---------------- Data utils ---------------- #
def load_dataset() -> Optional[pd.DataFrame]:
    if not os.path.exists(DATA_PATH):
        return None
    df = pd.read_csv(DATA_PATH)
    needed = {"date","ticker","close","volume"}
    if not needed.issubset(df.columns):
        raise ValueError("CSV must contain columns: date,ticker,close,volume")
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.sort_values(["ticker","date"]).reset_index(drop=True)
    return df

def sample_prices(n_days=260, tickers=("AAPL","MSFT","AMZN","SPY")) -> pd.DataFrame:
    start = (dt.date.today() - dt.timedelta(days=int(n_days*1.6)))
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    rng = np.random.default_rng(42)
    for t in tickers:
        price = 100.0 + rng.normal(0, 1.0, size=n_days).cumsum()
        price = np.maximum(5.0, price)
        vol = (rng.uniform(1.0, 3.0, size=n_days) * 1e6).astype(int)
        for d, p, v in zip(dates, price, vol):
            rows.append((d.date().isoformat(), t, float(np.round(p, 2)), int(v)))
    return pd.DataFrame(rows, columns=["date","ticker","close","volume"])

def compute_momentum_signal(df: pd.DataFrame, mom_win: int, gap: int) -> pd.Series:
    g = df.groupby("ticker")["close"]
    num = g.shift(gap)
    den = g.shift(gap + mom_win)
    return (num / den) - 1.0

def make_weights(df: pd.DataFrame, signal: pd.Series, quantile: float, max_pos: float) -> pd.Series:
    work = df[["date","ticker"]].copy()
    work["sig"] = signal.values
    def per_date(group: pd.DataFrame) -> pd.Series:
        g = group.dropna(subset=["sig"]).copy()
        if g.empty: return pd.Series(0.0, index=group.index)
        n = len(g); k = max(1, int(math.floor(n * quantile)))
        g = g.sort_values("sig")
        shorts = g.iloc[:k]; longs  = g.iloc[-k:]
        w = pd.Series(0.0, index=group.index)
        if len(longs) > 0:  w.loc[longs.index]  =  1.0 / len(longs)
        if len(shorts) > 0: w.loc[shorts.index] = -1.0 / len(shorts)
        w = w.clip(lower=-max_pos, upper=max_pos)
        pos = w[w > 0].sum(); neg = -w[w < 0].sum()
        if pos > 0: w[w > 0] = w[w > 0] / pos * 0.5
        if neg > 0: w[w < 0] = w[w < 0] / neg * -0.5
        return w
    return work.groupby("date", group_keys=False).apply(per_date)

# ---------------- Backtest ---------------- #
def backtest(df: pd.DataFrame,
             start: Optional[str],
             end: Optional[str],
             mom_win: int = 60,
             gap: int = 5,
             quantile: float = 0.2,
             max_pos: float = 0.02,
             tc_bps: float = 10.0) -> Dict:
    """
    Run momentum backtest on given dataset.

    Returns dict with:
      - run_id: unique ID
      - params: parameters used
      - metrics: performance metrics (CAGR, Sharpe, etc.)
      - chart: structured equity curve data (dates, equity values)
      - n_days: length of backtest
    """
    t0 = time.time()
    dff = df.copy()
    if start:
        dff = dff[dff["date"] >= pd.to_datetime(start)]
    if end:
        dff = dff[dff["date"] <= pd.to_datetime(end)]
    dff = dff.sort_values(["date", "ticker"]).reset_index(drop=True)

    # Compute returns, signals, weights
    dff["ret"] = dff.groupby("ticker")["close"].pct_change()
    sig = compute_momentum_signal(dff, mom_win, gap)
    dff["w"] = make_weights(dff, sig, quantile, max_pos).values
    dff["w_lag"] = dff.groupby("ticker")["w"].shift(1).fillna(0.0)
    dff["dw"] = (dff["w"].fillna(0.0) - dff["w_lag"]).abs()

    # Portfolio daily PnL
    turn_by_date = dff.groupby("date")["dw"].sum().clip(lower=0.0)
    daily_ret = dff.groupby("date").apply(lambda g: float((g["w_lag"] * g["ret"].fillna(0.0)).sum()))
    daily_cost = (tc_bps / 10000.0) * turn_by_date
    daily_pnl = daily_ret - daily_cost
    equity = (1.0 + daily_pnl.fillna(0.0)).cumprod()

    # Metrics
    ann_factor = 252.0
    cagr = (equity.iloc[-1] ** (ann_factor / len(equity)) - 1.0) if len(equity) else 0.0
    vol = daily_pnl.std(ddof=0) * math.sqrt(ann_factor) if len(equity) > 1 else 0.0
    sharpe = (daily_pnl.mean() / daily_pnl.std(ddof=0) * math.sqrt(ann_factor)) if daily_pnl.std(ddof=0) > 1e-12 else 0.0
    dd = (equity / equity.cummax() - 1.0).min() if len(equity) else 0.0
    avg_turn = turn_by_date.mean() if len(turn_by_date) else 0.0
    hit_rate = (daily_pnl > 0).mean() if len(daily_pnl) else 0.0

    # Save equity curve to CSV
    run_id = str(uuid.uuid4())[:8]
    out = pd.DataFrame({
        "date": equity.index.astype(str),
        "daily_pnl": daily_pnl.values,
        "equity": equity.values
    })
    out_path = os.path.join(RUNS_DIR, f"equity_{run_id}.csv")
    out.to_csv(out_path, index=False)

    # Assemble output
    params = dict(
        start=str(dff["date"].min().date()) if len(dff) else "",
        end=str(dff["date"].max().date()) if len(dff) else "",
        mom_win=mom_win, gap=gap, quantile=quantile,
        max_pos=max_pos, tc_bps=tc_bps
    )
    metrics = dict(
        cagr=cagr, vol=vol, sharpe=sharpe,
        max_dd=dd, avg_turn=avg_turn, hit_rate=hit_rate
    )
    log.info(f"[{g.req_id}] backtest ok n_days={len(equity)} "
             f"cagr={cagr:.3%} sharpe={sharpe:.2f} in {time.time()-t0:.2f}s")

    return {
        "run_id": run_id,
        "params": params,
        "metrics": metrics,
        # <-- frontend will now use this with Plotly -->
        "chart": {
            "dates": equity.index.astype(str).tolist(),
            "equity": equity.values.tolist()
        },
        "n_days": int(len(equity))
    }


# ---------------- Routes ---------------- #
@app.route("/", methods=["GET"])
def index():
    df = load_dataset()
    has_data = df is not None and len(df) > 0
    rows = len(df) if has_data else 0
    ntickers = df["ticker"].nunique() if has_data else 0
    start = str(df["date"].min().date()) if has_data else ""
    end = str(df["date"].max().date()) if has_data else ""

    return render_template_string(open("templates/index.html").read(),
        has_data=has_data, rows=rows, ntickers=ntickers,
        default_start=start, default_end=end)

@app.route("/run-all", methods=["POST"])
def run_all():
    try:
        start = request.form.get("start") or None
        end = request.form.get("end") or None
        mom_win = int(float(request.form.get("mom_win", 60)))
        gap = int(float(request.form.get("gap", 5)))
        quantile = float(request.form.get("quantile", 0.2))
        max_pos = float(request.form.get("max_pos", 0.02))
        tc_bps = float(request.form.get("tc_bps", 10.0))

        f = request.files.get("file")
        if f and f.filename:
            buf = io.StringIO(f.stream.read().decode("utf-8"))
            df = pd.read_csv(buf)
            needed = {"date","ticker","close","volume"}
            if not needed.issubset(df.columns):
                return jsonify({"ok": False, "message": "CSV must include: date,ticker,close,volume"}), 400
            df.to_csv(DATA_PATH, index=False)

        # Fixed: explicit check instead of "or" shortcut
        df_loaded = load_dataset()
        if df_loaded is None or df_loaded.empty:
            df_loaded = sample_prices()

        res = backtest(df_loaded, start, end, mom_win, gap, quantile, max_pos, tc_bps)
        return jsonify({"ok": True, "message": "Backtest completed.", **res})
    except Exception as e:
        log.exception(f"[{g.req_id}] run-all failed")
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/sample.csv")
def download_sample():
    df = sample_prices()
    buf = io.StringIO(); df.to_csv(buf, index=False); buf.seek(0)
    return send_file(io.BytesIO(buf.getvalue().encode("utf-8")),
        mimetype="text/csv", as_attachment=True, download_name="sample_prices.csv")

@app.route("/download/<run_id>")
def download_run(run_id):
    path = os.path.join(RUNS_DIR, f"equity_{run_id}.csv")
    if not os.path.exists(path):
        return ("Run not found.", 404)
    return send_file(path, as_attachment=True, download_name=f"equity_{run_id}.csv")

if __name__ == "__main__":
    app.run(debug=True)
