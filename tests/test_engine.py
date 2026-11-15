"""Tests for the monitoring engine and SQLite; no real internet requests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
import engine


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = database.DB_PATH
        self.original_demo = engine.DEMO_PATH
        database.DB_PATH = Path(self.temp.name) / "database.db"
        engine.DEMO_PATH = Path(self.temp.name) / "demo.html"
        engine.DEMO_PATH.write_text(
            "<html><body>Цена 1000 рублей</body></html>", encoding="utf-8"
        )
        database.init_db()
        with database.connect() as db:
            db.execute(
                "INSERT INTO users(username,password_hash,created_at) VALUES ('alice','hash',?)",
                (database.now_iso(),)
            )
            db.execute(
                "INSERT INTO pages(user_id,url,title,interval_hours,created_at)"
                " VALUES (1,'demo://example','test',6,?)",
                (database.now_iso(),)
            )
            db.commit()

    def tearDown(self):
        database.DB_PATH = self.original_db
        engine.DEMO_PATH = self.original_demo
        self.temp.cleanup()

    def test_demo_records_only_real_change(self):
        self.assertIn("Исходное", engine.check_page(1))
        self.assertEqual(engine.check_page(1), "Изменений нет")
        engine.DEMO_PATH.write_text(
            "<html><body>Цена 900 рублей</body></html>", encoding="utf-8"
        )
        self.assertIn("900", engine.check_page(1))
        with database.connect() as db:
            events = db.execute("SELECT summary FROM events").fetchall()
            self.assertEqual(len(events), 1)
            self.assertIn("900", events[0]["summary"])
            self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 3)

    def test_worker_runs_due_and_schedules_next(self):
        with patch.object(engine.time, "sleep", return_value=None):
            self.assertEqual(engine.run_due(), 1)
            self.assertEqual(engine.run_due(), 0)
        with database.connect() as db:
            self.assertIsNotNone(
                db.execute("SELECT next_check_at FROM pages WHERE id=1").fetchone()[0]
            )

    def test_private_addresses_are_rejected(self):
        for url in ("http://example.org", "https://localhost/",
                    "https://127.0.0.1/", "https://10.0.0.1/",
                    "https://example.org:5000/"):
            with self.assertRaises(ValueError, msg=url):
                engine.validate_public_url(url)

    def test_visible_text_ignores_scripts(self):
        result = engine.visible_text(
            "<html><script>hidden</script><main>hello world</main></html>"
        )
        self.assertEqual(result, "hello world")

    def test_old_database_schema_upgrades(self):
        old_path = Path(self.temp.name) / "old.db"
        with sqlite3.connect(old_path) as db:
            db.execute(
                "CREATE TABLE pages(id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL,"
                " last_text TEXT, last_checked TEXT)"
            )
            db.execute(
                "CREATE TABLE events(id INTEGER PRIMARY KEY, page_id INTEGER,"
                " checked_at TEXT, old_text TEXT, new_text TEXT)"
            )
            db.execute("INSERT INTO pages(url,last_text) VALUES ('demo://example','старое')")
        database.DB_PATH = old_path
        database.init_db()
        with database.connect() as db:
            self.assertEqual(db.execute("SELECT last_text FROM pages").fetchone()[0], "старое")
            self.assertIn(
                "next_check_at",
                {row["name"] for row in db.execute("PRAGMA table_info(pages)")}
            )


if __name__ == "__main__":
    unittest.main()
