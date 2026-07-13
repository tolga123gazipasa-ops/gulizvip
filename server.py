#!/usr/bin/env python3
import sys; sys.stderr.write("[!] server.py loading...\n"); sys.stderr.flush()
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

# PostgreSQL modülü — opsiyonel, yüklenemezse tüm fonksiyonlar None döndürür
try:
    import db
except Exception:
    class _DBStub:
        def __getattr__(self, name):
            return lambda *a, **kw: None
    db = _DBStub()
import uuid
import socket
import traceback
import sys

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
ADMIN_USER = "admin@guliztransfer.com"
ADMIN_PASS = "Guliz2025!"
SECRET_KEY = "guliz-vip-hmac-secret-2026"
TOKEN_TTL = 86400  # 24 hours
FLIGHT_REFRESH_INTERVAL = 300  # 5 minutes
GOOGLE_MAPS_API_KEY = "AIzaSyD-IGkbR6iyxvdeQ_Cfekjks3KOWMD7RKw"

# Admin tarafından belirlenen km başı birim fiyat (varsayılan: 25₺)
UNIT_PRICE = 25.0

# ─── Page Content Fallback (PostgreSQL yoksa kullanılır) ─────────────────
# Slug alias mapping — "mesafelisatis" (no hyphen) → "mesafeli-satis" (with hyphen)
SLUG_ALIASES = {
    "mesafelisatis": "mesafeli-satis",
    "iade": "iade-sartlari",
}

PAGE_CONTENT = {
    "hakkimizda": {
        "title": "Hakkımızda",
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>Güliz VIP Transfer</h2><p>Güliz VIP Transfer olarak, Gazipaşa Havalimanı ve Alanya bölgesinde lüks ve konforlu VIP transfer hizmeti sunuyoruz. Misafirlerimize güvenli, zamanında ve prestijli bir seyahat deneyimi yaşatmak en önemli önceliğimizdir.</p><h2>Vizyonumuz</h2><p>Akdeniz bölgesinin en güvenilir VIP transfer markası olmak. Her yolculuğu konfor ve lüksün buluştuğu unutulmaz bir deneyime dönüştürmek için çalışıyoruz.</p><h2>Misyonumuz</h2><p>Profesyonel ekibimiz ve modern araç filomuzla, misafirlerimize havalimanı transferi ve şoförlü günlük VIP hizmetlerinde kesintisiz, güvenli ve ayrıcalıklı bir deneyim sunmak.</p><h2>Değerlerimiz</h2><ul><li><strong>Güvenlik:</strong> Her yolculukta en üst düzey güvenlik standartları</li><li><strong>Konfor:</strong> Lüks araç filomuzla seyahat konforunda sıfır tolerans</li><li><strong>Zamanında Hizmet:</strong> Uçuş takibi ile %99 zamanında teslimat oranı</li><li><strong>Müşteri Memnuniyeti:</strong> Kişiye özel çözümlerle fark yaratan hizmet anlayışı</li></ul>"
    },
    "gizlilik": {
        "title": "Gizlilik Sözleşmesi",
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>1. Toplanan Bilgiler</h2><p>Güliz VIP Transfer olarak, rezervasyon işlemleri sırasında ad, soyad, telefon numarası, e-posta adresi ve ödeme bilgileri gibi kişisel verilerinizi toplamaktayız. Bu bilgiler yalnızca hizmetlerimizi sağlamak amacıyla kullanılır.</p><h2>2. Bilgi Kullanımı</h2><p>Toplanan kişisel verileriniz; rezervasyonlarınızın yönetilmesi, size özel teklifler sunulması ve müşteri hizmetleri kalitesinin artırılması amacıyla işlenmektedir.</p><h2>3. Bilgi Paylaşımı</h2><p>Kişisel verileriniz, yasal zorunluluklar dışında üçüncü taraflarla paylaşılmaz. Ödeme işlemleri güvenli ödeme altyapımız üzerinden gerçekleştirilir.</p><h2>4. Veri Güvenliği</h2><p>Kişisel verileriniz, endüstri standardı güvenlik önlemleri (SSL, şifreleme) ile korunmaktadır.</p><h2>5. Çerez Politikası</h2><p>Web sitemiz, kullanıcı deneyimini iyileştirmek amacıyla çerezler kullanmaktadır. Çerez ayarlarınızı tarayıcınızdan yönetebilirsiniz.</p><h2>6. Haklarınız</h2><p>KVKK kapsamında; verilerinize erişme, düzeltme, silme ve işleme itiraz etme haklarına sahipsiniz. Talepleriniz için bizimle iletişime geçebilirsiniz.</p>"
    },
    "mesafeli-satis": {
        "title": "Mesafeli Satış Sözleşmesi",
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>1. Taraflar</h2><p>İşbu Mesafeli Satış Sözleşmesi, Güliz VIP Transfer hizmetleri kapsamında web sitesi üzerinden yapılan rezervasyonlar için geçerlidir.</p><h2>2. Hizmet Tanımı</h2><p>VIP havalimanı transferi ve şoförlü günlük VIP araç kiralama hizmetleri, belirtilen tarih, saat ve güzergahta profesyonel şoför eşliğinde lüks araç ile sağlanır.</p><h2>3. Fiyatlandırma</h2><p>Fiyatlandırma, güncel km başı birim fiyat üzerinden hesaplanır. Tüm fiyatlar Türk Lirası (TL) olarak belirtilmiştir ve KDV dahildir.</p><h2>4. Ödeme Koşulları</h2><p>Ödeme, kredi kartı veya banka havalesi ile yapılabilir. Kredi kartı ödemelerinde geçerli kart ağlarının komisyon oranları uygulanır.</p><h2>5. Cayma Hakkı</h2><p>6502 sayılı Tüketicinin Korunması Hakkında Kanun kapsamında, VIP transfer hizmetleri belirli bir tarihte ifası gereken hizmetlerdir. Cayma hakkı kullanımı İade Şartları sayfasında detaylandırılmıştır.</p><h2>6. Sözleşmenin İfası</h2><p>Rezervasyon onaylandıktan sonra hizmet, belirtilen tarih ve saatte başlar. Gecikme ve iptallerde mücbir sebepler dikkate alınır.</p>"
    },
    "teslimat": {
        "title": "Teslimat ve İade Şartları",
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>Teslimat Şartları</h2><p>VIP transfer hizmetimiz, rezervasyon sırasında belirtilen buluşma noktasında, belirtilen tarih ve saatte başlar. Şoförümüz, uçuş takibi sayesinde gecikmelerden haberdar olur ve sizi karşılama alanında bekler.</p><h2>Hizmet Süreci</h2><ul><li>Buluşma noktasında şoför karşılaması</li><li>Bagaj yardımı ve araç yerleştirme</li><li>Konforlu ve güvenli VIP transfer</li><li>Varış noktasına zamanında ulaşım</li></ul><h2>İptal ve İade Koşulları</h2><ul><li><strong>24 saat ve üzeri:</strong> Tam iade</li><li><strong>24 saatten az:</strong> %50 iade</li><li><strong>Hizmet tarihinde:</strong> İade yapılmaz</li></ul><h2>Değişiklikler</h2><p>Rezervasyon tarih, saat veya güzergah değişiklikleri, hizmetten en az 12 saat önce bildirilmelidir. Son dakika değişiklikleri operasyon ekibinin onayına tabidir.</p><h2>Mücbir Sebepler</h2><p>Doğal afet, kötü hava koşulları veya yol kapanması gibi mücbir sebeplerde tam iade veya alternatif tarih seçeneği sunulur.</p>"
    },
    "iade-sartlari": {
        "title": "İade Şartları",
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>İade Politikası</h2><p>Güliz VIP Transfer olarak, müşteri memnuniyetini ön planda tutuyoruz. İşbu iade politikası, web sitemiz üzerinden yapılan rezervasyonlara ilişkin iade ve para iadesi koşullarını düzenlemektedir.</p><h2>1. Cayma Hakkı</h2><p>6502 sayılı Tüketicinin Korunması Hakkında Kanun kapsamında, VIP transfer hizmetleri belirli bir tarihte ifası gereken hizmetler olarak değerlendirildiğinden, cayma hakkı aşağıdaki şartlara tabidir:</p><ul><li><strong>24 saat ve üzeri kala iptal:</strong> Herhangi bir kesinti yapılmaksızın tam iade sağlanır.</li><li><strong>24 saatten az kala iptal:</strong> Ödenen tutarın %50'si iade edilir.</li><li><strong>Hizmet tarihinde iptal veya gelinmemesi:</strong> İade yapılmaz.</li></ul><h2>2. İade Süreci</h2><p>İade talebinizi aşağıdaki kanallardan bize iletebilirsiniz:</p><ul><li><strong>E-posta:</strong> info@gulizvip.com.tr</li><li><strong>Telefon:</strong> +90 242 606 25 48</li><li><strong>WhatsApp:</strong> +90 242 606 25 48</li></ul><p>İade talebiniz operasyon ekibimiz tarafından değerlendirilir ve en geç 3 iş günü içinde tarafınıza dönüş yapılır.</p><h2>3. İade Yöntemleri</h2><p>Onaylanan iadeler, kullanılan ödeme yöntemine göre aşağıdaki şekilde gerçekleştirilir:</p><ul><li><strong>Kredi Kartı:</strong> iyzico altyapısı üzerinden 3-7 iş günü içinde kartınıza iade edilir.</li><li><strong>Havale / EFT:</strong> Banka hesabınıza 3-5 iş günü içinde yatırılır.</li></ul><h2>4. Değişiklik ve Düzeltmeler</h2><p>Rezervasyon tarih, saat veya güzergah değişiklikleri, hizmet tarihinden en az 12 saat önce bildirilmesi koşuluyla ücretsiz olarak yapılabilir. Son dakika değişiklikleri operasyon ekibimizin onayına tabidir ve ek ücret gerektirebilir.</p><h2>5. Mücbir Sebep</h2><p>Doğal afet, kötü hava koşulları, yol kapanması, grev veya benzeri mücbir sebepler nedeniyle hizmetin ifa edilememesi durumunda, müşteriye tam iade veya alternatif tarihte hizmet seçeneği sunulur.</p><h2>6. İletişim</h2><p>İade ve değişiklik talepleriniz için bizimle iletişime geçebilirsiniz:</p><p>Telefon: +90 242 606 25 48<br>E-posta: info@gulizvip.com.tr<br>Adres: Gazipaşa / Antalya</p>"
    }
}

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
# ─── Visitor Tracking (Görünmez Ajan) ────────────────────────────────────────
VISITOR_SESSIONS = {}
visitor_lock = threading.Lock()
VISITOR_SESSION_TIMEOUT = 30  # seconds before marking offline
VISITOR_SESSION_CLEANUP = 300  # seconds before removing stale session

# Telegram bot konfigürasyonu — admin panelden güncellenebilir
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── Reservation Data ───────────────────────────────────────────────────────────
RESERVATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reservations.json")
RESERVATIONS = []
RESERVATION_ID = 1000

# ─── Price Data (Rota Fiyatları) ────────────────────────────────────────────────
PRICES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices.json")
ROUTE_PRICES = []
TAHSIS_PRICES = {}

# ─── Page Content File (PostgreSQL yoksa fallback) ─────────────────────────────────
PAGE_CONTENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page_content.json")


def load_page_content():
    """page_content.json dosyasından sayfa içeriklerini yükle, PAGE_CONTENT dict'ine aktar."""
    global PAGE_CONTENT
    try:
        if os.path.exists(PAGE_CONTENT_FILE):
            with open(PAGE_CONTENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and len(data) > 0:
                    # Sadece bilinen slug'ları al, bilinmeyenleri atla
                    known_slugs = {"hakkimizda", "gizlilik", "mesafeli-satis", "teslimat", "iade-sartlari"}
                    for slug in known_slugs:
                        if slug in data and data[slug].get("title") and data[slug].get("content"):
                            PAGE_CONTENT[slug] = {"title": data[slug]["title"], "content": data[slug]["content"]}
                    print(f"[✓] load_page_content() başarılı — {len(data)} sayfa yüklendi")
    except Exception as e:
        print(f"[!] Sayfa içerik dosyası yüklenemedi: {e}")


def save_page_content_to_json():
    """PAGE_CONTENT dict'ini page_content.json dosyasına yaz (PostgreSQL fallback)."""
    try:
        with open(PAGE_CONTENT_FILE, "w", encoding="utf-8") as f:
            json.dump(PAGE_CONTENT, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Sayfa içeriği JSON'a kaydedilemedi: {e}")


def load_prices():
    global ROUTE_PRICES, TAHSIS_PRICES
    try:
        if os.path.exists(PRICES_FILE):
            with open(PRICES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                ROUTE_PRICES = data.get("route_prices", [])
                TAHSIS_PRICES = data.get("tahsis_prices", {})
    except Exception as e:
        print(f"[!] Fiyat dosyası yüklenemedi: {e}")
        ROUTE_PRICES = []
        TAHSIS_PRICES = {}

def save_prices():
    try:
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump({"route_prices": ROUTE_PRICES, "tahsis_prices": TAHSIS_PRICES}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Fiyat kaydedilemedi: {e}")

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


def _get_visitor_ip(handler):
    """Extract real visitor IP from request headers."""
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = handler.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    client, _ = handler.client_address
    return client


def _format_duration(seconds):
    """Format seconds to human-readable duration string."""
    if seconds < 60:
        return f"{int(seconds)}sn"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}d {secs:02d}sn"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}s {mins:02d}d {secs:02d}sn"


def _cleanup_offline_sessions():
    """Remove stale visitor sessions that have been offline too long."""
    now = time.time()
    with visitor_lock:
        stale = []
        for sid, visitor in VISITOR_SESSIONS.items():
            last = visitor.get("lastHeartbeat", 0)
            if last > 0 and (now - last) > VISITOR_SESSION_CLEANUP:
                stale.append(sid)
        for sid in stale:
            del VISITOR_SESSIONS[sid]
        if stale:
            print(f"[tracking] {len(stale)} eski ziyaretçi oturumu temizlendi")


def _send_telegram_visitor_identify(visitor):
    """Send Telegram notification when a visitor is identified."""
    msg = (
        f"\U0001f441 <b>Görünmez Ajan — Yeni Ziyaretçi</b>\n"
        f"\U0001f310 <b>IP:</b> {visitor.get('ip', '?')}\n"
        f"\U0001f4cd <b>Konum:</b> {visitor.get('city', '?')}, {visitor.get('country', '?')}\n"
        f"\U0001f4f1 <b>Cihaz:</b> {visitor.get('device', '?')} / {visitor.get('os', '?')}\n"
        f"\U0001f30d <b>Tarayıcı:</b> {visitor.get('browser', '?')}\n"
        f"\U0001f6aa <b>Giriş:</b> {visitor.get('entryPage', '?')}\n"
        f"\U0001f517 <b>Yönlendiren:</b> {visitor.get('referrer', 'Doğrudan')}\n"
        f"\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}"
    )
    send_telegram(msg)


def _send_telegram_visitor_event(visitor, event):
    """Send Telegram notification for critical visitor events."""
    label = event.get("label", "Bilinmeyen")
    detail = event.get("detail", "")
    page = event.get("page", "?")
    msg = (
        f"⚠️ <b>Ziyaretçi Etkinliği: {label}</b>\n"
        f"\U0001f464 <b>IP:</b> {visitor.get('ip', '?')}\n"
        f"\U0001f4cd <b>Konum:</b> {visitor.get('city', '?')}, {visitor.get('country', '?')}\n"
        f"\U0001f4c4 <b>Sayfa:</b> {page}\n"
    )
    if detail:
        msg += f"\U0001f4dd <b>Detay:</b> {detail}\n"
    msg += f"\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}"
    send_telegram(msg)


def visitor_cleanup_loop():
    while True:
        time.sleep(15)
        _cleanup_offline_sessions()

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
        # ─── Railway Healthcheck ──────────────────────────────────────────
        if path == "/_health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
            return
        if path == "/api/flights":
            self._send_json({"success": True, "data": {"gzp": flight_cache["gzp"], "ayt": flight_cache["ayt"]}, "updated_at": max(flight_cache["gzp"]["updated_at"] or "", flight_cache["ayt"]["updated_at"] or "")})
            return
        if path == "/api/maps/config":
            self._send_json({"success": True, "apiKey": GOOGLE_MAPS_API_KEY})
            return
        if path == "/api/unit-price":
            self._send_json({"success": True, "unitPrice": UNIT_PRICE})
            return
        if path == "/api/route-prices":
            self._send_json({"success": True, "prices": ROUTE_PRICES})
            return
        if path == "/api/tahsis-prices":
            self._send_json({"success": True, "prices": TAHSIS_PRICES})
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

        if path == "/api/admin/dashboard-stats":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            total = len(RESERVATIONS)
            pending = sum(1 for r in RESERVATIONS if r.get("status") == "pending")
            today_str = datetime.now().strftime("%Y-%m-%d")
            this_month_str = datetime.now().strftime("%Y-%m")
            today_transfers = sum(
                1 for r in RESERVATIONS
                if r.get("createdAt", "").startswith(today_str)
                and r.get("status") in ("pending", "approved", "completed")
            )
            unread_chat = sum(1 for m in CHAT_MESSAGES if not m.get("read") and not m.get("isAdmin"))
            monthly_revenue = sum(
                (r.get("price", 0) or 0)
                for r in RESERVATIONS
                if r.get("createdAt", "").startswith(this_month_str)
                and r.get("status") in ("approved", "completed")
            )
            now_ts = time.time()
            online_count = 0
            with visitor_lock:
                for v in VISITOR_SESSIONS.values():
                    last = v.get("lastHeartbeat", 0)
                    if last > 0 and (now_ts - last) < VISITOR_SESSION_TIMEOUT:
                        online_count += 1
            recent = sorted(RESERVATIONS, key=lambda x: x.get("createdAt", ""), reverse=True)[:5]
            self._send_json({
                "success": True,
                "totalReservations": total,
                "pendingReservations": pending,
                "todayTransfers": today_transfers,
                "unreadChat": unread_chat,
                "monthlyRevenue": monthly_revenue,
                "onlineVisitors": online_count,
                "recentReservations": recent,
                "updatedAt": datetime.now().isoformat()
            })
            return

        if path == "/api/admin/dashboard":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            now = time.time()
            online_count = 0
            with visitor_lock:
                for v in VISITOR_SESSIONS.values():
                    last = v.get("lastHeartbeat", 0)
                    if last > 0 and (now - last) < VISITOR_SESSION_TIMEOUT:
                        online_count += 1
            pending = sum(1 for r in RESERVATIONS if r.get("status") == "pending")
            approved = sum(1 for r in RESERVATIONS if r.get("status") == "approved")
            completed = sum(1 for r in RESERVATIONS if r.get("status") == "completed")
            cancelled = sum(1 for r in RESERVATIONS if r.get("status") == "cancelled")
            unread_chat = sum(1 for m in CHAT_MESSAGES if not m.get("read") and not m.get("isAdmin"))

            today_str = datetime.now().strftime("%Y-%m-%d")
            this_month_str = datetime.now().strftime("%Y-%m")
            daily_revenue = sum(
                (r.get("price", 0) or 0)
                for r in RESERVATIONS
                if r.get("createdAt", "").startswith(today_str)
                and r.get("status") in ("approved", "completed")
            )
            monthly_revenue = sum(
                (r.get("price", 0) or 0)
                for r in RESERVATIONS
                if r.get("createdAt", "").startswith(this_month_str)
                and r.get("status") in ("approved", "completed")
            )
            today_transfers = sum(
                1 for r in RESERVATIONS
                if r.get("createdAt", "").startswith(today_str)
                and r.get("status") in ("pending", "approved")
            )
            recent = sorted(RESERVATIONS, key=lambda x: x.get("createdAt", ""), reverse=True)[:5]
            self._send_json({
                "success": True,
                "pending": pending,
                "today": today_transfers,
                "unreadChat": unread_chat,
                "monthlyRevenue": monthly_revenue,
                "dailyRevenue": daily_revenue,
                "todayTransfers": today_transfers,
                "recentReservations": recent,
                "onlineVisitors": online_count,
            })
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

        if path == "/api/admin/radar":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            with visitor_lock:
                now = time.time()
                visitors_list = []
                for sid, v in VISITOR_SESSIONS.items():
                    entry_time = v.get("entryTime", 0)
                    last_heartbeat = v.get("lastHeartbeat", 0)
                    elapsed = (now - entry_time) if entry_time else 0
                    online = bool(last_heartbeat and (now - last_heartbeat) < VISITOR_SESSION_TIMEOUT)
                    events = v.get("events", [])
                    last_event = events[-1].get("label", "") if events else ""
                    visitor_data = {
                        "sessionId": sid, "ip": v.get("ip", ""),
                        "city": v.get("city", ""), "country": v.get("country", ""),
                        "region": v.get("region", ""), "device": v.get("device", ""),
                        "os": v.get("os", ""), "browser": v.get("browser", ""),
                        "currentPage": v.get("currentPage", ""), "entryPage": v.get("entryPage", ""),
                        "referrer": v.get("referrer", ""), "entryTime": entry_time,
                        "lastHeartbeat": last_heartbeat, "elapsed": elapsed,
                        "elapsedFormatted": _format_duration(elapsed),
                        "online": online, "duration": _format_duration(elapsed),
                        "lastEvent": last_event, "events": events,
                        "chatName": v.get("chatName", ""), "chatPhone": v.get("chatPhone", ""),
                        "name": v.get("name", ""),
                        "email": v.get("email", ""),
                        "reservationId": v.get("reservationId", ""),
                    }
                    visitors_list.append(visitor_data)
                visitors_list.sort(key=lambda x: x.get("lastHeartbeat", 0), reverse=True)
            self._send_json({"success": True, "visitors": visitors_list, "onlineCount": sum(1 for v in visitors_list if v["online"])})
            return
        if path == "/api/track/location":
            ip = params.get("ip", "")
            if not ip:
                self._send_error("IP parametresi gerekli.", 400)
                return
            try:
                ip_url = f"http://ip-api.com/json/{ip}?fields=status,message,city,region,country,query,lat,lon,isp,org,as,timezone,mobile,proxy"
                req = urllib.request.Request(ip_url, headers={"User-Agent": "GulizVIP/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    geo_data = json.loads(resp.read().decode("utf-8"))
                self._send_json({"success": geo_data.get("status") == "success", "data": geo_data})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return
        if path == "/api/chat/messages":
            since = params.get("since")
            session_id = params.get("sessionId")
            if since:
                try:
                    since_id = int(since)
                    messages = [m for m in CHAT_MESSAGES if m["id"] > since_id]
                except ValueError:
                    messages = CHAT_MESSAGES
            else:
                messages = CHAT_MESSAGES
            if session_id:
                messages = [m for m in messages if m.get("sessionId") == session_id]
            self._send_json({"success": True, "messages": messages})
            return
        if path == "/api/admin/chat/messages":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            self._send_json({"success": True, "messages": CHAT_MESSAGES, "unread": sum(1 for m in CHAT_MESSAGES if not m.get("read") and not m.get("isAdmin"))})
            return
        if path == "/api/admin/chat/history":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            session_id = params.get("sessionId", "")
            if not session_id:
                self._send_error("sessionId parametresi gereklidir.", 400)
                return
            filtered = [
                m for m in CHAT_MESSAGES
                if m.get("sessionId") == session_id
            ]
            filtered.sort(key=lambda x: x.get("id", 0))
            self._send_json({"success": True, "messages": filtered, "sessionId": session_id})
            return
        if path == "/api/admin/destinations":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                active_only = params.get("active_only", [None])[0] if params else None
                dests = db.get_destinations(active_only=(active_only == "1" or active_only == "true"))
                if dests is None:
                    dests = []
                self._send_json({"success": True, "destinations": dests})
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path.startswith("/api/page/"):
            slug = path[len("/api/page/"):]
            slug = SLUG_ALIASES.get(slug, slug)
            if slug not in PAGE_CONTENT:
                self._send_error("Sayfa bulunamadı.", 404)
                return
            # DB'den almayı dene, yoksa fallback kullan
            try:
                db_page = db.get_page_content(slug)
                if db_page and db_page.get("title") and db_page.get("content"):
                    self._send_json({"success": True, "page": {"title": db_page["title"], "content": db_page["content"]}})
                    return
            except Exception as e:
                print(f"[!] API sayfa okuma ({slug}) DB hatası: {e}")
            # JSON dosyasından okumayı dene (PostgreSQL yoksa veya boş döndüyse)
            try:
                if os.path.exists(PAGE_CONTENT_FILE):
                    with open(PAGE_CONTENT_FILE, "r", encoding="utf-8") as f:
                        json_data = json.load(f)
                        if slug in json_data and json_data[slug].get("title") and json_data[slug].get("content"):
                            self._send_json({"success": True, "page": {"title": json_data[slug]["title"], "content": json_data[slug]["content"]}})
                            return
            except Exception as e:
                print(f"[!] API sayfa okuma ({slug}) JSON fallback hatası: {e}")
            self._send_json({"success": True, "page": PAGE_CONTENT[slug]})
            return
        if path.startswith("/sayfa/"):
            self._serve_static("page.html")
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
                    "customerEmail": body.get("customerEmail", ""),
                    "pickup": body.get("pickup", ""),
                    "destination": body.get("destination", ""),
                    "flightNumber": body.get("flightNumber", ""),
                    "date": body.get("date", ""),
                    "time": body.get("time", ""),
                    "passengers": body.get("passengers", 1),
                    "duration": body.get("duration", ""),
                    "notes": body.get("notes", ""),
                    "price": body.get("price", 0),
                    "paymentMethod": body.get("paymentMethod", "havale"),
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
                # Identity matching — eşleşen ziyaretçiyi güncelle
                rez_session_id = body.get("sessionId", "")
                if rez_session_id:
                    with visitor_lock:
                        if rez_session_id in VISITOR_SESSIONS:
                            name_parts = reservation.get("customerName", "").split()
                            short_name = name_parts[0] + " " + (name_parts[1][0] + "." if len(name_parts) > 1 else "") if name_parts else reservation.get("customerName", "")
                            email_val = reservation.get("customerEmail", "")
                            display_name = f"{short_name} ({email_val})" if email_val else short_name
                            VISITOR_SESSIONS[rez_session_id]["name"] = display_name
                            VISITOR_SESSIONS[rez_session_id]["email"] = email_val
                            VISITOR_SESSIONS[rez_session_id]["reservationId"] = str(reservation["id"])
                            print(f"[tracking] Identity matched: session {rez_session_id} → {display_name}")
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
                    telegram_text = f"🆕 <b>Yeni Canlı Destek Mesajı</b>\n👤 <b>İsim:</b> {msg['name'] or 'Belirtilmemiş'}\n📞 <b>Telefon:</b> {msg['phone'] or 'Belirtilmemiş'}\n💬 <b>Mesaj:</b> {msg['message']}\n🆔 <b>Session:</b> <code>{msg['sessionId']}</code>\n🕐 <b>Saat:</b> {msg['timestamp']}\n\n⚠️ <b>Müşteriye iletilmesi için lütfen bu mesaja YANITLA (Reply) diyerek cevap veriniz.</b>"
                else:
                    telegram_text = f"🆕 <b>Yeni Canlı Destek Mesajı</b>\n💬 <b>Mesaj:</b> {msg['message']}\n🆔 <b>Session:</b> <code>{msg['sessionId']}</code>\n🕐 <b>Saat:</b> {msg['timestamp']}\n\n⚠️ <b>Müşteriye iletilmesi için lütfen bu mesaja YANITLA (Reply) diyerek cevap veriniz.</b>"
                send_telegram(telegram_text)
                self._send_json({"success": True, "message": msg})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/telegram-webhook":
            try:
                body = json.loads(self._read_body())
                update = body.get("message", {})
                reply_to = update.get("reply_to_message")
                message_text = update.get("text", "")
                if not reply_to or not message_text:
                    self._send_json({"ok": True})
                    return
                replied_text = reply_to.get("text", "") or reply_to.get("caption", "") or ""
                import re
                session_match = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', replied_text)
                if not session_match:
                    self._send_json({"ok": True})
                    return
                matched_session_id = session_match.group(1)
                sender_name = update.get("from", {}).get("first_name", "Telegram Admin")
                msg = {
                    "id": CHAT_ID,
                    "name": "Güliz Asistan",
                    "phone": "",
                    "message": message_text,
                    "timestamp": datetime.now().isoformat(),
                    "isAdmin": True,
                    "adminName": "",
                    "read": True,
                    "sessionId": matched_session_id
                }
                CHAT_MESSAGES.append(msg)
                CHAT_ID += 1
                print(f"[telegram-webhook] Reply session {matched_session_id}: \"{message_text[:60]}\"")
                self._send_json({"ok": True})
            except Exception as e:
                print(f"[!] Telegram webhook hatası: {e}")
                self._send_json({"ok": True})
            return
        if path == "/api/admin/chat/send":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                message_text = body.get("message", "")
                if not message_text:
                    self._send_error("Mesaj boş olamaz.", 400)
                    return
                msg = {
                    "id": CHAT_ID,
                    "message": message_text,
                    "timestamp": datetime.now().isoformat(),
                    "isAdmin": True,
                    "adminName": "",
                    "read": True,
                    "sessionId": session_id,
                    "name": "Güliz Asistan",
                    "phone": ""
                }
                CHAT_MESSAGES.append(msg)
                CHAT_ID += 1
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
                msg = {"id": CHAT_ID, "message": body.get("message", ""), "timestamp": datetime.now().isoformat(), "isAdmin": True, "adminName": "", "read": True, "sessionId": body.get("sessionId", ""), "name": "Güliz Asistan", "phone": ""}
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


        if path == "/api/track/identify":
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                if not session_id:
                    self._send_error("sessionId gerekli.", 400)
                    return
                ip = _get_visitor_ip(self)
                visitor = {
                    "sessionId": session_id,
                    "ip": ip,
                    "device": body.get("device", ""),
                    "os": body.get("os", ""),
                    "browser": body.get("browser", ""),
                    "city": body.get("city", ""),
                    "country": body.get("country", ""),
                    "region": body.get("region", ""),
                    "referrer": body.get("referrer", ""),
                    "entryPage": body.get("entryPage", ""),
                    "currentPage": body.get("entryPage", ""),
                    "entryTime": time.time(),
                    "lastHeartbeat": time.time(),
                    "events": [],
                    "chatName": "",
                    "chatPhone": "",
                    "name": "",
                    "email": "",
                    "reservationId": "",
                }
                with visitor_lock:
                    VISITOR_SESSIONS[session_id] = visitor
                print(f"[tracking] Yeni ziyaretçi: {ip} / {body.get('city', '?')} / {body.get('device', '?')}")
                threading.Thread(target=_send_telegram_visitor_identify, args=(visitor,), daemon=True).start()
                self._send_json({"success": True, "visitorId": session_id})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/track/heartbeat":
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                if not session_id:
                    self._send_error("sessionId gerekli.", 400)
                    return
                with visitor_lock:
                    if session_id in VISITOR_SESSIONS:
                        VISITOR_SESSIONS[session_id]["lastHeartbeat"] = time.time()
                        if body.get("currentPage"):
                            VISITOR_SESSIONS[session_id]["currentPage"] = body["currentPage"]
                        if body.get("chatName"):
                            VISITOR_SESSIONS[session_id]["chatName"] = body["chatName"]
                        if body.get("chatPhone"):
                            VISITOR_SESSIONS[session_id]["chatPhone"] = body["chatPhone"]
                        self._send_json({"success": True})
                    else:
                        self._send_json({"success": False, "error": "Oturum bulunamadı"}, 404)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/track/event":
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                if not session_id:
                    self._send_error("sessionId gerekli.", 400)
                    return
                event = {
                    "label": body.get("label", ""),
                    "detail": body.get("detail", ""),
                    "page": body.get("page", ""),
                    "timestamp": datetime.now().isoformat(),
                    "is_critical": body.get("is_critical", False),
                }
                with visitor_lock:
                    if session_id in VISITOR_SESSIONS:
                        VISITOR_SESSIONS[session_id].setdefault("events", []).append(event)
                        self._send_json({"success": True})
                    else:
                        self._send_json({"success": False, "error": "Oturum bulunamadı"}, 404)
                if body.get("is_critical"):
                    visitor = dict(VISITOR_SESSIONS.get(session_id, {}))
                    threading.Thread(target=_send_telegram_visitor_event, args=(visitor, event), daemon=True).start()
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/chat/delete":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                message_id = body.get("messageId")
                session_id = body.get("sessionId", "")
                if message_id is None:
                    self._send_error("messageId gerekli.", 400)
                    return
                # CHAT_MESSAGES zaten global
                initial_count = len(CHAT_MESSAGES)
                if session_id:
                    CHAT_MESSAGES = [m for m in CHAT_MESSAGES if not (m["id"] == message_id and m.get("sessionId") == session_id)]
                else:
                    CHAT_MESSAGES = [m for m in CHAT_MESSAGES if m["id"] != message_id]
                if len(CHAT_MESSAGES) < initial_count:
                    self._send_json({"success": True, "message": "Mesaj silindi."})
                else:
                    self._send_error("Mesaj bulunamadı.", 404)
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
        if path == "/api/admin/route-prices":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                prices = body.get("prices", [])
                if not isinstance(prices, list):
                    self._send_error("Geçersiz format.", 400)
                    return
                global ROUTE_PRICES
                ROUTE_PRICES = prices
                save_prices()
                self._send_json({"success": True, "prices": ROUTE_PRICES})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/tahsis-prices":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                new_prices = body.get("prices", {})
                if not isinstance(new_prices, dict):
                    self._send_error("Geçersiz format.", 400)
                    return
                global TAHSIS_PRICES
                TAHSIS_PRICES = new_prices
                save_prices()
                self._send_json({"success": True, "prices": TAHSIS_PRICES})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/bank-accounts":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                accounts = body.get("accounts", {})
                if not isinstance(accounts, dict):
                    self._send_error("Geçersiz format.", 400)
                    return
                global BANK_ACCOUNTS
                BANK_ACCOUNTS = accounts
                self._send_json({"success": True, "accounts": BANK_ACCOUNTS})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/slider-images":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                global SLIDER_IMAGES
                if action == "add":
                    image = body.get("image", {})
                    if not image.get("src"):
                        self._send_error("Görsel URL'si gerekli.", 400)
                        return
                    SLIDER_IMAGES.append({"src": image["src"], "alt": image.get("alt", "Slider Görseli")})
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                elif action == "delete":
                    index = body.get("index")
                    if index is None or not isinstance(index, int) or index < 0 or index >= len(SLIDER_IMAGES):
                        self._send_error("Geçersiz index.", 400)
                        return
                    SLIDER_IMAGES.pop(index)
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                elif action == "reorder":
                    from_index = body.get("fromIndex")
                    to_index = body.get("toIndex")
                    if from_index is None or to_index is None:
                        self._send_error("fromIndex ve toIndex gerekli.", 400)
                        return
                    if 0 <= from_index < len(SLIDER_IMAGES) and 0 <= to_index < len(SLIDER_IMAGES):
                        item = SLIDER_IMAGES.pop(from_index)
                        SLIDER_IMAGES.insert(to_index, item)
                        self._send_json({"success": True, "images": SLIDER_IMAGES})
                    else:
                        self._send_error("Geçersiz index aralığı.", 400)
                elif action == "replace":
                    index = body.get("index")
                    image = body.get("image", {})
                    if index is None or not isinstance(index, int) or index < 0 or index >= len(SLIDER_IMAGES):
                        self._send_error("Geçersiz index.", 400)
                        return
                    if not image.get("src"):
                        self._send_error("Görsel URL'si gerekli.", 400)
                        return
                    SLIDER_IMAGES[index] = {"src": image["src"], "alt": image.get("alt", "Slider Görseli")}
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/reservations":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                if action == "update":
                    res_id = body.get("id")
                    if res_id is None:
                        self._send_error("Rezervasyon ID gerekli.", 400)
                        return
                    global RESERVATIONS
                    for r in RESERVATIONS:
                        if r.get("id") == res_id:
                            for key in ("status", "customer_name", "customer_phone", "customer_email",
                                        "pickup", "destination", "flight_number", "date", "time",
                                        "passengers", "notes", "price", "payment_method", "payment_status"):
                                if key in body:
                                    r[key] = body[key]
                            save_reservations()
                            # DB'ye de kaydet
                            try:
                                db.save_reservation_to_db(r)
                            except Exception:
                                pass
                            self._send_json({"success": True, "reservation": r})
                            return
                    self._send_error("Rezervasyon bulunamadı.", 404)
                elif action == "delete":
                    res_id = body.get("id")
                    if res_id is None:
                        self._send_error("Rezervasyon ID gerekli.", 400)
                        return
                    RESERVATIONS = [r for r in RESERVATIONS if r.get("id") != res_id]
                    save_reservations()
                    self._send_json({"success": True, "message": "Rezervasyon silindi."})
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
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
                self._send_json({"success": True, "botToken": TELEGRAM_BOT_TOKEN[:8] + "..." if TELEGRAM_BOT_TOKEN else "",
                                 "chatId": TELEGRAM_CHAT_ID})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/credentials":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                new_user = body.get("username", "")
                new_pass = body.get("password", "")
                if not new_user or not new_pass:
                    self._send_error("Kullanıcı adı ve şifre gerekli.", 400)
                    return
                if len(new_pass) < 6:
                    self._send_error("Şifre en az 6 karakter olmalıdır.", 400)
                    return
                global ADMIN_USER, ADMIN_PASS
                ADMIN_USER = new_user
                ADMIN_PASS = new_pass
                # DB'ye kaydet
                try:
                    db.set_admin_credentials(new_user, new_pass)
                except Exception:
                    pass
                self._send_json({"success": True, "message": "Giriş bilgileri güncellendi."})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path.startswith("/api/admin/page/"):
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            slug = path[len("/api/admin/page/"):]
            slug = SLUG_ALIASES.get(slug, slug)
            if not slug or slug not in PAGE_CONTENT:
                self._send_error("Sayfa bulunamadı.", 404)
                return
            try:
                body = json.loads(self._read_body())
                title = body.get("title", "")
                content = body.get("content", "")
                if not title or not content:
                    self._send_error("Başlık ve içerik gerekli.", 400)
                    return
                
                PAGE_CONTENT[slug] = {"title": title, "content": content}
                # DB'ye de kaydet
                try:
                    db.save_page_content(slug, title, content)
                except Exception as e:
                    print(f"[!] Admin sayfa kaydetme ({slug}) DB hatası: {e}")
                # JSON fallback'e de yaz (her durumda)
                save_page_content_to_json()
                self._send_json({"success": True, "page": PAGE_CONTENT[slug]})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/destinations":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                if action == "add":
                    result = db.save_destination(body)
                    if result:
                        self._send_json({"success": True, "destination": result})
                    else:
                        self._send_error("Destinasyon eklenemedi.", 500)
                elif action == "update":
                    dest_id = body.get("id")
                    if not dest_id:
                        self._send_error("Destinasyon ID gerekli.", 400)
                        return
                    result = db.save_destination(body)
                    if result:
                        self._send_json({"success": True, "destination": result})
                    else:
                        self._send_error("Destinasyon güncellenemedi.", 500)
                elif action == "delete":
                    dest_id = body.get("id")
                    if not dest_id:
                        self._send_error("Destinasyon ID gerekli.", 400)
                        return
                    result = db.delete_destination(dest_id)
                    if result:
                        self._send_json({"success": True, "message": "Destinasyon silindi."})
                    else:
                        self._send_error("Destinasyon silinemedi.", 500)
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        self._send_error("Bulunamadı", 404)


if __name__ == "__main__":
    # ─── Başlangıç görevleri: hata olursa çökme, sadece logla ────────
    try:
        load_prices()
        print("[✓] load_prices() başarılı")
    except Exception as e:
        print(f"[!] load_prices() hatası (önemsiz, devam): {e}")

    try:
        load_reservations()
        print("[✓] load_reservations() başarılı")
    except Exception as e:
        print(f"[!] load_reservations() hatası (önemsiz, devam): {e}")

    try:
        load_page_content()
        print("[✓] load_page_content() başarılı")
    except Exception as e:
        print(f"[!] load_page_content() hatası (önemsiz, devam): {e}")

    try:
        threading.Thread(target=refresh_flights, daemon=True).start()
        print("[✓] refresh_flights() thread başlatıldı")
    except Exception as e:
        print(f"[!] refresh_flights() hatası (önemsiz, devam): {e}")

    try:
        threading.Thread(target=scheduler_loop, daemon=True).start()
        print("[✓] scheduler_loop başlatıldı")
    except Exception as e:
        print(f"[!] scheduler_loop hatası (önemsiz, devam): {e}")

    try:
        threading.Thread(target=visitor_cleanup_loop, daemon=True).start()
        print("[✓] visitor_cleanup_loop başlatıldı")
    except Exception as e:
        print(f"[!] visitor_cleanup_loop hatası (önemsiz, devam): {e}")

    # Railway ve Cloud platformlar için ZORUNLU ayarlar:
    # 1. Port dinamik olmalı
    # 2. Host kesinlikle 0.0.0.0 olmalı (127.0.0.1 veya localhost OLMAZ)
    PORT = int(os.environ.get("PORT", 8081))
    host = "0.0.0.0"

    try:
        server = http.server.HTTPServer((host, PORT), GulizHandler)
        print(f"[!] SUNUCU BAŞARILI BİR ŞEKİLDE {host}:{PORT} ÜZERİNDE BAŞLATILDI")  # Bu log çok kritik!
        sys.stdout.flush()
        server.serve_forever()
    except OSError as e:
        print(f"[-] SUNUCU HATASI (OSError): {e}")
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        # Port meşgul olabilir, 2sn bekle ve tekrar dene
        try:
            import time
            time.sleep(2)
            server = http.server.HTTPServer((host, PORT), GulizHandler)
            print(f"[!] 2. DENEMEDE SUNUCU {host}:{PORT} ÜZERİNDE BAŞLATILDI")
            sys.stdout.flush()
            server.serve_forever()
        except Exception as e2:
            print(f"[-] 2. DENEME DE BAŞARISIZ: {e2}")
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
    except Exception as e:
        print(f"[-] SUNUCU HATASI: {e}")
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
