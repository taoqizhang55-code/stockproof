"""
Whole-market chart scan (A-shares): which stocks broke out of / broke down through a support or
resistance zone today?

Two stages, so the whole market costs a few dozen requests instead of five thousand:
  1. One market list sorted by today's change (Eastmoney): the biggest movers in each direction,
     minus ST names, fresh listings, and anything too illiquid to trade (turnover < MIN_AMOUNT).
  2. For the most liquid candidates only, ~1.5 years of daily bars, then the same zone logic as the
     single-stock chart (ta.signals): zones come from bars before today, a breakout needs volume.

Output is a list of observations with the rule that fired. They are chart facts, NOT orders, and
untested as a strategy until run through the lab.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from stockproof import cn, ta

MIN_AMOUNT = 1e8          # yuan traded today
MIN_MOVE = 0.02           # |change| to be a candidate
MAX_CANDIDATES = 60
FIELDS = {"f12": "code", "f14": "name", "f2": "price", "f3": "pct", "f6": "amount", "f10": "vol_ratio",
          "f8": "turnover", "f20": "cap"}
CHART = ("breakout", "breakdown")


def scan_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "scan")
    os.makedirs(os.path.join(d, "bars"), exist_ok=True)
    return d


def movers(direction: str = "both", pages: int = 2, log=print) -> pd.DataFrame:
    """Today's biggest movers: Eastmoney's market list sorted by change, or Sina's when Eastmoney is down."""
    try:
        return _movers_em(direction, pages)
    except Exception as e:
        log(f"  Eastmoney list unavailable ({type(e).__name__}); using Sina ...")
        return _movers_sina(direction, pages)


def _movers_sina(direction: str, pages: int) -> pd.DataFrame:
    """Sina's whole-A-share list sorted by change (80 rows a page). No volume ratio; the bars check volume."""
    from stockproof import screener
    headers = {**cn.UA, "Referer": "https://finance.sina.com.cn"}
    rows = []
    for asc in ({"up": [0], "down": [1]}.get(direction, [0, 1])):
        for page in range(1, pages + 2):                       # 80 a page: one extra page ~ the same depth
            data = screener._sina_json(screener._get(screener.SINA_URL, {"page": page, "num": 80, "sort": "changepercent",
                                                                          "asc": asc, "node": "hs_a"}, headers, gap=1.0))
            for d in data if isinstance(data, list) else []:
                if isinstance(d, dict) and d.get("code"):
                    rows.append({"f12": str(d["code"]), "f14": str(d.get("name") or ""), "f2": d.get("trade"),
                                 "f3": d.get("changepercent"), "f6": d.get("amount"), "f10": None,
                                 "f8": d.get("turnoverratio"), "f20": d.get("mktcap")})
    if not rows:
        raise RuntimeError("Sina returned no rows")
    return _frame(rows)


def _movers_em(direction: str, pages: int) -> pd.DataFrame:
    from stockproof import screener
    rows = []
    for po in ({"up": [1], "down": [0]}.get(direction, [1, 0])):
        for pn in range(1, pages + 1):
            last = None
            for host in screener.SPOT_HOSTS:
                try:
                    r = screener._get(f"https://{host}/api/qt/clist/get",
                                      {"pn": pn, "pz": 100, "po": po, "np": 1, "fltt": 2, "invt": 2, "fid": "f3",
                                       "fs": screener.A_SHARES, "fields": ",".join(FIELDS)}, cn.UA)
                    diff = ((r.json() or {}).get("data") or {}).get("diff") or []
                    rows += list(diff.values()) if isinstance(diff, dict) else diff
                    last = None
                    break
                except Exception as e:
                    last = e
            if last is not None:
                raise last
    return _frame(rows)


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows).rename(columns=FIELDS)
    if df.empty:
        return pd.DataFrame(columns=list(FIELDS.values()))
    for c in ("price", "pct", "amount", "vol_ratio", "turnover", "cap"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["pct"] /= 100
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str)
    return df.drop_duplicates("code")


def candidates(mv: pd.DataFrame, n: int = MAX_CANDIDATES) -> pd.DataFrame:
    """Liquid, ordinary stocks that moved enough today, most traded first."""
    ok = (mv["pct"].abs() >= MIN_MOVE) & (mv["amount"] >= MIN_AMOUNT) & (mv["price"] > 0)
    ok &= ~mv["name"].str.contains("ST|退", regex=True) & ~mv["name"].str.match(r"^[NC]")
    return mv[ok].sort_values("amount", ascending=False).head(n)


def _bars(data_dir: str, ticker: str, today: dt.date, fetch: bool = True) -> pd.DataFrame | None:
    """~400 days of bars, cached per day in scan/bars (the watchlist's own price files are used when fresh)."""
    from stockproof import quotes
    own = quotes.load_bars(data_dir, ticker)
    if len(own) >= 120 and own.index[-1].date() >= today:
        return own
    p = os.path.join(scan_dir(data_dir), "bars", f"{ticker}.csv")
    if os.path.exists(p) and dt.date.fromtimestamp(os.path.getmtime(p)) >= today:
        return pd.read_csv(p, index_col=0, parse_dates=True)
    if not fetch:
        return None
    try:
        b = quotes.download_bars(ticker, today - dt.timedelta(days=400))
    except Exception:
        return None
    if b is None or b.empty:
        return None
    b.to_csv(p)
    return b


def scan(data_dir: str, direction: str = "both", n: int = MAX_CANDIDATES, lang: str = "zh",
         mv: pd.DataFrame | None = None, fetch: bool = True, log=print) -> dict:
    """Run the scan and save it to scan/market_<day>.json."""
    today = dt.date.today()
    if mv is None:
        mv = movers(direction, log=log)
    cand = candidates(mv, n)
    log(f"  {len(mv)} movers, {len(cand)} liquid candidates; checking their charts ...")
    rules = ta.RULES if lang == "zh" else ta.RULES_EN

    def one(r):
        tk = cn.parse(r.code)["symbol"]
        b = _bars(data_dir, tk, today, fetch)
        if b is None or len(b.dropna(subset=["close"])) < 60:
            return []
        sigs = [sg for sg in ta.signals(b, days=1) if sg["kind"] in CHART]
        if not sigs:
            return []
        zs = {(x["low"], x["high"]): x["touches"] for x in ta.zones(b.iloc[:-1])}
        vr = ta.indicators(b)["vol_ratio"].iloc[-1]                   # from the bars: works for every source
        out = []
        for kind in CHART:                                            # one row per stock and direction
            ks = [sg for sg in sigs if sg["kind"] == kind]
            if not ks:
                continue
            # the most significant zone: the highest one broken out of, the lowest one broken down through
            sg = max(ks, key=lambda x: x["zone"][1]) if kind == "breakout" else min(ks, key=lambda x: x["zone"][0])
            z = sg["zone"]
            out.append({"ticker": tk, "name": r.name, "date": sg["date"], "kind": kind,
                        "direction": sg["direction"], "close": sg["close"], "pct": float(r.pct),
                        "amount": float(r.amount),
                        "vol_ratio": None if pd.isna(vr) else round(float(vr), 2),
                        "zone": z, "touches": zs.get((z[0], z[1])), "zones_crossed": len(ks),
                        "rule": rules[kind]})
        return out

    with ThreadPoolExecutor(max_workers=4) as ex:
        found = [h for hs in ex.map(one, cand.itertuples()) for h in hs]
    # keep only today's bar (a stale cached file would report an old day)
    latest = max((h["date"] for h in found), default=None)
    found = [h for h in found if h["date"] == latest]
    found.sort(key=lambda h: (h["kind"] != "breakout", -h["amount"]))
    res = {"day": latest or today.isoformat(), "scanned_at": dt.datetime.now().isoformat(timespec="seconds"),
           "movers": int(len(mv)), "candidates": int(len(cand)), "hits": found,
           "breakouts": sum(h["kind"] == "breakout" for h in found),
           "breakdowns": sum(h["kind"] == "breakdown" for h in found),
           "how": (f"当天涨跌幅最大的股票里，剔除 ST、新股和成交额不到 {MIN_AMOUNT / 1e8:.0f} 亿的，"
                   f"取成交额最大的 {len(cand)} 只看 K 线；支撑/阻力区间只用今天之前的数据，突破需要放量（量比 ≥ 1.5）。"
                   if lang == "zh" else
                   f"Of today's biggest movers, minus ST names, new listings and stocks trading under "
                   f"{MIN_AMOUNT / 1e8:.0f}00M yuan, the {len(cand)} most traded were charted; zones use only bars "
                   f"before today and a breakout needs volume (ratio >= 1.5)."),
           "note": ("这些是图形上的事实，不是买卖指令；作为策略是否有效，要先在实验室里用历史检验。" if lang == "zh" else
                    "Chart facts, not orders; whether trading them works is untested until run through the lab.")}
    with open(os.path.join(scan_dir(data_dir), f"market_{res['day']}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    return res


def latest(data_dir: str) -> dict | None:
    d = scan_dir(data_dir)
    files = sorted(f for f in os.listdir(d) if f.startswith("market_") and f.endswith(".json"))
    if not files:
        return None
    with open(os.path.join(d, files[-1]), encoding="utf-8") as f:
        return json.load(f)
