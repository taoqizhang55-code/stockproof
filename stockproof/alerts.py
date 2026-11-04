"""
Real-time alerts: a price crossing a support/resistance zone, a level in an AI research-team plan being
reached, and paper orders filling or being cancelled.

Prices come from Sina's real-time quote feed during the session (a few seconds behind the exchange);
outside trading hours the last daily close is used. Each alert is recorded once (append-only) and shown as
a desktop notification. Alerts describe what the price did; they are NOT orders.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time

import pandas as pd
import requests

from stockproof import cn, quotes, ta

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    key TEXT PRIMARY KEY, created_at TEXT, day TEXT, ticker TEXT, kind TEXT, price REAL, text TEXT, detail TEXT);
CREATE TRIGGER IF NOT EXISTS alerts_no_update BEFORE UPDATE ON alerts
BEGIN SELECT RAISE(ABORT, 'alerts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS alerts_no_delete BEFORE DELETE ON alerts
BEGIN SELECT RAISE(ABORT, 'alerts are append-only'); END;
"""
NOT_ORDER = "提醒不是交易指令。"
NOT_ORDER_EN = "Alerts are not orders."


def _init(store):
    store.conn.executescript(SCHEMA)


# ---------------------------------------------------------------- live prices
def _sina_symbol(ticker: str) -> str | None:
    p = cn.parse(ticker)
    if p:
        return {"SH": "sh", "SZ": "sz", "BJ": "bj", "HK": "rt_hk"}[p["market"]] + p["code"]
    if re.fullmatch(r"[A-Z.\-]{1,6}", ticker.upper()):
        return "gb_" + ticker.lower().replace(".", "$").replace("-", "")
    return None


def live_prices(tickers: list[str], timeout: float = 8) -> dict[str, dict]:
    """{ticker: {"price", "prev_close", "time"}} from Sina's quote feed; tickers it can't price are left out."""
    syms = {s: t for t in tickers if (s := _sina_symbol(t))}
    if not syms:
        return {}
    try:
        r = requests.get("https://hq.sinajs.cn/list=" + ",".join(syms), timeout=timeout,
                         headers={**cn.UA, "Referer": "https://finance.sina.com.cn"})
        r.encoding = "gbk"
        text = r.text
    except Exception:
        return {}
    return parse_sina(text, syms)


def parse_sina(text: str, syms: dict[str, str]) -> dict[str, dict]:
    out = {}
    for m in re.finditer(r'var hq_str_(\w+?)="([^"]*)"', text):
        sym, f = m.group(1), m.group(2).split(",")
        tk = syms.get(sym)
        if not tk or len(f) < 5:
            continue
        try:
            if sym.startswith(("sh", "sz", "bj")):
                price, prev = float(f[3]), float(f[2])
                stamp = f"{f[30]} {f[31]}" if len(f) > 31 else ""
            elif sym.startswith("rt_hk"):
                price, prev, stamp = float(f[6]), float(f[3]), f"{f[17]} {f[18]}" if len(f) > 18 else ""
            else:                                                   # gb_: US
                price, prev, stamp = float(f[1]), float(f[26]) if len(f) > 26 and f[26] else None, f[3]
        except (ValueError, IndexError):
            continue
        if price > 0:
            out[tk] = {"price": price, "prev_close": prev, "time": stamp}
    return out


# ---------------------------------------------------------------- what to watch
def watch_list(app, store) -> list[str]:
    """Watchlist + paper holdings + stocks with an AI team call in the last 30 days."""
    tk = list(app.settings.get("watchlist", [])) if hasattr(app, "settings") else []
    try:
        from stockproof import paper
        for a in paper.accounts(store):
            od = paper.orders(store, a["id"])
            tk += list(od.loc[od["status"].isna() | (od["status"] == "filled"), "ticker"])
    except Exception:
        pass
    try:
        since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        tk += [r[0] for r in store.conn.execute("SELECT DISTINCT ticker FROM team_calls WHERE day >= ?", (since,))]
    except Exception:
        pass
    return list(dict.fromkeys(tk))


def _team_plans(store, ticker: str) -> list[dict]:
    """Plan levels of the latest team call on this stock (made in the last 60 days)."""
    try:
        row = store.conn.execute("SELECT id, day, result FROM team_calls WHERE ticker=? AND day >= ? ORDER BY made_at DESC "
                                 "LIMIT 1", (ticker, (dt.date.today() - dt.timedelta(days=60)).isoformat())).fetchone()
    except Exception:
        return []
    if not row:
        return []
    res = json.loads(row[2])
    return [{"call": row[0], "day": row[1], **p} for p in (res.get("final") or {}).get("plan", [])
            if isinstance(p.get("level"), (int, float))]


# ---------------------------------------------------------------- checking
def check(store, data_dir: str, tickers: list[str], live: dict | None = None, lang: str = "zh") -> list[dict]:
    """New alerts (already recorded once are skipped). `live` overrides the price used per ticker."""
    _init(store)
    zh = lang == "zh"
    live = live or {}
    new = []
    now = dt.datetime.now().isoformat(timespec="seconds")

    def add(key, day, tk, kind, price, text, detail=None):
        cur = store.conn.execute("INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?,?,?,?)",
                                 (key, now, day, tk, kind, price, text, json.dumps(detail or {}, ensure_ascii=False)))
        if cur.rowcount:
            new.append({"key": key, "day": day, "ticker": tk, "kind": kind, "price": price, "text": text, "detail": detail})

    for tk in tickers:
        bars = quotes.load_bars(data_dir, tk).dropna(subset=["close"])
        if len(bars) < 30:
            continue
        q = live.get(tk)
        if q:
            price, prev = float(q["price"]), float(q.get("prev_close") or bars["close"].iloc[-1])
            day = dt.date.today().isoformat()
            hist = bars if bars.index[-1].date() < dt.date.today() else bars.iloc[:-1]
        else:                                                      # no live price: the last daily bar
            price, prev = float(bars["close"].iloc[-1]), float(bars["close"].iloc[-2])
            day = bars.index[-1].date().isoformat()
            hist = bars.iloc[:-1]
        for z in ta.zones(hist):
            lo, hi = round(z["low"], 2), round(z["high"], 2)
            if prev <= z["high"] < price:
                add(f"{day}:{tk}:up:{hi}", day, tk, "zone_up", price,
                    f"{tk} 升破 {lo}–{hi} 区间（现价 {price:g}）" if zh else f"{tk} broke above the {lo}–{hi} zone ({price:g})",
                    {"zone": [lo, hi], "zone_kind": z["kind"]})
            if prev >= z["low"] > price:
                add(f"{day}:{tk}:down:{lo}", day, tk, "zone_down", price,
                    f"{tk} 跌破 {lo}–{hi} 区间（现价 {price:g}）" if zh else f"{tk} broke below the {lo}–{hi} zone ({price:g})",
                    {"zone": [lo, hi], "zone_kind": z["kind"]})
        for p in _team_plans(store, tk):
            lv = float(p["level"])
            if min(prev, price) <= lv <= max(prev, price) and prev != price:
                add(f"{p['call']}:{lv}", day, tk, "team_level", price,
                    (f"{tk} 到了投研团队计划里的 {lv:g}：如果{p.get('if', '')}，那么{p.get('then', '')}" if zh else
                     f"{tk} reached {lv:g} from the research team's plan: if {p.get('if', '')}, then {p.get('then', '')}"),
                    {"call": p["call"], "level": lv})
    try:                                                           # paper fills / cancellations
        from stockproof import paper
        paper._init(store)
        rows = store.conn.execute(
            "SELECT f.order_id, f.day, f.status, f.price, f.shares, f.reason, o.ticker, o.side, a.name FROM paper_fills f "
            "JOIN paper_orders o ON o.id=f.order_id JOIN paper_accounts a ON a.id=o.account").fetchall()
        for oid, day, status, px, n, reason, tk, side, aname in rows:
            if status == "filled":
                t = (f"模拟盘「{aname}」：{'买入' if side == 'buy' else '卖出'} {tk} {n} 股 @ {px:g}" if zh else
                     f"Paper '{aname}': {side} {n} {tk} @ {px:g}")
            else:
                t = f"模拟盘「{aname}」：{tk} 订单取消——{reason}" if zh else f"Paper '{aname}': {tk} order cancelled — {reason}"
            add(f"fill:{oid}", day, tk, "paper_" + status, px, t)
    except Exception:
        pass
    store.conn.commit()
    return new


def recent(store, limit: int = 50) -> list[dict]:
    _init(store)
    cur = store.conn.execute("SELECT key, created_at, day, ticker, kind, price, text FROM alerts ORDER BY created_at DESC, "
                             "rowid DESC LIMIT ?", (limit,))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def market_open(now: dt.datetime | None = None) -> dict:
    """Which markets are in session right now (weekdays; holidays not checked)."""
    from zoneinfo import ZoneInfo
    now = now or dt.datetime.now(dt.timezone.utc)
    sh = now.astimezone(ZoneInfo("Asia/Shanghai"))
    ny = now.astimezone(ZoneInfo("America/New_York"))
    t_sh, t_ny = sh.hour * 60 + sh.minute, ny.hour * 60 + ny.minute
    return {"cn": sh.weekday() < 5 and (570 <= t_sh <= 690 or 780 <= t_sh <= 900),
            "us": ny.weekday() < 5 and 570 <= t_ny <= 960}


def watch(app, store, interval: int = 60, once: bool = False, lang: str = "zh", log=print, notify: bool = True) -> list[dict]:
    """Poll live prices while a market is open and raise alerts. Ctrl-C to stop."""
    from stockproof import digest
    seen = []
    while True:
        tks = watch_list(app, store)
        mo = market_open()
        live_tk = [t for t in tks if mo["cn" if cn.is_cn(t) else "us"]]
        live = live_prices(live_tk) if live_tk else {}
        new = check(store, app.data_dir, tks, live, lang)
        for a in new:
            log(f"[{dt.datetime.now():%H:%M}] {a['text']}")
            if notify:
                digest.notify("stockproof", a["text"] + " " + (NOT_ORDER if lang == "zh" else NOT_ORDER_EN))
        seen += new
        if once:
            return seen
        if not new:
            log(f"[{dt.datetime.now():%H:%M}] {len(tks)} stocks watched, {len(live)} live, no new alerts")
        time.sleep(max(15, interval))
