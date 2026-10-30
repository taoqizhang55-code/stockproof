"""
Company names for tickers. Used to tell the LLM which company a headline should
be about (so "Merck KGaA" news is not counted for MRK), and to search Google News
(single-letter tickers like "T" or "C" are useless as search words).

Users can add or override names: `marketmood scan T=AT&T C=Citigroup`
or a watchlist file with a "name" column.
"""

from __future__ import annotations

KNOWN_NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet (Google)", "GOOG": "Alphabet (Google)",
    "AMZN": "Amazon", "META": "Meta Platforms", "NVDA": "Nvidia", "TSLA": "Tesla",
    "AMD": "Advanced Micro Devices", "AVGO": "Broadcom", "INTC": "Intel", "CSCO": "Cisco",
    "ORCL": "Oracle", "IBM": "IBM", "ADBE": "Adobe", "CRM": "Salesforce", "QCOM": "Qualcomm",
    "TXN": "Texas Instruments", "NFLX": "Netflix", "UBER": "Uber", "PLTR": "Palantir",
    "TSM": "Taiwan Semiconductor (TSMC)", "BABA": "Alibaba", "PDD": "PDD Holdings (Temu)",
    "JPM": "JPMorgan Chase", "BAC": "Bank of America", "WFC": "Wells Fargo", "GS": "Goldman Sachs",
    "C": "Citigroup", "MS": "Morgan Stanley", "AXP": "American Express", "USB": "U.S. Bancorp",
    "V": "Visa", "MA": "Mastercard", "PYPL": "PayPal", "COIN": "Coinbase",
    "BRK-B": "Berkshire Hathaway", "KO": "Coca-Cola", "PEP": "PepsiCo", "PG": "Procter & Gamble",
    "WMT": "Walmart", "COST": "Costco", "MCD": "McDonald's", "NKE": "Nike", "SBUX": "Starbucks",
    "TGT": "Target Corporation", "HD": "Home Depot", "DIS": "Walt Disney",
    "JNJ": "Johnson & Johnson", "PFE": "Pfizer", "MRK": "Merck & Co.", "ABBV": "AbbVie",
    "LLY": "Eli Lilly", "BMY": "Bristol Myers Squibb", "UNH": "UnitedHealth", "CVS": "CVS Health",
    "AMGN": "Amgen", "GILD": "Gilead Sciences", "XOM": "Exxon Mobil", "CVX": "Chevron",
    "COP": "ConocoPhillips", "SLB": "SLB (Schlumberger)", "OXY": "Occidental Petroleum",
    "BA": "Boeing", "CAT": "Caterpillar", "GE": "GE Aerospace", "MMM": "3M", "HON": "Honeywell",
    "UPS": "United Parcel Service (UPS)", "LMT": "Lockheed Martin", "T": "AT&T", "VZ": "Verizon",
    "DUK": "Duke Energy", "SO": "Southern Company", "NEE": "NextEra Energy",
    "APD": "Air Products and Chemicals", "NEM": "Newmont",
}


def company_name(ticker: str, overrides: dict | None = None) -> str:
    ticker = ticker.upper()
    if overrides and ticker in overrides:
        return overrides[ticker]
    return KNOWN_NAMES.get(ticker, ticker)


def display_name(ticker: str, overrides: dict | None = None, data_dir: str | None = None) -> str:
    """company_name(), plus Chinese names saved by the China module."""
    name = company_name(ticker, overrides)
    if name != ticker.upper() or not data_dir:
        return name
    from marketmood import cn
    if cn.is_cn(ticker):
        return cn.CNCache(data_dir).names().get(cn.canonical(ticker), name)
    return name
