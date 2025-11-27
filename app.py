# app.py
import os
import json
import asyncio
from typing import List, Dict, Any, Tuple

from aiohttp import web
import aiohttp
from aiogram.filters import Command
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
STORMGLASS_API_KEY = os.getenv("STORMGLASS_API_KEY")
DOMAIN = os.getenv("DOMAIN")  # https://your-app.onrender.com
FORECAST_HOURS = int(os.getenv("FORECAST_HOURS", "24"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env")
if not DOMAIN:
    raise RuntimeError("DOMAIN not set in .env (example: https://your-app.onrender.com)")

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# -----------------------
# Bot handlers
# -----------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗺️ Карта",
                    web_app=WebAppInfo(url=f"{DOMAIN}/map/")
                )
            ]
        ]
    )
    await message.answer(
        "🌊 Привет, сёрфер!\n"
        "Я помогу подобрать идеальное время и место для катания.\n\n"
        "📍 Нажми «Карта», чтобы выбрать локацию.",
        reply_markup=kb
    )


@dp.message()
async def handle_webapp_data(message: types.Message):
    print("web_app_data:", message.web_app_data)
    if not message.web_app_data:
        print("не пришло")
        return  # не WebAppData — игнорируем

    try:
        data = json.loads(message.web_app_data.data)
        lat = float(data.get("lat"))
        lng = float(data.get("lng"))
    except Exception as e:
        await message.answer("Не удалось распарсить координаты.")
        return

    await message.answer("Получаю прогноз и анализирую условия...")

    place = await reverse_geocode(lat, lng)

    try:
        hours = await fetch_stormglass(lat, lng, hours=FORECAST_HOURS)
    except Exception as e:
        await message.answer(f"Ошибка при получении прогноза: {e}")
        return

    report = build_report(place, lat, lng, hours)
    await message.answer(report)


# -----------------------
# StormGlass client (simple)
# -----------------------
STORMGLASS_ENDPOINT = "https://api.stormglass.io/v2/weather/point"
PARAMS = [
    "windSpeed", "windDirection",
    "waveHeight", "wavePeriod", "waveDirection",
    "swellHeight", "swellPeriod", "swellDirection",
    "airTemperature", "waterTemperature"
]

async def fetch_stormglass(lat: float, lng: float, hours: int = 24) -> List[Dict[str, Any]]:
    now = aiohttp.helpers.datetime.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    start = now.isoformat() + "Z"
    end = (now + aiohttp.helpers.datetime.timedelta(hours=hours)).isoformat() + "Z"

    params = {
        "lat": str(lat),
        "lng": str(lng),
        "params": ",".join(PARAMS),
        "start": start,
        "end": end
    }
    headers = {"Authorization": STORMGLASS_API_KEY} if STORMGLASS_API_KEY else {}

    async with aiohttp.ClientSession() as session:
        async with session.get(STORMGLASS_ENDPOINT, params=params, headers=headers, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"StormGlass API error {resp.status}: {text}")
            data = await resp.json()
    hours_data = data.get("hours", [])
    # normalize picking first available source for each param
    normalized = []
    for h in hours_data:
        row = {"time": h.get("time")}
        for p in PARAMS:
            val = h.get(p)
            if isinstance(val, dict):
                # pick any source
                chosen = None
                for src in ("noaa", "sg", "gfs", "icon", "nam"):
                    if src in val:
                        chosen = val[src]; break
                if chosen is None:
                    # take first value
                    for v in val.values():
                        chosen = v; break
                row[p] = chosen
            else:
                row[p] = val
        normalized.append(row)
    return normalized

# -----------------------
# Reverse geocoding via Nominatim
# -----------------------
async def reverse_geocode(lat: float, lng: float) -> str:
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"User-Agent":"surf-bot/1.0"}) as resp:
            if resp.status == 200:
                j = await resp.json()
                return j.get("display_name", f"{lat:.4f}, {lng:.4f}")
            else:
                return f"{lat:.4f}, {lng:.4f}"

# -----------------------
# Heuristic scoring and report builder
# -----------------------
def score_hour(h: Dict[str, Any]) -> float:
    # simple heuristic: prefer wave height 0.5-2.5, low wind, longer swell period
    wh = h.get("waveHeight") or 0
    ws = h.get("windSpeed") or 999
    sp = h.get("swellPeriod") or (h.get("wavePeriod") or 0)

    wind_score = max(0, 10 - ws)  # smaller wind is better
    if ws > 12: wind_score *= 0.5
    if 0.5 <= wh <= 2.5:
        wave_score = 10 - abs(1.2 - wh) * 4
    else:
        wave_score = max(0, 2 - abs(wh - 1.2))
    swell_score = min(sp, 14)/14 * 10 if sp else 0
    total = wind_score*0.35 + wave_score*0.45 + swell_score*0.2
    return total

def find_best_block(hours: List[Dict[str, Any]], block_len:int=2) -> Tuple[str,str,float]:
    if not hours:
        return ("","",0.0)
    scores = [score_hour(h) for h in hours]
    best_avg = -1
    best_i = 0
    for i in range(0, len(scores)-block_len+1):
        avg = sum(scores[i:i+block_len])/block_len
        if avg > best_avg:
            best_avg = avg
            best_i = i
    start_iso = hours[best_i]["time"]
    end_iso = hours[min(best_i+block_len-1, len(hours)-1)]["time"]
    return (start_iso, end_iso, best_avg)

def iso_to_hm(iso_ts: str) -> str:
    try:
        # e.g. "2025-11-27T15:00:00+00:00" or "2025-11-27T15:00:00Z"
        dt = aiohttp.helpers.datetime.datetime.fromisoformat(iso_ts.replace("Z","+00:00"))
        return dt.strftime("%H:%M")
    except Exception:
        return iso_ts

def build_report(place: str, lat: float, lng: float, hours: List[Dict[str, Any]]) -> str:
    if not hours:
        return "Нет данных прогноза."

    # current hour = first element
    now = hours[0]
    wind = now.get("windSpeed") or "—"
    wdir = now.get("windDirection") or "—"
    wave = now.get("waveHeight") or "—"
    air = now.get("airTemperature") or "—"
    water = now.get("waterTemperature") or "—"

    start_iso, end_iso, score = find_best_block(hours[:24], block_len=2)
    if start_iso:
        start = iso_to_hm(start_iso)
        end = iso_to_hm(end_iso)
        best_line = f"\n\n🕒 Лучшие часы катания: {start}–{end}\nРейтинг: {score:.2f}"
    else:
        best_line = "\n\n🕒 Не найдено подходящих подряд идущих часов."

    report = (
        f"📍 Пляж: {place}\n\n"
        f"💨 Ветер: {wind} м/с ({int(wdir) if isinstance(wdir,(int,float)) else wdir}°)\n"
        f"🌊 Волна: {wave} м\n"
        f"🌡️ Воздух: {air}°C\n"
        f"🐚 Вода: {water}°C"
        f"{best_line}"
    )
    return report

# -----------------------
# aiohttp web server routes: serve mini app files
# -----------------------
BASE_DIR = os.path.dirname(__file__)
WEBAPP_DIR = os.path.join(BASE_DIR, "webapp")

async def map_page(request):
    return web.FileResponse(os.path.join(WEBAPP_DIR, "index.html"))

async def static_file(request):
    fname = request.match_info.get("filename")
    path = os.path.join(WEBAPP_DIR, fname)
    if os.path.exists(path):
        return web.FileResponse(path)
    raise web.HTTPNotFound()

async def set_webhook_handler(request):
    webhook_url = f"{DOMAIN}/webhook"
    try:
        await bot.set_webhook(webhook_url)
        print("Webhook установлен:", {webhook_url})
        return web.Response(text=f"✅ Webhook установлен: {webhook_url}")
    except Exception as e:
        return web.Response(text=f"❌ Ошибка установки webhook: {e}")

# -----------------------
# Startup: set webhook on Telegram
# -----------------------
async def on_startup(app: web.Application):
    webhook_url = f"{DOMAIN}/webhook"
    await bot.set_webhook(webhook_url)
    print("Webhook set to", webhook_url)

async def on_cleanup(app: web.Application):
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    await bot.session.close()

# -----------------------
# Application factory: register aiohttp routes and aiogram webhook handler
# -----------------------
def create_app():
    app = web.Application()
    # map and static
    app.router.add_get("/map/", map_page)
    app.router.add_get("/map/{filename}", static_file)
    app.router.add_get("/set_webhook", set_webhook_handler)

    # aiogram webhook handler on /webhook
    SimpleRequestHandler(dp, bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot, on_startup=on_startup, on_shutdown=on_cleanup)
    return app

app = create_app()

# If run directly, start aiohttp server
if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
