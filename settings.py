"""Общие настройки проекта. Все пути строятся от папки проекта."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DB_PATH = Path(os.environ.get('RIVALWATCH_DB', ROOT / 'rivalwatch.db'))
DEMO_PATH = ROOT / 'demo.html'
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
USER_AGENT = 'RivalWatchEducationalBot/0.4 (+local prototype)'
MIN_INTERVAL_HOURS = 6


def get_secret_key():
    """Секрет Flask сохраняется локально между перезапусками."""
    if os.environ.get('RIVALWATCH_SECRET_KEY'):
        return os.environ['RIVALWATCH_SECRET_KEY']
    path = ROOT / '.flask_secret'
    if not path.exists():
        try:
            with path.open('x', encoding='utf-8') as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    return path.read_text(encoding='utf-8').strip()
