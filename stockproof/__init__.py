"""stockproof (有据): an LLM reads stock news, earnings and filings with cited sources, and history checks what matters."""

import os as _os

__version__ = "0.3.0"


def compat_env() -> None:
    """The project was called marketmood until 0.2: keep reading the old MARKETMOOD_* variables."""
    for k, v in list(_os.environ.items()):
        if k.startswith("MARKETMOOD_"):
            _os.environ.setdefault("STOCKPROOF_" + k[len("MARKETMOOD_"):], v)


compat_env()
