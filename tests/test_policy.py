import numpy as np
import pandas as pd

from marketmood import policy as pl
from marketmood.store import Store


ITEMS = [
    {"title": "习近平致电祝贺某国总统", "content": "国家主席习近平致电……"},
    {"title": "国务院常务会议部署加快发展集成电路产业", "content": "会议指出，要加快推进集成电路产业发展，加大专项资金支持……"},
    {"title": "国际联播快讯", "content": "某国经济政策……"},
    {"title": "多地整治房地产市场乱象", "content": "住建部表示，将加强监管，整治房地产市场秩序，限制违规投资……"},
    {"title": "春耕备耕有序开展", "content": "各地农民抢抓农时。"},
]


def test_candidates_filter():
    c = pl.candidates(ITEMS)
    assert [x["i"] for x in c] == [1, 3]                 # no diplomacy, foreign briefs or non-policy items


def test_download_resumable(tmp_path):
    calls = []

    def fake(day):
        calls.append(day)
        if day == "20200103":
            raise ConnectionError("x")
        return [] if day == "20200102" else ITEMS

    st = pl.download(str(tmp_path), "2020-01-01", "2020-01-03", workers=2, log=lambda *a: None, fetch=fake,
                     retry_wait=0)
    assert st["ok"] == 1 and st["empty"] == 1 and st["failed"] == 1
    assert pl.load_day(str(tmp_path), "20200101") == ITEMS
    assert pl.load_day(str(tmp_path), "20200102") == []    # old empty day kept (no broadcast text)
    calls.clear()
    pl.download(str(tmp_path), "2020-01-01", "2020-01-03", workers=1, log=lambda *a: None, fetch=lambda d: ITEMS)
    assert pl.load_day(str(tmp_path), "20200103") == ITEMS


class FakeClient:
    model = "fake"

    def __init__(self):
        self.n = 0

    def chat_json(self, prompt, temperature=0.0):
        self.n += 1
        return {"signals": [
            {"item": 1, "industry": "电子", "stance": "support", "strength": 4, "quote": "加快推进集成电路",
             "kind": "new_measure", "central": True},
            {"item": 2, "industry": "房地产", "stance": "restrict", "strength": 3, "quote": "整治房地产市场秩序"},
            {"item": 1, "industry": "芯片", "stance": "support", "strength": 3},          # not a Shenwan name
            {"item": 9, "industry": "计算机", "stance": "support", "strength": 2},        # no such item
            {"item": 1, "industry": "通信", "stance": "support", "strength": 7}]}         # off the ladder


def test_read_days_validates_and_caches(tmp_path):
    d = str(tmp_path)
    pl.download(d, "2020-01-01", "2020-01-02", workers=1, log=lambda *a: None, fetch=lambda day: ITEMS)
    store, client = Store(d), FakeClient()
    st = pl.read_days(store, client, "deepseek:fake", d, ["20200101", "20200102"], workers=1, log=lambda *a: None)
    assert st["read"] == 2 and st["signals"] == 4
    sig = pl.signals_frame(store, "deepseek:fake")
    assert set(sig["industry"]) == {"电子", "房地产"}
    assert set(sig["signed"]) == {4, -3}
    assert set(sig["kind"]) == {"new_measure", "report"}           # missing kind -> report
    assert len(pl.events(sig, kinds=("new_measure",))) == 2         # one per day
    pl.read_days(store, client, "deepseek:fake", d, ["20200101", "20200102"], workers=1, log=lambda *a: None)
    assert client.n == 2                                   # cached


def _prices(days, boost_code=None, boost_from=None):
    rng = np.random.default_rng(0)
    cols = {}
    for code in pl.SW_L1:
        r = rng.normal(0, 0.01, len(days))
        if code == boost_code:
            r[days >= boost_from] += 0.01
        c = 1000 * np.cumprod(1 + r)
        cols[f"{code}_c"] = c
        cols[f"{code}_o"] = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.002, len(days)))
    return pd.DataFrame(cols, index=days)


def test_events_escalation_and_returns():
    sig = pd.DataFrame({"day": pd.to_datetime(["2021-01-05", "2021-01-20", "2021-06-01"]), "item": 1,
                        "industry": "电子", "stance": "support", "strength": [2, 3, 3], "quote": "", "title": ""})
    sig["signed"] = sig["strength"]
    ev = pl.events(sig, fresh_days=60)
    assert list(ev["escalation"]) == [True, True, True]     # 2 -> 3 is a step up; June is > 60 days later
    sig2 = pd.concat([sig, sig.iloc[[1]].assign(day=pd.Timestamp("2021-02-01"))])
    ev2 = pl.events(sig2)
    assert not ev2[ev2["day"] == "2021-02-01"]["escalation"].iloc[0]   # same strength again: not news

    days = pd.bdate_range("2020-06-01", "2022-06-30")
    px = _prices(days, boost_code="801080", boost_from=pd.Timestamp("2021-01-06"))
    out = pl.attach_returns(ev, px)
    first = out.iloc[0]
    assert first["trade_day"] == pd.Timestamp("2021-01-06")  # the broadcast is after the close
    assert first["d2_20"] > 0.03                              # the planted outperformance shows up


def test_study_and_backtest_find_planted_effect():
    days = pd.bdate_range("2018-01-01", "2023-12-29")
    rng = np.random.default_rng(3)
    rows, boosts = [], {}
    codes = list(pl.SW_L1)
    for k in range(80):
        day = days[60 + k * 15]
        code = codes[k % len(codes)]
        rows.append({"day": day, "item": 1, "industry": pl.SW_L1[code], "stance": "support", "strength": 4,
                     "quote": "", "title": ""})
        boosts.setdefault(code, []).append(day)
    sig = pd.DataFrame(rows)
    sig["signed"] = 4
    cols = {}
    for code in codes:
        r = rng.normal(0, 0.008, len(days))
        for d in boosts.get(code, []):
            i = days.searchsorted(d, side="right")
            r[i + 1:i + 20] += 0.003
        c = 1000 * np.cumprod(1 + r)
        cols[f"{code}_c"], cols[f"{code}_o"] = c, np.r_[c[0], c[:-1]]
    px = pd.DataFrame(cols, index=days)
    ev = pl.attach_returns(pl.events(sig), px)
    res = pl.study(ev)
    d = res["tables"]["support_4"]["d2_20"]
    assert d["mean"] > 0.03 and d["t"] > 3
    assert abs(res["tables"]["support_4"]["pre20"]["mean"]) < 0.02
    bt = pl.backtest(ev, px, hold=20)
    assert bt["ann_excess"] > 0.05 and bt["t"] > 2


def test_scorecard_policy_dimension(tmp_path):
    import json as _json
    from marketmood import scorecard as scd
    d = str(tmp_path)
    store = Store(d)
    store.conn.executescript(pl.SCHEMA)
    day = (pd.Timestamp.today() - pd.Timedelta(days=5)).strftime("%Y%m%d")
    store.conn.execute("INSERT INTO policy_reads VALUES (?,?,?,?)", (day, "deepseek:fake#p2", _json.dumps({"signals": [
        {"item": 1, "industry": "电子", "stance": "support", "strength": 4, "kind": "new_measure", "central": True,
         "quote": "加快集成电路", "title": "国务院常务会议"}]}), "x"))
    store.conn.commit()
    (tmp_path / "cn").mkdir()
    (tmp_path / "cn" / "research_yjbb2_20260930.json").write_text(_json.dumps([{"code": "301308", "industry": "半导体"}]))

    class C:
        def chat_json(self, prompt, temperature=0.0):
            return {"map": {"半导体": "电子"}}
    dim = scd.policy_dim(d, store, C(), "deepseek:fake", "301308.SZ")
    assert dim["sw"] == "电子" and dim["n"] == 1 and dim["score"] is None
    assert pl.industry_map(d, None, ["半导体"]) == {"半导体": "电子"}       # cached, no LLM needed
    assert scd.policy_dim(d, store, None, None, "AAPL")["score"] is None
    # validation line from saved results; info only, never counted
    pl.save_results(d, {"study": {"start": "2016-03-03", "end": "2026-10-29", "tables": {"support": {
        "events": 7358, "gap": {"mean": 0.0003}, "d2_20": {"mean": -0.0023}, "d21_60": {"mean": -0.0051}}}},
        "backtest": {"20": {"ann_excess": 0.0064}}})
    f = pl.finding(d, "zh")
    assert f["tested"] and not f["useful"] and "7358" in f["text"]
    assert scd.validation(d, "cn", "zh")["policy"]["info_only"]
