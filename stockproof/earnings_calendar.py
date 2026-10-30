"""
Earnings calendar: which watchlist companies report in the coming days.

  A-shares  Eastmoney 预约披露: the date each company booked with the exchange (and its later
            changes) for the current report period. Official, all A-shares in one table.
  US        Nasdaq's public earnings calendar (one request per day): date, before/after market,
            and the analysts' consensus EPS. If a company isn't listed yet, an estimate from the
            same quarter last year (its 8-K date + 52 weeks), marked as an estimate.
  Hong Kong not covered yet.

Fetched by the daily run / "Refresh earnings" and saved in stockproof_data/calendar.json,
so the dashboard never waits on the network.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time

import pandas as pd
import requests

from stockproof import clock
from stockproof import cn

NASDAQ_URL = "https://api.nasdaq.com/api/calendar/earnings"
NASDAQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                  "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com",
                  "Referer": "https://www.nasdaq.com/"}
TIMES = {"time-pre-market": "before_open", "time-after-hours": "after_close", "time-not-supplied": None}


def path(data_dir: str) -> str:
    return os.path.join(data_dir, "calendar.json")


def load(data_dir: str) -> dict:
    try:
        with open(path(data_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"updated": None, "items": [], "errors": []}


def upcoming(data_dir: str, watchlist: list[str], days: int = 14, today: dt.date | None = None) -> list[dict]:
    """Saved calendar entries for the watchlist from today on, soonest first. No network."""
    today = today or clock.today()
    end = (today + dt.timedelta(days=days)).isoformat()
    items = [i for i in load(data_dir)["items"]
             if i["ticker"] in watchlist and today.isoformat() <= i["date"] <= end]
    return sorted(items, key=lambda i: (i["date"], i["ticker"]))


# ---------------------------------------------------------------- A-shares

def _deadline(end: dt.date) -> dt.date:
    return cn._available_date_a(pd.Timestamp(end)).date()


def open_periods(today: dt.date) -> list[str]:
    """Report periods that have ended but whose legal deadline hasn't passed: on Oct 29 the Q3
    period (due Oct 31); from January the annual report; in April also Q1."""
    out = []
    for y in (today.year - 1, today.year):
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            end = dt.date(y, m, d)
            if end < today <= _deadline(end):
                out.append(end.strftime("%Y%m%d"))
    return out


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def a_share_calendar(codes: set[str], today: dt.date) -> list[dict]:
    ak = cn._ak()
    out = []
    for period in open_periods(today):
        df = ak.stock_yysj_em(symbol="沪深A股", date=period)
        if df is None or not len(df):
            continue
        c_code = _col(df, "股票代码")
        c_actual = _col(df, "实际披露时间")
        changes = [c for c in ("三次变更日期", "二次变更日期", "一次变更日期", "首次预约时间") if c in df.columns]
        for _, r in df.iterrows():
            code = str(r[c_code]).zfill(6)
            if code not in codes:
                continue
            if c_actual and pd.notna(r[c_actual]):
                continue                                         # already published
            planned = next((pd.Timestamp(r[c]) for c in changes if pd.notna(r[c])), None)
            if planned is None:
                continue
            info = cn.parse(code)
            out.append({"ticker": info["symbol"], "date": planned.date().isoformat(),
                        "period": f"{period[:4]}-{period[4:6]}", "time": None,
                        "source": "appointment", "eps_forecast": None,
                        "changed": changes.index(next(c for c in changes if pd.notna(r[c]))) < len(changes) - 1})
    return out


# ---------------------------------------------------------------- US

def _money(v):
    try:
        return float(str(v).replace("$", "").replace(",", "").replace("(", "-").replace(")", ""))
    except (TypeError, ValueError):
        return None


def nasdaq_day(day: dt.date) -> list[dict]:
    r = requests.get(NASDAQ_URL, params={"date": day.isoformat()}, headers=NASDAQ_HEADERS, timeout=20)
    r.raise_for_status()
    rows = (((r.json() or {}).get("data") or {}).get("rows")) or []
    return [{"symbol": str(x.get("symbol", "")).upper().replace(".", "-"), "time": TIMES.get(x.get("time")),
             "eps_forecast": _money(x.get("epsForecast")), "period": x.get("fiscalQuarterEnding"),
             "n_estimates": x.get("noOfEsts")} for x in rows]


def us_calendar(tickers: set[str], today: dt.date, days: int) -> tuple[list[dict], list[str]]:
    out, errors = [], []
    for k in range(days + 1):
        day = today + dt.timedelta(days=k)
        if day.weekday() >= 5:
            continue
        try:
            rows = nasdaq_day(day)
        except Exception as e:
            errors.append(f"Nasdaq {day}: {type(e).__name__}")
            if len(errors) >= 3:
                break                                            # blocked: don't hammer it
            continue
        for x in rows:
            if x["symbol"] in tickers:
                out.append({"ticker": x["symbol"], "date": day.isoformat(), "period": x["period"],
                            "time": x["time"], "source": "nasdaq", "eps_forecast": x["eps_forecast"]})
        time.sleep(0.3)
    return out, errors


def estimate_from_last_year(sec_dir: str, tmap: dict, tickers: set[str], today: dt.date, days: int) -> list[dict]:
    """Same week as last year's earnings 8-K (+52 weeks), from saved SEC files. No network."""
    out = []
    for tk in tickers:
        entry = tmap.get(tk)
        if not entry:
            continue
        p = os.path.join(sec_dir, f"submissions_{entry['cik']}.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            recent = json.load(f).get("filings", {}).get("recent", {})
        for form, items, filed in zip(recent.get("form", []), recent.get("items", []), recent.get("filingDate", [])):
            if form != "8-K" or "2.02" not in (items or ""):
                continue
            guess = dt.date.fromisoformat(filed) + dt.timedelta(weeks=52)
            if today <= guess <= today + dt.timedelta(days=days):
                out.append({"ticker": tk, "date": guess.isoformat(), "period": None, "time": None,
                            "source": "estimate", "eps_forecast": None})
                break
    return out


# ---------------------------------------------------------------- refresh

def refresh(data_dir: str, watchlist: list[str], days: int = 21, log=print) -> dict:
    """Fetch the calendar for the watchlist and save it. Each market fails on its own."""
    today = clock.today()
    items, errors = [], []
    a_codes = {cn.parse(t)["code"] for t in watchlist if cn.parse(t) and cn.parse(t)["market"] != "HK"}
    us = {t for t in watchlist if not cn.is_cn(t)}
    if a_codes:
        try:
            items += a_share_calendar(a_codes, today)
        except Exception as e:
            errors.append(f"A-shares: {type(e).__name__}: {str(e)[:80]}")
    if us:
        found, errs = us_calendar(us, today, days)
        items += found
        errors += errs
        missing = us - {i["ticker"] for i in found}
        if missing:
            try:
                from stockproof.sec import SECCache
                cache = SECCache(data_dir)
                raw = cache.cached("company_tickers.json") or {}
                tmap = {str(r["ticker"]).upper().replace(".", "-"): {"cik": int(r["cik_str"])} for r in raw.values()}
                items += estimate_from_last_year(cache.dir, tmap, missing, today, days)
            except Exception as e:
                errors.append(f"estimates: {type(e).__name__}")
    # keep saved entries of stocks that weren't part of this refresh (e.g. refreshing one stock)
    kept = [i for i in load(data_dir).get("items", []) if i.get("ticker") not in set(watchlist)]
    data = {"updated": dt.datetime.now().isoformat(timespec="seconds"), "items": kept + items, "errors": errors}
    with open(path(data_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    log(f"calendar: {len(items)} upcoming reports" + (f" ({'; '.join(errors[:3])})" if errors else ""))
    return data
