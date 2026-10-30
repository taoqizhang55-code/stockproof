"""
Which Chinese price sources work from here? Run once before the China research study:

    python tools/china_price_probe.py

Tests each source with 鞍钢 (000898 / 00347) and writes tools/china_price_probe_result.txt.
Nothing is saved to the database.
"""

import os
import sys
import time
import traceback

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "china_price_probe_result.txt")
lines = []


def log(msg=""):
    print(msg)
    lines.append(str(msg))


def probe(label, fn):
    t0 = time.time()
    try:
        df = fn()
        n = 0 if df is None else len(df)
        log(f"OK   {label}: {n} rows in {time.time() - t0:.1f}s")
        if n:
            log(f"     columns: {list(df.columns)[:10]}")
            log(f"     first: {df.iloc[0].tolist()[:7]}")
            log(f"     last:  {df.iloc[-1].tolist()[:7]}")
    except Exception as e:
        log(f"FAIL {label}: {type(e).__name__}: {str(e)[:200]}")
        lines.append(traceback.format_exc(limit=2))


try:
    import akshare as ak
except ImportError:
    sys.exit("akshare is not installed in this Python. Activate the .venv first.")

log(f"akshare {ak.__version__}, Python {sys.version.split()[0]}")
log("-- A-share prices (鞍钢 000898)")
probe("Eastmoney stock_zh_a_hist hfq", lambda: ak.stock_zh_a_hist("000898", "daily", "20150101", "20500101", "hfq"))
probe("Sina stock_zh_a_daily hfq", lambda: ak.stock_zh_a_daily("sz000898", "20150101", "20500101", "hfq"))
log("-- HK prices (鞍钢 00347)")
probe("Eastmoney stock_hk_hist hfq", lambda: ak.stock_hk_hist("00347", "daily", "20150101", "22220101", "hfq"))
probe("Sina stock_hk_daily hfq", lambda: ak.stock_hk_daily("00347", "hfq"))
log("-- Benchmarks")
probe("Eastmoney index_zh_a_hist 000300 (CSI 300)", lambda: ak.index_zh_a_hist("000300", "daily", "20150101", "22220101"))
probe("Eastmoney stock_zh_index_daily_em sh000300", lambda: ak.stock_zh_index_daily_em("sh000300", "20150101", "20500101"))
probe("Sina stock_zh_index_daily sh000300", lambda: ak.stock_zh_index_daily("sh000300"))
probe("Eastmoney stock_hk_index_daily_em HSI", lambda: ak.stock_hk_index_daily_em("HSI"))
log("-- Index members (to pick a study universe)")
probe("csindex index_stock_cons_csindex 000300", lambda: ak.index_stock_cons_csindex("000300"))
probe("Sina index_stock_cons 000300", lambda: ak.index_stock_cons("000300"))

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
log(f"\nSaved to {OUT}")
