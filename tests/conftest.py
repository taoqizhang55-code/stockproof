import pytest


@pytest.fixture(autouse=True)
def _no_eastmoney_wait(monkeypatch):
    """Tests use fake responses: skip the polite pause between Eastmoney requests."""
    from stockproof import cn
    monkeypatch.setattr(cn, "EM_GAP", 0.0)
