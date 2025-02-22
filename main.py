import math
import sqlite3
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from config import BOT_TOKEN, DATABASE_FILE, SEARCH_RADIUS_KM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)

def get_parkings_data():
    try:
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, latitude, longitude, address FROM parkings")
            return [{"name": row[0], "latitude": float(row[1]), "longitude": float(row[2]), "address":row[3]} for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return []

def haversine(lat1, lon1, lat2, lon2):
    R = 6371 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_driving_distance_osrm(origin, destination):
    url = f"http://router.project-osrm.org/route/v1/driving/{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    try:
        response = requests.get(url).json()
        if response.get("code") == "Ok":
            return f"{response['routes'][0]['distance'] / 1000:.1f} km", f"{response['routes'][0]['duration'] / 60:.0f} min"
    except requests.RequestException as e:
        logger.error(f"OSRM API request error: {e}")
    return None, None

@dp.message_handler(commands=['start', 'menu'])
async def menu(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add(
        KeyboardButton("Geolokatsiyani yuborish", request_location=True)
    )
    await message.answer("Quyidagi menyudan tanlang:", reply_markup=keyboard)

@dp.message_handler(content_types=types.ContentType.LOCATION)
async def handle_location(message: types.Message):
    user_lat, user_lon = message.location.latitude, message.location.longitude
    user_location = (user_lat, user_lon)

    parkings = get_parkings_data()
    nearby = []

    for parking in parkings:
        parking_location = (parking['latitude'], parking['longitude'])
        distance_km = haversine(user_lat, user_lon, parking['latitude'], parking['longitude'])
        if distance_km <= SEARCH_RADIUS_KM:
            driving_distance, driving_duration = get_driving_distance_osrm(user_location, parking_location)
            if driving_distance and driving_duration:
                parking.update({"driving_distance": driving_distance, "driving_duration": driving_duration})
                nearby.append(parking)
    if nearby:
        nearby.sort(key=lambda x: float(x["driving_distance"].split()[0]))
        response = "\n\n".join(
            [f"<b>{i+1}. {parking['name']}</b>\n"
             f"📍 <a href='http://www.google.com/maps/place/{parking['latitude']},{parking['longitude']}'>Manzil</a>\n"
             f"🚗 Masofa: {parking['driving_distance']}\n"
             f"⏳ Vaqt: {parking['driving_duration']}\n"
             f"🏠 Manzil: {parking['address']}"
             for i, parking in enumerate(nearby)]
        )
    else:
        response = f"{SEARCH_RADIUS_KM} km radiusda parkovkalar topilmadi. Radiusni kengaytirish uchun qayta urinib ko'ring."

    await message.answer(response, parse_mode="HTML", disable_web_page_preview=True)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
