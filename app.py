import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set")

app = Flask(__name__)

# Глобальный объект Application (инициализируем позже)
bot_app = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь /meme для мема.")

async def meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        resp = requests.get("https://meme-api.com/gimme", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        url = data.get('url')
        title = data.get('title', 'Мем')
        author = data.get('author', '')
        caption = f"{title}\nАвтор: {author}"
        if url:
            await update.message.reply_photo(photo=url, caption=caption)
        else:
            await update.message.reply_text("Не удалось получить картинку.")
    except Exception as e:
        logger.exception("Ошибка в /meme")
        await update.message.reply_text("Ошибка при загрузке мема. Попробуйте позже.")

@app.route('/webhook', methods=['POST'])
async def webhook():
    if not bot_app:
        return "Bot not ready", 500
    try:
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        await bot_app.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.exception("Webhook error")
        return "Error", 500

@app.route('/')
def index():
    return "Bot is running"

def setup_bot():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("meme", meme))
    return application

if __name__ == '__main__':
    bot_app = setup_bot()
    # Устанавливаем вебхук
    port = int(os.environ.get('PORT', 5000))
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/webhook"
    # В Render имя хоста автоматически подставляется в переменную RENDER_EXTERNAL_HOSTNAME
    # Если её нет, используем домен, который вы видите в URL сервиса
    # Можно задать вручную: webhook_url = "https://ваш-сервис.onrender.com/webhook"
    bot_app.run_webhook(listen="0.0.0.0", port=port, url_path="/webhook", webhook_url=webhook_url)