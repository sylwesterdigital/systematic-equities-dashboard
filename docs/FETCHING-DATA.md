# Fastest (no API key): **Stooq**

US tickers usually need the `.us` suffix (e.g., `aapl.us`).

```zsh
mkdir -p data/tmp
TICKERS=(AAPL MSFT AMZN SPY)
echo "date,ticker,close,volume" > data/prices.csv

for t in "${TICKERS[@]}"; do
  curl -sL "https://stooq.com/q/d/l/?s=${t:l}.us&i=d" -o "data/tmp/${t}.csv"
  # Stooq CSV: Date,Open,High,Low,Close,Volume
  tail -n +2 "data/tmp/${t}.csv" | awk -F',' -v T="$t" 'NF>1{print $1 "," T "," $5 "," $6}' >> data/prices.csv
done
```

> Notes: Good for quick historical **daily** data. Check if values are **split-adjusted** for your symbols; use at your discretion.

---

# Free (with key), **Adjusted** prices: **Alpha Vantage**

Daily adjusted includes dividends/splits. Free tier has rate limits.

```zsh
export AV_KEY="YOUR_ALPHA_VANTAGE_KEY"
mkdir -p data
TICKERS=(AAPL MSFT AMZN SPY)
echo "date,ticker,close,volume" > data/prices.csv

for t in "${TICKERS[@]}"; do
  curl -s "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=$t&datatype=csv&outputsize=full&apikey=$AV_KEY" \
  | tail -n +2 \
  | awk -F',' -v T="$t" 'NF>1{print $1 "," T "," $6 "," $7}' >> data/prices.csv
done
```

> CSV cols: `timestamp,open,high,low,close,**adjusted_close**,volume,dividend_amount,split_coefficient`.
> The snippet uses **adjusted\_close** (`$6`) and `volume` (`$7`).

---

# “Nicer” free/paid option: **Tiingo (EOD)**

Reliable EOD; generous free tier for personal use.

```zsh
export TIINGO_TOKEN="YOUR_TIINGO_TOKEN"
mkdir -p data
TICKERS=(AAPL MSFT AMZN SPY)
echo "date,ticker,close,volume" > data/prices.csv

for t in "${TICKERS[@]}"; do
  curl -s "https://api.tiingo.com/tiingo/daily/${t}/prices?startDate=2018-01-01&format=csv&token=$TIINGO_TOKEN" \
  | awk -F',' 'NR==1{for(i=1;i<=NF;i++)h[$i]=i} NR>1{print $0}' > data/tmp_tiingo.csv

  # Use header indices so we don’t guess column order:
  awk -F',' -v T="$t" '
    NR==1 { for(i=1;i<=NF;i++) h[$i]=i; next }
    { date=$h["date"]; close= (h["adjClose"]? $h["adjClose"] : $h["close"]); vol=$h["volume"];
      if(date!="" && close!="" && vol!="") print date "," T "," close "," vol }' data/tmp_tiingo.csv \
  >> data/prices.csv
done
rm -f data/tmp_tiingo.csv
```

> Uses `adjClose` if present, else `close`.

---

## One-file Python fetcher (pandas) — safer column handling

If you prefer **one command** that outputs your app’s schema:

```python
# fetch_csv.py
import os, sys, pandas as pd, requests

def from_alpha_vantage(ticker, key, outputsize="full"):
    url = ("https://www.alphavantage.co/query"
           f"?function=TIME_SERIES_DAILY_ADJUSTED&symbol={ticker}"
           f"&datatype=csv&outputsize={outputsize}&apikey={key}")
    df = pd.read_csv(url)
    df = df.rename(columns={"timestamp":"date","adjusted_close":"close"})
    df["ticker"] = ticker
    return df[["date","ticker","close","volume"]]

def from_stooq(ticker):
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
    df = pd.read_csv(url)
    df = df.rename(columns=str.lower)
    df["ticker"] = ticker.upper()
    df = df.rename(columns={"date":"date","close":"close","volume":"volume"})
    return df[["date","ticker","close","volume"]]

def main():
    source = os.environ.get("SRC","av")   # av | stooq
    tickers = os.environ.get("TICKERS","AAPL,MSFT,AMZN,SPY").split(",")
    out = []
    if source == "av":
        key = os.environ.get("AV_KEY")
        if not key: sys.exit("Set AV_KEY")
        for t in tickers:
            out.append(from_alpha_vantage(t.strip(), key))
    else:
        for t in tickers:
            out.append(from_stooq(t.strip()))
    df = pd.concat(out).dropna().sort_values(["ticker","date"])
    df.to_csv("data/prices.csv", index=False)
    print("Wrote data/prices.csv", df.shape)

if __name__ == "__main__":
    main()
```

Run:

```zsh
pip install pandas
mkdir -p data
SRC=av AV_KEY=YOUR_ALPHA_VANTAGE_KEY python fetch_csv.py
# or: SRC=stooq python fetch_csv.py
```

---

## Quality & caveats (important)

* **Adjustments:** Prefer **adjusted** prices for backtests (splits/dividends). The AV/Tiingo snippets handle this.
* **Rate limits:** Alpha Vantage free tier throttles; loop slowly or use a paid plan for larger universes.
* **Universes:** For realistic tests, fix a **point-in-time universe** (e.g., current S\&P 500 introduces survivorship bias).
* **Intraday data:** Free, clean intraday is rare. Consider paid (IEX Cloud, Polygon, Intrinio) and convert JSON→CSV yourself.

If you tell which symbols/date range you want, a ready-made command can be tailored exactly to your case.
