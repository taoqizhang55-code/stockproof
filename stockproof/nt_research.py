"""
"Act on what the national team does": tests that try to turn the disclosed moves of the national team,
pensions, insurers, northbound and funds into something tradable, and say plainly which ones survive.

Three studies, all in one saved report (flows/nt_research.json):

1. signal tests — for each investor kind x action (new / add / reduce / exit), the 60-day return of the stock
   after the disclosure, against OTHER stocks whose top-10 holders were disclosed in the same month. That
   matched baseline matters: every disclosure lands in report season, and against the plain equal-weight index
   almost every signal looks negative (-6%/yr for all disclosures together), which says nothing about the signal.
   Standard errors cluster by month; the bar is Bonferroni over all the tests run. Only the lab's exploration
   period is used; anything that passes is then checked once on the locked holdout.

2. ETF timing — days the key broad ETFs saw a flagged "rescue" creation (and, the other way, unusually large
   redemptions), and what the CSI 300 did over the next 20 / 60 trading days against an ordinary day.
   Few episodes: the result is descriptive, never a verdict.

3. next-quarter prediction — before a quarter's reports come out, which stocks are most likely to show a NEW
   national-team holder? A logistic model on what was known at the quarter's end (past national holdings, the
   quarter's fall, size proxy, other long-term holders, the industry's recent national buying), trained only on
   earlier quarters (walk-forward). Scored on precision of its top picks against the base rate, and on whether
   buying the top picks at the quarter's end and selling at the disclosure beat the other stocks.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os

import numpy as np
import pandas as pd

HOLD = 60
KINDS = ("national", "social", "northbound", "insurance", "qfii", "fund")
ACTIONS = ("new", "add", "reduce", "exit")
TOP_K = 20


def _path(data_dir: str) -> str:
    from stockproof.flows import flows_dir
    return os.path.join(flows_dir(data_dir), "nt_research.json")


def load(data_dir: str) -> dict | None:
    p = _path(data_dir)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bonferroni_t(n_tests: int, alpha: float = 0.05) -> float:
    """Two-sided |t| bar for `n_tests` tests at family-wise `alpha` (normal approximation)."""
    p = alpha / (2 * max(1, n_tests))
    lo, hi = 0.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if 1 - _norm_cdf(mid) > p:
            lo = mid
        else:
            hi = mid
    return round(hi, 2)


# ---------------------------------------------------------------- 1. per-event returns + signal tests
def event_returns(data_dir: str, hold: int = HOLD, log=print) -> pd.DataFrame:
    """Every disclosure event in the research price universe, with the stock's return from the close of the
    first trading day after the announcement to `hold` days later, and the same for the equal-weight universe."""
    from stockproof import flows, lab
    px = lab.stock_prices(data_dir, "cn")
    if px is None:
        raise RuntimeError("no A-share research prices: run `stockproof research --market cn` once")
    ev = flows.events(data_dir, log=log)
    ev = ev[ev["ticker"].isin(px.columns)].copy()
    idx = px.index.values
    pos = np.searchsorted(idx, ev["day0"].values.astype("datetime64[ns]"), side="right")
    ok = pos + hold < len(idx)
    ev, pos = ev[ok].copy(), pos[ok]
    a = px.to_numpy(float)
    cols = np.array([px.columns.get_loc(t) for t in ev["ticker"]])
    ew = px.pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0).to_numpy()
    cum = np.cumprod(1 + ew)
    ev["entry_day"] = px.index[pos]
    ev["ret"] = a[pos + hold, cols] / a[pos, cols] - 1
    ev["mkt"] = cum[pos + hold] / cum[pos] - 1
    ev["ex"] = ev["ret"] - ev["mkt"]
    return ev.dropna(subset=["ex"])


def _vs_others(ev: pd.DataFrame, mask: pd.Series) -> dict:
    """Mean 60-day excess of the group minus the other events disclosed in the same month; t clustered by month."""
    x = ev.assign(_g=mask.astype(int), _m=ev["day0"].dt.to_period("M"))
    mm = x.groupby(["_m", "_g"])["ex"].mean().unstack()
    if 1 not in mm or 0 not in mm:
        return {"n": int(mask.sum()), "months": 0, "diff": None, "t": None}
    d = (mm[1] - mm[0]).dropna()
    t = float(d.mean() / d.std(ddof=1) * math.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else None
    return {"n": int(mask.sum()), "months": int(len(d)), "diff": float(d.mean()), "t": t,
            "group_mean": float(ev.loc[mask, "ex"].mean()), "hit": float((d > 0).mean())}


def _mask(ev: pd.DataFrame, kind: str, action: str) -> pd.Series:
    m = (ev["category"] == kind) & (ev["action"] == action)
    if action == "exit":
        m &= ev["confidence"] == "inferred"
    return m


def signal_tests(ev: pd.DataFrame, holdout: pd.Timestamp) -> dict:
    explore = ev[ev["day0"] < holdout]
    hold = ev[ev["day0"] >= holdout]
    rows = []
    for k in KINDS:
        for a in ACTIONS:
            m = _mask(explore, k, a)
            if m.sum() < 30:
                continue
            rows.append({"kind": k, "action": a, **_vs_others(explore, m)})
    bar = bonferroni_t(len(rows))
    for r in rows:
        r["passes"] = r["t"] is not None and abs(r["t"]) >= bar
        if r["passes"]:                                     # checked once on the locked holdout
            h = _vs_others(hold, _mask(hold, r["kind"], r["action"]))
            r["holdout"] = h
            r["confirmed"] = h["t"] is not None and np.sign(h["diff"] or 0) == np.sign(r["diff"]) and abs(h["t"]) >= 2.0
    return {"tests": rows, "n_tests": len(rows), "bar": bar,
            "baseline": {"events": int(len(explore)), "mean_excess_60d": float(explore["ex"].mean())},
            "period": [explore["day0"].min().date().isoformat(), holdout.date().isoformat()]}


# ---------------------------------------------------------------- 2. ETF timing
def etf_timing(data_dir: str, fetch: bool = False) -> dict:
    from stockproof import etf_flows
    df = etf_flows.daily(data_dir, fetch=fetch, start=dt.date(2023, 11, 1), log=lambda *a: None)
    if df.empty or "510300" not in "".join(df.columns):
        return {"available": False}
    nav = etf_flows.nav(data_dir, "510300", dt.date(2023, 11, 1), fetch=False).dropna()   # every trading day
    nav = nav[~nav.index.duplicated()].sort_index()
    sd = df["total"].rolling(60, min_periods=20).std().shift(1)
    df = df.assign(redeem=(df["total"] <= -etf_flows.FLAG_MIN) & (df["total"] / sd <= -etf_flows.FLAG_Z))

    def episodes(flag: pd.Series) -> list[pd.Timestamp]:
        days, last = [], None                                # days within 10 trading days = one episode
        pos = {d: i for i, d in enumerate(df.index)}
        for d in df.index[flag.fillna(False).to_numpy()]:
            if last is None or pos[d] - pos[last] > 10:
                days.append(d)
            last = d
        return days

    def fwd(days, n):
        out = []
        for d in days:
            i = int(nav.index.searchsorted(d))
            if i + n < len(nav):
                out.append(float(nav.iloc[i + n] / nav.iloc[i] - 1))
        return out
    all20 = (nav.shift(-20) / nav - 1).dropna()
    all60 = (nav.shift(-60) / nav - 1).dropna()
    res = {"available": True, "from": df.index[0].date().isoformat(), "to": df.index[-1].date().isoformat(),
           "share_days": int(len(df)), "trading_days": int(((nav.index >= df.index[0]) & (nav.index <= df.index[-1])).sum()),
           "normal_20d": float(all20.mean()), "normal_60d": float(all60.mean())}
    for name, flag in (("rescue", df["flag"]), ("redemption", df["redeem"])):
        eps = episodes(flag)
        f20, f60 = fwd(eps, 20), fwd(eps, 60)
        res[name] = {"episodes": [d.date().isoformat() for d in eps], "n": len(eps),
                     "after_20d": f20, "after_60d": f60,
                     "mean_20d": float(np.mean(f20)) if f20 else None, "mean_60d": float(np.mean(f60)) if f60 else None,
                     "up_20d": int(sum(x > 0 for x in f20))}
    return res


# ---------------------------------------------------------------- 3. next-quarter prediction
def _logit_fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 30) -> np.ndarray:
    """Logistic regression by Newton steps with a small ridge penalty (no intercept penalty)."""
    w = np.zeros(X.shape[1])
    P = np.eye(X.shape[1]) * l2
    P[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y) + P @ w
        H = (X * (p * (1 - p))[:, None]).T @ X + P
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return w


FEATURES = ["ever_national", "national_last_q", "qtr_return", "qtr_drawdown", "size", "social", "insurance",
            "fund", "northbound", "industry_new_share"]
FEATURE_ZH = {"ever_national": "以前被国家队持有过", "national_last_q": "上季度国家队在前十", "qtr_return": "本季度涨跌",
              "qtr_drawdown": "本季度最大回撤", "size": "规模（前十大股东市值）", "social": "社保在前十",
              "insurance": "险资在前十", "fund": "公募在前十", "northbound": "北向在前十",
              "industry_new_share": "同行业上季度被国家队新进的比例"}


def quarter_panel(data_dir: str, log=print) -> pd.DataFrame:
    """One row per (stock in the research universe, quarter end): features known at the quarter's end (holder
    features from the PREVIOUS quarter's reports, prices up to the quarter's end) and whether the national team
    shows up as a new holder in this quarter's report, plus prices to trade before that report comes out."""
    import re
    from stockproof import cn, flows, lab
    px = lab.stock_prices(data_dir, "cn")
    d = flows.flows_dir(data_dir)
    qs = sorted(f[8:16] for f in os.listdir(d) if re.fullmatch(r"holders_\d{8}\.csv", f))
    ind = flows._industry_map(data_dir)
    uni = {c: (cn.parse(c) or {}).get("code", c[:6]) for c in px.columns}
    rows = []
    ever: set[str] = set()
    prev = None
    for q in qs:
        cur = flows.holders(data_dir, q, fetch=False)
        if cur.empty:
            continue
        cur = cur[cur["code"].isin(uni.values())]
        cats = cur.groupby("code")["category"].apply(lambda s: set(x for x in s if isinstance(x, str)))
        new_nat = set(cur.loc[(cur["category"] == "national") & (cur["action"] == "new"), "code"])
        public = cur.groupby("code")["public"].max()
        if prev is not None:
            pc, pval, pnew, pind_new = prev
            qend = pd.Timestamp(q)
            qstart = pd.Timestamp(qs[qs.index(q) - 1])
            win = px[(px.index > qstart) & (px.index <= qend)]
            for tk, code in uni.items():
                if code not in cats.index and code not in pc.index:
                    continue
                s = win[tk].dropna()
                if len(s) < 20:
                    continue
                pcat = pc.get(code, set())
                rows.append({
                    "quarter": q, "ticker": tk, "code": code,
                    "ever_national": float(code in ever), "national_last_q": float("national" in pcat),
                    "qtr_return": float(s.iloc[-1] / s.iloc[0] - 1),
                    "qtr_drawdown": float((s / s.cummax() - 1).min()),
                    "size": float(np.log1p(pval.get(code, 0.0) / 1e8)),
                    "social": float("social" in pcat), "insurance": float("insurance" in pcat),
                    "fund": float("fund" in pcat), "northbound": float("northbound" in pcat),
                    "industry_new_share": float(pind_new.get(ind.get(code), 0.0)),
                    "y": float(code in new_nat), "public": public.get(code)})
        val = pd.to_numeric(cur["value"], errors="coerce").groupby(cur["code"]).sum()
        by_ind = pd.Series({c: ind.get(c) for c in cats.index})
        ind_new = by_ind.groupby(by_ind).apply(lambda s: float(np.mean([c in new_nat for c in s.index])))
        ever |= set(cur.loc[cur["category"] == "national", "code"])
        prev = (cats, val, new_nat, ind_new.to_dict())
    if prev is not None and qs:                                  # the quarter now under way: y unknown yet
        pc, pval, _, pind_new = prev
        qstart = pd.Timestamp(qs[-1])
        nxt = (qstart + pd.offsets.QuarterEnd(1)).strftime("%Y%m%d")
        win = px[px.index > qstart]
        for tk, code in uni.items():
            s = win[tk].dropna()
            if len(s) < 10 or code not in pc.index:
                continue
            pcat = pc.get(code, set())
            rows.append({"quarter": nxt, "ticker": tk, "code": code, "ever_national": float(code in ever),
                         "national_last_q": float("national" in pcat), "qtr_return": float(s.iloc[-1] / s.iloc[0] - 1),
                         "qtr_drawdown": float((s / s.cummax() - 1).min()), "size": float(np.log1p(pval.get(code, 0.0) / 1e8)),
                         "social": float("social" in pcat), "insurance": float("insurance" in pcat),
                         "fund": float("fund" in pcat), "northbound": float("northbound" in pcat),
                         "industry_new_share": float(pind_new.get(ind.get(code), 0.0)), "y": np.nan, "public": None})
    return pd.DataFrame(rows)


def predict_test(data_dir: str, panel: pd.DataFrame | None = None, k: int = TOP_K, min_train: int = 8,
                 log=print) -> dict:
    from stockproof import lab
    p = quarter_panel(data_dir, log) if panel is None else panel
    if p.empty:
        return {"available": False}
    live = p[p["y"].isna()]
    p = p[p["y"].notna()]
    px = lab.stock_prices(data_dir, "cn")
    qs = sorted(p["quarter"].unique())
    X_all = p[FEATURES].to_numpy(float)
    mu, sd = X_all.mean(0), X_all.std(0) + 1e-9
    per = []
    last_w = None
    for i, q in enumerate(qs):
        if i < min_train:
            continue
        tr = p[p["quarter"] < q]
        te = p[p["quarter"] == q].copy()
        if tr["y"].sum() < 10 or te.empty:
            continue
        Xtr = np.c_[np.ones(len(tr)), (tr[FEATURES].to_numpy(float) - mu) / sd]
        w = _logit_fit(Xtr, tr["y"].to_numpy(float))
        last_w = w
        te["score"] = np.c_[np.ones(len(te)), (te[FEATURES].to_numpy(float) - mu) / sd] @ w
        top = te.nlargest(k, "score")
        base = float(te["y"].mean())
        # trade: buy the top picks at the quarter's end, sell at each stock's report date (or 60 days at most)
        qend = pd.Timestamp(q)
        i0 = int(px.index.searchsorted(qend, side="right")) - 1

        def ret(tk, pub):
            j = px.index.searchsorted(pd.Timestamp(pub), side="left") if isinstance(pub, str) else i0 + 40
            j = min(max(j, i0 + 1), i0 + 60, len(px) - 1)
            a, b = px[tk].iloc[i0], px[tk].iloc[j]
            return float(b / a - 1) if pd.notna(a) and pd.notna(b) else np.nan
        te["fwd"] = [ret(t, pub) for t, pub in zip(te["ticker"], te["public"])]
        top_ret = te.loc[top.index, "fwd"].mean()
        rest_ret = te.drop(top.index)["fwd"].mean()
        per.append({"quarter": q, "stocks": int(len(te)), "new": int(te["y"].sum()), "base_rate": base,
                    "hits": int(top["y"].sum()), "precision": float(top["y"].mean()),
                    "auc": _auc(te["score"].to_numpy(), te["y"].to_numpy()),
                    "top_return": None if pd.isna(top_ret) else float(top_ret),
                    "rest_return": None if pd.isna(rest_ret) else float(rest_ret),
                    "picks": list(top["ticker"])})
    if not per:
        return {"available": False}
    df = pd.DataFrame(per)
    gap = (df["top_return"] - df["rest_return"]).dropna()
    t = float(gap.mean() / gap.std(ddof=1) * math.sqrt(len(gap))) if len(gap) > 2 and gap.std(ddof=1) > 0 else None
    cost = 0.0035                                              # one round trip, A-shares
    out = {"available": True, "quarters": per, "k": k,
           "precision": float(df["precision"].mean()), "base_rate": float(df["base_rate"].mean()),
           "lift": float(df["precision"].mean() / df["base_rate"].mean()) if df["base_rate"].mean() else None,
           "auc": float(np.nanmean(df["auc"])),
           "excess_per_quarter": float(gap.mean()) if len(gap) else None,
           "excess_after_costs": float(gap.mean() - cost) if len(gap) else None, "t": t,
           "features": FEATURES}
    if last_w is not None:
        out["weights"] = {f: round(float(x), 3) for f, x in zip(FEATURES, last_w[1:])}
        # the quarter under way: its reports aren't out yet, so these are real forecasts
        if live.empty:
            return out
        latest = live.copy()
        latest["score"] = np.c_[np.ones(len(latest)), (latest[FEATURES].to_numpy(float) - mu) / sd] @ last_w
        out["latest_quarter"] = latest["quarter"].iloc[0]
        out["latest_note"] = ("用到目前为止的价格和上一季的股东名单做的预测；这个季度的报告出来之前没法验证。")
        out["latest_picks"] = [{"ticker": r.ticker, "prob": float(1 / (1 + math.exp(-r.score)))}
                               for r in latest.nlargest(k, "score").itertuples()]
    return out


def _names(data_dir: str) -> dict:
    import re
    from stockproof import flows
    d = flows.flows_dir(data_dir)
    qs = sorted(f[8:16] for f in os.listdir(d) if re.fullmatch(r"holders_\d{8}\.csv", f))
    if not qs:
        return {}
    h = flows.holders(data_dir, qs[-1], fetch=False)
    return dict(zip(h["code"], h["name"])) if "name" in h else {}


def _auc(score: np.ndarray, y: np.ndarray) -> float | None:
    pos, neg = score[y == 1], score[y == 0]
    if not len(pos) or not len(neg):
        return None
    r = pd.Series(np.r_[pos, neg]).rank().to_numpy()
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


# ---------------------------------------------------------------- the report
def run(data_dir: str, log=print, fetch_etf: bool = False) -> dict:
    """All three studies; `fetch_etf` first fills missing days of ETF share counts from the exchange."""
    from stockproof import lab
    h0 = lab.holdout_start()
    if fetch_etf:
        from stockproof import etf_flows
        log("  filling ETF share history since 2023-11 (a few minutes the first time) ...")
        etf_flows.daily(data_dir, fetch=True, start=dt.date(2023, 11, 1), log=log)
    log("  1/3 signal tests against a matched baseline ...")
    ev = event_returns(data_dir, log=log)
    sig = signal_tests(ev, h0)
    log("  2/3 ETF timing ...")
    etf = etf_timing(data_dir)
    log("  3/3 next-quarter prediction (walk-forward) ...")
    pred = predict_test(data_dir, log=log)
    if pred.get("latest_picks"):
        names = _names(data_dir)
        for x in pred["latest_picks"]:
            x["name"] = names.get(x["ticker"][:6], "")
    out = {"made": dt.date.today().isoformat(), "hold_days": HOLD, "holdout_start": h0.date().isoformat(),
           "signals": sig, "etf": etf, "predict": pred,
           "universe": "research price universe: today's CSI 300 members (about 300 stocks)"}
    with open(_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, default=str)
    return out


KIND_ZH = {"national": "国家队", "social": "社保/养老金", "northbound": "北向", "insurance": "险资", "qfii": "QFII",
           "fund": "公募"}
ACT_ZH = {"new": "新进", "add": "加仓", "reduce": "减仓", "exit": "退出前十"}


def summary_text(r: dict, lang: str = "zh") -> list[str]:
    """Plain-language conclusions, in the order a reader needs them."""
    zh = lang == "zh"
    s, e, p = r["signals"], r["etf"], r["predict"]
    out = []
    passed = [t for t in s["tests"] if t["passes"]]
    best = max(s["tests"], key=lambda t: abs(t["t"] or 0))
    if zh:
        out.append(f"跟着披露做（买入或回避）：{s['n_tests']} 种“谁 × 什么动作”和同月其他披露的股票比，"
                   + ("没有一种过了多重检验的门槛" if not passed else f"{len(passed)} 种过了门槛")
                   + f"（门槛 |t| ≥ {s['bar']}；最强的是{KIND_ZH[best['kind']]}{ACT_ZH[best['action']]}，"
                   f"60 天差 {100 * (best['diff'] or 0):+.1f}%，t = {best['t']:+.1f}）。")
        out.append(f"注意：和大盘直接比，所有披露过的股票之后都偏弱，这是财报季的共同现象，不是信号；"
                   f"必须和同期其他披露比才公平。")
    else:
        out.append(f"Acting on disclosures (buy or avoid): of {s['n_tests']} kind x action tests against other stocks "
                   f"disclosed the same month, {'none' if not passed else len(passed)} cleared the multiple-testing bar "
                   f"(|t| >= {s['bar']}; the strongest: {best['kind']} {best['action']}, {100 * (best['diff'] or 0):+.1f}% "
                   f"over 60 days, t = {best['t']:+.1f}).")
    for t in passed:
        h = t.get("holdout") or {}
        out.append((f"{KIND_ZH[t['kind']]}{ACT_ZH[t['action']]}：锁定的近两年数据上"
                     + ("确认了" if t.get("confirmed") else "没有确认") + f"（差 {100 * (h.get('diff') or 0):+.1f}%，t = {h.get('t') or 0:+.1f}）")
                    if zh else f"{t['kind']} {t['action']} on the locked holdout: "
                    + ("confirmed" if t.get("confirmed") else "not confirmed"))
    if e.get("available"):
        rs, rd = e["rescue"], e["redemption"]
        if zh:
            out.append(f"ETF 托底信号（{e['from']} 至 {e['to']}）：{rs['n']} 次托底，之后 20 天沪深300 平均 "
                       f"{100 * (rs['mean_20d'] or 0):+.1f}%（{rs['up_20d']}/{len(rs['after_20d'])} 次上涨），"
                       f"平常任意 20 天平均 {100 * e['normal_20d']:+.1f}%；{rd['n']} 次大额赎回，之后 20 天平均 "
                       f"{100 * (rd['mean_20d'] or 0):+.1f}%。次数太少，只能参考，不能当规律。")
        else:
            out.append(f"ETF rescue days ({e['from']} to {e['to']}): {rs['n']} episodes, CSI 300 next 20 days "
                       f"{100 * (rs['mean_20d'] or 0):+.1f}% vs {100 * e['normal_20d']:+.1f}% on an ordinary day; "
                       f"{rd['n']} big-redemption episodes, {100 * (rd['mean_20d'] or 0):+.1f}%. Too few to be a rule.")
    if p.get("available"):
        if zh:
            out.append(f"预测下季度新进：前 {p['k']} 名里平均 {100 * p['precision']:.0f}% 真的被新进，随便猜是 "
                       f"{100 * p['base_rate']:.1f}%（{p['lift']:.1f} 倍），AUC {p['auc']:.2f}。"
                       f"季报公布前买入这 {p['k']} 只，比其他股票每季平均 {100 * (p['excess_per_quarter'] or 0):+.1f}%，"
                       f"扣成本后 {100 * (p['excess_after_costs'] or 0):+.1f}%（t = {p['t'] or 0:+.1f}）。")
        else:
            out.append(f"Next-quarter new entries: {100 * p['precision']:.0f}% of the top {p['k']} were hit vs "
                       f"{100 * p['base_rate']:.1f}% by chance ({p['lift']:.1f}x), AUC {p['auc']:.2f}. Buying them "
                       f"before the reports: {100 * (p['excess_per_quarter'] or 0):+.1f}% a quarter vs the rest, "
                       f"{100 * (p['excess_after_costs'] or 0):+.1f}% after costs (t = {p['t'] or 0:+.1f}).")
    return out
