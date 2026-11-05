"""
Run the daily refresh automatically, so news history builds up without you:
macOS launchd, Windows Task Scheduler, or cron on Linux.

  stockproof daily                      one refresh now: news + earnings for the dashboard watchlist
  stockproof schedule --time 21:00      install a daily job; --remove, --status, --run-now

The job runs the same Python that installed it, in this project folder. API keys are not copied
anywhere: with --load-shell-env the job asks your login shell for them at run time (they stay in
~/.zshrc where you put them). If the Mac is asleep at that time, launchd runs the job when it wakes.

macOS protects the Desktop/Documents folders from background programs. If the first run reports
"Operation not permitted", give this Python "Full Disk Access" once (the command prints the path).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import plistlib
import subprocess
import sys

LABEL = "com.stockproof.daily"
KEY_ENVS = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DASHSCOPE_API_KEY", "STOCKPROOF_SEC_CONTACT", "MARKETMOOD_SEC_CONTACT")
OLD_LABEL = "com.marketmood.daily"           # name before 0.3


def plist_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


TASK = "stockproof-daily"                     # Windows Task Scheduler name
CRON_MARK = "# stockproof daily"               # marks our crontab line


def log_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "stockproof", "daily.log")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/stockproof/daily.log")
    return os.path.expanduser("~/.local/state/stockproof/daily.log")


def last_run_path(data_dir: str) -> str:
    return os.path.join(data_dir, "daily_last.json")


def load_shell_env(names=KEY_ENVS) -> list[str]:
    """Copy API keys / SEC contact from the user's interactive shell into this process only."""
    missing = [n for n in names if not os.environ.get(n)]
    if not missing or sys.platform == "win32":     # Windows: user variables reach every program already
        return []
    shell = os.environ.get("SHELL") or "/bin/zsh"
    try:
        out = subprocess.run([shell, "-i", "-c", "env"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    found = []
    for line in out.splitlines():
        k, _, v = line.partition("=")
        if k in missing and v:
            os.environ[k] = v
            found.append(k)
    from stockproof import compat_env
    compat_env()
    return found


def build_plist(python: str, workdir: str, hour: int, minute: int, args: list[str]) -> dict:
    os.makedirs(os.path.dirname(log_path()), exist_ok=True)
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "stockproof", "daily", "--load-shell-env", *args],
        "WorkingDirectory": workdir,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": log_path(),
        "StandardErrorPath": log_path(),
        "ProcessType": "Background",
    }


# ---------------------------------------------------------------- Windows: Task Scheduler
def _q(x: str) -> str:
    return '"' + x.replace('"', '') + '"'


def build_win_cmd(python: str, workdir: str, args: list[str], log: str) -> str:
    """The batch file the scheduled task runs (UTF-8 console, project folder, output to the log)."""
    return ("@echo off\r\nchcp 65001 >nul\r\nset PYTHONUTF8=1\r\n"
            f"cd /d {_q(workdir)}\r\n"
            f"{_q(python)} -m stockproof daily {' '.join(_q(a) for a in args)} >> {_q(log)} 2>&1\r\n")


def build_win_xml(command: str, hour: int, minute: int) -> str:
    """Task definition: daily at HH:MM, and as soon as possible after a missed start (computer off/asleep)."""
    from xml.sax.saxutils import escape
    start = f"{dt.date.today().isoformat()}T{hour:02d}:{minute:02d}:00"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>stockproof daily refresh</Description></RegistrationInfo>
  <Triggers><CalendarTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled>
    <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><StartWhenAvailable>true</StartWhenAvailable><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><Enabled>true</Enabled></Settings>
  <Actions Context="Author"><Exec><Command>{escape(command)}</Command></Exec></Actions>
</Task>
"""


def _install_windows(h: int, m: int, data_dir: str, extra: list[str]) -> str:
    import tempfile
    os.makedirs(os.path.dirname(log_path()), exist_ok=True)
    runner = os.path.join(os.path.dirname(log_path()), "daily.cmd")
    with open(runner, "w", encoding="utf-8", newline="") as f:
        f.write(build_win_cmd(sys.executable, os.getcwd(), ["--data-dir", os.path.abspath(data_dir), *extra], log_path()))
    xml = os.path.join(tempfile.gettempdir(), "stockproof-task.xml")
    with open(xml, "w", encoding="utf-16") as f:
        f.write(build_win_xml(runner, h, m))
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/XML", xml, "/F"], capture_output=True, text=True)
    if r.returncode != 0:
        return f"Could not create the scheduled task: {(r.stderr or r.stdout).strip()}"
    return (f"Daily refresh scheduled at {h:02d}:{m:02d} in Windows Task Scheduler (task “{TASK}”;\n"
            f"runs as soon as possible if the computer was off or asleep).\n  log: {log_path()}\n"
            f"Test it now with:  python -m stockproof schedule --run-now")


# ---------------------------------------------------------------- Linux: cron
def cron_line(python: str, workdir: str, hour: int, minute: int, args: list[str], log: str) -> str:
    import shlex
    cmd = " ".join(shlex.quote(a) for a in [python, "-m", "stockproof", "daily", "--load-shell-env", *args])
    return f"{minute} {hour} * * * cd {shlex.quote(workdir)} && {cmd} >> {shlex.quote(log)} 2>&1 {CRON_MARK}"


def merge_crontab(existing: str, line: str | None) -> str:
    """Replace our line in a crontab (or remove it when line is None); other lines are kept."""
    keep = [x for x in existing.splitlines() if CRON_MARK not in x]
    if line:
        keep.append(line)
    return ("\n".join(keep) + "\n") if keep else ""


def _crontab() -> str:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _write_crontab(text: str) -> subprocess.CompletedProcess:
    return subprocess.run(["crontab", "-"], input=text, capture_output=True, text=True)


def _install_linux(h: int, m: int, data_dir: str, extra: list[str]) -> str:
    import shutil
    if not shutil.which("crontab"):
        return "cron is not installed (no `crontab` command). Install cron, or run `stockproof daily` yourself."
    os.makedirs(os.path.dirname(log_path()), exist_ok=True)
    line = cron_line(sys.executable, os.getcwd(), h, m, ["--data-dir", os.path.abspath(data_dir), *extra], log_path())
    r = _write_crontab(merge_crontab(_crontab(), line))
    if r.returncode != 0:
        return f"Could not update the crontab: {r.stderr.strip()}"
    return (f"Daily refresh scheduled at {h:02d}:{m:02d} with cron (skipped if the computer is off then).\n"
            f"  log: {log_path()}\nSee it with `crontab -l`.")


# ---------------------------------------------------------------- all platforms
def install(time_hhmm: str, data_dir: str, extra: list[str]) -> str:
    h, m = (int(x) for x in time_hhmm.split(":"))
    if sys.platform == "win32":
        return _install_windows(h, m, data_dir, extra)
    if sys.platform != "darwin":
        return _install_linux(h, m, data_dir, extra)
    plist = build_plist(sys.executable, os.getcwd(), h, m, ["--data-dir", data_dir, *extra])
    path = plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    remove_old()
    subprocess.run(["launchctl", "unload", path], capture_output=True)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    r = subprocess.run(["launchctl", "load", path], capture_output=True, text=True)
    if r.returncode != 0:
        return f"Saved {path}, but launchctl said: {r.stderr.strip()}"
    return (f"Daily refresh scheduled at {h:02d}:{m:02d} (runs on wake if the Mac was asleep).\n"
            f"  job file: {path}\n  log:      {log_path()}\n"
            f"Test it now with:  python -m stockproof schedule --run-now")


def remove_old() -> bool:
    """Remove the daily job installed under the old name (marketmood), if any (macOS)."""
    old = os.path.expanduser(f"~/Library/LaunchAgents/{OLD_LABEL}.plist")
    if not os.path.exists(old):
        return False
    subprocess.run(["launchctl", "unload", old], capture_output=True)
    os.remove(old)
    return True


def remove() -> str:
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True, text=True)
        return "Daily job removed." if r.returncode == 0 else "No daily job installed."
    if sys.platform != "darwin":
        cur = _crontab()
        if CRON_MARK not in cur:
            return "No daily job installed."
        _write_crontab(merge_crontab(cur, None))
        return "Daily job removed."
    remove_old()
    path = plist_path()
    if not os.path.exists(path):
        return "No daily job installed."
    subprocess.run(["launchctl", "unload", path], capture_output=True)
    os.remove(path)
    return "Daily job removed."


def _installed() -> str | None:
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK, "/FO", "LIST"], capture_output=True, text=True)
        return f"Installed: Windows task “{TASK}”" if r.returncode == 0 else None
    if sys.platform != "darwin":
        line = next((x for x in _crontab().splitlines() if CRON_MARK in x), None)
        if not line:
            return None
        mi, hr = line.split()[:2]
        return f"Installed: daily at {int(hr):02d}:{int(mi):02d} (crontab)"
    path = plist_path()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        p = plistlib.load(f)
    t = p.get("StartCalendarInterval", {})
    return f"Installed: daily at {t.get('Hour', 0):02d}:{t.get('Minute', 0):02d} ({path})"


def status(data_dir: str) -> str:
    lines = [_installed() or "Not installed."]
    last = read_last(data_dir)
    if last:
        lines.append(f"Last run: {last.get('finished')} — {last.get('summary')}")
    if os.path.exists(log_path()):
        with open(log_path(), encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-8:]
        lines.append("Log (last lines):\n" + "".join("  " + x for x in tail).rstrip())
    return "\n".join(lines)


def run_now() -> str:
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/Run", "/TN", TASK], capture_output=True, text=True)
        if r.returncode != 0:
            return f"Could not start the job ({(r.stderr or r.stdout).strip()}). Is it installed?"
        return f"Started in the background. The log is {log_path()}"
    if sys.platform != "darwin":
        line = next((x for x in _crontab().splitlines() if CRON_MARK in x), None)
        if not line:
            return "No daily job installed."
        cmd = line.split(None, 5)[5].replace(CRON_MARK, "")
        subprocess.Popen(cmd, shell=True, start_new_session=True)
        return f"Started in the background. Follow it with:\n  tail -f {log_path()}"
    r = subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LABEL}"], capture_output=True, text=True)
    if r.returncode != 0:
        return f"Could not start the job ({r.stderr.strip() or r.returncode}). Is it installed?"
    return (f"Started in the background. Follow it with:\n  tail -f {log_path()}\n"
            f"If it says 'Operation not permitted', open System Settings → Privacy & Security → "
            f"Full Disk Access, click +, press ⌘⇧G and paste:\n  {os.path.realpath(sys.executable)}")


def read_last(data_dir: str) -> dict | None:
    try:
        with open(last_run_path(data_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def daily(data_dir: str, provider: str, model: str | None, base_url: str | None,
          lang: str | None, skip_earnings: bool = False) -> int:
    """One refresh of the dashboard watchlist: news, then earnings. Writes daily_last.json."""
    from stockproof.dashboard import Dashboard
    started = dt.datetime.now()
    print(f"=== stockproof daily {started:%Y-%m-%d %H:%M} ===", flush=True)
    app = Dashboard(data_dir, provider, model, base_url)
    app.echo = True
    tickers = list(app.settings["watchlist"])
    if not tickers:
        print("Watchlist is empty: add stocks in the dashboard first.")
        return 1
    lang = lang or app.settings.get("lang", "en")
    results = {}
    for kind in (["news"] if skip_earnings else ["news", "earnings"]):
        app.job = {"running": True, "kind": kind, "done": 0, "total": len(tickers), "current": "",
                   "log": [], "error": None, "finished_at": None}
        app._run(kind, tickers, lang)
        results[kind] = {"done": app.job["done"], "error": app.job["error"]}
        if app.job["error"]:
            break
    try:                                     # market-wide data: ETF channel, margin, the quarter's holders
        if os.environ.get("STOCKPROOF_MARKET_DATA", "1") == "0":
            raise RuntimeError("disabled (STOCKPROOF_MARKET_DATA=0)")
        from stockproof import etf_flows, flows, margin
        etf_flows.szse_snapshot(data_dir)
        etf_flows.daily(data_dir, 60, fetch=True, log=lambda *a: None)
        margin.history(data_dir, 20, fetch=True)
        flows.holders(data_dir, None, fetch=True, log=lambda *a: None)    # re-downloads only while reports come in
        results["market_data"] = {"done": 1, "error": None}
        print("market data: ETF shares, margin, holders updated", flush=True)
    except Exception as e:
        results["market_data"] = {"done": 0, "error": None, "warning": f"{type(e).__name__}: {e}"}
        print(f"market data skipped: {type(e).__name__}: {str(e)[:120]}", flush=True)
    try:                                     # monthly: extend whole-market prices and refit the forecaster
        from stockproof import forecast as fc
        fr = fc.load(data_dir)
        if fr and (dt.date.today() - dt.date.fromisoformat(fr["made"])).days >= 28:
            fc.update_prices(data_dir, log=lambda *a: None)
            fc.run(data_dir, log=lambda *a: None)
            print("forecast: refit", flush=True)
    except Exception as e:
        print(f"forecast refit skipped: {type(e).__name__}: {e}", flush=True)
    try:                                     # paper trading: strategy orders, fills; then alerts
        from stockproof import alerts, paper
        st = app._store()
        pr = paper.run_all(st, data_dir, fetch=True, log=lambda *a: None)
        new = alerts.check(st, data_dir, alerts.watch_list(app, st), None, lang)
        results["paper"] = {"done": 1, "error": None}
        print(f"paper: {pr['processed']}; alerts: {len(new)} new", flush=True)
    except Exception as e:
        results["paper"] = {"done": 0, "error": None, "warning": f"{type(e).__name__}: {e}"}
    try:                                     # one-page digest + notification
        from stockproof import digest
        from stockproof.llm import LLMClient
        try:
            client = LLMClient.from_provider(provider, model, base_url)
            model_id = f"{provider}:{client.model}"
        except Exception:
            client, model_id = None, None
        dg = digest.build(app, lang, client, model_id)
        results["digest"] = {"done": 1, "error": None, "path": dg["path"]}
        print(f"digest: {dg['path']} — {dg['summary']}", flush=True)
        digest.notify("stockproof", dg["summary"])
    except Exception as e:
        results["digest"] = {"done": 0, "error": f"{type(e).__name__}: {e}"}
    errors = [f"{k}: {v['error']}" for k, v in results.items() if v["error"] and k != "digest"]
    summary = "; ".join(errors) if errors else f"{len(tickers)} stocks: " + ", ".join(results)
    last = {"started": started.isoformat(timespec="seconds"),
            "finished": dt.datetime.now().isoformat(timespec="seconds"),
            "ok": not errors, "summary": summary, "results": results}
    with open(last_run_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(last, f)
    print(f"=== done: {summary} ===", flush=True)
    return 0 if not errors else 1
