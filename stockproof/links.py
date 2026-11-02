"""
Turn Google News redirect links (news.google.com/rss/articles/...) into the publisher's own URL.

A citation that opens Reuters or 证券时报 is checkable; a news.google.com redirect looks like we hid
the source. Resolution is lazy (only for items we actually cite), cached on disk, time-boxed, and
always falls back to the original link, so it can never make things worse.

  1. Offline: older article ids are base64 of a small protobuf that contains the URL itself.
  2. Online: newer ids ("AU_yqL...") need the signature + timestamp that Google puts on the article
     page, then one call to Google's own batchexecute endpoint (the same one its web app uses).
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import quote, urlparse

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
_ID = re.compile(r"news\.google\.com/(?:rss/)?(?:articles|read)/([A-Za-z0-9_\-]+)")
_URL = re.compile(rb"https?://[\x21-\x7e]+")
_LOCK = threading.Lock()


def google_id(url: str) -> str | None:
    m = _ID.search(url or "")
    return m.group(1) if m else None


def is_google(url: str) -> bool:
    return google_id(url) is not None


def decode_offline(art_id: str) -> str | None:
    """Old-style ids carry the URL inside: base64url(protobuf) with the URL as a length-prefixed string."""
    try:
        raw = base64.urlsafe_b64decode(art_id + "=" * (-len(art_id) % 4))
    except Exception:
        return None
    if raw.startswith(b"\x08\x13\x22"):
        raw = raw[3:]
        n = raw[0]
        if n & 0x80:                                  # two-byte varint length
            n, raw = (n & 0x7F) | (raw[1] << 7), raw[2:]
        else:
            raw = raw[1:]
        cand = raw[:n]
    else:
        cand = raw
    m = _URL.match(cand) or _URL.search(cand)
    if not m:
        return None
    url = m.group(0).decode("ascii", "ignore")
    if url.startswith("AU_yqL") or "news.google.com" in url:
        return None
    return url


def _params(art_id: str, session, timeout: float) -> tuple[str, str] | None:
    for path in (f"https://news.google.com/articles/{art_id}", f"https://news.google.com/rss/articles/{art_id}"):
        try:
            r = session.get(path, headers=HEADERS, timeout=timeout)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        sg = re.search(r'data-n-a-sg="([^"]+)"', r.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
        if sg and ts:
            return sg.group(1), ts.group(1)
    return None


def _parse_batch(text: str) -> str | None:
    try:
        body = text.split("\n\n", 1)[1]
        parsed = json.loads(body)[:-2]
        url = json.loads(parsed[0][2])[1]
        if isinstance(url, str) and url.startswith("http"):
            return url
    except Exception:
        pass
    m = re.search(r'garturlres\\",\\"(https?://[^\\"]+)', text)
    return m.group(1) if m else None


def decode_online(art_id: str, session=None, timeout: float = 6.0) -> str | None:
    session = session or requests
    p = _params(art_id, session, timeout)
    if not p:
        return None
    sg, ts = p
    inner = (f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
             f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{art_id}",{ts},"{sg}"]')
    data = "f.req=" + quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
    try:
        r = session.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                         headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                         data=data, timeout=timeout)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    url = _parse_batch(r.text)
    return url if url and "news.google.com" not in url else None


# ---------------------------------------------------------------- cache + batch
def _cache_path(data_dir: str) -> str:
    return os.path.join(data_dir, "links.json")


def _load(data_dir: str) -> dict:
    try:
        with open(_cache_path(data_dir), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data_dir: str, cache: dict) -> None:
    os.makedirs(data_dir, exist_ok=True)
    tmp = _cache_path(data_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, _cache_path(data_dir))


def resolve_many(urls: list[str], data_dir: str, online: bool = True, budget: float = 12.0,
                 workers: int = 6, session=None) -> dict[str, str]:
    """Map each Google News link to its publisher URL where it can be found; other links map to themselves.
    Failures are cached too (as "") for a week so a dead id isn't retried on every page load."""
    out = {u: u for u in urls if u}
    todo = {}
    with _LOCK:
        cache = _load(data_dir)
    now = time.time()
    for u in out:
        gid = google_id(u)
        if not gid:
            continue
        hit = cache.get(gid)
        if hit and hit.get("url"):
            out[u] = hit["url"]
            continue
        if hit is not None and now - hit.get("t", 0) < 7 * 86400:
            continue
        url = decode_offline(gid)
        if url:
            out[u] = url
            cache[gid] = {"url": url, "t": now}
        elif online:
            todo[u] = gid
    if todo:
        pool = ThreadPoolExecutor(max_workers=workers)
        futs = {pool.submit(decode_online, gid, session): (u, gid) for u, gid in todo.items()}
        done, _ = wait(futs, timeout=budget)
        for f in done:
            u, gid = futs[f]
            try:
                url = f.result()
            except Exception:
                url = None
            cache[gid] = {"url": url or "", "t": now}
            if url:
                out[u] = url
        pool.shutdown(wait=False, cancel_futures=True)
    with _LOCK:
        merged = {**_load(data_dir), **cache}
        try:
            _save(data_dir, merged)
        except OSError:
            pass
    return out


def resolve_items(items: list[dict], data_dir: str, key: str = "link", store=None, **kw) -> list[dict]:
    """Replace Google News links in a list of dicts in place; also fix them in the headlines table."""
    urls = [it.get(key) for it in items if is_google(it.get(key) or "")]
    if not urls:
        return items
    m = resolve_many(urls, data_dir, **kw)
    changed = []
    for it in items:
        old = it.get(key)
        if old in m and m[old] != old:
            it[key] = m[old]
            if (it.get("source") or "google") == "google":       # saved before publishers were recorded
                it["source"] = publisher_of(m[old])
            changed.append((m[old], it.get("source") or "", old))
    if store is not None and changed:
        try:
            store.conn.executemany("UPDATE headlines SET link = ?, source = CASE WHEN source IN ('google', '') "
                                   "THEN ? ELSE source END WHERE link = ?", changed)
            store.conn.commit()
        except Exception:
            pass
    return items


def publisher_of(url: str) -> str:
    """A readable site name from a URL: https://www.guancha.cn/x -> guancha.cn"""
    host = urlparse(url).netloc.lower().split(":")[0]
    for p in ("www.", "m.", "wap.", "mobile."):
        if host.startswith(p):
            host = host[len(p):]
    return host or "web"
