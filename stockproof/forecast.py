"""
Medium- and long-horizon forecasts: each stock's return over the next 3, 6 or 12 months against the average
stock, not tomorrow's direction.

Why this shape:
  * a daily forecast that is "right" by 0.1% loses money after costs; over a quarter or a year one round trip
    (about 0.35% in A-shares) is small next to the move being forecast;
  * a forecast is only worth showing next to its own track record, so every number on screen comes with what
    the same model did in the past, out of sample.

Method:
  * at every month end, features known on that day (point-in-time): price trend over 12 months excluding the last,
    last month's move (A-shares often reverse), 3-month volatility, earnings growth, revenue growth, ROE, gross
    margin and earnings yield from the latest report already published (dated by its announcement);
  * features become cross-sectional ranks (0..1), so the model compares stocks with each other on the same day;
  * a ridge regression on those ranks, refit every month on past months only, with an embargo so no training
    target overlaps the day being forecast (walk-forward);
  * tested on non-overlapping periods: buy the top tenth, hold for the horizon, against the average stock, after
    costs. The locked holdout (the lab's last two years) is reported separately.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re

import numpy as np
import pandas as pd

HORIZONS = {"3m": 63, "6m": 126, "12m": 252}
FEATURES = ["mom_12_1", "rev_1m", "vol_3m", "np_yoy", "rev_yoy", "roe", "gm", "ep"]
FEATURE_ZH = {"mom_12_1": "过去 12 个月走势（去掉最近 1 个月）", "rev_1m": "最近 1 个月涨跌", "vol_3m": "近 3 个月波动",
              "np_yoy": "净利润同比增长", "rev_yoy": "营收同比增长", "roe": "ROE", "gm": "毛利率", "ep": "盈利收益率（市盈率的倒数）"}
COST = 0.0035                     # one A-share round trip: commission + slippage both ways + stamp duty
MIN_TRAIN_MONTHS = 24
TOP = 0.1


def _dir(data_dir: str) -> str:
    d = os.path.join(data_dir, "research")
    os.makedirs(d, exist_ok=True)
    return d


def _path(data_dir: str) -> str:
    return os.path.join(_dir(data_dir), "forecast_cn.json")


def load(data_dir: str) -> dict | None:
    p = _path(data_dir)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- data
def prices(data_dir: str) -> tuple[pd.DataFrame, str]:
    """Whole-market adjusted closes if downloaded (`stockproof forecast --download`), else the research universe."""
    p = os.path.join(_dir(data_dir), "cn_all_prices.csv.gz")
    if os.path.exists(p):
        df = pd.read_csv(p, index_col=0, parse_dates=True).sort_index()
        return df[~df.index.duplicated()], "all"
    from stockproof import lab
    px = lab.stock_prices(data_dir, "cn")
    if px is None:
        raise RuntimeError("no A-share prices: run `stockproof research --market cn` or `stockproof forecast --download`")
    return px, "csi300"


def fundamentals(data_dir: str) -> pd.DataFrame:
    """Every (stock, report period) from the screen's cached 业绩报表 tables, with the day it became public and
    trailing-twelve-month EPS. A missing announcement date falls back to the legal deadline."""
    d = os.path.join(data_dir, "cn")
    rows = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = re.fullmatch(r"research_yjbb2_(\d{8})\.json", f)
        if not m:
            continue
        end = pd.Timestamp(m.group(1))
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            for r in json.load(fh):
                rows.append({"code": str(r["code"]).zfill(6), "end": end, "eps": r.get("eps"), "rev_yoy": r.get("rev_yoy"),
                             "np_yoy": r.get("np_yoy"), "roe": r.get("roe"), "gm": r.get("gm"), "date": r.get("date")})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for c in ("eps", "rev_yoy", "np_yoy", "roe", "gm"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    q = df["end"].dt.quarter
    deadline = pd.to_datetime([f"{e.year + 1}-04-30" if qq == 4 else f"{e.year}-{ {1: '04-30', 2: '08-31', 3: '10-31'}[qq]}"
                               for e, qq in zip(df["end"], q)])
    pub = pd.to_datetime(df["date"], errors="coerce")
    df["public"] = pub.where(pub.notna() & (pub > df["end"]), deadline)
    df["roe"] = df["roe"] * 4 / q                                # year-to-date ROE, annualized
    # TTM EPS = this year-to-date + last full year - last year's same year-to-date
    key = df.set_index(["code", "end"])["eps"]
    def ttm(code, end, eps, qq):
        if qq == 4:
            return eps
        last_year = pd.Timestamp(end.year - 1, 12, 31)
        same = pd.Timestamp(end.year - 1, end.month, end.day)
        a, b = key.get((code, last_year)), key.get((code, same))
        return eps + a - b if a is not None and b is not None and pd.notna(a) and pd.notna(b) else np.nan
    df["eps_ttm"] = [ttm(c, e, x, qq) for c, e, x, qq in zip(df["code"], df["end"], df["eps"], q)]
    return df.sort_values(["code", "public"])


def _rank(df: pd.DataFrame) -> pd.DataFrame:
    return df.rank(axis=1, pct=True)


def panel(data_dir: str, log=print) -> tuple[dict, pd.DataFrame, str]:
    """Month-end feature ranks (dict of DataFrames: date x stock) and the price panel."""
    px, universe = prices(data_dir)
    px = px.loc[:, px.notna().sum() > 260]
    ret = px.pct_change(fill_method=None)
    me = px.resample("ME").last().index
    me = [px.index[px.index <= d][-1] for d in me if (px.index <= d).any()]
    me = pd.DatetimeIndex(sorted(set(me)))
    pos = {d: i for i, d in enumerate(px.index)}
    feats: dict[str, dict] = {f: {} for f in FEATURES}
    fund = fundamentals(data_dir)
    codes = {c: c[:6] for c in px.columns}
    latest_fund = None
    if len(fund):
        fund = fund[fund["code"].isin(set(codes.values()))]
    for d in me:
        i = pos[d]
        if i < 252:
            continue
        p0 = px.iloc[i]
        feats["mom_12_1"][d] = px.iloc[i - 21] / px.iloc[i - 252] - 1
        feats["rev_1m"][d] = p0 / px.iloc[i - 21] - 1
        feats["vol_3m"][d] = -ret.iloc[i - 63:i + 1].std()          # higher rank = calmer
        if len(fund):
            known = fund[fund["public"] <= d]
            last = known.groupby("code").tail(1).set_index("code")
            m = pd.Series(codes).map(lambda c: c)
            for f in ("np_yoy", "rev_yoy", "roe", "gm"):
                feats[f][d] = pd.Series(m.map(last[f]).to_numpy(), index=px.columns)
            eps = pd.Series(m.map(last["eps_ttm"]).to_numpy(), index=px.columns)
            feats["ep"][d] = eps / p0
            latest_fund = d
    F = {f: _rank(pd.DataFrame(v).T) if v else pd.DataFrame() for f, v in feats.items()}
    F = {f: v for f, v in F.items() if len(v)}
    log(f"  forecast panel: {len(me)} month ends, {px.shape[1]} stocks, features {', '.join(F)}"
        + ("" if latest_fund else " (no fundamentals cached: run `stockproof screen` once)"))
    return F, px, universe


# ---------------------------------------------------------------- model
def _fit(X: np.ndarray, y: np.ndarray, l2: float = 10.0) -> np.ndarray:
    A = X.T @ X + l2 * np.eye(X.shape[1])
    A[0, 0] -= l2
    return np.linalg.solve(A, X.T @ y)


def walk_forward(F: dict, px: pd.DataFrame, horizon: int, holdout: pd.Timestamp | None = None,
                 keep_preds: bool = False) -> dict:
    feats = list(F)
    dates = F[feats[0]].index
    cols = px.columns
    pos = {d: i for i, d in enumerate(px.index)}
    ew = px.pct_change(fill_method=None).mean(axis=1).fillna(0)
    cum = (1 + ew).cumprod()

    def target(d):
        i = pos[d]
        if i + horizon >= len(px):
            return None
        r = px.iloc[i + horizon] / px.iloc[i] - 1
        return r - (cum.iloc[i + horizon] / cum.iloc[i] - 1)

    rows = {}
    for d in dates:
        X = np.stack([F[f].reindex(columns=cols).loc[d].to_numpy(float) for f in feats], axis=1)
        rows[d] = X
    Y = {d: target(d) for d in dates}
    preds, deciles = {}, []
    k_ = len(feats) + 1
    gram = {}                                                   # per month: X'X and X'y on demeaned targets
    for t in dates:
        if Y[t] is None:
            continue
        X, y = rows[t], Y[t].to_numpy(float)
        ok = ~np.isnan(X).any(1) & ~np.isnan(y)
        if ok.sum() <= 20:
            continue
        Xo = np.c_[np.ones(ok.sum()), X[ok] - 0.5]
        yo = y[ok] - y[ok].mean()
        gram[t] = (Xo.T @ Xo, Xo.T @ yo)
    for k, d in enumerate(dates):
        train = [t for t in dates[:k] if t in gram and pos[t] + horizon < pos[d]]          # embargo
        if len(train) < MIN_TRAIN_MONTHS:
            continue
        A = sum(gram[t][0] for t in train) + 10.0 * np.diag([0] + [1] * (k_ - 1))
        b = sum(gram[t][1] for t in train)
        w = np.linalg.solve(A, b)
        X = rows[d]
        ok = ~np.isnan(X).any(1)
        s = pd.Series(np.nan, index=cols)
        s[ok] = np.c_[np.ones(ok.sum()), X[ok] - 0.5] @ w
        preds[d] = (s, w)
    out = {"horizon": horizon, "features": feats, "months": len(preds)}
    if keep_preds:
        out["_preds"] = {d: s_ for d, (s_, _) in preds.items()}
    if not preds:
        return out
    # evaluation on non-overlapping periods (every `horizon` trading days)
    pdates = sorted(preds)
    step = max(1, round(horizon / 21))
    picks, last_hold = [], set()
    for d in pdates[::step]:
        y = Y[d]
        if y is None:
            continue
        s = preds[d][0].dropna()
        both = pd.concat([s, y], axis=1).dropna()
        if len(both) < 30:
            continue
        ic = both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())
        n = max(5, int(len(both) * TOP))
        top = both.iloc[:, 0].nlargest(n).index
        hold = set(top)
        turnover = 1.0 if not last_hold else len(hold - last_hold) / len(hold)
        last_hold = hold
        gross = float(both.loc[top].iloc[:, 1].mean())
        dec = pd.qcut(both.iloc[:, 0].rank(method="first"), 10, labels=False)
        deciles.append(both.iloc[:, 1].groupby(dec).mean().to_numpy())
        picks.append({"date": d.date().isoformat(), "ic": float(ic), "top_excess": gross,
                      "net": gross - COST * turnover, "turnover": turnover, "n": int(len(both)),
                      "holdout": bool(holdout is not None and d >= holdout - pd.Timedelta(days=int(horizon * 1.45)))})
    df = pd.DataFrame(picks)

    def stats(sub):
        if len(sub) < 3:
            return {"periods": int(len(sub))}
        per_year = 252 / horizon
        t = float(sub["net"].mean() / sub["net"].std(ddof=1) * math.sqrt(len(sub))) if sub["net"].std(ddof=1) > 0 else None
        ti = float(sub["ic"].mean() / sub["ic"].std(ddof=1) * math.sqrt(len(sub))) if sub["ic"].std(ddof=1) > 0 else None
        return {"periods": int(len(sub)), "from": sub["date"].iloc[0], "to": sub["date"].iloc[-1],
                "ic": float(sub["ic"].mean()), "ic_t": ti, "ic_positive": float((sub["ic"] > 0).mean()),
                "top_excess": float(sub["top_excess"].mean()), "net": float(sub["net"].mean()),
                "net_per_year": float((1 + sub["net"].mean()) ** per_year - 1), "t": t,
                "hit": float((sub["net"] > 0).mean()), "turnover": float(sub["turnover"].mean())}
    ex = df[~df["holdout"]] if len(df) else df
    ho = df[df["holdout"]] if len(df) else df
    out["explore"] = stats(ex) if len(ex) else {"periods": 0}
    out["holdout"] = stats(ho) if len(ho) else {"periods": 0}
    out["periods"] = picks
    if deciles:
        dm = np.nanmean(np.vstack([x for x in deciles if len(x) == 10]), axis=0) if any(len(x) == 10 for x in deciles) else None
        out["decile_excess"] = None if dm is None else [float(x) for x in dm]
    # the latest forecast
    d = pdates[-1]
    s, w = preds[d]
    out["as_of"] = d.date().isoformat()
    out["weights"] = {f: float(x) for f, x in zip(feats, w[1:])}
    out["latest"] = {tk: float(v) for tk, v in s.dropna().items()}
    e = out["explore"]
    out["passes"] = bool(e.get("t") is not None and e["t"] >= 2.0 and e.get("ic_t") is not None and e["ic_t"] >= 2.0)
    return out


def run(data_dir: str, log=print) -> dict:
    from stockproof import lab
    h0 = lab.holdout_start()
    F, px, universe = panel(data_dir, log)
    res = {"made": dt.date.today().isoformat(), "universe": universe, "stocks": int(px.shape[1]),
           "holdout_start": h0.date().isoformat(), "cost": COST, "horizons": {}}
    for name, h in HORIZONS.items():
        log(f"  forecast {name}: walk-forward ...")
        r = walk_forward(F, px, h, h0)
        latest = r.pop("latest", {})
        if latest:
            s = pd.Series(latest)
            pct = s.rank(pct=True)
            dec = r.get("decile_excess")
            r["stocks"] = {tk: {"pct": round(float(pct[tk]), 3),
                                "expected": None if not dec else round(float(dec[min(9, int(pct[tk] * 10))]), 4)}
                           for tk in s.index}
        res["horizons"][name] = r
    with open(_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, default=str)
    return res


# ---------------------------------------------------------------- reading it
def stock_view(res: dict, ticker: str, lang: str = "zh") -> dict | None:
    """One stock's forecast at each horizon, with the model's track record and whether it can be trusted."""
    zh = lang == "zh"
    out = {"ticker": ticker, "as_of": None, "horizons": [], "universe": res.get("universe")}
    for name, r in res.get("horizons", {}).items():
        x = (r.get("stocks") or {}).get(ticker)
        if not x:
            continue
        out["as_of"] = r.get("as_of")
        e, h = r.get("explore", {}), r.get("holdout", {})
        ok = r.get("passes")
        out["horizons"].append({
            "horizon": name, "pct": x["pct"], "expected": x["expected"], "reliable": ok,
            "track": {"periods": e.get("periods"), "net_per_year": e.get("net_per_year"), "t": e.get("t"),
                      "ic": e.get("ic"), "hit": e.get("hit")},
            "holdout": {"periods": h.get("periods"), "net": h.get("net"), "t": h.get("t")},
            "text": _line(name, x, r, zh)})
    return out if out["horizons"] else None


def _line(name: str, x: dict, r: dict, zh: bool) -> str:
    hz = {"3m": "3 个月", "6m": "6 个月", "12m": "12 个月"}[name] if zh else name
    e = r.get("explore", {})
    rank = f"{100 * x['pct']:.0f}"
    exp = x.get("expected")
    if zh:
        s = f"未来 {hz}：在可比的 A 股里排第 {rank} 百分位（100 最看好）"
        if exp is not None:
            s += f"，历史上同档股票平均相对大盘 {100 * exp:+.1f}%"
        s += "。" + ("模型通过了检验" if r.get("passes") else "模型没通过检验，只能参考")
        if e.get("periods"):
            s += f"（买前 10%：扣成本后每年 {100 * (e.get('net_per_year') or 0):+.1f}%，t = {e.get('t') or 0:+.1f}，{e['periods']} 期）"
        return s
    s = f"Next {hz}: {rank}th percentile of the stocks covered (100 = most favoured)"
    if exp is not None:
        s += f"; stocks in that tenth averaged {100 * exp:+.1f}% vs the market"
    s += ". " + ("The model passed its tests" if r.get("passes") else "The model did not pass its tests; context only")
    if e.get("periods"):
        s += f" (top 10%: {100 * (e.get('net_per_year') or 0):+.1f}%/yr after costs, t = {e.get('t') or 0:+.1f}, {e['periods']} periods)"
    return s


def summary_text(res: dict, lang: str = "zh") -> list[str]:
    zh = lang == "zh"
    out = []
    uni = ("全市场" if res.get("universe") == "all" else "今天的沪深300 成分股（偏乐观，建议下载全市场价格）") if zh else \
          ("the whole market" if res.get("universe") == "all" else "today's CSI 300 members (optimistic; download the whole market)")
    out.append((f"范围：{uni}，{res.get('stocks')} 只股票；每次买入排名前 10% 的股票，持有到期，和平均股票比，扣成本 {100 * res['cost']:.2f}%/次。")
               if zh else f"Universe: {uni}, {res.get('stocks')} stocks; buy the top 10%, hold, vs the average stock, {100 * res['cost']:.2f}% per round trip.")
    for name, r in res["horizons"].items():
        e, h = r.get("explore", {}), r.get("holdout", {})
        if not e.get("periods"):
            continue
        hz = {"3m": "3 个月", "6m": "6 个月", "12m": "12 个月"}[name] if zh else name
        if zh:
            out.append(f"{hz}：排序能力 IC {e['ic']:+.3f}（t = {e.get('ic_t') or 0:+.1f}），买前 10% 扣成本后每年 "
                       f"{100 * e['net_per_year']:+.1f}%（t = {e.get('t') or 0:+.1f}，{e['periods']} 期，{100 * e['hit']:.0f}% 的期数赚钱）"
                       + ("，通过检验" if r.get("passes") else "，没通过检验")
                       + (f"；锁定的近两年 {h['periods']} 期，平均每期 {100 * (h.get('net') or 0):+.1f}%" if h.get("periods") else "") + "。")
        else:
            out.append(f"{hz}: IC {e['ic']:+.3f} (t = {e.get('ic_t') or 0:+.1f}); top 10% {100 * e['net_per_year']:+.1f}%/yr after costs "
                       f"(t = {e.get('t') or 0:+.1f}, {e['periods']} periods)" + (", passes" if r.get("passes") else ", does not pass")
                       + (f"; locked last two years: {h['periods']} periods, {100 * (h.get('net') or 0):+.1f}% each" if h.get("periods") else "") + ".")
    return out


# ---------------------------------------------------------------- whole-market prices
def all_codes(data_dir: str) -> list[str]:
    """Every A-share code seen in any cached 业绩报表 period since 2015 (includes later-delisted companies)."""
    d = os.path.join(data_dir, "cn")
    codes = set()
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if re.fullmatch(r"research_yjbb2_\d{8}\.json", f):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                codes |= {str(r["code"]).zfill(6) for r in json.load(fh)}
    return sorted(c for c in codes if c[0] in "036")            # Shanghai / Shenzhen A-shares (no B shares, no BJ)


def download_prices(data_dir: str, start: str = "2015-01-01", batch: int = 200, log=print) -> dict:
    """Adjusted daily closes for the whole A-share market from Yahoo Finance, in resumable batches
    (research/allpx/). About 30-60 minutes the first time; reruns skip finished batches."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("needs yfinance:  pip install yfinance") from e
    import time
    codes = all_codes(data_dir)
    if not codes:
        raise RuntimeError("no 业绩报表 cache: run `stockproof screen` once first")
    out_dir = os.path.join(_dir(data_dir), "allpx")
    os.makedirs(out_dir, exist_ok=True)
    yahoo = {c: c + (".SS" if c[0] == "6" else ".SZ") for c in codes}
    ours = {v: c + (".SH" if c[0] == "6" else ".SZ") for c, v in yahoo.items()}
    chunks = [codes[i:i + batch] for i in range(0, len(codes), batch)]
    done = failed = 0
    for i, ch in enumerate(chunks):
        p = os.path.join(out_dir, f"part_{i:03d}.csv")
        if os.path.exists(p):
            done += 1
            continue
        for attempt in range(3):
            try:
                df = yf.download([yahoo[c] for c in ch], start=start, auto_adjust=True, progress=False, threads=True)["Close"]
                break
            except Exception as e:                                # rate limits: back off and retry
                log(f"  batch {i + 1}: {type(e).__name__}, retrying")
                time.sleep(20 * (attempt + 1))
        else:
            failed += 1
            continue
        if isinstance(df, pd.Series):
            df = df.to_frame(yahoo[ch[0]])
        df = df.rename(columns=ours).dropna(how="all", axis=1).round(4)
        df.to_csv(p)
        done += 1
        log(f"  prices: batch {i + 1}/{len(chunks)} ({df.shape[1]} stocks)")
        time.sleep(2)
    parts = [pd.read_csv(os.path.join(out_dir, f), index_col=0, parse_dates=True)
             for f in sorted(os.listdir(out_dir)) if f.endswith(".csv")]
    if not parts:
        return {"stocks": 0, "failed_batches": failed}
    allpx = pd.concat(parts, axis=1)
    allpx = allpx.loc[:, ~allpx.columns.duplicated()].sort_index()
    today = pd.Timestamp(dt.date.today())
    allpx = allpx[allpx.index < today]                             # today's bar may be partial
    allpx.to_csv(os.path.join(_dir(data_dir), "cn_all_prices.csv.gz"), compression="gzip")
    return {"stocks": int(allpx.shape[1]), "codes": len(codes), "days": int(allpx.shape[0]),
            "from": allpx.index[0].date().isoformat(), "to": allpx.index[-1].date().isoformat(), "failed_batches": failed}
