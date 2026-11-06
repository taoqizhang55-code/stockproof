"""
A long-term investment plan: split money across A-shares, government bonds, gold and US stocks, buy every month,
tilt the A-share part toward cheap times, and rebalance once a year. Nothing here forecasts anything; the
return comes from holding several assets with real long-run returns and from the discipline.

Every profile is shown with what it did historically from several start dates, including buying at the
2007 and 2015 tops, its worst year and its deepest fall.

Data: monthly closes of the indices (Eastmoney, cached in plan/). Simplifications, stated on screen: price
indices without dividends (the bond index includes coupons), US indices in dollars, no fund fees.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os

import numpy as np
import pandas as pd

ASSETS = {
    "hs300": {"name": "沪深300", "en": "CSI 300", "secid": "1.000300", "etf": "510300", "etf_name": "沪深300ETF", "a": True},
    "zz500": {"name": "中证500", "en": "CSI 500", "secid": "1.000905", "etf": "510500", "etf_name": "中证500ETF", "a": True},
    "bond": {"name": "国债", "en": "Treasuries", "secid": "1.000012", "etf": "511010", "etf_name": "国债ETF", "a": False},
    "gold": {"name": "黄金", "en": "Gold", "secid": "118.AU9999", "etf": "518880", "etf_name": "黄金ETF", "a": False},
    "spx": {"name": "标普500", "en": "S&P 500", "secid": "100.SPX", "etf": "513500", "etf_name": "标普500ETF（QDII）", "a": False},
    # US-listed ETFs for a dollar account (prices adjusted for dividends)
    "vti": {"name": "美国全市场", "en": "US total market", "secid": "107.VTI", "fqt": "1", "etf": "VTI", "etf_name": "Vanguard VTI", "a": False},
    "efa": {"name": "美国以外发达市场", "en": "Developed ex-US", "secid": "107.EFA", "fqt": "1", "etf": "EFA", "etf_name": "iShares EFA", "a": False},
    "agg": {"name": "美国债券", "en": "US bonds", "secid": "107.AGG", "fqt": "1", "etf": "AGG", "etf_name": "iShares AGG", "a": False},
    "gld": {"name": "黄金（美元）", "en": "Gold (USD)", "secid": "107.GLD", "fqt": "1", "etf": "GLD", "etf_name": "SPDR GLD", "a": False},
    "fxi": {"name": "中国大盘股（美元）", "en": "China large caps (USD)", "secid": "107.FXI", "fqt": "1", "etf": "FXI", "etf_name": "iShares FXI", "a": False},
}
PROFILES = {
    "conservative": {"zh": "稳健", "w": {"hs300": 0.20, "bond": 0.50, "gold": 0.15, "spx": 0.15}},
    "balanced": {"zh": "平衡", "w": {"hs300": 0.125, "zz500": 0.125, "bond": 0.25, "gold": 0.25, "spx": 0.25}},
    "growth": {"zh": "进取", "w": {"hs300": 0.20, "zz500": 0.20, "bond": 0.15, "gold": 0.15, "spx": 0.30}},
    "a_only": {"zh": "只买沪深300（对照）", "w": {"hs300": 1.0}},
    # in dollars, for an account in the US
    "us_conservative": {"zh": "美元·稳健", "w": {"vti": 0.25, "efa": 0.10, "agg": 0.50, "gld": 0.15}, "currency": "usd"},
    "us_balanced": {"zh": "美元·平衡", "w": {"vti": 0.35, "efa": 0.15, "fxi": 0.05, "agg": 0.30, "gld": 0.15}, "currency": "usd"},
    "us_growth": {"zh": "美元·进取", "w": {"vti": 0.55, "efa": 0.20, "fxi": 0.05, "agg": 0.10, "gld": 0.10}, "currency": "usd"},
    "us_only": {"zh": "只买美国全市场（对照）", "w": {"vti": 1.0}, "currency": "usd"},
}
STARTS = ["2005-01", "2007-10", "2015-06", "2018-01"]
CASH_RATE = 0.02
TILT_LOOKBACK = 60                     # months of A-share history the "cheap or expensive" position is judged on


def _dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "plan")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- data
def _fetch(secid: str, fqt: str = "0") -> pd.Series:
    import requests
    r = requests.get("https://push2his.eastmoney.com/api/qt/stock/kline/get",
                     params={"secid": secid, "klt": "103", "fqt": fqt, "beg": "20050101", "end": "20500101",
                             "fields1": "f1", "fields2": "f51,f53"},
                     headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, timeout=20)
    k = (r.json().get("data") or {}).get("klines") or []
    s = pd.Series({pd.Timestamp(x.split(",")[0]).to_period("M"): float(x.split(",")[1]) for x in k}, dtype=float)
    return s.sort_index()


AK_FALLBACK = {"hs300": ("index", "sh000300"), "zz500": ("index", "sh000905"), "bond": ("index", "sh000012"),
               "gold": ("sge", "Au99.99"), "spx": ("us", ".INX")}


def _fetch_ak(asset: str) -> pd.Series:
    """Same series from AKShare (Sina / SGE) when Eastmoney refuses."""
    from stockproof import cn
    if asset not in AK_FALLBACK:
        raise KeyError(asset)
    kind, sym = AK_FALLBACK[asset]
    ak = cn._ak()
    if kind == "index":
        df = ak.stock_zh_index_daily(symbol=sym)
        d, c = df["date"], df["close"]
    elif kind == "sge":
        df = ak.spot_hist_sge(symbol=sym)
        d, c = df["date"], df["close"]
    else:
        df = ak.index_us_stock_sina(symbol=sym)
        d, c = df["date"], df["close"]
    s = pd.Series(pd.to_numeric(c, errors="coerce").to_numpy(), index=pd.to_datetime(d)).dropna()
    s = s[s.index >= "2005-01-01"].resample("ME").last().dropna()
    s.index = s.index.to_period("M")
    return s


def monthly(data_dir: str, fetch: bool = True) -> pd.DataFrame:
    """Month-end closes of every asset (cached; refreshed at most daily)."""
    p = os.path.join(_dir(data_dir), "monthly.csv")
    if os.path.exists(p) and (not fetch or dt.date.fromtimestamp(os.path.getmtime(p)) >= dt.date.today()):
        df = pd.read_csv(p, index_col=0)
        df.index = pd.PeriodIndex(df.index, freq="M")
        if not fetch or set(ASSETS) <= set(df.columns):
            return df
    if not fetch:
        return pd.DataFrame()
    cols = {}
    for a, x in ASSETS.items():
        for get in (lambda: _fetch(x["secid"], x.get("fqt", "0")), lambda: _fetch_ak(a)):
            try:
                s = get()
                if len(s) > 24:
                    cols[a] = s
                    break
            except Exception:
                continue
    if not cols:
        if os.path.exists(p):
            return monthly(data_dir, fetch=False)
        raise RuntimeError("index data unavailable (Eastmoney): try again later")
    df = pd.DataFrame(cols).sort_index()
    df.to_csv(p)
    return df


# ---------------------------------------------------------------- simulation
def tilt(a_prices: pd.Series, i: int) -> float:
    """How much of the A-share contribution to invest this month: 2.25x when the index sits at the bottom of its
    last 5 years, 0.25x at the top, 1.25x in the middle."""
    w = a_prices.iloc[max(0, i - TILT_LOOKBACK):i + 1].dropna()
    if len(w) < 12:
        return 1.0
    pct = float((w <= w.iloc[-1]).mean())
    return float(min(2.25, max(0.25, 2.25 - 2 * pct)))


def simulate(px: pd.DataFrame, weights: dict, start: str, monthly_amount: float = 0.0, initial: float = 0.0,
             use_tilt: bool = True, rebalance_months: int = 12) -> dict:
    """Month by month: add `monthly_amount` (A-share part scaled by `tilt`, the rest of the month's money to the
    others by weight, anything held back stays in cash), and rebalance every `rebalance_months` to the weights."""
    w = {a: x for a, x in weights.items() if x > 0}
    df = px[list(w)].loc[pd.Period(start, "M"):].dropna()
    if len(df) < 13:
        return {"error": "not enough history"}
    a_assets = [a for a in w if ASSETS[a]["a"]]
    a_share = sum(w[a] for a in a_assets)
    ref = df[a_assets].mean(axis=1) if a_assets else None
    hold = {a: initial * w[a] for a in w}
    cash, flows, values, contributed = 0.0, [], [], initial
    if initial:
        flows.append(-initial)
    for i in range(len(df)):
        if i:
            for a in hold:
                hold[a] *= df[a].iloc[i] / df[a].iloc[i - 1]
            cash *= 1 + CASH_RATE / 12
        if monthly_amount:
            cash += monthly_amount
            contributed += monthly_amount
            flows.append(-monthly_amount)
            m = tilt(ref, i) if (use_tilt and a_assets) else 1.0
            budget = min(cash, monthly_amount * (a_share * m + (1 - a_share)))
            a_amt = min(budget, monthly_amount * a_share * m)
            other = budget - a_amt
            for a in w:
                if ASSETS[a]["a"]:
                    hold[a] += a_amt * w[a] / a_share if a_share else 0
                else:
                    hold[a] += other * w[a] / (1 - a_share) if a_share < 1 else 0
            cash -= budget
        if rebalance_months and i and i % rebalance_months == 0:
            tot = sum(hold.values())
            hold = {a: tot * w[a] for a in w}
        values.append(sum(hold.values()) + cash)
    v = np.array(values)
    peak = np.maximum.accumulate(v)
    dd = float((v / peak - 1).min())
    flows[-1] = flows[-1] + v[-1] if flows else 0
    if not monthly_amount:
        flows = [-initial] + [0.0] * (len(v) - 2) + [v[-1]]
    yearly = [v[j] / v[j - 12] - 1 for j in range(12, len(v))] if not monthly_amount else []
    return {"start": str(df.index[0]), "end": str(df.index[-1]), "years": round((len(df) - 1) / 12, 1),
            "final": float(v[-1]), "contributed": float(contributed), "irr": _irr(flows),
            "max_drawdown": dd, "worst_year": float(min(yearly)) if yearly else None,
            "cash_left": float(cash), "path": [[str(p), round(float(x), 2)] for p, x in zip(df.index, v)]}


def _irr(flows: list[float]) -> float | None:
    if not flows or sum(flows) == 0 and flows[-1] == 0:
        return None
    lo, hi = -0.3, 0.3                               # monthly rates
    f = np.array(flows, dtype=float)
    t = np.arange(len(f))
    npv = lambda r: float((f / (1 + r) ** t).sum())
    if npv(lo) * npv(hi) > 0:
        return None
    if abs(npv(0.0)) < 1e-9 * max(1.0, abs(f).sum()):
        return 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (1 + (lo + hi) / 2) ** 12 - 1


def history(data_dir: str, fetch: bool = True) -> dict:
    """Every profile from every start date: a lump sum (rebalanced yearly) and monthly buying with the tilt."""
    px = monthly(data_dir, fetch)
    out = {"made": dt.date.today().isoformat(), "through": str(px.index[-1]), "profiles": {}}
    for k, p in PROFILES.items():
        rows = {}
        for s in STARTS:
            lump = simulate(px, p["w"], s, initial=1.0)
            dca = simulate(px, p["w"], s, monthly_amount=1.0)
            plain = simulate(px, p["w"], s, monthly_amount=1.0, use_tilt=False)
            rows[s] = {"lump_cagr": _cagr(lump), "lump_maxdd": lump.get("max_drawdown"), "worst_year": lump.get("worst_year"),
                       "dca_irr": dca.get("irr"), "dca_plain_irr": plain.get("irr"), "dca_maxdd": dca.get("max_drawdown")}
        out["profiles"][k] = {"name": p["zh"], "weights": p["w"], "starts": rows,
                              "lump_path": simulate(px, p["w"], STARTS[0], initial=1.0).get("path")}
    with open(os.path.join(_dir(data_dir), "history.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


def _cagr(r: dict) -> float | None:
    if "error" in r or not r.get("years"):
        return None
    return float(r["final"] ** (1 / r["years"]) - 1)


# ---------------------------------------------------------------- this month's plan
def this_month(data_dir: str, profile: str, amount: float, holdings: dict | None = None, fetch: bool = True,
               lang: str = "zh") -> dict:
    """What to buy this month: the A-share part scaled by how cheap A-shares are now, new money steered toward
    whatever is below its target weight, and a rebalance warning when any weight is 5+ points off."""
    zh = lang == "zh"
    px = monthly(data_dir, fetch)
    w = PROFILES[profile]["w"]
    a_assets = [a for a in w if ASSETS[a]["a"]]
    ref = px[a_assets].mean(axis=1).dropna()
    m = tilt(ref, len(ref) - 1) if a_assets else 1.0
    pct = float((ref.iloc[-TILT_LOOKBACK:] <= ref.iloc[-1]).mean()) if len(ref) else None
    a_share = sum(w[a] for a in a_assets)
    a_amt = amount * a_share * m                   # above 1x the extra comes from cash kept back in dearer months
    other = amount * (1 - a_share)
    held_back = max(0.0, amount - a_amt - other)
    extra = max(0.0, a_amt + other - amount)
    holdings = holdings or {}
    tot = sum(holdings.values())
    buys = {}
    for a in w:
        base = (a_amt * w[a] / a_share) if ASSETS[a]["a"] else (other * w[a] / (1 - a_share) if a_share < 1 else 0)
        buys[a] = base
    drift = {}
    if tot > 0:                                    # steer this month's non-A money toward underweight assets
        for a in w:
            drift[a] = holdings.get(a, 0) / tot - w[a]
    rows = [{"asset": a, "name": ASSETS[a]["name"] if zh else ASSETS[a]["en"], "etf": ASSETS[a]["etf"],
             "etf_name": ASSETS[a]["etf_name"], "target": w[a], "buy": round(buys[a], 2),
             "now_weight": None if tot <= 0 else holdings.get(a, 0) / tot,
             "drift": drift.get(a)} for a in w]
    rebalance = [r for r in rows if r["drift"] is not None and abs(r["drift"]) >= 0.05]
    pos = ("便宜" if pct is not None and pct <= 0.3 else "偏贵" if pct is not None and pct >= 0.7 else "中等") if zh else \
          ("cheap" if pct is not None and pct <= 0.3 else "expensive" if pct is not None and pct >= 0.7 else "middle")
    usd = PROFILES[profile].get("currency") == "usd"
    reb_zh = "有资产偏离目标 5 个百分点以上，建议这次再平衡。" if rebalance else ""
    reb_en = " Some weights are 5+ points off target: rebalance this time." if rebalance else ""
    if not a_assets:
        note = ("每月按目标比例买入，偏离 5 个百分点以上就再平衡。" + reb_zh) if zh else \
               ("Buy at target weights every month; rebalance when a weight is 5+ points off." + reb_en)
    elif zh:
        note = (f"A 股现在处在过去 5 年价格的第 {100 * (pct or 0):.0f} 百分位（{pos}），这个月 A 股部分投入正常额度的 {m:.2f} 倍"
                + (f"，少投的 {held_back:,.0f} 先留作现金，等便宜时再投" if held_back > 0 else "")
                + (f"，多出的 {extra:,.0f} 用之前留下的现金（没有就按正常额度买）" if extra > 0 else "") + "。" + reb_zh)
    else:
        note = (f"A-shares sit at the {100 * (pct or 0):.0f}th percentile of their last 5 years ({pos}): the A-share part "
                f"gets {m:.2f}x its normal amount" + (f"; {held_back:,.0f} is kept as cash for cheaper times" if held_back > 0 else "")
                + "." + reb_en)
    if usd:
        caveats = ("美元 ETF 的历史价格已按分红复权，以美元计，没扣基金费用（VTI、AGG 等费率很低）；黄金过去 20 年表现特别好，"
                   "未来不一定一样。不是投资建议。") if zh else \
                  "US ETF history is dividend-adjusted, in dollars, before (low) fund fees; gold had an unusually good 20 years. Not advice."
    else:
        caveats = ("历史成绩用的是价格指数（不含分红，国债指数含利息）、美股按美元计算、没扣基金费用；"
                   "黄金和美股是过去 20 年表现最好的两类资产，未来不一定一样。不是投资建议。") if zh else \
                  ("History uses price indices (no dividends; the bond index includes coupons), US in dollars, no "
                   "fund fees; gold and US stocks had an unusually good 20 years. Not advice.")
    return {"profile": profile, "profile_name": PROFILES[profile]["zh"], "amount": amount, "rows": rows,
            "a_share_position": pct, "a_share_label": pos, "a_multiplier": m, "held_back": round(held_back, 2),
            "extra_from_cash": round(extra, 2), "rebalance": rebalance, "as_of": str(px.index[-1]),
            "currency": "usd" if usd else "cny", "note": note, "caveats": caveats}


def summary_text(h: dict, lang: str = "zh") -> list[str]:
    zh = lang == "zh"
    out = []
    pct = lambda v: "—" if v is None else f"{100 * v:+.1f}%"
    for k, p in h["profiles"].items():
        st = p["starts"]
        parts = []
        for s in STARTS:
            r = st.get(s) or {}
            parts.append(f"{s} 起 {pct(r.get('lump_cagr'))}/年" if zh else f"from {s} {pct(r.get('lump_cagr'))}/yr")
        r0 = st.get(STARTS[0]) or {}
        out.append(f"{p['name']}：" + "，".join(parts) + (f"；最大回撤 {pct(r0.get('lump_maxdd'))}，最差一年 {pct(r0.get('worst_year'))}；"
                                                       f"每月定投（含估值调整）{pct(r0.get('dca_irr'))}/年，普通定投 {pct(r0.get('dca_plain_irr'))}/年"
                                                       if zh else f"; max drawdown {pct(r0.get('lump_maxdd'))}, worst year {pct(r0.get('worst_year'))}; "
                                                       f"monthly with tilt {pct(r0.get('dca_irr'))}/yr, plain {pct(r0.get('dca_plain_irr'))}/yr"))
    return out
