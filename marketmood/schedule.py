"""
Run the daily refresh automatically (macOS launchd), so news history builds up without you.

  marketmood daily                      one refresh now: news + earnings for the dashboard watchlist
  marketmood schedule --time 21:00      install a daily job (macOS); --remove, --status, --run-now

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

LABEL = "com.marketmood.daily"
KEY_ENVS = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DASHSCOPE_API_KEY", "MARKETMOOD_SEC_CONTACT")


def plist_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def log_path() -> str:
    return os.path.expanduser("~/Library/Logs/marketmood/daily.log")


def last_run_path(data_dir: str) -> str:
    return os.path.join(data_dir, "daily_last.json")


def load_shell_env(names=KEY_ENVS) -> list[str]:
    """Copy API keys / SEC contact from the user's interactive shell into this process only."""
    missing = [n for n in names if not os.environ.get(n)]
    if not missing:
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
    return found


def build_plist(python: str, workdir: str, hour: int, minute: int, args: list[str]) -> dict:
    os.makedirs(os.path.dirname(log_path()), exist_ok=True)
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "marketmood", "daily", "--load-shell-env", *args],
        "WorkingDirectory": workdir,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": log_path(),
        "StandardErrorPath": log_path(),
        "ProcessType": "Background",
    }


def install(time_hhmm: str, data_dir: str, extra: list[str]) -> str:
    if sys.platform != "darwin":
        h, m = time_hhmm.split(":")
        return ("Automatic scheduling is built in for macOS only. On Linux, add this line with `crontab -e`:\n"
                f"  {m} {h} * * * cd {os.getcwd()} && {sys.executable} -m marketmood daily --data-dir {data_dir}")
    h, m = (int(x) for x in time_hhmm.split(":"))
    plist = build_plist(sys.executable, os.getcwd(), h, m, ["--data-dir", data_dir, *extra])
    path = plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["launchctl", "unload", path], capture_output=True)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    r = subprocess.run(["launchctl", "load", path], capture_output=True, text=True)
    if r.returncode != 0:
        return f"Saved {path}, but launchctl said: {r.stderr.strip()}"
    return (f"Daily refresh scheduled at {h:02d}:{m:02d} (runs on wake if the Mac was asleep).\n"
            f"  job file: {path}\n  log:      {log_path()}\n"
            f"Test it now with:  python -m marketmood schedule --run-now")


def remove() -> str:
    path = plist_path()
    if not os.path.exists(path):
        return "No daily job installed."
    subprocess.run(["launchctl", "unload", path], capture_output=True)
    os.remove(path)
    return "Daily job removed."


def status(data_dir: str) -> str:
    lines = []
    path = plist_path()
    if os.path.exists(path):
        with open(path, "rb") as f:
            p = plistlib.load(f)
        t = p.get("StartCalendarInterval", {})
        lines.append(f"Installed: daily at {t.get('Hour', 0):02d}:{t.get('Minute', 0):02d} ({path})")
    else:
        lines.append("Not installed.")
    last = read_last(data_dir)
    if last:
        lines.append(f"Last run: {last.get('finished')} — {last.get('summary')}")
    if os.path.exists(log_path()):
        with open(log_path(), encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-8:]
        lines.append("Log (last lines):\n" + "".join("  " + x for x in tail).rstrip())
    return "\n".join(lines)


def run_now() -> str:
    if sys.platform != "darwin":
        return "Only on macOS. Run `python -m marketmood daily` instead."
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
    from marketmood.dashboard import Dashboard
    started = dt.datetime.now()
    print(f"=== marketmood daily {started:%Y-%m-%d %H:%M} ===", flush=True)
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
    try:                                     # one-page digest + notification
        from marketmood import digest
        from marketmood.llm import LLMClient
        try:
            client = LLMClient.from_provider(provider, model, base_url)
            model_id = f"{provider}:{client.model}"
        except Exception:
            client, model_id = None, None
        dg = digest.build(app, lang, client, model_id)
        results["digest"] = {"done": 1, "error": None, "path": dg["path"]}
        print(f"digest: {dg['path']} — {dg['summary']}", flush=True)
        digest.notify("marketmood", dg["summary"])
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
