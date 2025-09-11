# app.py
# Minimal Systematic Equities Dashboard (Flask + Jinja)
# Features:
# - Upload CSV (date,ticker,close,volume) in long format
# - Configure simple momentum L/S backtest
# - Dollar-neutral, equal-weight long/short, position cap, turnover cost
# - Equity curve SVG + key metrics

import os
import io
import uuid
import math
import datetime as dt
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd
from flask import (
    Flask, request, render_template, redirect, url_for, flash, send_file
)

app = Flask(__name__)
app.secret_key = "change-me"

DATA_DIR = "data"
RUNS_DIR = "runs"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RUNS_DIR, exist_ok=True)

DATA_PATH = os.path.join(DATA_DIR, "prices.csv")

# ---------------------------- Utilities ---------------------------- #

def load_dataset() -> Optional[pd.DataFrame]:
    if not os.path.exists(DATA_PATH):
        return None
    df = pd.read_csv(DATA_PATH)
    # expected: date,ticker,close,volume
    needed = {"date","ticker","close","volume"}
    if not needed.issubset(df.columns):
        raise ValueError("CSV must contain columns: date,ticker,close,volume")
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.sort_values(["ticker","date"]).reset_index(drop=True)
    return df

def sample_prices(n_days=260, tickers=("AAPL","MSFT","AMZN")) -> pd.DataFrame:
    # synthetic sample (no internet required)
    start = (dt.date.today() - dt.timedelta(days=int(n_days*1.6)))
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    rng = np.random.default_rng(42)
    for t in tickers:
        price = 100.0 + rng.normal(0, 1.0, size=n_days).cumsum()
        price = np.maximum(5.0, price)  # no negative
        vol = (rng.uniform(1.0, 3.0, size=n_days) * 1e6).astype(int)
        for d, p, v in zip(dates, price, vol):
            rows.append((d.date().isoformat(), t, float(np.round(p, 2)), int(v)))
    return pd.DataFrame(rows, columns=["date","ticker","close","volume"])

def compute_momentum_signal(df: pd.DataFrame, mom_win: int, gap: int) -> pd.Series:
    # momentum = close.shift(gap) / close.shift(gap+mom_win) - 1
    g = df.groupby("ticker")["close"]
    num = g.shift(gap)
    den = g.shift(gap + mom_win)
    mom = (num / den) - 1.0
    return mom

def make_weights(df: pd.DataFrame, signal: pd.Series, quantile: float, max_pos: float) -> pd.Series:
    # Cross-sectional top/bottom quantiles per date → equal-weight long/short
    work = df[["date","ticker"]].copy()
    work["sig"] = signal.values
    def per_date(group: pd.DataFrame) -> pd.Series:
        g = group.dropna(subset=["sig"]).copy()
        if g.empty:
            return pd.Series(0.0, index=group.index)
        n = len(g)
        k = max(1, int(math.floor(n * quantile)))
        g = g.sort_values("sig")
        shorts = g.iloc[:k]    # lowest k
        longs  = g.iloc[-k:]   # highest k
        w = pd.Series(0.0, index=group.index)
        if len(longs) > 0:
            w.loc[longs.index] =  1.0 / len(longs)
        if len(shorts) > 0:
            w.loc[shorts.index] = -1.0 / len(shorts)
        # cap per name
        w = w.clip(lower=-max_pos, upper=max_pos)
        # re-normalize to keep dollar-neutral
        pos = w[w > 0].sum()
        neg = -w[w < 0].sum()
        scale_pos = (pos if pos > 0 else 1.0)
        scale_neg = (neg if neg > 0 else 1.0)
        w[w > 0] = w[w > 0] / scale_pos * 0.5  # target +0.5 gross per side
        w[w < 0] = w[w < 0] / scale_neg * -0.5
        return w
    weights = work.groupby("date", group_keys=False).apply(per_date)
    return weights

def backtest(df: pd.DataFrame,
             start: Optional[pd.Timestamp],
             end: Optional[pd.Timestamp],
             mom_win: int = 60,
             gap: int = 5,
             quantile: float = 0.2,
             max_pos: float = 0.02,
             tc_bps: float = 10.0) -> Dict:
    dff = df.copy()
    if start:
        dff = dff[dff["date"] >= pd.to_datetime(start)]
    if end:
        dff = dff[dff["date"] <= pd.to_datetime(end)]
    dff = dff.sort_values(["date","ticker"]).reset_index(drop=True)

    # returns by ticker/date
    dff["ret"] = dff.groupby("ticker")["close"].pct_change()
    # signal
    sig = compute_momentum_signal(dff, mom_win, gap)
    # weights per date/ticker
    w = make_weights(dff, sig, quantile, max_pos)
    dff["w"] = w.values

    # Align: apply yesterday's weights to today's returns
    dff["w_lag"] = dff.groupby("ticker")["w"].shift(1).fillna(0.0)

    # Turnover (per date): sum abs(w - w_prev)
    dff["dw"] = (dff["w"].fillna(0.0) - dff["w_lag"]).abs()
    turn_by_date = dff.groupby("date")["dw"].sum().clip(lower=0.0)

    # Daily portfolio return before cost
    daily_ret = dff.groupby("date").apply(lambda g: float((g["w_lag"] * g["ret"].fillna(0.0)).sum()))
    # Costs: tc_bps per unit of turnover
    daily_cost = (tc_bps / 10000.0) * turn_by_date
    daily_pnl = daily_ret - daily_cost

    equity = (1.0 + daily_pnl.fillna(0.0)).cumprod()

    # Metrics
    ann_factor = 252.0
    cagr = (equity.iloc[-1] ** (ann_factor / len(equity)) - 1.0) if len(equity) > 0 else 0.0
    vol = daily_pnl.std(ddof=0) * math.sqrt(ann_factor) if len(equity) > 1 else 0.0
    sharpe = (daily_pnl.mean() / daily_pnl.std(ddof=0) * math.sqrt(ann_factor)) if daily_pnl.std(ddof=0) > 1e-12 else 0.0
    dd = (equity / equity.cummax() - 1.0).min() if len(equity) else 0.0
    avg_turn = turn_by_date.mean() if len(turn_by_date) else 0.0
    hit_rate = (daily_pnl > 0).mean() if len(daily_pnl) else 0.0

    # Prepare SVG polyline path
    x = np.arange(len(equity), dtype=float)
    y = equity.values.astype(float)
    if len(y) > 0:
        # normalize to SVG viewBox
        wsvg, hsvg = 900.0, 260.0
        x_norm = (x - x.min()) / (x.max() - x.min() + 1e-9) * (wsvg - 40) + 20
        y_min, y_max = y.min(), y.max()
        y_norm = (1 - (y - y_min) / (y_max - y_min + 1e-9)) * (hsvg - 40) + 20
        points = " ".join(f"{x_norm[i]:.1f},{y_norm[i]:.1f}" for i in range(len(y_norm)))
    else:
        wsvg, hsvg, points = 900.0, 260.0, ""

    run_id = str(uuid.uuid4())[:8]
    out = pd.DataFrame({
        "date": equity.index.astype(str),
        "daily_pnl": daily_pnl.values,
        "equity": equity.values
    })
    out_path = os.path.join(RUNS_DIR, f"equity_{run_id}.csv")
    out.to_csv(out_path, index=False)

    params = dict(
        start=str(dff["date"].min().date()) if len(dff) else "",
        end=str(dff["date"].max().date()) if len(dff) else "",
        mom_win=mom_win, gap=gap, quantile=quantile, max_pos=max_pos, tc_bps=tc_bps
    )
    metrics = dict(
        cagr=cagr, vol=vol, sharpe=sharpe, max_dd=dd, avg_turn=avg_turn, hit_rate=hit_rate
    )
    chart = dict(width=int(wsvg), height=int(hsvg), points=points)
    return {
        "run_id": run_id,
        "params": params,
        "metrics": metrics,
        "chart": chart,
        "n_days": int(len(equity))
    }

# ---------------------------- Routes ---------------------------- #

@app.route("/", methods=["GET"])
def index():
    df = load_dataset()
    has_data = df is not None and len(df) > 0
    rows = len(df) if has_data else 0
    ntickers = df["ticker"].nunique() if has_data else 0
    start = str(df["date"].min().date()) if has_data else ""
    end = str(df["date"].max().date()) if has_data else ""
    default_start = start
    default_end = end
    return render_template(
        "index.html",
        has_data=has_data,
        rows=rows,
        ntickers=ntickers,
        start=start, end=end,
        default_start=default_start, default_end=default_end
    )

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or f.filename == "":
        flash("Please choose a CSV file.")
        return redirect(url_for("index"))
    try:
        # basic CSV validation
        buf = io.StringIO(f.stream.read().decode("utf-8"))
        df = pd.read_csv(buf)
        needed = {"date","ticker","close","volume"}
        if not needed.issubset(df.columns):
            flash("CSV must include: date,ticker,close,volume")
            return redirect(url_for("index"))
        # persist
        df.to_csv(DATA_PATH, index=False)
        flash(f"Uploaded {len(df)} rows for {df['ticker'].nunique()} tickers.")
    except Exception as e:
        flash(f"Upload error: {e}")
    return redirect(url_for("index"))

@app.route("/run", methods=["POST"])
def run_backtest():
    df = load_dataset()
    if df is None:
        flash("No dataset found. Upload a CSV first or use the sample.")
        return redirect(url_for("index"))

    # parse params
    start = request.form.get("start") or None
    end = request.form.get("end") or None
    mom_win = int(float(request.form.get("mom_win", 60)))
    gap = int(float(request.form.get("gap", 5)))
    quantile = float(request.form.get("quantile", 0.2))
    max_pos = float(request.form.get("max_pos", 0.02))
    tc_bps = float(request.form.get("tc_bps", 10.0))

    res = backtest(df, start, end, mom_win, gap, quantile, max_pos, tc_bps)
    return render_template("results.html", **res)

@app.route("/sample.csv", methods=["GET"])
def download_sample():
    df = sample_prices()
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="sample_prices.csv"
    )

@app.route("/download/<run_id>", methods=["GET"])
def download_run(run_id):
    path = os.path.join(RUNS_DIR, f"equity_{run_id}.csv")
    if not os.path.exists(path):
        flash("Run not found.")
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True, download_name=f"equity_{run_id}.csv")

if __name__ == "__main__":
    app.run(debug=True)
