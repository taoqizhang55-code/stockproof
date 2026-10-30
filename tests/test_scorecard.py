import datetime as dt
import json

from stockproof import scorecard as scd
from stockproof.store import Store


class FakeApp:
    def __init__(self, data_dir, data):
        self.data_dir = data_dir
        self.data = data

    def stock(self, ticker, lang):
        return self.data


class FakeClient:
    model = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def chat_json(self, prompt, temperature=0.0):
        self.prompts.append(prompt)
        return self.reply


def _today(days=0):
    return (dt.date.today() - dt.timedelta(days=days)).isoformat()


def _data():
    return {"name": "测试公司", "headlines": [
        {"title": "大单落地", "link": "https://a", "date": _today(1), "relevance": 0.9, "score": 0.6, "reason": "订单", "dup": False},
        {"title": "产能扩张", "link": "https://b", "date": _today(2), "relevance": 0.8, "score": 0.4, "reason": "扩产", "dup": False},
        {"title": "重复", "link": "https://c", "date": _today(2), "relevance": 0.8, "score": 0.9, "reason": "", "dup": True},
        {"title": "股东减持", "link": "https://d", "date": _today(3), "relevance": 0.7, "score": -0.3, "reason": "减持", "dup": False},
        {"title": "无关", "link": "https://e", "date": _today(3), "relevance": 0.1, "score": -0.9, "reason": "", "dup": False},
    ], "earnings": {"filed": _today(5), "tone": 0.5, "guidance": "raised", "summary": "营收增长 40%",
                    "key_points": ["毛利率提升"], "risks": ["应收账款增加"], "url": "https://r", "doc_title": "三季报"},
        "report": {"sue": 2.5}, "price": {"m1": 0.1, "ytd": 0.3}}


def test_rule_dimensions():
    n = scd.news_dim(_data()["headlines"])
    assert n["n"] == 3 and n["score"] > 50                    # dup and irrelevant dropped
    assert scd.news_dim(_data()["headlines"][:1])["score"] is None   # too few
    r = scd.report_dim(_data()["earnings"])
    assert r["score"] == 50 + 20 + 15
    f = scd.filings_dim([{"importance": 3, "direction": -1, "title": "减持", "category": "insider_selling"},
                         {"importance": 2, "direction": 1, "title": "回购", "category": "buyback", "read": {"impact": 0.5}},
                         {"importance": 1, "direction": 1, "title": "分红", "category": "dividend"}])
    assert f["n"] == 2 and f["score"] == 50 + 12 * (-2 + 0.5)
    # one buyback = many filings: counted once
    many = [{"importance": 2, "direction": 1, "title": f"回购进展{i}", "category": "buyback"} for i in range(10)]
    g = scd.filings_dim(many)
    assert g["n"] == 10 and g["events"] == 1 and g["score"] == 62
    assert scd.fundamentals_dim(None, 0.0)["score"] == 50
    assert scd.fundamentals_dim({"covered": True, "score": 91.2, "rank": 7, "of": 2800}, None)["rank"] == 7
    assert scd.overall({"a": {"score": 90}, "b": {"score": 80}})["label"] == "positive"
    assert scd.overall({"a": {"score": 95}, "b": {"score": 20}})["label"] == "mixed"
    assert scd.overall({"a": {"score": 95}})["label"] == "insufficient"


def test_build_with_llm_and_citation_check(tmp_path):
    store = Store(str(tmp_path))
    client = FakeClient({"summary": "订单和财报都偏正面。",
                         "positives": [{"text": "大单落地", "evidence": [2]}, {"text": "编的", "evidence": [99]}],
                         "risks": [{"text": "应收账款增加", "evidence": [1]}],
                         "quality": {"score": 0.4, "reason": "增长来自主业", "evidence": [1]},
                         "watch": ["下季度毛利率"]})
    app = FakeApp(str(tmp_path), _data())
    card = scd.build(app, store, client, "deepseek:fake", "AAPL", "zh",
                     screen_rec={"covered": False, "why": "选股目前只覆盖 A 股"})
    dims = {d["key"]: d for d in card["dimensions"]}
    assert [d["key"] for d in card["dimensions"]] == scd.DIMS
    assert dims["quality"]["score"] == 70
    assert dims["fundamentals"]["source"] == "sue"
    assert dims["momentum"]["score"] is None
    assert len(card["synthesis"]["positives"]) == 1           # uncitable point dropped
    assert card["overall"]["score"] is not None and card["disclaimer"]
    assert dims["report"]["validated"]["tested"] and not dims["news"]["validated"]["tested"]
    assert "不构成投资建议" in card["disclaimer"]
    # untested dimensions (news, filings, quality) are shown but not counted in the total
    assert set(card["overall"]["counted"]) <= {"fundamentals", "momentum", "report"}
    assert card["overall"]["score"] == round((dims["fundamentals"]["score"] + dims["report"]["score"]) / 2, 1)
    # the prompt forbids advice and lists the evidence
    assert "do NOT give buy/sell advice" in client.prompts[0] and "[1] (report" in client.prompts[0]
    # cached for the day: no second LLM call
    scd.build(app, store, client, "deepseek:fake", "AAPL", "zh", screen_rec={"covered": False})
    assert len(client.prompts) == 1
    txt = scd.text(card, "zh")
    assert "测试公司" in txt and "大单落地 [2]" in txt


def test_validation_reads_backtest(tmp_path):
    d = tmp_path / "screens"
    d.mkdir()
    (d / "cn_backtest.json").write_text(json.dumps({"factors": [
        {"factors": ["sue", "rev_yoy", "np_yoy", "roe", "mom60"], "n": 32, "ann_excess": 0.013, "t": 0.5},
        {"factors": ["mom60"], "n": 32, "ann_excess": 0.064, "t": 1.5}]}))
    v = scd.validation(str(tmp_path), "cn", "zh")
    assert "+1.3%" in v["fundamentals"]["text"] and not v["fundamentals"]["useful"]
    assert "t=1.5" in v["momentum"]["text"]


def test_no_llm_card(tmp_path):
    store = Store(str(tmp_path))
    card = scd.build(FakeApp(str(tmp_path), _data()), store, None, None, "AAPL", "en",
                     screen_rec={"covered": False})
    assert card["synthesis"] is None
    assert {d["key"]: d for d in card["dimensions"]}["quality"]["score"] is None


def test_save_batch_merges(tmp_path):
    a = {"ticker": "A", "overall": {"score": 1}}
    scd.save_batch(str(tmp_path), [a])
    scd.save_batch(str(tmp_path), [{"ticker": "B", "overall": {"score": 2}}, {"ticker": "A", "overall": {"score": 3}}])
    got = {c["ticker"]: c["overall"]["score"] for c in scd.load_batch(str(tmp_path))}
    assert got == {"A": 3, "B": 2}


def test_dashboard_screen_and_card(tmp_path, monkeypatch):
    from stockproof import screener
    from stockproof.dashboard import Dashboard
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    day = dt.date.today().isoformat()
    screener.save(str(tmp_path), [{"ticker": "301308.SZ", "name": "江波龙", "rank": 2, "score": 98.9, "reasons": []}],
                  {"as_of": day, "screened": 2809, "top": 30, "per_industry": 3},
                  {"301308.SZ": {"rank": 2, "score": 98.9, "sue": 99}})
    app = Dashboard(str(tmp_path), "deepseek", None, None)
    page = app.screen_page("zh")
    assert page["meta"]["screened"] == 2809 and page["results"][0]["ticker"] == "301308.SZ"
    card = app.scorecard("301308.SZ", "zh")                   # no key: rule-based dimensions only
    assert card["name"] == "江波龙"
    assert {d["key"]: d for d in card["dimensions"]}["fundamentals"]["rank"] == 2
    assert app.screen_page("zh")["cards"]["301308.SZ"]["label"] == "insufficient"
    assert app.stock("301308.SZ", "zh")["screen"]["covered"]
    assert not app.stock("AAPL", "zh")["screen"]["covered"]
