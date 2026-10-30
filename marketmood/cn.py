"""
China markets: Shanghai, Shenzhen, Beijing (A-shares) and Hong Kong.

Data sources (all free, checked with tools/china_probe.py on 2026-10-28):
  news           AKShare stock_news_em (Eastmoney), A-share and HK codes; plus Google News
                 in Chinese (by company name) and, for HK, Yahoo Finance RSS
  announcements  Eastmoney announcement API: list + full text (no PDF parsing needed)
  EPS history    A-shares: AKShare stock_financial_abstract (Sina), year-to-date totals
                 HK:       AKShare stock_financial_hk_analysis_indicator_em (Eastmoney)
  forecasts      A-shares: AKShare stock_yjyg_em (业绩预告: companies pre-announce profit changes)

AKShare needs Python 3.11+:  pip install akshare
These endpoints are not official APIs and can change; every call fails with a clear
message instead of crashing the whole run.

Ticker formats accepted: 600519, 600519.SH, 600519.SS, 000001.SZ, 430047.BJ,
700, 0700.HK, 00700. Stored as 600519.SH / 000001.SZ / 920xxx.BJ / 00700.HK.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
ANN_LIST = "https://np-anotice-stock.eastmoney.com/api/security/ann"
ANN_TEXT = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
MAX_CHARS = 15000


class CNError(RuntimeError):
    pass


# ---------------------------------------------------------------- codes
def parse(ticker: str) -> dict | None:
    """'600519' -> {'code': '600519', 'market': 'SH', 'symbol': '600519.SH'}; None if not Chinese."""
    t = str(ticker).strip().upper()
    m = re.fullmatch(r"(\d{1,6})(?:\.(SH|SS|SZ|BJ|HK))?", t)
    if not m:
        return None
    digits, suffix = m.group(1), m.group(2)
    if suffix == "SS":
        suffix = "SH"
    if suffix == "HK" or (suffix is None and len(digits) <= 5):
        code = digits.zfill(5)
        return {"code": code, "market": "HK", "symbol": f"{code}.HK"}
    if len(digits) != 6:
        return None
    if suffix is None:
        if digits.startswith(("92", "4", "8")):
            suffix = "BJ"
        elif digits.startswith(("6", "9")):
            suffix = "SH"
        else:
            suffix = "SZ"
    return {"code": digits, "market": suffix, "symbol": f"{digits}.{suffix}"}


def is_cn(ticker: str) -> bool:
    return parse(ticker) is not None


def canonical(ticker: str) -> str:
    info = parse(ticker)
    return info["symbol"] if info else str(ticker).strip().upper()


def _ak():
    try:
        import akshare as ak
    except ImportError:
        raise CNError("China markets need AKShare (Python 3.11+): pip install akshare")
    return ak


# ---------------------------------------------------------------- small disk cache
class CNCache:
    def __init__(self, data_dir: str):
        self.dir = os.path.join(data_dir, "cn")
        os.makedirs(self.dir, exist_ok=True)
        self.names_path = os.path.join(self.dir, "names.json")

    def _path(self, name):
        return os.path.join(self.dir, name)

    def load(self, name, max_age_hours=None):
        p = self._path(name)
        if not os.path.exists(p):
            return None
        if max_age_hours is not None and time.time() - os.path.getmtime(p) > max_age_hours * 3600:
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def save(self, name, data):
        with open(self._path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)

    def names(self) -> dict:
        return self.load("names.json") or {}

    def set_name(self, symbol: str, name: str):
        names = self.names()
        if name and names.get(symbol) != name:
            names[symbol] = name
            self.save("names.json", names)


# ---------------------------------------------------------------- announcements
def announcements(info: dict, page_size: int = 50, page_index: int = 1) -> list[dict]:
    """Recent announcements, newest first: art_code, title, date, column, name."""
    r = _em_get(ANN_LIST, {
        "sr": -1, "page_size": page_size, "page_index": page_index,
        "ann_type": "H" if info["market"] == "HK" else "A",
        "client_source": "web", "stock_list": info["code"], "f_node": 0, "s_node": 0}, timeout=20)
    items = ((r.json() or {}).get("data") or {}).get("list") or []
    out = []
    for it in items:
        codes = it.get("codes") or [{}]
        cols = it.get("columns") or [{}]
        out.append({"art_code": it.get("art_code"), "title": it.get("title") or "",
                    "date": str(it.get("notice_date") or "")[:10],
                    "column": cols[0].get("column_name") or "",
                    "name": codes[0].get("short_name") or ""})
    return out


class Blocked(CNError):
    """Eastmoney keeps refusing connections: too many requests, wait a while."""


_em_lock = threading.Lock()
_em_last = [0.0]
EM_GAP = 0.6          # seconds between requests to Eastmoney's announcement service


def _em_get(url: str, params: dict, timeout: int = 30):
    """GET from Eastmoney one request at a time (even from several threads), with retries.
    Eastmoney resets connections when requests come too fast; back off instead of hammering it."""
    last_error = None
    for attempt in range(4):
        with _em_lock:
            wait = EM_GAP - (time.time() - _em_last[0])
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(url, params=params, headers=UA, timeout=timeout)
                r.raise_for_status()
                return r
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
            finally:
                _em_last[0] = time.time()
        time.sleep(3 * 2 ** attempt)                 # 3, 6, 12, 24 s (outside the lock)
    raise Blocked(f"Eastmoney is refusing connections ({type(last_error).__name__}); "
                  f"wait 15-30 minutes and run again — finished work is kept")


def announcement_text(art_code: str) -> tuple[str, str]:
    """(text, pdf_url) of one announcement."""
    r = _em_get(ANN_TEXT, {"art_code": art_code, "client_source": "web", "page_index": 1})
    d = (r.json() or {}).get("data") or {}
    text = re.sub(r"[ \t　]+", " ", d.get("notice_content") or "")
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text[:MAX_CHARS], d.get("attach_url") or ""


def lookup_name(info: dict) -> str | None:
    """Company short name, taken from its announcements (works for A and HK)."""
    for a in announcements(info, page_size=1):
        if a["name"]:
            return a["name"]
    return None


def resolve_name(info: dict, cache: CNCache) -> str:
    name = cache.names().get(info["symbol"])
    if name:
        return name
    try:
        name = lookup_name(info)
    except Exception:
        name = None
    if name:
        cache.set_name(info["symbol"], name)
        return name
    return info["symbol"]


EARN_WORDS = ("季度报告", "半年度报告", "年度报告", "年报", "业绩快报", "业绩预告",
              "業績", "业绩公告", "中期報告", "年度報告", "季度業績", "results")
SKIP_WORDS = ("说明会", "說明會", "会议", "會議", "召开", "召開", "日期", "更正", "英文", "审计报告",
              "内部控制", "社会责任", "ESG", "可持续", "董事会", "董事會")


def pick_earnings_announcement(items: list[dict]) -> dict | None:
    """The newest earnings document; on the same day prefer a summary (摘要), flash report
    (快报) or quarterly report over a 200-page annual report."""
    cands = []
    for a in items:
        text = a["title"] + " " + a["column"]
        if any(w in text for w in EARN_WORDS) and not any(w in a["title"] for w in SKIP_WORDS):
            cands.append(a)
    if not cands:
        return None
    newest = max(a["date"] for a in cands)
    same_day = [a for a in cands if a["date"] == newest]

    def rank(a):
        t = a["title"] + a["column"]
        if "摘要" in t or "快报" in t or "預告" in t or "预告" in t:
            return 0
        if "季度" in t or "業績" in t or "业绩" in t:
            return 1
        return 2
    return sorted(same_day, key=rank)[0]


# ---------------------------------------------------------------- news
def _eastmoney_news(info: dict, name: str, limit: int) -> list[dict]:
    df = _ak().stock_news_em(symbol=info["code"])
    items = []
    if df is None or df.empty:
        return items
    for _, r in df.iterrows():
        title = str(r.get("新闻标题") or "").strip()
        if title:
            items.append({"title": title, "link": str(r.get("新闻链接") or ""),
                          "published": str(r.get("发布时间") or "")[:10],
                          "source": "eastmoney", "summary": str(r.get("新闻内容") or "")[:150]})
    return items


def _google_news_zh(info: dict, name: str, limit: int) -> list[dict]:
    """Google News in Chinese, searched by the company's Chinese name."""
    from marketmood.news import parse_rss
    if not name or name == info["symbol"]:
        return []
    r = requests.get("https://news.google.com/rss/search",
                     params={"q": f'"{name}"', "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
                     headers=UA, timeout=20)
    r.raise_for_status()
    items = parse_rss(r.text, "google", limit)
    for it in items:
        it["title"] = it["title"].rsplit(" - ", 1)[0]
    return items


def _yahoo_hk(info: dict, name: str, limit: int) -> list[dict]:
    """Yahoo Finance RSS for Hong Kong stocks (Yahoo uses 4-digit codes: 0700.HK)."""
    from marketmood.news import parse_rss
    if info["market"] != "HK":
        return []
    sym = f"{int(info['code']):04d}.HK"
    r = requests.get(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US",
                     headers=UA, timeout=20)
    r.raise_for_status()
    return parse_rss(r.text, "yahoo", limit)


NEWS_SOURCES = [("eastmoney", _eastmoney_news), ("google", _google_news_zh), ("yahoo", _yahoo_hk)]


def fetch_headlines(info: dict, limit: int = 20, name: str | None = None) -> tuple[list[dict], list[str]]:
    """Merges all sources (newest first), drops exact repeats and near-identical titles.
    Eastmoney items carry a 'summary' (first ~150 characters of the article)."""
    from difflib import SequenceMatcher
    from marketmood.news import normalize

    collected, problems = [], []
    for source_name, source in NEWS_SOURCES:
        try:
            got = source(info, name or "", limit)
        except CNError as e:
            problems.append(str(e))
            continue
        except Exception as e:
            problems.append(f"{source_name}: {type(e).__name__}: {str(e)[:80]}")
            continue
        collected += got
    collected.sort(key=lambda it: it.get("published") or "", reverse=True)

    kept, keys = [], []
    for it in collected:
        key = normalize(it["title"]) or it["title"]
        # exact repeats, or near-identical wording (>= 0.9): same story from another source.
        # Looser matches are left to the LLM (duplicate_of), which can tell "rises" from "falls".
        if any(key == k or (len(key) > 8 and SequenceMatcher(None, key, k).ratio() >= 0.9) for k in keys):
            continue
        keys.append(key)
        kept.append(it)
        if len(kept) >= limit:
            break
    if not kept and not problems:
        problems.append("0 items from all sources")
    return kept, problems


# ---------------------------------------------------------------- EPS history
def _num(v):
    try:
        x = float(v)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


def _available_date_a(end: pd.Timestamp) -> pd.Timestamp:
    """Legal deadline for an A-share report: the latest date it can become public.
    Used instead of the real filing date (not in this data) so backtests never peek ahead."""
    if end.month == 3:
        return pd.Timestamp(end.year, 4, 30)
    if end.month == 6:
        return pd.Timestamp(end.year, 8, 31)
    if end.month == 9:
        return pd.Timestamp(end.year, 10, 31)
    return pd.Timestamp(end.year + 1, 4, 30)


def decumulate(cum: pd.DataFrame) -> pd.DataFrame:
    """cum: columns start (fiscal year start), end, value (year-to-date). Returns single-period
    values: the first report of a fiscal year as is, later ones minus the previous report."""
    rows = []
    for _, g in cum.sort_values("end").groupby("start"):
        prev_end, prev_val = None, None
        for _, r in g.iterrows():
            # fy_start: the fiscal year start of the REPORT that published this number. A Q4
            # derived from an annual report only becomes known when the annual report is out.
            if prev_end is None:
                # first report of the fiscal year: already a single period (e.g. Q1); if the data
                # starts later in the year it stays a longer period (e.g. Jan-Jun)
                rows.append({"start": r["start"], "end": r["end"], "eps": r["value"], "derived": False,
                             "fy_start": r["start"]})
            else:
                rows.append({"start": prev_end + pd.Timedelta(days=1), "end": r["end"],
                             "eps": r["value"] - prev_val, "derived": True, "fy_start": r["start"]})
            prev_end, prev_val = r["end"], r["value"]
    return pd.DataFrame(rows)


def eps_history_a(code: str) -> pd.DataFrame:
    df = _ak().stock_financial_abstract(symbol=code)
    row = df[df["指标"].astype(str).str.contains("基本每股收益")]
    if row.empty:
        row = df[df["指标"].astype(str).str.contains("每股收益")]
    if row.empty:
        return _empty_eps()
    row = row.iloc[0]
    recs = []
    for col in df.columns:
        if re.fullmatch(r"\d{8}", str(col)):
            v = _num(row[col])
            if v is not None:
                end = pd.Timestamp(str(col))
                recs.append({"start": pd.Timestamp(end.year, 1, 1), "end": end, "value": v})
    if not recs:
        return _empty_eps()
    q = decumulate(pd.DataFrame(recs))
    q["filed"] = q["end"].map(_available_date_a)
    return _finish(q)


def eps_history_hk(code: str) -> pd.DataFrame:
    df = _ak().stock_financial_hk_analysis_indicator_em(symbol=code, indicator="报告期")
    recs = []
    for _, r in df.iterrows():
        v = _num(r.get("BASIC_EPS"))
        if v is None:
            continue
        recs.append({"start": pd.Timestamp(str(r.get("START_DATE"))[:10]),
                     "end": pd.Timestamp(str(r.get("REPORT_DATE"))[:10]), "value": v})
    if not recs:
        return _empty_eps()
    q = decumulate(pd.DataFrame(recs))
    # HK listing rules: interim results within 2 months, annual results within 3 months of the
    # period end. Judged by the length of the REPORT (fiscal-year start to end), not of the derived
    # single period: a Q4 obtained as "annual minus 9 months" waits for the annual report.
    q["filed"] = [e + pd.Timedelta(days=90 if (e - fs).days > 300 else 60)
                  for fs, e in zip(q["fy_start"], q["end"])]
    return _finish(q)


def _empty_eps() -> pd.DataFrame:
    return pd.DataFrame(columns=["start", "end", "eps", "filed", "fiscal", "q4_derived"])


def _finish(q: pd.DataFrame) -> pd.DataFrame:
    q = q.sort_values("end").drop_duplicates("end").reset_index(drop=True)
    q["fiscal"] = [f"{e.year} {e.month:02d}" for e in q["end"]]
    q["q4_derived"] = q["derived"].astype(bool)
    return q[["start", "end", "eps", "filed", "fiscal", "q4_derived"]]


EPS_CACHE_VERSION = 2       # bump when the EPS rules change, so saved files are recomputed


def eps_cache_name(symbol: str) -> str:
    return f"eps_v{EPS_CACHE_VERSION}_{symbol}.json"


def eps_history(info: dict, cache: CNCache, max_age_hours: float = 24) -> pd.DataFrame:
    """Cached on disk (cn/eps_v<N>_<symbol>.json)."""
    name = eps_cache_name(info["symbol"])
    data = cache.load(name, max_age_hours)
    if data is None:
        q = eps_history_hk(info["code"]) if info["market"] == "HK" else eps_history_a(info["code"])
        data = [{k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v) for k, v in r.items()}
                for r in q.drop(columns=["fy_start"], errors="ignore").to_dict("records")]
        cache.save(name, data)
    return eps_from_records(data)


def eps_from_records(data: list[dict]) -> pd.DataFrame:
    if not data:
        return _empty_eps()
    q = pd.DataFrame(data)
    for col in ("start", "end", "filed"):
        q[col] = pd.to_datetime(q[col])
    q["q4_derived"] = q["q4_derived"].astype(bool)
    return q


# ---------------------------------------------------------------- 业绩预告 (A-shares)
def _recent_period_ends(today: dt.date, n: int = 3) -> list[str]:
    ends, y = [], today.year
    for year in (y, y - 1):
        for md in ("1231", "0930", "0630", "0331"):
            d = f"{year}{md}"
            if dt.datetime.strptime(d, "%Y%m%d").date() <= today + dt.timedelta(days=120):
                ends.append(d)
    return sorted(set(ends), reverse=True)[:n]


def latest_forecast(info: dict, cache: CNCache, offline: bool = False) -> dict | None:
    """Most recent profit pre-announcement (业绩预告) for an A-share, or None.
    offline=True only looks at files already saved (used when a page loads)."""
    if info["market"] == "HK":
        return None
    best = None
    for period in _recent_period_ends(dt.date.today()):
        name = f"yjyg_{period}.json"
        data = cache.load(name, None if offline else 12)
        if data is None:
            if offline:
                continue
            try:
                df = _ak().stock_yjyg_em(date=period)
            except Exception:
                continue
            data = [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()}
                    for r in df.astype(object).to_dict("records")] if df is not None else []
            cache.save(name, data)
        for r in data:
            if str(r.get("股票代码")) != info["code"]:
                continue
            if "扣除" in str(r.get("预测指标", "")):
                continue          # prefer net profit attributable to shareholders
            cand = {"period": period, "type": r.get("预告类型"), "change_pct": _num(r.get("业绩变动幅度")),
                    "text": str(r.get("业绩变动") or "")[:300], "reason": str(r.get("业绩变动原因") or "")[:300],
                    "date": str(r.get("公告日期") or "")[:10]}
            if best is None or cand["date"] > best["date"]:
                best = cand
    return best


# ---------------------------------------------------------------- one stock's earnings
def earnings_ticker(store, data_dir: str, client, model_id: str, info: dict, name: str, lang: str) -> dict:
    """Same result shape as core.earnings_ticker, plus 'forecast' for A-shares."""
    from marketmood import earnings as er
    from marketmood.llm import LLMError
    from marketmood.eps import add_sue

    cache = CNCache(data_dir)
    row = {"ticker": info["symbol"], "name": name, "read": None, "history": None,
           "forecast": None, "errors": [], "fatal": False}
    try:
        row["history"] = add_sue(eps_history(info, cache))
    except Exception as e:
        row["errors"].append(f"EPS history unavailable ({type(e).__name__}: {str(e)[:120]})")
    try:
        row["forecast"] = latest_forecast(info, cache)
    except Exception as e:
        row["errors"].append(f"forecast unavailable ({type(e).__name__})")
    try:
        ann = pick_earnings_announcement(announcements(info))
        if ann and client is not None:
            read_key = f"{model_id}#v{er.READ_VERSION}"
            read = store.earnings_read(ann["art_code"], read_key, lang)
            if read is None:
                text, url = announcement_text(ann["art_code"])
                if text:
                    result = er.read_release(client, name, info["symbol"], text, lang,
                                             doc_kind="earnings report or announcement")
                    result["doc_title"] = ann["title"][:120]
                    store.save_earnings_read(ann["art_code"], read_key, lang, info["symbol"],
                                             ann["date"], url, result)
                    read = {**result, "url": url, "filed": ann["date"]}
            row["read"] = read
    except LLMError as e:
        from marketmood.core import is_fatal
        row["errors"].append(f"report not read ({e})")
        row["fatal"] = is_fatal(e)
    except Exception as e:
        row["errors"].append(f"report not read ({type(e).__name__}: {str(e)[:120]})")
    return row
