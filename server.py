#!/usr/bin/env python3
"""
Güliz VIP Backend Server
Python stdlib — HMAC auth, flight API, static serving, scheduler
"""
import http.server
import json
import os
import time
import hmac
import hashlib
import base64
import threading
import random
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta

import db  # PostgreSQL modülü

# ============================================================
# HİZMET BÖLGESİ — Gazipaşa, Alanya, Antalya
# ============================================================
SERVICE_AREA_TERMS = [
    # Alanya bölgesi
    "alanya", "mahmutlar", "kargıcak", "kestel", "tosmur", "oba",
    "konaklı", "avsallar", "incekum", "payallar", "türkler",
    "okurcalar", "demirtaş", "kleopatra", "alanya merkez",
    # Gazipaşa bölgesi
    "gazipaşa", "gzp", "kahyalar", "zeytinada", "sugözü", "koru",
    "gözüküçüklü", "çamlıca", "kaledran", "muzkent", "sarıağaç",
    # Antalya merkez
    "antalya", "ayt", "muratpaşa", "konyaaltı", "lara", "şirinyalı",
    "fener", "çağlayan", "antalya havalimanı",
    # Manavgat / Side koridoru
    "manavgat", "side", "ılıca", "çolaklı", "gündoğdu",
    # Serik / Belek
    "serik", "belek", "kadriye",
]

def is_in_service_area(location_text):
    """Verilen konum metninin hizmet bölgesi içinde olup olmadığını kontrol eder."""
    if not location_text or not location_text.strip():
        return False
    lower = location_text.lower().strip()
    for term in SERVICE_AREA_TERMS:
        if term in lower:
            return True
    return False

# ─── Config ───────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8081))
ADMIN_USER = "admin"
ADMIN_PASS = "gulizvip2026"
SECRET_KEY = "guliz-vip-hmac-secret-2026"
TOKEN_TTL = 86400  # 24 hours
FLIGHT_REFRESH_INTERVAL = 300  # 5 minutes
GOOGLE_MAPS_API_KEY = "AIzaSyD-IGkbR6iyxvdeQ_Cfekjks3KOWMD7RKw"

# Admin tarafından belirlenen km başı birim fiyat (varsayılan: 25₺)
UNIT_PRICE = 25.0

# Ana sayfa slider görselleri — varsayılan 3 görsel
SLIDER_IMAGES = [
    {"src": "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?ixlib=rb-4.0.3&w=2074&q=80", "alt": "Gazipaşa Havalimanı"},
    {"src": "https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?ixlib=rb-4.0.3&w=2070&q=80", "alt": "VIP Vito Lüks Transfer"},
    {"src": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?ixlib=rb-4.0.3&w=2073&q=80", "alt": "Alanya Sahil"},
]

# Banka hesap bilgileri — admin panelden güncellenebilir
BANK_ACCOUNTS = {
    "halkbank": {
        "name": "Halkbank",
        "iban": "TR12 0001 2009 4321 1234 5678 90"
    },
    "vakifbank": {
        "name": "VakıfBank",
        "iban": "TR34 0001 5001 2345 6789 0123 45"
    }
}

# Telegram bot konfigürasyonu — admin panelden güncellenebilir
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── Reservation Data ───────────────────────────────────────────────────────────
RESERVATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reservations.json")
RESERVATIONS = []
RESERVATION_ID = 1000

def load_reservations():
    global RESERVATIONS, RESERVATION_ID
    # Önce PostgreSQL dene
    db_reservations = db.load_reservations_from_db()
    if db_reservations is not None:
        RESERVATIONS = db_reservations
        next_id = db.get_next_reservation_id()
        if next_id:
            RESERVATION_ID = next_id
        print(f"[i] {len(RESERVATIONS)} rezervasyon PostgreSQL'den yüklendi.")
        return
    # Yoksa JSON dosyasına düş
    try:
        if os.path.exists(RESERVATIONS_FILE):
            with open(RESERVATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                RESERVATIONS = data.get("reservations", [])
                RESERVATION_ID = data.get("next_id", 1000)
    except Exception as e:
        print(f"[!] Rezervasyon dosyası yüklenemedi: {e}")
        RESERVATIONS = []
        RESERVATION_ID = 1000

def save_reservations():
    try:
        with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"reservations": RESERVATIONS, "next_id": RESERVATION_ID}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Rezervasyon kaydedilemedi: {e}")

WORKSPACE = os.path.dirname(os.path.abspath(__file__))

# ─── Flight Data (Simulated) ──────────────────────────────────────────────────

GZP_FLIGHTS_GELEN = [
    {"saat": "07:30", "flight": "XC 3001", "from": "Moskova (VKO)", "airline": "Corendon", "status": "Bekleniyor", "code": "expected"},
    {"saat": "08:45", "flight": "TK 2592", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "10:15", "flight": "PC 2034", "from": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "12:00", "flight": "XC 3003", "from": "Tel Aviv (TLV)", "airline": "Corendon", "status": "Bekleniyor", "code": "expected"},
    {"saat": "14:30", "flight": "TK 2594", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "16:45", "flight": "PC 2036", "from": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "19:00", "flight": "XC 3005", "from": "Helsinki (HEL)", "airline": "Corendon", "status": "Bekleniyor", "code": "expected"},
    {"saat": "21:15", "flight": "TK 2596", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "23:00", "flight": "PC 2038", "from": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
]

GZP_FLIGHTS_GIDEN = [
    {"saat": "08:00", "flight": "XC 3002", "to": "Moskova (VKO)", "airline": "Corendon", "status": "Bekleniyor", "code": "expected"},
    {"saat": "09:15", "flight": "TK 2593", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "10:45", "flight": "PC 2035", "to": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "12:30", "flight": "XC 3004", "to": "Tel Aviv (TLV)", "airline": "Corendon", "status": "Bekleniyor", "code": "expected"},
    {"saat": "15:00", "flight": "TK 2595", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "17:15", "flight": "PC 2037", "to": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "19:30", "flight": "XC 3006", "to": "Helsinki (HEL)", "airline": "Corendon", "status": "Bekleniyor", "code": "expected"},
    {"saat": "21:45", "flight": "TK 2597", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "23:30", "flight": "PC 2039", "to": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
]

AYT_FLIGHTS_GELEN = [
    {"saat": "06:00", "flight": "TK 2408", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "07:15", "flight": "PC 4001", "from": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "08:30", "flight": "XQ 9101", "from": "Berlin (BER)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
    {"saat": "10:00", "flight": "TK 2410", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "11:20", "flight": "PC 4003", "from": "Ankara (ESB)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "12:45", "flight": "XQ 9103", "from": "Amsterdam (AMS)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
    {"saat": "14:00", "flight": "TK 2412", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "15:30", "flight": "PC 4005", "from": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "17:00", "flight": "XQ 9105", "from": "Düsseldorf (DUS)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
    {"saat": "18:30", "flight": "TK 2414", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "20:00", "flight": "PC 4007", "from": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "22:00", "flight": "TK 2416", "from": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "23:30", "flight": "XQ 9107", "from": "Munih (MUC)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
]

AYT_FLIGHTS_GIDEN = [
    {"saat": "07:00", "flight": "TK 2409", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "08:00", "flight": "PC 4002", "to": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "09:15", "flight": "XQ 9102", "to": "Berlin (BER)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
    {"saat": "10:30", "flight": "TK 2411", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "12:00", "flight": "PC 4004", "to": "Ankara (ESB)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "13:30", "flight": "XQ 9104", "to": "Amsterdam (AMS)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
    {"saat": "14:45", "flight": "TK 2413", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "16:00", "flight": "PC 4006", "to": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "17:45", "flight": "XQ 9106", "to": "Düsseldorf (DUS)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
    {"saat": "19:00", "flight": "TK 2415", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "20:30", "flight": "PC 4008", "to": "İstanbul (SAW)", "airline": "Pegasus", "status": "Bekleniyor", "code": "expected"},
    {"saat": "22:30", "flight": "TK 2417", "to": "İstanbul (IST)", "airline": "Turkish Airlines", "status": "Bekleniyor", "code": "expected"},
    {"saat": "23:59", "flight": "XQ 9108", "to": "Munih (MUC)", "airline": "SunExpress", "status": "Bekleniyor", "code": "expected"},
]

# ─── OpenSky Network API ──────────────────────────────────────────────────────────

AIRPORT_NAMES = {
    "LTGZ": "Gazipaşa (GZP)", "LTAI": "Antalya (AYT)",
    "LTBA": "İstanbul (IST)", "LTFM": "İstanbul (IST)", "LTFJ": "İstanbul (SAW)",
    "LTAC": "Ankara (ESB)", "LTBJ": "İzmir (ADB)", "LTBS": "Dalaman (DLM)",
    "LTBR": "Bursa (YEI)", "LTAF": "Adana (ADA)", "LTAU": "Kayseri (ASR)",
    "LTCP": "Balıkesir (BZI)",
    "EDDL": "Düsseldorf (DUS)", "EDDB": "Berlin (BER)", "EDDF": "Frankfurt (FRA)",
    "EDDM": "Münih (MUC)", "EDDK": "Köln (CGN)",
    "EHAM": "Amsterdam (AMS)",
    "UUEE": "Moskova (SVO)", "UUDD": "Moskova (DME)", "UUWW": "Moskova (VKO)",
    "LLBG": "Tel Aviv (TLV)", "EFHK": "Helsinki (HEL)",
    "ESSA": "Stockholm (ARN)", "ENGM": "Oslo (OSL)", "EKCH": "Kopenhag (CPH)",
    "EPWA": "Varşova (WAW)", "LKPR": "Prag (PRG)", "LOWW": "Viyana (VIE)",
    "LSZH": "Zürih (ZRH)", "LEBL": "Barselona (BCN)", "LEMD": "Madrid (MAD)",
    "LIRF": "Roma (FCO)", "LIML": "Milano (LIN)", "LPPT": "Lizbon (LIS)",
    "LFPG": "Paris (CDG)", "LFPO": "Paris (ORY)",
    "EGLL": "Londra (LHR)", "EGKK": "Londra (LGW)", "EGSS": "Londra (STN)",
}

AIRLINE_NAMES = {
    "THY": "Turkish Airlines", "TK": "Turkish Airlines",
    "PGT": "Pegasus", "PC": "Pegasus",
    "SXS": "SunExpress", "XQ": "SunExpress",
    "CAI": "Corendon", "XC": "Corendon",
    "FH": "Freebird",
}

OPENSKY_BASE = "https://opensky-network.org/api"
OPENSKY_LAST_CALL = 0.0
OPENSKY_MIN_INTERVAL = 12

def _icao_to_name(icao):
    return AIRPORT_NAMES.get(icao, icao)

def _callsign_to_airline(callsign):
    c = callsign.upper().strip()
    if len(c) >= 3 and c[:3] in AIRLINE_NAMES:
        return AIRLINE_NAMES[c[:3]]
    if len(c) >= 2 and c[:2] in AIRLINE_NAMES:
        return AIRLINE_NAMES[c[:2]]
    return c

def _fetch_opensky_flights(airport_icao, is_arrival):
    global OPENSKY_LAST_CALL
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    today_end = today_start + timedelta(days=1)
    begin_ts = int(today_start.timestamp())
    end_ts = int(today_end.timestamp())
    elapsed = time.time() - OPENSKY_LAST_CALL
    if elapsed < OPENSKY_MIN_INTERVAL:
        time.sleep(OPENSKY_MIN_INTERVAL - elapsed)
    endpoint = "arrival" if is_arrival else "departure"
    url = f"{OPENSKY_BASE}/flights/{endpoint}?airport={airport_icao}&begin={begin_ts}&end={end_ts}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GulizVIP/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        OPENSKY_LAST_CALL = time.time()
    except Exception as e:
        print(f"[!] OpenSky {airport_icao} {endpoint}: {e}")
        return None
    if not isinstance(data, list) or len(data) == 0:
        return None
    flights = []
    seen = set()
    for f in data:
        callsign = (f.get("callsign") or "").strip()
        if not callsign or callsign in seen:
            continue
        seen.add(callsign)
        ts = f.get("lastSeen" if is_arrival else "firstSeen")
        if not ts:
            continue
        flight_time = datetime.fromtimestamp(ts)
        saat = flight_time.strftime("%H:%M")
        callsign_upper = callsign.upper().replace(" ", "")
        airline = _callsign_to_airline(callsign_upper)
        if is_arrival:
            origin = _icao_to_name(f.get("estDepartureAirport") or "")
            entry = {"saat": saat, "flight": callsign_upper, "from": origin, "to": "", "airline": airline, "status": "Bekleniyor", "code": "expected"}
        else:
            dest = _icao_to_name(f.get("estArrivalAirport") or "")
            entry = {"saat": saat, "flight": callsign_upper, "from": "", "to": dest, "airline": airline, "status": "Bekleniyor", "code": "expected"}
        entry["type"] = _classify_flight_type(entry)
        flights.append(entry)
    flights.sort(key=lambda x: (0 if x["type"] == "ic" else 1))
    return flights[:10]

# ─── In-Memory Cache ──────────────────────────────────────────────────────────

flight_cache = {"gzp": {"gelen": [], "giden": [], "updated_at": None}, "ayt": {"gelen": [], "giden": [], "updated_at": None}}

# ─── Live Chat ──────────────────────────────────────────────────────────────────
CHAT_MESSAGES = []
CHAT_ID = 1

# ─── Telegram Bot ─────────────────────────────────────────────────────────────────
def send_telegram(message):
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode("utf-8")
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[!] Telegram mesajı gönderilemedi: {e}")
        return False

def _classify_flight_type(flight):
    turkish_codes = ["(IST)", "(SAW)", "(ESB)", "(ADB)", "(AYT)", "(GZP)", "(DLM)"]
    loc = flight.get("from", "") or flight.get("to", "")
    return "ic" if any(code in loc for code in turkish_codes) else "dis"

def refresh_flights():
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    airports = {"gzp": {"icao": "LTGZ"}, "ayt": {"icao": "LTAI"}}
    for airport_key, ap in airports.items():
        icao = ap["icao"]
        real_gelen = _fetch_opensky_flights(icao, is_arrival=True)
        real_giden = _fetch_opensky_flights(icao, is_arrival=False)
        if real_gelen is not None and real_giden is not None:
            def apply_status(flight, is_arrival):
                f_min = int(flight["saat"].split(":")[0]) * 60 + int(flight["saat"].split(":")[1])
                c_min = int(current_time.split(":")[0]) * 60 + int(current_time.split(":")[1])
                diff = c_min - f_min
                ft = flight
                if diff < -30:
                    ft["status"] = "Bekleniyor"; ft["code"] = "expected"
                elif -30 <= diff < 0:
                    ft["status"] = "Zamanında"; ft["code"] = "expected"
                elif 0 <= diff < 20:
                    ft["status"] = "İndi" if is_arrival else "Kapı Kapandı"
                    ft["code"] = "landed" if is_arrival else "departed"
                elif 20 <= diff < 60:
                    ft["status"] = "İndi" if is_arrival else "Biniş Başladı"
                    ft["code"] = "landed" if is_arrival else "expected"
                elif 60 <= diff < 120:
                    ft["status"] = "İndi" if is_arrival else "Kapı Kapandı"
                    ft["code"] = "landed" if is_arrival else "departed"
                else:
                    if random.random() < 0.15:
                        delay = random.randint(10, 45)
                        new_time = (datetime.strptime(flight["saat"], "%H:%M") + timedelta(minutes=delay)).strftime("%H:%M")
                        ft["status"] = f"Rötarlı ({new_time})"; ft["code"] = "delayed"
                    else:
                        ft["status"] = "Zamanında"; ft["code"] = "expected"
                return ft
            flight_cache[airport_key] = {"gelen": [apply_status(dict(f), True) for f in real_gelen], "giden": [apply_status(dict(f), False) for f in real_giden], "updated_at": now.isoformat()}
            print(f"[{current_time}] {airport_key.upper()}: OpenSky'den {len(real_gelen)} gelen / {len(real_giden)} giden")
        else:
            mock_gelen = GZP_FLIGHTS_GELEN if airport_key == "gzp" else AYT_FLIGHTS_GELEN
            mock_giden = GZP_FLIGHTS_GIDEN if airport_key == "gzp" else AYT_FLIGHTS_GIDEN
            def get_status(flight_saat, is_arrival):
                ft = flight_saat.split(":")
                ct = current_time.split(":")
                f_min = int(ft[0]) * 60 + int(ft[1])
                c_min = int(ct[0]) * 60 + int(ct[1])
                diff = c_min - f_min
                if diff < -30:
                    return ("Bekleniyor", "expected")
                elif -30 <= diff < 0:
                    return ("Zamanında", "expected")
                elif 0 <= diff < 20:
                    return ("İndi", "landed") if is_arrival else ("Kapı Kapandı", "departed")
                elif 20 <= diff < 60:
                    return ("İndi", "landed") if is_arrival else ("Biniş Başladı", "expected")
                elif 60 <= diff < 120:
                    return ("İndi", "landed") if is_arrival else ("Kapı Kapandı", "departed")
                else:
                    if random.random() < 0.15:
                        delay = random.randint(10, 45)
                        new_time = (datetime.strptime(flight_saat, "%H:%M") + timedelta(minutes=delay)).strftime("%H:%M")
                        return (f"Rötarlı ({new_time})", "delayed")
                    return ("Zamanında", "expected") if is_arrival else ("Biniş Başladı", "expected")
            def process_flights(flights, is_arrival):
                result = []
                for f in flights:
                    stat_text, stat_code = get_status(f["saat"], is_arrival)
                    entry = dict(f)
                    entry["status"] = stat_text
                    entry["code"] = stat_code
                    entry["type"] = _classify_flight_type(f)
                    result.append(entry)
                result.sort(key=lambda x: (0 if x["type"] == "ic" else 1))
                return result[:10]
            flight_cache[airport_key] = {"gelen": process_flights(mock_gelen, True), "giden": process_flights(mock_giden, False), "updated_at": now.isoformat()}
            print(f"[{current_time}] {airport_key.upper()}: Mock veri kullanıldı")

def scheduler_loop():
    while True:
        refresh_flights()
        time.sleep(FLIGHT_REFRESH_INTERVAL)

# ─── HMAC Auth ────────────────────────────────────────────────────────────────

def generate_token(username):
    expiry = int(time.time()) + TOKEN_TTL
    payload = f"{username}:{expiry}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')}.{token}"

def verify_token(token):
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64 = parts[0]
        sig_b64 = parts[1]
        payload_b64_pad = payload_b64 + "=" * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else payload_b64
        sig_b64_pad = sig_b64 + "=" * (4 - len(sig_b64) % 4) if len(sig_b64) % 4 else sig_b64
        payload_bytes = base64.urlsafe_b64decode(payload_b64_pad)
        payload = payload_bytes.decode()
        username, expiry_str = payload.split(":", 1)
        expiry = int(expiry_str)
        if time.time() > expiry:
            return None
        expected_sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).digest()
        sig_bytes = base64.urlsafe_b64decode(sig_b64_pad)
        if hmac.compare_digest(expected_sig, sig_bytes):
            return username
    except Exception:
        pass
    return None

# ─── HTTP Handler ─────────────────────────────────────────────────────────────

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
}

class GulizHandler(http.server.BaseHTTPRequestHandler):

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message, status=400):
        self._send_json({"error": message}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length).decode("utf-8")
        return ""

    def _parse_path(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, dict(urllib.parse.parse_qsl(parsed.query))

    def _authenticate(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            return verify_token(token)
        return None

    def _serve_static(self, filepath):
        full_path = os.path.join(WORKSPACE, filepath)
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            self._send_error("Dosya bulunamadı", 404)
            return
        ext = os.path.splitext(filepath)[1].lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        path, params = self._parse_path()
        if path == "/api/flights":
            self._send_json({"success": True, "data": {"gzp": flight_cache["gzp"], "ayt": flight_cache["ayt"]}, "updated_at": max(flight_cache["gzp"]["updated_at"] or "", flight_cache["ayt"]["updated_at"] or "")})
            return
        if path == "/api/maps/config":
            self._send_json({"success": True, "apiKey": GOOGLE_MAPS_API_KEY})
            return
        if path == "/api/unit-price":
            self._send_json({"success": True, "unitPrice": UNIT_PRICE})
            return
        if path == "/api/slider-images":
            self._send_json({"success": True, "images": SLIDER_IMAGES})
            return
        if path == "/api/bank-accounts":
            self._send_json({"success": True, "accounts": BANK_ACCOUNTS})
            return
        if path == "/api/maps/distance":
            origins = params.get("origins", "")
            destinations = params.get("destinations", "")
            mode = params.get("mode", "driving")
            if not origins or not destinations:
                self._send_error("origins ve destinations parametreleri gereklidir.")
                return
            google_url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={urllib.parse.quote(origins)}&destinations={urllib.parse.quote(destinations)}&mode={mode}&language=tr&key={GOOGLE_MAPS_API_KEY}"
            try:
                req = urllib.request.Request(google_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self._send_json({"success": data["status"] == "OK", "data": data})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return
        if path == "/api/maps/geocode":
            address = params.get("address", "")
            if not address:
                self._send_error("address parametresi gereklidir.")
                return
            google_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&language=tr&key={GOOGLE_MAPS_API_KEY}"
            try:
                req = urllib.request.Request(google_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self._send_json({"success": data["status"] == "OK", "data": data})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return
        if path == "/api/admin/flights":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim. Lütfen giriş yapın.", 401)
                return
            self._send_json({"success": True, "data": {"gzp": flight_cache["gzp"], "ayt": flight_cache["ayt"]}})
            return
        if path == "/api/admin/check":
            user = self._authenticate()
            if user:
                self._send_json({"success": True, "user": user})
            else:
                self._send_json({"success": False}, 401)
            return
        if path == "/api/admin/reservations":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            self._send_json({"success": True, "reservations": RESERVATIONS})
            return
        if path == "/api/admin/telegram/config":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            self._send_json({"success": True, "config": {"botToken": TELEGRAM_BOT_TOKEN[:8] + "..." if TELEGRAM_BOT_TOKEN else "", "chatId": TELEGRAM_CHAT_ID}})
            return
        if path == "/api/chat/messages":
            since = params.get("since")
            if since:
                try:
                    since_id = int(since)
                    messages = [m for m in CHAT_MESSAGES if m["id"] > since_id]
                except ValueError:
                    messages = CHAT_MESSAGES
            else:
                messages = CHAT_MESSAGES
            self._send_json({"success": True, "messages": messages})
            return
        if path == "/api/admin/chat/messages":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            self._send_json({"success": True, "messages": CHAT_MESSAGES, "unread": sum(1 for m in CHAT_MESSAGES if not m.get("read") and not m.get("isAdmin"))})
            return
        if path == "/" or path == "":
            self._serve_static("index.html")
        elif path.startswith("/"):
            self._serve_static(path.lstrip("/"))
        else:
            self._send_error("Bulunamadı", 404)

    def do_POST(self):
        path, _ = self._parse_path()
        if path == "/api/admin/login":
            try:
                body = json.loads(self._read_body())
                username = body.get("username", "")
                password = body.get("password", "")
                if username == ADMIN_USER and password == ADMIN_PASS:
                    token = generate_token(username)
                    self._send_json({"success": True, "token": token, "user": username})
                else:
                    self._send_error("Kullanıcı adı veya şifre hatalı.", 401)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/slider-images/upload":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._send_error("multipart/form-data gerekli.", 400)
                return
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)
            boundary = content_type.split('boundary=')[1].strip()
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
            boundary_bytes = ('--' + boundary).encode()
            parts = raw.split(boundary_bytes)
            file_data = None
            file_filename = None
            alt_text = 'Slider Görseli'
            for part in parts:
                if b'Content-Disposition' not in part:
                    continue
                if b'name="file"' in part:
                    for line in part.split(b'\r\n'):
                        if b'filename=' in line:
                            fn = line.split(b'filename=')[1].strip().strip(b'"').decode()
                            file_filename = fn
                            break
                    header_end = part.find(b'\r\n\r\n')
                    if header_end > 0:
                        content_end = part.rfind(b'\r\n--')
                        if content_end == -1:
                            content_end = len(part)
                        file_data = part[header_end + 4:content_end].rstrip(b'\r\n')
                elif b'name="alt"' in part:
                    header_end = part.find(b'\r\n\r\n')
                    if header_end > 0:
                        content_end = part.rfind(b'\r\n--')
                        if content_end == -1:
                            content_end = len(part)
                        val = part[header_end + 4:content_end].strip().decode()
                        if val:
                            alt_text = val
            if not file_data or not file_filename:
                self._send_error("Dosya gönderilmedi.", 400)
                return
            slider_dir = os.path.join(WORKSPACE, 'slider')
            os.makedirs(slider_dir, exist_ok=True)
            ext = os.path.splitext(file_filename)[1] or '.jpg'
            unique_name = f"{int(time.time() * 1000)}{ext}"
            filepath = os.path.join(slider_dir, unique_name)
            with open(filepath, 'wb') as f:
                f.write(file_data)
            global SLIDER_IMAGES
            img_entry = {"src": f"/slider/{unique_name}", "alt": alt_text}
            SLIDER_IMAGES.append(img_entry)
            self._send_json({"success": True, "image": img_entry, "images": SLIDER_IMAGES})
            return
        if path == "/api/reservations":
            try:
                body = json.loads(self._read_body())
                global RESERVATION_ID
                reservation = {
                    "id": RESERVATION_ID,
                    "type": body.get("type", "transfer"),
                    "customerName": body.get("customerName", ""),
                    "customerPhone": body.get("customerPhone", ""),
                    "pickup": body.get("pickup", ""),
                    "destination": body.get("destination", ""),
                    "flightNumber": body.get("flightNumber", ""),
                    "date": body.get("date", ""),
                    "time": body.get("time", ""),
                    "passengers": body.get("passengers", 1),
                    "duration": body.get("duration", ""),
                    "notes": body.get("notes", ""),
                    "price": body.get("price", 0),
                    "status": "pending",
                    "createdAt": datetime.now().isoformat()
                }
                if not reservation["customerName"] or not reservation["pickup"]:
                    self._send_error("Ad ve alış noktası zorunludur.", 400)
                    return
                # Hizmet bölgesi doğrulama
                pickup_ok = is_in_service_area(reservation["pickup"])
                dest_ok = is_in_service_area(reservation["destination"]) if reservation["destination"] else True
                if not pickup_ok:
                    self._send_error("Üzgünüz, bu alış noktası hizmet bölgemiz dışındadır. Yalnızca Gazipaşa, Alanya ve Antalya bölgelerinde hizmet vermekteyiz.", 400)
                    return
                if not dest_ok:
                    self._send_error("Üzgünüz, bu varış noktası hizmet bölgemiz dışındadır. Yalnızca Gazipaşa, Alanya ve Antalya bölgelerinde hizmet vermekteyiz.", 400)
                    return
                db_id = db.save_reservation_to_db(reservation)
                if db_id:
                    reservation["id"] = db_id
                    RESERVATION_ID = db_id + 1
                else:
                    RESERVATIONS.insert(0, reservation)
                    RESERVATION_ID += 1
                    save_reservations()
                self._send_json({"success": True, "reservation": reservation})
                tip_etiket = "🚗 Transfer" if reservation["type"] == "transfer" else "👑 Şoförlü Günlük VIP"
                telegram_rez = (
                    f"🆕 <b>Yeni Rezervasyon #{reservation['id']}</b>\n"
                    f"📋 <b>Tür:</b> {tip_etiket}\n"
                    f"👤 <b>İsim:</b> {reservation['customerName']}\n"
                    f"📞 <b>Telefon:</b> {reservation['customerPhone']}\n"
                    f"📍 <b>Alış:</b> {reservation['pickup']}\n"
                    f"🏁 <b>Varış:</b> {reservation['destination']}\n"
                    f"📅 <b>Tarih:</b> {reservation['date']} {reservation['time']}\n"
                    f"👥 <b>Kişi:</b> {reservation['passengers']}\n"
                    f"💰 <b>Ücret:</b> {reservation['price']}₺\n"
                    f"🕐 <b>Oluşturulma:</b> {reservation['createdAt']}"
                )
                if reservation.get("flightNumber"):
                    telegram_rez += f"\n✈️ <b>Uçuş:</b> {reservation['flightNumber']}"
                send_telegram(telegram_rez)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/telegram/test":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            test_msg = f"✅ <b>Telegram bağlantısı başarılı!</b>\n🕐 Test mesajı: {datetime.now().isoformat()}\n\nGüliz VIP canlı destek ve rezervasyon bildirimleri bu kanala iletilecek."
            success = send_telegram(test_msg)
            if success:
                self._send_json({"success": True, "message": "Test mesajı gönderildi!"})
            else:
                self._send_error("Telegram mesajı gönderilemedi. Bot token ve Chat ID'yi kontrol edin.", 400)
            return
        if path == "/api/chat/send":
            try:
                body = json.loads(self._read_body())
                global CHAT_ID, CHAT_MESSAGES
                msg = {"id": CHAT_ID, "name": body.get("name", ""), "phone": body.get("phone", ""), "message": body.get("message", ""), "timestamp": datetime.now().isoformat(), "isAdmin": False, "adminName": "", "read": False, "sessionId": body.get("sessionId", "")}
                if not msg["message"]:
                    self._send_error("Mesaj boş olamaz.", 400)
                    return
                CHAT_MESSAGES.append(msg)
                CHAT_ID += 1
                if msg["name"] or msg["phone"]:
                    telegram_text = f"🆕 <b>Yeni Canlı Destek Mesajı</b>\n👤 <b>İsim:</b> {msg['name'] or 'Belirtilmemiş'}\n📞 <b>Telefon:</b> {msg['phone'] or 'Belirtilmemiş'}\n💬 <b>Mesaj:</b> {msg['message']}\n🕐 <b>Saat:</b> {msg['timestamp']}"
                else:
                    telegram_text = f"🆕 <b>Yeni Canlı Destek Mesajı</b>\n💬 <b>Mesaj:</b> {msg['message']}\n🕐 <b>Saat:</b> {msg['timestamp']}"
                send_telegram(telegram_text)
                self._send_json({"success": True, "message": msg})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/chat/reply":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                msg = {"id": CHAT_ID, "message": body.get("message", ""), "timestamp": datetime.now().isoformat(), "isAdmin": True, "adminName": user, "read": True, "sessionId": body.get("sessionId", ""), "name": body.get("name", f"Admin ({user})"), "phone": ""}
                if not msg["message"]:
                    self._send_error("Mesaj boş olamaz.", 400)
                    return
                CHAT_MESSAGES.append(msg)
                CHAT_ID += 1
                self._send_json({"success": True, "message": msg})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/chat/read":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                for m in CHAT_MESSAGES:
                    if m.get("sessionId") == session_id and not m.get("isAdmin"):
                        m["read"] = True
                self._send_json({"success": True})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        self._send_error("Bulunamadı", 404)

    def do_PUT(self):
        path, _ = self._parse_path()
        if path == "/api/admin/flights":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                airport = body.get("airport")
                direction = body.get("direction")
                index = body.get("index")
                updates = body.get("updates", {})
                if airport not in ("gzp", "ayt") or direction not in ("gelen", "giden"):
                    self._send_error("Geçersiz parametre.", 400)
                    return
                flights = flight_cache[airport][direction]
                if index is not None and 0 <= index < len(flights):
                    flights[index].update(updates)
                    flight_cache[airport]["updated_at"] = datetime.now().isoformat()
                    self._send_json({"success": True, "flight": flights[index]})
                else:
                    self._send_error("Geçersiz index.", 400)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/unit-price":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                price = float(body.get("unitPrice", 25))
                if price < 1:
                    self._send_error("Fiyat en az 1₺ olmalıdır.", 400)
                    return
                global UNIT_PRICE
                UNIT_PRICE = price
                self._send_json({"success": True, "unitPrice": UNIT_PRICE})
            except (ValueError, TypeError):
                self._send_error("Geçersiz fiyat.", 400)
            return
        if path == "/api/admin/bank-accounts":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                accounts = body.get("accounts", {})
                global BANK_ACCOUNTS
                for key in ("halkbank", "vakifbank"):
                    if key not in accounts:
                        self._send_error(f"'{key}' hesabı eksik.", 400)
                        return
                    if not isinstance(accounts[key], dict) or "name" not in accounts[key] or "iban" not in accounts[key]:
                        self._send_error(f"'{key}' için name ve iban gerekli.", 400)
                        return
                    if not accounts[key]["name"].strip() or not accounts[key]["iban"].strip():
                        self._send_error(f"'{key}' için name ve iban boş olamaz.", 400)
                        return
                BANK_ACCOUNTS = accounts
                self._send_json({"success": True, "accounts": BANK_ACCOUNTS})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/slider-images":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "replace")
                global SLIDER_IMAGES
                if action == "replace":
                    images = body.get("images", [])
                    if not isinstance(images, list):
                        self._send_error("Geçersiz format.", 400)
                        return
                    for img in images:
                        if not isinstance(img, dict) or "src" not in img:
                            self._send_error("Her görsel {src, alt} formatında olmalı.", 400)
                            return
                        if "alt" not in img:
                            img["alt"] = "Slider Görseli"
                    SLIDER_IMAGES = images
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                elif action == "delete":
                    index = body.get("index")
                    if index is None or not isinstance(index, int) or index < 0 or index >= len(SLIDER_IMAGES):
                        self._send_error("Geçersiz index.", 400)
                        return
                    SLIDER_IMAGES.pop(index)
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                elif action == "add":
                    img = body.get("image", {})
                    if not isinstance(img, dict) or "src" not in img:
                        self._send_error("Görsel {src, alt} formatında olmalı.", 400)
                        return
                    if "alt" not in img:
                        img["alt"] = "Slider Görseli"
                    SLIDER_IMAGES.append(img)
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                elif action == "reorder":
                    from_index = body.get("fromIndex")
                    to_index = body.get("toIndex")
                    if from_index is None or to_index is None or not isinstance(from_index, int) or not isinstance(to_index, int):
                        self._send_error("fromIndex ve toIndex gereklidir.", 400)
                        return
                    if from_index < 0 or from_index >= len(SLIDER_IMAGES) or to_index < 0 or to_index >= len(SLIDER_IMAGES):
                        self._send_error("Geçersiz index aralığı.", 400)
                        return
                    img = SLIDER_IMAGES.pop(from_index)
                    SLIDER_IMAGES.insert(to_index, img)
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                else:
                    self._send_error("Bilinmeyen aksiyon: " + action, 400)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/telegram/config":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
                if "botToken" in body:
                    TELEGRAM_BOT_TOKEN = body["botToken"]
                if "chatId" in body:
                    TELEGRAM_CHAT_ID = str(body["chatId"])
                self._send_json({"success": True, "config": {"botToken": TELEGRAM_BOT_TOKEN[:8] + "..." if TELEGRAM_BOT_TOKEN else "", "chatId": TELEGRAM_CHAT_ID}})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/reservations":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                global RESERVATIONS, RESERVATION_ID
                if action == "update-status":
                    res_id = body.get("id")
                    new_status = body.get("status")
                    if new_status not in ("pending", "approved", "completed", "cancelled"):
                        self._send_error("Geçersiz durum.", 400)
                        return
                    if not db.update_reservation_status_in_db(res_id, new_status):
                        found = False
                        for r in RESERVATIONS:
                            if r["id"] == res_id:
                                r["status"] = new_status
                                r["updatedAt"] = datetime.now().isoformat()
                                found = True
                                break
                        if not found:
                            self._send_error("Rezervasyon bulamadi.", 404)
                            return
                        save_reservations()
                    self._send_json({"success": True})
                elif action == "delete":
                    res_id = body.get("id")
                    if not db.delete_reservation_from_db(res_id):
                        found = False
                        for i, r in enumerate(RESERVATIONS):
                            if r["id"] == res_id:
                                RESERVATIONS.pop(i)
                                found = True
                                break
                        if not found:
                            self._send_error("Rezervasyon bulamadi.", 404)
                            return
                        save_reservations()
                    self._send_json({"success": True})
                else:
                    self._send_error("Bilinmeyen aksiyon: " + action, 400)
            except json.JSONDecodeError:
                self._send_error("Gecersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        self._send_error("Bulunamadi", 404)

if __name__ == "__main__":
    db.init_db()
    load_reservations()
    print(f"[i] Toplam {len(RESERVATIONS)} rezervasyon yüklendi.")
    print(f"[i] Sunucu {HOST}:{PORT} üzerinde başlatılıyor...")
    server = http.server.HTTPServer((HOST, PORT), GulizHandler)
    scheduler = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler.start()
    server.serve_forever()
