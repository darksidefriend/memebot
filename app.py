import os
import logging
import threading
import asyncio
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные окружения
TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_TOKEN не задана!")

# Flask приложение для health check
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "Бот работает!", 200

# -------- Логика Telegram-бота ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = (
        "Привет! Я бот, который отправляет случайные мемы.\n"
        "Просто отправь команду /meme и получи порцию юмора!"
    )
    await update.message.reply_text(welcome_text)

async def meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет случайный мем из публичного API"""
    api_url = "https://meme-api.com/gimme"
    try:
        # Таймаут 10 секунд
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()  # выбросит исключение при HTTP ошибке
        data = response.json()

        # Извлекаем данные
        image_url = data.get('url')
        title = data.get('title', 'Без названия')
        author = data.get('author', 'Неизвестный автор')
        caption = f"{title}\nАвтор: {author}"

        if not image_url:
            raise ValueError("В ответе API отсутствует URL изображения")

        # Отправляем фото
        await update.message.reply_photo(photo=image_url, caption=caption)

    except requests.exceptions.Timeout:
        logger.error("Таймаут при запросе к API")
        await update.message.reply_text("Сервер мемов не отвечает. Попробуйте позже.")
    except requests.exceptions.ConnectionError:
        logger.error("Ошибка соединения с API")
        await update.message.reply_text("Не удаётся подключиться к серверу мемов. Проверьте интернет.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP ошибка: {e.response.status_code}")
        await update.message.reply_text(f"Сервер мемов вернул ошибку {e.response.status_code}. Попробуйте позже.")
    except Exception as e:
        logger.exception("Непредвиденная ошибка при получении мема")
        await update.message.reply_text("Произошла ошибка. Попробуйте ещё раз.")

def setup_bot() -> Application:
    """Создаёт и настраивает экземпляр Application для бота"""
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("meme", meme))
    return app

def run_bot_polling():
    """Запускает polling бота в отдельном асинхронном цикле"""
    bot_app = setup_bot()
    # Создаём новый event loop для этого потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Запускаем polling (блокирует поток)
    loop.run_until_complete(bot_app.run_polling())

# -------- Точка входа ----------
if __name__ == '__main__':
    # Запускаем Telegram-бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot_polling, daemon=True)
    bot_thread.start()
    logger.info("Telegram бот запущен в фоновом потоке")

    # Запускаем Flask (основной поток) для health check
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)