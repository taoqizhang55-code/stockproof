"""Check that Google News links resolve to publisher URLs on this machine (needs the internet).

    python tools/links_probe.py            # the 8 newest Google links in stockproof_data
    python tools/links_probe.py --fix-all  # also rewrite every stored Google link (slow, cached)
"""

import sys
import time

sys.path.insert(0, ".")

from stockproof import links  # noqa: E402
from stockproof.store import Store  # noqa: E402

data = "stockproof_data"
st = Store(data)
limit = "" if "--fix-all" in sys.argv else "LIMIT 8"
rows = st.conn.execute("SELECT title, link, source FROM headlines WHERE link LIKE '%news.google.com%' "
                       f"ORDER BY first_seen DESC {limit}").fetchall()
print(f"{len(rows)} Google News links to try")
t0 = time.time()
items = [{"title": t, "link": u, "source": s} for t, u, s in rows]
before = [it["link"] for it in items]
links.resolve_items(items, data, store=st, budget=60 if limit else 600)
ok = 0
for it, old in zip(items, before):
    good = it["link"] != old
    ok += good
    print(("OK   " if good else "KEEP ") + f"[{it['source']}] {it['title'][:40]}\n      {it['link'][:110]}")
print(f"\n{ok}/{len(items)} resolved in {time.time() - t0:.1f}s")
