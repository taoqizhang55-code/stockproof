"""Daily refresh and the launchd job file. No network, nothing installed."""

import json
import os

from marketmood import schedule


def test_build_plist_runs_daily_with_shell_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = schedule.build_plist("/x/.venv/bin/python", "/x", 21, 5, ["--data-dir", "d"])
    assert p["ProgramArguments"][:5] == ["/x/.venv/bin/python", "-m", "marketmood", "daily", "--load-shell-env"]
    assert p["StartCalendarInterval"] == {"Hour": 21, "Minute": 5}
    assert p["WorkingDirectory"] == "/x"
    assert not any("KEY" in a for a in p["ProgramArguments"])       # no secrets in the job file
    assert "EnvironmentVariables" not in p


def test_load_shell_env_only_takes_missing_keys(monkeypatch):
    class R:
        stdout = "PATH=/bin\nDEEPSEEK_API_KEY=sk-from-shell\nMARKETMOOD_SEC_CONTACT=A a@b.c\nOTHER=1\n"
    monkeypatch.setattr(schedule.subprocess, "run", lambda *a, **k: R())
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("MARKETMOOD_SEC_CONTACT", "already set")
    monkeypatch.delenv("OTHER", raising=False)
    found = schedule.load_shell_env()
    assert found == ["DEEPSEEK_API_KEY"]
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-from-shell"
    assert os.environ["MARKETMOOD_SEC_CONTACT"] == "already set"
    assert "OTHER" not in os.environ


def test_daily_runs_news_then_earnings_and_records_it(tmp_path, monkeypatch):
    from marketmood import dashboard
    calls = []

    def fake_run(self, kind, tickers, lang):
        calls.append((kind, tuple(tickers), lang))
        self.job["done"] = len(tickers)

    monkeypatch.setattr(dashboard.Dashboard, "_run", fake_run)
    d = str(tmp_path)
    app = dashboard.Dashboard(d, "deepseek", None, None)
    app.set_watchlist(["AAPL", "600519"])
    assert schedule.daily(d, "deepseek", None, None, None) == 0
    assert [c[0] for c in calls] == ["news", "earnings"] and calls[0][1] == ("AAPL", "600519.SH")
    last = schedule.read_last(d)
    assert last["ok"] and "2 stocks" in last["summary"]
    assert dashboard.Dashboard(d, "deepseek", None, None).state()["daily"]["ok"] is True
