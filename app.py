import os
import logging
import requests
from flask import Flask, request
from threading import Lock
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан!")

app = Flask(__name__)

# Структура данных пользователя
user_settings = {}      # {chat_id: {'allow_nsfw': bool, 'category': str, 'history': deque}}
settings_lock = Lock()

# Доступные категории (сабреддиты)
CATEGORIES = {
    "🎭 Любой": "random",           # любой случайный мем
    "😂 Dad Jokes": "dadjokes",
    "🔞 18+": "GoneWild",        # сабреддит с NSFW-мемами (проверьте, работает ли)
    "💻 IT Jokes": "programmerhumor",
    "🎮 Gaming Jokes": "gamingmemes"
}

# Обратные названия для отображения
CATEGORY_NAMES = {v: k for k, v in CATEGORIES.items()}

# Размер истории для каждого пользователя
HISTORY_SIZE = 20

def get_main_keyboard(chat_id):
    """Главное меню с выбором категорий"""
    current_cat = user_settings.get(chat_id, {}).get('category', 'random')
    current_cat_name = CATEGORY_NAMES.get(current_cat, "🎭 Любой")
    nsfw_status = user_settings.get(chat_id, {}).get('allow_nsfw', False)
    nsfw_btn = "🔞 NSFW: ВКЛ" if nsfw_status else "🔞 NSFW: ВЫКЛ"
    keyboard = [
        [f"📂 Категория: {current_cat_name}"],
        list(CATEGORIES.keys()),   # все категории в одной строке (может быть длинно)
        [nsfw_btn, "❓ Помощь"]
    ]
    # Если категорий много, можно разбить по две, но пока так
    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def get_after_meme_keyboard(chat_id):
    """Клавиатура после отправки мема"""
    current_cat = user_settings.get(chat_id, {}).get('category', 'random')
    current_cat_name = CATEGORY_NAMES.get(current_cat, "🎭 Любой")
    nsfw_status = user_settings.get(chat_id, {}).get('allow_nsfw', False)
    nsfw_btn = "🔞 NSFW: ВКЛ" if nsfw_status else "🔞 NSFW: ВЫКЛ"
    return {
        "keyboard": [
            ["➡️ Следующий мем", f"📂 {current_cat_name}"],
            [nsfw_btn, "🏠 Меню"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"send_message error: {e}")

def send_photo(chat_id, photo_url, caption, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {'chat_id': chat_id, 'photo': photo_url, 'caption': caption}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"send_photo error: {e}")

def fetch_meme(category, allow_nsfw, history):
    """
    Получает мем из указанной категории (сабреддита), избегая повторений из history.
    Возвращает словарь с мемом или None.
    """
    if category == "random":
        api_url = "https://meme-api.com/gimme"
    else:
        api_url = f"https://meme-api.com/gimme/{category}"
    
    # Добавляем параметр NSFW, если нужно
    params = {}
    if allow_nsfw:
        params['nsfw'] = 'true'
    else:
        params['nsfw'] = 'false'
    
    for attempt in range(5):  # максимум 5 попыток получить уникальный мем
        try:
            resp = requests.get(api_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Проверяем, что URL мема не в истории
            meme_url = data.get('url')
            if meme_url and meme_url not in history:
                # Дополнительная проверка: если NSFW выключен, но мем пришёл NSFW – пропускаем
                if not allow_nsfw and data.get('nsfw', False):
                    continue
                return data
            else:
                logger.info(f"Повтор мема {meme_url}, пробуем снова")
                continue
        except Exception as e:
            logger.exception(f"Ошибка запроса мема (попытка {attempt+1})")
            if attempt == 4:
                return None
    return None

def update_history(chat_id, meme_url):
    """Добавляет URL мема в историю пользователя, удаляет старые"""
    with settings_lock:
        if chat_id not in user_settings:
            user_settings[chat_id] = {'allow_nsfw': False, 'category': 'random', 'history': deque(maxlen=HISTORY_SIZE)}
        hist = user_settings[chat_id].get('history')
        if hist is None:
            user_settings[chat_id]['history'] = deque(maxlen=HISTORY_SIZE)
            hist = user_settings[chat_id]['history']
        hist.append(meme_url)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or 'message' not in data:
        return 'OK', 200

    message = data['message']
    chat_id = message['chat']['id']
    text = message.get('text', '')

    # Инициализация пользователя
    with settings_lock:
        if chat_id not in user_settings:
            user_settings[chat_id] = {'allow_nsfw': False, 'category': 'random', 'history': deque(maxlen=HISTORY_SIZE)}

    user = user_settings[chat_id]
    current_category = user.get('category', 'random')
    allow_nsfw = user.get('allow_nsfw', False)

    # Обработка команд и кнопок
    if text == '/start' or text == '🏠 Меню':
        send_message(chat_id, "📋 Главное меню. Выберите категорию мемов:", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    elif text == '➡️ Следующий мем':
        # Используем текущую категорию
        meme = fetch_meme(current_category, allow_nsfw, user['history'])
        if not meme:
            send_message(chat_id, "Не удалось получить новый мем. Попробуйте позже.", reply_markup=get_main_keyboard(chat_id))
            return 'OK', 200
        update_history(chat_id, meme['url'])
        title = meme.get('title', 'Мем')
        author = meme.get('author', 'Неизвестный автор')
        nsfw_tag = " 🔞 NSFW" if meme.get('nsfw', False) else ""
        caption = f"{title}\nАвтор: {author}{nsfw_tag}"
        send_photo(chat_id, meme['url'], caption, reply_markup=get_after_meme_keyboard(chat_id))
        return 'OK', 200

    elif text.startswith('📂 Категория:') or text.startswith('📂 '):
        # Кнопка смены категории – отправляем сообщение с просьбой выбрать из списка
        # Но у нас уже есть все категории в главном меню, поэтому просто показываем главное меню
        send_message(chat_id, "Выберите категорию из кнопок ниже:", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    elif text in CATEGORIES:
        # Пользователь выбрал категорию из списка
        new_category = CATEGORIES[text]
        user['category'] = new_category
        category_display = text
        send_message(chat_id, f"✅ Категория изменена на {category_display}. Теперь отправьте мем.", reply_markup=get_main_keyboard(chat_id))
        # Автоматически отправляем мем из новой категории (опционально)
        meme = fetch_meme(new_category, allow_nsfw, user['history'])
        if meme:
            update_history(chat_id, meme['url'])
            title = meme.get('title', 'Мем')
            author = meme.get('author', 'Неизвестный автор')
            nsfw_tag = " 🔞 NSFW" if meme.get('nsfw', False) else ""
            caption = f"{title}\nАвтор: {author}{nsfw_tag}"
            send_photo(chat_id, meme['url'], caption, reply_markup=get_after_meme_keyboard(chat_id))
        else:
            send_message(chat_id, "Не удалось получить мем для этой категории.", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    elif text in ['🎲 Случайный мем', '/meme']:
        # Старая команда – используем текущую категорию
        meme = fetch_meme(current_category, allow_nsfw, user['history'])
        if not meme:
            send_message(chat_id, "Не удалось получить мем.", reply_markup=get_main_keyboard(chat_id))
            return 'OK', 200
        update_history(chat_id, meme['url'])
        title = meme.get('title', 'Мем')
        author = meme.get('author', 'Неизвестный автор')
        nsfw_tag = " 🔞 NSFW" if meme.get('nsfw', False) else ""
        caption = f"{title}\nАвтор: {author}{nsfw_tag}"
        send_photo(chat_id, meme['url'], caption, reply_markup=get_after_meme_keyboard(chat_id))
        return 'OK', 200

    elif text == '🔞 NSFW: ВЫКЛ' or text == '🔞 NSFW: ВКЛ':
        current = user['allow_nsfw']
        user['allow_nsfw'] = not current
        status_text = "включён" if user['allow_nsfw'] else "выключен"
        send_message(chat_id, f"Режим NSFW {status_text}.", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    elif text == '❓ Помощь':
        help_text = (
            "📖 Доступные действия:\n"
            "• Выберите категорию мемов из главного меню.\n"
            "• После получения мема можно нажать «Следующий мем» — он будет из той же категории.\n"
            "• Кнопка NSFW включает/выключает взрослые мемы (работает только для категорий, где они есть).\n"
            "• Категория «18+» показывает мемы из специального сабреддита.\n"
            "• Бот запоминает последние 20 мемов и старается не повторяться.\n\n"
            "Команды: /start, /meme"
        )
        send_message(chat_id, help_text, reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

    else:
        send_message(chat_id, "Используйте кнопки меню.", reply_markup=get_main_keyboard(chat_id))
        return 'OK', 200

@app.route('/')
def index():
    return "Бот работает", 200

if __name__ == '__main__':
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
        logger.warning("RENDER_EXTERNAL_HOSTNAME не задан")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)