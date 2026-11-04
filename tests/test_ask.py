import pytest

from stockproof import ask


class App:
    data_dir = "/nonexistent"
    settings = {"watchlist": ["002230.SZ", "NVDA"], "names": {"002230.SZ": "科大讯飞"}}

    def name_of(self, t):
        return self.settings["names"].get(t, t)


@pytest.mark.parametrize("text,intent,ticker", [
    ("茅台能买吗", "team", "600519.SH"),
    ("科大讯飞为什么跌了", "why", "002230.SZ"),
    ("国家队最近买了什么", "moneymap", None),
    ("国家队有没有买科大讯飞", "smart_money", "002230.SZ"),
    ("今天全市场哪些股票突破了", "breakouts", None),
    ("模拟买入10万宁德时代", "paper_order", "300750.SZ"),
    ("业绩大超预期后买入能赚钱吗", "lab", None),
    ("NVDA 的支撑位在哪", "technical", "NVDA"),
    ("最近有没有托底", "etf", None),
    ("AI 团队准不准", "team_record", None),
    ("随便聊聊", "menu", None),
    ("why did NVDA drop", "why", "NVDA"),
])
def test_route(text, intent, ticker):
    r = ask.route(App(), text)
    assert (r["intent"], r["ticker"]) == (intent, ticker)


def test_args_and_cli():
    r = ask.route(App(), "模拟买入10万宁德时代")
    assert r["args"] == {"side": "buy", "value": 100000.0}
    r = ask.route(App(), "体检持仓 600519 100股 00700 300股 AAPL 50")
    assert [h["ticker"] for h in r["args"]["holdings"]] == ["600519", "00700", "AAPL"]
    assert ask.cli_argv(r)[0] == "portfolio"
    r = ask.route(App(), "社保基金加仓了哪些")
    assert ask.cli_argv(r) == ["moneymap", "--category", "social"]
    assert ask.cli_argv(ask.route(App(), "科大讯飞")) == ["team", "002230.SZ"]          # no question beyond the name


def test_llm_fallback_only_into_known_intents():
    class C:
        def __init__(self, it):
            self.it = it

        def chat_json(self, prompt):
            return {"intent": self.it}
    assert ask.route(App(), "嗯……", C("digest"))["intent"] == "digest"
    assert ask.route(App(), "嗯……", C("rm -rf"))["intent"] == "menu"
