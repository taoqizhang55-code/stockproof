"""
Local SQLite database. Keeps every headline ever seen and every score, so:
  - re-running the scan never pays the LLM twice for the same headline
  - you build up a history you can study later (see the research tools)

Default location: ./marketmood_data/marketmood.db (change with --data-dir).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sqlite3

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS headlines (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT,
    source TEXT,
    published TEXT,
    first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scores (
    headline_id TEXT NOT NULL,
    model TEXT NOT NULL,
    lang TEXT NOT NULL,
    relevance REAL,
    score REAL,
    reason TEXT,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (headline_id, model, lang)
);
CREATE INDEX IF NOT EXISTS idx_headlines_ticker ON headlines (ticker);
CREATE TABLE IF NOT EXISTS earnings_reads (
    accession TEXT NOT NULL,
    model TEXT NOT NULL,
    lang TEXT NOT NULL,
    ticker TEXT NOT NULL,
    filed TEXT,
    url TEXT,
    result TEXT NOT NULL,
    read_at TEXT NOT NULL,
    PRIMARY KEY (accession, model, lang)
);
"""


def headline_id(ticker: str, title: str) -> str:
    from marketmood.news import normalize
    return hashlib.sha1(f"{ticker.upper()}|{normalize(title)}".encode()).hexdigest()[:16]


class Store:
    def __init__(self, data_dir: str = "marketmood_data"):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "marketmood.db")
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(scores)")}
        if "duplicate_of" not in cols:                       # databases made by older versions
            self.conn.execute("ALTER TABLE scores ADD COLUMN duplicate_of TEXT")
            self.conn.commit()

    def add_headlines(self, ticker: str, items: list[dict]) -> list[str]:
        """Save headlines (ignores ones already saved). Returns their ids."""
        now = dt.datetime.now().isoformat(timespec="seconds")
        ids = []
        for it in items:
            hid = headline_id(ticker, it["title"])
            ids.append(hid)
            self.conn.execute(
                "INSERT OR IGNORE INTO headlines VALUES (?, ?, ?, ?, ?, ?, ?)",
                (hid, ticker.upper(), it["title"], it.get("link", ""), it.get("source", ""),
                 it.get("published", ""), now))
        self.conn.commit()
        return ids

    def unscored(self, ids: list[str], model: str, lang: str) -> list[tuple[str, str]]:
        """(id, title) pairs among `ids` that have no score yet for this model and language."""
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT h.id, h.title FROM headlines h WHERE h.id IN ({marks}) AND NOT EXISTS "
            "(SELECT 1 FROM scores s WHERE s.headline_id = h.id AND s.model = ? AND s.lang = ?)",
            (*ids, model, lang)).fetchall()
        return rows

    def save_score(self, hid: str, model: str, lang: str, result: dict) -> None:
        """result may carry 'duplicate_of': the id of a headline reporting the same event."""
        self.conn.execute(
            "INSERT OR REPLACE INTO scores (headline_id, model, lang, relevance, score, reason, scored_at, "
            "duplicate_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (hid, model, lang, result["relevance"], result["score"], result["reason"],
             dt.datetime.now().isoformat(timespec="seconds"), result.get("duplicate_of")))
        self.conn.commit()

    def earnings_read(self, accession: str, model: str, lang: str) -> dict | None:
        row = self.conn.execute(
            "SELECT result, url, filed FROM earnings_reads WHERE accession=? AND model=? AND lang=?",
            (accession, model, lang)).fetchone()
        if not row:
            return None
        import json
        out = json.loads(row[0])
        out.update({"url": row[1], "filed": row[2]})
        return out

    def save_earnings_read(self, accession: str, model: str, lang: str, ticker: str,
                           filed: str, url: str, result: dict) -> None:
        import json
        self.conn.execute(
            "INSERT OR REPLACE INTO earnings_reads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (accession, model, lang, ticker.upper(), filed, url,
             json.dumps(result, ensure_ascii=False), dt.datetime.now().isoformat(timespec="seconds")))
        self.conn.commit()

    def scored(self, tickers: list[str], model: str | None, lang: str,
               since: str | None = None, any_lang: bool = False) -> pd.DataFrame:
        """All scored headlines for these tickers. `since` = YYYY-MM-DD filter on publish date
        (headlines without a date fall back to the day first seen).
        model=None accepts any model. any_lang=True falls back to scores in another language
        when a headline has none in `lang` (one row per headline, `lang` preferred)."""
        marks = ",".join("?" * len(tickers))
        where = [f"h.ticker IN ({marks})"]
        params = [t.upper() for t in tickers]
        if model:
            where.append("s.model = ?")
            params.append(model)
        if not any_lang:
            where.append("s.lang = ?")
            params.append(lang)
        df = pd.read_sql_query(
            "SELECT h.id, h.ticker, h.title, h.link, h.source, h.published, h.first_seen, "
            "s.relevance, s.score, s.reason, s.model, s.lang, s.scored_at, s.duplicate_of "
            "FROM headlines h JOIN scores s ON s.headline_id = h.id WHERE " + " AND ".join(where),
            self.conn, params=params)
        if len(df):
            df["_pref"] = (df["lang"] != lang).astype(int)
            df = df.sort_values(["_pref", "scored_at"], ascending=[True, False])
            df = df.drop_duplicates("id").drop(columns="_pref")
        df["date"] = df["published"].where(df["published"] != "", df["first_seen"].str[:10])
        if since:
            df = df[df["date"] >= since]
        return df.sort_values(["ticker", "date"], ascending=[True, False]).reset_index(drop=True)

    def latest_earnings(self, ticker: str, lang: str) -> dict | None:
        """The most recent saved earnings reading for a ticker (prefers `lang`). No network."""
        import json
        rows = self.conn.execute(
            "SELECT result, url, filed, lang FROM earnings_reads WHERE ticker = ? "
            "ORDER BY filed DESC, (lang = ?) DESC, read_at DESC LIMIT 1",
            (ticker.upper(), lang)).fetchall()
        if not rows:
            return None
        out = json.loads(rows[0][0])
        out.update({"url": rows[0][1], "filed": rows[0][2], "lang": rows[0][3]})
        return out
