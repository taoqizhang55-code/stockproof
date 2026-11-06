"""stockproof (有据): an LLM reads stock news, earnings and filings with cited sources, and history checks what matters."""

import os as _os

__version__ = "0.4.0"


def compat_env() -> None:
    """The project was called marketmood until 0.2: keep reading the old MARKETMOOD_* variables."""
    for k, v in list(_os.environ.items()):
        if k.startswith("MARKETMOOD_"):
            _os.environ.setdefault("STOCKPROOF_" + k[len("MARKETMOOD_"):], v)


compat_env()


def code_stamp() -> int:
    """Newest modification time of the package's own .py files: tells a long-running dashboard started
    by an agent apart from the code now on disk (after an update it must be restarted)."""
    here = _os.path.dirname(_os.path.abspath(__file__))
    try:
        return int(max(_os.path.getmtime(_os.path.join(here, f)) for f in _os.listdir(here) if f.endswith(".py")))
    except (OSError, ValueError):
        return 0
