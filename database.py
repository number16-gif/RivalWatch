"""SQLite: пользователи, страницы, проверки и события."""
import sqlite3
from datetime import datetime, timezone
from settings import DB_PATH


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 10000')
    return connection


def has_column(db, table, name):
    return name in {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}


def init_db():
    """Создаёт таблицы; также расширяет БД v0.1, если её перенесли."""
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            telegram_chat_id TEXT,
            created_at TEXT NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            interval_hours INTEGER NOT NULL DEFAULT 6,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_text TEXT,
            last_checked TEXT,
            last_attempt TEXT,
            last_error TEXT,
            next_check_at TEXT,
            created_at TEXT,
            UNIQUE(user_id, url)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            checked_at TEXT NOT NULL,
            old_text TEXT NOT NULL,
            new_text TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            notified INTEGER NOT NULL DEFAULT 0
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            run_at TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT NOT NULL
        )''')
        for col, definition in {
            'user_id': 'INTEGER REFERENCES users(id)',
            'title': "TEXT NOT NULL DEFAULT ''",
            'interval_hours': 'INTEGER NOT NULL DEFAULT 6',
            'enabled': 'INTEGER NOT NULL DEFAULT 1',
            'last_attempt': 'TEXT',
            'last_error': 'TEXT',
            'next_check_at': 'TEXT',
            'created_at': 'TEXT',
        }.items():
            if not has_column(db, 'pages', col):
                db.execute(f'ALTER TABLE pages ADD COLUMN {col} {definition}')
        for col, definition in {
            'summary': "TEXT NOT NULL DEFAULT ''",
            'notified': 'INTEGER NOT NULL DEFAULT 0',
        }.items():
            if not has_column(db, 'events', col):
                db.execute(f'ALTER TABLE events ADD COLUMN {col} {definition}')
        db.execute('CREATE INDEX IF NOT EXISTS idx_pages_due ON pages(enabled, next_check_at)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_events_page ON events(page_id, id DESC)')
        db.commit()
