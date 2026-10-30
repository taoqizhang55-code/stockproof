"""
`stockproof demo`: the full dashboard on bundled real data — no API key, no downloads, works offline.

The bundle (stockproof/demo_data, built with tools/make_demo.py) is copied to a temporary folder, so
anything you click or add there never touches it. The date is pinned to the day the data was saved, so
"last 7 days of news" and "upcoming reports" look the way they did then.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

BUNDLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_data")


def available() -> bool:
    return os.path.exists(os.path.join(BUNDLE, "demo.json"))


def prepare(target: str | None = None) -> tuple[str, dict]:
    """Copy the bundle to a fresh folder; returns (folder, demo meta)."""
    if not available():
        raise FileNotFoundError("the demo data is not included in this installation")
    with open(os.path.join(BUNDLE, "demo.json"), encoding="utf-8") as f:
        meta = json.load(f)
    target = target or tempfile.mkdtemp(prefix="stockproof-demo-")
    shutil.copytree(BUNDLE, target, dirs_exist_ok=True)
    return target, meta


def make_app(lang: str | None = None, target: str | None = None):
    from stockproof.dashboard import Dashboard
    folder, meta = prepare(target)
    os.environ["STOCKPROOF_TODAY"] = meta["as_of"]
    app = Dashboard(folder, "deepseek", None, None)
    app.demo = {"as_of": meta["as_of"], "model": meta.get("model", "deepseek:deepseek-chat")}
    if lang:
        app.settings["lang"] = lang
        app.save_settings()
    return app


def run(port: int = 8765, lang: str | None = None, open_browser: bool = True) -> int:
    from stockproof.dashboard import serve
    try:
        app = make_app(lang)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    print(f"stockproof demo · real data saved on {app.demo['as_of']} · offline, no API key needed")
    print(f"  (a temporary copy in {app.data_dir}; your own data is not touched)")
    serve(app, port, open_browser)
    return 0
