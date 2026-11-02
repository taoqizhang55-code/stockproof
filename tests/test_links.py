import base64
import json

from stockproof import links, news

REUTERS = "https://www.reuters.com/markets/us/apple-results-2026-10-30/"


def _old_id(url):
    raw = b"\x08\x13\x22" + bytes([len(url)]) + url.encode() + b"\xd2\x01\x00"
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class _Resp:
    def __init__(self, text, code=200):
        self.text, self.status_code = text, code


class FakeSession:
    def __init__(self, url=REUTERS):
        self.url, self.calls = url, []

    def get(self, u, headers=None, timeout=None):
        self.calls.append(("get", u))
        return _Resp('<c-wiz><div jscontroller="x" data-n-a-sg="SIG123" data-n-a-ts="1793300000"></div></c-wiz>')

    def post(self, u, headers=None, data=None, timeout=None):
        self.calls.append(("post", u))
        assert "SIG123" in data and "1793300000" in data
        inner = json.dumps(["garturlres", self.url, 1])
        body = json.dumps([["wrb.fr", "Fbv4je", inner, None, None, None, "generic"], ["di", 12], ["af.httprm", 12, "", 3]])
        return _Resp(")]}'\n\n" + body)


def test_offline_decode_old_ids():
    gid = _old_id(REUTERS)
    assert links.google_id(f"https://news.google.com/rss/articles/{gid}?oc=5") == gid
    assert links.decode_offline(gid) == REUTERS
    assert links.decode_offline("CBMiYEFVX3lxTE5JRVVDQVVUazB5UUc0emdYVVVDRVoydXVJM2Q0bHUxenhkc0J6QUFreko3WUxtcmFnZmd2SF9ZbVJaX0hZZEF4T0VlVlAwdDR1SjhRdnBxX0drdGVEYVFaYg") is None
    assert links.google_id("https://www.reuters.com/x") is None


def test_online_decode_and_cache(tmp_path):
    gid = "CBMiYEFVX3lxTE5JRVVDQVVUazB5UUc0emdYVVVD"
    g = f"https://news.google.com/rss/articles/{gid}?oc=5"
    s = FakeSession()
    m = links.resolve_many([g, "https://finance.eastmoney.com/a/1.html"], str(tmp_path), session=s)
    assert m[g] == REUTERS and m["https://finance.eastmoney.com/a/1.html"] == "https://finance.eastmoney.com/a/1.html"
    assert [c[0] for c in s.calls] == ["get", "post"]
    s2 = FakeSession()
    assert links.resolve_many([g], str(tmp_path), session=s2)[g] == REUTERS and not s2.calls   # cached


def test_failures_fall_back_and_are_not_retried(tmp_path):
    class Dead(FakeSession):
        def get(self, u, headers=None, timeout=None):
            self.calls.append(("get", u))
            return _Resp("", 429)
    g = "https://news.google.com/rss/articles/AU_yqLdeadbeef"
    s = Dead()
    assert links.resolve_many([g], str(tmp_path), session=s)[g] == g
    s2 = Dead()
    assert links.resolve_many([g], str(tmp_path), session=s2)[g] == g and not s2.calls


def test_resolve_items_updates_store(tmp_path):
    from stockproof.store import Store
    st = Store(str(tmp_path))
    g = f"https://news.google.com/rss/articles/{_old_id(REUTERS)}"
    st.add_headlines("AAPL", [{"title": "Apple beats", "link": g, "source": "Reuters", "published": "2026-10-30"}])
    st.add_headlines("AAPL", [{"title": "Old one", "link": g + "x", "source": "google", "published": "2026-10-29"}])
    items = links.resolve_items([{"title": "Apple beats", "link": g, "source": "Reuters"}], str(tmp_path),
                                store=st, online=False)
    assert items[0]["link"] == REUTERS and items[0]["source"] == "Reuters"
    assert st.conn.execute("SELECT link, source FROM headlines WHERE title='Apple beats'").fetchone() == (REUTERS, "Reuters")
    assert links.publisher_of("https://wap.eastmoney.com/a/1.html") == "eastmoney.com"


def test_google_rss_publisher_is_kept():
    xml = ("<rss><channel><item><title>Apple beats - Reuters</title><link>https://news.google.com/rss/articles/X</link>"
           "<pubDate>Thu, 30 Oct 2026 20:00:00 GMT</pubDate><source url=\"https://www.reuters.com\">Reuters</source>"
           "</item></channel></rss>")
    it = news.parse_rss(xml, "google", 5)[0]
    assert it["source"] == "Reuters" and it["site"] == "https://www.reuters.com"


def test_old_google_source_becomes_site_name(tmp_path):
    from stockproof.store import Store
    st = Store(str(tmp_path))
    g = f"https://news.google.com/rss/articles/{_old_id(REUTERS)}"
    st.add_headlines("AAPL", [{"title": "Old one", "link": g, "source": "google", "published": "2026-10-29"}])
    items = links.resolve_items([{"title": "Old one", "link": g, "source": "google"}], str(tmp_path), store=st, online=False)
    assert items[0]["source"] == "reuters.com"
    assert st.conn.execute("SELECT source FROM headlines").fetchone()[0] == "reuters.com"
