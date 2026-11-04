import pandas as pd

from stockproof import flows

RAW = pd.DataFrame([
    # 序号, 股东名称, 股东类型, 股票代码, 股票简称, 报告期, 数量, 数量变化, 变化比例, 持股变动, 流通市值, 公告日
    (1, "中央汇金资产管理有限责任公司", "投资公司", "600519", "贵州茅台", "2026-09-30", 1000, 1000, None, "新进", 1.5e6, "2026-10-25"),
    (2, "中国证券金融股份有限公司", "其它", "600036", "招商银行", "2026-09-30", 2000, 500, 33.3, "增加", 8.0e4, "2026-10-28"),
    (3, "全国社保基金一一四组合", "社保", "002230", "科大讯飞", "2026-09-30", 3000, -1000, -25.0, "减少", 1.2e5, "2026-10-20"),
    (4, "香港中央结算有限公司", "其它", "002230", "科大讯飞", "2026-09-30", 5000, 200, 4.2, "增加", 2.0e5, "2026-10-20"),
    (5, "中国人寿保险股份有限公司-传统-普通保险产品", "保险", "600036", "招商银行", "2026-09-30", 900, 0, None, "不变", 3.6e4, "2026-10-28"),
    (6, "UBS AG", "QFII", "300750", "宁德时代", "2026-09-30", 100, 100, None, "新进", 3.0e4, "2026-11-01"),
    (7, "华夏上证50交易型开放式指数证券投资基金", "基金", "600519", "贵州茅台", "2026-09-30", 50, -5, -9.1, "减少", 7.5e4, "2026-10-25"),
    (8, "张三", "个人", "600519", "贵州茅台", "2026-09-30", 10, 0, None, "不变", 1.5e4, "2026-10-25"),
], columns=["序号", "股东名称", "股东类型", "股票代码", "股票简称", "报告期", "期末持股-数量", "期末持股-数量变化",
            "期末持股-数量变化比例", "期末持股-持股变动", "期末持股-流通市值", "公告日"])


class FakeAk:
    calls = 0

    def stock_gdfx_free_holding_detail_em(self, date):
        FakeAk.calls += 1
        return RAW.copy()


def test_classify():
    assert flows.classify("中央汇金投资有限责任公司") == "national"
    assert flows.classify("梧桐树投资平台有限责任公司") == "national"
    assert flows.classify("全国社保基金四一三组合") == "social"
    assert flows.classify("基本养老保险基金一二零三组合") == "social"
    assert flows.classify("香港中央结算有限公司") == "northbound"
    assert flows.classify("新华人寿保险股份有限公司-分红-个人分红") == "insurance"
    assert flows.classify("GOLDMAN SACHS", "QFII") == "qfii"
    assert flows.classify("易方达创业板交易型开放式指数证券投资基金") == "fund"
    assert flows.classify("张三", "个人") is None
    assert flows.classify("招商基金管理有限公司-社保基金1903组合") == "social"
    assert flows.classify("国泰佳泰股票专项型养老金产品-招商银行股份有限公司") == "social"
    assert flows.classify("嘉实基金-农业银行-嘉实中证金融资产管理计划") == "national"
    assert flows.classify("国新宏盛投资(北京)有限公司") == "national"
    assert flows.classify("香港中央结算(代理人)有限公司") is None               # H-share nominee, not northbound
    assert flows.classify("某某", "全国社保基金") == "social" and flows.classify("某", "保险产品") == "insurance"
    assert flows.display_name("兴业银行股份有限公司-华夏中证人工智能主题交易型开放式指数证券投资基金").startswith("华夏中证")


def test_quarters():
    import datetime as dt
    assert flows.latest_quarter(dt.date(2026, 11, 3)) == "20260930"
    assert flows.latest_quarter(dt.date(2026, 10, 15)) == "20260630"
    assert flows.latest_quarter(dt.date(2026, 3, 1)) == "20250930"
    assert flows.quarter_ends(3, dt.date(2026, 11, 3)) == ["20260930", "20260630", "20260331"]


def test_money_map_and_stock_view(tmp_path, monkeypatch):
    monkeypatch.setattr(flows.cn, "_ak", lambda: FakeAk())
    monkeypatch.setattr(flows, "latest_quarter", lambda today=None: "20260930")
    d = str(tmp_path)
    m = flows.money_map(d, "national", log=lambda *a: None)
    assert m["stocks"] == 2 and m["counts"]["new"] == 1 and m["counts"]["add"] == 1
    assert m["new"][0]["ticker"] == "600519.SH" and m["new"][0]["value_change"] == 1.5e6
    assert abs(m["added"][0]["value_change"] - 500 * 40.0) < 1e-6          # 500 shares at 8e4/2000
    assert "十大流通股东" in m["limits"] and m["reported_companies"] == 4
    flows.money_map(d, "social", log=lambda *a: None)
    assert FakeAk.calls == 1                                                # cached per quarter
    # point in time: only reports public by the date count
    early = flows.money_map(d, "national", as_of="2026-10-26", log=lambda *a: None)
    assert early["stocks"] == 1 and early["new"][0]["name"] == "贵州茅台"
    s = flows.stock_holders(d, "002230.SZ", quarters=1)
    cats = {x["category"] for x in s["tracked"]}
    assert cats == {"social", "northbound"} and "减持" in s["summary"] and "增持" in s["summary"]
    assert flows.stock_holders(d, "601988.SH", quarters=1)["tracked"] == []
    m2 = flows.stock_holders(d, "600519.SH", quarters=1)                         # read back from the cached CSV
    assert {x["category"] for x in m2["holders"]} == {"national", "fund", None} and "None" not in m2["summary"]


def test_download_history_skips_saved_and_retries(tmp_path, monkeypatch):
    got = []

    class Ak:
        def stock_gdfx_free_holding_detail_em(self, date):
            got.append(date)
            if date == "20250331" and got.count(date) == 1:
                raise ConnectionError("reset")
            return RAW.copy()
    monkeypatch.setattr(flows.cn, "_ak", lambda: Ak())
    monkeypatch.setattr(flows.time if hasattr(flows, "time") else __import__("time"), "sleep", lambda s: None)
    import time as _t
    monkeypatch.setattr(_t, "sleep", lambda s: None)
    r = flows.download_history(str(tmp_path), "2025", log=lambda *a: None, pause=0)
    assert "20250331" in r["downloaded"] and not r["failed"] and got.count("20250331") == 2
    n = len(got)
    flows.download_history(str(tmp_path), "2025", log=lambda *a: None, pause=0)
    assert len(got) - n <= 2                    # only still-filling quarters are fetched again


def _q(rows):
    df = pd.DataFrame(rows, columns=["holder", "code", "name", "shares", "value", "action", "public", "category"])
    df["change"] = 0.0
    df["change_pct"] = None
    df["htype"] = ""
    df["period"] = ""
    return df


def test_exits_infer_sales_with_the_tenth_holder():
    prev = _q([("中央汇金投资有限责任公司", "600000", "浦发", 5e6, 5e7, "same", "2026-08-30", "national"),
               ("全国社保基金一组合", "600000", "浦发", 1e6, 1e7, "same", "2026-08-30", "social"),
               ("中国证券金融股份有限公司", "600001", "未报", 9e6, 9e7, "same", "2026-08-30", "national")])
    cur_rows = [(f"股东{i}", "600000", "浦发", 2e6 + i * 1e5, (2e6 + i * 1e5) * 10, "same", "2026-10-30", None)
                for i in range(10)]
    cur = _q(cur_rows)
    ex = flows.exits(cur, prev).set_index("holder")
    # 汇金 held 5M; this quarter's 10th holder has 2M -> it sold at least 3M
    assert ex.loc["中央汇金投资有限责任公司", "confidence"] == "inferred"
    assert ex.loc["中央汇金投资有限责任公司", "sold_at_least"] == 3e6
    assert abs(ex.loc["中央汇金投资有限责任公司", "sold_value_at_least"] - 3e7) < 1
    # 社保 held 1M < 2M: may simply have been pushed out
    assert ex.loc["全国社保基金一组合", "confidence"] == "possible"
    assert "中国证券金融股份有限公司" not in ex.index                  # its company hasn't reported yet
    assert flows.upper_bound(cur, "600000") == 2e6 and flows.upper_bound(cur, "600001") is None
    assert flows.prev_quarter("20260331") == "20251231" and flows.prev_quarter("20260930") == "20260630"


def test_money_map_and_stock_view_include_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(flows, "latest_quarter", lambda today=None: "20260930")
    d = str(tmp_path)
    prev = _q([("中央汇金投资有限责任公司", "600000", "浦发", 5e6, 5e7, "same", "2026-08-30", "national")])
    cur = _q([(f"股东{i}", "600000", "浦发", 2e6 + i * 1e5, (2e6 + i * 1e5) * 10, "same", "2026-10-30", None)
              for i in range(10)] + [("国新投资有限公司", "600519", "茅台", 1e5, 1.5e8, "new", "2026-10-25", "national")])
    prev.to_csv(f"{d}/flows/holders_20260630.csv" if __import__("os").makedirs(f"{d}/flows", exist_ok=True) is None else "", index=False)
    cur.to_csv(f"{d}/flows/holders_20260930.csv", index=False)
    m = flows.money_map(d, "national", fetch=False, log=lambda *a: None)
    assert m["previous_quarter"] == "20260630" and m["exit_counts"] == {"inferred": 1, "possible": 0}
    assert m["exits"][0]["confidence"] == "inferred" and m["inferred_reduction"] < 0 and "第十名" in m["confidence_note"]
    s = flows.stock_holders(d, "600000.SH", quarters=1, fetch=False)
    assert s["exits"] and "至少卖出 300 万股" in s["summary"] and "最多持有" in s["summary"]


def test_renamed_holder_is_not_an_exit():
    prev = _q([("香港中央结算有限公司", "002703", "浙江世宝", 2.18e8, 4e9, "same", "2025-08-30", "northbound")])
    cur = _q([("香港中央结算(代理人)有限公司", "002703", "浙江世宝", 2.185e8, 4e9, "same", "2025-10-30", None)] +
             [(f"股东{i}", "002703", "浙江世宝", 1e6, 1e7, "same", "2025-10-30", None) for i in range(9)])
    assert flows.exits(cur, prev).empty
