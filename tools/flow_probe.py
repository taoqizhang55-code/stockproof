"""Phase 2 probe: which capital-flow data sources answer from this machine, and what their columns are.

    python tools/flow_probe.py        # writes stockproof_data/flow_probe.txt (a few minutes)
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
pd.set_option("display.max_colwidth", 24)

today = dt.date.today()
q = "20260930"                                      # latest quarter whose reports are all out
d1 = (today - dt.timedelta(days=1)).strftime("%Y%m%d")
d7 = (today - dt.timedelta(days=8)).strftime("%Y%m%d")

CALLS = [
    ("机构持仓: 社保", lambda: ak.stock_report_fund_hold(symbol="社保持仓", date=q)),
    ("机构持仓: 基金", lambda: ak.stock_report_fund_hold(symbol="基金持仓", date=q)),
    ("机构持仓: QFII", lambda: ak.stock_report_fund_hold(symbol="QFII持仓", date=q)),
    ("十大流通股东 600519", lambda: ak.stock_gdfx_free_top_10_em(symbol="sh600519", date=q)),
    ("十大股东 002230", lambda: ak.stock_gdfx_top_10_em(symbol="sz002230", date=q)),
    ("全市场流通股东明细 (all holders, one quarter)", lambda: ak.stock_gdfx_free_holding_detail_em(date=q)),
    ("股东持股统计 (by holder)", lambda: ak.stock_gdfx_free_holding_statistics_em(date=q)),
    ("机构持股一览", lambda: ak.stock_institute_hold(symbol="20263")),
    ("北向持股排行", lambda: ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行")),
    ("北向资金汇总", lambda: ak.stock_hsgt_fund_flow_summary_em()),
    ("龙虎榜明细 (last week)", lambda: ak.stock_lhb_detail_em(start_date=d7, end_date=d1)),
    ("龙虎榜机构买卖", lambda: ak.stock_lhb_jgmmtj_em(start_date=d7, end_date=d1)),
    ("龙虎榜营业部 002230", lambda: ak.stock_lhb_stock_detail_em(symbol="002230", date=d1, flag="买入")),
    ("融资融券 深市", lambda: ak.stock_margin_detail_szse(date=d1)),
    ("融资融券 沪市", lambda: ak.stock_margin_detail_sse(date=d1)),
    ("个股资金流 002230", lambda: ak.stock_individual_fund_flow(stock="002230", market="sz")),
    ("资金流排行 今日", lambda: ak.stock_individual_fund_flow_rank(indicator="今日")),
    ("板块资金流", lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")),
]

out = [f"akshare {ak.__version__} · python {sys.version.split()[0]} · {dt.datetime.now():%Y-%m-%d %H:%M}\n"]
for name, fn in CALLS:
    t0 = time.time()
    try:
        df = fn()
        secs = time.time() - t0
        shape = getattr(df, "shape", None)
        out.append(f"### OK  {name}  ({secs:.1f}s, shape {shape})")
        if isinstance(df, pd.DataFrame):
            out.append("columns: " + " | ".join(map(str, df.columns)))
            out.append(df.head(3).to_string())
    except Exception as e:
        out.append(f"### FAIL {name}  ({time.time() - t0:.1f}s): {type(e).__name__}: {str(e)[:200]}")
        out.append(traceback.format_exc(limit=2)[-600:])
    out.append("")
    print(next(l for l in reversed(out) if l.startswith("###")), flush=True)
    time.sleep(1.0)

with open("stockproof_data/flow_probe.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\nsaved stockproof_data/flow_probe.txt")
