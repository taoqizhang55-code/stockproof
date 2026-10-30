"""
Research toolkit: does any of this predict stock prices?

Two event studies, built so that nothing uses information from the future:

1. Earnings (US).  For every quarter since `since`:
     SUE (from SEC XBRL, first-reported EPS)  and, optionally, the LLM's reading of the
     press release (tone, guidance), against the stock's market-adjusted return
       - reaction : day 0 and day 1 after the announcement (what the market did at once)
       - drift    : day 2 to day 61 (what you could still have earned after reading it)
   The announcement date is the 8-K "Item 2.02" filing (the press release). If it was filed
   after 16:00 New York time, day 0 is the next trading day. Quarters without a matching 8-K
   are kept but flagged: the 10-Q date is often weeks later and hides the reaction.

2. News.  Every relevant headline (relevance >= 0.5, repeats removed) against the stock's
   market-adjusted return on the day before, the day of, the day after, and days 1-5.
   Headlines only carry a date, not a time, so day 0 mixes "news caused the move" with
   "news reports the move"; only day 1 onward is something you could have traded.

Market-adjusted return = stock return minus the equal-weighted average of all stocks in the
price file (or minus SPY if the file has a SPY column).

Prices come from a CSV (Date + one column per ticker, adjusted closes), or are downloaded
with yfinance (`pip install yfinance`).
"""

from __future__ import annotations

import datetime as dt
import math
import os

import numpy as np
import pandas as pd

REACTION = (0, 1)          # trading days after the announcement, inclusive
DRIFT = (2, 61)
PRE = (-5, -1)
SUE_EDGES = [-np.inf, -2, -0.5, 0.5, 2, np.inf]
SUE_LABELS = ["≤ −2", "−2 to −0.5", "−0.5 to 0.5", "0.5 to 2", "≥ 2"]
TONE_EDGES = [-np.inf, -0.15, 0.15, np.inf]
TONE_LABELS = ["negative", "neutral", "positive"]
MAX_DAYS_TO_ANNOUNCE = 75
BENCHMARKS = ("SPY", "CSI300")   # index columns a price file may carry; else equal-weighted  # an 8-K this long after quarter end is not that quarter's results


# ---------------------------------------------------------------- prices

def load_prices(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True).sort_index()
    df.columns = [str(c).upper() for c in df.columns]
    return df[~df.index.duplicated()]


def download_prices(tickers: list[str], start: str, path: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("Downloading prices needs yfinance:  pip install yfinance\n"
                           "(or pass a CSV of adjusted closes with --prices)") from e
    symbols = sorted(set(tickers) | {"SPY"})
    df = yf.download(symbols, start=start, auto_adjust=True, progress=False)["Close"]
    df = df.dropna(how="all")
    # drop today's row while the market may still be open (a half-day "close" is not a close)
    today = pd.Timestamp(dt.date.today())
    if len(df) and df.index[-1] >= today:
        df = df.iloc[:-1]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_csv(path)
    return load_prices(path)


def abnormal_returns(prices: pd.DataFrame, use_index: bool = False) -> pd.DataFrame:
    """Stock return minus the equal-weighted average of all stocks in the file (default), or minus
    the index column (SPY / CSI300) with use_index=True. The equal-weighted default is usually the
    fairer one: a list of TODAY's index members beats the index over the past (survivorship), and
    adjusted prices include dividends while a price index doesn't; the average of the same stocks
    shares those biases, so they cancel out."""
    ret = prices.pct_change(fill_method=None)
    bench = [c for c in BENCHMARKS if c in ret.columns]
    stocks = ret.drop(columns=bench)
    market = ret[bench[0]] if (bench and use_index) else stocks.mean(axis=1)
    return stocks.sub(market, axis=0)


def event_index(days: pd.DatetimeIndex, date, after_close: bool = False) -> int | None:
    """Position of day 0: the first trading day on/after `date` (the next one if after the close)."""
    i = int(days.searchsorted(pd.Timestamp(date)))
    if i < len(days) and after_close and days[i] == pd.Timestamp(date).normalize():
        i += 1
    return i if i < len(days) else None


def window_sum(values: np.ndarray, i: int, a: int, b: int) -> float:
    """Sum of values[i+a .. i+b]; NaN if the window is not complete yet (the future)."""
    lo, hi = i + a, i + b
    if lo < 0 or hi >= len(values):
        return float("nan")
    w = values[lo:hi + 1]
    return float("nan") if np.isnan(w).all() else float(np.nansum(w))


# ---------------------------------------------------------------- SEC announcement dates

def announcement_filings(cache, cik: int, since: str, fetch: bool = True) -> list[dict]:
    """All 8-K Item 2.02 filings since `since`, oldest first.
    The main submissions file lists only the ~1000 latest filings; banks file so many notes
    that this covers barely a year, so older pages are fetched too (and kept: they never change)."""
    subs = cache.submissions(cik) if fetch else cache.cached(f"submissions_{cik}.json")
    if not subs:
        return []
    blocks = [subs.get("filings", {}).get("recent", {})]
    for page in subs.get("filings", {}).get("files", []):
        if str(page.get("filingTo", "9999")) < since:
            continue
        name = page["name"]
        data = cache.cached(name)
        if data is None and fetch:
            from marketmood.sec import get
            data = get(f"https://data.sec.gov/submissions/{name}")
            cache.save(name, data)
        if data:
            blocks.append(data)
    out, seen = [], set()
    for b in blocks:
        forms = b.get("form", [])
        for i, form in enumerate(forms):
            items = (b.get("items") or [""] * len(forms))[i] or ""
            if form not in ("8-K", "8-K/A") or "2.02" not in items:
                continue
            acc = b["accessionNumber"][i]
            if acc in seen or b["filingDate"][i] < since:
                continue
            seen.add(acc)
            out.append({"accession": acc, "filed": b["filingDate"][i],
                        "accepted": (b.get("acceptanceDateTime") or [""] * len(forms))[i] or "",
                        "primary": b["primaryDocument"][i], "form": form})
    return sorted(out, key=lambda f: f["filed"])


def after_close(accepted: str) -> bool:
    """SEC's acceptanceDateTime is New York time (despite the trailing 'Z')."""
    try:
        return int(accepted[11:13]) >= 16
    except (ValueError, IndexError):
        return False


def match_announcements(eps_q: pd.DataFrame, filings: list[dict]) -> pd.DataFrame:
    """Adds ann_date, ann_after_close, accession, date_source ('8-K' or '10-Q') to each quarter."""
    q = eps_q.copy()
    ann = pd.DataFrame(filings)
    cols = {"ann_date": [], "ann_after_close": [], "accession": [], "primary": [], "date_source": []}
    used = set()
    for _, row in q.iterrows():
        end = pd.Timestamp(row["end"])
        hit = None
        if len(ann):
            filed = pd.to_datetime(ann["filed"])
            ok = ann[(filed > end) & (filed <= end + pd.Timedelta(days=MAX_DAYS_TO_ANNOUNCE))
                     & ~ann["accession"].isin(used)]
            if len(ok):
                hit = ok.iloc[0]
        if hit is not None and str(hit["form"]) == "8-K/A" and len(ok) > 1:
            hit = ok.iloc[1] if str(ok.iloc[1]["form"]) == "8-K" else hit
        if hit is not None:
            used.add(hit["accession"])
            cols["ann_date"].append(hit["filed"])
            cols["ann_after_close"].append(after_close(hit["accepted"]))
            cols["accession"].append(hit["accession"])
            cols["primary"].append(hit["primary"])
            cols["date_source"].append("8-K")
        else:      # fall back to the 10-Q: known by then for sure, but usually later than the news
            cols["ann_date"].append(str(row["filed"])[:10])
            cols["ann_after_close"].append(True)
            cols["accession"].append(None)
            cols["primary"].append(None)
            cols["date_source"].append("10-Q")
    for k, v in cols.items():
        q[k] = v
    return q


def earnings_events(quarters: pd.DataFrame, ar: pd.DataFrame) -> pd.DataFrame:
    """quarters: rows with ticker, end, eps, sue, ann_date, ann_after_close, date_source, accession.
    Adds pre, reaction, drift (market-adjusted, summed daily returns)."""
    days = ar.index
    rows = []
    for _, q in quarters.iterrows():
        tk = q["ticker"]
        if tk not in ar.columns or pd.isna(q.get("sue")):
            continue
        i = event_index(days, q["ann_date"], bool(q["ann_after_close"]))
        if i is None:
            continue
        s = ar[tk].to_numpy(dtype=float)
        if np.isnan(s[max(0, i - 5):i + 2]).all():
            continue                       # stock not trading yet / no prices around the event
        row = {**q.to_dict(), "day0": days[i].date().isoformat(),
               "pre": window_sum(s, i, *PRE),
               "reaction": window_sum(s, i, *REACTION),
               "drift": window_sum(s, i, *DRIFT)}
        # the same quarter measured from the 10-Q date instead, to show how much the date matters
        j = event_index(days, q["filed"], True) if pd.notna(q.get("filed")) else None
        row["reaction_10q"] = window_sum(s, j, *REACTION) if j is not None else float("nan")
        row["drift_10q"] = window_sum(s, j, *DRIFT) if j is not None else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- statistics

def mean_t(x) -> tuple[int, float, float]:
    x = pd.Series(x, dtype=float).dropna()
    n = len(x)
    if n < 2:
        return n, (float(x.mean()) if n else float("nan")), float("nan")
    sd = x.std(ddof=1)
    return n, float(x.mean()), float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else float("nan")


def bucket_table(df: pd.DataFrame, col: str, edges, labels, outcomes=("reaction", "drift")) -> pd.DataFrame:
    """Mean outcome (and t-stat) per bucket of `col`, plus the top-minus-bottom difference."""
    if not len(df):
        return pd.DataFrame()
    b = pd.cut(df[col], edges, labels=labels)
    rows = []
    for lab in labels:
        part = df[b == lab]
        row = {"bucket": lab, "n": len(part)}
        for o in outcomes:
            n, m, t = mean_t(part[o])
            row[o], row[o + "_t"], row[o + "_n"] = m, t, n
        rows.append(row)
    top, bot = df[b == labels[-1]], df[b == labels[0]]
    row = {"bucket": "top − bottom", "n": len(top) + len(bot)}
    for o in outcomes:
        a, c = top[o].dropna(), bot[o].dropna()
        if len(a) > 1 and len(c) > 1:
            diff = a.mean() - c.mean()
            se = math.sqrt(a.var(ddof=1) / len(a) + c.var(ddof=1) / len(c))
            row[o], row[o + "_t"] = float(diff), float(diff / se) if se > 0 else float("nan")
        else:
            row[o], row[o + "_t"] = float("nan"), float("nan")
        row[o + "_n"] = len(a) + len(c)
    rows.append(row)
    return pd.DataFrame(rows)


def ols(y, X: pd.DataFrame) -> dict:
    """OLS with a constant and heteroskedasticity-robust (White) t-stats."""
    data = pd.concat([pd.Series(y, name="_y"), X], axis=1).dropna()
    if len(data) < X.shape[1] + 5:
        return {"n": len(data), "coef": {}, "t": {}, "r2": float("nan")}
    yv = data["_y"].to_numpy(dtype=float)
    Xv = np.column_stack([np.ones(len(data)), data[X.columns].to_numpy(dtype=float)])
    names = ["const"] + list(X.columns)
    XtX_inv = np.linalg.pinv(Xv.T @ Xv)
    beta = XtX_inv @ Xv.T @ yv
    resid = yv - Xv @ beta
    meat = Xv.T @ (Xv * (resid ** 2)[:, None])
    cov = XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    ss_tot = ((yv - yv.mean()) ** 2).sum()
    r2 = 1 - (resid ** 2).sum() / ss_tot if ss_tot > 0 else float("nan")
    return {"n": len(data), "coef": dict(zip(names, beta.tolist())),
            "t": dict(zip(names, (beta / np.where(se > 0, se, np.nan)).tolist())), "r2": float(r2)}


def clip_sue(s: pd.Series, limit: float = 5.0) -> pd.Series:
    """A few SUEs are huge (a near-zero history of changes); cap them so one stock can't dominate."""
    return s.clip(-limit, limit)


# ---------------------------------------------------------------- LLM readings of past releases

def attach_reads(events: pd.DataFrame, store, read_key: str) -> pd.DataFrame:
    """Adds tone and guidance from saved readings (by accession, any language)."""
    ev = events.copy()
    tones, guid = [], []
    import json
    for acc in ev.get("accession", pd.Series(dtype=object)):
        row = None
        if acc:
            row = store.conn.execute(
                "SELECT result FROM earnings_reads WHERE accession = ? AND model = ? "
                "ORDER BY (lang = 'en') DESC LIMIT 1", (acc, read_key)).fetchone()
        if row:
            r = json.loads(row[0])
            tones.append(r.get("tone"))
            guid.append(r.get("guidance"))
        else:
            tones.append(None)
            guid.append(None)
    ev["tone"] = pd.to_numeric(pd.Series(tones, index=ev.index), errors="coerce")
    ev["guidance"] = guid
    return ev


def backfill_reads(store, client, model_id: str, events: pd.DataFrame, names: dict,
                   per_ticker: int, lang: str = "en", log=print, workers: int = 4) -> dict:
    """Read the press releases of past announcements (the newest `per_ticker` per stock) with
    the LLM, so tone can be tested against returns. Saved like live readings, so never paid twice.
    Several releases are read at once (the LLM is the slow part); SEC requests stay rate-limited
    and all database writes happen on this thread."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from marketmood import earnings as er
    from marketmood.core import is_fatal
    read_key = f"{model_id}#v{er.READ_VERSION}"
    todo = events[events["accession"].notna()].sort_values("ann_date", ascending=False)
    todo = todo.groupby("ticker").head(per_ticker)
    jobs = [ev for _, ev in todo.iterrows() if store.earnings_read(ev["accession"], read_key, lang) is None]
    stats = {"read": 0, "cached": len(todo) - len(jobs), "failed": 0}
    if not jobs:
        return stats

    def work(ev):
        text, url = er.fetch_release_text(int(ev["cik"]), {"accession": ev["accession"], "primary": ev["primary"]})
        if not text:
            return ev, None, url
        return ev, er.read_release(client, names.get(ev["ticker"], ev["ticker"]), ev["ticker"], text, lang), url

    fatal = None
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, ev) for ev in jobs]
        for k, fut in enumerate(as_completed(futures), 1):
            try:
                ev, result, url = fut.result()
            except Exception as e:
                stats["failed"] += 1
                log(f"  [{k}/{len(jobs)}] {type(e).__name__}: {str(e)[:80]}")
                if is_fatal(e) and fatal is None:
                    fatal = e
                    for f in futures:
                        f.cancel()
                continue
            if result is None:
                stats["failed"] += 1
                log(f"  [{k}/{len(jobs)}] {ev['ticker']} {ev['ann_date']}: no press release found")
                continue
            store.save_earnings_read(ev["accession"], read_key, lang, ev["ticker"], ev["ann_date"], url, result)
            stats["read"] += 1
            log(f"  [{k}/{len(jobs)}] {ev['ticker']} {ev['ann_date']}: tone {result['tone']:+.2f}, "
                f"guidance {result['guidance']}")
    if fatal is not None:
        raise fatal
    return stats


# ---------------------------------------------------------------- news

def news_events(store, ar: pd.DataFrame, min_relevance: float = 0.5) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT h.id, h.ticker, h.title, h.source, h.published, s.relevance, s.score, s.duplicate_of, "
        "s.lang, s.scored_at FROM headlines h JOIN scores s ON s.headline_id = h.id", store.conn)
    if not len(df):
        return df
    df = df.sort_values("scored_at", ascending=False).drop_duplicates("id")   # one score per headline
    df = df[(df["relevance"] >= min_relevance) & df["duplicate_of"].isna() & (df["published"] != "")]
    days = ar.index
    rows = []
    for _, h in df.iterrows():
        tk = h["ticker"]
        if tk not in ar.columns:
            continue
        i = event_index(days, h["published"])
        if i is None:
            rows.append({**h.to_dict(), "day0": None, "d_1": np.nan, "d0": np.nan, "d1": np.nan, "d1_5": np.nan})
            continue
        s = ar[tk].to_numpy(dtype=float)
        rows.append({**h.to_dict(), "day0": days[i].date().isoformat(),
                     "d_1": window_sum(s, i, -1, -1), "d0": window_sum(s, i, 0, 0),
                     "d1": window_sum(s, i, 1, 1), "d1_5": window_sum(s, i, 1, 5)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- the whole study

def build_quarters(cache, tmap: dict, tickers: list[str], since: str, fetch: bool, log=print) -> pd.DataFrame:
    from marketmood.eps import add_sue, quarterly_eps
    frames = []
    for tk in tickers:
        entry = tmap.get(tk)
        if not entry:
            continue
        cik = entry["cik"]
        try:
            facts = cache.company_facts(cik) if fetch else cache.cached(f"facts_{cik}.json")
            if not facts:
                log(f"  {tk}: no saved SEC data (run without --offline)")
                continue
            q = add_sue(quarterly_eps(facts))
            q = q[q["end"].astype(str) >= since]
            q = match_announcements(q, announcement_filings(cache, cik, since, fetch))
        except Exception as e:
            log(f"  {tk}: {type(e).__name__}: {str(e)[:80]}")
            continue
        q["ticker"], q["cik"] = tk, cik
        frames.append(q)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def summarize_earnings(ev: pd.DataFrame) -> dict:
    out = {"n": len(ev)}
    if not len(ev):
        return out
    ev = ev.copy()
    ev["sue_c"] = clip_sue(ev["sue"])
    main = ev[ev["date_source"] == "8-K"]
    three = ([-np.inf, -0.5, 0.5, np.inf], ["bad (≤ −0.5)", "in line", "good (≥ 0.5)"])
    out["by_source"] = {"8-K": bucket_table(main, "sue", *three)}
    if "reaction_10q" in main:      # same quarters, dated by the 10-Q instead
        alt = main.drop(columns=["reaction", "drift"]).rename(
            columns={"reaction_10q": "reaction", "drift_10q": "drift"})
        out["by_source"]["10-Q"] = bucket_table(alt, "sue", *three)
    out["n_8k"] = len(main)
    out["sue_table"] = bucket_table(main, "sue", SUE_EDGES, SUE_LABELS)
    out["reg_sue"] = {o: ols(main[o], main[["sue_c"]]) for o in ("reaction", "drift")}
    halves = sorted(main["day0"].dropna())
    if halves:
        cut = halves[len(halves) // 2]
        out["halves"] = {f"before {cut}": bucket_table(main[main["day0"] < cut], "sue", SUE_EDGES, SUE_LABELS),
                         f"from {cut}": bucket_table(main[main["day0"] >= cut], "sue", SUE_EDGES, SUE_LABELS)}
        out["cut"] = cut
    if "tone" in main and main["tone"].notna().sum() >= 20:
        t = main[main["tone"].notna()].copy()
        out["n_tone"] = len(t)
        out["tone_table"] = bucket_table(t, "tone", TONE_EDGES, TONE_LABELS)
        X1, X2 = t[["sue_c"]], t[["sue_c", "tone"]]
        out["reg_tone"] = {o: {"sue": ols(t[o], X1), "sue+tone": ols(t[o], X2)} for o in ("reaction", "drift")}
        g = t["guidance"].fillna("none")
        out["guidance_table"] = pd.DataFrame(
            [{"guidance": k, **dict(zip(["n", "reaction", "reaction_t"], mean_t(t.loc[g == k, "reaction"]))),
              **dict(zip(["drift_n", "drift", "drift_t"], mean_t(t.loc[g == k, "drift"])))}
             for k in ["raised", "maintained", "provided", "lowered", "none", "initiated", "withdrawn"]
             if (g == k).sum() >= 3])
        out["tone_dates"] = (t["day0"].min(), t["day0"].max())
    return out


def summarize_news(nv: pd.DataFrame) -> dict:
    out = {"n": len(nv)}
    if not len(nv):
        return out
    out["dates"] = (nv["published"].min(), nv["published"].max())
    out["n_stocks"] = int(nv["ticker"].nunique())
    out["n_d1"] = int(nv["d1"].notna().sum())
    out["n_d1_5"] = int(nv["d1_5"].notna().sum())
    out["table"] = bucket_table(nv, "score", [-1.01, -0.15, 0.15, 1.01], ["negative", "neutral", "positive"],
                                outcomes=("d_1", "d0", "d1", "d1_5"))
    return out


# ---------------------------------------------------------------- saved results (for the dashboard)

def results_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "research")


def save_results(data_dir: str, market: str, events: pd.DataFrame, news: pd.DataFrame,
                 prices_meta: dict, prices_path: str, backtest: dict | None = None) -> None:
    """Keep the event-level data of the last run, so the report can be rebuilt (in any language)."""
    import json
    d = results_dir(data_dir)
    os.makedirs(d, exist_ok=True)
    events.drop(columns=[c for c in ("primary",) if c in events.columns]).to_csv(
        os.path.join(d, f"{market}_earnings.csv"), index=False)
    news.to_csv(os.path.join(d, f"{market}_news.csv"), index=False)
    meta = {"market": market, "prices": prices_meta, "prices_path": prices_path,   # as given (relative to where marketmood runs)
            "updated": dt.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(d, f"{market}_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    bt_path = os.path.join(d, f"{market}_backtest.json")
    if backtest:
        with open(bt_path, "w", encoding="utf-8") as f:
            json.dump(backtest, f)
    elif os.path.exists(bt_path):
        os.remove(bt_path)


def saved_meta(data_dir: str, market: str) -> dict | None:
    import json
    p = os.path.join(results_dir(data_dir), f"{market}_meta.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _read_csv(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype={"accession": object})
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def results_from_saved(data_dir: str, market: str) -> dict | None:
    """The `res` dict for build_research_report, rebuilt from the last saved run (no network)."""
    meta = saved_meta(data_dir, market)
    if meta is None:
        return None
    d = results_dir(data_dir)
    ev = _read_csv(os.path.join(d, f"{market}_earnings.csv"))
    nv = _read_csv(os.path.join(d, f"{market}_news.csv"))
    res = {"prices": meta.get("prices", {}), "updated": meta.get("updated")}
    if len(ev):
        summ = summarize_earnings(ev)
        summ.update(n_stocks=int(ev["ticker"].nunique()), market=market)
        res["earnings"] = summ
    res["news"] = summarize_news(nv) if len(nv) else {"n": 0}
    bt_path = os.path.join(d, f"{market}_backtest.json")
    if os.path.exists(bt_path):
        import json
        with open(bt_path, encoding="utf-8") as f:
            res["backtest"] = json.load(f)
    return res


# ---------------------------------------------------------------- history lookup (dashboard alerts)

def history_for(events: pd.DataFrame, sue: float | None = None, tone: float | None = None) -> dict:
    """What happened after similar announcements in the research data: average reaction (day 0-1),
    drift (day 2-61) and how often the drift beat the market, for the SUE bucket of `sue`
    and the tone bucket of `tone` (US, where past releases were read by the LLM)."""
    out = {}
    if events is None or not len(events):
        return out
    ev = events[events["date_source"] == "8-K"] if "date_source" in events.columns else events

    def describe(part: pd.DataFrame, label: str) -> dict:
        d = part["drift"].dropna()
        n, m, t = mean_t(d)
        return {"bucket": label, "n": int(len(part)), "reaction": mean_t(part["reaction"])[1],
                "drift": m, "drift_t": t, "beat": float((d > 0).mean()) if len(d) else None}

    if sue is not None and not pd.isna(sue):
        b = pd.cut(pd.Series([sue]), SUE_EDGES, labels=SUE_LABELS)[0]
        part = ev[pd.cut(ev["sue"], SUE_EDGES, labels=SUE_LABELS) == b]
        if len(part) >= 20:
            out["sue"] = describe(part, str(b))
    if tone is not None and "tone" in ev and ev["tone"].notna().sum() >= 20:
        b = pd.cut(pd.Series([tone]), TONE_EDGES, labels=TONE_LABELS)[0]
        t = ev[ev["tone"].notna()]
        part = t[pd.cut(t["tone"], TONE_EDGES, labels=TONE_LABELS) == b]
        if len(part) >= 10:
            out["tone"] = describe(part, str(b))
    return out
