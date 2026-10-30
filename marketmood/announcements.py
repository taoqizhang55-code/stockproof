"""
Announcement monitor (A-shares and Hong Kong, via Eastmoney).

Company announcements are the most important information source in A-shares, and their titles
are highly standardized ("关于股东减持股份计划的公告", "关于收到上海证券交易所问询函的公告"…).
So the type and importance come from title rules: free, instant and predictable. The LLM is only
used for the important ones: a two-sentence summary and an impact score, read from the full text.

Categories carry a typical direction (+1 usually good for the price, -1 usually bad, 0 unclear);
the LLM's score for the specific announcement can differ (e.g. a small buyback plan).
"""

from __future__ import annotations

import datetime as dt
import json
import re

from marketmood import clock
from marketmood import cn

# (key, importance 3/2/1, typical direction, title patterns). First match wins, so order matters:
# specific risks before generic words ("终止回购" is not a buyback).
RULES = [
    ("delisting_risk", 3, -1, [r"退市", r"\*ST", r"终止上市", r"暂停上市", r"实施其他风险警示", r"delisting"]),
    ("investigation", 3, -1, [r"立案", r"行政处罚", r"刑事", r"留置", r"被调查", r"investigation"]),
    ("regulatory_letter", 3, -1, [r"问询函", r"关注函", r"监管函", r"警示函", r"监管措施", r"纪律处分", r"通报批评"]),
    ("trading_halt", 3, 0, [r"停牌", r"trading halt", r"suspension of trading"]),
    ("restructuring", 3, 0, [r"重大资产重组", r"重大资产", r"吸收合并", r"收购报告书", r"要约收购", r"控制权变更",
                             r"实际控制人.{0,6}变更", r"major transaction", r"very substantial"]),
    ("earnings_warning", 3, 0, [r"业绩预告", r"业绩预亏", r"业绩预增", r"业绩快报", r"profit warning",
                                r"positive profit alert", r"盈利警告", r"盈利预告"]),
    ("insider_selling", 3, -1, [r"减持", r"大宗交易"]),
    ("insider_buying", 2, 1, [r"增持"]),
    ("buyback", 2, 1, [r"(?<!终止)回购.{0,10}(股份|方案|计划|报告书|进展|实施)", r"buy-?back", r"repurchase"]),
    ("lawsuit", 2, -1, [r"诉讼", r"仲裁", r"litigation"]),
    ("pledge_freeze", 2, -1, [r"质押", r"冻结", r"司法拍卖"]),
    ("lockup_expiry", 2, -1, [r"限售股.{0,8}上市流通", r"解除限售", r"解禁"]),
    ("share_issue", 2, -1, [r"非公开发行", r"向特定对象发行", r"定向增发", r"配股", r"可转换公司债券", r"可转债",
                            r"placing", r"rights issue", r"subscription of new shares"]),
    ("management_change", 2, 0, [r"辞职", r"辞任", r"离任", r"resignation", r"change of (director|chief)"]),
    ("big_contract", 2, 1, [r"中标", r"重大合同", r"战略合作", r"framework agreement"]),
    ("incentive", 1, 1, [r"股权激励", r"员工持股", r"限制性股票", r"股票期权", r"share award", r"share option"]),
    ("dividend", 1, 1, [r"利润分配", r"分红", r"派息", r"权益分派", r"dividend"]),
    ("periodic_report", 1, 0, [r"季度报告", r"半年度报告", r"年度报告", r"interim report", r"annual report",
                               r"quarterly report", r"results announcement", r"业绩公告"]),
]
# Paperwork that only accompanies an event (lawyers' opinions, brokers' checks, replies, meeting
# resolutions…) or is routine. Checked FIRST: "律师事务所关于…增持股份的法律意见书" is not a purchase.
NOISE = [r"律师事务所", r"法律意见", r"核查意见", r"专项核查", r"持续督导", r"自查报告", r"的回复", r"之回复",
         r"论证分析", r"会议规则", r"募集说明书", r"上市保荐", r"保荐书", r"独立董事", r"会议决议", r"董事会决议",
         r"监事会决议", r"股东(大)?会(决议|通知|的通知|会议资料)", r"召开.{0,30}(股东|说明会|会议)", r"说明会",
         r"投资者关系", r"章程", r"议事规则", r"管理制度", r"工作细则", r"履职情况", r"内部控制", r"社会责任",
         r"ESG", r"環境、社會", r"可持续发展", r"更正", r"英文", r"H股公告", r"月报表", r"月報表", r"通函",
         r"关联交易预计", r"日常关联交易", r"提示性公告$", r"财务顾问", r"董事会关于本次交易", r"验资",
         r"评级报告", r"可行性分析", r"审核意见", r"前十(大|名)(股东|流通)",
         r"monthly return", r"next day disclosure", r"date of board meeting", r"董事会会议召开日期"]
# Words that turn a matching title into something routine.
NOT_EVENT = {
    "regulatory_letter": [r"不存在", r"未被", r"审核问询", r"注册.{0,6}问询", r"回复", r"回函"],
    "trading_halt": [r"债券", r"转债", r"转股", r"票据", r"可交换"],
    "buyback": [r"限制性股票", r"激励", r"债券", r"注销.{0,6}限制性"],
    "lockup_expiry": [r"限制性股票", r"激励", r"员工持股"],
    "investigation": [r"不存在", r"说明会"],
    "pledge_freeze": [r"解除质押(?!.{0,4}及)"],
}

CATEGORY_NAMES = {
    "en": {"delisting_risk": "delisting / ST risk", "investigation": "investigation / penalty",
           "regulatory_letter": "regulator's letter", "trading_halt": "trading halt", "restructuring": "M&A / restructuring",
           "earnings_warning": "earnings preview", "insider_selling": "shareholder selling",
           "insider_buying": "shareholder buying", "buyback": "buyback", "lawsuit": "lawsuit", "pledge_freeze": "pledge / freeze",
           "lockup_expiry": "lock-up expiry", "share_issue": "new shares / convertible", "management_change": "management change",
           "big_contract": "major contract", "incentive": "stock incentive", "dividend": "dividend",
           "periodic_report": "periodic report", "other": "other"},
    "zh": {"delisting_risk": "退市/ST 风险", "investigation": "立案调查/处罚", "regulatory_letter": "监管问询",
           "trading_halt": "停牌", "restructuring": "重组/收购", "earnings_warning": "业绩预告/快报",
           "insider_selling": "股东减持", "insider_buying": "股东增持", "buyback": "回购", "lawsuit": "诉讼仲裁",
           "pledge_freeze": "质押/冻结", "lockup_expiry": "限售股解禁", "share_issue": "增发/可转债",
           "management_change": "高管变动", "big_contract": "重大合同/中标", "incentive": "股权激励", "dividend": "分红",
           "periodic_report": "定期报告", "other": "其他"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS announcements (
    art_code TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    importance INTEGER NOT NULL,
    direction INTEGER NOT NULL,
    url TEXT,
    first_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ann_ticker ON announcements (ticker, date);
CREATE TABLE IF NOT EXISTS announcement_reads (
    art_code TEXT NOT NULL,
    model TEXT NOT NULL,
    lang TEXT NOT NULL,
    result TEXT NOT NULL,
    read_at TEXT NOT NULL,
    PRIMARY KEY (art_code, model, lang)
);
"""
READ_VERSION = 1


def classify(title: str) -> tuple[str, int, int]:
    """(category, importance 0-3, typical direction). Importance 0 = routine paperwork."""
    t = title.split(":", 1)[-1] if ":" in title[:20] else title       # drop the "公司名:" prefix
    low = t.lower()
    hit = lambda pats: any(re.search(p, t) or re.search(p, low, re.I) for p in pats)
    if hit(NOISE):
        return "other", 0, 0
    for key, imp, direction, pats in RULES:
        if hit(pats) and not hit(NOT_EVENT.get(key, [])):
            return key, imp, direction
    if re.search(r"限制性股票|激励", t):
        return "incentive", 1, 1                  # vesting / cancellation of incentive shares
    if re.search(r"解除质押", t):
        return "pledge_freeze", 1, 1              # pledge released: mildly reassuring
    return "other", 1, 0


def page_url(info: dict, art_code: str) -> str:
    if info["market"] == "HK":
        return f"https://data.eastmoney.com/notices/hk/detail/{info['code']}/{art_code}.html"
    return f"https://data.eastmoney.com/notices/detail/{info['code']}/{art_code}.html"


def ensure_schema(store) -> None:
    store.conn.executescript(SCHEMA)


def fetch(store, ticker: str, days: int = 30) -> int:
    """Save the latest announcements of one stock (newest page only). Returns how many were new."""
    ensure_schema(store)
    info = cn.parse(ticker)
    if not info:
        return 0
    since = (clock.today() - dt.timedelta(days=days)).isoformat()
    now = dt.datetime.now().isoformat(timespec="seconds")
    new = 0
    for a in cn.announcements(info, page_size=100):
        if not a.get("art_code") or not a.get("date") or a["date"] < since:
            continue
        cat, imp, direction = classify(a["title"])
        cur = store.conn.execute(
            "INSERT OR IGNORE INTO announcements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (a["art_code"], info["symbol"], a["date"], a["title"], cat, imp, direction,
             page_url(info, a["art_code"]), now))
        new += cur.rowcount
    store.conn.commit()
    return new


def build_prompt(name: str, ticker: str, title: str, text: str, lang: str) -> str:
    language = "Simplified Chinese" if lang == "zh" else "English"
    return (
        "You are an equity analyst reading a listed company's official announcement.\n"
        f"Company: {name} ({ticker}). Title: {title}\n\n"
        f"--- ANNOUNCEMENT (may be cut off) ---\n{text}\n--- END ---\n\n"
        "Report only what the announcement says.\n"
        "Reply ONLY with JSON:\n"
        f'{{"summary": "at most 2 sentences in {language}, with the key numbers (amounts, share counts, '
        'percentages, dates)",\n'
        ' "impact": -1 to 1 (likely effect on the share price; 0 if routine or unclear),\n'
        f' "why": "one short sentence in {language}"}}'
    )


def read(store, client, model_id: str, art_code: str, name: str, ticker: str, title: str, lang: str) -> dict:
    """LLM summary of one announcement, cached per model and language."""
    ensure_schema(store)
    key = f"{model_id}#a{READ_VERSION}"
    row = store.conn.execute("SELECT result FROM announcement_reads WHERE art_code=? AND model=? AND lang=?",
                             (art_code, key, lang)).fetchone()
    if row:
        return json.loads(row[0])
    text, pdf = cn.announcement_text(art_code)
    data = client.chat_json(build_prompt(name, ticker, title, text[:8000] or title, lang))
    try:
        impact = max(-1.0, min(1.0, float(data.get("impact", 0))))
    except (TypeError, ValueError):
        impact = 0.0
    result = {"summary": str(data.get("summary", ""))[:400], "impact": impact,
              "why": str(data.get("why", ""))[:200], "pdf": pdf}
    store.conn.execute("INSERT OR REPLACE INTO announcement_reads VALUES (?, ?, ?, ?, ?)",
                       (art_code, key, lang, json.dumps(result, ensure_ascii=False),
                        dt.datetime.now().isoformat(timespec="seconds")))
    store.conn.commit()
    return result


def refresh(store, client, model_id: str, tickers: list[str], names: dict, lang: str,
            days: int = 30, min_importance: int = 2, max_reads: int = 40, log=print) -> dict:
    """Fetch announcements for the Chinese tickers; summarize the important new ones with the LLM."""
    ensure_schema(store)
    stats = {"stocks": 0, "new": 0, "read": 0, "errors": 0}
    for tk in tickers:
        if not cn.is_cn(tk):
            continue
        try:
            stats["new"] += fetch(store, tk, days)
            stats["stocks"] += 1
        except cn.Blocked as e:
            stats["errors"] += 1
            log(f"  announcements skipped: {e}")
            return stats                                 # the rest would be refused too
        except Exception as e:
            stats["errors"] += 1
            log(f"  {tk}: announcements unavailable ({type(e).__name__})")
    if client is None:
        return stats
    since = (clock.today() - dt.timedelta(days=days)).isoformat()
    key = f"{model_id}#a{READ_VERSION}"
    todo = store.conn.execute(
        "SELECT a.art_code, a.ticker, a.title FROM announcements a WHERE a.importance >= ? AND a.date >= ? "
        "AND NOT EXISTS (SELECT 1 FROM announcement_reads r WHERE r.art_code = a.art_code AND r.model = ? "
        "AND r.lang = ?) ORDER BY a.importance DESC, a.date DESC LIMIT ?",
        (min_importance, since, key, lang, max_reads)).fetchall()
    for code, tk, title in todo:
        try:
            read(store, client, model_id, code, names.get(tk, tk), tk, title, lang)
            stats["read"] += 1
        except Exception as e:
            from marketmood.core import is_fatal
            stats["errors"] += 1
            if is_fatal(e):
                raise
            if isinstance(e, cn.Blocked):
                log(f"  announcement summaries skipped: {e}")
                break
    return stats


def recent(store, tickers: list[str], days: int = 30, min_importance: int = 1,
           lang: str = "en", model_id: str | None = None) -> list[dict]:
    """Saved announcements (newest first) with the LLM summary when there is one. No network."""
    ensure_schema(store)
    if not tickers:
        return []
    since = (clock.today() - dt.timedelta(days=days)).isoformat()
    marks = ",".join("?" * len(tickers))
    rows = store.conn.execute(
        f"SELECT art_code, ticker, date, title, category, importance, direction, url FROM announcements "
        f"WHERE ticker IN ({marks}) AND date >= ? AND importance >= ? ORDER BY date DESC, importance DESC",
        (*tickers, since, min_importance)).fetchall()
    out = []
    for code, tk, date, title, cat, imp, direction, url in rows:
        q = ("SELECT result FROM announcement_reads WHERE art_code = ? AND lang = ? "
             + ("AND model = ? " if model_id else "") + "ORDER BY read_at DESC LIMIT 1")
        params = (code, lang, f"{model_id}#a{READ_VERSION}") if model_id else (code, lang)
        r = store.conn.execute(q, params).fetchone()
        if r is None:                          # fall back to a reading in the other language
            r = store.conn.execute("SELECT result FROM announcement_reads WHERE art_code = ? "
                                   "ORDER BY read_at DESC LIMIT 1", (code,)).fetchone()
        out.append({"art_code": code, "ticker": tk, "date": date, "title": title, "category": cat,
                    "category_name": CATEGORY_NAMES.get(lang, CATEGORY_NAMES["en"]).get(cat, cat),
                    "importance": imp, "direction": direction, "url": url,
                    "read": json.loads(r[0]) if r else None})
    return out
