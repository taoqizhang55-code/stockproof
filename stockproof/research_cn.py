"""
China (A-share) data for the research study, via AKShare (Eastmoney + Sina).

Same question as the US study: does the earnings surprise move the stock, and does it keep
moving afterwards? Built point-in-time from tables that cover ALL A-shares per report period,
so a whole index costs a few hundred requests, not thousands:

  - 业绩报表 (stock_yjbb_em)    year-to-date EPS of every company for one report period
  - 预约披露 (stock_yysj_em)    the ACTUAL disclosure date of each company's report
  - 业绩快报 (stock_yjkb_em)    preliminary results; when published earlier, that is the news day

Single quarters come from de-cumulating the year-to-date EPS (Q2 = H1 − Q1 ...), then SUE as
for US stocks. The legal deadline (Apr 30 / Aug 31 / Oct 31 / Apr 30) is kept as the "late date"
comparison, like the 10-Q date for US stocks.

Dates have no time of day. Most A-share reports come out after the close, so day 0 is the date
itself and the reaction window covers day 0 and day 1; the drift (day 2 on) is safe either way.

Universe: by default the current CSI 300 members (survivorship bias: today's members).
"""

from __future__ import annotations

import datetime as dt
import os
import time

import numpy as np
import pandas as pd

from stockproof import cn

BENCH_A = "CSI300"


def period_ends(since: str, today: dt.date | None = None) -> list[str]:
    """Report period ends (YYYYMMDD) from the year of `since` up to today."""
    today = today or dt.date.today()
    out = []
    for y in range(int(since[:4]), today.year + 1):
        for md in ("0331", "0630", "0930", "1231"):
            d = dt.date(y, int(md[:2]), int(md[2:]))
            if d <= today:
                out.append(f"{y}{md}")
    return out


def _col(df: pd.DataFrame, *keys: str) -> str | None:
    for k in keys:
        if k in df.columns:
            return k
    for k in keys:
        for c in df.columns:
            if k in str(c):
                return c
    return None


def _code6(v) -> str:
    s = str(v).strip().split(".")[0]
    return s.zfill(6) if s.isdigit() else s


def period_table(cache: cn.CNCache, kind: str, date: str, max_age_days: float = 2) -> list[dict]:
    """One report period of one table, as [{code, eps, date}], cached in cn/research/.
    Periods older than ~a year never change, so they are kept for good."""
    name = f"research_{kind}_{date}.json"
    old = (dt.date.today() - dt.date(int(date[:4]), int(date[4:6]), int(date[6:]))).days > 400
    data = cache.load(name, None if old else max_age_days * 24)
    if data is not None:
        return data
    ak = cn._ak()
    calls = {"yjbb": lambda: ak.stock_yjbb_em(date=date),
             "yysj": lambda: ak.stock_yysj_em(symbol="沪深A股", date=date),
             "yjkb": lambda: ak.stock_yjkb_em(date=date)}
    if kind not in calls:
        raise ValueError(kind)
    for attempt in range(3):              # Eastmoney sometimes drops a connection mid-way
        try:
            df = calls[kind]()
            break
        except Exception as e:
            if "no data" in str(e).lower() or attempt == 2:
                if isinstance(e, (KeyError, TypeError)):
                    df = None             # AKShare raises these when a period has no rows yet
                    break
                raise
            time.sleep(2 * (attempt + 1))
    out = []
    if df is not None and len(df):
        c_code = _col(df, "股票代码")
        c_eps = _col(df, "每股收益")
        c_date = (_col(df, "实际披露时间") if kind == "yysj" else _col(df, "公告日期", "最新公告日期"))
        for _, r in df.iterrows():
            rec = {"code": _code6(r[c_code])}
            if c_eps is not None:
                v = pd.to_numeric(r[c_eps], errors="coerce")
                rec["eps"] = None if pd.isna(v) else float(v)
            if c_date is not None:
                d = pd.to_datetime(r[c_date], errors="coerce")
                rec["date"] = None if pd.isna(d) else d.strftime("%Y-%m-%d")
            out.append(rec)
    cache.save(name, out)
    return out


def build_quarters_cn(cache: cn.CNCache, codes: list[str], since: str, log=print,
                      tables: dict | None = None) -> pd.DataFrame:
    """Quarterly EPS, SUE and announcement dates for 6-digit A-share codes.
    `tables` (for tests): {(kind, date): records} instead of downloading."""
    from stockproof.eps import add_sue
    want = set(codes)
    # one extra year before `since` so SUE has history from the start
    start = f"{int(since[:4]) - 3}0101"
    cum, dates, kb = [], {}, {}
    periods = period_ends(start)
    for k, date in enumerate(periods, 1):
        try:
            def get(kind):
                return tables[(kind, date)] if tables is not None else period_table(cache, kind, date)
            end = pd.Timestamp(date)
            for r in get("yjbb"):
                if r["code"] in want and r.get("eps") is not None:
                    cum.append({"code": r["code"], "start": pd.Timestamp(end.year, 1, 1), "end": end,
                                "value": r["eps"]})
            for r in get("yysj"):
                if r["code"] in want and r.get("date"):
                    dates[(r["code"], date)] = r["date"]
            for r in get("yjkb"):
                if r["code"] in want and r.get("date"):
                    kb[(r["code"], date)] = r["date"]
        except Exception as e:
            log(f"  period {date}: {type(e).__name__}: {str(e)[:80]}")
        if tables is None and k % 8 == 0:
            log(f"  report periods: {k}/{len(periods)}")
    if not cum:
        return pd.DataFrame()
    frames = []
    allcum = pd.DataFrame(cum)
    for code, g in allcum.groupby("code"):
        q = cn.decumulate(g[["start", "end", "value"]])
        q = q[(q["end"] - q["start"]).dt.days.between(80, 100)].sort_values("end").reset_index(drop=True)
        if not len(q):
            continue
        q = add_sue(q)
        q["filed"] = q["end"].map(cn._available_date_a)          # legal deadline: the "late" date
        key = q["end"].dt.strftime("%Y%m%d")
        # The news day for a single quarter is when the REPORT containing it came out:
        # a Q4 derived from the annual report is news on the annual report's date.
        actual = [dates.get((code, k)) for k in key]
        quick = [kb.get((code, k)) for k in key]
        q["ann_date"] = [min([d for d in (a, b) if d]) if (a or b) else None for a, b in zip(actual, quick)]
        q["date_source"] = ["actual" if d else "none" for d in q["ann_date"]]
        q["ann_after_close"] = False
        q["accession"] = None
        info = cn.parse(code)
        q["ticker"] = info["symbol"] if info else code
        q["cik"] = None
        frames.append(q[q["end"].astype(str) >= since])
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(out):
        out["ann_date"] = out["ann_date"].fillna(out["filed"].dt.strftime("%Y-%m-%d"))
    return out


def index_members(index: str = "000300") -> list[str]:
    """Current members of a CSI index (6-digit codes)."""
    ak = cn._ak()
    try:
        df = ak.index_stock_cons_csindex(symbol=index)
        col = _col(df, "成分券代码")
    except Exception:
        df = ak.index_stock_cons(symbol=index)
        col = _col(df, "品种代码")
    return sorted({_code6(c) for c in df[col]})


def _close_series(df: pd.DataFrame) -> pd.Series:
    c_date = _col(df, "日期", "date")
    c_close = _col(df, "收盘", "close")
    s = pd.Series(pd.to_numeric(df[c_close], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df[c_date]), dtype=float)
    return s[~s.index.duplicated()].sort_index()


def download_prices_cn(codes: list[str], since: str, path: str, log=print) -> pd.DataFrame:
    """Back-adjusted (后复权) daily closes for A-shares + CSI 300, saved as one CSV.
    Columns are stockproof tickers (600519.SH ...)."""
    ak = cn._ak()
    start = since.replace("-", "")
    cols, failed = {}, []
    for k, code in enumerate(codes, 1):
        info = cn.parse(code)
        if not info or info["market"] == "HK":
            continue
        s = None
        for attempt in ("em", "sina"):
            try:
                if attempt == "em":
                    df = ak.stock_zh_a_hist(symbol=info["code"], period="daily", start_date=start,
                                            end_date="20500101", adjust="hfq")
                else:
                    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[info["market"]]
                    df = ak.stock_zh_a_daily(symbol=prefix + info["code"], start_date=start,
                                             end_date="20500101", adjust="hfq")
                if df is not None and len(df):
                    s = _close_series(df)
                    break
            except Exception:
                time.sleep(0.5)
        if s is None:
            failed.append(code)
        else:
            cols[info["symbol"]] = s
        if k % 25 == 0:
            log(f"  prices: {k}/{len(codes)}")
    try:
        idx = _close_series(ak.stock_zh_index_daily(symbol="sh000300"))
        cols[BENCH_A] = idx[idx.index >= pd.Timestamp(since)]
    except Exception as e:
        log(f"  CSI 300 not available ({type(e).__name__}); using the equal-weighted average instead")
    if failed:
        log(f"  no prices for {len(failed)} stocks: {', '.join(failed[:10])}{' …' if len(failed) > 10 else ''}")
    df = pd.DataFrame(cols).sort_index()       # Chinese markets close before a US morning: no partial day
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_csv(path)
    return df


def summarize_by_actual(ev: pd.DataFrame) -> pd.DataFrame:
    """Rename China date labels to the generic ones the summary uses."""
    ev = ev.copy()
    ev["date_source"] = ev["date_source"].map({"actual": "8-K", "none": "10-Q"}).fillna("10-Q")
    return ev


# ---------------------------------------------------------------- LLM readings of past reports

PERIOD_WORDS = {3: ("第一季度", "一季度"), 6: ("半年度", "半年报", "中期"), 9: ("第三季度", "三季度"),
                12: ("年度报告", "年报", "年度业绩")}
DOC_KIND = "earnings report or announcement"
# Other "reports" filed around results time: banks' Pillar 3 / capital and liquidity disclosures,
# fund-use and assurance reports, audit or review opinions.
NOT_RESULTS = ("支柱", "资本充足", "流动性", "募集资金", "鉴证", "审核", "审阅", "核查", "专项说明",
               "提示性", "更正", "补充", "说明会", "董事会", "监事会")


def _end_key(ticker: str, end) -> str:
    return f"{ticker}|{pd.Timestamp(end).strftime('%Y-%m-%d')}"


def announcements_since(info: dict, since: str, cache: cn.CNCache, max_pages: int = 40) -> list[dict]:
    """All announcements back to `since` (newest first), cached for a day in cn/ann_<symbol>.json."""
    name = f"ann_{info['symbol']}.json"
    saved = cache.load(name, 24)
    if saved and saved.get("since", "9999") <= since:
        return saved["items"]
    items = []
    for page in range(1, max_pages + 1):
        batch = cn.announcements(info, page_size=100, page_index=page)
        if not batch:
            break
        items.extend(batch)
        if min(a["date"] for a in batch if a["date"]) < since:
            break
        time.sleep(0.2)
    cache.save(name, {"since": since, "items": items})
    return items


def valid_report_title(t: str) -> bool:
    """The report itself (or its summary / flash report), not a notice that merely mentions it,
    e.g. "关于计提2025年第三季度减值准备的公告" (an impairment notice) or "关于召开…业绩说明会"."""
    body = t.split(":", 1)[-1].split("：", 1)[-1]          # drop the "公司名:" prefix
    if body.startswith("关于") or "公告" in body and "报告" not in body:
        return False
    if any(w in body for w in NOT_RESULTS):
        return False
    return "报告" in body or "业绩快报" in body


def report_doc_for(items: list[dict], end, ann_date: str) -> dict | None:
    """The document that published period `end`: dated within a few days of `ann_date`, its title
    naming the period's year and type (or 业绩快报). Summaries (摘要) and flash reports are preferred
    over full reports: same numbers, far shorter."""
    end = pd.Timestamp(end)
    day = pd.Timestamp(ann_date)
    year = str(end.year)
    words = PERIOD_WORDS[end.month]
    cands = []
    for a in items:
        if not a.get("date"):
            continue
        d = pd.Timestamp(a["date"])
        if not (day - pd.Timedelta(days=2) <= d <= day + pd.Timedelta(days=3)):
            continue
        t = a["title"]
        if year not in t or any(w in t for w in cn.SKIP_WORDS):
            continue
        quick = "业绩快报" in t
        if end.month == 12 and "半年" in t:
            continue                                      # "半年度报告" also contains "年度报告"
        if not (quick or any(w in t for w in words)):
            continue
        if not valid_report_title(t):
            continue
        if "预告" in t:
            continue                                      # a forecast is not the result
        rank = 0 if ("摘要" in t or quick) else 1
        cands.append((rank, abs((d - day).days), a))
    if not cands:
        return None
    return sorted(cands, key=lambda c: (c[0], c[1]))[0][2]


def find_docs(cache: cn.CNCache, events: pd.DataFrame, per_ticker: int, log=print) -> dict:
    """{'600519.SH|2025-12-31': {art_code, title, date, name}} for the newest `per_ticker` quarters
    of each stock; merged into cn/research_docs.json."""
    docs = {k: v for k, v in (cache.load("research_docs.json") or {}).items()
            if valid_report_title(v.get("title", ""))}             # drops matches from older rules
    ev = events.dropna(subset=["ann_date"]).copy()
    ev["_end"] = pd.to_datetime(ev["end"])
    ev = ev.sort_values("_end", ascending=False).groupby("ticker").head(per_ticker)
    tickers = sorted(ev["ticker"].unique())
    for k, (tk, g) in enumerate(ev.groupby("ticker"), 1):
        todo = [r for _, r in g.iterrows() if _end_key(tk, r["_end"]) not in docs]
        if not todo:
            continue
        info = cn.parse(tk)
        since = (pd.to_datetime(g["ann_date"]).min() - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
        try:
            items = announcements_since(info, since, cache)
        except Exception as e:
            log(f"  {tk}: announcements unavailable ({type(e).__name__})")
            continue
        for r in todo:
            a = report_doc_for(items, r["_end"], r["ann_date"])
            if a:
                docs[_end_key(tk, r["_end"])] = {"art_code": a["art_code"], "title": a["title"],
                                                 "date": a["date"], "name": a.get("name", "")}
        if k % 25 == 0:
            log(f"  documents found for {k}/{len(tickers)} stocks")
            cache.save("research_docs.json", docs)
    cache.save("research_docs.json", docs)
    return docs


def attach_docs(events: pd.DataFrame, cache: cn.CNCache) -> pd.DataFrame:
    """Puts each quarter's document id in the `accession` column (so readings can be joined)."""
    docs = cache.load("research_docs.json") or {}
    ev = events.copy()
    ev["accession"] = [(docs.get(_end_key(t, e)) or {}).get("art_code") for t, e in zip(ev["ticker"], ev["end"])]
    return ev


def backfill_reads_cn(store, client, model_id: str, events: pd.DataFrame, cache: cn.CNCache,
                      per_ticker: int, lang: str = "en", log=print, workers: int = 4) -> dict:
    """Read the newest `per_ticker` reports of each stock with the LLM (saved; never paid twice)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from stockproof import earnings as er
    from stockproof.core import is_fatal
    read_key = f"{model_id}#v{er.READ_VERSION}"
    docs = find_docs(cache, events, per_ticker, log)
    ev = events.copy()
    ev["_end"] = pd.to_datetime(ev["end"])
    ev = ev.sort_values("_end", ascending=False).groupby("ticker").head(per_ticker)
    jobs, missing = [], 0
    for _, r in ev.iterrows():
        d = docs.get(_end_key(r["ticker"], r["_end"]))
        if not d:
            missing += 1
        elif store.earnings_read(d["art_code"], read_key, lang) is None:
            jobs.append((r["ticker"], d))
    stats = {"read": 0, "cached": len(ev) - missing - len(jobs), "no_document": missing, "failed": 0}
    log(f"  {len(ev)} reports: {len(jobs)} to read, {stats['cached']} already read, "
        f"{missing} without a matching document")

    def work(job):
        tk, d = job
        text, url = cn.announcement_text(d["art_code"])
        if not text:
            return job, None, url
        res = er.read_release(client, d.get("name") or tk, tk, text, lang, doc_kind=DOC_KIND)
        res["doc_title"] = d["title"][:120]
        return job, res, url

    fatal = None
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, j) for j in jobs]
        for k, fut in enumerate(as_completed(futures), 1):
            try:
                (tk, d), res, url = fut.result()
            except Exception as e:
                if fut.cancelled():
                    continue
                stats["failed"] += 1
                if fatal is None:
                    log(f"  [{k}/{len(jobs)}] {type(e).__name__}: {str(e)[:120]}")
                # stop everything if the LLM key is rejected, or if Eastmoney is blocking us:
                # every further request would fail too
                if (is_fatal(e) or isinstance(e, cn.Blocked)) and fatal is None:
                    fatal = e
                    for f in futures:
                        f.cancel()
                continue
            if res is None:
                stats["failed"] += 1
                continue
            store.save_earnings_read(d["art_code"], read_key, lang, tk, d["date"], url, res)
            stats["read"] += 1
            log(f"  [{k}/{len(jobs)}] {tk} {d['date']} {d['title'][:28]}: tone {res['tone']:+.2f}")
    if fatal is not None:
        raise fatal
    return stats
