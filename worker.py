"""Фоновый работник. Запускается В ОТДЕЛЬНОМ терминале от app.py."""
import argparse
import logging
import time

from database import init_db
from engine import run_due

logging.basicConfig(filename='rivalwatch.log', level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')


def main():
    parser = argparse.ArgumentParser(description='RivalWatch: автоматические проверки')
    parser.add_argument('--once', action='store_true',
                        help='Проверить все страницы, срок которых наступил, и выйти')
    args = parser.parse_args()
    init_db()
    print('RivalWatch Worker: проверка каждые 60 секунд. Ctrl+C — остановка.')
    try:
        while True:
            number = run_due()
            if number:
                print(f'Запущены проверки: {number}')
            if args.once:
                break
            time.sleep(60)
    except KeyboardInterrupt:
        print('Worker остановлен')


if __name__ == '__main__':
    main()
