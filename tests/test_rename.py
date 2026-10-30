"""The project was called marketmood until 0.2: old installs keep working."""
import os
import sqlite3

from stockproof import compat_env, mcp_server
from stockproof.store import Store


def test_old_env_names_still_work(monkeypatch):
    monkeypatch.delenv("STOCKPROOF_SEC_CONTACT", raising=False)
    monkeypatch.setenv("MARKETMOOD_SEC_CONTACT", "A b@c.d")
    compat_env()
    assert os.environ["STOCKPROOF_SEC_CONTACT"] == "A b@c.d"


def test_old_database_is_taken_over(tmp_path):
    sqlite3.connect(tmp_path / "marketmood.db").execute("CREATE TABLE t (x)")
    s = Store(str(tmp_path))
    assert s.path.endswith("stockproof.db") and not (tmp_path / "marketmood.db").exists()
    assert "t" in {r[0] for r in s.conn.execute("SELECT name FROM sqlite_master")}


def test_install_replaces_old_dsh_entry_and_skills(tmp_path):
    home = tmp_path / "dsh"
    (home / "skills" / "marketmood-menu").mkdir(parents=True)
    (home / "skills" / "marketmood-menu" / ".marketmood-skill").write_text("")
    (home / "skills" / "marketmood-mine").mkdir()                      # not ours: kept
    (home / "cordis.patch.yml").write_text(
        "- insert:\n    - id: other\n# >>> marketmood (added by `marketmood mcp --install-dsh`; remove with --uninstall-dsh)\n"
        "- insert:\n    - id: marketmood-mcp\n# <<< marketmood\n", encoding="utf-8")
    r = mcp_server.install_dsh(str(tmp_path / "data"), home=str(home), python="/py")
    text = (home / "cordis.patch.yml").read_text(encoding="utf-8")
    assert r["ok"] and r["updated"] and "marketmood" not in text and "id: stockproof-mcp" in text and "id: other" in text
    assert not (home / "skills" / "marketmood-menu").exists() and (home / "skills" / "marketmood-mine").exists()
    assert (home / "skills" / "stockproof-checkup" / "SKILL.md").exists()
