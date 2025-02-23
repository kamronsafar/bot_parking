import telebot
import sqlite3
import requests
import math
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from config import BOT_TOKEN, DATABASE_FILE, SEARCH_RADIUS_KM

bot = telebot.TeleBot(BOT_TOKEN)
user_locations = {}

def get_parkings_data():
    """Bazadan parkovka ma'lumotlarini olish."""
    try:
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, latitude, longitude, address FROM parkings")
            return [{"name": row[0], "latitude": float(row[1]), "longitude": float(row[2]), "address": row[3]} for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []

def haversine(lat1, lon1, lat2, lon2):
    """Ikki nuqta orasidagi masofani km da hisoblash (Haversine formula)."""
    R = 6371  
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_driving_distance_osrm(origin, destination):
    """OSRM orqali haydash masofasi va vaqtini olish."""
    url = f"http://router.project-osrm.org/route/v1/driving/{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    try:
        response = requests.get(url).json()
        if response.get("code") == "Ok":
            return f"{response['routes'][0]['distance'] / 1000:.1f} km", f"{response['routes'][0]['duration'] / 60:.0f} min"
    except requests.RequestException as e:
        print(f"OSRM API error: {e}")
    return None, None

@bot.message_handler(commands=['start', 'menu'])
def menu(message):
    """Foydalanuvchiga lokatsiya so‘rash tugmasini chiqarish."""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📍 Geolokatsiyani yuborish", request_location=True))
    bot.send_message(message.chat.id, "Quyidagi tugmani bosing:", reply_markup=keyboard)

@bot.message_handler(content_types=['location'])
def handle_location(message):
    """Foydalanuvchi lokatsiyasini qabul qilish va tanlov tugmalarini chiqarish."""
    user_lat, user_lon = message.location.latitude, message.location.longitude
    user_locations[message.chat.id] = (user_lat, user_lon)

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("3 km radiusdagi parkovkalar", "Eng yaqin parkovka")

    bot.send_message(message.chat.id, "Qaysi variantni tanlaysiz?", reply_markup=keyboard)
import time

@bot.message_handler(func=lambda message: message.text == "3 km radiusdagi parkovkalar")
def show_nearby_parkings(message):
    """4 km radiusdagi barcha parkovkalarni chiqarish."""
    user_lat, user_lon = user_locations.get(message.chat.id, (None, None))
    if user_lat is None or user_lon is None:
        bot.send_message(message.chat.id, "📍 Geolokatsiyani yuboring.")
        return

    loading_texts = ["⏳ Yuklanmoqda.", "⏳ Yuklanmoqda..", "⏳ Yuklanmoqda..."]
    loading_message = bot.send_message(message.chat.id, loading_texts[0])

    last_text = loading_texts[0] 
    for i in range(9):  
        new_text = loading_texts[i % 3]
        if new_text != last_text:
            bot.edit_message_text(chat_id=message.chat.id, message_id=loading_message.message_id, text=new_text)
            last_text = new_text

    parkings = get_parkings_data()
    nearby = []

    for p in parkings:
        distance_km = haversine(user_lat, user_lon, p['latitude'], p['longitude'])
        if distance_km <= SEARCH_RADIUS_KM:
            driving_distance, driving_duration = get_driving_distance_osrm((user_lat, user_lon), (p['latitude'], p['longitude']))
            if driving_distance and driving_duration:
                p.update({"driving_distance": driving_distance, "driving_duration": driving_duration})
                nearby.append(p)

    if nearby:
        nearby.sort(key=lambda x: haversine(user_lat, user_lon, x['latitude'], x['longitude']))
        response = "\n\n".join(
            [f"<b>{i+1}. {p['name']}</b>\n"
             f"📍 <a href='http://www.google.com/maps/place/{p['latitude']},{p['longitude']}'>Manzil</a>\n"
             f"🚗 Masofa: {p['driving_distance']}\n"
             f"⏳ Vaqt: {p['driving_duration']}\n"
             f"🏠 Manzil: {p['address']}"
             for i, p in enumerate(nearby)]
        )
    else:
        response = "❌ 4 km radiusda parkovkalar topilmadi."       
    bot.send_message(message.chat.id, response, parse_mode="HTML", disable_web_page_preview=True)
    bot.delete_message(message.chat.id, loading_message.message_id)
    


@bot.message_handler(func=lambda message: message.text == "Eng yaqin parkovka")
def show_nearest_parking(message):
    """Eng yaqin parkovkani chiqarish."""
    user_lat, user_lon = user_locations.get(message.chat.id, (None, None))
    if user_lat is None or user_lon is None:
        bot.send_message(message.chat.id, "Geolokatsiyani yuboring.")
        return
    
    parkings = get_parkings_data()
    if not parkings:
        bot.send_message(message.chat.id, "Parkovkalar bazasi bo‘sh.")
        return

    nearest_parking = min(
        parkings, key=lambda p: haversine(user_lat, user_lon, p['latitude'], p['longitude'])
    )

    driving_distance, driving_duration = get_driving_distance_osrm((user_lat, user_lon), (nearest_parking['latitude'], nearest_parking['longitude']))
    if driving_distance and driving_duration:
        nearest_parking.update({"driving_distance": driving_distance, "driving_duration": driving_duration})

    response = (
        f"<b>{nearest_parking['name']}</b>\n"
        f"📍 <a href='http://www.google.com/maps/place/{nearest_parking['latitude']},{nearest_parking['longitude']}'>Manzil</a>\n"
        f"🚗 Masofa: {nearest_parking['driving_distance']}\n"
        f"⏳ Vaqt: {nearest_parking['driving_duration']}\n"
        f"🏠 Manzil: {nearest_parking['address']}"
    )

    bot.send_message(message.chat.id, response, parse_mode="HTML", disable_web_page_preview=True)

if __name__ == "__main__":
    bot.polling(none_stop=True)
