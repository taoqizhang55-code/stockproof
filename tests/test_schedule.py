"""Daily refresh and the launchd job file. No network, nothing installed."""

import json
import os

from stockproof import schedule


def test_build_plist_runs_daily_with_shell_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = schedule.build_plist("/x/.venv/bin/python", "/x", 21, 5, ["--data-dir", "d"])
    assert p["ProgramArguments"][:5] == ["/x/.venv/bin/python", "-m", "stockproof", "daily", "--load-shell-env"]
    assert p["StartCalendarInterval"] == {"Hour": 21, "Minute": 5}
    assert p["WorkingDirectory"] == "/x"
    assert not any("KEY" in a for a in p["ProgramArguments"])       # no secrets in the job file
    assert "EnvironmentVariables" not in p


def test_load_shell_env_only_takes_missing_keys(monkeypatch):
    class R:
        stdout = "PATH=/bin\nDEEPSEEK_API_KEY=sk-from-shell\nSTOCKPROOF_SEC_CONTACT=A a@b.c\nOTHER=1\n"
    monkeypatch.setattr(schedule.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(schedule.sys, "platform", "darwin")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("STOCKPROOF_SEC_CONTACT", "already set")
    monkeypatch.delenv("OTHER", raising=False)
    found = schedule.load_shell_env()
    assert found == ["DEEPSEEK_API_KEY"]
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-from-shell"
    assert os.environ["STOCKPROOF_SEC_CONTACT"] == "already set"
    assert "OTHER" not in os.environ


def test_daily_runs_news_then_earnings_and_records_it(tmp_path, monkeypatch):
    from stockproof import dashboard
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


def test_windows_task_files():
    cmd = schedule.build_win_cmd(r"C:\Users\张\venv\python.exe", r"C:\Users\张\proj", ["--data-dir", r"C:\Users\张\proj\stockproof_data"], r"C:\L\daily.log")
    assert "chcp 65001" in cmd and 'cd /d "C:\\Users\\张\\proj"' in cmd and "-m stockproof daily" in cmd and ">> \"C:\\L\\daily.log\" 2>&1" in cmd
    assert "KEY" not in cmd                                            # no secrets in the job
    xml = schedule.build_win_xml(r"C:\L\daily & co.cmd", 21, 5)
    assert "T21:05:00</StartBoundary>" in xml and "<StartWhenAvailable>true" in xml and "daily &amp; co.cmd" in xml


def test_cron_line_and_merge():
    line = schedule.cron_line("/v/bin/python", "/my proj", 21, 5, ["--data-dir", "/my proj/d"], "/l/daily.log")
    assert line.startswith("5 21 * * * cd '/my proj' && /v/bin/python -m stockproof daily --load-shell-env")
    assert line.endswith(schedule.CRON_MARK)
    cur = "0 1 * * * backup\n" + "1 2 * * * old " + schedule.CRON_MARK + "\n"
    merged = schedule.merge_crontab(cur, line)
    assert merged.count(schedule.CRON_MARK) == 1 and "backup" in merged and line in merged
    assert schedule.merge_crontab(merged, None) == "0 1 * * * backup\n"


def test_install_on_linux_writes_crontab(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule.sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    store = {"tab": "0 1 * * * backup\n"}

    class R:
        def __init__(self, out=""):
            self.returncode, self.stdout, self.stderr = 0, out, ""

    def fake_run(cmd, input=None, **k):
        if cmd == ["crontab", "-l"]:
            return R(store["tab"])
        if cmd == ["crontab", "-"]:
            store["tab"] = input
            return R()
        raise AssertionError(cmd)
    monkeypatch.setattr(schedule.subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/" + n)
    out = schedule.install("21:00", str(tmp_path / "d"), [])
    assert "cron" in out and "backup" in store["tab"] and schedule.CRON_MARK in store["tab"]
    assert "21:00" in schedule.status(str(tmp_path / "d"))
    assert schedule.remove() == "Daily job removed." and schedule.CRON_MARK not in store["tab"]


def test_install_on_windows_creates_task(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls = []

    class R:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(schedule.subprocess, "run", lambda cmd, **k: calls.append(cmd) or R())
    out = schedule.install("21:30", str(tmp_path / "d"), [])
    assert calls[0][:4] == ["schtasks", "/Create", "/TN", schedule.TASK] and "21:30" in out
    assert (tmp_path / "stockproof" / "daily.cmd").exists()
    assert schedule.load_shell_env() == []                     # Windows: nothing to load


def test_notify_never_raises(monkeypatch):
    from stockproof import digest
    def boom(*a, **k):
        raise OSError("no notifier")
    monkeypatch.setattr(digest.subprocess, "run", boom)
    for plat in ("darwin", "win32", "linux"):
        monkeypatch.setattr(digest.sys, "platform", plat)
        digest.notify("t", "m")
