# set_webhook.py
import os
import asyncio
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DOMAIN = os.getenv("DOMAIN")

if not BOT_TOKEN or not DOMAIN:
    raise RuntimeError("BOT_TOKEN или DOMAIN не установлены в .env")

bot = Bot(token=BOT_TOKEN)

async def main():
    webhook_url = f"{DOMAIN}/webhook"
    await bot.set_webhook(webhook_url)
    print(f"✅ Webhook установлен: {webhook_url}")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
