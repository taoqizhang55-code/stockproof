"""
The quant lab: test a trading idea on point-in-time history, the way a careful researcher would.

An AI agent (or you) describes a strategy as a small JSON spec; the lab runs it on real data with real
frictions and writes an illustrated report. Two guards against fooling yourself are built in:

  * A locked holdout. The most recent HOLDOUT_YEARS are hidden while you explore. When a strategy looks
    good, `confirm` runs it once on the hidden period. A strategy can be confirmed only once.
  * Counting tries. Every explored variant is logged. The more variants were tried, the higher the bar
    for calling a result significant (Bonferroni on the daily excess-return t-statistic), and the
    report says so in plain words.
  * 2x cost stress. Every run is repeated with all trading costs doubled; a strategy whose edge is gone
    at 2x costs is flagged "fragile" (practitioners' rule: budget twice the fees you expect).
  * Walk-forward. Picking the best of many variants is itself fitting. Each year, using only the years
    before it, the lab picks the best of the variants you tried for this question and records how that
    pick did in the next year. The stitched out-of-sample years are compared with the in-sample best.

Strategy types
  earnings   A-share (CSI 300) or US quarterly reports: filter on SUE, the reaction, the LLM's tone,
             guidance, revenue / profit growth, ROE, gross margin, industry, report month.
  forecast   A-share 业绩预告 (profit pre-announcements): filter on type (预增, 扭亏, 预减 …) and size.
  policy     新闻联播 industry policy signals: trade the Shenwan industry index after a signal.
  factor     Periodic rebalance into the top-N stocks by chosen fundamentals / momentum.

Universe caveat (always shown): stock strategies trade the stocks the research price file covers
(today's CSI 300 members, or the US sample) — large caps, with survivorship; the benchmark is the
equal-weighted average of the same stocks, so the excess return is the meaningful number.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import time

import numpy as np
import pandas as pd

from stockproof import clock

HOLDOUT_YEARS = 2
STRESS_MULT = 2.0          # cost stress test: every cost doubled
WF_WARMUP = 2              # walk-forward: years of history before the first out-of-sample year
WF_MAX_VARIANTS = 12
TYPES = ("earnings", "forecast", "smart_money", "policy", "factor")
OPS = {">=": lambda s, v: s >= v, "<=": lambda s, v: s <= v, ">": lambda s, v: s > v, "<": lambda s, v: s < v,
       "==": lambda s, v: s == v, "!=": lambda s, v: s != v,
       "in": lambda s, v: s.isin(v if isinstance(v, list) else [v]),
       "not_in": lambda s, v: ~s.isin(v if isinstance(v, list) else [v]),
       "contains": lambda s, v: s.astype(str).str.contains(str(v), regex=False, na=False),
       "between": lambda s, v: s.between(v[0], v[1])}

FIELDS = {
    "earnings": {
        "sue": "earnings surprise: (EPS − same quarter last year) / its usual variation; 2 = big beat",
        "reaction": "market-adjusted return on days 0–1 after the report (known at entry)",
        "pre": "market-adjusted return in the 5 days before the report",
        "tone": "LLM tone of the report, −1..1 (only for reports that were read; most are 2024+)",
        "guidance": "LLM guidance label: raised / maintained / lowered / provided / withdrawn / none",
        "rev_yoy": "revenue growth year on year, % (A-shares)",
        "np_yoy": "net profit growth year on year, % (A-shares; empty when EPS ≤ 0)",
        "roe": "annualized return on equity, % (A-shares)",
        "gm": "gross margin, % (A-shares)",
        "industry": "Eastmoney industry name, e.g. 半导体, 银行 (A-shares; use 'contains' or 'in')",
        "quarter": "fiscal quarter of the report: 1, 2, 3 or 4",
    },
    "forecast": {
        "type": "预增, 略增, 扭亏, 续盈, 预减, 略减, 首亏, 续亏, 增亏, 减亏, 不确定",
        "change_pct": "forecast profit change vs last year, % (mid-point)",
        "industry": "Eastmoney industry name",
        "quarter": "period the forecast is for: 1, 2, 3 or 4",
    },
    "smart_money": {
        "category": "national (汇金/证金/国新/诚通…), social (社保/养老金), northbound (香港中央结算), insurance, qfii, fund",
        "action": "new, add, reduce, same, or exit (left the top-10 tradable holders since last quarter)",
        "confidence": "disclosed, inferred (exit: must have sold) or possible (exit: sold or pushed out)",
        "value_yi": "value of the position at quarter end, 亿 yuan",
        "value_change_yi": "estimated value bought (+) / sold (−) in the quarter, 亿 yuan",
        "change_pct": "change in shares held, %",
        "holders": "how many entities of that kind hold the stock",
        "industry": "Eastmoney industry name",
        "quarter": "quarter of the report: 1, 2, 3 or 4",
    },
    "policy": {
        "industry": "Shenwan level-1 industry, e.g. 电子, 计算机, 电力设备, 医药生物",
        "stance": "support or restrict",
        "strength": "wording strength 1–4 (研究/鼓励 → 稳步推进 → 加快/重点支持 → 大力/国家战略)",
        "kind": "new_measure, leader_directive or report",
        "escalation": "true = stronger than anything said about the industry in the previous 60 days",
    },
    "factor": {},
}
FACTORS = ("sue", "rev_yoy", "np_yoy", "roe", "mom60")


class SpecError(ValueError):
    """The spec can't be run; the message says what to change."""


# ---------------------------------------------------------------- paths and data

def lab_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "lab")
    os.makedirs(os.path.join(d, "reports"), exist_ok=True)
    return d


def holdout_start() -> pd.Timestamp:
    t = clock.today()
    return pd.Timestamp(t.year - HOLDOUT_YEARS, t.month, min(t.day, 28))


def _resolve(data_dir: str, path: str | None) -> str | None:
    if not path:
        return None
    for p in (path, os.path.join(os.path.dirname(os.path.abspath(data_dir)), path), os.path.join(data_dir, path)):
        if os.path.exists(p):
            return p
    return None


_CACHE: dict = {}


def _memo(key, path, loader):
    stamp = (key, path, os.path.getmtime(path) if path and os.path.exists(path) else None)
    if stamp not in _CACHE:
        _CACHE[stamp] = loader()
    return _CACHE[stamp]


def stock_prices(data_dir: str, market: str) -> pd.DataFrame | None:
    from stockproof import research
    meta = research.saved_meta(data_dir, market) or {}
    path = _resolve(data_dir, meta.get("prices_path"))
    if not path:
        return None
    return _memo("prices", path, lambda: research.load_prices(path))


def earnings_events(data_dir: str, market: str) -> pd.DataFrame | None:
    path = os.path.join(data_dir, "research", f"{market}_earnings.csv")
    if not os.path.exists(path):
        return None

    def load():
        ev = pd.read_csv(path, dtype={"accession": object})
        if "date_source" in ev:
            ev = ev[ev["date_source"] == "8-K"]
        ev = ev.dropna(subset=["day0"]).copy()
        ev["day0"] = pd.to_datetime(ev["day0"])
        ev["end"] = pd.to_datetime(ev["end"])
        ev["quarter"] = ev["end"].dt.quarter
        if market == "cn":
            fund = fundamentals(data_dir)
            if fund is not None and len(fund):
                ev["code"] = ev["ticker"].str[:6]
                ev = ev.merge(fund, on=["code", "end"], how="left")
        return ev.reset_index(drop=True)
    return _memo("earnings", path, load)


def fundamentals(data_dir: str) -> pd.DataFrame | None:
    """Revenue / profit growth, ROE, margin and industry per (stock, report period), from the screen's cache."""
    from stockproof import cn, screener
    d = os.path.join(data_dir, "cn")
    if not os.path.isdir(d) or not any(f.startswith("research_yjbb2_") for f in os.listdir(d)):
        return None
    cache = os.path.join(lab_dir(data_dir), "fundamentals.pkl")
    newest = max(os.path.getmtime(os.path.join(d, f)) for f in os.listdir(d) if f.startswith("research_yjbb2_"))
    if os.path.exists(cache) and os.path.getmtime(cache) >= newest:
        return pd.read_pickle(cache)
    rows = []
    for f in sorted(os.listdir(d)):
        if not (f.startswith("research_yjbb2_") and f.endswith(".json")):
            continue
        end = pd.Timestamp(f[15:23])
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            for r in json.load(fh):
                rows.append({"code": r["code"], "end": end, "eps_ytd": r.get("eps"), "rev_yoy": r.get("rev_yoy"),
                             "np_yoy": r.get("np_yoy"), "roe_ytd": r.get("roe"), "gm": r.get("gm"),
                             "industry": r.get("industry") or None})
    df = pd.DataFrame(rows)
    if not len(df):
        return None
    df = df.drop_duplicates(["code", "end"], keep="last")
    df["roe"] = df["roe_ytd"] * 12 / df["end"].dt.month
    bad = df["eps_ytd"] <= 0
    df.loc[bad, ["np_yoy", "roe"]] = np.nan
    df = df.drop(columns=["eps_ytd", "roe_ytd"])
    df.to_pickle(cache)
    return df


def forecast_table(data_dir: str, date: str, max_age_days: float = 2) -> list[dict]:
    """业绩预告 for one report period (A-shares; cached like the other report tables)."""
    from stockproof import cn
    from stockproof import research_cn as rc
    cache = cn.CNCache(data_dir)
    name = f"research_yjyg_{date}.json"
    old = (clock.today() - dt.date(int(date[:4]), int(date[4:6]), int(date[6:]))).days > 400
    data = cache.load(name, None if old else max_age_days * 24)
    if data is not None:
        return data
    df = None
    for attempt in range(3):
        try:
            df = cn._ak().stock_yjyg_em(date=date)
            break
        except (KeyError, TypeError):
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    out = []
    if df is not None and len(df):
        col = lambda *k: rc._col(df, *k)
        c_code, c_ind, c_type = col("股票代码"), col("预测指标"), col("预告类型")
        c_chg, c_date = col("业绩变动幅度"), col("公告日期")
        seen = {}
        for _, r in df.iterrows():
            code = rc._code6(r[c_code])
            ind = str(r[c_ind]) if c_ind else ""
            rank = 0 if "归属" in ind and "扣除" not in ind else (1 if "净利润" in ind else 2)
            if code in seen and seen[code][0] <= rank:
                continue
            d = pd.to_datetime(r[c_date], errors="coerce")
            chg = pd.to_numeric(r[c_chg], errors="coerce") if c_chg else np.nan
            seen[code] = (rank, {"code": code, "type": str(r[c_type]) if c_type else "",
                                 "change_pct": None if pd.isna(chg) else float(chg),
                                 "date": None if pd.isna(d) else d.strftime("%Y-%m-%d")})
        out = [v for _, v in seen.values()]
    cache.save(name, out)
    return out


def forecast_events(data_dir: str, since: str = "2016-01-01", log=print, download: bool = True) -> pd.DataFrame:
    from stockproof import research_cn as rc
    rows = []
    periods = rc.period_ends(since)
    for k, date in enumerate(periods, 1):
        try:
            recs = forecast_table(data_dir, date) if download else None
        except Exception as e:
            log(f"  业绩预告 {date}: {type(e).__name__}")
            continue
        if recs is None:
            continue
        for r in recs:
            if r.get("date"):
                rows.append({**r, "end": pd.Timestamp(date)})
        if k % 10 == 0:
            log(f"  业绩预告 periods {k}/{len(periods)}")
    ev = pd.DataFrame(rows)
    if not len(ev):
        return ev
    from stockproof import cn
    ev["ticker"] = [cn.canonical(c) for c in ev["code"]]
    ev["day0"] = pd.to_datetime(ev["date"])
    ev["quarter"] = ev["end"].dt.quarter
    fund = fundamentals(data_dir)
    if fund is not None:
        ev = ev.merge(fund[["code", "end", "industry"]], on=["code", "end"], how="left")
    return ev


# ---------------------------------------------------------------- the spec

FIELD_ZH = {"sue": "业绩惊喜SUE", "reaction": "公布两天涨跌", "pre": "公布前5天涨跌", "tone": "AI读财报语气",
            "guidance": "业绩指引", "rev_yoy": "营收增长%", "np_yoy": "利润增长%", "roe": "年化ROE%", "gm": "毛利率%",
            "industry": "行业", "quarter": "季度", "type": "预告类型", "change_pct": "预告变动%", "stance": "态度",
            "strength": "措辞强度", "kind": "类别", "escalation": "措辞升级", "category": "资金类型",
            "action": "动作", "confidence": "可信度", "value_yi": "持仓市值(亿)", "value_change_yi": "估算买卖金额(亿)",
            "holders": "持有主体数"}
OP_ZH = {"contains": "包含", "in": "属于", "not_in": "不属于", "between": "介于"}


def describe_spec(spec: dict, lang: str = "zh") -> str:
    zh = lang == "zh"
    t = spec.get("type")
    conds = []
    for f in spec.get("filters") or []:
        v = f.get("value")
        v = "、".join(map(str, v)) if isinstance(v, list) else v
        field = FIELD_ZH.get(f.get("field"), f.get("field")) if zh else f.get("field")
        op = OP_ZH.get(f.get("op"), f.get("op")) if zh else f.get("op")
        conds.append(f"{field} {op} {v}")
    what = {"earnings": "财报发布后" if zh else "after quarterly reports",
            "forecast": "业绩预告发布后" if zh else "after profit pre-announcements (业绩预告)",
            "smart_money": "十大流通股东公布后（聪明钱持仓变化）" if zh else "after top-10 holder disclosures (smart money)",
            "policy": "新闻联播政策信号后买入申万行业指数" if zh else "after 新闻联播 policy signals, buy the Shenwan industry index",
            "factor": "定期调仓买入因子得分最高的股票" if zh else "rebalance into the top stocks by factors"}.get(t, t)
    parts = [what]
    if conds:
        parts.append(("条件：" if zh else "when ") + "；".join(conds))
    if t == "factor":
        parts.append(f"{'因子' if zh else 'factors'}: {', '.join(spec.get('factors') or FACTORS)} · top {spec.get('top', 30)}")
    else:
        parts.append((f"第 {spec.get('entry_lag', 1)} 个交易日收盘买入，持有 {spec.get('hold_days', 20)} 个交易日" if zh else
                      f"buy at the close of trading day {spec.get('entry_lag', 1)}, hold {spec.get('hold_days', 20)} trading days"))
    return "，".join(parts) if zh else ", ".join(parts)


def validate(spec: dict) -> dict:
    """A cleaned copy with defaults; SpecError with a fixable message otherwise."""
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object")
    t = spec.get("type")
    if t not in TYPES:
        raise SpecError(f"type must be one of {', '.join(TYPES)}")
    out = {"type": t, "name": str(spec.get("name") or "")[:80]}
    out["market"] = spec.get("market", "cn")
    if out["market"] not in ("cn", "us") or (out["market"] == "us" and t != "earnings"):
        raise SpecError("market must be cn (all types) or us (earnings only)")
    filters = []
    for f in spec.get("filters") or []:
        if not isinstance(f, dict) or "field" not in f or "op" not in f or "value" not in f:
            raise SpecError("each filter needs field, op and value, e.g. {\"field\": \"sue\", \"op\": \">=\", \"value\": 2}")
        if t != "factor" and f["field"] not in FIELDS[t]:
            raise SpecError(f"unknown field '{f['field']}' for {t}; available: {', '.join(FIELDS[t])}")
        if f["op"] not in OPS:
            raise SpecError(f"op must be one of {', '.join(OPS)}")
        if f["op"] == "between" and not (isinstance(f["value"], list) and len(f["value"]) == 2):
            raise SpecError("between needs a two-element list, e.g. [0.5, 2]")
        filters.append({"field": f["field"], "op": f["op"], "value": f["value"]})
    out["filters"] = filters
    if t == "factor":
        fs = spec.get("factors") or list(FACTORS)
        bad = [f for f in fs if f not in FACTORS]
        if bad:
            raise SpecError(f"factors must be among {', '.join(FACTORS)}")
        out["factors"] = list(fs)
        out["top"] = int(spec.get("top", 30))
        if not 5 <= out["top"] <= 100:
            raise SpecError("top must be 5–100")
    else:
        out["hold_days"] = int(spec.get("hold_days", 20))
        out["entry_lag"] = int(spec.get("entry_lag", 1))
        out["slots"] = int(spec.get("slots", 20))
        if not 1 <= out["hold_days"] <= 250:
            raise SpecError("hold_days must be 1–250 trading days")
        if not 1 <= out["entry_lag"] <= 10:
            raise SpecError("entry_lag must be 1–10 (1 = the close of the trading day after the news)")
        if not 1 <= out["slots"] <= 100:
            raise SpecError("slots must be 1–100")
    return out


def spec_hash(spec: dict) -> str:
    key = {k: v for k, v in spec.items() if k != "name"}
    return hashlib.sha1(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def apply_filters(ev: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    for f in filters:
        if f["field"] not in ev.columns:
            raise SpecError(f"field '{f['field']}' has no data here")
        s = ev[f["field"]]
        if f["field"] == "escalation":
            s = s.astype(bool)
        ev = ev[OPS[f["op"]](s, f["value"]).fillna(False)]
    return ev


# ---------------------------------------------------------------- running

def scaled_costs(market: str, mult: float = 1.0):
    """The market's trading costs with every component multiplied by `mult`."""
    from stockproof.backtest import COSTS, Costs
    c = COSTS.get(market, Costs())
    if mult == 1.0:
        return c
    return dataclasses.replace(c, commission=c.commission * mult, slippage=c.slippage * mult,
                               stamp_duty=c.stamp_duty * mult, stamp_duty_after=c.stamp_duty_after * mult)


def _stock_backtest(ev: pd.DataFrame, prices: pd.DataFrame, market: str, spec: dict,
                    start: pd.Timestamp | None, end: pd.Timestamp | None, cost_mult: float = 1.0) -> dict:
    from stockproof import backtest as bt
    px = prices
    if start is not None:
        px = px[px.index >= start - pd.Timedelta(days=10)]
    if end is not None:
        px = px[px.index < end]
    ev = ev.copy()
    ev["sue"] = 1.0                                            # every selected event is a long signal
    run = bt.run(ev, px, market, long_sue=0.5, short_sue=-1e9, hold=spec["hold_days"],
                 slots=spec["slots"], entry_lag=spec["entry_lag"], costs=scaled_costs(market, cost_mult))
    s = bt.summarize(run)
    trades = run["trades"]
    per = []
    if len(trades):
        net = run["long_trade_excess"]
        for (_, t), x in zip(trades[trades["side"] == 1].iterrows(), net):
            per.append({"ticker": t["ticker"], "entry": t["entry_date"], "exit": t["exit_date"], "excess": float(x)})
    return {"summary": s, "trades": per, "excess": run["long_excess"], "n": run["long_n"]}


def _policy_backtest(ev: pd.DataFrame, px: pd.DataFrame, spec: dict, start, end, cost_per_side: float = 0.001) -> dict:
    """Hold each signalled industry index for hold_days from the next open (via close-to-close after day 1)."""
    from stockproof.policy import NAME_TO_CODE
    closes = px[[c for c in px.columns if c.endswith("_c")]].rename(columns=lambda c: c[:-2])
    if start is not None:
        closes = closes[closes.index >= start - pd.Timedelta(days=10)]
    if end is not None:
        closes = closes[closes.index < end]
    ret = closes.pct_change(fill_method=None)
    mkt = ret.mean(axis=1)
    days = closes.index
    T, hold, lag = len(days), spec["hold_days"], spec["entry_lag"]
    s, n = np.zeros(T), np.zeros(T)
    per = []
    for r in ev.itertuples():
        code = NAME_TO_CODE.get(r.industry)
        if code not in ret.columns:
            continue
        a = int(days.searchsorted(r.day, side="right")) + lag - 1     # entry at this day's close
        b = a + hold
        if a >= T - 1:
            continue
        b = min(b, T - 1)
        x = ret[code].to_numpy()[a + 1:b + 1].copy()
        m = mkt.to_numpy()[a + 1:b + 1]
        x = np.nan_to_num(x)
        x[0] -= cost_per_side
        if b < T - 1:
            x[-1] -= cost_per_side
        s[a + 1:b + 1] += x
        n[a + 1:b + 1] += 1
        per.append({"ticker": r.industry, "entry": days[a].date().isoformat(), "exit": days[b].date().isoformat(),
                    "excess": float(np.prod(1 + x) - np.prod(1 + np.nan_to_num(m)))})
    k = np.maximum(n, spec["slots"])
    mv = mkt.fillna(0).to_numpy()
    book = pd.Series(np.where(n > 0, (s + (k - n) * mv) / k, mv), index=days)
    excess = book - mkt.fillna(0)
    from stockproof import backtest as bt
    live = pd.Series(0, index=days)
    nz = n.nonzero()[0]
    if len(nz):
        live.iloc[nz[0]:] = 1
    summ = {"n_trades": len(per), "long_excess": bt.stats(excess, live),
            "years": bt.by_year(excess, live).rename(columns={"return": "long_excess"})}
    if len(nz):
        summ["years"] = summ["years"][summ["years"].index >= days[nz[0]].year]
        summ["curve"] = pd.DataFrame({"long_excess": (1 + excess).cumprod()}).iloc[nz[0]:]
        summ["avg_positions"] = float(pd.Series(n, index=days)[live > 0].mean())
        net = pd.Series([p["excess"] for p in per])
        summ["long_trade"] = {"n": len(net), "mean": float(net.mean()), "win": float((net > 0).mean()),
                              "t": float(net.mean() / (net.std(ddof=1) / math.sqrt(len(net))))
                              if len(net) > 1 and net.std(ddof=1) > 0 else float("nan")}
    return {"summary": summ, "trades": per, "excess": excess, "n": pd.Series(n, index=days)}


def _factor_backtest(data_dir: str, spec: dict, start, end, cost_mult: float = 1.0) -> dict:
    from stockproof import screener
    from stockproof import cn
    prices = stock_prices(data_dir, "cn")
    if prices is None:
        raise SpecError("factor strategies need the A-share research prices: run `stockproof research --market cn` once")
    pan = _memo("panel", os.path.join(data_dir, "cn"), lambda: screener.panel(cn.CNCache(data_dir), "2015-01-01",
                                                                              log=lambda *a: None))
    px = prices
    if end is not None:
        px = px[px.index < end]
    s0 = (start or pd.Timestamp("2016-01-01")).date().isoformat()
    res = screener.backtest(pan, px, spec["top"], spec["factors"], start=s0, cost_per_side=0.0015 * cost_mult)
    if not res.get("n"):
        return {"summary": {"n_trades": 0}, "trades": [], "excess": pd.Series(dtype=float), "n": pd.Series(dtype=float)}
    per = [{"ticker": f"{p['picks']} stocks", "entry": p["date"], "exit": "", "excess": p["return"] - p["market"]}
           for p in res["periods"]]
    years = pd.DataFrame({"long_excess": res["years"]}).rename_axis(None)
    ann, t = res["ann_excess"], res["t"]
    summ = {"n_trades": res["n"], "long_excess": {"ann_return": ann, "t": t, "max_dd": res["max_dd"],
                                                  "days": None, "sharpe": None},
            "years": years, "long_trade": {"n": res["n"], "mean": float(np.mean([p["excess"] for p in per])),
                                           "win": res["hit_rate"], "t": float("nan")}}
    return {"summary": summ, "trades": per, "excess": None, "n": None, "periods": res["periods"]}


def run_spec(data_dir: str, spec: dict, phase: str = "explore", log=print, cost_mult: float = 1.0) -> dict:
    """Run a validated spec on the explore period (before the holdout) or the holdout.
    `cost_mult` scales every trading cost (2.0 = the stress test)."""
    spec = validate(spec)
    h0 = holdout_start()
    start, end = (None, h0) if phase == "explore" else (h0, None)
    t = spec["type"]
    universe = ""
    if t in ("earnings", "forecast", "smart_money"):
        market = spec["market"]
        prices = stock_prices(data_dir, market)
        if prices is None:
            raise SpecError(f"no price file for {market}: run `stockproof research --market {market}` once")
        if t == "earnings":
            ev = earnings_events(data_dir, market)
            if ev is None:
                raise SpecError(f"no earnings events for {market}: run `stockproof research --market {market}` once")
        elif t == "smart_money":
            from stockproof import flows
            ev = _memo("smart_money", flows.flows_dir(data_dir), lambda: flows.events(data_dir, log=log))
            if not len(ev):
                raise SpecError("no holder history: run `stockproof moneymap --history 2016` once (about 1.5 hours)")
        else:
            ev = _memo("forecast", os.path.join(data_dir, "cn"), lambda: forecast_events(data_dir, log=log))
            if not len(ev):
                raise SpecError("no 业绩预告 data could be loaded")
        ev = ev[ev["ticker"].isin(prices.columns)]
        sel = apply_filters(ev, spec["filters"])
        sel = sel[(sel["day0"] < end) if end is not None else (sel["day0"] >= start)]
        universe = (f"{prices.shape[1]} stocks in the research price file "
                    f"({'today’s CSI 300 members' if market == 'cn' else 'US large caps'})")
        res = _stock_backtest(sel, prices, market, spec, start, end, cost_mult)
        n_events = len(sel)
    elif t == "policy":
        from stockproof import policy
        from stockproof.store import Store
        px = policy.load_prices(data_dir)
        if px is None:
            raise SpecError("no Shenwan industry prices: run `stockproof policy` once")
        sig = policy.signals_frame(Store(data_dir), _policy_model(data_dir))
        if not len(sig):
            raise SpecError("no policy readings: run `stockproof policy` once")
        sel = _policy_filter(sig, spec["filters"])
        sel = sel[(sel["day"] < end) if end is not None else (sel["day"] >= start)]
        universe = "31 Shenwan level-1 industry indices (benchmark: their equal-weighted average)"
        res = _policy_backtest(sel, px, spec, start, end, cost_per_side=0.001 * cost_mult)
        n_events = len(sel)
    else:
        res = _factor_backtest(data_dir, spec, start, end, cost_mult)
        n_events = res["summary"].get("n_trades", 0)
        universe = "today’s CSI 300 members with prices; rebalanced early May / Sep / Nov after report deadlines"
    return {"spec": spec, "phase": phase, "holdout_start": h0.date().isoformat(), "universe": universe,
            "n_events": int(n_events), **res}


def _policy_model(data_dir: str) -> str:
    from stockproof.llm import PROVIDERS
    p = os.path.join(data_dir, "policy", "results.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("model") or f"deepseek:{PROVIDERS['deepseek']['model']}"
    except (OSError, ValueError):
        return f"deepseek:{PROVIDERS['deepseek']['model']}"


def _policy_filter(sig: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    """Policy events after the filters: one per (day, industry, stance), strongest wording; escalation is
    computed among the signals that pass the non-escalation filters (same kind of news)."""
    from stockproof import policy
    pre = [f for f in filters if f["field"] != "escalation"]
    esc = [f for f in filters if f["field"] == "escalation"]
    s = apply_filters(sig, [f for f in pre if f["field"] != "strength"])
    ev = policy.events(s)
    if not len(ev):
        return ev
    ev = apply_filters(ev, [f for f in pre if f["field"] == "strength"] + esc)
    return ev


# ---------------------------------------------------------------- multiple testing

def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's approximation; plenty for thresholds)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        return -_norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def t_needed(n_tries: int, alpha: float = 0.05) -> float:
    """Two-sided t (normal) a result needs after n_tries variants (Bonferroni)."""
    return _norm_ppf(1 - alpha / (2 * max(1, n_tries)))


def p_value(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2)) if t == t else float("nan")


# ---------------------------------------------------------------- the log

def _log_path(data_dir: str) -> str:
    return os.path.join(lab_dir(data_dir), "trials.jsonl")


def trials(data_dir: str) -> list[dict]:
    p = _log_path(data_dir)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def n_tries(data_dir: str, since: str | None = None) -> int:
    """Distinct strategies explored (since the last reset)."""
    return len({r["hash"] for r in trials(data_dir) if r.get("phase") == "explore" and (not since or r["time"] > since)})


def reset(data_dir: str) -> None:
    """Start a new research question: earlier tries no longer raise the bar (they stay in the log)."""
    with open(_log_path(data_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps({"reset": True, "time": dt.datetime.now().isoformat(timespec="microseconds")}) + "\n")


def _since_reset(data_dir: str) -> str | None:
    r = [x["time"] for x in trials(data_dir) if x.get("reset")]
    return r[-1] if r else None


def _append(data_dir: str, rec: dict) -> None:
    with open(_log_path(data_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------- the public entry points

# ---------------------------------------------------------------- robustness: 2x costs, walk-forward

def _le(res: dict) -> tuple[float | None, float | None]:
    le = res["summary"].get("long_excess") or {}
    t, ann = le.get("t"), le.get("ann_return")
    return (None if ann is None or ann != ann else float(ann)), (None if t is None or t != t else float(t))


def stress(base: dict, stressed: dict, lang: str = "zh") -> dict:
    """Compare a run with the same run at STRESS_MULT x costs."""
    zh = lang == "zh"
    a1, t1 = _le(base)
    a2, t2 = _le(stressed)
    m = f"{STRESS_MULT:g}"
    if a2 is None or t2 is None:
        return {"code": "n/a", "mult": STRESS_MULT, "ann": None, "t": None, "text": ""}
    if a1 is not None and a1 > 0 and a2 <= 0:
        code = "fragile"
        text = (f"脆弱：成本×{m}（佣金、滑点、印花税都翻倍）后每年超额变成 {100 * a2:+.1f}%（t={t2:.1f}）。"
                f"真实交易的滑点常比假设大，这点优势很可能被吃掉。" if zh else
                f"Fragile: with every cost x{m} (commission, slippage, stamp duty) the excess becomes "
                f"{100 * a2:+.1f}%/yr (t={t2:.1f}). Real slippage is often worse than assumed; this edge may not survive.")
    elif a2 > 0 and t2 >= 2:
        code = "robust"
        text = (f"成本×{m} 后仍有每年 {100 * a2:+.1f}% 超额（t={t2:.1f}），对交易成本不敏感。" if zh else
                f"Still {100 * a2:+.1f}%/yr (t={t2:.1f}) with every cost x{m}: not sensitive to trading costs.")
    else:
        code = "weak" if a1 is not None and a1 > 0 else "no_edge"
        text = (f"成本×{m} 后每年超额 {100 * a2:+.1f}%（t={t2:.1f}）。" if zh else
                f"With every cost x{m}: {100 * a2:+.1f}%/yr (t={t2:.1f}).")
    return {"code": code, "mult": STRESS_MULT, "ann": a2, "t": t2, "text": text}


def yearly_excess(res: dict) -> dict[int, float]:
    years = res["summary"].get("years")
    if not isinstance(years, pd.DataFrame) or not len(years):
        return {}
    return {int(i): float(r.iloc[0]) for i, r in years.iterrows() if not pd.isna(r.iloc[0])}


def _variants(data_dir: str, spec: dict) -> list[dict]:
    """This spec plus the other variants explored for the same question (same type and market), newest first."""
    since = _since_reset(data_dir)
    seen, out = {spec_hash(spec)}, [spec]
    for r in reversed(trials(data_dir)):
        sp = r.get("spec") or {}
        if r.get("phase") != "explore" or (since and r.get("time", "") <= since) or r.get("hash") in seen:
            continue
        if sp.get("type") != spec["type"] or sp.get("market") != spec.get("market"):
            continue
        seen.add(r["hash"])
        out.append(sp)
        if len(out) >= WF_MAX_VARIANTS:
            break
    return out


def walk_forward(data_dir: str, spec: dict, lang: str = "zh", base: dict | None = None) -> dict:
    """Each year Y, pick the variant with the best average excess over the years before Y (at least
    WF_WARMUP of them), and record what that pick earned in Y. Only the explore period is used."""
    zh = lang == "zh"
    h_main = spec_hash(spec)
    table = {}
    for sp in _variants(data_dir, spec):
        h = spec_hash(sp)
        key = ("wf", data_dir, h, dt.date.today().isoformat())
        if key not in _CACHE:
            try:
                r = base if base is not None and h == h_main else run_spec(data_dir, sp, "explore", log=lambda *a: None)
                _CACHE[key] = yearly_excess(r)
            except SpecError:
                _CACHE[key] = {}
        table[h] = (sp, _CACHE[key])
    years = sorted({y for _, ys in table.values() for y in ys})
    rows = []
    for Y in years:
        best, score = None, None
        for h, (sp, ys) in table.items():
            past = [ys[y] for y in years if y < Y and y in ys]
            if len(past) < WF_WARMUP or Y not in ys:
                continue
            sc = float(np.mean(past))
            if score is None or sc > score:
                best, score = h, sc
        if best is not None:
            rows.append({"year": Y, "pick": describe_spec(table[best][0], lang), "pick_is_this": best == h_main,
                         "past_mean": score, "excess": table[best][1][Y]})
    k = len(table)
    out = {"variants": k, "years": rows, "warmup": WF_WARMUP}
    if len(rows) < 2:
        out.update(code="too_short", mean=None, positive=None, in_sample_best=None,
                   text=(f"历史太短，做不了滚动向前验证（需要至少 {WF_WARMUP + 2} 年有交易）。" if zh else
                         f"Too little history for a walk-forward test (needs {WF_WARMUP + 2}+ years with trades)."))
        return out
    test_years = [r["year"] for r in rows]
    oos = float(np.mean([r["excess"] for r in rows]))
    pos = sum(r["excess"] > 0 for r in rows)
    # the variant that looks best with hindsight, over the same years
    ins = max(float(np.mean([ys.get(y, 0.0) for y in test_years])) for _, ys in table.values() if ys)
    how = (f"每年年初只用之前的数据，从你为这个问题试过的 {k} 个版本里挑出当时最好的，再看它下一年的表现"
           if k > 1 else "目前只试了 1 个版本，所以就是从第 3 年起逐年检验它本身") if zh else \
          (f"each year, using only earlier years, the best of the {k} variants you tried was picked and its next year recorded"
           if k > 1 else "only 1 variant tried, so this is the rule itself year by year after a warm-up")
    code = "holds" if oos > 0 and pos * 2 >= len(rows) else "fades"
    if zh:
        text = (f"滚动向前验证（{how}）：{len(rows)} 个样本外年份平均每年 {100 * oos:+.1f}%，{pos}/{len(rows)} 年为正")
        text += (f"；事后看最好的版本同期平均 {100 * ins:+.1f}%。" if k > 1 else "。")
        if code == "fades":
            text += ("优势没能延续到下一年，样本内的好结果很可能是挑出来的。" if ins > 0 else
                     "试过的版本里没有一个能持续跑赢市场。")
    else:
        text = (f"Walk-forward ({how}): {len(rows)} out-of-sample years average {100 * oos:+.1f}%/yr, "
                f"{pos}/{len(rows)} positive")
        text += (f"; the hindsight-best variant averaged {100 * ins:+.1f}% over the same years." if k > 1 else ".")
        if code == "fades":
            text += (" The edge did not carry into the next year; the in-sample result was likely picked, not real."
                     if ins > 0 else " None of the variants tried beat the market consistently.")
    out.update(code=code, mean=oos, positive=pos, in_sample_best=ins, gap=ins - oos, text=text)
    return out


def _warn(v: dict, st: dict | None, wf: dict | None, lang: str) -> dict:
    """Attach robustness warnings to a passing verdict."""
    v["warnings"] = []
    if v["code"] not in ("passes", "confirmed"):
        return v
    if st and st.get("code") == "fragile":
        v["warnings"].append(st["text"])
    if wf and wf.get("code") == "fades":
        v["warnings"].append(wf["text"])
    if v["warnings"]:
        v["text"] += (" 但要注意：" if lang == "zh" else " But: ") + " ".join(v["warnings"])
    return v


def verdict(res: dict, tries: int, lang: str = "zh") -> dict:
    zh = lang == "zh"
    le = res["summary"].get("long_excess") or {}
    t, ann = le.get("t"), le.get("ann_return")
    n = res["summary"].get("n_trades", 0)
    need = t_needed(tries)
    if not n or t is None or t != t:
        code = "no_trades"
        text = "这个条件在历史上没有产生交易，换个条件试试。" if zh else "No trades in history; loosen the conditions."
    elif res["phase"] == "confirm":
        ex = res.get("explore_t")
        same = ex is not None and t * ex > 0
        if same and t >= 1.65 and ann > 0:
            code, text = "confirmed", (f"样本外（{res['holdout_start']} 之后、研究时从未看过的数据）同样成立："
                                       f"每年超额 {100 * ann:+.1f}%，t={t:.1f}。" if zh else
                                       f"Holds out of sample (data never seen while exploring): {100 * ann:+.1f}%/yr, t={t:.1f}.")
        else:
            code, text = "failed", (f"样本外失效：锁定的近 {HOLDOUT_YEARS} 年数据里每年超额 {100 * ann:+.1f}%，t={t:.1f}。"
                                    f"样本内的好结果很可能是拟合了过去。" if zh else
                                    f"Fails out of sample: {100 * ann:+.1f}%/yr, t={t:.1f} in the locked last {HOLDOUT_YEARS} "
                                    f"years. The in-sample result was likely fitted to the past.")
    elif t <= -2:
        code = "negative"
        text = (f"不但没有超额，反而稳定跑输：扣费后每年 {100 * ann:+.1f}%，t={t:.1f}。在这段历史里，"
                f"按这个条件买入是亏钱的。" if zh else
                f"Worse than no edge: {100 * ann:+.1f}%/yr after costs, t={t:.1f}. Over this history, buying on "
                f"this condition lost money relative to the market.")
    elif t < 2 or ann <= 0:
        code = "no_edge"
        text = (f"没有可靠证据：扣费后每年超额 {100 * ann:+.1f}%，t={t:.1f}（一般需要 t>2）。" if zh else
                f"No reliable edge: {100 * ann:+.1f}%/yr after costs, t={t:.1f} (needs t > 2).")
    elif t < need:
        code = "luck_risk"
        text = (f"看起来不错（t={t:.1f}），但这个问题已经试了 {tries} 个版本，按次数修正后需要 t>{need:.1f}。"
                f"很可能是多次尝试碰出来的运气。" if zh else
                f"Looks good (t={t:.1f}), but {tries} variants were tried; after correcting for that it needs "
                f"t > {need:.1f}. Likely luck from trying many versions.")
    else:
        code = "passes"
        text = (f"通过样本内检验（t={t:.1f}，试了 {tries} 个版本，门槛 {need:.1f}）。下一步：用 confirm 在锁定的近 "
                f"{HOLDOUT_YEARS} 年数据上检验一次——只有一次机会。" if zh else
                f"Passes in sample (t={t:.1f}; {tries} variants tried, bar {need:.1f}). Next: confirm it once on the "
                f"locked last {HOLDOUT_YEARS} years — one shot.")
    return {"code": code, "text": text, "t": t, "t_needed": need, "tries": tries,
            "p_adjusted": None if t is None or t != t else min(1.0, p_value(t) * max(1, tries))}


def explore(data_dir: str, spec: dict, lang: str = "zh", log=print) -> dict:
    """Run on the explore period, log the try, write the report. Returns a JSON-safe summary."""
    spec = validate(spec)
    h = spec_hash(spec)
    res = run_spec(data_dir, spec, "explore", log=log)
    st = stress(res, run_spec(data_dir, spec, "explore", log=lambda *a: None, cost_mult=STRESS_MULT), lang)
    wf = walk_forward(data_dir, spec, lang, base=res)
    since = _since_reset(data_dir)
    known = {r["hash"] for r in trials(data_dir) if r.get("phase") == "explore" and (not since or r["time"] > since)}
    tries = len(known | {h})
    v = _warn(verdict(res, tries, lang), st, wf, lang)
    exp_id = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{h[:6]}"
    out = _package(data_dir, exp_id, h, res, v, lang, {"stress": st, "walk_forward": wf})
    _append(data_dir, {"id": exp_id, "hash": h, "phase": "explore", "time": dt.datetime.now().isoformat(timespec="microseconds"),
                       "spec": spec, "t": v["t"], "ann": (res["summary"].get("long_excess") or {}).get("ann_return"),
                       "n": res["summary"].get("n_trades", 0), "verdict": v["code"],
                       "stress": st["code"], "walk_forward": wf["code"]})
    return out


def confirm(data_dir: str, exp_id: str, lang: str = "zh", log=print) -> dict:
    """Run an explored strategy once on the locked holdout."""
    rec = next((r for r in trials(data_dir) if r.get("id") == exp_id and r.get("phase") == "explore"), None)
    if rec is None:
        raise SpecError(f"no explored experiment '{exp_id}'; run explore first and use the id it returns")
    done = [r for r in trials(data_dir) if r.get("phase") == "confirm" and r.get("hash") == rec["hash"]]
    if done:
        raise SpecError(f"this strategy was already confirmed ({done[0]['id']}): the holdout can be used only once. "
                        f"Result then: {done[0].get('verdict')}")
    res = run_spec(data_dir, rec["spec"], "confirm", log=log)
    res["explore_t"] = rec.get("t")
    st = stress(res, run_spec(data_dir, rec["spec"], "confirm", log=lambda *a: None, cost_mult=STRESS_MULT), lang)
    v = _warn(verdict(res, 1, lang), st, None, lang)
    cid = f"{exp_id}-holdout"
    out = _package(data_dir, cid, rec["hash"], res, v, lang, {"stress": st})
    _append(data_dir, {"id": cid, "hash": rec["hash"], "phase": "confirm", "of": exp_id,
                       "time": dt.datetime.now().isoformat(timespec="microseconds"), "spec": rec["spec"], "t": v["t"],
                       "ann": (res["summary"].get("long_excess") or {}).get("ann_return"),
                       "n": res["summary"].get("n_trades", 0), "verdict": v["code"]})
    return out


def _package(data_dir: str, exp_id: str, h: str, res: dict, v: dict, lang: str, extra: dict | None = None) -> dict:
    from stockproof import lab_report
    s = res["summary"]
    le = s.get("long_excess") or {}
    years = s.get("years")
    ylist = [{"year": int(i), "excess": None if pd.isna(r.iloc[0]) else round(float(r.iloc[0]), 4)}
             for i, r in years.iterrows()] if isinstance(years, pd.DataFrame) else []
    trades = sorted(res.get("trades") or [], key=lambda x: x["excess"])
    uni = res["universe"]
    if lang == "zh":
        uni = (uni.replace("stocks in the research price file", "只股票（研究用价格文件）")
               .replace("today’s CSI 300 members with prices; rebalanced early May / Sep / Nov after report deadlines",
                        "今天的沪深300成分股；每年5、9、11月初财报截止后调仓")
               .replace("today’s CSI 300 members", "今天的沪深300成分股").replace("US large caps", "美股大盘股")
               .replace("31 Shenwan level-1 industry indices (benchmark: their equal-weighted average)",
                        "31 个申万一级行业指数（基准：它们的等权平均）"))
    out = {"id": exp_id, "hash": h, "phase": res["phase"], "spec": res["spec"],
           "description": describe_spec(res["spec"], lang), "universe": uni,
           "period": ("before " if res["phase"] == "explore" else "from ") + res["holdout_start"],
           "holdout_start": res["holdout_start"], "events": res["n_events"],
           "trades": s.get("n_trades", 0), "avg_positions": s.get("avg_positions"),
           "ann_excess": le.get("ann_return"), "t": le.get("t"), "sharpe": le.get("sharpe"), "max_dd": le.get("max_dd"),
           "per_trade": s.get("long_trade"), "years": ylist,
           "worst_trades": trades[:5], "best_trades": trades[-5:][::-1], "verdict": v, **(extra or {})}
    html = lab_report.build(out, res, lang)
    path = os.path.join(lab_dir(data_dir), "reports", f"{exp_id}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    out["report"] = path
    return json.loads(json.dumps(out, default=_safe))


def _safe(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return str(v)


def capabilities(data_dir: str) -> dict:
    """What the lab can test with the data on this computer."""
    out = {"holdout_start": holdout_start().date().isoformat(), "holdout_years": HOLDOUT_YEARS,
           "tries_since_reset": n_tries(data_dir, _since_reset(data_dir)), "types": {}, "ops": list(OPS)}
    for m in ("cn", "us"):
        ev = earnings_events(data_dir, m)
        px = stock_prices(data_dir, m)
        if ev is not None and px is not None:
            out["types"].setdefault("earnings", {"fields": FIELDS["earnings"], "markets": {}})
            out["types"]["earnings"]["markets"][m] = {
                "events": int(len(ev)), "stocks": int(px.shape[1]), "from": str(ev["day0"].min().date()),
                "to": str(ev["day0"].max().date()), "with_tone": int(ev["tone"].notna().sum()) if "tone" in ev else 0}
    if stock_prices(data_dir, "cn") is not None:
        out["types"]["forecast"] = {"fields": FIELDS["forecast"], "note": "业绩预告 tables download on first use (~1 min)"}
        if fundamentals(data_dir) is not None:
            out["types"]["factor"] = {"factors": list(FACTORS), "note": "top-N rebalanced after each report deadline"}
    from stockproof import flows
    nq = len([f for f in os.listdir(flows.flows_dir(data_dir)) if f.startswith("holders_")])
    if nq >= 8 and stock_prices(data_dir, "cn") is not None:
        out["types"]["smart_money"] = {"fields": FIELDS["smart_money"], "quarters": nq,
                                       "note": "events dated by each company's announcement; CSI 300 members only"}
    from stockproof import policy
    if policy.load_prices(data_dir) is not None:
        out["types"]["policy"] = {"fields": FIELDS["policy"]}
    out["labels_zh"] = FIELD_ZH
    out["example"] = {"type": "earnings", "market": "cn", "filters": [{"field": "sue", "op": ">=", "value": 2},
                                                                     {"field": "reaction", "op": ">", "value": 0}],
                      "hold_days": 20, "entry_lag": 1}
    out["rules"] = ["Explore runs use only data before holdout_start; confirm(id) runs once on the rest.",
                    "Every explored variant counts: more tries raise the t-statistic needed.",
                    "Costs: A-shares commission 0.025%/side, slippage 0.1%/side, stamp duty on sales; price limits.",
                    "Returns are in excess of the equal-weighted universe."]
    return out


# ---------------------------------------------------------------- "what happened in situations like this?"

def similar(data_dir: str, ticker: str, sue: float | None = None, tone: float | None = None,
            reaction: float | None = None, market: str | None = None, lang: str = "zh") -> dict:
    """Base rates: past reports that looked like this stock's latest one, and what followed (days 2–61).
    Matches on SUE (±0.75), and on the day-0–1 reaction (±3 pp) and the LLM tone (same third) when known."""
    from stockproof import cn
    tk = cn.canonical(ticker)
    market = market or ("cn" if cn.is_cn(tk) else "us")
    if market == "cn" and tk.endswith(".HK"):
        return {"error": "Hong Kong stocks have no event history in the lab yet"}
    ev = earnings_events(data_dir, market)
    if ev is None:
        return {"error": f"no event history for {market}: run `stockproof research --market {market}` once"}
    own = ev[ev["ticker"] == tk].sort_values("day0")
    latest = own.iloc[-1].to_dict() if len(own) else {}
    sue = sue if sue is not None else latest.get("sue")
    reaction = reaction if reaction is not None else latest.get("reaction")
    tone = tone if tone is not None else latest.get("tone")
    if sue is None or sue != sue:
        return {"error": "no earnings surprise known for this stock; pass sue=… to ask about a hypothetical"}
    m = ev.dropna(subset=["drift", "sue"])
    m = m[(m["sue"] - sue).abs() <= 0.75]
    used = [f"SUE {sue:+.1f} ± 0.75"]
    if reaction is not None and reaction == reaction:
        m2 = m[(m["reaction"] - reaction).abs() <= 0.03]
        if len(m2) >= 30:
            m, used = m2, used + [f"reaction {100 * reaction:+.1f}% ± 3pp"]
    if tone is not None and tone == tone and "tone" in m:
        b = lambda x: 0 if x < -0.15 else (2 if x > 0.15 else 1)
        m3 = m[m["tone"].notna() & (m["tone"].map(b) == b(tone))]
        if len(m3) >= 30:
            m, used = m3, used + ["same LLM tone group"]
    m = m[m["ticker"] != tk] if len(m[m["ticker"] != tk]) >= 30 else m
    if len(m) < 10:
        return {"error": f"only {len(m)} similar reports in history — too few to say anything", "conditions": used}
    d = m["drift"]
    q = d.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d))) if d.std(ddof=1) > 0 else float("nan")
    years = m.groupby(m["day0"].dt.year)["drift"].mean()
    examples = m.assign(dist=(m["sue"] - sue).abs()).sort_values(["dist", "day0"], ascending=[True, False]).head(8)
    zh = lang == "zh"
    summary = ((f"历史上 {len(m)} 份类似的财报（{'；'.join(used)}），之后第 2–61 个交易日相对市场平均 {100 * d.mean():+.1f}%"
                f"（t={t:.1f}），{100 * (d > 0).mean():.0f}% 跑赢市场；中位数 {100 * q[0.5]:+.1f}%，"
                f"10%–90% 区间 {100 * q[0.1]:+.0f}% 到 {100 * q[0.9]:+.0f}%。这是很多公司的平均，不是对这只股票的预测。")
               if zh else
               (f"{len(m)} similar past reports ({'; '.join(used)}): days 2–61 averaged {100 * d.mean():+.1f}% vs the "
                f"market (t={t:.1f}); {100 * (d > 0).mean():.0f}% beat it; median {100 * q[0.5]:+.1f}%, 10–90% range "
                f"{100 * q[0.1]:+.0f}% to {100 * q[0.9]:+.0f}%. An average over many companies, not a forecast."))
    return {"ticker": tk, "market": market, "latest": {"sue": sue, "reaction": reaction, "tone": tone,
                                                         "date": str(latest.get("day0", ""))[:10] or None},
            "conditions": used, "n": int(len(m)), "mean": float(d.mean()), "t": float(t),
            "beat_rate": float((d > 0).mean()), "quantiles": {str(k): float(v) for k, v in q.items()},
            "by_year": {int(k): round(float(v), 4) for k, v in years.items()},
            "examples": [{"ticker": r.ticker, "date": str(r.day0)[:10], "sue": round(float(r.sue), 2),
                          "reaction": round(float(r.reaction), 4), "after": round(float(r.drift), 4)}
                         for r in examples.itertuples()],
            "summary": summary}


# ---------------------------------------------------------------- custom whole-market screen

SCREEN_FIELDS = {"sue": "earnings surprise", "rev_yoy": "revenue growth %", "np_yoy": "profit growth %",
                 "roe": "annualized ROE %", "gm": "gross margin %", "pe": "P/E (dynamic)", "pb": "P/B",
                 "cap": "market value, 亿元", "mom60": "60-day return (fraction; may be missing)",
                 "ytd": "return this year (fraction; may be missing)", "industry": "Eastmoney industry", "name": "name"}


def custom_screen(data_dir: str, filters: list[dict], sort_by: str = "rev_yoy", descending: bool = True,
                  top: int = 30, log=print) -> dict:
    """Any combination of conditions over all A-shares (latest reports + today's snapshot)."""
    from stockproof import cn, screener
    for f in filters:
        if f.get("field") not in SCREEN_FIELDS or f.get("op") not in OPS:
            raise SpecError(f"filters use fields {', '.join(SCREEN_FIELDS)} and ops {', '.join(OPS)}")
    if sort_by not in SCREEN_FIELDS:
        raise SpecError(f"sort_by must be one of {', '.join(SCREEN_FIELDS)}")
    cache = cn.CNCache(data_dir)
    pan = _memo("panel_recent", os.path.join(data_dir, "cn"),
                lambda: screener.panel(cache, f"{clock.today().year - 4}-01-01", log=lambda *a: None))
    snap = screener.snapshot(cache, log=log)
    full = screener.screen(pan, snap, top=None, min_cap=0)
    full = full.drop(columns=["roe"], errors="ignore").rename(columns={"roe_ann": "roe"})
    full = full[~full["name"].str.contains(r"ST|退", regex=True)]
    sel = apply_filters(full, filters)
    sel = sel.sort_values(sort_by, ascending=not descending, na_position="last").head(max(1, min(top, 100)))
    keep = ["ticker", "name", "industry", "cap", "pe", "pb", "rev_yoy", "np_yoy", "roe", "gm", "sue", "mom60", "rank"]
    rows = [{k: (None if pd.isna(r.get(k)) else (round(float(r[k]), 3) if isinstance(r.get(k), (float, np.floating)) else r[k]))
             for k in keep if k in sel.columns} for _, r in sel.iterrows()]
    return {"as_of": clock.today().isoformat(), "universe": int(len(full)), "matched": int(len(apply_filters(full, filters))),
            "filters": filters, "sort_by": sort_by, "results": rows,
            "note": "Latest public reports and today's prices; a list to research, not advice."}


# ---------------------------------------------------------------- policy history

def policy_history(data_dir: str, industry: str | None = None, keyword: str | None = None,
                   stance: str | None = None, kind: str | None = "new_measure", min_strength: int = 1,
                   since: str | None = None, limit: int = 20) -> dict:
    """Past 新闻联播 signals (by industry and/or a word in the quote/title) and the industry's excess return after."""
    from stockproof import policy
    from stockproof.store import Store
    sig = policy.signals_frame(Store(data_dir), _policy_model(data_dir))
    if not len(sig):
        return {"error": "no policy readings: run `stockproof policy` once"}
    if industry:
        if industry not in policy.NAME_TO_CODE:
            return {"error": f"industry must be a Shenwan level-1 name: {'、'.join(policy.NAME_TO_CODE)}"}
        sig = sig[sig["industry"] == industry]
    if keyword:
        sig = sig[sig["quote"].astype(str).str.contains(keyword, regex=False) |
                  sig["title"].astype(str).str.contains(keyword, regex=False)]
    if stance:
        sig = sig[sig["stance"] == stance]
    if kind:
        sig = sig[sig["kind"] == kind]
    sig = sig[sig["strength"] >= min_strength]
    if since:
        sig = sig[sig["day"] >= pd.Timestamp(since)]
    if not len(sig):
        return {"n": 0, "events": []}
    px = policy.load_prices(data_dir)
    ev = policy.events(sig)
    if px is not None:
        ev = policy.attach_returns(ev, px)
    stats = {}
    for c in ("pre20", "gap", "react", "d2_20", "d21_60"):
        if c in ev:
            x = ev[c].dropna()
            stats[c] = {"n": int(len(x)), "mean": float(x.mean()) if len(x) else None,
                        "beat": float((x > 0).mean()) if len(x) else None}
    recent = ev.sort_values("day", ascending=False).head(limit)
    rows = [{"date": str(r["day"])[:10], "industry": r["industry"], "stance": r["stance"], "strength": int(r["strength"]),
             "quote": r["quote"], "title": r["title"],
             **{c: (None if pd.isna(r.get(c)) else round(float(r[c]), 4)) for c in ("d2_20", "d21_60") if c in ev}}
            for _, r in recent.iterrows()]
    return {"n": int(len(ev)), "stats": stats, "events": rows,
            "note": "returns: industry minus the average of 31 Shenwan industries; d2_20 = trading days 2–20 after"}


def list_experiments(data_dir: str, limit: int = 30) -> list[dict]:
    out = []
    for r in reversed(trials(data_dir)):
        if r.get("reset") or "id" not in r:
            continue
        out.append({k: r.get(k) for k in ("id", "phase", "time", "t", "ann", "n", "verdict")} |
                   {"description": describe_spec(r["spec"], "zh"), "name": r["spec"].get("name")})
        if len(out) >= limit:
            break
    return out
