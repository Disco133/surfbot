import os
import json
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
STORMGLASS_TOKEN = os.getenv("STORMGLASS_TOKEN")
DOMAIN = os.getenv("DOMAIN")  # https://yourapp.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{DOMAIN}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# -----------------------------
# /start
# -----------------------------
@dp.message(CommandStart())
async def start(message: types.Message):
    # создаём кнопку
    kb_button = KeyboardButton(
        text="🗺️ Карта",
        web_app=WebAppInfo(url=f"{DOMAIN}/map/")
    )

    # создаём клавиатуру, обязательно передаём список списков кнопок
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[kb_button]],
        resize_keyboard=True
    )

    await message.answer(
        "🌊 Привет, сёрфер!\n"
        "Я помогу подобрать идеальное время и место для катания.\n\n"
        "📍 Нажми «Карта», чтобы выбрать локацию.",
        reply_markup=keyboard
    )


# -----------------------------
# Обработка данных из WebApp
# -----------------------------
@dp.message(F.web_app_data)
async def process_webapp(message: types.Message):
    data = json.loads(message.web_app_data.data)
    lat = data["lat"]
    lng = data["lng"]

    # Получить название локации через reverse geocoding
    place = await reverse_geocode(lat, lng)

    # Получить прогноз
    forecast = await get_stormglass_forecast(lat, lng)

    await message.answer(f"📍 Локация: {place}\n\n" + forecast)


# -----------------------------
# Reverse Geocoding (OpenStreetMap)
# -----------------------------
async def reverse_geocode(lat, lng):
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            j = await resp.json()
            return j.get("display_name", "Неизвестное место")


# -----------------------------
# StormGlass API
# -----------------------------
async def get_stormglass_forecast(lat, lng):
    url = (
        f"https://api.stormglass.io/v2/weather/point?"
        f"lat={lat}&lng={lng}&params=windSpeed,windDirection,waveHeight,waterTemperature,airTemperature"
    )

    headers = {"Authorization": STORMGLASS_TOKEN}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()

    hours = data.get("hours", [])[:8]  # 8 ближайших часов

    best = None
    best_score = -999

    # Простейшая эвристика
    for hour in hours:
        wv = hour["waveHeight"]["sg"]
        ws = hour["windSpeed"]["sg"]

        score = 0
        if 0.5 < wv < 2.5: score += 2
        if ws < 10: score += 1

        if score > best_score:
            best_score = score
            best = hour

    if not best:
        return "Нет данных"

    t = best["time"][11:16]  # часы:минуты

    msg = (
        f"💨 Ветер: {best['windSpeed']['sg']} м/с\n"
        f"🌊 Волна: {best['waveHeight']['sg']} м\n"
        f"🌡️ Воздух: {best['airTemperature']['sg']}°C\n"
        f"🐚 Вода: {best['waterTemperature']['sg']}°C\n\n"
        f"🕒 Лучший час катания: {t}"
    )

    return msg


# -----------------------------
# Запуск webhook сервера
# -----------------------------
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)


def main():
    app = web.Application()
    SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot, on_startup=on_startup)
    return app


app = main()
