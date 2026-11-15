"""Узнать Chat ID после отправки сообщения своему боту в Telegram."""
import requests
from settings import BOT_TOKEN

if not BOT_TOKEN:
    print('Сначала добавь TELEGRAM_BOT_TOKEN в файл .env')
else:
    try:
        response = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates', timeout=10)
        response.raise_for_status()
        updates = response.json().get('result', [])
        chats = {str(item['message']['chat']['id']) for item in updates if 'message' in item}
        if chats:
            print('Chat ID из сообщений боту:')
            for chat in sorted(chats):
                print(chat)
        else:
            print('Нет сообщений. Напиши своему боту /start и любое сообщение, повтори команду.')
    except (requests.RequestException, ValueError) as error:
        print('Не удалось связаться с Telegram:', error.__class__.__name__)
