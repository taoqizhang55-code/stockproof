import pytest


@pytest.fixture(autouse=True)
def _no_eastmoney_wait(monkeypatch):
    """Tests use fake responses: skip the polite pause between Eastmoney requests."""
    from stockproof import cn
    monkeypatch.setattr(cn, "EM_GAP", 0.0)


@pytest.fixture(autouse=True)
def _no_link_lookups(monkeypatch):
    """Tests never call Google to resolve news links (tests of links.py turn it back on explicitly)."""
    monkeypatch.setenv("STOCKPROOF_RESOLVE_LINKS", "0")
    monkeypatch.setenv("STOCKPROOF_CHART_IMAGES", "0")          # tests never start a dashboard for chart images
