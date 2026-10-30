"""
Portfolio check-up: what your holdings really add up to, measured on real price history.

Give it holdings (ticker + shares, value or weight; an AI agent can read them off a broker screenshot) and it
computes, from daily prices:
  * concentration: largest positions, industries (Shenwan for A-shares), effective number of positions
  * hidden overlap: pairs of holdings that move together (correlation over the last year)
  * risk: volatility, beta to each market's index, where the risk actually comes from (risk contribution)
  * stress tests: replays of real crashes (2015, 2018, 2020, 2021–22, early 2024) on today's weights —
    with each stock's own return in that window when it was listed, else its beta times the index (marked)
  * each holding's whole-market rank and saved evidence scorecard, when available
and writes an illustrated report plus plain-language findings. No buy/sell advice.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os

import numpy as np
import pandas as pd

from stockproof import clock, cn, quotes

FX_DEFAULT = {"CNY": 1.0, "HKD": 0.92, "USD": 7.15}           # approximate; callers can pass current rates
CCY = {"A": "CNY", "HK": "HKD", "US": "USD"}
STRESS = [
    ("2015 股灾", "2015 crash", "2015-06-12", "2015-08-26"),
    ("2018 贸易摩擦", "2018 trade war", "2018-01-26", "2018-10-18"),
    ("2020 新冠冲击", "2020 Covid shock", "2020-01-14", "2020-03-23"),
    ("2021–22 核心资产下跌", "2021–22 large-cap selloff", "2021-02-10", "2022-04-26"),
    ("2024 年初小盘股踩踏", "early-2024 small-cap rout", "2024-01-02", "2024-02-05"),
]


class HoldingsError(ValueError):
    pass


def pdir(data_dir: str) -> str:
    d = os.path.join(data_dir, "portfolio")
    os.makedirs(os.path.join(d, "prices"), exist_ok=True)
    os.makedirs(os.path.join(d, "reports"), exist_ok=True)
    return d


def history(data_dir: str, ticker: str, start: str = "2015-01-01", max_age_hours: float = 20,
            fetch=quotes.download) -> pd.Series:
    """Long daily history (cached per ticker, refreshed daily)."""
    p = os.path.join(pdir(data_dir), "prices", ticker.replace("^", "_") + ".csv")
    if os.path.exists(p) and (dt.datetime.now().timestamp() - os.path.getmtime(p)) < max_age_hours * 3600:
        s = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0].astype(float)
        if len(s):
            return s
    s = fetch(ticker, dt.date.fromisoformat(start))
    if len(s):
        s.rename("close").to_frame().to_csv(p)
    return s


def parse_holdings(holdings) -> list[dict]:
    """[{ticker, shares | value | weight, cost?, name?, industry?}] or 'AAPL 100, 600519 200' text."""
    if isinstance(holdings, str):
        items = []
        for part in holdings.replace("，", ",").replace("\n", ",").split(","):
            bits = part.split()
            if len(bits) >= 2:
                try:
                    items.append({"ticker": bits[0], "shares": float(bits[1])})
                except ValueError:
                    raise HoldingsError(f"can't read '{part.strip()}': use 'TICKER SHARES'")
        holdings = items
    if not isinstance(holdings, list) or not holdings:
        raise HoldingsError("holdings must be a non-empty list like [{\"ticker\": \"600519\", \"shares\": 100}]")
    out, seen = [], {}
    for h in holdings:
        if not isinstance(h, dict) or not h.get("ticker"):
            raise HoldingsError("each holding needs a ticker")
        tk = cn.canonical(str(h["ticker"]).strip().upper())
        keys = [k for k in ("shares", "value", "weight") if h.get(k) not in (None, "")]
        if not keys:
            raise HoldingsError(f"{tk}: give shares, value or weight")
        rec = {"ticker": tk, "market": quotes.market_of(tk), "name": h.get("name"), "industry": h.get("industry")}
        for k in ("shares", "value", "weight", "cost"):
            if h.get(k) not in (None, ""):
                try:
                    rec[k] = float(h[k])
                except (TypeError, ValueError):
                    raise HoldingsError(f"{tk}: {k} must be a number")
        if tk in seen:                                            # the same stock twice: add up
            for k in ("shares", "value", "weight"):
                if k in rec:
                    out[seen[tk]][k] = out[seen[tk]].get(k, 0) + rec[k]
            continue
        seen[tk] = len(out)
        out.append(rec)
    kinds = {("weight" if "weight" in h else "amount") for h in out}
    if len(kinds) > 1:
        raise HoldingsError("use either weights for all holdings, or shares/values for all")
    return out


def _industry(data_dir: str, h: dict, client=None) -> str:
    if h.get("industry"):
        return h["industry"]
    if h["market"] == "A":
        from stockproof import policy, screener
        em = screener.industry_of(data_dir, h["ticker"][:6])
        if em:
            try:
                sw = policy.industry_map(data_dir, client, [em]).get(em)
            except Exception:
                sw = None
            return sw or em
        return "A股（行业未知）"
    return {"HK": "港股", "US": "美股"}[h["market"]]


def _stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 20:
        return {}
    curve = (1 + r).cumprod()
    return {"ann_vol": float(r.std(ddof=1) * math.sqrt(252)), "ret": float(curve.iloc[-1] - 1),
            "max_dd": float((curve / curve.cummax() - 1).min())}


def remember(data_dir: str, text: str) -> None:
    """Keep the last holdings typed in the dashboard (local file, so the tab can refill it next time)."""
    text = text.strip()[:2000]
    if text:
        with open(os.path.join(pdir(data_dir), "last_holdings.txt"), "w", encoding="utf-8") as f:
            f.write(text)


def saved(data_dir: str, limit: int = 20) -> dict:
    """The last holdings text and the saved reports, newest first."""
    d = pdir(data_dir)
    try:
        with open(os.path.join(d, "last_holdings.txt"), encoding="utf-8") as f:
            last = f.read()
    except OSError:
        last = ""
    ids = sorted((f[:-5] for f in os.listdir(os.path.join(d, "reports")) if f.endswith(".html")), reverse=True)
    return {"last": last, "reports": ids[:limit]}


def checkup(data_dir: str, holdings, fx: dict | None = None, lang: str = "zh", client=None,
            fetch=quotes.download, log=print) -> dict:
    zh = lang == "zh"
    hs = parse_holdings(holdings)
    fx = {**FX_DEFAULT, **(fx or {})}
    today = clock.today()
    prices, problems = {}, []
    for h in hs:
        try:
            prices[h["ticker"]] = history(data_dir, h["ticker"], fetch=fetch)
        except Exception as e:
            problems.append(f"{h['ticker']}: prices unavailable ({type(e).__name__})")
    benches = {}
    for m in sorted({h["market"] for h in hs}):
        try:
            benches[m] = history(data_dir, quotes.BENCH[m], fetch=fetch)
        except Exception as e:
            problems.append(f"{quotes.BENCH[m]}: index unavailable ({type(e).__name__})")
    hs = [h for h in hs if h["ticker"] in prices and len(prices[h["ticker"]])]
    if not hs:
        raise HoldingsError("no prices for any holding: " + "; ".join(problems))

    # --- weights in CNY
    for h in hs:
        last = float(prices[h["ticker"]].iloc[-1])
        h["price"] = last
        h["price_date"] = prices[h["ticker"]].index[-1].date().isoformat()
        if "weight" in h:
            h["value_cny"] = h["weight"]
        else:
            v = h["value"] if "value" in h else h["shares"] * last
            h["value_local"] = v
            h["value_cny"] = v * fx[CCY[h["market"]]]
            if "cost" in h and "shares" in h:
                h["pnl_pct"] = last / h["cost"] - 1 if h["cost"] else None
    total = sum(h["value_cny"] for h in hs)
    for h in hs:
        h["weight"] = h["value_cny"] / total
        h["industry"] = _industry(data_dir, h, client)
    w = pd.Series({h["ticker"]: h["weight"] for h in hs})

    # --- one year of daily returns (holidays differ by market: a closed day counts as 0)
    start1y = pd.Timestamp(today) - pd.Timedelta(days=365)
    # returns on each stock's own trading days, then aligned (a holiday in one market isn't a missing return)
    rets = pd.DataFrame({tk: s.pct_change(fill_method=None) for tk, s in prices.items() if tk in w.index})
    r1 = rets[rets.index >= start1y].fillna(0.0)
    r1 = r1.loc[:, [c for c in w.index if c in r1]]
    port = (r1 * w).sum(axis=1)
    corr = r1.corr()
    cov = r1.cov() * 252
    pv = float(w @ cov.loc[w.index, w.index] @ w)
    rc = (w * (cov.loc[w.index, w.index] @ w)) / pv if pv > 0 else w * 0
    per_vol = (r1.std(ddof=1) * math.sqrt(252)).to_dict()
    betas = {}
    for h in hs:
        b = benches.get(h["market"])
        if b is None:
            continue
        br = b.pct_change(fill_method=None)
        x = pd.concat([rets[h["ticker"]], br], axis=1, keys=["s", "b"]).dropna()
        x = x[x.index >= start1y]
        if len(x) > 60 and x["b"].var() > 0:
            betas[h["ticker"]] = float(x["s"].cov(x["b"]) / x["b"].var())
    pstats = _stats(port)
    pstats["beta"] = float(sum(w[t] * betas.get(t, 1.0) for t in w.index))
    eff_n = float(1 / (w ** 2).sum())
    dr = float(sum(w[t] * per_vol.get(t, 0) for t in w.index) / math.sqrt(pv)) if pv > 0 else None

    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c = corr.iloc[i, j]
            if c == c and c >= 0.6:
                pairs.append({"a": cols[i], "b": cols[j], "corr": round(float(c), 2)})
    pairs.sort(key=lambda p: -p["corr"])
    ind = {}
    for h in hs:
        ind[h["industry"]] = ind.get(h["industry"], 0) + h["weight"]
    ind = dict(sorted(ind.items(), key=lambda kv: -kv[1]))

    # --- stress tests on today's weights
    stress = []
    for name_zh, name_en, a, b in STRESS:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        total_r, est, parts = 0.0, [], {}
        for h in hs:
            s = prices[h["ticker"]]
            s_win = s[(s.index >= a) & (s.index <= b)]
            if len(s_win) >= 5 and s.index[0] <= a + pd.Timedelta(days=7):
                r = float(s_win.iloc[-1] / s_win.iloc[0] - 1)
            else:
                bm = benches.get(h["market"])
                if bm is None:
                    r = float("nan")
                else:
                    bw = bm[(bm.index >= a) & (bm.index <= b)]
                    r = float(betas.get(h["ticker"], 1.0) * (bw.iloc[-1] / bw.iloc[0] - 1)) if len(bw) >= 5 else float("nan")
                est.append(h["ticker"])
            parts[h["ticker"]] = r
            total_r += h["weight"] * (0 if r != r else r)
        idx = {}
        for m, bm in benches.items():
            bw = bm[(bm.index >= a) & (bm.index <= b)]
            if len(bw) >= 5:
                idx[quotes.BENCH[m]] = float(bw.iloc[-1] / bw.iloc[0] - 1)
        stress.append({"name": name_zh if zh else name_en, "from": a.date().isoformat(), "to": b.date().isoformat(),
                       "portfolio": total_r, "index": idx, "estimated": est, "by_holding": parts})

    # --- each holding: rank and saved scorecard
    from stockproof import scorecard, screener
    cards = {c["ticker"]: c for c in scorecard.load_batch(data_dir)}
    rows = []
    for h in sorted(hs, key=lambda x: -x["weight"]):
        tk = h["ticker"]
        rank = screener.lookup(data_dir, tk, lang) if h["market"] == "A" else None
        card = cards.get(tk)
        rows.append({**{k: h.get(k) for k in ("ticker", "name", "market", "industry", "weight", "price", "price_date",
                                              "pnl_pct", "value_cny")},
                     "vol": per_vol.get(tk), "beta": betas.get(tk), "risk_share": float(rc.get(tk, 0)),
                     "rank": rank if rank and rank.get("covered") else None,
                     "card": {"score": card["overall"].get("score"), "label": card["overall"].get("label_text")}
                     if card else None})
    if not any(r.get("name") for r in rows):
        names = cn.CNCache(data_dir).names() if os.path.isdir(os.path.join(data_dir, "cn")) else {}
        for r in rows:
            r["name"] = r.get("name") or names.get(r["ticker"])

    findings = _findings(rows, ind, pairs, eff_n, pstats, stress, zh)
    out = {"as_of": today.isoformat(), "holdings": rows, "total_cny": total if "value_local" in hs[0] else None,
           "industries": ind, "correlated_pairs": pairs[:10], "effective_n": eff_n, "diversification_ratio": dr,
           "portfolio": pstats, "stress": stress, "findings": findings, "fx": fx if "value_local" in hs[0] else None,
           "problems": problems,
           "corr": {"tickers": cols, "matrix": [[round(float(x), 2) for x in row] for row in corr.to_numpy()]},
           "curve": {"dates": [d.date().isoformat() for d in port.index],
                     "values": [round(float(v), 5) for v in (1 + port).cumprod().to_numpy()]},
           "note": ("用今天的持仓比例回看历史；不是预测，也不构成投资建议。" if zh else
                    "Today's weights applied to history; not a forecast or investment advice.")}
    from stockproof import portfolio_report
    rid = f"{dt.datetime.now():%Y%m%d-%H%M%S}"
    path = os.path.join(pdir(data_dir), "reports", f"{rid}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(portfolio_report.build(out, lang))
    out["id"], out["report"] = rid, path
    return json.loads(json.dumps(out, default=lambda v: None if isinstance(v, float) and not math.isfinite(v) else str(v)))


def _findings(rows, ind, pairs, eff_n, pstats, stress, zh) -> list[dict]:
    f = []
    top = rows[0]
    if top["weight"] >= 0.3:
        f.append({"level": "warn", "text": (f"{top['name'] or top['ticker']} 占了 {100 * top['weight']:.0f}%，一只股票就决定了大半个账户。"
                                            if zh else f"{top['ticker']} is {100 * top['weight']:.0f}% of the account.")})
    big_ind = next(iter(ind.items()))
    if "未知" not in big_ind[0] and (big_ind[1] >= 0.4 and len(ind) > 1 or (len(ind) == 1 and len(rows) > 1)):
        f.append({"level": "warn", "text": (f"{big_ind[0]} 行业占 {100 * big_ind[1]:.0f}%：行业出问题时这些股票会一起跌。"
                                            if zh else f"{big_ind[0]} is {100 * big_ind[1]:.0f}% of the account: one sector's bad news hits all of it.")})
    hi = [p for p in pairs if p["corr"] >= 0.7]
    if hi:
        names = "、".join(f"{p['a']}/{p['b']}" for p in hi[:3])
        f.append({"level": "warn", "text": (f"{len(hi)} 对持仓走势高度同步（相关系数 ≥ 0.7，比如 {names}），看起来分散，其实是同一个赌注。"
                                            if zh else f"{len(hi)} pairs move together (correlation ≥ 0.7, e.g. {names}): less diversified than it looks.")})
    if eff_n < 4 and len(rows) >= 4:
        f.append({"level": "info", "text": (f"按仓位算，相当于只持有 {eff_n:.1f} 只等权股票。" if zh else
                                            f"By weight, this is like holding {eff_n:.1f} equal positions.")})
    if pstats.get("beta", 1) >= 1.2:
        f.append({"level": "info", "text": (f"组合的贝塔约 {pstats['beta']:.2f}：大盘跌 10%，这个组合平均跌约 {10 * pstats['beta']:.0f}%。"
                                            if zh else f"Beta about {pstats['beta']:.2f}: a 10% market fall has meant about {10 * pstats['beta']:.0f}% here.")})
    worst = min(stress, key=lambda s: s["portfolio"]) if stress else None
    if worst and worst["portfolio"] <= -0.2:
        f.append({"level": "warn", "text": (f"如果重演「{worst['name']}」，按今天的持仓大约会亏 {100 * -worst['portfolio']:.0f}%。"
                                            if zh else f"A repeat of the {worst['name']} would cost about {100 * -worst['portfolio']:.0f}% at today's weights.")})
    risky = max(rows, key=lambda r: r["risk_share"])
    if risky["risk_share"] >= 0.4 and risky["risk_share"] > risky["weight"] * 1.3:
        f.append({"level": "info", "text": (f"{risky['name'] or risky['ticker']} 仓位 {100 * risky['weight']:.0f}%，却贡献了 {100 * risky['risk_share']:.0f}% 的波动。"
                                            if zh else f"{risky['ticker']} is {100 * risky['weight']:.0f}% of the money but {100 * risky['risk_share']:.0f}% of the risk.")})
    if not f:
        f.append({"level": "ok", "text": "没有发现明显的集中或同涨同跌问题。" if zh else "No obvious concentration or overlap found."})
    return f
