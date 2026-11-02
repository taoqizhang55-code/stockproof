"""
Daily prices for the watchlist, and "unusual moves".

Sources (no API key):
  A-shares   Eastmoney via AKShare (forward-adjusted 前复权, so splits/dividends don't look like moves)
  Hong Kong  Eastmoney via AKShare (forward-adjusted)
  US         Nasdaq's public historical quotes; AKShare (Sina, adjusted) as a fallback
  Market     CSI 300 (A), Hang Seng (HK), S&P 500 (US) for "compared with the market"

Saved per ticker in stockproof_data/quotes/<ticker>.csv and topped up on each refresh.

A move is "unusual" when the stock's return minus the market's is large compared with how much
that difference usually varies for this stock (z-score over the previous 60 trading days), or
simply large (|excess| >= 5%). So a 3% day is news for a utility but not for a small-cap chip maker.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import time

import numpy as np
import pandas as pd
import requests

from stockproof import cn

BENCH = {"A": "^CSI300", "HK": "^HSI", "US": "^SPX"}
NASDAQ_HIST = "https://api.nasdaq.com/api/quote/{sym}/historical"
NASDAQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                  "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com",
                  "Referer": "https://www.nasdaq.com/"}
Z_LIMIT = 2.5
BIG_MOVE = 0.05


def market_of(ticker: str) -> str:
    if ticker.startswith("^"):
        return {"^CSI300": "A", "^HSI": "HK"}.get(ticker, "US")
    info = cn.parse(ticker)
    if not info:
        return "US"
    return "HK" if info["market"] == "HK" else "A"


COLS = ["close", "open", "high", "low", "volume"]          # close first: older files hold only close


def _frame(dates, closes) -> pd.Series:
    s = pd.Series(pd.to_numeric(pd.Series(closes), errors="coerce").to_numpy(),
                  index=pd.to_datetime(pd.Series(dates)), dtype=float).dropna()
    return s[~s.index.duplicated()].sort_index()


def _num(x):
    return pd.to_numeric(pd.Series(x).astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce").to_numpy()


def _bars(df: pd.DataFrame, date: str, close: str, open_: str | None = None, high: str | None = None,
          low: str | None = None, volume: str | None = None) -> pd.DataFrame:
    """A daily OHLCV frame (close always; the others when the source has them), newest last."""
    out = pd.DataFrame({"close": _num(df[close])}, index=pd.to_datetime(pd.Series(df[date]).to_numpy()))
    for name, col in (("open", open_), ("high", high), ("low", low), ("volume", volume)):
        out[name] = _num(df[col]) if col and col in df.columns else np.nan
    out = out.dropna(subset=["close"])
    out = out[~out.index.duplicated()].sort_index()
    out.index.name = None
    return out[COLS]


def _pick(df, *names):
    return next((n for n in names if n in df.columns), None)


def _std(df: pd.DataFrame) -> pd.DataFrame:
    """Recognise the usual column names (AKShare Chinese / English, Nasdaq)."""
    return _bars(df, _col(df, "日期", "date", "Date"), _col(df, "收盘", "close", "Close"),
                 _pick(df, "开盘", "open", "Open"), _pick(df, "最高", "high", "High"),
                 _pick(df, "最低", "low", "Low"), _pick(df, "成交量", "volume", "Volume"))


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    raise KeyError(names)


def _nasdaq(sym: str, start: dt.date, assetclass: str = "stocks") -> pd.DataFrame:
    r = requests.get(NASDAQ_HIST.format(sym=sym.replace("-", ".")), headers=NASDAQ_HEADERS, timeout=20,
                     params={"assetclass": assetclass, "fromdate": start.isoformat(),
                             "todate": dt.date.today().isoformat(), "limit": 9999})
    r.raise_for_status()
    rows = ((((r.json() or {}).get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    if not rows:
        raise ValueError("no rows")
    df = pd.DataFrame(rows)
    df["date"] = [pd.to_datetime(x, format="%m/%d/%Y") for x in df["date"]]
    return _std(df)


def download_bars(ticker: str, start: dt.date) -> pd.DataFrame:
    """Daily OHLCV from `start`, newest last (forward-adjusted for A/HK/US stocks)."""
    s8 = start.strftime("%Y%m%d")
    if ticker == "^SPX":
        try:
            return _nasdaq("SPX", start, "index")
        except Exception:
            return _std(cn._ak().index_us_stock_sina(symbol=".INX")).loc[str(start):]
    if ticker == "^CSI300":
        return _std(cn._ak().stock_zh_index_daily(symbol="sh000300")).loc[str(start):]
    if ticker == "^HSI":
        return _std(cn._ak().stock_hk_index_daily_sina(symbol="HSI")).loc[str(start):]
    info = cn.parse(ticker)
    if info and info["market"] == "HK":
        try:
            return _std(cn._ak().stock_hk_hist(symbol=info["code"], period="daily", start_date=s8,
                                               end_date="22220101", adjust="qfq"))
        except Exception:                                   # Eastmoney refused: Sina has HK history too
            return _std(cn._ak().stock_hk_daily(symbol=info["code"], adjust="qfq")).loc[str(start):]
    if info:
        try:
            return _std(cn._ak().stock_zh_a_hist(symbol=info["code"], period="daily", start_date=s8,
                                                 end_date="20500101", adjust="qfq"))
        except Exception:
            prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[info["market"]]
            return _std(cn._ak().stock_zh_a_daily(symbol=prefix + info["code"], start_date=s8, end_date="20500101",
                                                  adjust="qfq"))
    try:
        return _nasdaq(ticker, start)
    except Exception:
        return _std(cn._ak().stock_us_daily(symbol=ticker.replace("-", "."), adjust="qfq")).loc[str(start):]


def download(ticker: str, start: dt.date) -> pd.Series:
    """Daily closes from `start`, newest last."""
    return download_bars(ticker, start)["close"]


def _path(data_dir: str, ticker: str) -> str:
    return os.path.join(data_dir, "quotes", ticker.replace("^", "_") + ".csv")


def load_bars(data_dir: str, ticker: str) -> pd.DataFrame:
    """Saved OHLCV (open/high/low/volume are NaN in files saved before 0.4: only closes were kept)."""
    p = _path(data_dir, ticker)
    if not os.path.exists(p):
        return pd.DataFrame(columns=COLS, dtype=float)
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    if "close" not in df.columns:
        df = df.rename(columns={df.columns[0]: "close"})
    for c in COLS:
        if c not in df.columns:
            df[c] = np.nan
    return df[COLS].astype(float)


def load(data_dir: str, ticker: str) -> pd.Series:
    return load_bars(data_dir, ticker)["close"]


def update(data_dir: str, ticker: str, years: float = 2.0) -> pd.Series:
    """Top up the saved bars. Forward-adjusted prices change when a dividend is paid, so the last
    ~2 years are re-downloaded when the new data doesn't line up with the saved data, or when the
    saved file has no open/high/low yet (files from before 0.4)."""
    old = load_bars(data_dir, ticker)
    today = dt.date.today()
    full = today - dt.timedelta(days=int(365 * years))
    if not old.empty and old["high"].notna().sum() == 0:
        old = old.iloc[0:0]                                  # closes only: fetch full bars once
    start = full if old.empty else (old.index[-1].date() - dt.timedelta(days=10))
    new = download_bars(ticker, start)
    if not old.empty and len(new):
        overlap = old.index.intersection(new.index)
        if len(overlap) and not np.allclose(old.loc[overlap, "close"], new.loc[overlap, "close"], rtol=1e-4):
            new = download_bars(ticker, full)                # re-adjusted
            old = old.iloc[0:0]
    df = pd.concat([old[~old.index.isin(new.index)], new]).sort_index() if not old.empty else new
    os.makedirs(os.path.dirname(_path(data_dir, ticker)), exist_ok=True)
    df[COLS].to_csv(_path(data_dir, ticker))
    return df["close"]


def refresh(data_dir: str, tickers: list[str], log=print) -> dict:
    stats = {"ok": 0, "failed": []}
    markets = {market_of(t) for t in tickers}
    for t in [BENCH[m] for m in sorted(markets)] + list(tickers):
        try:
            update(data_dir, t)
            stats["ok"] += 1
        except Exception as e:
            stats["failed"].append(t)
            log(f"  {t}: prices unavailable ({type(e).__name__}: {str(e)[:60]})")
        time.sleep(0.2)
    log(f"prices: {stats['ok']} updated" + (f", failed: {', '.join(stats['failed'][:8])}" if stats["failed"] else ""))
    return stats


def moves(data_dir: str, ticker: str, window: int = 60) -> pd.DataFrame:
    """Daily return, market return, excess, and z-score of the excess vs the previous `window` days."""
    s = load(data_dir, ticker)
    if len(s) < 2:
        return pd.DataFrame()
    b = load(data_dir, BENCH[market_of(ticker)])
    df = pd.DataFrame({"close": s, "ret": s.pct_change()})
    df["market"] = b.pct_change().reindex(df.index) if len(b) else np.nan
    df["excess"] = df["ret"] - df["market"].fillna(0.0)
    sd = df["excess"].rolling(window, min_periods=20).std().shift(1)
    df["z"] = df["excess"] / sd
    df["unusual"] = (df["z"].abs() >= Z_LIMIT) | (df["excess"].abs() >= BIG_MOVE)
    return df.dropna(subset=["ret"])


def summary(data_dir: str, ticker: str) -> dict | None:
    """Latest price, 1-day / 5-day / 1-month / YTD returns, and the latest unusual move."""
    m = moves(data_dir, ticker)
    if m.empty:
        return None
    s = m["close"]
    last = s.index[-1]

    def back(days):
        prev = s[s.index <= last - pd.Timedelta(days=days)]
        return float(s.iloc[-1] / prev.iloc[-1] - 1) if len(prev) else None
    ytd_base = s[s.index < pd.Timestamp(last.year, 1, 1)]
    unusual = m[m["unusual"]]
    recent = unusual[unusual.index >= last - pd.Timedelta(days=10)]
    move = None
    if len(recent):
        r = recent.iloc[-1]
        move = {"date": recent.index[-1].date().isoformat(), "ret": float(r["ret"]),
                "excess": float(r["excess"]), "z": None if pd.isna(r["z"]) else float(r["z"])}
    return {"date": last.date().isoformat(), "close": float(s.iloc[-1]), "d1": float(m["ret"].iloc[-1]),
            "d1_excess": float(m["excess"].iloc[-1]), "w1": back(7), "m1": back(30),
            "ytd": float(s.iloc[-1] / ytd_base.iloc[-1] - 1) if len(ytd_base) else None,
            "z": None if pd.isna(m["z"].iloc[-1]) else float(m["z"].iloc[-1]), "move": move,
            "spark": [round(float(x), 4) for x in s.iloc[-60:].to_numpy()]}


def fmt_pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+.1f}%"
