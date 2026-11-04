"""Probe: which ETF share / scale data sources answer from this machine (for tracking the national team's ETF buying).

    python tools/etf_probe.py        # writes stockproof_data/etf_probe.txt
"""

import datetime as dt
import sys
import time
import traceback

sys.path.insert(0, ".")
import pandas as pd  # noqa: E402

import akshare as ak  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)

d1 = (dt.date.today() - dt.timedelta(days=1)).strftime("%Y%m%d")
d0 = "20240205"                                     # a known national-team buying day (Feb 2024 rescue)

CALLS = [
    ("ETF 实时行情 (all ETFs)", lambda: ak.fund_etf_spot_em()),
    ("上交所 ETF 规模 (yesterday)", lambda: ak.fund_etf_scale_sse(date=d1)),
    ("上交所 ETF 规模 (2024-02-05)", lambda: ak.fund_etf_scale_sse(date=d0)),
    ("深交所 ETF 规模", lambda: ak.fund_etf_scale_szse()),
    ("ETF 历史行情 510300", lambda: ak.fund_etf_hist_em(symbol="510300", period="daily", start_date="20240101",
                                                       end_date="20240301", adjust="")),
    ("基金规模变动 510300", lambda: ak.fund_individual_detail_hold_xq(symbol="510300", date="20241231")),
    ("基金持有人结构 510300", lambda: ak.fund_hold_structure_em()),
    ("基金份额变动 (东财)", lambda: ak.fund_scale_change_em()),
    ("ETF 份额 新浪 510300", lambda: ak.fund_etf_fund_info_em(fund="510300", start_date="20240101", end_date="20240301")),
]

out = [f"akshare {ak.__version__} · {dt.datetime.now():%Y-%m-%d %H:%M}\n"]
for name, fn in CALLS:
    t0 = time.time()
    try:
        df = fn()
        out.append(f"### OK  {name}  ({time.time() - t0:.1f}s, shape {getattr(df, 'shape', None)})")
        if isinstance(df, pd.DataFrame):
            out.append("columns: " + " | ".join(map(str, df.columns)))
            out.append(df.head(4).to_string())
    except Exception as e:
        out.append(f"### FAIL {name}  ({time.time() - t0:.1f}s): {type(e).__name__}: {str(e)[:200]}")
        out.append(traceback.format_exc(limit=2)[-400:])
    out.append("")
    print(next(l for l in reversed(out) if l.startswith("###")), flush=True)
    time.sleep(1.0)

with open("stockproof_data/etf_probe.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\nsaved stockproof_data/etf_probe.txt")
