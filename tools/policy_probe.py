"""
Which sources work for the policy-signal study? Run once:

    python tools/policy_probe.py

Tests 新闻联播 transcripts (CCTV, via AKShare) on old and recent dates, and Shenwan (申万) industry
index history. Writes tools/policy_probe_result.txt. Nothing is saved to the database.
"""

import os
import time
import traceback

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy_probe_result.txt")
lines = []


def log(msg=""):
    print(msg)
    lines.append(str(msg))


def probe(label, fn, show=3):
    t0 = time.time()
    try:
        df = fn()
        n = 0 if df is None else len(df)
        log(f"OK   {label}: {n} rows in {time.time() - t0:.1f}s")
        if n:
            log(f"     columns: {list(df.columns)[:10]}")
            for i in range(min(show, n)):
                log(f"     row {i}: {[str(x)[:60] for x in df.iloc[i].tolist()[:6]]}")
            if n > show:
                log(f"     last:  {[str(x)[:60] for x in df.iloc[-1].tolist()[:6]]}")
        return df
    except Exception as e:
        log(f"FAIL {label}: {type(e).__name__}: {str(e)[:200]}")
        lines.append(traceback.format_exc(limit=2))
        return None


try:
    import akshare as ak
    log(f"akshare {ak.__version__}")
except ImportError:
    raise SystemExit("pip install akshare")

log("\n== 新闻联播 transcripts ==")
for d in ("20160301", "20190610", "20230315", "20261027"):
    probe(f"news_cctv {d}", lambda d=d: ak.news_cctv(date=d), show=2)
    time.sleep(1)

log("\n== Shenwan industry indices ==")
probe("index_hist_sw 801080 电子 (day)", lambda: ak.index_hist_sw(symbol="801080", period="day"))
probe("index_hist_sw 801750 计算机 (day)", lambda: ak.index_hist_sw(symbol="801750", period="day"))
probe("sw_index_first_info", lambda: ak.sw_index_first_info(), show=2)

log("\n== Eastmoney industry board (by BK code, fallback) ==")
probe("stock_board_industry_hist_em BK1036 半导体", lambda: ak.stock_board_industry_hist_em(
    symbol="BK1036", start_date="20160101", end_date="20261028"))

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nSaved {OUT}")
