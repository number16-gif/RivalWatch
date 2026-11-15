"""RivalWatch: извлечение текста, сравнение и отправка уведомлений.

Для запуска локально. Не публикуйте этот сервер как интернет-сервис:
DNS-проверка сама по себе не обеспечивает полной защиты от SSRF.
"""
import difflib
import ipaddress
import logging
import socket
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from database import connect, now_iso
from settings import BOT_TOKEN, DEMO_PATH, MIN_INTERVAL_HOURS, USER_AGENT

log = logging.getLogger("rivalwatch")
HOST_LAST_REQUEST = {}
HOST_MIN_DELAY = {}


def validate_public_url(url):
    """Разрешаем только публичные HTTPS-домены и встроенную демостраницу."""
    if url == "demo://example":
        return
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Неверный URL") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Нужна публичная HTTPS-ссылка без логина и пароля")
    if port not in (None, 443):
        raise ValueError("Допускается только порт 443")
    host = parsed.hostname
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test")):
        raise ValueError("Локальные адреса запрещены")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Используйте доменное имя вместо IP")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise ValueError("Не удалось определить адрес сайта") from exc
    if not addresses:
        raise ValueError("Не найден IP сайта")
    if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Непубличные IP-адреса запрещены")


def wait_for_host(url):
    host = urlsplit(url).hostname
    delay = HOST_MIN_DELAY.get(host, 5)
    elapsed = time.monotonic() - HOST_LAST_REQUEST.get(host, float("-inf"))
    if elapsed < delay:
        time.sleep(delay - elapsed)
    HOST_LAST_REQUEST[host] = time.monotonic()


def fetch(url, byte_limit=1_000_000):
    """Ограниченная загрузка без редиректов и переменных прокси."""
    validate_public_url(url)
    wait_for_host(url)
    with closing(requests.Session()) as session:
        session.trust_env = False
        with session.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=(5, 12),
            allow_redirects=False, stream=True
        ) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("Укажите конечный HTTPS-адрес без редиректа")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                data.extend(chunk)
                if len(data) > byte_limit:
                    raise ValueError("Ответ превышает разрешённый размер")
            response.encoding = response.apparent_encoding or "utf-8"
            return (response.status_code,
                    response.headers.get("Content-Type", ""),
                    bytes(data).decode(response.encoding, errors="replace"))


def robots_allowed(url):
    parts = urlsplit(url)
    status, _, text = fetch(f"https://{parts.hostname}/robots.txt", byte_limit=200_000)
    if status == 404:
        return True
    if status != 200:
        raise ValueError(f"Не удалось проверить robots.txt: HTTP {status}")
    robot = RobotFileParser()
    robot.parse(text.splitlines())
    if not robot.can_fetch(USER_AGENT, url):
        return False
    delay = robot.crawl_delay(USER_AGENT)
    if delay:
        HOST_MIN_DELAY[parts.hostname] = max(HOST_MIN_DELAY.get(parts.hostname, 5), delay)
    rate = robot.request_rate(USER_AGENT)
    if rate and rate.requests > 0:
        seconds = rate.seconds / rate.requests
        HOST_MIN_DELAY[parts.hostname] = max(HOST_MIN_DELAY.get(parts.hostname, 5), seconds)
    if HOST_MIN_DELAY.get(parts.hostname, 5) > MIN_INTERVAL_HOURS * 3600:
        raise ValueError("Ограничение частоты сайта не поддерживается")
    return True


def visible_text(html):
    """Убирает из HTML служебные элементы и извлекает текст."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()
    return " ".join(soup.stripped_strings)


def retrieve(url):
    if url == "demo://example":
        return visible_text(DEMO_PATH.read_text(encoding="utf-8"))
    if not robots_allowed(url):
        raise ValueError("robots.txt запрещает мониторинг этой страницы")
    status, content_type, html = fetch(url)
    if status != 200:
        raise ValueError(f"HTTP {status}")
    if not any(t in content_type.lower() for t in ("text/html", "text/plain", "application/xhtml+xml")):
        raise ValueError("Нужна HTML-страница или текст")
    return visible_text(html)


def summary_of_change(old, new):
    old_words = old.split()[:2000]
    new_words = new.split()[:2000]
    for operation, a, b, c, d in difflib.SequenceMatcher(a=old_words, b=new_words).get_opcodes():
        if operation != "equal":
            before = " ".join(old_words[a:min(b, a + 15)]) or "(нет)"
            after = " ".join(new_words[c:min(d, c + 15)]) or "(нет)"
            return f"Было: {before[:180]}\nСтало: {after[:180]}"
    return "Текст страницы изменился"


def send_telegram(chat_id, url, summary):
    if not BOT_TOKEN or not chat_id:
        return False
    message = f"🔔 RivalWatch: изменение\n{url}\n\n{summary}"[:3900]
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": message}, timeout=(5, 10)
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise ValueError("Telegram не подтвердил отправку")
    return True


def check_page(page_id, force=False):
    """Сохраняет исходную версию или событие изменения в SQLite."""
    with closing(connect()) as db:
        page = db.execute(
            """SELECT pages.*, users.telegram_chat_id
               FROM pages JOIN users ON users.id=pages.user_id WHERE pages.id=?""",
            (page_id,)
        ).fetchone()
        if not page:
            return "Страница не найдена"
        if not page["enabled"] and not force:
            return "Мониторинг выключен"
        now = datetime.now(timezone.utc)
        if page["url"] != "demo://example" and page["last_attempt"]:
            if now - datetime.fromisoformat(page["last_attempt"]) < timedelta(minutes=5):
                return "Повторная проверка разрешена через 5 минут"
        attempt = now.isoformat(timespec="seconds")
        interval = max(MIN_INTERVAL_HOURS, page["interval_hours"] or MIN_INTERVAL_HOURS)
        next_check = (now + timedelta(hours=interval)).isoformat(timespec="seconds")
        db.execute(
            "UPDATE pages SET last_attempt=?,next_check_at=? WHERE id=?",
            (attempt, next_check, page_id)
        )
        db.commit()

        state, info, event_id = "error", "", None
        try:
            current = retrieve(page["url"])
            if page["last_text"] is None:
                state, info = "initial", "Исходное состояние сохранено"
            elif current != page["last_text"]:
                state, info = "changed", summary_of_change(page["last_text"], current)
                event_id = db.execute(
                    """INSERT INTO events(page_id,checked_at,old_text,new_text,summary)
                       VALUES (?,?,?,?,?)""",
                    (page_id, attempt, page["last_text"], current, info)
                ).lastrowid
            else:
                state, info = "same", "Изменений нет"
            db.execute(
                "UPDATE pages SET last_text=?,last_checked=?,last_error=NULL WHERE id=?",
                (current, attempt, page_id)
            )
        except (requests.RequestException, ValueError, OSError, UnicodeError) as exc:
            info = str(exc)[:400]
            db.execute("UPDATE pages SET last_error=? WHERE id=?", (info, page_id))
            log.warning("Ошибка проверки %s: %s", page["url"], info)
        db.execute(
            "INSERT INTO runs(page_id,run_at,status,description) VALUES(?,?,?,?)",
            (page_id, attempt, state, info[:500])
        )
        db.commit()
        if event_id and page["telegram_chat_id"]:
            try:
                if send_telegram(page["telegram_chat_id"], page["url"], info):
                    db.execute("UPDATE events SET notified=1 WHERE id=?", (event_id,))
                    db.commit()
            except (requests.RequestException, ValueError) as exc:
                log.warning("Telegram: %s", exc.__class__.__name__)
        return info


def run_due():
    """Выполняет проверки, наступившие по расписанию."""
    moment = now_iso()
    with closing(connect()) as db:
        rows = db.execute(
            """SELECT id FROM pages WHERE enabled=1 AND user_id IS NOT NULL
               AND (next_check_at IS NULL OR next_check_at <= ?)
               ORDER BY id LIMIT 20""", (moment,)
        ).fetchall()
    for row in rows:
        check_page(row["id"])
    return len(rows)
