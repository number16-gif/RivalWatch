# RivalWatch 🔎

**A Python/Flask portfolio project for detecting changes on public web pages.**

[Русская версия](README.md) · [Security notes](SECURITY.md)

> Educational, **local-only** prototype — not a production SaaS. Do not expose it to the public Internet without security improvements.

## Features

- Local web dashboard with registration and sign-in.
- Add, pause, edit, delete and manually check monitored pages.
- Background worker for periodic page checks.
- Extract visible text from HTML, compare versions, and store change history in SQLite.
- Optional Telegram notifications.
- Local offline demo to verify the monitoring engine without a network connection.
- Basic checks for public HTTPS URLs, `robots.txt`, redirects and response size.
- Automated Python tests through GitHub Actions.

## Technology

Python 3.11+, Flask, SQLite, Requests, BeautifulSoup, Jinja2, HTML/CSS, Telegram Bot API, unittest.

## Quick start (Windows)

1. Install Python 3.11 or newer.
2. Clone the repository or select **Code → Download ZIP**.
3. Run `install.bat` to create a virtual environment and install dependencies.
4. Run `start_web.bat`, then open http://127.0.0.1:5000 .
5. Register a local account and click **Добавить демо** (Add demo).
6. Open the demo page, check it, modify the price from 1000 to 900 in `demo.html`, and check again.
7. Run `start_worker.bat` in a second terminal for scheduled checks.

### Telegram

Copy `.env.example` to `.env`, set `TELEGRAM_BOT_TOKEN` to a token created via @BotFather, send a message to the bot, run `python telegram_chat_id.py`, and save the resulting Chat ID in the dashboard settings. **Never commit a token.**

## Architecture

```text
Flask dashboard (app.py)
        ↕
SQLite (database.py)
        ↕
Background checks (worker.py)
        ↓
Monitoring engine (engine.py)
        ├──→ Public HTTPS pages
        └──→ Telegram notifications
```

HTML templates live in `templates/`, styles in `static/`, and unit tests in `tests/`.

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

GitHub Actions runs the tests for Python 3.11 and 3.12 on pushes and pull requests.

## Known limitations

- Only HTML/text pages; no browser rendering, login bypass, CAPTCHA bypass or built-in marketplace integrations.
- A simple DNS check is **not** a sufficient SSRF defense for public deployment.
- Page changes can create false positives.
- No payment system, commercial plans or production-grade job queue.
- Respect `robots.txt`, site terms and rate limits.

The project is for educational use and as a code example. There is no license yet; all rights are reserved by default.
