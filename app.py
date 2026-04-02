import os
import logging
import requests
from flask import Flask, request
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан!")

app = Flask(__name__)

# Хранилище настроек пользователей: {chat_id: {'allow_nsfw': bool}}
user_settings = {}
settings_lock = Lock()  # для потокобезопасности (хотя Flask однопоточный по умолчанию)

# Клавиатуры
def get_main_keyboard(chat_id):
    """Главное меню с учётом текущего статуса NSFW"""
    nsfw_status = user_settings.get(chat_id, {}).get('allow_nsfw', False)
    nsfw_btn = "🔞 NSFW: ВКЛ" if nsfw_status else "🔞 NSFW: ВЫКЛ"
    return {
        "keyboard": [
            ["🎲 Случайный мем"],
            [nsfw_btn, "❓ Помощь"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def get_after_meme_keyboard(chat_id):
    """Клавиатура, показываемая после отправки мема"""
    nsfw_status = user_settings.get(chat_id, {}).get('allow_nsfw', False)
    nsfw_btn = "🔞 NSFW: ВКЛ" if nsfw_status else "🔞 NSFW: ВЫКЛ"
    return {
        "keyboard": [
            ["➡️ Следующий мем"],
            [nsfw_btn, "🏠 Меню"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

# Вспомогательные функции для отправки сообщений и фото
def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Ошибка send_message: {e}")

def send_photo(chat_id, photo_url, caption, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {'chat_id': chat_id, 'photo': photo_url, 'caption': caption}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Ошибка send_photo: {e}")

def fetch_meme(allow_nsfw):
    """Запрашивает мем из API с учётом NSFW"""
    api_url = "https://meme-api.com/gimme"
    if allow_nsfw:
        api_url += "?nsfw=true"   # явно разрешаем NSFW
    else:
        api_url += "?nsfw=false"  # запрещаем NSFW
    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # API может вернуть NSFW-контент, даже если запросили false, но обычно нет.
        # Проверяем поле nsfw (если есть) и при необходимости перезапрашиваем
        if not allow_nsfw and data.get('nsfw', False):
            # Если получили NSFW, хотя запрещено – повторяем запрос (макс 3 раза)
            for _ in range(3):
                resp = requests.get(api_url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if not data.get('nsfw', False):
                    break
        return data
    except Exception as e:
        logger.exception("Ошибка при получении мема")
        return None

# Обработка входящих сообщений
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or 'message' not in data:
        return 'OK', 200

    message = data['message']
    chat_id = message['chat']['id']
    text = message.get('text', '')

    # Инициализация настроек пользователя, если их нет
    with settings_lock:
        if chat_id not in user_settings:
            user_settings[chat_id] = {'allow_nsfw': False}

    # Обработка команд и кнопок
    if text == '/start' or text == '🏠 Меню':
        send_message(chat_id, "Добро пожаловать! Выберите действие:", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    elif text == '/meme' or text == '🎲 Случайный мем' or text == '➡️ Следующий мем':
        allow_nsfw = user_settings[chat_id]['allow_nsfw']
        meme = fetch_meme(allow_nsfw)
        if not meme:
            send_message(chat_id, "Не удалось получить мем. Попробуйте позже.")
            return 'OK', 200

        title = meme.get('title', 'Мем')
        author = meme.get('author', 'Неизвестный автор')
        nsfw_tag = " 🔞 NSFW" if meme.get('nsfw', False) else ""
        caption = f"{title}\nАвтор: {author}{nsfw_tag}"
        send_photo(chat_id, meme['url'], caption, reply_markup=get_after_meme_keyboard(chat_id))
        return 'OK', 200

    elif text == '🔞 NSFW: ВЫКЛ' or text == '🔞 NSFW: ВКЛ':
        # Переключаем NSFW
        current = user_settings[chat_id]['allow_nsfw']
        new_status = not current
        user_settings[chat_id]['allow_nsfw'] = new_status
        status_text = "включён" if new_status else "выключен"
        send_message(chat_id, f"Режим NSFW {status_text}.", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    elif text == '❓ Помощь':
        help_text = (
            "📖 Доступные действия:\n"
            "• 🎲 Случайный мем – показать один мем\n"
            "• ➡️ Следующий мем – следующий случайный мем (после просмотра)\n"
            "• 🔞 NSFW: ВКЛ/ВЫКЛ – показывать или скрывать взрослые мемы\n"
            "• 🏠 Меню – вернуться в главное меню\n\n"
            "Также работают команды /start и /meme."
        )
        send_message(chat_id, help_text, reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    else:
        send_message(chat_id, "Используйте кнопки меню или команду /start", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

@app.route('/')
def index():
    return "Бот работает", 200

if __name__ == '__main__':
    # Установка вебхука при старте
    hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if hostname:
        webhook_url = f"https://{hostname}/webhook"
        set_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
        try:
            resp = requests.get(set_url, timeout=10)
            logger.info(f"Webhook set: {resp.json()}")
        except Exception as e:
            logger.error(f"Ошибка установки вебхука: {e}")
    else:
        logger.warning("RENDER_EXTERNAL_HOSTNAME не задан, вебхук не установлен")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)