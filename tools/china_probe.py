"""
China data probe: checks which Chinese data sources work from this computer,
and records exactly what they return, so stockproof's China module is built
on real formats instead of guesses.

Run (inside the Python 3.14 environment):
    python tools/china_probe.py

Writes tools/china_probe_result.txt. Takes about a minute. Sends no personal data.
"""

import json
import platform
import sys
import time
import traceback
from pathlib import Path

OUT = Path(__file__).with_name("china_probe_result.txt")
lines = []


def log(msg=""):
    print(msg)
    lines.append(str(msg))


def describe(obj, rows=2):
    """Short description of whatever came back (DataFrame, dict, list, text)."""
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            out = [f"DataFrame {obj.shape[0]} rows x {obj.shape[1]} cols",
                   f"columns: {list(obj.columns)}"]
            for i in range(min(rows, len(obj))):
                rec = {str(k): (str(v)[:120]) for k, v in obj.iloc[i].to_dict().items()}
                out.append(f"row {i}: {json.dumps(rec, ensure_ascii=False)}")
            return "\n    ".join(out)
    except Exception:
        pass
    if isinstance(obj, dict):
        return "dict keys: " + str(list(obj.keys()))[:400]
    if isinstance(obj, list):
        return f"list of {len(obj)}; first: " + json.dumps(obj[0], ensure_ascii=False)[:600] if obj else "empty list"
    return f"{type(obj).__name__}: {str(obj)[:400]}"


def probe(name, fn):
    log(f"\n=== {name}")
    t = time.time()
    try:
        result = fn()
        log(f"  OK ({time.time() - t:.1f}s)")
        log("    " + describe(result))
        return result
    except Exception as e:
        log(f"  FAILED ({time.time() - t:.1f}s): {type(e).__name__}: {str(e)[:300]}")
        tb = traceback.format_exc().strip().splitlines()
        log("    " + " | ".join(tb[-3:])[:500])
        return None


def main():
    log(f"python {sys.version.split()[0]} on {platform.platform()}")
    try:
        import akshare as ak
        log(f"akshare {ak.__version__}")
    except Exception as e:
        log(f"akshare NOT importable: {e}")
        ak = None
    import requests

    UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    if ak:
        # ---------- names ----------
        probe("A-share code/name list: stock_info_a_code_name()", ak.stock_info_a_code_name)
        probe("HK list: stock_hk_spot_em()", ak.stock_hk_spot_em)

        # ---------- news ----------
        for code in ("600519", "300750", "00700"):
            probe(f"news: stock_news_em('{code}')", lambda c=code: ak.stock_news_em(symbol=c))

        # ---------- announcements via AKShare (cninfo) ----------
        probe("cninfo via akshare: stock_zh_a_disclosure_report_cninfo('600519', 沪深京)",
              lambda: ak.stock_zh_a_disclosure_report_cninfo(
                  symbol="600519", market="沪深京", category="", start_date="20260101", end_date="20261031"))
        probe("cninfo via akshare: HK 00700 (港股)",
              lambda: ak.stock_zh_a_disclosure_report_cninfo(
                  symbol="00700", market="港股", category="", start_date="20260101", end_date="20261031"))

        # ---------- financials ----------
        probe("A financial abstract: stock_financial_abstract('600519')",
              lambda: ak.stock_financial_abstract(symbol="600519"))
        probe("A earnings table: stock_yjbb_em('20260630')", lambda: ak.stock_yjbb_em(date="20260630"))
        probe("A earnings forecasts: stock_yjyg_em('20260930')", lambda: ak.stock_yjyg_em(date="20260930"))
        probe("HK indicators: stock_financial_hk_analysis_indicator_em('00700', 报告期)",
              lambda: ak.stock_financial_hk_analysis_indicator_em(symbol="00700", indicator="报告期"))

    # ---------- announcements directly from Eastmoney (no AKShare) ----------
    def em_list(code, ann_type):
        r = requests.get("https://np-anotice-stock.eastmoney.com/api/security/ann",
                         params={"sr": -1, "page_size": 10, "page_index": 1, "ann_type": ann_type,
                                 "client_source": "web", "stock_list": code, "f_node": 0, "s_node": 0},
                         headers=UA, timeout=20)
        r.raise_for_status()
        data = r.json()
        items = (data.get("data") or {}).get("list") or []
        log(f"    top-level keys: {list(data.keys())}; items: {len(items)}")
        for it in items[:3]:
            log("    item: " + json.dumps({k: it.get(k) for k in ("art_code", "title", "notice_date", "display_time",
                                                                   "columns", "codes")}, ensure_ascii=False)[:500])
        return items

    items_a = probe("Eastmoney announcements: 600519 (A)", lambda: em_list("600519", "A"))
    probe("Eastmoney announcements: 00700 (H)", lambda: em_list("00700", "H"))

    if items_a:
        art = items_a[0].get("art_code")

        def em_content():
            r = requests.get("https://np-cnotice-stock.eastmoney.com/api/content/ann",
                             params={"art_code": art, "client_source": "web", "page_index": 1},
                             headers=UA, timeout=20)
            r.raise_for_status()
            d = r.json().get("data") or {}
            text = d.get("notice_content") or ""
            log(f"    data keys: {list(d.keys())}")
            log(f"    notice_content length: {len(text)}; start: {text[:200]!r}")
            log(f"    attach_url: {d.get('attach_url')}")
            return d
        probe(f"Eastmoney announcement text: {art}", em_content)

    # ---------- cninfo directly ----------
    def cninfo_query():
        r = requests.post("http://www.cninfo.com.cn/new/hisAnnouncement/query",
                          data={"stock": "600519,gssh0600519", "tabName": "fulltext", "pageSize": 10, "pageNum": 1,
                                "column": "sse", "category": "category_yjdbg_szsh;category_bndbg_szsh;category_sjdbg_szsh;category_ndbg_szsh",
                                "seDate": "2025-01-01~2026-10-31", "isHLtitle": "true"},
                          headers={**UA, "X-Requested-With": "XMLHttpRequest"}, timeout=20)
        r.raise_for_status()
        d = r.json()
        anns = d.get("announcements") or []
        log(f"    totalAnnouncement: {d.get('totalAnnouncement')}; got {len(anns)}")
        for a in anns[:3]:
            log("    ann: " + json.dumps({k: a.get(k) for k in ("secCode", "secName", "announcementTitle",
                                                                  "announcementTime", "adjunctUrl")}, ensure_ascii=False))
        return anns
    probe("cninfo direct: 600519 periodic reports", cninfo_query)

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()
