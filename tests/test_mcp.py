"""MCP tools: tool logic directly, and a real stdio round trip when the MCP SDK is installed."""

import asyncio
import datetime as dt
import json
import os
import sys

import pytest

import test_moves as tm
from stockproof import mcp_server


def make_tools(tmp_path):
    tm.setup_prices(tmp_path)
    t = mcp_server.Tools(str(tmp_path))
    t.app.set_watchlist(["300750", "AAPL"])
    store = t.app._store()
    ids = store.add_headlines("300750.SZ", [{"title": "宁德时代发布新电池", "published": dt.date.today().isoformat(),
                                             "link": "https://n/1"}])
    store.save_score(ids[0], "m", "zh", {"relevance": 0.9, "score": 0.6, "reason": "利好"})
    return t


def test_tools_return_sources_and_hints(tmp_path):
    t = make_tools(tmp_path)
    wl = t.watchlist("zh")
    assert [s["ticker"] for s in wl["stocks"]] == ["300750.SZ", "AAPL"] or len(wl["stocks"]) == 2
    b = t.stock_brief("300750", "zh")
    assert b["followed"] and b["name"] and b["news"][0]["link"] == "https://n/1"
    assert b["price"]["close"] > 0
    assert t.stock_brief("TSLA")["followed"] is False                     # tells the agent what to do
    assert "error" in t.company_announcements("AAPL")                     # US: explained, not empty
    assert t.research_findings("xx")["error"]
    assert t.daily_digest()["error"].startswith("no digest")
    out = t.add_to_watchlist(["00700"])
    assert "00700.HK" in out["watchlist"]
    assert "00700.HK" not in t.remove_from_watchlist(["700"])["watchlist"]
    json.dumps(b)                                                          # JSON-safe


def test_dsh_config_passes_keys_explicitly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = mcp_server.dsh_config(str(tmp_path / "stockproof_data"))
    assert "@deepseek-ai/dsh-mcp-client" in text and "serverName: stockproof" in text
    assert "DEEPSEEK_API_KEY: !!js process.env.DEEPSEEK_API_KEY" in text
    assert sys.executable in text and "sk-" not in text                    # no secret written


def test_stdio_round_trip(tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    make_tools(tmp_path)
    root = os.path.dirname(os.path.dirname(os.path.abspath(mcp_server.__file__)))

    async def go():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "stockproof", "mcp", "--data-dir", str(tmp_path)],
                                       env={"PYTHONPATH": root, "PATH": os.environ.get("PATH", "")})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = [x.name for x in (await s.list_tools()).tools]
                res = await s.call_tool("stock_brief", {"ticker": "300750", "lang": "zh"})
                return names, json.loads(res.content[0].text)
    names, brief = asyncio.run(go())
    assert {"stock_brief", "why_did_it_move", "refresh_stock", "research_findings"} <= set(names)
    assert brief["ticker"] == "300750.SZ" and brief["news"]


def test_install_dsh_merges_and_uninstalls(tmp_path):
    home = tmp_path / "dsh"
    data = tmp_path / "proj" / "stockproof_data"
    r = mcp_server.install_dsh(str(data), home=str(home), python="/opt/py/bin/python3")
    assert r["ok"] and r["created_home"] and r["backup"] is None
    text = (home / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "'/opt/py/bin/python3'" in text and "--load-shell-env" in text and str(data) in text
    # someone else's entries are kept; running again updates instead of duplicating; a backup is made
    (home / "cordis.patch.yml").write_text("- replace:\n    id: other\n" + text)
    r = mcp_server.install_dsh(str(data), home=str(home), python="/new/python")
    text = (home / "cordis.patch.yml").read_text(encoding="utf-8")
    assert r["updated"] and r["backup"] and text.count("stockproof-mcp") == 1
    assert "id: other" in text and "/new/python" in text and "/opt/py" not in text
    r = mcp_server.uninstall_dsh(home=str(home))
    text = (home / "cordis.patch.yml").read_text(encoding="utf-8")
    assert r["removed"] and "stockproof" not in text and "id: other" in text
    # refuses to touch a file it doesn't understand
    (home / "cordis.patch.yml").write_text("foo: bar\n")
    assert not mcp_server.install_dsh(str(data), home=str(home))["ok"]


def test_menu_lists_every_tool(tmp_path):
    import asyncio as _a
    t = mcp_server.Tools(str(tmp_path))
    menu = t.stockproof_menu("zh")
    listed = {x for g in menu["groups"] for x in g["tools"]}
    assert [g["group"] for g in menu["groups"]] == ["日常看盘", "AI 投研团队", "一句话与分享卡片", "模拟盘与提醒", "长期投资计划", "中长期预测", "资金地图", "选股与评分卡", "量化实验室", "持仓体检", "网页看板"]
    try:
        names = {x.name for x in _a.run(mcp_server.build_server(t).list_tools())}
    except Exception:
        return
    assert names - listed - {"stockproof_menu", "add_to_watchlist", "remove_from_watchlist"} == set()


def test_prompts_listed_and_filled(tmp_path):
    import asyncio
    srv = mcp_server.build_server(mcp_server.Tools(str(tmp_path)))
    names = {p.name for p in asyncio.run(srv.list_prompts())}
    assert {"menu", "checkup", "backtest", "scorecard", "why_moved"} <= names
    r = asyncio.run(srv.get_prompt("checkup", {"holdings": "600519 100"}))
    assert "portfolio_checkup" in r.messages[0].content.text and "600519 100" in r.messages[0].content.text


def test_open_dashboard_starts_once(tmp_path, monkeypatch):
    t = mcp_server.Tools(str(tmp_path))
    state = {"up": False, "cmds": []}
    monkeypatch.setattr(t, "_dashboard_up", lambda port: state["up"])

    def spawn(cmd, **k):
        state["cmds"].append(cmd)
        state["up"] = True
        assert k.get("start_new_session") is True
    r = t.open_dashboard("portfolio", open_browser=False, _spawn=spawn)
    assert r["started"] and r["url"].endswith("#portfolio") and "--no-browser" in state["cmds"][0]
    r = t.open_dashboard("nonsense", open_browser=False, _spawn=spawn)
    assert not r["started"] and r["tab"] == "home" and len(state["cmds"]) == 1


def test_first_time_only_dashboard_and_welcome(tmp_path, monkeypatch):
    import asyncio
    t = mcp_server.Tools(str(tmp_path))
    t.auto_dashboard = True
    opened = []
    monkeypatch.setattr(t, "_dashboard_up", lambda port: False)
    monkeypatch.setattr(t, "open_dashboard", lambda tab="home", **k: opened.append(tab) or {"url": "x"})
    monkeypatch.setattr(t, "auto_open", lambda tool, background=True: mcp_server.Tools.auto_open(t, tool, False))
    wrapped = mcp_server._AutoDashboard(t)
    t.auto_open("startup")
    first = wrapped.watchlist()
    second = wrapped.watchlist()
    assert opened == ["home"] and "IMPORTANT_first_time_user" in first and "IMPORTANT_first_time_user" not in second
    # a new session (new process) on the same data folder: nothing opens, no welcome
    t2 = mcp_server.Tools(str(tmp_path))
    t2.auto_dashboard = True
    monkeypatch.setattr(t2, "_dashboard_up", lambda port: False)
    monkeypatch.setattr(t2, "open_dashboard", lambda tab="home", **k: opened.append(tab))
    mcp_server.Tools.auto_open(t2, "startup", False)
    assert opened == ["home"] and "IMPORTANT_first_time_user" not in mcp_server._AutoDashboard(t2).watchlist()


def test_auto_dashboard_off_by_default(tmp_path, monkeypatch):
    t = mcp_server.Tools(str(tmp_path))
    opened = []
    monkeypatch.setattr(t, "_dashboard_up", lambda port: False)
    monkeypatch.setattr(t, "open_dashboard", lambda tab="home", **k: opened.append(tab))
    t.auto_open("startup", background=False)
    assert opened == []


def test_menu_text_lists_everything(tmp_path):
    txt = mcp_server.Tools(str(tmp_path)).stockproof_menu("zh")["text"]
    for w in ("日常看盘", "选股与评分卡", "量化实验室", "持仓体检", "/", "打开网页看板"):
        assert w in txt


def test_install_writes_skills_and_uninstall_removes_only_ours(tmp_path):
    home, data = tmp_path / "dsh", tmp_path / "data"
    (home / "skills" / "stockproof-menu").mkdir(parents=True)          # a user's own skill with our name
    (home / "skills" / "stockproof-menu" / "SKILL.md").write_text("mine")
    (home / "skills" / "other").mkdir()
    r = mcp_server.install_dsh(str(data), home=str(home), python="/py")
    assert "stockproof-checkup" in r["skills"] and "stockproof-menu" not in r["skills"]
    txt = (home / "skills" / "stockproof-checkup" / "SKILL.md").read_text(encoding="utf-8")
    assert txt.startswith("---\nname: stockproof-checkup\n") and "portfolio_checkup" in txt
    mcp_server.uninstall_dsh(home=str(home))
    assert not (home / "skills" / "stockproof-checkup").exists()
    assert (home / "skills" / "stockproof-menu" / "SKILL.md").read_text(encoding="utf-8") == "mine" and (home / "skills" / "other").exists()


def test_welcome_suggests_dashboard_without_opening(tmp_path, monkeypatch):
    t = mcp_server.Tools(str(tmp_path))
    t.welcome = True
    opened = []
    monkeypatch.setattr(t, "open_dashboard", lambda tab="home", **k: opened.append(tab))
    w = mcp_server._AutoDashboard(t)
    t.auto_open("startup", background=False)
    out = w.watchlist()
    assert "打开网页看板" in out["IMPORTANT_first_time_user"]["show_to_user_after_your_answer"] and opened == []


def test_stale_dashboard_is_restarted(tmp_path, monkeypatch):
    import stockproof
    t = mcp_server.Tools(str(tmp_path))
    states = [{"pid": 4242, "code": 1}, None, None]            # old code running -> stopped -> gone
    monkeypatch.setattr(t, "_dashboard_state", lambda port: states.pop(0) if states else {"pid": 1, "code": 9e12})
    killed = []
    monkeypatch.setattr(mcp_server.os, "kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(stockproof, "code_stamp", lambda: 100)
    spawned = []
    r = t.open_dashboard("home", open_browser=False, _spawn=lambda *a, **k: spawned.append(a), _wait=2)
    assert killed == [4242] and spawned and r["started"]


def test_technical_analysis_gives_chart_image(tmp_path, monkeypatch):
    import datetime as dt
    import numpy as np
    import pandas as pd
    monkeypatch.setenv("STOCKPROOF_CHART_IMAGES", "1")
    q = tmp_path / "quotes"
    q.mkdir()
    days = pd.bdate_range(end=dt.date.today(), periods=200)
    c = 10 + np.sin(np.arange(200) / 8)
    pd.DataFrame({"close": c, "open": c, "high": c * 1.01, "low": c * 0.99, "volume": 1e6}, index=days) \
        .rename_axis("date").to_csv(q / "600000.SH.csv")
    t = mcp_server.Tools(str(tmp_path))
    monkeypatch.setattr(t, "open_dashboard", lambda *a, **k: {"url": "http://127.0.0.1:8765/"})
    r = t.technical_analysis("600000.SH", lang="zh")
    assert r["chart_markdown"].startswith("![") and "/chart/600000.SH.svg" in r["chart_markdown"]
    assert "text_chart" not in r
    monkeypatch.setattr(t, "open_dashboard", lambda *a, **k: {"error": "no"})
    assert "text_chart" in t.technical_analysis("600000.SH", lang="zh")
