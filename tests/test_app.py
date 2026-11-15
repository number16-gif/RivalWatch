"""Tests for the local Flask web application."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as webapp
import database
import engine


class RivalWatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_db = database.DB_PATH
        self.old_engine_demo = engine.DEMO_PATH
        self.old_app_demo = webapp.DEMO_PATH
        database.DB_PATH = Path(self.folder.name) / "test.db"
        engine.DEMO_PATH = Path(self.folder.name) / "demo.html"
        webapp.DEMO_PATH = engine.DEMO_PATH
        self.app = webapp.create_app(testing=True)
        self.client = self.app.test_client()

    def tearDown(self):
        database.DB_PATH = self.old_db
        engine.DEMO_PATH = self.old_engine_demo
        webapp.DEMO_PATH = self.old_app_demo
        self.folder.cleanup()

    def csrf(self):
        self.client.get("/register")
        with self.client.session_transaction() as sess:
            return sess["csrf_token"]

    def register(self, username="tester"):
        response = self.client.post("/register", data={
            "username": username,
            "password": "safe-educational-password",
            "csrf_token": self.csrf()
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_registration_demo_check_change_and_history(self):
        self.register()
        self.client.post("/demo/add", data={"csrf_token": self.csrf()})
        with database.connect() as db:
            page_id = db.execute("SELECT id FROM pages").fetchone()["id"]
        self.client.post(
            f"/pages/{page_id}/check", data={"csrf_token": self.csrf()}
        )
        engine.DEMO_PATH.write_text(
            "<html><body><main><h1>Демо</h1><p>Цена: 900 рублей</p></main></body></html>", encoding="utf-8"
        )
        self.client.post(
            f"/pages/{page_id}/check", data={"csrf_token": self.csrf()}
        )
        with database.connect() as db:
            event = db.execute("SELECT summary FROM events").fetchone()
            self.assertIn("900", event["summary"])
            self.assertEqual(
                db.execute("SELECT count(*) FROM runs").fetchone()[0], 2
            )
        self.assertIn(b"900", self.client.get(f"/pages/{page_id}").data)

    def test_csrf_is_required(self):
        self.register()
        self.assertEqual(self.client.post("/demo/add", data={}).status_code, 400)

    def test_users_cannot_see_other_users_pages(self):
        self.register()
        self.client.post("/demo/add", data={"csrf_token": self.csrf()})
        with database.connect() as db:
            page_id = db.execute("SELECT id FROM pages").fetchone()["id"]
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.register("another")
        self.assertEqual(self.client.get(f"/pages/{page_id}").status_code, 404)
        self.assertEqual(
            self.client.post(
                f"/pages/{page_id}/delete",
                data={"csrf_token": self.csrf()}
            ).status_code, 404
        )

    def test_private_urls_rejected(self):
        for url in ("http://example.com", "https://localhost/x",
                    "https://127.0.0.1/", "https://192.168.1.1/",
                    "https://example.com:8080/"):
            with self.assertRaises(ValueError):
                engine.validate_public_url(url)

    def test_worker_checks_due_page_and_sends_notification(self):
        self.register()
        self.client.post("/demo/add", data={"csrf_token": self.csrf()})
        with database.connect() as db:
            page_id = db.execute("SELECT id FROM pages").fetchone()["id"]
            db.execute("UPDATE users SET telegram_chat_id=?", ("123456789",))
            db.commit()
        with patch.object(engine, "send_telegram", return_value=True) as send:
            self.assertEqual(engine.run_due(), 1)
            engine.DEMO_PATH.write_text(
                "<html><body>Цена: 50 рублей</body></html>", encoding="utf-8"
            )
            with database.connect() as db:
                db.execute(
                    "UPDATE pages SET next_check_at=? WHERE id=?",
                    ("2000-01-01T00:00:00+00:00", page_id)
                )
                db.commit()
            self.assertEqual(engine.run_due(), 1)
            send.assert_called_once()
        with database.connect() as db:
            self.assertEqual(
                db.execute("SELECT notified FROM events").fetchone()[0], 1
            )


if __name__ == "__main__":
    unittest.main()
