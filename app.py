import os
import logging
import requests
from flask import Flask, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан!")

app = Flask(__name__)

def send_message(chat_id, text):
    """Отправляет текстовое сообщение"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception as e:
        logger.error(f"Ошибка send_message: {e}")

def send_photo(chat_id, photo_url, caption):
    """Отправляет фото"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    try:
        requests.post(url, json={'chat_id': chat_id, 'photo': photo_url, 'caption': caption}, timeout=10)
    except Exception as e:
        logger.error(f"Ошибка send_photo: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обрабатывает входящие обновления от Telegram"""
    data = request.get_json()
    if not data or 'message' not in data:
        return 'OK', 200

    message = data['message']
    chat_id = message['chat']['id']
    text = message.get('text', '')

    if text == '/start':
        send_message(chat_id, "Привет! Я бот с мемами.\nОтправь /meme – получу случайный мем из интернета.")
    elif text == '/meme':
        try:
            # Запрос к API мемов
            resp = requests.get("https://meme-api.com/gimme", timeout=10)
            resp.raise_for_status()
            meme = resp.json()
            title = meme.get('title', 'Мем')
            author = meme.get('author', 'Неизвестный автор')
            caption = f"{title}\nАвтор: {author}"
            send_photo(chat_id, meme['url'], caption)
        except requests.exceptions.Timeout:
            send_message(chat_id, "Сервер мемов не отвечает. Попробуйте позже.")
        except Exception as e:
            logger.exception("Ошибка при получении мема")
            send_message(chat_id, "Не удалось получить мем. Попробуйте ещё раз.")
    else:
        send_message(chat_id, "Используйте /start или /meme")

    return 'OK', 200

@app.route('/')
def index():
    return "Бот работает", 200

if __name__ == '__main__':
    # Устанавливаем вебхук при старте
    hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if not hostname:
        logger.error("RENDER_EXTERNAL_HOSTNAME не задан! Вебхук не установится.")
    else:
        webhook_url = f"https://{hostname}/webhook"
        set_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
        try:
            response = requests.get(set_url, timeout=10)
            logger.info(f"Установка вебхука: {response.json()}")
        except Exception as e:
            logger.error(f"Не удалось установить вебхук: {e}")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)