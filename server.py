#!/usr/bin/env python3
import sys; sys.stderr.write("[!] server.py loading...\n"); sys.stderr.flush()
"""
Güliz VIP Backend Server
Python stdlib — HMAC auth, flight API, static serving, scheduler
"""
import http.server
import json
import os
import re
import time
import hmac
import hashlib
import base64
import threading
import random
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# Railway konteynerleri varsayılan olarak UTC saatiyle çalışır — TZ ayarlanmazsa
# koddaki "02:00 / 13:00" gibi saatler (uçuş scraping, vs.) aslında UTC'de tetiklenir,
# Türkiye saatiyle (UTC+3) 05:00 / 16:00 demek olurdu. datetime.now() Türkiye saatini
# döndürsün diye TZ burada açıkça sabitleniyor (Linux'ta çalışır — Railway Linux).
os.environ["TZ"] = "Europe/Istanbul"
try:
    time.tzset()
except AttributeError:
    pass  # Windows'ta tzset yok (lokal geliştirmede sorun değil, Railway Linux'ta çalışır)

# PostgreSQL modülü — opsiyonel, yüklenemezse tüm fonksiyonlar None döndürür
try:
    import db
except Exception:
    class _DBStub:
        def __getattr__(self, name):
            return lambda *a, **kw: None
    db = _DBStub()
import sys
import uuid
import socket
import traceback
import collections
import ipaddress

# Resend e-posta — opsiyonel, yoksa sessizce atlanır
try:
    import resend
    _RESEND_AVAILABLE = True
except ImportError:
    _RESEND_AVAILABLE = False

# Pillow — görsel otomatik boyutlandırma için opsiyonel, yoksa ham dosya kaydedilir
try:
    from PIL import Image, ImageOps
    import io
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# BeautifulSoup4 — AYT (Antalya Havalimanı) uçuş sayfası HTML parse için gerekli.
# Yoksa AYT scraping sessizce atlanır, önbellekteki son başarılı veri korunur.
try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

# curl_cffi — AYT (antalya-airport.aero) sitesinin TLS/JA3 parmak izi tabanlı bot
# korumasını aşmak için opsiyonel. Yüklü değilse AYT scraping normal urllib
# yöntemine geri döner (GZP hiçbir zaman bundan etkilenmez, kendi JSON API'sini kullanır).
try:
    from curl_cffi import requests as _cffi_requests
    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False

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
# Sunucu tarafı (server-to-server) Google Maps çağrıları için AYRI bir anahtar.
# GOOGLE_MAPS_API_KEY tarayıcıya (/api/maps/config) verilip Maps JS SDK ile
# kullanıldığı için "HTTP referrer" kısıtlamalı — bu kısıtlama türü sunucudan
# sunucuya yapılan isteklerde Google tarafından "API keys with referer
# restrictions cannot be used with this API" hatasıyla reddediliyor (14 Ağustos'ta
# canlıda doğrulandı: admin panelindeki "Google ile Hesapla" özelliği bu yüzden
# çalışmıyordu). Bu yeni anahtar Google Cloud Console'da kısıtlama YOK, sadece
# Distance Matrix + Geocoding API'lerine izinli olacak şekilde oluşturuldu.
# Railway env var yoksa (henüz eklenmediyse) eski anahtara düşer — o durumda da
# aynı hata devam eder, en azından sistem çökmez.
GOOGLE_MAPS_SERVER_API_KEY = os.environ.get("GOOGLE_MAPS_SERVER_API_KEY", GOOGLE_MAPS_API_KEY)

# Admin tarafından belirlenen km başı birim fiyat (varsayılan: 25₺)
UNIT_PRICE = 25.0

# Not: Kredi kartı ödeme entegrasyonu (Odesin) kaldırıldı — banka havalesi ile devam ediliyor.
# İleride farklı bir ödeme sağlayıcısı entegre edilecek.

# ─── Page Content Fallback (PostgreSQL yoksa kullanılır) ─────────────────
# Slug alias mapping — "mesafelisatis" (no hyphen) → "mesafeli-satis" (with hyphen)
SLUG_ALIASES = {
    "mesafelisatis": "mesafeli-satis",
    "iade": "iade-sartlari",
}

PAGE_CONTENT = {
    "hakkimizda": {
        "title": "Hakkımızda",
        "subtitle": "Premium VIP transfer hizmetinin ayrıcalıklı dünyası",
        "is_active": True,
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>Güliz VIP Transfer</h2><p>Güliz VIP Transfer olarak, Gazipaşa Havalimanı ve Alanya bölgesinde lüks ve konforlu VIP transfer hizmeti sunuyoruz. Misafirlerimize güvenli, zamanında ve prestijli bir seyahat deneyimi yaşatmak en önemli önceliğimizdir.</p><h2>Vizyonumuz</h2><p>Akdeniz bölgesinin en güvenilir VIP transfer markası olmak. Her yolculuğu konfor ve lüksün buluştuğu unutulmaz bir deneyime dönüştürmek için çalışıyoruz.</p><h2>Misyonumuz</h2><p>Profesyonel ekibimiz ve modern araç filomuzla, misafirlerimize havalimanı transferi ve şoförlü günlük VIP hizmetlerinde kesintisiz, güvenli ve ayrıcalıklı bir deneyim sunmak.</p><h2>Değerlerimiz</h2><ul><li><strong>Güvenlik:</strong> Her yolculukta en üst düzey güvenlik standartları</li><li><strong>Konfor:</strong> Lüks araç filomuzla seyahat konforunda sıfır tolerans</li><li><strong>Zamanında Hizmet:</strong> Uçuş takibi ile %99 zamanında teslimat oranı</li><li><strong>Müşteri Memnuniyeti:</strong> Kişiye özel çözümlerle fark yaratan hizmet anlayışı</li></ul>"
    },
    "gizlilik": {
        "title": "Gizlilik Sözleşmesi",
        "subtitle": "Kişisel verilerinizin korunması ve işlenmesi hakkında bilgilendirme",
        "is_active": True,
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>1. Toplanan Bilgiler</h2><p>Güliz VIP Transfer olarak, rezervasyon işlemleri sırasında ad, soyad, telefon numarası, e-posta adresi ve ödeme bilgileri gibi kişisel verilerinizi toplamaktayız. Bu bilgiler yalnızca hizmetlerimizi sağlamak amacıyla kullanılır.</p><h2>2. Bilgi Kullanımı</h2><p>Toplanan kişisel verileriniz; rezervasyonlarınızın yönetilmesi, size özel teklifler sunulması ve müşteri hizmetleri kalitesinin artırılması amacıyla işlenmektedir.</p><h2>3. Bilgi Paylaşımı</h2><p>Kişisel verileriniz, yasal zorunluluklar dışında üçüncü taraflarla paylaşılmaz. Ödeme işlemleri güvenli ödeme altyapımız üzerinden gerçekleştirilir.</p><h2>4. Veri Güvenliği</h2><p>Kişisel verileriniz, endüstri standardı güvenlik önlemleri (SSL, şifreleme) ile korunmaktadır.</p><h2>5. Çerez Politikası</h2><p>Web sitemiz, kullanıcı deneyimini iyileştirmek amacıyla çerezler kullanmaktadır. Çerez ayarlarınızı tarayıcınızdan yönetebilirsiniz.</p><h2>6. Haklarınız</h2><p>KVKK kapsamında; verilerinize erişme, düzeltme, silme ve işleme itiraz etme haklarına sahipsiniz. Talepleriniz için bizimle iletişime geçebilirsiniz.</p>"
    },
    "mesafeli-satis": {
        "title": "Mesafeli Satış Sözleşmesi",
        "subtitle": "Online rezervasyon ve satış koşullarına ilişkin sözleşme metni",
        "is_active": True,
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>1. Taraflar</h2><p>İşbu Mesafeli Satış Sözleşmesi, Güliz VIP Transfer hizmetleri kapsamında web sitesi üzerinden yapılan rezervasyonlar için geçerlidir.</p><h2>2. Hizmet Tanımı</h2><p>VIP havalimanı transferi ve şoförlü günlük VIP araç kiralama hizmetleri, belirtilen tarih, saat ve güzergahta profesyonel şoför eşliğinde lüks araç ile sağlanır.</p><h2>3. Fiyatlandırma</h2><p>Fiyatlandırma, güncel km başı birim fiyat üzerinden hesaplanır. Tüm fiyatlar Türk Lirası (TL) olarak belirtilmiştir ve KDV dahildir.</p><h2>4. Ödeme Koşulları</h2><p>Ödeme, kredi kartı veya banka havalesi ile yapılabilir. Kredi kartı ödemelerinde geçerli kart ağlarının komisyon oranları uygulanır.</p><h2>5. Cayma Hakkı</h2><p>6502 sayılı Tüketicinin Korunması Hakkında Kanun kapsamında, VIP transfer hizmetleri belirli bir tarihte ifası gereken hizmetlerdir. Cayma hakkı kullanımı İade Şartları sayfasında detaylandırılmıştır.</p><h2>6. Sözleşmenin İfası</h2><p>Rezervasyon onaylandıktan sonra hizmet, belirtilen tarih ve saatte başlar. Gecikme ve iptallerde mücbir sebepler dikkate alınır.</p>"
    },
    "teslimat": {
        "title": "Teslimat ve İade Şartları",
        "subtitle": "VIP transfer hizmetimizin teslimat ve iade koşulları hakkında detaylı bilgi",
        "is_active": True,
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>Teslimat Şartları</h2><p>VIP transfer hizmetimiz, rezervasyon sırasında belirtilen buluşma noktasında, belirtilen tarih ve saatte başlar. Şoförümüz, uçuş takibi sayesinde gecikmelerden haberdar olur ve sizi karşılama alanında bekler.</p><h2>Hizmet Süreci</h2><ul><li>Buluşma noktasında şoför karşılaması</li><li>Bagaj yardımı ve araç yerleştirme</li><li>Konforlu ve güvenli VIP transfer</li><li>Varış noktasına zamanında ulaşım</li></ul><h2>İptal ve İade Koşulları</h2><ul><li><strong>24 saat ve üzeri:</strong> Tam iade</li><li><strong>24 saatten az:</strong> %50 iade</li><li><strong>Hizmet tarihinde:</strong> İade yapılmaz</li></ul><h2>Değişiklikler</h2><p>Rezervasyon tarih, saat veya güzergah değişiklikleri, hizmetten en az 12 saat önce bildirilmelidir. Son dakika değişiklikleri operasyon ekibinin onayına tabidir.</p><h2>Mücbir Sebepler</h2><p>Doğal afet, kötü hava koşulları veya yol kapanması gibi mücbir sebeplerde tam iade veya alternatif tarih seçeneği sunulur.</p>"
    },
    "iade-sartlari": {
        "title": "İade Şartları",
        "subtitle": "VIP transfer hizmetimizin iade ve para iadesi koşulları",
        "is_active": True,
        "content": "<p class=\"last-updated\">Son Güncelleme: Temmuz 2026</p><h2>İade Politikası</h2><p>Güliz VIP Transfer olarak, müşteri memnuniyetini ön planda tutuyoruz. İşbu iade politikası, web sitemiz üzerinden yapılan rezervasyonlara ilişkin iade ve para iadesi koşullarını düzenlemektedir.</p><h2>1. Cayma Hakkı</h2><p>6502 sayılı Tüketicinin Korunması Hakkında Kanun kapsamında, VIP transfer hizmetleri belirli bir tarihte ifası gereken hizmetler olarak değerlendirildiğinden, cayma hakkı aşağıdaki şartlara tabidir:</p><ul><li><strong>24 saat ve üzeri kala iptal:</strong> Herhangi bir kesinti yapılmaksızın tam iade sağlanır.</li><li><strong>24 saatten az kala iptal:</strong> Ödenen tutarın %50'si iade edilir.</li><li><strong>Hizmet tarihinde iptal veya gelinmemesi:</strong> İade yapılmaz.</li></ul><h2>2. İade Süreci</h2><p>İade talebinizi aşağıdaki kanallardan bize iletebilirsiniz:</p><ul><li><strong>E-posta:</strong> info@gulizvip.com.tr</li><li><strong>Telefon:</strong> +90 242 606 25 48</li><li><strong>WhatsApp:</strong> +90 242 606 25 48</li></ul><p>İade talebiniz operasyon ekibimiz tarafından değerlendirilir ve en geç 3 iş günü içinde tarafınıza dönüş yapılır.</p><h2>3. İade Yöntemleri</h2><p>Onaylanan iadeler, kullanılan ödeme yöntemine göre aşağıdaki şekilde gerçekleştirilir:</p><ul><li><strong>Kredi Kartı:</strong> Garanti BBVA Sanal POS altyapısı üzerinden 3-7 iş günü içinde kartınıza iade edilir.</li><li><strong>Havale / EFT:</strong> Banka hesabınıza 3-5 iş günü içinde yatırılır.</li></ul><h2>4. Değişiklik ve Düzeltmeler</h2><p>Rezervasyon tarih, saat veya güzergah değişiklikleri, hizmet tarihinden en az 12 saat önce bildirilmesi koşuluyla ücretsiz olarak yapılabilir. Son dakika değişiklikleri operasyon ekibimizin onayına tabidir ve ek ücret gerektirebilir.</p><h2>5. Mücbir Sebep</h2><p>Doğal afet, kötü hava koşulları, yol kapanması, grev veya benzeri mücbir sebepler nedeniyle hizmetin ifa edilememesi durumunda, müşteriye tam iade veya alternatif tarihte hizmet seçeneği sunulur.</p><h2>6. İletişim</h2><p>İade ve değişiklik talepleriniz için bizimle iletişime geçebilirsiniz:</p><p>Telefon: +90 242 606 25 48<br>E-posta: info@gulizvip.com.tr<br>Adres: Gazipaşa / Antalya</p>"
    }
}

# ─── Sayfa Çevirileri (İngilizce / Rusça) ───────────────────────────────────────
# Bu 5 içerik sayfası (Hakkımızda, Gizlilik, Mesafeli Satış, Teslimat, İade
# Şartları) için EN/RU çevirileri. NOT: Bunlar AI/makine çevirisidir, admin
# panelinden düzenlenemez — sadece Türkçe (DB'deki) sürüm admin panelinden
# yönetilebilir. Türkçe içerik admin panelinden değiştirilirse buradaki
# çeviriler OTOMATİK GÜNCELLENMEZ, elle senkronize edilmesi gerekir. Mesafeli
# Satış Sözleşmesi gibi yasal metinlerde resmi/hukuki geçerlilik için
# profesyonel çeviri önerilir.
PAGE_TRANSLATIONS = {
    "en": {
        "hakkimizda": {
            "title": "About Us",
            "subtitle": "The privileged world of premium VIP transfer service",
            "content": "<h2>Güliz VIP Transfer</h2><p>At Güliz VIP Transfer, we provide a luxurious and comfortable VIP transfer service in the Gazipaşa Airport and Alanya region. Providing our guests with a safe, punctual and prestigious travel experience is our top priority.</p><h2>Our Vision</h2><p>To become the most trusted VIP transfer brand in the Mediterranean region. We work to turn every journey into an unforgettable experience where comfort meets luxury.</p><h2>Our Mission</h2><p>To offer our guests an uninterrupted, safe and exclusive experience in airport transfer and chauffeured daily VIP services, with our professional team and modern vehicle fleet.</p><h2>Our Values</h2><ul><li><strong>Safety:</strong> The highest safety standards on every journey</li><li><strong>Comfort:</strong> Zero compromise on travel comfort with our luxury vehicle fleet</li><li><strong>Punctuality:</strong> 99% on-time delivery rate thanks to flight tracking</li><li><strong>Customer Satisfaction:</strong> A service approach that stands out with personalized solutions</li></ul>"
        },
        "gizlilik": {
            "title": "Privacy Policy",
            "subtitle": "Information about the protection and processing of your personal data",
            "content": "<h2>1. Information Collected</h2><p>At Güliz VIP Transfer, we collect personal data such as your name, surname, phone number, email address and payment information during the reservation process. This information is used solely to provide our services.</p><h2>2. Use of Information</h2><p>Your collected personal data is processed to manage your reservations, offer you personalized deals, and improve the quality of customer service.</p><h2>3. Sharing of Information</h2><p>Your personal data is not shared with third parties except where legally required. Payment transactions are carried out through our secure payment infrastructure.</p><h2>4. Data Security</h2><p>Your personal data is protected by industry-standard security measures (SSL, encryption).</p><h2>5. Cookie Policy</h2><p>Our website uses cookies to improve the user experience. You can manage your cookie preferences from your browser settings.</p><h2>6. Your Rights</h2><p>Under the Turkish Personal Data Protection Law (KVKK), you have the right to access, correct, delete and object to the processing of your data. You may contact us to exercise these rights.</p>"
        },
        "mesafeli-satis": {
            "title": "Distance Sales Agreement",
            "subtitle": "Terms and conditions governing online reservations and sales",
            "content": "<h2>1. Parties</h2><p>This Distance Sales Agreement is made between the following parties:</p><p><strong>Seller:</strong><br>Company Name: Güliz Lojistik Mimarlık Sanayi ve Tic. Ltd. Şti.<br>Head Office Address: Pazarcı Mah. 10003. Sok. No: 32/7, Gazipaşa/Antalya, Türkiye<br>Gazipaşa Airport Office: Gazipaşa Havalimanı İçi No:3 Sarıağaç, Gazipaşa/Antalya, Türkiye<br>Tax Office: Gazipaşa Mal Müdürlüğü<br>Tax ID (VKN): 4200721970<br>Phone: +90 242 606 25 48<br>Email: info@gulizvip.com.tr</p><p><strong>Buyer:</strong> The individual or legal entity (Customer) making a reservation through the website</p><p>This agreement applies to reservations made through the website within the scope of Güliz VIP Transfer services.</p><h2>2. Description of Service</h2><p>Airport VIP transfer and chauffeured daily VIP vehicle rental services are provided with a luxury vehicle accompanied by a professional driver, on the specified date, time and route.</p><h2>3. Pricing</h2><p>Pricing is calculated based on the current price per kilometer. All prices are stated in Turkish Lira (TL) and include VAT.</p><h2>4. Payment Terms</h2><p>Payment can be made by credit card or bank transfer. Commission rates of the applicable card networks apply to credit card payments.</p><h2>5. Right of Withdrawal</h2><p>Under Turkish Consumer Protection Law No. 6502, VIP transfer services are considered services to be performed at a specific date, and the right of withdrawal is therefore subject to the conditions detailed on the Refund Terms page.</p><h2>6. Performance of the Agreement</h2><p>Once a reservation is confirmed, the service begins on the specified date and time. Force majeure circumstances are taken into account in cases of delay or cancellation.</p>"
        },
        "teslimat": {
            "title": "Delivery and Refund Terms",
            "subtitle": "Detailed information about the delivery and refund conditions of our VIP transfer service",
            "content": "<h2>Delivery Terms</h2><p>Our VIP transfer service begins at the meeting point specified at the time of reservation, on the specified date and time. Thanks to flight tracking, our driver is aware of any delays and waits for you in the arrivals area.</p><h2>Service Process</h2><ul><li>Driver greeting at the meeting point</li><li>Luggage assistance and vehicle boarding</li><li>Comfortable and safe VIP transfer</li><li>Timely arrival at the destination</li></ul><h2>Cancellation and Refund Conditions</h2><ul><li><strong>24 hours or more before:</strong> Full refund</li><li><strong>Less than 24 hours before:</strong> 50% refund</li><li><strong>On the day of service:</strong> No refund</li></ul><h2>Changes</h2><p>Changes to the reservation date, time or route must be notified at least 12 hours before the service. Last-minute changes are subject to the approval of the operations team.</p><h2>Force Majeure</h2><p>In the case of force majeure events such as natural disasters, adverse weather conditions or road closures, a full refund or an alternative date option is offered.</p>"
        },
        "iade-sartlari": {
            "title": "Refund Terms",
            "subtitle": "The refund and reimbursement conditions of our VIP transfer service",
            "content": "<h2>Refund Policy</h2><p>At Güliz VIP Transfer, customer satisfaction is our top priority. This refund policy governs the refund and reimbursement conditions for reservations made through our website.</p><h2>1. Right of Withdrawal</h2><p>Under Turkish Consumer Protection Law No. 6502, VIP transfer services are considered services to be performed at a specific date, and the right of withdrawal is therefore subject to the following conditions:</p><ul><li><strong>Cancellation 24 hours or more before:</strong> A full refund is provided without any deduction.</li><li><strong>Cancellation less than 24 hours before:</strong> 50% of the amount paid is refunded.</li><li><strong>Cancellation on the day of service, or no-show:</strong> No refund is provided.</li></ul><h2>2. Refund Process</h2><p>You can submit your refund request through the following channels:</p><ul><li><strong>Email:</strong> info@gulizvip.com.tr</li><li><strong>Phone:</strong> +90 242 606 25 48</li><li><strong>WhatsApp:</strong> +90 242 606 25 48</li></ul><p>Your refund request will be reviewed by our operations team and you will receive a response within 3 business days at the latest.</p><h2>3. Refund Methods</h2><p>Approved refunds are processed as follows, depending on the payment method used:</p><ul><li><strong>Credit Card:</strong> Refunded to your card within 3-7 business days via Garanti BBVA Sanal POS infrastructure.</li><li><strong>Bank Transfer / EFT:</strong> Deposited to your bank account within 3-5 business days.</li></ul><h2>4. Changes and Corrections</h2><p>Changes to the reservation date, time or route can be made free of charge, provided they are notified at least 12 hours before the service date. Last-minute changes are subject to the approval of our operations team and may incur additional charges.</p><h2>5. Force Majeure</h2><p>In the event that the service cannot be performed due to force majeure such as natural disasters, adverse weather conditions, road closures, strikes or similar events, the customer is offered a full refund or the option of service on an alternative date.</p><h2>6. Contact</h2><p>You may contact us for refund and change requests:</p><p>Phone: +90 242 606 25 48<br>Email: info@gulizvip.com.tr<br>Address: Gazipaşa / Antalya</p>"
        }
    },
    "ru": {
        "hakkimizda": {
            "title": "О нас",
            "subtitle": "Привилегированный мир премиального VIP-трансфера",
            "content": "<h2>Güliz VIP Transfer</h2><p>Компания Güliz VIP Transfer предоставляет роскошные и комфортные VIP-трансферы в районе аэропорта Газипаша и Аланьи. Обеспечение безопасного, пунктуального и престижного путешествия для наших гостей — наш главный приоритет.</p><h2>Наше видение</h2><p>Стать самым надёжным брендом VIP-трансфера в Средиземноморском регионе. Мы стремимся превратить каждую поездку в незабываемый опыт, где комфорт сочетается с роскошью.</p><h2>Наша миссия</h2><p>Благодаря профессиональной команде и современному автопарку предложить нашим гостям бесперебойный, безопасный и эксклюзивный опыт трансфера из аэропорта и услуг VIP-аренды автомобиля с водителем.</p><h2>Наши ценности</h2><ul><li><strong>Безопасность:</strong> высочайшие стандарты безопасности в каждой поездке</li><li><strong>Комфорт:</strong> никаких компромиссов в комфорте благодаря нашему автопарку класса люкс</li><li><strong>Пунктуальность:</strong> 99% случаев прибытия вовремя благодаря отслеживанию рейсов</li><li><strong>Удовлетворённость клиентов:</strong> индивидуальный подход, который выделяет наш сервис</li></ul>"
        },
        "gizlilik": {
            "title": "Политика конфиденциальности",
            "subtitle": "Информация о защите и обработке ваших персональных данных",
            "content": "<h2>1. Собираемая информация</h2><p>Güliz VIP Transfer собирает такие персональные данные, как имя, фамилия, номер телефона, адрес электронной почты и платёжная информация в процессе бронирования. Эта информация используется исключительно для предоставления наших услуг.</p><h2>2. Использование информации</h2><p>Собранные персональные данные обрабатываются для управления вашими бронированиями, предоставления персональных предложений и повышения качества обслуживания клиентов.</p><h2>3. Передача информации</h2><p>Ваши персональные данные не передаются третьим лицам, за исключением случаев, предусмотренных законом. Платёжные операции осуществляются через нашу защищённую платёжную инфраструктуру.</p><h2>4. Безопасность данных</h2><p>Ваши персональные данные защищены отраслевыми стандартами безопасности (SSL, шифрование).</p><h2>5. Политика использования файлов cookie</h2><p>Наш сайт использует файлы cookie для улучшения пользовательского опыта. Вы можете управлять настройками cookie в своём браузере.</p><h2>6. Ваши права</h2><p>В соответствии с турецким Законом о защите персональных данных (KVKK) вы имеете право на доступ, исправление, удаление своих данных и возражение против их обработки. Для реализации этих прав вы можете связаться с нами.</p>"
        },
        "mesafeli-satis": {
            "title": "Договор дистанционной продажи",
            "subtitle": "Условия онлайн-бронирования и продажи услуг",
            "content": "<h2>1. Стороны</h2><p>Настоящий Договор дистанционной продажи заключён между следующими сторонами:</p><p><strong>Продавец:</strong><br>Наименование компании: Güliz Lojistik Mimarlık Sanayi ve Tic. Ltd. Şti.<br>Юридический адрес: Pazarcı Mah. 10003. Sok. No: 32/7, Газипаша/Анталья, Турция<br>Офис в аэропорту Газипаша: Gazipaşa Havalimanı İçi No:3 Sarıağaç, Газипаша/Анталья, Турция<br>Налоговая инспекция: Gazipaşa Mal Müdürlüğü<br>Налоговый номер (VKN): 4200721970<br>Телефон: +90 242 606 25 48<br>Эл. почта: info@gulizvip.com.tr</p><p><strong>Покупатель:</strong> Физическое или юридическое лицо (Клиент), осуществляющее бронирование через сайт</p><p>Настоящий договор применяется к бронированиям, сделанным через сайт в рамках услуг Güliz VIP Transfer.</p><h2>2. Описание услуги</h2><p>Услуги VIP-трансфера из аэропорта и аренды VIP-автомобиля с водителем на день предоставляются на автомобиле класса люкс в сопровождении профессионального водителя, в указанные дату, время и по указанному маршруту.</p><h2>3. Ценообразование</h2><p>Цена рассчитывается на основе текущего тарифа за километр. Все цены указаны в турецких лирах (TL) и включают НДС.</p><h2>4. Условия оплаты</h2><p>Оплата может быть произведена кредитной картой или банковским переводом. При оплате кредитной картой применяются комиссии соответствующих платёжных систем.</p><h2>5. Право на отказ от услуги</h2><p>В соответствии с турецким Законом о защите прав потребителей № 6502, услуги VIP-трансфера считаются услугами, оказываемыми в определённую дату, поэтому право на отказ регулируется условиями, подробно изложенными на странице «Условия возврата».</p><h2>6. Исполнение договора</h2><p>После подтверждения бронирования услуга начинается в указанные дату и время. В случае задержек и отмен учитываются форс-мажорные обстоятельства.</p>"
        },
        "teslimat": {
            "title": "Условия предоставления услуги и возврата",
            "subtitle": "Подробная информация об условиях предоставления и возврата нашей услуги VIP-трансфера",
            "content": "<h2>Условия предоставления услуги</h2><p>Наш VIP-трансфер начинается в указанном при бронировании месте встречи, в указанные дату и время. Благодаря отслеживанию рейсов наш водитель знает о задержках и ожидает вас в зоне прилёта.</p><h2>Процесс обслуживания</h2><ul><li>Встреча с водителем в месте сбора</li><li>Помощь с багажом и посадка в автомобиль</li><li>Комфортный и безопасный VIP-трансфер</li><li>Своевременное прибытие в пункт назначения</li></ul><h2>Условия отмены и возврата</h2><ul><li><strong>За 24 часа и более:</strong> полный возврат</li><li><strong>Менее чем за 24 часа:</strong> возврат 50%</li><li><strong>В день оказания услуги:</strong> возврат не производится</li></ul><h2>Изменения</h2><p>Об изменениях даты, времени или маршрута бронирования необходимо сообщить не менее чем за 12 часов до оказания услуги. Изменения в последнюю минуту подлежат согласованию с операционной командой.</p><h2>Форс-мажор</h2><p>В случае форс-мажорных обстоятельств, таких как стихийные бедствия, неблагоприятные погодные условия или перекрытие дорог, предоставляется полный возврат средств или альтернативная дата оказания услуги.</p>"
        },
        "iade-sartlari": {
            "title": "Условия возврата",
            "subtitle": "Условия возврата и возмещения средств за нашу услугу VIP-трансфера",
            "content": "<h2>Политика возврата</h2><p>Для Güliz VIP Transfer удовлетворённость клиентов — главный приоритет. Настоящая политика возврата регулирует условия возврата и возмещения средств за бронирования, сделанные через наш сайт.</p><h2>1. Право на отказ от услуги</h2><p>В соответствии с турецким Законом о защите прав потребителей № 6502, услуги VIP-трансфера считаются услугами, оказываемыми в определённую дату, поэтому право на отказ подчиняется следующим условиям:</p><ul><li><strong>Отмена за 24 часа и более:</strong> производится полный возврат без каких-либо удержаний.</li><li><strong>Отмена менее чем за 24 часа:</strong> возвращается 50% от уплаченной суммы.</li><li><strong>Отмена в день оказания услуги или неявка:</strong> возврат не производится.</li></ul><h2>2. Процесс возврата</h2><p>Вы можете отправить запрос на возврат через следующие каналы:</p><ul><li><strong>Эл. почта:</strong> info@gulizvip.com.tr</li><li><strong>Телефон:</strong> +90 242 606 25 48</li><li><strong>WhatsApp:</strong> +90 242 606 25 48</li></ul><p>Ваш запрос на возврат будет рассмотрен нашей операционной командой, и вы получите ответ не позднее чем через 3 рабочих дня.</p><h2>3. Способы возврата</h2><p>Одобренные возвраты производятся следующим образом, в зависимости от использованного способа оплаты:</p><ul><li><strong>Кредитная карта:</strong> возврат на карту в течение 3-7 рабочих дней через инфраструктуру Garanti BBVA Sanal POS.</li><li><strong>Банковский перевод:</strong> зачисление на банковский счёт в течение 3-5 рабочих дней.</li></ul><h2>4. Изменения и исправления</h2><p>Изменения даты, времени или маршрута бронирования могут быть внесены бесплатно при условии уведомления не менее чем за 12 часов до даты оказания услуги. Изменения в последнюю минуту подлежат согласованию с нашей операционной командой и могут повлечь дополнительную плату.</p><h2>5. Форс-мажор</h2><p>В случае невозможности оказания услуги вследствие форс-мажорных обстоятельств, таких как стихийные бедствия, неблагоприятные погодные условия, перекрытие дорог, забастовки или подобные события, клиенту предлагается полный возврат средств или возможность получения услуги в альтернативную дату.</p><h2>6. Контакты</h2><p>По вопросам возврата и изменений вы можете связаться с нами:</p><p>Телефон: +90 242 606 25 48<br>Эл. почта: info@gulizvip.com.tr<br>Адрес: Газипаша / Анталья</p>"
        }
    }
}

# ─── SEO: Dinamik Rota Sayfaları (Teknik SEO / Dinamik Rota SEO) ────────────────
# Bu slug'lar gerçek bir alt sayfa değildir — index.html ile AYNI görünür içeriği
# sunar, sadece <title>/<meta description>/canonical/OG/Twitter etiketlerini o
# rotaya özel hale getirir (arama sonuçlarında rotaya özgü başlık/açıklama
# görünmesi ve sitemap.xml'de ayrı URL olarak listelenmesi için). Tam benzersiz
# içerik değildir — ilerleyen aşamada her rota için gerçek, kendine özgü içerik
# eklenmesi SEO açısından daha da güçlü olur.
BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://gulizvip.com.tr")
ROUTE_SEO_PAGES = {
    "gazipasa-alanya-transfer": {
        "title": "Gazipaşa Havalimanı (GZP) - Alanya VIP Transfer | Güliz VIP Transfer",
        "description": "Gazipaşa Havalimanı'ndan (GZP) Alanya'ya 7/24 konforlu, dakik ve lüks Mercedes Vito VIP transfer hizmeti. Uygun fiyat, dövizle ödeme imkanı.",
    },
    "gazipasa-mahmutlar-transfer": {
        "title": "Gazipaşa Havalimanı (GZP) - Mahmutlar VIP Transfer | Güliz VIP Transfer",
        "description": "Gazipaşa Havalimanı'ndan (GZP) Mahmutlar'a 7/24 özel VIP transfer. Karşılama, bagaj yardımı ve konforlu Vito araçlarla güvenli ulaşım.",
    },
    "antalya-alanya-transfer": {
        "title": "Antalya Havalimanı (AYT) - Alanya VIP Transfer | Güliz VIP Transfer",
        "description": "Antalya Havalimanı'ndan (AYT) Alanya'ya lüks, dakik ve konforlu VIP transfer hizmeti. 7/24 hizmet, en uygun fiyat garantisi.",
    },
    "antalya-side-transfer": {
        "title": "Antalya Havalimanı (AYT) - Side VIP Transfer | Güliz VIP Transfer",
        "description": "Antalya Havalimanı'ndan (AYT) Side'ye 7/24 lüks Mercedes Vito VIP transfer. Uçuş takibi, karşılama ve dövizle ödeme imkanı.",
    },
    "antalya-belek-transfer": {
        "title": "Antalya Havalimanı (AYT) - Belek VIP Transfer | Güliz VIP Transfer",
        "description": "Antalya Havalimanı'ndan (AYT) Belek'teki otelinize konforlu, sessiz ve lüks VIP Vito transfer hizmeti. 7/24 rezervasyon.",
    },
    "antalya-kemer-transfer": {
        "title": "Antalya Havalimanı (AYT) - Kemer VIP Transfer | Güliz VIP Transfer",
        "description": "Antalya Havalimanı'ndan (AYT) Kemer'e güvenli, zamanında ve lüks VIP transfer. Mercedes Vito araç filomuzla 7/24 hizmetinizdeyiz.",
    },
    "antalya-manavgat-transfer": {
        "title": "Antalya Havalimanı (AYT) - Manavgat VIP Transfer | Güliz VIP Transfer",
        "description": "Antalya Havalimanı'ndan (AYT) Manavgat'a konforlu VIP transfer hizmeti. 7/24 uçuş takipli, dakik ve lüks ulaşım.",
    },
    # Not: "iletisim", "sss" ve "hizli-rezervasyon" anasayfadaki gerçek bölümlere (#iletisim,
    # #sss, #rezervasyon) karşılık gelir — Google fragment (#) URL'lerini ayrı sayfa saymadığı
    # için bunları sitemap'te anlamlı şekilde listeleyebilmek adına kendi title/description/
    # canonical'ı olan gerçek URL'ler haline getirdik. "anchor" alanı, sayfa açılınca ilgili
    # bölüme otomatik kaydırma yapar.
    "iletisim": {
        "title": "İletişim | Güliz VIP Transfer - Gazipaşa & Antalya Transfer",
        "description": "Güliz VIP Transfer ile iletişime geçin. Telefon, WhatsApp ve e-posta ile 7/24 rezervasyon ve bilgi alın. Gazipaşa (GZP) ve Antalya (AYT) havalimanı VIP transfer hizmeti.",
        "anchor": "iletisim",
    },
    "sss": {
        "title": "Sıkça Sorulan Sorular | Güliz VIP Transfer",
        "description": "Uçuş rötarı, ödeme yöntemleri, bebek koltuğu ve gece transferleri hakkında merak edilenler. Gazipaşa & Antalya havalimanı VIP transfer sıkça sorulan sorular.",
        "anchor": "sss",
    },
    "hizli-rezervasyon": {
        "title": "Hızlı Rezervasyon | Güliz VIP Transfer - Gazipaşa & Antalya",
        "description": "Gazipaşa (GZP) ve Antalya (AYT) havalimanı VIP transferinizi saniyeler içinde online rezerve edin. Anında fiyat, uygun ödeme seçenekleri.",
        "anchor": "rezervasyon",
    },
}


def _render_route_seo_page(slug):
    """ROUTE_SEO_PAGES'teki bir rota için index.html'i okur, title/description/
    canonical/OG/Twitter etiketlerini rotaya özel içerikle değiştirip döndürür.
    Görünür sayfa içeriği ana sayfayla aynıdır (bkz. yukarıdaki not)."""
    route = ROUTE_SEO_PAGES.get(slug)
    if not route:
        return None
    index_path = os.path.join(WORKSPACE, "index.html")
    if not os.path.exists(index_path):
        return None
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    page_url = f"{BASE_URL}/{slug}"
    new_title = route["title"]
    new_desc = route["description"]
    html = html.replace(
        "<title>Gazipaşa & Antalya Havalimanı VIP Transfer | Güliz VIP Transfer</title>",
        f"<title>{new_title}</title>"
    )
    html = html.replace(
        'content="Gazipaşa Havalimanı (GZP) ve Antalya Havalimanı\'ndan (AYT); Alanya, Side, Manavgat, Belek, Kemer ve tüm Akdeniz bölgesine 7/24 konforlu, direkt ve ayrıcalıklı VIP transfer hizmeti sunuyoruz."',
        f'content="{new_desc}"'
    )
    html = html.replace(
        '<link rel="canonical" href="https://gulizvip.com.tr/">',
        f'<link rel="canonical" href="{page_url}">'
    )
    # Bu rota sayfalarının EN/RU karşılığı yok (görünür içerik TR kalıyor, sadece
    # meta çevrilmiyor) — hreflang tr/en/ru bloğunu bırakmak yanlış sinyal verir
    # (canonical rota URL'sini gösterirken hreflang="tr" ana sayfayı gösterir).
    # Tek dilli sayfa için sade, kendine referans veren tek hreflang yeterli.
    html = html.replace(
        '<link rel="alternate" hreflang="tr" href="https://gulizvip.com.tr/">\n'
        '    <link rel="alternate" hreflang="en" href="https://gulizvip.com.tr/en/">\n'
        '    <link rel="alternate" hreflang="ru" href="https://gulizvip.com.tr/ru/">\n'
        '    <link rel="alternate" hreflang="x-default" href="https://gulizvip.com.tr/">',
        f'<link rel="alternate" hreflang="tr" href="{page_url}">'
    )
    html = html.replace(
        'content="Gazipaşa & Antalya Havalimanı VIP Transfer Hizmetleri | Güliz VIP"',
        f'content="{new_title}"'
    )
    html = html.replace(
        'content="Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından; Alanya, Side, Manavgat, Belek, Kemer ve tüm Akdeniz bölgesine 7/24 kesintisiz VIP Vito transfer ayrıcalığı."',
        f'content="{new_desc}"'
    )
    html = html.replace(
        '<meta property="og:url" content="https://gulizvip.com.tr/">',
        f'<meta property="og:url" content="{page_url}">'
    )
    html = html.replace(
        'content="Gazipaşa & Antalya Havalimanı VIP Transfer | Güliz VIP">',
        f'content="{new_title}">'
    )
    html = html.replace(
        'content="Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından Alanya, Side, Manavgat, Belek ve Kemer\'e 7/24 VIP transfer."',
        f'content="{new_desc}"'
    )
    anchor = route.get("anchor")
    if anchor and "</body>" in html:
        scroll_script = (
            f'<script>window.addEventListener("load", function() {{'
            f'var el = document.getElementById("{anchor}");'
            f'if (el) el.scrollIntoView({{behavior: "smooth", block: "start"}});'
            f'}});</script></body>'
        )
        html = html.replace("</body>", scroll_script, 1)
    return html


# İngilizce/Rusça meta çevirileri — /en/ ve /ru/ rotaları için. Görünür sayfa içeriği
# (data-i18n) tamamen istemci tarafında index.html içindeki I18N sözlüğüyle değişiyor;
# burada sadece arama motorlarının/paylaşım kartlarının gördüğü <title>/<meta> ve
# <html lang> değiştiriliyor, artı sayfaya window.SITE_LANG enjekte ediliyor ki
# istemci script'i doğru dille açılsın (localStorage'a bakmadan önce).
LANG_META = {
    "en": {
        "title": "Gazipaşa & Antalya Airport VIP Transfer | Güliz VIP Transfer",
        "description": "We offer 24/7 comfortable, direct and exclusive VIP transfer service from Gazipaşa Airport (GZP) and Antalya Airport (AYT) to Alanya, Side, Manavgat, Belek, Kemer and the entire Mediterranean region.",
        "og_title": "Gazipaşa & Antalya Airport VIP Transfer Services | Güliz VIP",
        "og_description": "24/7 uninterrupted VIP Vito transfer privilege from Gazipaşa (GZP) and Antalya (AYT) airports to Alanya, Side, Manavgat, Belek, Kemer and the entire Mediterranean region.",
        "twitter_title": "Gazipaşa & Antalya Airport VIP Transfer | Güliz VIP",
        "twitter_description": "24/7 VIP transfer from Gazipaşa (GZP) and Antalya (AYT) airports to Alanya, Side, Manavgat, Belek and Kemer.",
    },
    "ru": {
        "title": "VIP-трансфер из аэропортов Газипаша и Анталия | Güliz VIP Transfer",
        "description": "Комфортный, прямой и эксклюзивный VIP-трансфер 24/7 из аэропорта Газипаша (GZP) и аэропорта Анталии (AYT) в Аланию, Сиде, Манавгат, Белек, Кемер и весь Средиземноморский регион.",
        "og_title": "VIP-трансфер из аэропортов Газипаша и Анталия | Güliz VIP",
        "og_description": "Непрерывный VIP-трансфер на автомобиле Vito 24/7 из аэропортов Газипаша (GZP) и Анталия (AYT) в Аланию, Сиде, Манавгат, Белек, Кемер и весь Средиземноморский регион.",
        "twitter_title": "VIP-трансфер из аэропортов Газипаша и Анталия | Güliz VIP",
        "twitter_description": "VIP-трансфер 24/7 из аэропортов Газипаша (GZP) и Анталия (AYT) в Аланию, Сиде, Манавгат, Белек и Кемер.",
    },
}


def _render_lang_page(lang):
    """/en/ veya /ru/ için index.html'i okur, <html lang>, title/meta/OG/Twitter
    etiketlerini o dile çevirir ve window.SITE_LANG enjekte eder. Görünür içerik
    aynı index.html'den geldiği için istemci tarafındaki I18N motoru sayfayı
    yüklenir yüklenmez tamamen o dile çevirir (bkz. index.html applyLanguage())."""
    meta = LANG_META.get(lang)
    if not meta:
        return None
    index_path = os.path.join(WORKSPACE, "index.html")
    if not os.path.exists(index_path):
        return None
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace('<html lang="tr">', f'<html lang="{lang}">', 1)
    html = html.replace(
        "<head>",
        f"<head>\n    <script>window.SITE_LANG = '{lang}';</script>",
        1
    )
    html = html.replace(
        "<title>Gazipaşa & Antalya Havalimanı VIP Transfer | Güliz VIP Transfer</title>",
        f"<title>{meta['title']}</title>"
    )
    html = html.replace(
        'content="Gazipaşa Havalimanı (GZP) ve Antalya Havalimanı\'ndan (AYT); Alanya, Side, Manavgat, Belek, Kemer ve tüm Akdeniz bölgesine 7/24 konforlu, direkt ve ayrıcalıklı VIP transfer hizmeti sunuyoruz."',
        f'content="{meta["description"]}"'
    )
    html = html.replace(
        'content="Gazipaşa & Antalya Havalimanı VIP Transfer Hizmetleri | Güliz VIP"',
        f'content="{meta["og_title"]}"'
    )
    html = html.replace(
        'content="Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından; Alanya, Side, Manavgat, Belek, Kemer ve tüm Akdeniz bölgesine 7/24 kesintisiz VIP Vito transfer ayrıcalığı."',
        f'content="{meta["og_description"]}"'
    )
    html = html.replace(
        'content="Gazipaşa & Antalya Havalimanı VIP Transfer | Güliz VIP">',
        f'content="{meta["twitter_title"]}">'
    )
    html = html.replace(
        'content="Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından Alanya, Side, Manavgat, Belek ve Kemer\'e 7/24 VIP transfer."',
        f'content="{meta["twitter_description"]}"'
    )
    # Canonical ve og:url: her dil sürümü kendi URL'sini işaret etmeli, aksi halde
    # Google /en/ ve /ru/ sayfalarını ana sayfanın kopyası sanıp ayrı indekslemez.
    lang_url = f"{BASE_URL}/{lang}/"
    html = html.replace(
        '<link rel="canonical" href="https://gulizvip.com.tr/">',
        f'<link rel="canonical" href="{lang_url}">'
    )
    html = html.replace(
        '<meta property="og:url" content="https://gulizvip.com.tr/">',
        f'<meta property="og:url" content="{lang_url}">'
    )
    og_locale = {"en": "en_US", "ru": "ru_RU"}.get(lang, "tr_TR")
    html = html.replace(
        '<meta property="og:locale" content="tr_TR">',
        f'<meta property="og:locale" content="{og_locale}">'
    )
    return html


# Ana sayfa slider görselleri — varsayılan 3 görsel (kalıcı: slider_images.json)
SLIDER_IMAGES = [
    {"src": "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?ixlib=rb-4.0.3&w=2074&q=80", "alt": "Gazipaşa Havalimanı"},
    {"src": "https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?ixlib=rb-4.0.3&w=2070&q=80", "alt": "VIP Vito Lüks Transfer"},
    {"src": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?ixlib=rb-4.0.3&w=2073&q=80", "alt": "Alanya Sahil"},
]
SLIDER_IMAGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slider_images.json")

def load_slider_images():
    """Önce PostgreSQL (config tablosu, key='slider_images'), yoksa slider_images.json."""
    global SLIDER_IMAGES
    db_data = db.get_json_config("slider_images")
    if isinstance(db_data, list) and len(db_data) > 0:
        SLIDER_IMAGES = db_data
        print(f"[✓] load_slider_images() — PostgreSQL'den {len(SLIDER_IMAGES)} görsel yüklendi")
        return
    try:
        if os.path.exists(SLIDER_IMAGES_FILE):
            with open(SLIDER_IMAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data.get("images"), list) and len(data["images"]) > 0:
                    SLIDER_IMAGES = data["images"]
                    print(f"[✓] load_slider_images() — JSON dosyasından {len(SLIDER_IMAGES)} görsel yüklendi")
    except Exception as e:
        print(f"[!] Slider görselleri yüklenemedi: {e}")

def save_slider_images():
    """Önce PostgreSQL'e yazmayı dener; DB yoksa/başarısızsa slider_images.json'a yazar."""
    if db.set_json_config("slider_images", SLIDER_IMAGES):
        return
    try:
        with open(SLIDER_IMAGES_FILE, "w", encoding="utf-8") as f:
            json.dump({"images": SLIDER_IMAGES}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Slider görselleri kaydedilemedi: {e}")

# Banka hesap bilgileri — admin panelden güncellenebilir
BANK_ACCOUNTS = {
    "garantibbva": {
        "name": "Garanti BBVA",
        "accountHolder": "GÜLİZ LOJİSTİK MİMARLIK SANAYİ VE TİC.LTD.ŞTİ",
        "iban": "TR34 0006 2001 1370 0006 2935 07"
    }
}
# ─── Visitor Tracking (Görünmez Ajan) ────────────────────────────────────────
VISITOR_SESSIONS = {}
visitor_lock = threading.Lock()
VISITOR_SESSION_TIMEOUT = 30  # seconds before marking offline
VISITOR_SESSION_CLEANUP = 300  # seconds before removing stale session

# ─── Agent Rate Limiter (Satış Dönüşüm Radarı) ────────────────────────────────
_AGENT_RATE_LIMITER = {}
agent_lock = threading.Lock()
AGENT_COOLDOWN = {"step_change": 15, "field_blur": 5, "exit_intent": 30}

# Telegram bot konfigürasyonu — admin panelden güncellenebilir
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Resend e-posta konfigürasyonu
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_TEMPLATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_template.html")

# ─── Reservation Data ───────────────────────────────────────────────────────────
RESERVATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reservations.json")
RESERVATIONS = []
RESERVATION_ID = 1000
# RESERVATIONS listesine yazma (insert/delete/toplu değiştirme) yapan tüm noktalar bu kilidi
# kullanır — chat_messages/visitor_sessions'ın zaten kullandığı korumayla tutarlı olsun ve
# sunucu ileride threaded bir modele geçerse (şu an tekil-threadli http.server.HTTPServer)
# veri bozulmasına karşı baştan korunmuş olsun diye eklendi.
reservations_lock = threading.Lock()


def _reservations_insert(reservation):
    """RESERVATIONS listesine kilit altında ekleme yapar (bkz. reservations_lock tanımı)."""
    with reservations_lock:
        RESERVATIONS.insert(0, reservation)


def _reservations_replace(new_list):
    """RESERVATIONS listesinin tamamını kilit altında değiştirir (ör. silme sonrası filtrelenmiş liste)."""
    global RESERVATIONS
    with reservations_lock:
        RESERVATIONS = new_list

# ─── Canlı Destek / İletişim / Bildirim JSON Fallback Dosyaları ─────────────────
# DB varsa asıl veri PostgreSQL'dedir; bu dosyalar sadece DATABASE_URL yokken
# (ya da DB'ye erişilemediğinde) kalıcılığı sağlayan yedek/fallback'tir.
CHAT_MESSAGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_messages.json")
CONTACT_MESSAGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contact_messages.json")
DASHBOARD_NOTIFICATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_notifications.json")

# ─── Price Data (Rota Fiyatları) ────────────────────────────────────────────────
PRICES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices.json")
ROUTE_PRICES = []
TAHSIS_PRICES = {}

# ─── Page Content File (PostgreSQL yoksa fallback) ─────────────────────────────────
PAGE_CONTENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page_content.json")

# ─── Fleet / Vehicles Data ────────────────────────────────────────────────────
VEHICLES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vehicles.json")
VEHICLES = []
VEHICLE_ID = 1


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
                            entry = {
                                "title": data[slug]["title"],
                                "subtitle": data[slug].get("subtitle", ""),
                                "is_active": data[slug].get("is_active", True),
                                "content": data[slug]["content"]
                            }
                            if data[slug].get("updatedAt"):
                                entry["updatedAt"] = data[slug]["updatedAt"]
                            PAGE_CONTENT[slug] = entry
                    print(f"[✓] load_page_content() başarılı — {len(data)} sayfa yüklendi")
    except Exception as e:
        print(f"[!] Sayfa içerik dosyası yüklenemedi: {e}")


def _get_merged_pages(lang="tr"):
    """Sayfa listesini DB + PAGE_CONTENT (fallback) BİRLEŞTİRİLMİŞ olarak döner.
    lang 'en'/'ru' ise ve PAGE_TRANSLATIONS'ta karşılığı varsa title/subtitle
    çeviriyle değiştirilir (footer/liste linkleri de doğru dilde görünsün diye).

    Kök neden notu: Eskiden db.get_all_pages() herhangi bir satır döndürdüğünde
    (örn. admin panelinden sadece TEK bir sayfa düzenlenip DB'ye ilk kez
    yazıldığında) o tek satır TÜM liste sanılıyor, PAGE_CONTENT'teki (henüz
    hiç DB'ye kaydedilmemiş) diğer sayfalar listeden tamamen düşüyordu —
    footer'dan ve admin panelinden aniden kayboluyorlardı. Gerçek içerik hiç
    silinmiyordu (tekil /api/page/<slug> hâlâ doğru veriyi dönüyordu), sadece
    LİSTE eksik gösteriliyordu. Çözüm: PAGE_CONTENT'i taban al, DB'de kaydı
    olan slug'ları DB değerleriyle üzerine yaz, DB'de olup PAGE_CONTENT'te
    olmayan slug'ları da ekle.
    """
    merged = {}
    for slug, data in PAGE_CONTENT.items():
        merged[slug] = {
            "slug": slug,
            "title": data.get("title", ""),
            "subtitle": data.get("subtitle", ""),
            "is_active": data.get("is_active", True),
        }
    try:
        db_pages = db.get_all_pages()
        if db_pages:
            for p in db_pages:
                slug = p.get("slug")
                if not slug:
                    continue
                merged[slug] = {
                    "slug": slug,
                    "title": p.get("title", ""),
                    "subtitle": p.get("subtitle", ""),
                    "is_active": p.get("is_active", True),
                }
    except Exception as e:
        print(f"[!] _get_merged_pages() DB okuma hatası: {e}")
    if lang in ("en", "ru"):
        translations = PAGE_TRANSLATIONS.get(lang, {})
        for slug, entry in merged.items():
            t = translations.get(slug)
            if t:
                entry["title"] = t.get("title", entry["title"])
                entry["subtitle"] = t.get("subtitle", entry["subtitle"])
    return list(merged.values())


def get_page_data(slug, lang="tr"):
    """Tek bir sayfanın title/subtitle/content/is_active/updatedAt bilgisini
    DB (öncelikli) + PAGE_CONTENT (yedek) + PAGE_TRANSLATIONS (en/ru varsa)
    birleştirerek döner. Hem /api/page/<slug> hem de sunucu tarafında
    render edilen /sayfa/<slug> meta etiketleri (_render_sayfa_page) bu tek
    fonksiyonu kullanır — iki ayrı yerde aynı öncelik mantığının birbirinden
    sapması (bu oturumda yaşanan kafa karışıklıklarının kök nedeniydi) böylece
    engellenmiş olur. Sayfa/slug bilinmiyorsa None döner."""
    slug = SLUG_ALIASES.get(slug, slug)
    if slug not in PAGE_CONTENT:
        return None
    result_page = None
    try:
        db_page = db.get_page_content(slug)
        if db_page and db_page.get("title") and db_page.get("content"):
            result_page = {
                "title": db_page["title"],
                "subtitle": db_page.get("subtitle", ""),
                "is_active": db_page.get("is_active", True),
                "content": db_page["content"],
                "updatedAt": db_page.get("updatedAt", "")
            }
    except Exception as e:
        print(f"[!] get_page_data({slug}) DB hatası: {e}")
    if result_page is None:
        page_entry = PAGE_CONTENT[slug]
        result_page = {
            "title": page_entry.get("title", ""),
            "subtitle": page_entry.get("subtitle", ""),
            "is_active": page_entry.get("is_active", True),
            "content": page_entry.get("content", ""),
            "updatedAt": page_entry.get("updatedAt", "")
        }
    if lang in ("en", "ru"):
        translation = PAGE_TRANSLATIONS.get(lang, {}).get(slug)
        if translation:
            result_page = dict(result_page)
            result_page["title"] = translation.get("title", result_page["title"])
            result_page["subtitle"] = translation.get("subtitle", result_page["subtitle"])
            result_page["content"] = translation.get("content", result_page["content"])
    return result_page


def _render_sayfa_page(slug, lang="tr"):
    """/sayfa/<slug>, /en/sayfa/<slug>, /ru/sayfa/<slug> için index.html'i okuyup
    <title>/<meta description>/canonical/hreflang/OG/Twitter etiketlerini o
    sayfaya ve dile özel hale getirir. Önceden bu sayfalar index.html'i hiç
    değiştirmeden servis ediyordu — yani hepsi anasayfanın canonical/title/OG
    etiketlerini gösteriyordu (arama motorları için yanlış sinyal, "duplicate
    content" riski). Görünür içerik istemci tarafında /api/page/<slug>?lang=
    ile yükleniyor (bkz. index.html sayfa modu betiği) — burada sadece <head>
    ve <html lang> düzenleniyor, HTML gövdesi değişmiyor."""
    slug = SLUG_ALIASES.get(slug, slug)
    page_data = get_page_data(slug, lang)
    if page_data is None or not page_data.get("is_active", True):
        return None
    index_path = os.path.join(WORKSPACE, "index.html")
    if not os.path.exists(index_path):
        return None
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    title = page_data.get("title") or slug
    subtitle = (page_data.get("subtitle") or "").strip()
    if subtitle:
        description = subtitle
    else:
        plain = re.sub("<[^>]+>", " ", page_data.get("content", ""))
        plain = re.sub(r"\s+", " ", plain).strip()
        description = (plain[:157] + "...") if len(plain) > 160 else plain

    site_suffix = " | Güliz VIP Transfer"
    full_title = title if title.endswith(site_suffix) else title + site_suffix

    prefix = "" if lang == "tr" else f"/{lang}"
    page_url = f"{BASE_URL}{prefix}/sayfa/{slug}"

    if lang != "tr":
        html = html.replace('<html lang="tr">', f'<html lang="{lang}">', 1)
        html = html.replace(
            "<head>",
            f"<head>\n    <script>window.SITE_LANG = '{lang}';</script>",
            1
        )

    html = html.replace(
        "<title>Gazipaşa & Antalya Havalimanı VIP Transfer | Güliz VIP Transfer</title>",
        f"<title>{full_title}</title>"
    )
    html = html.replace(
        'content="Gazipaşa Havalimanı (GZP) ve Antalya Havalimanı\'ndan (AYT); Alanya, Side, Manavgat, Belek, Kemer ve tüm Akdeniz bölgesine 7/24 konforlu, direkt ve ayrıcalıklı VIP transfer hizmeti sunuyoruz."',
        f'content="{description}"'
    )
    html = html.replace(
        '<link rel="canonical" href="https://gulizvip.com.tr/">',
        f'<link rel="canonical" href="{page_url}">'
    )
    # Hreflang: sadece gerçekten var olan dil sürümlerini işaretle — çevirisi
    # olmayan bir sayfa için sahte hreflang üretmek Search Console hatası ve
    # yanlış sinyal riski taşır.
    hreflang_links = [f'<link rel="alternate" hreflang="tr" href="{BASE_URL}/sayfa/{slug}">']
    for hl in ("en", "ru"):
        if slug in PAGE_TRANSLATIONS.get(hl, {}):
            hreflang_links.append(f'<link rel="alternate" hreflang="{hl}" href="{BASE_URL}/{hl}/sayfa/{slug}">')
    hreflang_links.append(f'<link rel="alternate" hreflang="x-default" href="{BASE_URL}/sayfa/{slug}">')
    html = html.replace(
        '<link rel="alternate" hreflang="tr" href="https://gulizvip.com.tr/">\n'
        '    <link rel="alternate" hreflang="en" href="https://gulizvip.com.tr/en/">\n'
        '    <link rel="alternate" hreflang="ru" href="https://gulizvip.com.tr/ru/">\n'
        '    <link rel="alternate" hreflang="x-default" href="https://gulizvip.com.tr/">',
        "\n    ".join(hreflang_links)
    )
    html = html.replace(
        'content="Gazipaşa & Antalya Havalimanı VIP Transfer Hizmetleri | Güliz VIP"',
        f'content="{full_title}"'
    )
    html = html.replace(
        'content="Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından; Alanya, Side, Manavgat, Belek, Kemer ve tüm Akdeniz bölgesine 7/24 kesintisiz VIP Vito transfer ayrıcalığı."',
        f'content="{description}"'
    )
    html = html.replace(
        '<meta property="og:url" content="https://gulizvip.com.tr/">',
        f'<meta property="og:url" content="{page_url}">'
    )
    og_locale = {"en": "en_US", "ru": "ru_RU"}.get(lang, "tr_TR")
    html = html.replace(
        '<meta property="og:locale" content="tr_TR">',
        f'<meta property="og:locale" content="{og_locale}">'
    )
    html = html.replace(
        'content="Gazipaşa & Antalya Havalimanı VIP Transfer | Güliz VIP">',
        f'content="{full_title}">'
    )
    html = html.replace(
        'content="Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından Alanya, Side, Manavgat, Belek ve Kemer\'e 7/24 VIP transfer."',
        f'content="{description}"'
    )
    return html


def save_page_content_to_json():
    """PAGE_CONTENT dict'ini page_content.json dosyasına yaz (PostgreSQL fallback)."""
    try:
        with open(PAGE_CONTENT_FILE, "w", encoding="utf-8") as f:
            json.dump(PAGE_CONTENT, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Sayfa içeriği JSON'a kaydedilemedi: {e}")


def load_vehicles():
    """Önce PostgreSQL (config tablosu, key='vehicles'), yoksa vehicles.json,
    o da yoksa varsayılan demo araç."""
    global VEHICLES, VEHICLE_ID
    db_data = db.get_json_config("vehicles")
    if db_data is not None:
        VEHICLES = db_data.get("vehicles", [])
        VEHICLE_ID = db_data.get("next_id", 1)
        print(f"[✓] load_vehicles() — PostgreSQL'den {len(VEHICLES)} araç yüklendi")
        return
    try:
        if os.path.exists(VEHICLES_FILE):
            with open(VEHICLES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                VEHICLES = data.get("vehicles", [])
                VEHICLE_ID = data.get("next_id", 1)
                print(f"[✓] load_vehicles() — JSON dosyasından {len(VEHICLES)} araç yüklendi")
        else:
            # Varsayılan demo araç
            VEHICLES = [
                {
                    "id": 1,
                    "name": "Mercedes-Benz Vito VIP",
                    "count": 3,
                    "main_image": "vitoaracimiz.jpeg",
                    "gallery_images": "vitoaracimiz.jpeg,https://images.unsplash.com/photo-1503376780353-7e6692767b70?ixlib=rb-4.0.3&w=400&q=80,https://images.unsplash.com/photo-1552519507-da3b142c6e3d?ixlib=rb-4.0.3&w=400&q=80",
                    "passenger_count": 6,
                    "luggage_count": 6,
                    "features": "Hakiki Deri Koltuklar,Ücretsiz Hızlı Wi-Fi,VIP İkram ve İçecekler,Klima / İklimlendirme,Bebek Koltuğu (Talep Üzerine),Araçta Kredi Kartı Geçerli",
                    "order": 0
                }
            ]
            VEHICLE_ID = 2
            save_vehicles()
    except Exception as e:
        print(f"[!] Araç dosyası yüklenemedi: {e}")
        VEHICLES = []
        VEHICLE_ID = 1


def save_vehicles():
    """Önce PostgreSQL'e yazmayı dener; DB yoksa/başarısızsa vehicles.json'a yazar."""
    data = {"vehicles": VEHICLES, "next_id": VEHICLE_ID}
    if db.set_json_config("vehicles", data):
        return
    try:
        with open(VEHICLES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Araç kaydedilemedi: {e}")


# ─── Araç Takvim ve Filo Yönetim Modülü (FAZ 1) ────────────────────────────────
# VEHICLE_UNITS: takvimde tek tek planlanabilen somut araç birimleri (örn. "Vito 1",
# "Vito 2") — vehicles.json'daki araç TÜRLERİNDEN (count alanlı) farklıdır, admin
# panelinden mevcut filodan otomatik türetilebilir veya elle eklenebilir.
VEHICLE_UNITS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vehicle_units.json")
VEHICLE_UNITS = []

# CALENDAR_BLOCKS: admin'in "Bakım", "Şahsi Kullanım" vb. sebeplerle manuel olarak
# kapattığı zaman aralıkları (gerçek bir müşteri rezervasyonu değildir).
CALENDAR_BLOCKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar_blocks.json")
CALENDAR_BLOCKS = []


def load_vehicle_units():
    """Önce PostgreSQL (config tablosu, key='vehicle_units'), yoksa vehicle_units.json,
    o da yoksa boş liste (admin panelinden 'Filodan Otomatik Oluştur' ile başlatılır)."""
    global VEHICLE_UNITS
    db_data = db.get_json_config("vehicle_units")
    if db_data is not None:
        VEHICLE_UNITS = db_data.get("units", [])
        print(f"[✓] load_vehicle_units() — PostgreSQL'den {len(VEHICLE_UNITS)} araç birimi yüklendi")
        return
    try:
        if os.path.exists(VEHICLE_UNITS_FILE):
            with open(VEHICLE_UNITS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                VEHICLE_UNITS = data.get("units", [])
                print(f"[✓] load_vehicle_units() — JSON dosyasından {len(VEHICLE_UNITS)} araç birimi yüklendi")
        else:
            VEHICLE_UNITS = []
    except Exception as e:
        print(f"[!] Araç birimleri yüklenemedi: {e}")
        VEHICLE_UNITS = []


def save_vehicle_units():
    """Önce PostgreSQL'e yazmayı dener; DB yoksa/başarısızsa vehicle_units.json'a yazar."""
    data = {"units": VEHICLE_UNITS}
    if db.set_json_config("vehicle_units", data):
        return
    try:
        with open(VEHICLE_UNITS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Araç birimleri kaydedilemedi: {e}")


def load_calendar_blocks():
    """Önce PostgreSQL (config tablosu, key='calendar_blocks'), yoksa calendar_blocks.json."""
    global CALENDAR_BLOCKS
    db_data = db.get_json_config("calendar_blocks")
    if db_data is not None:
        CALENDAR_BLOCKS = db_data.get("blocks", [])
        print(f"[✓] load_calendar_blocks() — PostgreSQL'den {len(CALENDAR_BLOCKS)} blok yüklendi")
        return
    try:
        if os.path.exists(CALENDAR_BLOCKS_FILE):
            with open(CALENDAR_BLOCKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                CALENDAR_BLOCKS = data.get("blocks", [])
                print(f"[✓] load_calendar_blocks() — JSON dosyasından {len(CALENDAR_BLOCKS)} blok yüklendi")
        else:
            CALENDAR_BLOCKS = []
    except Exception as e:
        print(f"[!] Takvim blokları yüklenemedi: {e}")
        CALENDAR_BLOCKS = []


def save_calendar_blocks():
    """Önce PostgreSQL'e yazmayı dener; DB yoksa/başarısızsa calendar_blocks.json'a yazar."""
    data = {"blocks": CALENDAR_BLOCKS}
    if db.set_json_config("calendar_blocks", data):
        return
    try:
        with open(CALENDAR_BLOCKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Takvim blokları kaydedilemedi: {e}")


# Tahsis süre anahtarlarının dakika karşılığı (takvimde bloke süresi hesaplamak için)
TAHSIS_DURATION_MINUTES = {"4hours": 240, "8hours": 480, "12hours": 720, "24hours": 1440}
DEFAULT_TRANSFER_DURATION_MINUTES = 60  # Faz 2'de Google Maps'ten gelen gerçek süreyle değişecek


def _reservation_duration_minutes(r):
    """Bir rezervasyonun aracı ne kadar süre meşgul edeceğini (dakika) hesaplar."""
    if r.get("estimatedDurationMinutes"):
        try:
            return int(r["estimatedDurationMinutes"])
        except (ValueError, TypeError):
            pass
    if r.get("type") == "tahsis":
        return TAHSIS_DURATION_MINUTES.get(r.get("duration", ""), 480)
    return DEFAULT_TRANSFER_DURATION_MINUTES


def _add_minutes_to_time(time_str, minutes):
    """'HH:MM' formatındaki saate dakika ekler, yine 'HH:MM' döndürür."""
    try:
        h, m = map(int, time_str.split(":")[:2])
        total = (h * 60 + m + int(minutes)) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return time_str


def _time_to_minutes(time_str):
    """'HH:MM' formatındaki saati gün içindeki dakika sayısına çevirir."""
    try:
        h, m = map(int, str(time_str).split(":")[:2])
        return h * 60 + m
    except Exception:
        return 0


def find_available_vehicle_unit(date_str, time_str, duration_minutes, buffer_minutes, exclude_reservation_id=None):
    """Verilen tarih/saat/süre için çakışmayan ilk müsait (aktif) araç birimini döndürür.
    Hem mevcut rezervasyonları (+tampon süresi) hem de manuel kapatılan (Block) zamanları kontrol eder.
    Uygun araç yoksa None döner (rezervasyon atanmamış olarak kalır, admin panelinden manuel atanabilir)."""
    try:
        new_start = _time_to_minutes(time_str)
        new_end = new_start + int(duration_minutes or 60) + int(buffer_minutes or 0)

        units = sorted(
            [u for u in VEHICLE_UNITS if u.get("isActive", True)],
            key=lambda u: (u.get("sortOrder", 0), u.get("id", 0))
        )

        for u in units:
            unit_id = u.get("id")
            conflict = False

            for r in RESERVATIONS:
                if exclude_reservation_id is not None and r.get("id") == exclude_reservation_id:
                    continue
                if r.get("date") != date_str or r.get("vehicleUnitId") != unit_id:
                    continue
                if r.get("status") == "cancelled":
                    continue
                r_start = _time_to_minutes(r.get("time", ""))
                r_buf = r.get("bufferMinutes")
                r_buf = 45 if r_buf is None else r_buf
                r_end = r_start + _reservation_duration_minutes(r) + int(r_buf)
                if not (new_end <= r_start or new_start >= r_end):
                    conflict = True
                    break

            if not conflict:
                for b in CALENDAR_BLOCKS:
                    if b.get("date") != date_str or b.get("vehicleUnitId") != unit_id:
                        continue
                    b_start = _time_to_minutes(b.get("startTime", ""))
                    b_end = _time_to_minutes(b.get("endTime", ""))
                    if not (new_end <= b_start or new_start >= b_end):
                        conflict = True
                        break

            if not conflict:
                return unit_id

        return None
    except Exception as e:
        print(f"[!] find_available_vehicle_unit hata: {e}")
        return None


def resize_and_save_image(file_data, filepath, max_width=1600, max_height=1200, quality=85, crop_ratio=None):
    """Pillow yüklüyse görseli boyutlandırıp JPEG olarak kaydeder.
    crop_ratio verilirse (örn. (3, 2)) görsel önce bu en-boy oranına ortalanarak kırpılır
    (CSS object-fit:cover ile aynı mantıkla) — böylece hangi oranda yüklenirse yüklensin
    sitedeki gösterim alanına kusursuz oturur. Pillow yoksa ham veri olduğu gibi kaydedilir."""
    if not _PIL_AVAILABLE:
        with open(filepath, "wb") as f:
            f.write(file_data)
        return
    try:
        img = Image.open(io.BytesIO(file_data))
        img = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img.convert("RGB")
        if crop_ratio:
            ratio_w, ratio_h = crop_ratio
            target_size = (max_width, round(max_width * ratio_h / ratio_w))
            img = ImageOps.fit(img, target_size, Image.LANCZOS, centering=(0.5, 0.5))
        else:
            img.thumbnail((max_width, max_height), Image.LANCZOS)
        img.save(filepath, "JPEG", quality=quality, optimize=True)
    except Exception as e:
        print(f"[!] Görsel boyutlandırılamadı, ham dosya kaydediliyor: {e}")
        with open(filepath, "wb") as f:
            f.write(file_data)


def load_prices():
    """Önce PostgreSQL (config tablosu, key='prices'), yoksa prices.json.
    UNIT_PRICE de aynı blok içinde saklanır (önceden hiç kaydedilmiyordu)."""
    global ROUTE_PRICES, TAHSIS_PRICES, UNIT_PRICE
    db_data = db.get_json_config("prices")
    if db_data is not None:
        ROUTE_PRICES = db_data.get("route_prices", [])
        TAHSIS_PRICES = db_data.get("tahsis_prices", {})
        UNIT_PRICE = db_data.get("unit_price", UNIT_PRICE)
        print(f"[✓] load_prices() — PostgreSQL'den yüklendi (birim fiyat: {UNIT_PRICE}₺)")
        return
    try:
        if os.path.exists(PRICES_FILE):
            with open(PRICES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                ROUTE_PRICES = data.get("route_prices", [])
                TAHSIS_PRICES = data.get("tahsis_prices", {})
                UNIT_PRICE = data.get("unit_price", UNIT_PRICE)
    except Exception as e:
        print(f"[!] Fiyat dosyası yüklenemedi: {e}")
        ROUTE_PRICES = []
        TAHSIS_PRICES = {}

def save_prices():
    """Önce PostgreSQL'e yazmayı dener; DB yoksa/başarısızsa prices.json'a yazar."""
    data = {"route_prices": ROUTE_PRICES, "tahsis_prices": TAHSIS_PRICES, "unit_price": UNIT_PRICE}
    if db.set_json_config("prices", data):
        return
    try:
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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

# ─── Yüklemeler (Uploads) ──────────────────────────────────────────────────────
# Railway'de bir Volume bağlanırsa RAILWAY_VOLUME_MOUNT_PATH otomatik set edilir
# ve tüm yüklenen dosyalar orada kalıcı olarak saklanır (deploy'larda kaybolmaz).
# Volume yoksa (örn. lokal geliştirme) WORKSPACE/uploads kullanılır.
UPLOAD_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.path.join(WORKSPACE, "uploads")
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except Exception as e:
    print(f"[!] UPLOAD_DIR oluşturulamadı: {e}")

# ─── Flight Data — Canlı Kazıma (Web Scraping) ────────────────────────────────
# Mock veri tamamen kaldırıldı. Uçuş bilgileri doğrudan havalimanlarının kendi
# resmi web sitelerinden çekilir (GZP: dahili JSON API, AYT: sunucu tarafında
# render edilen HTML tablo). Bkz. scrape_gzp_flights() / scrape_ayt_flights().

SCRAPE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

GZP_API_URL = "https://gzpairport.com/Home/getCurrentFlights"
AYT_ARRIVALS_URL = "https://www.antalya-airport.aero/yolcu-ve-ziyaretciler/ucus-bilgileri/tum-hatlar-gelis"
AYT_DEPARTURES_URL = "https://www.antalya-airport.aero/yolcu-ve-ziyaretciler/ucus-bilgileri/dis-hat-gidis"

# Bekleme süresi (saniye) — hedef sitelere art arda istek atarken IP ban riskini azaltır.
SCRAPE_REQUEST_DELAY = (2, 3)

TURKISH_IATA_CODES = {
    "IST", "SAW", "ESB", "ADB", "AYT", "GZP", "DLM", "ADA", "TZX",
    "VAN", "GZT", "KYA", "EDO", "ASR", "TJK", "MLX", "ERZ", "SZF",
}


def _classify_by_iata(code):
    return "ic" if (code or "").upper() in TURKISH_IATA_CODES else "dis"


def _http_get(url, timeout=15, retries=2):
    """Gerçek bir tarayıcıya daha çok benzeyen header seti + yeniden deneme.
    16 Ağustos'ta AYT tarafında 'Connection reset by peer' hatası canlıda
    doğrulandı (muhtemelen sitenin bot koruması) — sadece User-Agent yeterli
    gelmiyor olabilir, bu yüzden Accept/Accept-Encoding/Connection gibi
    tarayıcıların her istekte gönderdiği ek header'lar eklendi. Yine de reddedilirse
    kısa bir bekleme sonrası tekrar denenir (geçici ağ/rate-limit sorunlarına karşı)."""
    headers = {
        "User-Agent": SCRAPE_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",  # gzip istemiyoruz — urllib otomatik decode etmiyor
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "no-cache",
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(random.uniform(2, 4))
    raise last_err


def _http_get_ayt(url, timeout=15, retries=2):
    """AYT (antalya-airport.aero) için özel istek fonksiyonu. Bu site normal
    urllib istekleri karşısında 'Connection reset by peer' hatası veriyor —
    muhtemelen TLS/JA3 parmak izi tabanlı bot koruması, çünkü User-Agent ve
    tarayıcı header'ları doğru olsa bile reddediliyor. curl_cffi kütüphanesi
    gerçek bir Chrome tarayıcısının TLS imzasını taklit ederek bu korumayı
    aşmayı dener. curl_cffi yüklü değilse veya tüm denemeler başarısız olursa
    normal urllib tabanlı _http_get()'e geri döner (GZP zaten bunu kullanıyor
    ve etkilenmiyor)."""
    if _CURL_CFFI_AVAILABLE:
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = _cffi_requests.get(
                    url,
                    impersonate="chrome124",
                    timeout=timeout,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                    },
                )
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                last_err = e
                print(f"[!] AYT curl_cffi denemesi {attempt + 1} başarısız: {e}")
                if attempt < retries:
                    time.sleep(random.uniform(2, 4))
        print(f"[!] AYT curl_cffi tüm denemeler başarısız oldu, urllib yöntemine geri dönülüyor: {last_err}")
    return _http_get(url, timeout=timeout, retries=retries)


def _derive_gzp_status(stad, etad, remark_tr, is_arrival):
    """GZP JSON API'sindeki planlı/tahmini saat ve remark alanına göre insan-okunur
    durum metni ve renk kodu (expected/landed/departed/delayed) üretir."""
    if remark_tr:
        code = "delayed"
        rt = remark_tr.lower()
        if "iptal" in rt:
            code = "delayed"
        return (remark_tr, code)
    try:
        fmt = "%d.%m.%Y %H:%M"
        sched_dt = datetime.strptime(stad, fmt)
        est_dt = datetime.strptime(etad, fmt) if etad else sched_dt
    except Exception:
        return ("Zamanında", "expected")
    if est_dt != sched_dt:
        return (f"Rötar ({est_dt.strftime('%H:%M')})", "delayed")
    now = datetime.now()
    if now >= est_dt:
        return ("İndi", "landed") if is_arrival else ("Kalktı", "departed")
    return ("Zamanında", "expected")


def scrape_gzp_flights(flight_leg):
    """GZP Havalimanı'nın kendi dahili JSON API'sinden canlı uçuş verisi çeker.
    flight_leg: 'DEP' (giden) veya 'ARR' (gelen). Hata durumunda None döner —
    çağıran taraf mevcut önbelleği KORUR, sıfırlamaz."""
    try:
        raw = _http_get(f"{GZP_API_URL}?flightLeg={flight_leg}")
        data = json.loads(raw)
        if not data.get("result"):
            return None
        flights = data.get("data", {}).get("flights", []) or []
    except Exception as e:
        print(f"[!] GZP scraping hatası ({flight_leg}): {e}")
        return None

    is_arrival = (flight_leg == "ARR")
    out = []
    for f in flights:
        try:
            stad = f.get("stad") or ""
            etad = f.get("etad") or stad
            time_str = stad.split(" ")[-1] if stad else ""
            remark_tr = ((f.get("remark") or {}).get("remarkTr") or "").strip()
            path = f.get("path", {}) or {}
            loc = (path.get("origin") if is_arrival else path.get("destination")) or {}
            if is_arrival:
                loc_name = loc.get("originTr") or loc.get("originEn") or ""
                loc_code = loc.get("originIata") or ""
            else:
                loc_name = loc.get("destinationTr") or loc.get("destinationEn") or ""
                loc_code = loc.get("destinationIata") or ""
            status_text, status_code = _derive_gzp_status(stad, etad, remark_tr, is_arrival)
            entry = {
                "saat": time_str,
                "flight": f"{f.get('airlineIata', '')} {f.get('flightNumber', '')}".strip(),
                "airline": (f.get("airlineName") or "").title(),
                "status": status_text,
                "code": status_code,
                "type": _classify_by_iata(loc_code),
            }
            loc_display = f"{loc_name.title()} ({loc_code})" if loc_name else loc_code
            entry["from" if is_arrival else "to"] = loc_display
            out.append(entry)
        except Exception:
            continue
    out.sort(key=lambda x: x.get("saat", ""))
    return out


def _ayt_status_code(status_text):
    """AYT'nin Türkçe durum metnini (İndi, Gecikme:.., Beklenen, vb.) renk koduna çevirir."""
    st = (status_text or "").lower()
    if "iptal" in st:
        return "delayed"
    if "gecikme" in st:
        return "delayed"
    if "indi" in st or "bagaj" in st or "bantta" in st:
        return "landed"
    if "kalktı" in st or "kalkti" in st or "kapandı" in st or "kapandi" in st:
        return "departed"
    return "expected"


def scrape_ayt_flights(direction):
    """AYT (Antalya Havalimanı) uçuş sayfasından (sunucu tarafında render edilmiş
    HTML tablo) canlı uçuş verisi çeker. direction: 'arrival' veya 'departure'.
    Hata durumunda None döner — çağıran taraf mevcut önbelleği KORUR."""
    if not _BS4_AVAILABLE:
        print("[!] AYT scraping atlandı: beautifulsoup4 yüklü değil.")
        return None
    url = AYT_ARRIVALS_URL if direction == "arrival" else AYT_DEPARTURES_URL
    try:
        raw = _http_get_ayt(url)
        soup = BeautifulSoup(raw, "html.parser")
        container = soup.find(id="ContentPlaceHolder_ForNested_ContentPlaceHolder_ForNested_div_list")
        table = container.find("table") if container else None
        if not table:
            return None
        rows = table.find_all("tr")[1:]  # ilk satır (th) başlık, atla
    except Exception as e:
        print(f"[!] AYT scraping hatası ({direction}): {e}")
        return None

    is_arrival = (direction == "arrival")
    out = []
    for row in rows:
        try:
            flightnum_td = row.find("td", class_="flightnum")
            city_td = row.find("td", class_="from")
            airline_td = row.find("td", class_="airline")
            sched_td = row.find("td", class_="scheduled")
            status_td = row.find("td", class_="status")
            if not flightnum_td or not city_td:
                continue
            flight_code = flightnum_td.get_text(strip=True)
            city_name = city_td.get_text(strip=True)
            time_text = sched_td.get_text(strip=True) if sched_td else ""
            status_text = status_td.get_text(strip=True) if status_td else "Bilgi Yok"
            entry = {
                "saat": time_text,
                "flight": flight_code,
                "airline": (airline_td.get_text(strip=True) if airline_td else "").title(),
                "status": status_text,
                "code": _ayt_status_code(status_text),
                "type": "dis",  # hedef sayfalar dış hat gelen/giden kapsıyor
            }
            entry["from" if is_arrival else "to"] = city_name
            out.append(entry)
        except Exception:
            continue
    return out


# ─── In-Memory Cache ──────────────────────────────────────────────────────────

flight_cache = {"gzp": {"gelen": [], "giden": [], "updated_at": None}, "ayt": {"gelen": [], "giden": [], "updated_at": None}}

# ─── Döviz Kurları (bilgilendirme amaçlı — ödeme HER ZAMAN TL üzerinden alınır) ─
# TCMB'nin (Türkiye Cumhuriyet Merkez Bankası) resmi günlük kur XML'i — ücretsiz,
# API anahtarı gerekmiyor. Sadece müşteriye "TL fiyatınız yaklaşık şu kadar $/€'ya
# denk geliyor" göstermek için kullanılıyor; ödeme/rezervasyon akışı bundan
# ETKİLENMEZ, hep TL olarak devam eder.
TCMB_KUR_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
exchange_rates_cache = {"USD": None, "EUR": None, "updated_at": None}


def fetch_exchange_rates():
    """TCMB günlük kur XML'ini çeker, USD ve EUR satış (ForexSelling) kurlarını
    döndürür. Hata durumunda None döner — çağıran taraf önbellekteki eski kuru korur
    (bir günlük gecikme fiyat gösteriminde önemli bir sorun yaratmaz)."""
    try:
        req = urllib.request.Request(TCMB_KUR_URL, headers={"User-Agent": SCRAPE_USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        rates = {}
        for currency in root.findall("Currency"):
            code = currency.get("Kod") or currency.get("CurrencyCode")
            if code in ("USD", "EUR"):
                selling = currency.findtext("ForexSelling")
                if selling:
                    rates[code] = float(selling)
        if "USD" in rates and "EUR" in rates:
            return rates
        return None
    except Exception as e:
        print(f"[!] TCMB kur çekme hatası: {e}")
        return None


def refresh_exchange_rates():
    rates = fetch_exchange_rates()
    if rates:
        exchange_rates_cache["USD"] = rates["USD"]
        exchange_rates_cache["EUR"] = rates["EUR"]
        exchange_rates_cache["updated_at"] = datetime.now().isoformat()
        print(f"[✓] Döviz kurları güncellendi: 1 USD = {rates['USD']}₺, 1 EUR = {rates['EUR']}₺")
    else:
        print("[!] Döviz kurları güncellenemedi, önbellekteki eski kur korunuyor.")


# ─── Live Chat ──────────────────────────────────────────────────────────────────
CHAT_MESSAGES = []
CHAT_ID = 1

# ─── Contact Form ────────────────────────────────────────────────
CONTACT_MESSAGES = []
CONTACT_ID = 1

# ─── Dashboard Bildirimleri (ör. ödeme başarılı) ────────────────────────────────
DASHBOARD_NOTIFICATIONS = []
DASHBOARD_NOTIFICATION_ID = 1
dashboard_notif_lock = threading.Lock()


def load_chat_messages():
    """Sohbet mesajlarını başlangıçta yükle. Önce PostgreSQL, yoksa JSON dosyası."""
    global CHAT_MESSAGES, CHAT_ID
    db_messages = db.load_chat_messages_from_db()
    if db_messages is not None:
        CHAT_MESSAGES = db_messages
        next_id = db.get_next_chat_id()
        if next_id:
            CHAT_ID = next_id
        print(f"[i] {len(CHAT_MESSAGES)} sohbet mesajı PostgreSQL'den yüklendi.")
        return
    try:
        if os.path.exists(CHAT_MESSAGES_FILE):
            with open(CHAT_MESSAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                CHAT_MESSAGES = data.get("messages", [])
                CHAT_ID = data.get("next_id", 1)
    except Exception as e:
        print(f"[!] Sohbet mesajları dosyası yüklenemedi: {e}")
        CHAT_MESSAGES = []
        CHAT_ID = 1


def save_chat_messages():
    """Sohbet mesajlarını JSON dosyasına yedekle (DB kullanılamadığında asıl kaynak)."""
    try:
        with open(CHAT_MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump({"messages": CHAT_MESSAGES, "next_id": CHAT_ID}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Sohbet mesajları kaydedilemedi: {e}")


def load_contact_messages():
    """İletişim formu mesajlarını başlangıçta yükle. Önce PostgreSQL, yoksa JSON dosyası."""
    global CONTACT_MESSAGES, CONTACT_ID
    db_messages = db.load_contact_messages_from_db()
    if db_messages is not None:
        CONTACT_MESSAGES = db_messages
        next_id = db.get_next_contact_id()
        if next_id:
            CONTACT_ID = next_id
        print(f"[i] {len(CONTACT_MESSAGES)} iletişim mesajı PostgreSQL'den yüklendi.")
        return
    try:
        if os.path.exists(CONTACT_MESSAGES_FILE):
            with open(CONTACT_MESSAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                CONTACT_MESSAGES = data.get("messages", [])
                CONTACT_ID = data.get("next_id", 1)
    except Exception as e:
        print(f"[!] İletişim mesajları dosyası yüklenemedi: {e}")
        CONTACT_MESSAGES = []
        CONTACT_ID = 1


def save_contact_messages():
    """İletişim formu mesajlarını JSON dosyasına yedekle."""
    try:
        with open(CONTACT_MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump({"messages": CONTACT_MESSAGES, "next_id": CONTACT_ID}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] İletişim mesajları kaydedilemedi: {e}")


def load_dashboard_notifications():
    """Dashboard bildirimlerini başlangıçta yükle. Önce PostgreSQL, yoksa JSON dosyası."""
    global DASHBOARD_NOTIFICATIONS, DASHBOARD_NOTIFICATION_ID
    db_notifs = db.load_dashboard_notifications_from_db()
    if db_notifs is not None:
        DASHBOARD_NOTIFICATIONS = db_notifs
        next_id = db.get_next_dashboard_notification_id()
        if next_id:
            DASHBOARD_NOTIFICATION_ID = next_id
        print(f"[i] {len(DASHBOARD_NOTIFICATIONS)} dashboard bildirimi PostgreSQL'den yüklendi.")
        return
    try:
        if os.path.exists(DASHBOARD_NOTIFICATIONS_FILE):
            with open(DASHBOARD_NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                DASHBOARD_NOTIFICATIONS = data.get("notifications", [])
                DASHBOARD_NOTIFICATION_ID = data.get("next_id", 1)
    except Exception as e:
        print(f"[!] Dashboard bildirimleri dosyası yüklenemedi: {e}")
        DASHBOARD_NOTIFICATIONS = []
        DASHBOARD_NOTIFICATION_ID = 1


def save_dashboard_notifications():
    """Dashboard bildirimlerini JSON dosyasına yedekle."""
    try:
        with open(DASHBOARD_NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"notifications": DASHBOARD_NOTIFICATIONS, "next_id": DASHBOARD_NOTIFICATION_ID}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Dashboard bildirimleri kaydedilemedi: {e}")


def _push_dashboard_notification(message, ntype="info", reservation_id=None):
    global DASHBOARD_NOTIFICATION_ID
    with dashboard_notif_lock:
        notif = {
            "id": DASHBOARD_NOTIFICATION_ID,
            "type": ntype,
            "message": message,
            "reservationId": reservation_id,
            "read": False,
            "createdAt": datetime.now().isoformat(),
        }
        DASHBOARD_NOTIFICATIONS.insert(0, notif)
        del DASHBOARD_NOTIFICATIONS[50:]  # yalnızca son 50 bildirimi tut
        db_id = db.save_dashboard_notification_to_db(notif)
        if db_id:
            notif["id"] = db_id
            DASHBOARD_NOTIFICATION_ID = db_id + 1
        else:
            DASHBOARD_NOTIFICATION_ID += 1
        save_dashboard_notifications()
    return notif

# ─── Ödeme — Garanti BBVA Sanal POS (3D'li Peşin Satış) ────────────────────────────
# https://dev.garantibbva.com.tr/sanalpos-satis-pesin-3dli
# PayPas tamamen kaldırıldı (Tolga kararı) — Garanti tek ödeme sağlayıcısı.
#
# Model PayPas'tan TAMAMEN FARKLI: PayPas'ta müşteriyi onların hazır ödeme sayfasına
# yönlendiriyorduk, kart bilgisini hiç görmüyorduk. Garanti'nin klasik Sanal POS'unda
# kart formu (isim/numara/SKT/CVV) BİZİM SİTEMİZDE — kart alanları müşterinin
# tarayıcısında kalıp, bizim ürettiğimiz "gizli" banka alanlarıyla BİRLİKTE aynı HTML
# formu içinde DOĞRUDAN Garanti'nin sunucusuna post edilir (tarayıcı → Garanti, bizim
# sunucumuza kart verisi hiç uğramaz). Biz sadece o gizli alanları (hash dahil) üretiriz.
#
# Railway env var'ları (Tolga gerçek değerleri kendisi girecek):
#   GARANTI_MODE              "TEST" | "PROD" (öntanımlı TEST)
#   GARANTI_MERCHANT_ID       Üye işyeri numarası
#   GARANTI_TERMINAL_ID       Terminal numarası
#   GARANTI_PROV_USER_ID      Provizyon kullanıcı adı (satış için genelde "PROVAUT")
#   GARANTI_TERMINAL_USER_ID  Terminal kullanıcı adı (resmi form şablonunda örnek değer "GARANTI" —
#                              banka Tolga'ya farklı bir değer verdiyse onunla değiştirilmeli)
#   GARANTI_PROVISION_PASSWORD  Provizyon şifresi
#   GARANTI_STORE_KEY         3D Secure mağaza anahtarı (storekey)
# Tanımlanmazlarsa Garanti'nin resmi dokümantasyonundaki TEST ortamı öntanımlı
# değerleriyle çalışır (gerçek para geçmez, sadece test kartlarıyla denenebilir).
GARANTI_MODE = os.environ.get("GARANTI_MODE", "TEST").upper()
GARANTI_MERCHANT_ID = os.environ.get("GARANTI_MERCHANT_ID", "7000679")
GARANTI_TERMINAL_ID = os.environ.get("GARANTI_TERMINAL_ID", "30691297")
GARANTI_PROV_USER_ID = os.environ.get("GARANTI_PROV_USER_ID", "PROVAUT")
GARANTI_TERMINAL_USER_ID = os.environ.get("GARANTI_TERMINAL_USER_ID", "GARANTI")
GARANTI_PROVISION_PASSWORD = os.environ.get("GARANTI_PROVISION_PASSWORD", "123qweASD/")
GARANTI_STORE_KEY = os.environ.get("GARANTI_STORE_KEY", "12345678")
GARANTI_POST_URL = (
    "https://sanalposprov.garanti.com.tr/servlet/gt3dengine" if GARANTI_MODE == "PROD"
    else "https://sanalposprovtest.garantibbva.com.tr/servlet/gt3dengine"
)
GARANTI_CURRENCY_CODES = {"TRY": "949", "USD": "840", "EUR": "978", "GBP": "826", "JPY": "392"}


def _garanti_sha1_hex(text):
    """Dokümantasyondaki hash algoritması ISO-8859-9 (Türkçe) encoding + SHA1, büyük harf hex ister."""
    return hashlib.sha1(text.encode("iso-8859-9", errors="replace")).hexdigest().upper()


def _garanti_sha512_hex(text):
    return hashlib.sha512(text.encode("iso-8859-9", errors="replace")).hexdigest().upper()


def _garanti_secure3dhash(order_id, amount_minor, currency_code, success_url, error_url, txn_type, installment_count):
    """secure3dhash = SHA512(terminalId + orderId + amount + currencyCode + successUrl +
    errorUrl + type + installmentCount + storeKey + hashedPassword). hashedPassword =
    SHA1(provisionPassword + terminalId'nin 9 haneye SOLDAN SIFIRLA doldurulmuş hali) —
    resmi PHP örneğinden doğrulandı (str_pad($terminalId, 9, '0', STR_PAD_LEFT))."""
    hashed_password = _garanti_sha1_hex(GARANTI_PROVISION_PASSWORD + GARANTI_TERMINAL_ID.zfill(9))
    data = (
        f"{GARANTI_TERMINAL_ID}{order_id}{amount_minor}{currency_code}"
        f"{success_url}{error_url}{txn_type}{installment_count}{GARANTI_STORE_KEY}{hashed_password}"
    )
    return _garanti_sha512_hex(data)


def _garanti_prepare_form(reservation, currency="TRY"):
    """Rezervasyon için Garanti 3D'li Peşin satış formunun GİZLİ (hidden) alanlarını ve
    hash'ini üretir. Kart bilgisi burada YOK — form istemci tarafında bu alanlarla
    birleştirilip doğrudan Garanti'ye post edilir."""
    res_id = reservation.get("id")
    order_id = f"GULIZ{res_id}-{uuid.uuid4().hex[:8]}".upper()
    base_url = os.environ.get("PUBLIC_BASE_URL", "https://gulizvip.com.tr")
    result_url = f"{base_url}/api/payments/garanti/result"
    amount = float(reservation.get("price", 0) or 0)
    amount_minor = int(round(amount * 100))  # kuruş/cent
    currency_code = GARANTI_CURRENCY_CODES.get((currency or "TRY").upper(), "949")
    txn_type = "sales"
    installment_count = ""  # peşin — form alanı boş
    # DÜZELTME: İlk canlı testte hash hep reddedildi (3D adımına hiç ulaşmadan "Güvenlik
    # Kodu hatalı"/procreturncode=99). Dokümantasyondaki jenerik PHP örneği installmentCount'u
    # hash'te literal 0 (integer) kullanıyordu ama bu genel bir örnekti, "peşin" işlemine özel
    # değildi. Bağımsız, çalışan bir prod referans entegrasyonunda (GitHub: bsevgin/garantipos)
    # hash'e giren installmentCount değeri HER ZAMAN form alanına gönderilen DEĞERİN AYNISI
    # (peşin için boş string "") — iki ayrı değer kullanılmıyor. Hash artık form alanıyla
    # birebir aynı değeri (boş string) kullanıyor.
    secure3dhash = _garanti_secure3dhash(order_id, amount_minor, currency_code, result_url, result_url, txn_type, installment_count)
    return {
        "postUrl": GARANTI_POST_URL,
        "mode": GARANTI_MODE,
        "apiversion": "512",
        "secure3dsecuritylevel": "3D_PAY",
        "terminalprovuserid": GARANTI_PROV_USER_ID,
        "terminaluserid": GARANTI_TERMINAL_USER_ID,
        "terminalmerchantid": GARANTI_MERCHANT_ID,
        "terminalid": GARANTI_TERMINAL_ID,
        "orderid": order_id,
        "successurl": result_url,
        "errorurl": result_url,
        "customeremailaddress": reservation.get("customerEmail", "") or "musteri@gulizvip.com.tr",
        "companyname": "Guliz VIP Transfer",
        "lang": "tr",
        "txntimestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "refreshtime": "1",
        "secure3dhash": secure3dhash,
        "txnamount": str(amount_minor),
        "txntype": txn_type,
        "txncurrencycode": currency_code,
        "txninstallmentcount": installment_count,
        "reservationId": res_id,
    }


def _generate_payment_link(reservation, amount, currency, provider):
    """Rezervasyon için ödeme linki üretir (admin panelindeki 'Ödeme Linki Oluştur' /
    WhatsApp'tan gönder özelliği için). Garanti'de tek bir 'checkout URL' yok — kart
    formu bizim sitemizde olduğu için link, kendi sunucumuzdaki bir sayfaya işaret eder
    (bkz. GET /odeme/garanti/<id> — orada kart formu + otomatik Garanti'ye post var)."""
    ref = uuid.uuid4().hex[:12]
    if provider == "garanti":
        base_url = os.environ.get("PUBLIC_BASE_URL", "https://gulizvip.com.tr")
        url = f"{base_url}/odeme/garanti/{reservation.get('id')}"
        return {"url": url, "intentId": f"garanti_{ref}", "provider": "garanti"}
    # Manuel/placeholder mod: operasyon ekibinin müşteriye ilettiği izlenebilir bir
    # referans linki — gerçek ödeme sayfasına yönlendirmez, sadece altyapıyı hazırlar.
    base_url = os.environ.get("PUBLIC_BASE_URL", "https://gulizvip.com.tr")
    url = f"{base_url}/odeme/{ref}?rez={reservation.get('id')}&tutar={amount}&para={currency}"
    return {"url": url, "intentId": f"manual_{ref}", "provider": provider}


def _render_garanti_payment_page(reservation):
    """Admin'in ürettiği ödeme linki (GET /odeme/garanti/<id>) açıldığında gösterilen,
    kendi başına ayakta duran kart formu sayfası. Kart alanları HİÇBİR ZAMAN bizim
    sunucumuza post edilmez — JS, /api/payments/garanti/prepare'den aldığı gizli
    alanları müşterinin girdiği kart bilgileriyle birleştirip DOĞRUDAN Garanti'nin
    sunucusuna (postUrl) post eder."""
    res_id = reservation.get("id")
    amount = reservation.get("price", 0)
    currency = reservation.get("currency", "TRY")
    customer_name = (reservation.get("customerName", "") or "").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex,nofollow">
<title>Güvenli Ödeme — Güliz VIP Transfer</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif; background:#0f172a; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; }}
  .card {{ background:#fff; border-radius:16px; padding:32px; max-width:420px; width:100%; box-shadow:0 20px 60px rgba(0,0,0,.35); }}
  .card h2 {{ margin:0 0 4px; font-size:20px; color:#0f172a; }}
  .card .sub {{ color:#64748b; font-size:14px; margin:0 0 20px; }}
  .amount {{ font-size:28px; font-weight:700; color:#b8860b; margin:0 0 24px; }}
  label {{ display:block; font-size:13px; color:#334155; margin:14px 0 6px; font-weight:600; }}
  input {{ width:100%; padding:12px 14px; border:1px solid #cbd5e1; border-radius:8px; font-size:15px; }}
  input:focus {{ outline:none; border-color:#b8860b; }}
  .row {{ display:flex; gap:10px; }}
  .row > div {{ flex:1; }}
  button {{ width:100%; margin-top:22px; padding:14px; border:none; border-radius:8px; background:#b8860b; color:#fff; font-size:16px; font-weight:600; cursor:pointer; }}
  button:disabled {{ opacity:.6; cursor:not-allowed; }}
  .err {{ color:#dc2626; font-size:13px; margin-top:10px; display:none; }}
  .secure {{ text-align:center; color:#94a3b8; font-size:12px; margin-top:16px; }}
</style>
</head>
<body>
  <div class="card">
    <h2>Güvenli Kart ile Ödeme</h2>
    <p class="sub">{customer_name} — Rezervasyon #{res_id}</p>
    <p class="amount">{amount} {currency}</p>
    <form id="cardForm">
      <label>Kart Üzerindeki İsim</label>
      <input id="cardName" required autocomplete="cc-name" placeholder="Ad Soyad">
      <label>Kart Numarası</label>
      <input id="cardNumber" required autocomplete="cc-number" inputmode="numeric" maxlength="19" placeholder="0000 0000 0000 0000">
      <div class="row">
        <div>
          <label>Ay</label>
          <input id="cardMonth" required autocomplete="cc-exp-month" inputmode="numeric" maxlength="2" placeholder="AA">
        </div>
        <div>
          <label>Yıl</label>
          <input id="cardYear" required autocomplete="cc-exp-year" inputmode="numeric" maxlength="2" placeholder="YY">
        </div>
        <div>
          <label>CVV</label>
          <input id="cardCvv" required autocomplete="cc-csc" inputmode="numeric" maxlength="4" placeholder="000">
        </div>
      </div>
      <button type="submit" id="payBtn">Öde</button>
      <div class="err" id="errBox"></div>
      <p class="secure">🔒 Kart bilgileriniz doğrudan Garanti BBVA'nın güvenli sunucusuna iletilir.</p>
    </form>
  </div>
<script>
document.getElementById('cardForm').addEventListener('submit', function(e) {{
  e.preventDefault();
  var btn = document.getElementById('payBtn');
  var errBox = document.getElementById('errBox');
  errBox.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Yönlendiriliyor...';
  fetch('/api/payments/garanti/prepare', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ reservationId: {res_id} }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(data) {{
    if (!data.success || !data.form) {{
      throw new Error(data.error || 'Ödeme formu hazırlanamadı.');
    }}
    var f = data.form;
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = f.postUrl;
    function addField(name, value) {{
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      input.value = value;
      form.appendChild(input);
    }}
    Object.keys(f).forEach(function(k) {{
      if (k !== 'postUrl') addField(k, f[k]);
    }});
    addField('cardholdername', document.getElementById('cardName').value.trim());
    addField('cardnumber', document.getElementById('cardNumber').value.replace(/\\s+/g, ''));
    addField('cardexpiredatemonth', document.getElementById('cardMonth').value.trim().padStart(2, '0'));
    addField('cardexpiredateyear', document.getElementById('cardYear').value.trim().padStart(2, '0'));
    addField('cardcvv2', document.getElementById('cardCvv').value.trim());
    document.body.appendChild(form);
    form.submit();
  }})
  .catch(function(err) {{
    errBox.textContent = err.message || 'Bir hata oluştu, lütfen tekrar deneyin.';
    errBox.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Öde';
  }});
}});
</script>
</body>
</html>"""


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

# ─── E-posta (Resend) ─────────────────────────────────────────────────────────────
def send_confirmation_email(reservation):
    """Rezervasyon onay e-postası gönder. Resend API + email_template.html kullanır."""
    if not RESEND_API_KEY:
        print("[!] E-posta gönderilemedi: RESEND_API_KEY tanımlanmamış")
        return False
    if not _RESEND_AVAILABLE:
        print("[!] E-posta gönderilemedi: resend paketi kurulu değil")
        return False
    recipient = reservation.get("customerEmail", "").strip()
    if not recipient:
        print("[!] E-posta gönderilemedi: alıcı e-posta adresi boş")
        return False
    try:
        resend.api_key = RESEND_API_KEY
        # Template oku
        try:
            with open(EMAIL_TEMPLATE_FILE, "r", encoding="utf-8") as f:
                html_template = f.read()
        except FileNotFoundError:
            print(f"[!] email_template.html bulunamadı: {EMAIL_TEMPLATE_FILE}")
            return False
        # Placeholder'ları doldur
        placeholders = {
            "{musteri_isim}": reservation.get("customerName", ""),
            "{alis_noktasi}": reservation.get("pickup", ""),
            "{varis_noktasi}": reservation.get("destination", ""),
            "{tarih}": reservation.get("date", ""),
            "{saat}": reservation.get("time", ""),
            "{yolcu_sayisi}": str(reservation.get("passengers", 1)),
            "{tahmini_tutar}": str(reservation.get("price", 0)),
        }
        html_body = html_template
        for key, val in placeholders.items():
            html_body = html_body.replace(key, val)
        # Gönder
        params = {
            "from": "Güliz VIP Transfer <info@gulizvip.com.tr>",
            "to": [recipient],
            "subject": f"Rezervasyon Onayı #{reservation.get('id', '')} — Güliz VIP Transfer",
            "html": html_body,
        }
        response = resend.Emails.send(params)
        print(f"[✓] Onay e-postası gönderildi → {recipient} (id: {response.get('id', '?')})")
        return True
    except Exception as e:
        print(f"[!] E-posta gönderilemedi: {e}")
        return False


def _looks_like_ip(value):
    """value gerçekten geçerli bir IPv4/IPv6 adresi mi? (Formatsız/zararlı string'lerin
    IP alanına sızmasını önlemek için biçimsel doğrulama — özel/yerel IP'lere de izin verir,
    sadece "bu hiç bir IP değil" durumunu eler.)"""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _is_public_ip(ip):
    """Bir IP'nin genel (internet üzerinden erişilebilir/coğrafi olarak konumlandırılabilir)
    olup olmadığını kontrol eder. Özel/yerel/rezerve aralıklar (10.x, 172.16-31.x, 192.168.x,
    127.x, ::1 vb.) proxy zincirindeki dahili sunucu adresleridir — bunlar için konum sorgusu
    anlamsız/yanıltıcı sonuç üretir (ör. Railway/Cloudflare'ın kendi altyapı IP'si yurtdışında
    olduğu için ziyaretçi yurtdışındaymış gibi görünür)."""
    try:
        addr = ipaddress.ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast)
    except ValueError:
        return False


def _get_visitor_ip(handler):
    """Ziyaretçinin gerçek IP adresini istek başlıklarından çıkar.

    ÖNEMLİ (konum/IP yanlışlığı düzeltmesi): Site Cloudflare üzerinden proxy'leniyorsa
    (turuncu bulut aktifse), Railway'e ulaşan bağlantı artık ziyaretçiden değil Cloudflare'ın
    kendi kenar (edge) sunucusundan gelir. Bu durumda:
      - CF-Connecting-IP: Cloudflare'ın enjekte ettiği, sahtesi üretilemeyen GERÇEK ziyaretçi IP'si.
        Bu her zaman X-Forwarded-For'dan ÖNCELİKLİDİR.
      - X-Forwarded-For: Railway'in kendi proxy katmanı bu başlığı bazen zincire eklemek yerine
        SIFIRLAYIP sadece kendisine bağlanan tarafın (yani Cloudflare edge sunucusunun) IP'sini
        yazabilir. Bu, IP-API sorgusunun ziyaretçi yerine Cloudflare'ın (genelde yurtdışındaki)
        veri merkezinin konumunu döndürmesine sebep olur — kullanıcının bildirdiği "hep yurtdışı
        gösteriyor" sorununun kök nedeni büyük ihtimalle budur.
    Bu yüzden X-Forwarded-For zincirindeki IP'ler soldan sağa taranır ve İLK GEÇERLİ GENEL
    (public) IP seçilir; sadece dahili/özel IP'ler bulunursa zincirdeki ilk değere geri dönülür.
    """
    # Not: CF-Connecting-IP/True-Client-IP başlıkları yalnızca gerçek trafik Cloudflare
    # üzerinden geçtiğinde güvenilirdir; Railway origin'i doğrudan (Cloudflare'ı atlayarak)
    # erişilebilirse bu başlıklar teorik olarak sahteleneiblir. Buradaki tek pratik önlem —
    # tam bir Cloudflare IP-aralığı listesi tutmadan — biçimsel geçerlilik kontrolüdür: en
    # azından rastgele/zararlı bir string'in IP alanına (loglara, admin panele) sızmasını önler.
    cf_ip = handler.headers.get("CF-Connecting-IP", "").strip()
    if cf_ip and _looks_like_ip(cf_ip):
        return cf_ip

    true_client_ip = handler.headers.get("True-Client-IP", "").strip()
    if true_client_ip and _looks_like_ip(true_client_ip):
        return true_client_ip

    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        candidates = [p.strip() for p in forwarded.split(",") if p.strip()]
        for candidate in candidates:
            if _is_public_ip(candidate):
                return candidate
        if candidates:
            return candidates[0]

    real_ip = handler.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    client, _ = handler.client_address
    return client


def _lookup_geo(ip):
    """Bir IP adresi için şehir/ülke/bölge bilgisini ip-api.com üzerinden SUNUCU tarafında
    sorgula. Not: ziyaretçinin tarayıcısından doğrudan https://ip-api.com'a istek atmak
    403 Forbidden ile başarısız oluyordu — ip-api.com'un ücretsiz planı sadece düz HTTP
    destekliyor, HTTPS için ücretli plan gerekiyor. Sunucudan HTTP ile sorgulamak bu kısıtı
    aşıyor (mixed-content/CORS sorunu da yok). Yerel/özel IP'lerde (127.0.0.1, 192.168.x.x
    vb.) ip-api başarısız döner — bu durumda sessizce boş değer döner."""
    try:
        ip_url = f"http://ip-api.com/json/{ip}?fields=status,city,country,regionName"
        req = urllib.request.Request(ip_url, headers={"User-Agent": "GulizVIP/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == "success":
            return data.get("city", ""), data.get("country", ""), data.get("regionName", "")
    except Exception:
        pass
    return "", "", ""


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


# ─── Agent Rate Limiter Functions ─────────────────────────────────────────────
def _rate_limit_agent_event(session_id, event_type):
    """Check if enough time has passed since the last identical event.
    Returns True if event should be sent, False if rate-limited."""
    now = time.time()
    cooldown = AGENT_COOLDOWN.get(event_type, 10)
    with agent_lock:
        last = _AGENT_RATE_LIMITER.get((session_id, event_type), 0)
        if now - last < cooldown:
            return False
        _AGENT_RATE_LIMITER[(session_id, event_type)] = now
        # Limit dict size — remove old entries if it grows too large
        if len(_AGENT_RATE_LIMITER) > 10000:
            cutoff = now - 120
            for key in list(_AGENT_RATE_LIMITER.keys()):
                if _AGENT_RATE_LIMITER[key] < cutoff:
                    del _AGENT_RATE_LIMITER[key]
    return True


def _send_telegram_agent_report(session_id, event_type, data):
    """Send Telegram notification for agent-tracked events with rate limiting."""
    if not _rate_limit_agent_event(session_id, event_type):
        return False
    short_id = session_id[:8] if len(session_id) >= 8 else session_id
    if event_type == "step_change":
        pickup = data.get("pickup", "?")
        from_step = data.get("fromStep", "?")
        to_step = data.get("toStep", "?")
        form_type = data.get("formType", "?")
        msg = (
            f"\U0001f504 <b>Ajan Raporu: Adım Değişikliği</b>\n"
            f"\U0001f464 <b>Session:</b> <code>{short_id}</code>\n"
            f"\U0001f4c5 <b>Adım:</b> {from_step} → {to_step}\n"
            f"\U0001f4cd <b>Form:</b> {form_type}\n"
            f"\U0001f3af <b>Hedef:</b> {pickup}\n"
            f"\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}"
        )
    elif event_type == "field_blur":
        field_label = data.get("field", "Alan")
        value = data.get("value", "")
        msg = (
            f"\U0001f464 <b>Ajan Raporu: Alan Dolduruldu</b>\n"
            f"\U0001f464 <b>Session:</b> <code>{short_id}</code>\n"
            f"\U0001f4dd <b>{field_label}:</b> {value}\n"
            f"\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}"
        )
    elif event_type == "exit_intent":
        page = data.get("page", "?")
        msg = (
            f"\U0001f6a8 <b>Acil: Çıkış Eğilimi!</b>\n"
            f"\U0001f464 <b>Session:</b> <code>{short_id}</code>\n"
            f"\U0001f4cd <b>Sayfa:</b> {page}\n"
            f"\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}\n\n"
            f"⚠️ Ziyaretçi formu doldururken sayfadan çıkma eğiliminde!"
        )
    else:
        label = data.get("label", event_type)
        detail = data.get("detail", "")
        msg = (
            f"\U0001f514 <b>Ajan Raporu: {label}</b>\n"
            f"\U0001f464 <b>Session:</b> <code>{short_id}</code>\n"
        )
        if detail:
            msg += f"\U0001f4dd <b>Detay:</b> {detail}\n"
        msg += f"\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}"
    send_telegram(msg)
    return True


def _resolve_geo_and_notify_contact(contact_id, ip, name, phone, email, message, timestamp):
    """Arka plan thread'i: /api/contact için konum tespitini yapar, hem bellekteki
    CONTACT_MESSAGES kaydını hem DB'yi günceller, ardından Telegram bildirimini gönderir."""
    city, country, region = _lookup_geo(ip)
    for m in CONTACT_MESSAGES:
        if m.get("id") == contact_id:
            m["city"] = city
            m["country"] = country
            m["region"] = region
            break
    save_contact_messages()
    try:
        db.update_contact_message_in_db(contact_id, {"city": city, "country": country, "region": region})
    except Exception:
        pass
    tg_msg = "📬 <b>Yeni Iletisim Mesaji</b>\n"
    tg_msg += "👤 <b>Isim:</b> " + name + "\n"
    tg_msg += "📞 <b>Telefon:</b> " + phone + "\n"
    tg_msg += "📧 <b>E-posta:</b> " + (email or "Belirtilmemis") + "\n"
    tg_msg += "📍 <b>Konum:</b> " + (f"{city}, {country}" if city else "Bilinmiyor") + "\n"
    tg_msg += "💬 <b>Mesaj:</b> " + (message[:200] + ("..." if len(message) > 200 else "")) + "\n"
    tg_msg += "🕐 <b>Saat:</b> " + timestamp
    send_telegram(tg_msg)


def _describe_traffic_source(visitor, html=True):
    """Ziyaretçinin nereden geldiğini en güvenilir sinyalden başlayarak belirler.
    document.referrer, Google Ads tıklamalarında GENELDE BOŞ gelir (Google'ın kendi
    reklam yönlendirme zinciri referrer'ı iletmez) — bu yüzden asıl güvenilir sinyal
    URL'deki gclid parametresi (Google Ads tıklama kimliği). Öncelik sırası:
    gclid (Google Ads) > utm_source/medium/campaign (genel kampanya etiketleri) >
    fbclid (Meta/Facebook Ads) > document.referrer (organik/diğer) > 'Doğrudan'.
    html=False → admin panel/API için düz metin (Telegram'daki <b> etiketleri olmadan)."""
    b0, b1 = ("<b>", "</b>") if html else ("", "")
    gclid = visitor.get("gclid", "")
    fbclid = visitor.get("fbclid", "")
    utm_source = visitor.get("utmSource", "")
    utm_medium = visitor.get("utmMedium", "")
    utm_campaign = visitor.get("utmCampaign", "")
    utm_term = visitor.get("utmTerm", "")
    referrer = visitor.get("referrer", "")
    if gclid:
        parts = [f"🎯 {b0}Google Ads (tıklamalı reklam){b1}"]
        if utm_campaign:
            parts.append(f"Kampanya: {utm_campaign}")
        if utm_term:
            parts.append(f"Anahtar kelime: {utm_term}")
        parts.append(f"gclid: {gclid[:24]}…")
        return " | ".join(parts)
    if fbclid:
        return f"🎯 {b0}Meta/Facebook Ads (tıklamalı reklam){b1}" + (f" | Kampanya: {utm_campaign}" if utm_campaign else "")
    if utm_source or utm_medium or utm_campaign:
        bits = [b for b in [utm_source, utm_medium, utm_campaign] if b]
        return f"📊 {b0}Kampanya:{b1} " + " / ".join(bits)
    if referrer:
        try:
            domain = urllib.parse.urlparse(referrer).netloc or referrer
        except Exception:
            domain = referrer
        if "google." in domain and "ads" not in domain:
            return f"🔍 Google Organik Arama ({domain})"
        return f"🔗 {domain}"
    return "➡️ Doğrudan (link/favori/uygulama içi)"


def _resolve_geo_and_notify_visitor(session_id, ip):
    """Arka plan thread'i: konum tespitini (ip-api.com) yapar, VISITOR_SESSIONS'taki
    kaydı günceller (hâlâ mevcutsa) ve ardından Telegram bildirimini gönderir.
    Bu iş request thread'ini bloklamasın diye ayrı thread'de çalışır."""
    city, country, region = _lookup_geo(ip)
    with visitor_lock:
        visitor = VISITOR_SESSIONS.get(session_id)
        if visitor:
            visitor["city"] = city
            visitor["country"] = country
            visitor["region"] = region
        visitor_snapshot = dict(visitor) if visitor else {"ip": ip, "city": city, "country": country}
    msg = (
        f"\U0001f441 <b>Görünmez Ajan — Yeni Ziyaretçi</b>\n"
        f"\U0001f310 <b>IP:</b> {visitor_snapshot.get('ip', '?')}\n"
        f"\U0001f4cd <b>Konum:</b> {city or '?'}, {country or '?'}\n"
        f"\U0001f4f1 <b>Cihaz:</b> {visitor_snapshot.get('device', '?')} / {visitor_snapshot.get('os', '?')}\n"
        f"\U0001f30d <b>Tarayıcı:</b> {visitor_snapshot.get('browser', '?')}\n"
        f"\U0001f6aa <b>Giriş:</b> {visitor_snapshot.get('entryPage', '?')}\n"
        f"{_describe_traffic_source(visitor_snapshot)}\n"
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

def _summarize_flight_changes(old_list, new_list, max_items=5):
    """İki uçuş listesi arasındaki farkı (yeni eklenen uçuşlar + durum değişiklikleri)
    kısa, Telegram'a uygun bir özet metnine çevirir. Müşteri tarafındaki canlı tablo
    onay beklemeden zaten güncellenir — bu sadece Tolga'ya bilgi amaçlı bir özet,
    hiçbir şeyi engellemez/geciktirmez."""
    def _key(f):
        return (f.get("flight", ""), f.get("saat", ""))

    old_map = {_key(f): f for f in (old_list or [])}
    new_map = {_key(f): f for f in (new_list or [])}

    added = [f for k, f in new_map.items() if k not in old_map]
    status_changed = []
    for k, f in new_map.items():
        old_f = old_map.get(k)
        if old_f and old_f.get("status") != f.get("status"):
            status_changed.append((f, old_f.get("status", ""), f.get("status", "")))

    if not added and not status_changed:
        return None

    lines = []
    if added:
        lines.append(f"➕ {len(added)} yeni uçuş" + (":" if added[:max_items] else ""))
        for f in added[:max_items]:
            city = f.get("from") or f.get("to") or ""
            lines.append(f"   {f.get('flight','?')} — {city} — {f.get('saat','')}")
        if len(added) > max_items:
            lines.append(f"   (+{len(added) - max_items} tane daha)")
    if status_changed:
        lines.append(f"🔄 {len(status_changed)} durum değişikliği" + (":" if status_changed[:max_items] else ""))
        for f, old_s, new_s in status_changed[:max_items]:
            lines.append(f"   {f.get('flight','?')} — {old_s or '—'} → {new_s or '—'}")
        if len(status_changed) > max_items:
            lines.append(f"   (+{len(status_changed) - max_items} tane daha)")
    return "\n".join(lines)


def refresh_flights():
    """Her iki havalimanının gelen/giden uçuş verisini canlı olarak kaynağından
    (kendi resmi web sitelerinden) çeker ve belleğe (flight_cache) yazar.

    GÜVENLİ FALLBACK: Bir kaynağa ulaşılamazsa veya scraping hata verirse, o
    havalimanı/yön için önbellekteki ÖNCEKİ (daha önce başarıyla çekilmiş) veri
    KESİNLİKLE silinmez/sıfırlanmaz — sadece o bölüm güncellenmeden bırakılır."""
    now = datetime.now()
    print(f"[{now.strftime('%H:%M:%S')}] Uçuş verisi güncelleme başlıyor (canlı kazıma)...")

    jobs = [
        ("gzp", "gelen", lambda: scrape_gzp_flights("ARR")),
        ("gzp", "giden", lambda: scrape_gzp_flights("DEP")),
        ("ayt", "gelen", lambda: scrape_ayt_flights("arrival")),
        ("ayt", "giden", lambda: scrape_ayt_flights("departure")),
    ]

    for i, (airport_key, direction, scrape_fn) in enumerate(jobs):
        try:
            result = scrape_fn()
        except Exception as e:
            print(f"[!] {airport_key.upper()} {direction} scraping beklenmedik hata: {e}")
            result = None

        if result is not None:
            old_result = flight_cache[airport_key][direction]
            changes_summary = _summarize_flight_changes(old_result, result)
            flight_cache[airport_key][direction] = result
            flight_cache[airport_key]["updated_at"] = now.isoformat()
            print(f"[✓] {airport_key.upper()} {direction}: {len(result)} uçuş güncellendi (canlı).")
            # Canlı tablo müşteri tarafında ANINDA güncellenir (onay beklemez) — bu
            # sadece Tolga'ya bilgi amaçlı bir özet, hiçbir şeyi geciktirmiyor.
            if changes_summary:
                try:
                    send_telegram(
                        f"✈️ <b>Uçuş güncellemesi: {airport_key.upper()} {direction}</b>\n{changes_summary}"
                    )
                except Exception:
                    pass
        else:
            print(f"[!] {airport_key.upper()} {direction}: çekilemedi, önbellekteki son veri korunuyor "
                  f"({len(flight_cache[airport_key][direction])} kayıt).")
            # 16 Ağustos'ta bu sessizce günlerce fark edilmeden kalmıştı (AYT bot
            # koruması nedeniyle "Connection reset by peer") — artık Telegram'a da
            # düşüyor ki admin panelini/logları kontrol etmeden haberi olsun.
            try:
                send_telegram(
                    f"⚠️ <b>Uçuş verisi çekilemedi: {airport_key.upper()} {direction}</b>\n"
                    f"Önbellekteki eski veri korunuyor, güncellenemedi. Sorun devam ederse "
                    f"kaynağın (havalimanı web sitesi) bot koruması/erişim engeli olabilir."
                )
            except Exception:
                pass

        # IP ban riskine karşı istekler arasında bekleme (son istekten sonra beklemeye gerek yok)
        if i < len(jobs) - 1:
            time.sleep(random.uniform(*SCRAPE_REQUEST_DELAY))

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Uçuş verisi güncelleme tamamlandı.")


# Günde 2 kez otomatik güncelleme saatleri (24 saat formatı, yerel sunucu saati)
FLIGHT_REFRESH_HOURS = (2, 13)  # 02:00 ve 13:00


def _seconds_until_next_refresh():
    now = datetime.now()
    candidates = []
    for h in FLIGHT_REFRESH_HOURS:
        target = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        candidates.append(target)
    next_run = min(candidates)
    return (next_run - now).total_seconds(), next_run


def scheduler_loop():
    """Arka plan thread'i: sunucu ilk açıldığında scraping'i BİR KEZ hemen tetikler
    (ziyaretçiler beklemeden önbellek dolsun diye, ama HTTP sunucusunun kendisi bu
    işlemi beklemeden hemen dinlemeye başlar — bkz. __main__). Bundan sonra sadece
    günde 2 kez (02:00 / 13:00) tekrar çalışır. Kullanıcılar siteye girdikçe scraping
    TEKRAR TETİKLENMEZ; her istek bellekteki hazır veriyi okur."""
    refresh_flights()
    refresh_exchange_rates()
    while True:
        wait_seconds, next_run = _seconds_until_next_refresh()
        print(f"[i] Bir sonraki otomatik uçuş güncellemesi: {next_run.strftime('%d.%m.%Y %H:%M')} "
              f"({int(wait_seconds // 60)} dk sonra)")
        time.sleep(max(wait_seconds, 1))
        refresh_flights()
        refresh_exchange_rates()

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

# _serve_static() için izin verilen tek statik dosya uzantısı listesi. .json BİLEREK yok —
# tüm gerçek veri (rezervasyon, iletişim mesajı vb.) API endpoint'leri üzerinden auth ile
# sunulur, ham .json dosyaları WORKSPACE'te backend veri/config olarak durur.
PUBLIC_STATIC_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"}

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

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, status=200, content_type="text/plain; charset=utf-8"):
        """robots.txt / sitemap.xml gibi düz metin/XML yanıtlar için."""
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

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

    def _serve_static(self, filepath, extra_headers=None):
        # Path traversal koruması (_serve_upload ile aynı desen)
        filepath = filepath.lstrip("/")
        full_path = os.path.normpath(os.path.join(WORKSPACE, filepath))
        if not full_path.startswith(os.path.normpath(WORKSPACE)):
            self._send_error("Geçersiz yol.", 400)
            return
        ext = os.path.splitext(filepath)[1].lower()
        # KRİTİK: WORKSPACE, server.py/db.py (kaynak kod — ADMIN_PASS/SECRET_KEY/API
        # anahtarları içerir) ve reservations.json/contact_messages.json gibi müşteri
        # verisi içeren dosyalarla AYNI dizin. Path traversal koruması tek başına yeterli
        # değil — traversal olmadan doğrudan "GET /server.py" bile dosyayı sızdırırdı.
        # Bu yüzden yalnızca gerçekten genel (public) statik varlık uzantılarına izin
        # veriliyor; .json dahil geri kalan her şey (kaynak kod, veri dosyaları, config) reddedilir.
        if ext not in PUBLIC_STATIC_EXTENSIONS:
            self._send_error("Dosya bulunamadı", 404)
            return
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            self._send_error("Dosya bulunamadı", 404)
            return
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_upload(self, relpath):
        """UPLOAD_DIR altındaki (slider, fleet, vb.) yüklenmiş dosyaları serve eder.
        WORKSPACE'ten bağımsızdır — Railway Volume başka bir yola bağlıysa da çalışır."""
        # Path traversal koruması
        relpath = relpath.lstrip("/")
        full_path = os.path.normpath(os.path.join(UPLOAD_DIR, relpath))
        if not full_path.startswith(os.path.normpath(UPLOAD_DIR)):
            self._send_error("Geçersiz yol.", 400)
            return
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            self._send_error("Dosya bulunamadı", 404)
            return
        ext = os.path.splitext(full_path)[1].lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=2592000")
        self.end_headers()
        self.wfile.write(data)

    def _parse_multipart_upload(self):
        """multipart/form-data body'sini ayrıştırır. 'file' alanındaki dosyayı ve
        diğer text alanlarını döndürür: (file_data, file_filename, other_fields_dict).
        Hata durumunda (None, None, None) döner ve kendi başına _send_error çağırmaz —
        çağıran fonksiyon uygun hatayı üretmelidir."""
        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            return None, None, None
        length = int(self.headers.get('Content-Length', 0))
        if length <= 0 or length > 15 * 1024 * 1024:
            return None, None, None
        raw = self.rfile.read(length)
        boundary = content_type.split('boundary=')[1].strip()
        if boundary.startswith('"') and boundary.endswith('"'):
            boundary = boundary[1:-1]
        boundary_bytes = ('--' + boundary).encode()
        parts = raw.split(boundary_bytes)
        file_data = None
        file_filename = None
        other_fields = {}
        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            header_end = part.find(b'\r\n\r\n')
            if header_end < 0:
                continue
            content_end = part.rfind(b'\r\n--')
            if content_end == -1:
                content_end = len(part)
            if b'name="file"' in part:
                for line in part.split(b'\r\n'):
                    if b'filename=' in line:
                        file_filename = line.split(b'filename=')[1].strip().strip(b'"').decode()
                        break
                file_data = part[header_end + 4:content_end].rstrip(b'\r\n')
            else:
                name_match = part.split(b'name="')
                if len(name_match) > 1:
                    field_name = name_match[1].split(b'"')[0].decode()
                    field_value = part[header_end + 4:content_end].rstrip(b'\r\n').decode(errors='replace')
                    other_fields[field_name] = field_value
        return file_data, file_filename, other_fields

    def _handle_image_upload(self, category, max_width=1600, max_height=1200, quality=85, crop_ratio=None):
        """Ortak görsel yükleme + otomatik boyutlandırma mantığı.
        UPLOAD_DIR/<category>/ altına kaydeder, '/uploads/<category>/<dosya>' URL'i döndürür.
        Slider, filo (fleet) ve gelecekteki tüm yükleme özellikleri bunu kullanır.
        crop_ratio verilirse görsel o en-boy oranına ortalanarak kırpılır (bkz. resize_and_save_image).
        Başarılıysa (url, other_fields) döner, hata varsa kendi _send_error'unu çağırıp None döner."""
        file_data, file_filename, other_fields = self._parse_multipart_upload()
        if not file_data or not file_filename:
            self._send_error("Dosya gönderilmedi veya çok büyük (maks. 15MB).", 400)
            return None
        category_dir = os.path.join(UPLOAD_DIR, category)
        os.makedirs(category_dir, exist_ok=True)
        ext = '.jpg' if _PIL_AVAILABLE else (os.path.splitext(file_filename)[1] or '.jpg')
        unique_name = f"{int(time.time() * 1000)}{ext}"
        filepath = os.path.join(category_dir, unique_name)
        resize_and_save_image(file_data, filepath, max_width=max_width, max_height=max_height, quality=quality, crop_ratio=crop_ratio)
        url = f"/uploads/{category}/{unique_name}"
        return url, other_fields

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        try:
            path, params = self._parse_path()
            # ─── Railway Healthcheck ──────────────────────────────────────────
            if path == "/_health":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"OK")
                return
            # ─── Tek canonical adrese 301 yönlendirme: www -> www'sız, http -> https ──
            # Search Console "Doğru standart etikete sahip alternatif sayfa" uyarısı
            # www.gulizvip.com.tr'nin de aynı içeriği sunmasından kaynaklanıyordu —
            # canonical etiketi zaten www'sız/https adresi gösteriyordu ama gerçek bir
            # yönlendirme yoktu, Google her seferinde canonical'a bakıp karar vermek
            # zorunda kalıyordu. Artık www ve/veya http ile gelen her istek doğrudan
            # https://gulizvip.com.tr'ye 301 ile yönlendiriliyor (path + query korunarak).
            # Not: http tespiti Cloudflare/Railway'in eklediği X-Forwarded-Proto header'ına
            # bakılarak yapılıyor — bu header hiç yoksa (örn. dahili healthcheck) yönlendirme
            # tetiklenmez, sonsuz döngü riski oluşmaz.
            host = (self.headers.get("Host", "") or "").split(":")[0].lower()
            forwarded_proto = (self.headers.get("X-Forwarded-Proto", "") or "").lower()
            needs_www_strip = host.startswith("www.")
            needs_https = (forwarded_proto == "http")
            if needs_www_strip or needs_https:
                clean_host = host[4:] if needs_www_strip else host
                target = "https://" + clean_host + self.path
                self.send_response(301)
                self.send_header("Location", target)
                self.end_headers()
                return
            if path == "/api/flights":
                self._send_json({"success": True, "data": {"gzp": flight_cache["gzp"], "ayt": flight_cache["ayt"]}, "updated_at": max(flight_cache["gzp"]["updated_at"] or "", flight_cache["ayt"]["updated_at"] or "")})
                return
            if path == "/api/flights/live":
                # Bellekteki son geçerli (canlı kazınmış) veriyi servis eder — istek anında
                # YENİDEN scraping YAPILMAZ, sadece flight_cache okunur.
                airport = (params.get("airport", "") or "").lower()
                if airport not in ("gzp", "ayt"):
                    self._send_error("Geçersiz havalimanı. 'gzp' veya 'ayt' olmalı.", 400)
                    return
                cache = flight_cache[airport]
                self._send_json({
                    "success": True,
                    "airport": airport,
                    "gelen": cache["gelen"],
                    "giden": cache["giden"],
                    "updatedAt": cache["updated_at"],
                })
                return
            if path == "/api/maps/config":
                self._send_json({"success": True, "apiKey": GOOGLE_MAPS_API_KEY})
                return
            if path == "/api/unit-price":
                self._send_json({"success": True, "unitPrice": UNIT_PRICE})
                return
            if path == "/api/exchange-rates":
                # Bilgilendirme amaçlı — ödeme her zaman TL. Frontend, hesaplanan TL
                # fiyatının yanında yaklaşık $ ve € karşılığını göstermek için kullanır.
                self._send_json({
                    "success": True,
                    "usd": exchange_rates_cache["USD"],
                    "eur": exchange_rates_cache["EUR"],
                    "updatedAt": exchange_rates_cache["updated_at"],
                })
                return
            if path.startswith("/odeme/garanti/"):
                # Admin panelindeki "Ödeme Linki Oluştur" / WhatsApp'tan gönder özelliğiyle
                # üretilen link buraya işaret eder — kart formu içeren bağımsız bir sayfa.
                # Ayrıca müşterinin kendi rezervasyon akışındaki kart adımı da aynı
                # /api/payments/garanti/prepare endpoint'ini kullanır (bkz. index.html).
                res_id_str = path[len("/odeme/garanti/"):].strip("/")
                try:
                    res_id = int(res_id_str)
                except ValueError:
                    res_id = None
                target = next((r for r in RESERVATIONS if r.get("id") == res_id), None) if res_id is not None else None
                if target is None:
                    self._send_html("<h2>Rezervasyon bulunamadı.</h2>", 404)
                    return
                self._send_html(_render_garanti_payment_page(target))
                return
            if path == "/api/availability":
                # FAZ 3: Sitede müsaitlik göstergesi. Filo tanımlı değilse (henüz araç birimi
                # oluşturulmadıysa) her zaman "müsait" döner — özellik devre dışı gibi davranır,
                # canlı siteyi kilitlemez.
                date_str = params.get("date", "")
                time_str = params.get("time", "")
                if not date_str or not time_str:
                    self._send_json({"success": True, "available": True})
                    return
                try:
                    duration = int(params.get("duration", "60") or "60")
                except ValueError:
                    duration = 60
                if not VEHICLE_UNITS or not any(u.get("isActive", True) for u in VEHICLE_UNITS):
                    self._send_json({"success": True, "available": True})
                    return
                unit_id = find_available_vehicle_unit(date_str, time_str, duration, 45)
                self._send_json({"success": True, "available": unit_id is not None, "date": date_str, "time": time_str})
                return
            if path == "/api/route-prices":
                self._send_json({"success": True, "prices": ROUTE_PRICES})
                return
            if path == "/api/tahsis-prices":
                self._send_json({"success": True, "prices": TAHSIS_PRICES})
                return
            if path == "/api/destinations":
                try:
                    limit_str = params.get("limit", "6")
                    offset_str = params.get("offset", "0")
                    limit = int(limit_str) if limit_str else 6
                    offset = int(offset_str) if offset_str else 0
                    dests = db.get_destinations(active_only=True)
                    if dests is None:
                        dests = []
                    total = len(dests)
                    paginated = dests[offset:offset + limit]
                    self._send_json({"success": True, "destinations": paginated, "total": total})
                except Exception as e:
                    self._send_json({"success": True, "destinations": [], "total": 0})
                return
            if path == "/api/slider-images":
                self._send_json({"success": True, "images": SLIDER_IMAGES})
                return
            if path == "/api/bank-accounts":
                self._send_json({"success": True, "accounts": BANK_ACCOUNTS})
                return
            if path == "/api/fleet":
                sorted_vehicles = sorted(VEHICLES, key=lambda v: v.get("order", 0))
                self._send_json({"success": True, "vehicles": sorted_vehicles})
                return
            if path == "/api/maps/distance":
                origins = params.get("origins", "")
                destinations = params.get("destinations", "")
                mode = params.get("mode", "driving")
                if not origins or not destinations:
                    self._send_error("origins ve destinations parametreleri gereklidir.")
                    return
                google_url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={urllib.parse.quote(origins)}&destinations={urllib.parse.quote(destinations)}&mode={mode}&language=tr&key={GOOGLE_MAPS_SERVER_API_KEY}"
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
                latlng = params.get("latlng", "")
                if latlng:
                    # Ters geocode: enlem,boylam -> okunur adres (örn. "Konumumu Kullan" butonu için)
                    google_url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={urllib.parse.quote(latlng)}&language=tr&key={GOOGLE_MAPS_SERVER_API_KEY}"
                elif address:
                    google_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&language=tr&key={GOOGLE_MAPS_SERVER_API_KEY}"
                else:
                    self._send_error("address ya da latlng parametresi gereklidir.")
                    return
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
            if path == "/api/admin/customers/search":
                # VIP Müşteri CRM Hafızası — manuel rezervasyon girerken isim/telefon autocomplete
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
                q = params.get("q", "")
                results = db.search_customers(q, limit=8)
                if results is None:
                    # DB yok/erişilemiyor — RESERVATIONS üzerinden basit bir fallback türet
                    seen = {}
                    for r in RESERVATIONS:
                        phone = (r.get("customerPhone") or "").strip()
                        if not phone:
                            continue
                        if q and q.lower() not in phone.lower() and q.lower() not in (r.get("customerName", "").lower()):
                            continue
                        entry = seen.setdefault(phone, {
                            "id": None, "name": r.get("customerName", ""), "phone": phone,
                            "email": r.get("customerEmail", ""), "notes": "", "totalBookings": 0,
                            "totalSpent": 0, "isVip": False,
                        })
                        entry["totalBookings"] += 1
                        try:
                            entry["totalSpent"] += float(r.get("price") or 0)
                        except (TypeError, ValueError):
                            pass
                    results = list(seen.values())[:8]
                self._send_json({"success": True, "customers": results})
                return
            if path == "/api/admin/notifications":
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
                self._send_json({"success": True, "notifications": DASHBOARD_NOTIFICATIONS})
                return
            if path == "/api/admin/fleet":
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
                self._send_json({"success": True, "vehicles": VEHICLES})
                return
            if path == "/api/admin/vehicle-units":
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
                units = sorted(VEHICLE_UNITS, key=lambda u: (u.get("sortOrder", 0), u.get("id", 0)))
                self._send_json({"success": True, "units": units})
                return
            if path == "/api/admin/calendar":
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
                date_str = params.get("date", "") or datetime.now().strftime("%Y-%m-%d")
                day_reservations = []
                for r in RESERVATIONS:
                    if r.get("date") == date_str and r.get("status") != "cancelled":
                        dur = _reservation_duration_minutes(r)
                        buf = r.get("bufferMinutes", 45)
                        if buf is None:
                            buf = 45
                        start_time = r.get("time", "00:00")
                        day_reservations.append({
                            "id": r.get("id"),
                            "customerName": r.get("customerName", ""),
                            "customerPhone": r.get("customerPhone", ""),
                            "pickup": r.get("pickup", ""),
                            "destination": r.get("destination", ""),
                            "type": r.get("type", "transfer"),
                            "time": start_time,
                            "endTime": _add_minutes_to_time(start_time, dur),
                            "blockedUntil": _add_minutes_to_time(start_time, dur + buf),
                            "vehicleUnitId": r.get("vehicleUnitId"),
                            "status": r.get("status", "pending"),
                            "isManual": r.get("isManual", False),
                            "price": r.get("price", 0),
                            "paymentStatus": r.get("paymentStatus", "pending"),
                            "pickupLat": r.get("pickupLat"),
                            "pickupLng": r.get("pickupLng"),
                            "dropoffLat": r.get("dropoffLat"),
                            "dropoffLng": r.get("dropoffLng"),
                        })
                day_blocks = [b for b in CALENDAR_BLOCKS if b.get("date") == date_str]
                active_units = sorted(
                    [u for u in VEHICLE_UNITS if u.get("isActive", True)],
                    key=lambda u: (u.get("sortOrder", 0), u.get("id", 0))
                )
                self._send_json({
                    "success": True,
                    "date": date_str,
                    "vehicleUnits": active_units,
                    "reservations": day_reservations,
                    "blocks": day_blocks,
                })
                return
            if path == "/api/reservations/monthly-summary":
                # Aylık Bakış & İş Yoğunluk Noktaları — admin panelindeki aylık takvim
                # matrisi ve harita senkronizasyonu için gün bazlı özet veri.
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
                month_str = params.get("month", "") or datetime.now().strftime("%Y-%m")
                try:
                    year_i, mon_i = map(int, month_str.split("-"))
                    if not (1 <= mon_i <= 12):
                        raise ValueError()
                    month_str = f"{year_i:04d}-{mon_i:02d}"
                except Exception:
                    self._send_error("Geçersiz ay formatı. 'YYYY-MM' olmalı.", 400)
                    return

                days = {}
                for r in RESERVATIONS:
                    rdate = r.get("date", "") or ""
                    if not rdate.startswith(month_str):
                        continue
                    if r.get("status") == "cancelled":
                        continue
                    day_entry = days.setdefault(rdate, {"count": 0, "reservations": []})
                    day_entry["count"] += 1
                    day_entry["reservations"].append({
                        "id": r.get("id"),
                        "time": r.get("time", ""),
                        "customerName": r.get("customerName", ""),
                        "pickup": r.get("pickup", ""),
                        "destination": r.get("destination", ""),
                        "status": r.get("status", "pending"),
                        "vehicleUnitId": r.get("vehicleUnitId"),
                        "pickupLat": r.get("pickupLat"),
                        "pickupLng": r.get("pickupLng"),
                        "dropoffLat": r.get("dropoffLat"),
                        "dropoffLng": r.get("dropoffLng"),
                    })
                for d in days.values():
                    d["reservations"].sort(key=lambda x: x.get("time", ""))

                self._send_json({"success": True, "month": month_str, "days": days})
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
                            "gclid": v.get("gclid", ""), "fbclid": v.get("fbclid", ""),
                            "utmSource": v.get("utmSource", ""), "utmMedium": v.get("utmMedium", ""),
                            "utmCampaign": v.get("utmCampaign", ""), "utmTerm": v.get("utmTerm", ""),
                            "trafficSource": _describe_traffic_source(v, html=False),
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
            if path == "/api/admin/contact-messages":
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
                sorted_messages = sorted(CONTACT_MESSAGES, key=lambda m: m.get("id", 0), reverse=True)
                self._send_json({"success": True, "messages": sorted_messages, "count": len(sorted_messages)})
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
            if path == "/api/admin/pages":
                user = self._authenticate()
                if not user:
                    self._send_error("Yetkisiz erişim.", 401)
                    return
            # Admin: tüm sayfalar (DB + fallback birleştirilmiş — DB'ye hiç
            # yazılmamış sayfalar da listede kalsın diye tam değiştirme değil
            # slug bazlı BİRLEŞTİRME yapılır, bkz. _get_merged_pages())
                pages = _get_merged_pages()
                self._send_json({"success": True, "pages": pages})
                return
            if path == "/api/pages":
            # Public: tüm sayfaların listesi (DB + fallback birleştirilmiş)
                pages = _get_merged_pages(params.get("lang", "tr"))
                self._send_json({"success": True, "pages": pages})
                return
            if path == "/api/footer-pages":
            # Public: sadece aktif sayfalar (footer için, DB + fallback birleştirilmiş)
                pages = _get_merged_pages(params.get("lang", "tr"))
                active = [p for p in pages if p.get("is_active", True)]
                self._send_json({"success": True, "pages": active})
                return
            if path.startswith("/api/page/"):
                slug = path[len("/api/page/"):]
                result_page = get_page_data(slug, params.get("lang", "tr"))
                if result_page is None:
                    self._send_error("Sayfa bulunamadı.", 404)
                    return
                self._send_json({"success": True, "page": result_page})
                return
            if path.startswith("/sayfa/"):
                sayfa_slug = path[len("/sayfa/"):].rstrip("/")
                rendered = _render_sayfa_page(sayfa_slug, "tr")
                if rendered:
                    self._send_html(rendered)
                    return
                # Sayfa bulunamadı/pasif — yine de index.html'i sun (istemci tarafındaki
                # sayfa modu betiği API'den 404 alınca "Sayfa Bulunamadı" gösterir), ama
                # HTTP durumu gerçekten 404 olmalı ki arama motorları bu URL'i
                # indekslemesin ("soft 404" arama motorları için sorunlu bir sinyaldir).
                index_path = os.path.join(WORKSPACE, "index.html")
                if os.path.exists(index_path):
                    with open(index_path, "r", encoding="utf-8") as f:
                        self._send_html(f.read(), status=404)
                else:
                    self._send_error("Sayfa bulunamadı", 404)
                return
            if path == "/robots.txt":
                lines = [
                    "User-agent: *",
                    "Allow: /",
                    "Disallow: /admin.html",
                    "Disallow: /admin",
                    "Disallow: /api/",
                    "Disallow: /uploads/",
                    # Kart bilgisi giriş sayfası — rezervasyona özel, dinamik, tarama
                    # bütçesi israfı ve gereksiz indeksleme riski taşır. Sayfanın kendi
                    # <meta name="robots" content="noindex,nofollow"> etiketi de var
                    # (bkz. _render_garanti_payment_page), bu ek bir savunma katmanı.
                    "Disallow: /odeme/",
                    "",
                    f"Sitemap: {BASE_URL}/sitemap.xml",
                ]
                self._send_text("\n".join(lines), content_type="text/plain; charset=utf-8")
                return
            if path == "/sitemap.xml":
                today = datetime.now().strftime("%Y-%m-%d")
                # Anasayfanın 3 dil sürümü birbirine karşılıklı (reciprocal) hreflang
                # referansı verir (Google'ın gerekli gördüğü kural: A, B'yi işaret
                # ediyorsa B de A'yı işaret etmeli).
                home_alternates = {"tr": f"{BASE_URL}/", "en": f"{BASE_URL}/en/", "ru": f"{BASE_URL}/ru/", "x-default": f"{BASE_URL}/"}
                urls = [{"loc": f"{BASE_URL}/", "lastmod": today, "changefreq": "daily", "priority": "1.0", "alternates": home_alternates}]
                try:
                    # DB + fallback birleştirilmiş güncel liste (bkz. _get_merged_pages —
                    # admin panelinden pasif/aktif yapılan sayfalar burada doğru yansır)
                    for page in _get_merged_pages():
                        slug = page.get("slug")
                        if not slug or not page.get("is_active", True):
                            continue
                        updated = page.get("updatedAt", "")
                        lastmod = updated[:10] if updated else today
                        # Bu sayfanın gerçekten var olan dil sürümlerinin tam listesi —
                        # hem /sayfa/<slug> hem /en/.../ru/ varyantları için AYNI
                        # alternates seti kullanılır (karşılıklı hreflang kuralı).
                        page_alternates = {"tr": f"{BASE_URL}/sayfa/{slug}"}
                        for lang in ("en", "ru"):
                            if slug in PAGE_TRANSLATIONS.get(lang, {}):
                                page_alternates[lang] = f"{BASE_URL}/{lang}/sayfa/{slug}"
                        page_alternates["x-default"] = f"{BASE_URL}/sayfa/{slug}"
                        urls.append({"loc": f"{BASE_URL}/sayfa/{slug}", "lastmod": lastmod, "changefreq": "monthly", "priority": "0.5", "alternates": page_alternates})
                        for lang in ("en", "ru"):
                            if slug in PAGE_TRANSLATIONS.get(lang, {}):
                                urls.append({"loc": f"{BASE_URL}/{lang}/sayfa/{slug}", "lastmod": lastmod, "changefreq": "monthly", "priority": "0.5", "alternates": page_alternates})
                except Exception as e:
                    print(f"[!] sitemap.xml sayfa listesi hatası: {e}")
                for slug in ROUTE_SEO_PAGES:
                    # Rota sayfalarının EN/RU karşılığı yok (bkz. _render_route_seo_page),
                    # bu yüzden alternates eklenmiyor — tek dilli sayfa için hreflang
                    # alternate listesi gereksiz/yanıltıcı olurdu.
                    urls.append({"loc": f"{BASE_URL}/{slug}", "lastmod": today, "changefreq": "weekly", "priority": "0.8"})
                for lang in ("en", "ru"):
                    urls.append({"loc": f"{BASE_URL}/{lang}/", "lastmod": today, "changefreq": "weekly", "priority": "0.9", "alternates": home_alternates})
                xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
                for u in urls:
                    xml_parts.append(
                        "<url>"
                        f"<loc>{u['loc']}</loc>"
                        f"<lastmod>{u['lastmod']}</lastmod>"
                        f"<changefreq>{u['changefreq']}</changefreq>"
                        f"<priority>{u['priority']}</priority>"
                    )
                    for hl, href in u.get("alternates", {}).items():
                        xml_parts.append(f'<xhtml:link rel="alternate" hreflang="{hl}" href="{href}"/>')
                    xml_parts.append("</url>")
                xml_parts.append("</urlset>")
                self._send_text("".join(xml_parts), content_type="application/xml; charset=utf-8")
                return
            lang_path = path.strip("/")
            if lang_path in ("en", "ru"):
                rendered = _render_lang_page(lang_path)
                if rendered:
                    self._send_html(rendered)
                    return
            # /en/sayfa/<slug> veya /ru/sayfa/<slug> — içerik sayfalarının (Hakkımızda,
            # Gizlilik, Mesafeli Satış vb.) İngilizce/Rusça sürümü (bkz. PAGE_TRANSLATIONS).
            # Aynı index.html kabuğu SITE_LANG enjekte edilerek servis edilir; sayfa
            # içeriği istemci tarafında /api/page/<slug>?lang=<dil> ile yükleniyor.
            lang_sayfa_parts = lang_path.split("/")
            if len(lang_sayfa_parts) == 3 and lang_sayfa_parts[0] in ("en", "ru") and lang_sayfa_parts[1] == "sayfa":
                rendered = _render_sayfa_page(lang_sayfa_parts[2], lang_sayfa_parts[0])
                if rendered:
                    self._send_html(rendered)
                    return
                index_path = os.path.join(WORKSPACE, "index.html")
                if os.path.exists(index_path):
                    with open(index_path, "r", encoding="utf-8") as f:
                        self._send_html(f.read(), status=404)
                else:
                    self._send_error("Sayfa bulunamadı", 404)
                return
            # /en/<rota-slug> veya /ru/<rota-slug> gibi birleşik adresler (örn. eski/dış
            # bağlantılar) — rota sayfalarının çevirisi yok, 404 yerine sade dil sayfasına
            # yönlendir (bkz. index.html switchLanguage() artık bu tarz URL üretmiyor).
            lang_path_parts = lang_path.split("/")
            if len(lang_path_parts) == 2 and (
                (lang_path_parts[0] in ("en", "ru") and lang_path_parts[1] in ROUTE_SEO_PAGES) or
                (lang_path_parts[1] in ("en", "ru") and lang_path_parts[0] in ROUTE_SEO_PAGES)
            ):
                redirect_lang = lang_path_parts[0] if lang_path_parts[0] in ("en", "ru") else lang_path_parts[1]
                self.send_response(302)
                self.send_header("Location", f"/{redirect_lang}/")
                self.end_headers()
                return
            route_slug = path.lstrip("/")
            if route_slug in ROUTE_SEO_PAGES:
                rendered = _render_route_seo_page(route_slug)
                if rendered:
                    self._send_html(rendered)
                    return
            if path == "/" or path == "":
                self._serve_static("index.html")
            elif path == "/admin.html":
                self._serve_static("admin.html", extra_headers={"X-Robots-Tag": "noindex, nofollow"})
            elif path.startswith("/uploads/"):
                self._serve_upload(path[len("/uploads/"):])
            elif path.startswith("/"):
                self._serve_static(path.lstrip("/"))
            else:
                self._send_error("Bulunamadı", 404)
            
            
        except Exception as e:
            import traceback, sys
            path = self.path if hasattr(self, "path") else "?"
            print(f"[do_GET CRASH] path={path} error={e}", flush=True)
            traceback.print_exc()
            try:
                self._send_error("Sunucu hatasi", 500)
            except Exception:
                pass
    def do_POST(self):
        global RESERVATION_ID, RESERVATIONS
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
            result = self._handle_image_upload("slider", max_width=1920, max_height=1080, quality=85)
            if result is None:
                return  # _handle_image_upload zaten hatayı gönderdi
            url, fields = result
            alt_text = (fields.get("alt") or "").strip() or "Slider Görseli"
            global SLIDER_IMAGES
            img_entry = {"src": url, "alt": alt_text}
            SLIDER_IMAGES.append(img_entry)
            save_slider_images()
            self._send_json({"success": True, "image": img_entry, "images": SLIDER_IMAGES})
            return
        if path == "/api/admin/fleet/upload":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            # index.html'de filo ana görseli ~1.5:1 (350px yükseklik) ve galeri küçük resimleri
            # 80x60 (4:3) oranında gösteriliyor — 3:2 oranı ikisine de kusursuz oturacak şekilde
            # ortalanarak kırpılıyor (CSS object-fit:cover ile aynı sonucu sunucu tarafında garanti eder).
            result = self._handle_image_upload("fleet", max_width=1200, max_height=800, quality=88, crop_ratio=(3, 2))
            if result is None:
                return  # _handle_image_upload zaten hatayı gönderdi
            url, _fields = result
            self._send_json({"success": True, "url": url, "resized": _PIL_AVAILABLE})
            return
        if path == "/api/admin/destinations/upload":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            # index.html'de "Popüler Turistik Bölgeler" kartları 16:9 oranında (width:100%, height:200px
            # masaüstünde) gösteriliyor — bölge görselleri bu orana ortalanarak kırpılıp kaydediliyor.
            result = self._handle_image_upload("destinations", max_width=1600, max_height=900, quality=88, crop_ratio=(16, 9))
            if result is None:
                return
            url, _fields = result
            self._send_json({"success": True, "url": url, "resized": _PIL_AVAILABLE})
            return
        if path == "/api/admin/calendar/quick-reservation":
            # Patron/operasyon ekibi tarafından takvim üzerinden elle girilen rezervasyon
            # (örn. telefonla gelen özel talep). Herhangi bir hizmet bölgesi kısıtlaması
            # UYGULANMAZ — "TAMAMEN MANUEL MÜDAHALE" yetkisi bu uçtan geçer.
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            global RESERVATION_ID
            try:
                body = json.loads(self._read_body())
                if not body.get("customerName") or not body.get("date") or not body.get("time"):
                    self._send_error("Müşteri adı, tarih ve saat zorunludur.", 400)
                    return
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
                    "status": body.get("status", "confirmed"),
                    "vehicleUnitId": body.get("vehicleUnitId"),
                    "bufferMinutes": body.get("bufferMinutes", 45),
                    "estimatedDurationMinutes": body.get("estimatedDurationMinutes"),
                    "isManual": True,
                    "currency": body.get("currency", "TRY"),
                    "paymentStatus": body.get("paymentStatus", "pending"),
                    "paymentLink": "",
                    "stripePaymentIntentId": "",
                    "createdAt": datetime.now().isoformat(),
                }

                def _to_float(v):
                    try:
                        return float(v) if v is not None else None
                    except (TypeError, ValueError):
                        return None

                for src_key, dst_key in (("pickupLat", "pickupLat"), ("pickupLng", "pickupLng"),
                                          ("dropoffLat", "dropoffLat"), ("dropoffLng", "dropoffLng"),
                                          ("distanceKm", "distanceKm")):
                    val = _to_float(body.get(src_key))
                    if val is not None:
                        reservation[dst_key] = val

                # VIP CRM: telefon numarasına göre müşteriyi bul/oluştur ve rezervasyona bağla
                try:
                    customer = db.find_or_create_customer(
                        reservation.get("customerPhone", ""),
                        reservation.get("customerName", ""),
                        reservation.get("customerEmail", "")
                    )
                    if customer:
                        reservation["customerId"] = customer["id"]
                except Exception as e:
                    print(f"[!] Müşteri eşleştirme hatası (manuel rezervasyon): {e}")

                db_id = db.save_reservation_to_db(reservation)
                if db_id:
                    reservation["id"] = db_id
                    RESERVATION_ID = db_id + 1
                    _reservations_insert(reservation)  # in-memory önbelleği de senkron tut (admin/takvim buradan okuyor)
                else:
                    _reservations_insert(reservation)
                    RESERVATION_ID += 1
                    save_reservations()
                    if os.environ.get("DATABASE_URL"):
                        # DATABASE_URL tanımlıyken (yani DB kullanılması bekleniyorken) yazma
                        # başarısız oldu — bu gerçek bir sorun. DATABASE_URL hiç yoksa (bilinçli
                        # JSON-only mod) bildirim atma, o normal bir çalışma şeklidir.
                        _push_dashboard_notification(
                            f"⚠️ Rezervasyon #{reservation['id']} DB'ye yazılamadı, sadece yedek dosyada (JSON) kayıtlı — DB bağlantısını kontrol edin.",
                            ntype="system", reservation_id=reservation["id"]
                        )
                self._send_json({"success": True, "reservation": reservation})
                telegram_msg = (
                    f"📌 <b>Manuel Rezervasyon Eklendi #{reservation['id']}</b>\n"
                    f"👤 <b>İsim:</b> {reservation['customerName']}\n"
                    f"📞 <b>Telefon:</b> {reservation['customerPhone']}\n"
                    f"📍 <b>Alış:</b> {reservation['pickup']}\n"
                    f"🏁 <b>Varış:</b> {reservation['destination']}\n"
                    f"📅 <b>Tarih:</b> {reservation['date']} {reservation['time']}\n"
                    f"💰 <b>Ücret:</b> {reservation['price']}₺\n"
                    f"🚐 <b>Takvimden admin tarafından girildi.</b>"
                )
                send_telegram(telegram_msg)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/reservations":
            try:
                body = json.loads(self._read_body())
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
                    "payment_session_id": "",
                    "payment_ref": "",
                    "payment_status": "pending",
                    "currency": body.get("currency", "TRY"),
                    "paymentStatus": "pending",
                    "paymentLink": "",
                    "stripePaymentIntentId": "",
                    "createdAt": datetime.now().isoformat()
                }

                def _to_float(v):
                    try:
                        return float(v) if v is not None else None
                    except (TypeError, ValueError):
                        return None

                pickup_lat = _to_float(body.get("pickupLat"))
                pickup_lng = _to_float(body.get("pickupLng"))
                dropoff_lat = _to_float(body.get("dropoffLat"))
                dropoff_lng = _to_float(body.get("dropoffLng"))
                distance_km = _to_float(body.get("distanceKm"))
                duration_min = _to_float(body.get("estimatedDurationMinutes"))
                if pickup_lat is not None: reservation["pickupLat"] = pickup_lat
                if pickup_lng is not None: reservation["pickupLng"] = pickup_lng
                if dropoff_lat is not None: reservation["dropoffLat"] = dropoff_lat
                if dropoff_lng is not None: reservation["dropoffLng"] = dropoff_lng
                if distance_km is not None: reservation["distanceKm"] = distance_km
                if duration_min is not None: reservation["estimatedDurationMinutes"] = int(duration_min)

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
                # Not: Kredi kartı ile online ödeme entegrasyonu kaldırıldı — tüm rezervasyonlar
                # (banka havalesi / araçta ödeme) doğrudan kaydediliyor, operasyon ekibi takip ediyor.

                # FAZ 3: Siteden gelen otomatik rezervasyonu çakışmayan ilk müsait araca ata.
                auto_dur = reservation.get("estimatedDurationMinutes") or _reservation_duration_minutes(reservation)
                assigned_unit = find_available_vehicle_unit(reservation["date"], reservation["time"], auto_dur, 45)
                if assigned_unit is not None:
                    reservation["vehicleUnitId"] = assigned_unit
                    reservation["bufferMinutes"] = 45
                    if not reservation.get("estimatedDurationMinutes"):
                        reservation["estimatedDurationMinutes"] = auto_dur

                # VIP CRM: telefon numarasına göre müşteriyi bul/oluştur ve rezervasyona bağla
                try:
                    customer = db.find_or_create_customer(
                        reservation.get("customerPhone", ""),
                        reservation.get("customerName", ""),
                        reservation.get("customerEmail", "")
                    )
                    if customer:
                        reservation["customerId"] = customer["id"]
                        db.register_customer_booking(customer["id"], reservation.get("price", 0))
                except Exception as e:
                    print(f"[!] Müşteri eşleştirme hatası (site rezervasyonu): {e}")

                db_id = db.save_reservation_to_db(reservation)
                if db_id:
                    reservation["id"] = db_id
                    RESERVATION_ID = db_id + 1
                    _reservations_insert(reservation)  # in-memory önbelleği de senkron tut (admin/takvim buradan okuyor)
                else:
                    _reservations_insert(reservation)
                    RESERVATION_ID += 1
                    save_reservations()
                    if os.environ.get("DATABASE_URL"):
                        # DATABASE_URL tanımlıyken (yani DB kullanılması bekleniyorken) yazma
                        # başarısız oldu — bu gerçek bir sorun. DATABASE_URL hiç yoksa (bilinçli
                        # JSON-only mod) bildirim atma, o normal bir çalışma şeklidir.
                        _push_dashboard_notification(
                            f"⚠️ Rezervasyon #{reservation['id']} DB'ye yazılamadı, sadece yedek dosyada (JSON) kayıtlı — DB bağlantısını kontrol edin.",
                            ntype="system", reservation_id=reservation["id"]
                        )
                self._send_json({
                    "success": True,
                    "reservation": reservation,
                    "checkout_url": None
                })
                tip_etiket = "🚗 Transfer" if reservation["type"] == "transfer" else "👑 Şoförlü Günlük VIP"
                # ÖNEMLİ: Kredi kartı seçildiğinde bu noktada MÜŞTERİ HENÜZ ÖDEMEYİ TAMAMLAMADI —
                # kart formu bir sonraki adımda açılacak (/odeme/garanti/<id>), 3D Secure onayı
                # gelmemiş olabilir, hatta müşteri ödemeyi hiç tamamlamayabilir. Bu yüzden "Rezervasyon
                # Onayı" e-postasını ve tam detaylı "Yeni Rezervasyon" Telegram bildirimini burada
                # göndermek yanıltıcı — ödeme başarısız/yarım kalsa bile müşteri "onaylandı" e-postası
                # almış, admin de sanki kesin bir rezervasyon gelmiş gibi görmüş oluyordu (canlıda
                # fark edildi). Kart ödemesinde asıl onay e-postası + detaylı bildirim, ödeme
                # gerçekten doğrulandığında (bkz. POST /api/payments/garanti/result, procreturncode
                # 00 + hash doğrulaması) gönderiliyor. Havale seçiminde ise müşteri zaten "işlemi ben
                # tamamlayacağım" dediği için eski davranış (anında bildirim) korunuyor.
                is_card_payment = reservation.get("paymentMethod") == "kart"
                if is_card_payment:
                    send_telegram(
                        f"🅿️ <b>Rezervasyon oluşturuldu — kredi kartı ödemesi bekleniyor</b>\n"
                        f"🆔 <b>#{reservation['id']}</b> — {tip_etiket}\n"
                        f"👤 {reservation['customerName']} — 📞 {reservation['customerPhone']}\n"
                        f"💰 {reservation['price']}₺\n"
                        f"<i>Ödeme onaylanınca ayrı bir bildirim gelecek. Şimdilik müşteriye "
                        f"onay e-postası gönderilmedi.</i>"
                    )
                else:
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
                    # Rezervasyon onay e-postası gönder (sadece havale/manuel ödemede — kart
                    # ödemesinde onay e-postası ödeme doğrulanınca gönderilir, bkz. yukarıdaki not)
                    try:
                        send_confirmation_email(reservation)
                    except Exception as e:
                        print(f"[!] E-posta gönderme hatası: {e}")
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
        if path == "/api/payments/garanti/prepare":
            # Müşteri rezervasyon formunda "Kredi Kartı" seçtiğinde (veya admin'in ürettiği
            # /odeme/garanti/<id> sayfası açıldığında) çağrılır — kimlik doğrulaması YOK
            # (public), ama tutar HİÇBİR ZAMAN istemciden alınmaz; her zaman sunucudaki
            # rezervasyonun kendi price/currency alanından okunur (aksi halde biri isteği
            # değiştirip 1₺ ödeyebilirdi). Kart numarası/CVV BURADA YOK — sadece Garanti'nin
            # istediği gizli form alanlarını (hash dahil) üretip döneriz, tarayıcı bu
            # alanları kendi girdiği kart bilgileriyle birleştirip DOĞRUDAN Garanti'ye postlar.
            try:
                body = json.loads(self._read_body())
                res_id = body.get("reservationId")
                target = None
                for r in RESERVATIONS:
                    if r.get("id") == res_id:
                        target = r
                        break
                if target is None:
                    self._send_error("Rezervasyon bulunamadı.", 404)
                    return
                if target.get("paymentStatus") == "paid":
                    self._send_error("Bu rezervasyon zaten ödenmiş.", 400)
                    return
                amount = target.get("price", 0)
                try:
                    amount = float(amount)
                except (TypeError, ValueError):
                    amount = 0
                if amount <= 0:
                    self._send_error("Geçersiz tutar.", 400)
                    return
                currency = (target.get("currency") or "TRY").upper()
                form = _garanti_prepare_form(target, currency)
                form["customeripaddress"] = self.client_address[0] if self.client_address else "0.0.0.0"
                with reservations_lock:
                    target["currency"] = currency
                    target["paymentMethod"] = "kredi_karti"
                    target["garantiOrderId"] = form["orderid"]
                    target["paymentStatus"] = "link_created"
                save_reservations()
                try:
                    db.update_reservation_in_db(res_id, {
                        "currency": currency, "paymentMethod": "kredi_karti",
                        "paymentStatus": "link_created",
                        "garantiOrderId": form["orderid"],
                    })
                except Exception:
                    pass
                self._send_json({"success": True, "form": form})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                print(f"[!] Garanti prepare hatası: {e}", flush=True)
                self._send_error("Ödeme formu hazırlanamadı, lütfen tekrar deneyin veya banka havalesini seçin.", 400)
            return
        if path == "/api/payments/garanti/result":
            # Garanti, kart formunu işledikten sonra tarayıcıyı BU adrese form-post ile
            # geri gönderir (successurl == errorurl == burası; başarı/hata alanlarına
            # 'procreturncode'/'mdstatus' üzerinden bakılır). Kimlik doğrulama YOK — bunun
            # yerine 'hash'/'hashparams' alanları StoreKey ile YENİDEN hesaplanıp doğrulanır;
            # bu adım atlanırsa herkes sahte bir "ödendi" isteği gönderebilir.
            base_url = os.environ.get("PUBLIC_BASE_URL", "https://gulizvip.com.tr")
            outcome = "dogrulanamadi"
            try:
                raw = self._read_body()
                try:
                    data = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    data = dict(urllib.parse.parse_qsl(raw))
                order_id = data.get("oid") or data.get("orderid") or ""
                proc_return_code = data.get("procreturncode", "")
                response_hash = data.get("hash", "")
                hashparams = data.get("hashparams", "")
                verified = False
                # ÖNEMLİ: hash/hashparams alanları SADECE 3D Secure doğrulaması başarıyla
                # tamamlanıp provizyon adımına ulaşıldığında gönderilir. 3D adımında
                # reddedilen (ör. yanlış OTP/güvenlik kodu) işlemlerde bu alanlar HİÇ
                # gelmez — bu durum "sahte istek" değil, normal bir başarısız ödemedir.
                hash_present = bool(hashparams and response_hash)
                if hash_present:
                    param_names = [p for p in hashparams.split(":") if p]
                    digest_data = "".join(data.get(p, "") or "" for p in param_names) + GARANTI_STORE_KEY
                    calculated = _garanti_sha512_hex(digest_data)
                    verified = (calculated == response_hash.upper())
                    if not verified:
                        # Hash mevcut ama tutmuyor — bu GERÇEKTEN şüpheli bir durum (sahte istek
                        # ya da StoreKey/terminal yanlış), o yüzden kalıcı olarak loglanıyor.
                        # Kart bilgisi İÇERMEZ, sadece hash'e giren sipariş/provizyon meta verisi.
                        field_dump = " | ".join(f"{p}='{data.get(p, '')}'" for p in param_names)
                        print(f"[!] Garanti hash uyuşmazlığı — hashparams='{hashparams}' | alanlar: {field_dump}", flush=True)
                        print(f"[!] Garanti hash uyuşmazlığı — hesapladığım={calculated} | gönderilen={response_hash.upper()}", flush=True)
                target = next((r for r in RESERVATIONS if r.get("garantiOrderId") == order_id), None)
                if target is not None and verified and proc_return_code == "00":
                    outcome = "basarili"
                    already_paid = target.get("paymentStatus") == "paid"
                    if not already_paid:
                        with reservations_lock:
                            target["paymentStatus"] = "paid"
                        save_reservations()
                        try:
                            db.update_reservation_in_db(target["id"], {"paymentStatus": "paid"})
                        except Exception:
                            pass
                        if target.get("customerId"):
                            try:
                                db.register_customer_booking(target["customerId"], target.get("price", 0))
                            except Exception:
                                pass
                        _push_dashboard_notification(
                            f"💳 Ödeme alındı: {target.get('customerName', '')} — Rezervasyon #{target['id']}",
                            ntype="payment", reservation_id=target["id"]
                        )
                        # Kart ödemesinde rezervasyon oluşturulurken sadece kısa bir "ödeme
                        # bekleniyor" bildirimi gitmişti (bkz. POST /api/reservations) — asıl
                        # detaylı bildirim ve müşteri onay e-postası, ödeme GERÇEKTEN doğrulandığı
                        # bu noktada gönderiliyor.
                        tip_etiket_pay = "🚗 Transfer" if target.get("type") == "transfer" else "👑 Şoförlü Günlük VIP"
                        send_telegram(
                            f"💳 <b>Ödeme Alındı — Rezervasyon Onaylandı #{target['id']}</b>\n"
                            f"📋 <b>Tür:</b> {tip_etiket_pay}\n"
                            f"👤 <b>İsim:</b> {target.get('customerName', '')}\n"
                            f"📞 <b>Telefon:</b> {target.get('customerPhone', '')}\n"
                            f"📍 <b>Alış:</b> {target.get('pickup', '')}\n"
                            f"🏁 <b>Varış:</b> {target.get('destination', '')}\n"
                            f"📅 <b>Tarih:</b> {target.get('date', '')} {target.get('time', '')}\n"
                            f"💰 <b>Ücret:</b> {target.get('price', 0)} {target.get('currency', 'TRY')}\n"
                            f"🔌 <b>Sağlayıcı:</b> Garanti BBVA"
                        )
                        try:
                            send_confirmation_email(target)
                        except Exception as e:
                            print(f"[!] Ödeme sonrası e-posta gönderme hatası: {e}")
                elif target is None:
                    outcome = "dogrulanamadi"
                    print(f"[!] Garanti result: eşleşen rezervasyon bulunamadı (orderid={order_id})", flush=True)
                elif not hash_present:
                    # 3D Secure adımında reddedildi/iptal edildi — hash hiç üretilmedi.
                    # Şüpheli DEĞİL, normal bir başarısız ödeme senaryosu.
                    outcome = "basarisiz"
                    mdstatus = data.get("mdstatus", "")
                    md_error = data.get("mderrormessage") or data.get("errmsg") or ""
                    print(f"[i] Garanti result: 3D Secure tamamlanmadı (orderid={order_id}, mdstatus={mdstatus}, procreturncode={proc_return_code}, mesaj='{md_error}')", flush=True)
                elif not verified:
                    outcome = "dogrulanamadi"
                    print(f"[!] Garanti result: hash doğrulaması BAŞARISIZ (orderid={order_id}) — sahte istek olabilir!", flush=True)
                else:
                    outcome = "basarisiz"
                    md_error = data.get("mderrormessage") or data.get("errmsg") or ""
                    mdstatus = data.get("mdstatus", "")
                    print(f"[!] Garanti result: ödeme reddedildi (orderid={order_id}, procreturncode={proc_return_code}, mdstatus={mdstatus}, mesaj='{md_error}')", flush=True)
            except Exception as e:
                print(f"[!] Garanti result işleme hatası: {e}", flush=True)
                outcome = "dogrulanamadi"
            self.send_response(302)
            self.send_header("Location", f"{base_url}/?odeme={outcome}")
            self.end_headers()
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
        if path == "/api/admin/notifications/read":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                notif_id = body.get("id")
                for n in DASHBOARD_NOTIFICATIONS:
                    if notif_id is None or n.get("id") == notif_id:
                        n["read"] = True
                        db.mark_dashboard_notification_read_in_db(n["id"])
                save_dashboard_notifications()
                self._send_json({"success": True})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/webhooks/stripe" or path == "/api/webhooks/paytr":
            # Ödeme sağlayıcısı callback iskeleti — kimlik doğrulama (Bearer) BİLEREK yok,
            # çünkü Stripe/PayTR bu uca kendi imzalı payload'ıyla gelir. Provider seçildiğinde:
            #   Stripe: 'Stripe-Signature' header + STRIPE_WEBHOOK_SECRET ile stripe.Webhook.construct_event(...)
            #   PayTR : 'hash' alanı + PAYTR_MERCHANT_SALT ile HMAC doğrulaması
            # yapılmalı — şu an imza doğrulaması YOK (altyapı hazırlığı, canlı anahtar yok).
            provider_name = "stripe" if path.endswith("stripe") else "paytr"
            try:
                raw = self._read_body()
                try:
                    body = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    # PayTR callback'i form-encoded gönderir; ileride burada
                    # urllib.parse.parse_qs(raw) ile ayrıştırılabilir.
                    body = dict(urllib.parse.parse_qsl(raw))

                intent_id = body.get("payment_intent") or body.get("id") or body.get("merchant_oid") or ""
                event_status = (body.get("status") or body.get("payment_status") or "").lower()
                # Şimdilik gerçek bir provider bağlı olmadığından, testte doğrudan
                # reservationId + status=succeeded ile de tetiklenebilir.
                res_id = body.get("reservationId")
                is_success = event_status in ("succeeded", "success", "paid", "completed") or body.get("type") == "payment_intent.succeeded"

                target = None
                if res_id is not None:
                    target = next((r for r in RESERVATIONS if r.get("id") == res_id), None)
                elif intent_id:
                    target = next((r for r in RESERVATIONS if r.get("stripePaymentIntentId") == intent_id), None)

                if target is None:
                    # Provider henüz bağlı değilken bilinmeyen payload'lar sessizce 200 döner
                    # (gerçek entegrasyonda sağlayıcılar yeniden deneme yapar, hata vermemek önemli).
                    self._send_json({"success": True, "note": "Eşleşen rezervasyon bulunamadı, yoksayıldı."})
                    return

                if is_success:
                    # İdempotency: sağlayıcı aynı olayı tekrar gönderirse (retry) rezervasyon
                    # zaten "paid" ise bildirim/sayaç tekrar işlenmesin — çift Telegram bildirimi
                    # ve müşteri booking sayacının yanlış artmasını önler.
                    already_paid = target.get("paymentStatus") == "paid"
                    if not already_paid:
                        with reservations_lock:
                            target["paymentStatus"] = "paid"
                        save_reservations()
                        try:
                            db.update_reservation_in_db(target["id"], {"paymentStatus": "paid"})
                        except Exception:
                            pass
                        if target.get("customerId"):
                            try:
                                db.register_customer_booking(target["customerId"], target.get("price", 0))
                            except Exception:
                                pass
                        _push_dashboard_notification(
                            f"💳 Ödeme alındı: {target.get('customerName', '')} — Rezervasyon #{target['id']}",
                            ntype="payment", reservation_id=target["id"]
                        )
                        send_telegram(
                            f"💳 <b>Ödeme Alındı</b>\n👤 {target.get('customerName', '')}\n"
                            f"🆔 Rezervasyon #{target['id']}\n💰 {target.get('price', 0)} {target.get('currency', 'TRY')}\n"
                            f"🔌 Sağlayıcı: {provider_name}"
                        )
                self._send_json({"success": True})
            except Exception as e:
                print(f"[!] Webhook hatası ({provider_name}): {e}")
                self._send_json({"success": True})  # provider'a her zaman 200 dön, yeniden denemeyi önle
            return
        if path == "/api/admin/payments/create-link":
            # Dövizli Ödeme Linki Oluşturma — provider-agnostic altyapı.
            # NOT: Stripe/PayTR arasında henüz karar verilmedi. Bu uç gerçek bir ödeme
            # sağlayıcısına bağlı DEĞİLDİR — rezervasyona bir "bekleyen ödeme linki" kaydı
            # oluşturur ve provider seçilip API anahtarları tanımlandığında
            # _generate_payment_link() içindeki TODO bloklarının doldurulması yeterlidir.
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                res_id = body.get("reservationId")
                amount = body.get("amount")
                currency = (body.get("currency") or "EUR").upper()
                provider = (body.get("provider") or PAYMENT_PROVIDER or "manual").lower()
                if res_id is None or amount in (None, ""):
                    self._send_error("reservationId ve amount zorunludur.", 400)
                    return
                try:
                    amount = float(amount)
                except (TypeError, ValueError):
                    self._send_error("Geçersiz tutar.", 400)
                    return
                target = None
                for r in RESERVATIONS:
                    if r.get("id") == res_id:
                        target = r
                        break
                if target is None:
                    self._send_error("Rezervasyon bulunamadı.", 404)
                    return
                link_info = _generate_payment_link(target, amount, currency, provider)
                with reservations_lock:
                    target["currency"] = currency
                    target["paymentLink"] = link_info["url"]
                    target["stripePaymentIntentId"] = link_info.get("intentId", "")
                    target["paymentStatus"] = "link_created"
                save_reservations()
                try:
                    db.update_reservation_in_db(res_id, {
                        "currency": currency, "paymentLink": link_info["url"],
                        "stripePaymentIntentId": link_info.get("intentId", ""),
                        "paymentStatus": "link_created",
                    })
                except Exception:
                    pass
                self._send_json({"success": True, "reservation": target, "paymentLink": link_info["url"]})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/chat/send":
            try:
                body = json.loads(self._read_body())
                global CHAT_ID, CHAT_MESSAGES
                session_id = body.get("sessionId", "")
                # Bu sessionId'den daha önce hiç mesaj (ziyaretçi ya da admin) gelmiş mi?
                # Gelmediyse bu, ziyaretçi için gerçekten yeni bir oturum demektir —
                # (ör. 12 saatlik kimlik sıfırlaması sonrası dönen ziyaretçi de dahil).
                is_new_session = bool(session_id) and not any(
                    m.get("sessionId") == session_id for m in CHAT_MESSAGES
                )
                msg = {"id": CHAT_ID, "name": body.get("name", ""), "phone": body.get("phone", ""), "message": body.get("message", ""), "timestamp": datetime.now().isoformat(), "isAdmin": False, "adminName": "", "read": False, "sessionId": session_id, "isNewSession": is_new_session}
                if not msg["message"]:
                    self._send_error("Mesaj boş olamaz.", 400)
                    return
                CHAT_MESSAGES.append(msg)
                db_id = db.save_chat_message_to_db(msg)
                if db_id:
                    msg["id"] = db_id
                    CHAT_ID = db_id + 1
                else:
                    CHAT_ID += 1
                save_chat_messages()
                if is_new_session:
                    telegram_text = f"🆕 <b>YENİ ZİYARETÇİ SOHBETİ BAŞLADI</b>\n👤 <b>İsim:</b> {msg['name'] or 'Belirtilmemiş'}\n📞 <b>Telefon:</b> {msg['phone'] or 'Belirtilmemiş'}\n💬 <b>Mesaj:</b> {msg['message']}\n🆔 <b>Session:</b> <code>{msg['sessionId']}</code>\n🕐 <b>Saat:</b> {msg['timestamp']}\n\n⚠️ <b>Müşteriye iletilmesi için lütfen bu mesaja YANITLA (Reply) diyerek cevap veriniz.</b>"
                else:
                    telegram_text = f"💬 <b>Devam Eden Sohbet — Yeni Mesaj</b>\n👤 <b>İsim:</b> {msg['name'] or 'Belirtilmemiş'}\n📞 <b>Telefon:</b> {msg['phone'] or 'Belirtilmemiş'}\n💬 <b>Mesaj:</b> {msg['message']}\n🆔 <b>Session:</b> <code>{msg['sessionId']}</code>\n🕐 <b>Saat:</b> {msg['timestamp']}\n\n⚠️ <b>Müşteriye iletilmesi için lütfen bu mesaja YANITLA (Reply) diyerek cevap veriniz.</b>"
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
                db_id = db.save_chat_message_to_db(msg)
                if db_id:
                    msg["id"] = db_id
                    CHAT_ID = db_id + 1
                else:
                    CHAT_ID += 1
                save_chat_messages()
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
                db_id = db.save_chat_message_to_db(msg)
                if db_id:
                    msg["id"] = db_id
                    CHAT_ID = db_id + 1
                else:
                    CHAT_ID += 1
                save_chat_messages()
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
                db_id = db.save_chat_message_to_db(msg)
                if db_id:
                    msg["id"] = db_id
                    CHAT_ID = db_id + 1
                else:
                    CHAT_ID += 1
                save_chat_messages()
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
                db.mark_chat_session_read_in_db(session_id)
                save_chat_messages()
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
                # Not: konum tespiti (ip-api.com) dış ağ isteği, sunucu tek thread'li
                # çalıştığı için burada senkron çağrılmaz — arka plan thread'inde yapılır,
                # ziyaretçi hemen yanıt alır, konum bilgisi birazdan Telegram'a düşer.
                visitor = {
                    "sessionId": session_id,
                    "ip": ip,
                    "device": body.get("device", ""),
                    "os": body.get("os", ""),
                    "browser": body.get("browser", ""),
                    "city": "",
                    "country": "",
                    "region": "",
                    "referrer": body.get("referrer", ""),
                    "gclid": body.get("gclid", ""),
                    "fbclid": body.get("fbclid", ""),
                    "utmSource": body.get("utmSource", ""),
                    "utmMedium": body.get("utmMedium", ""),
                    "utmCampaign": body.get("utmCampaign", ""),
                    "utmTerm": body.get("utmTerm", ""),
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
                print(f"[tracking] Yeni ziyaretçi: {ip} / {body.get('device', '?')} "
                      f"| CF-Connecting-IP={self.headers.get('CF-Connecting-IP', '-')} "
                      f"XFF={self.headers.get('X-Forwarded-For', '-')}")
                threading.Thread(target=_resolve_geo_and_notify_visitor, args=(session_id, ip), daemon=True).start()
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
        if path == "/api/agent/track-event":
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                if not session_id:
                    self._send_error("sessionId gerekli.", 400)
                    return
                event_type = body.get("eventType", "")
                if not event_type:
                    self._send_error("eventType gerekli.", 400)
                    return
                data = body.get("data", {})
                # Store event in visitor session if it exists
                with visitor_lock:
                    if session_id in VISITOR_SESSIONS:
                        VISITOR_SESSIONS[session_id].setdefault("events", []).append({
                            "label": f"agent:{event_type}",
                            "detail": json.dumps(data, ensure_ascii=False),
                            "timestamp": datetime.now().isoformat(),
                        })
                # Send Telegram report in background thread
                threading.Thread(
                    target=_send_telegram_agent_report,
                    args=(session_id, event_type, data),
                    daemon=True
                ).start()
                self._send_json({"success": True})
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
                    db.delete_chat_message_from_db(message_id, session_id or None)
                    save_chat_messages()
                    self._send_json({"success": True, "message": "Mesaj silindi."})
                else:
                    self._send_error("Mesaj bulunamadı.", 404)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return

        if path == "/api/contact":
            try:
                body = json.loads(self._read_body())
                name = body.get("name", "").strip()
                phone = body.get("phone", "").strip()
                email = body.get("email", "").strip()
                message = body.get("message", "").strip()
                if not name or not phone or not message:
                    self._send_error("Ad, telefon ve mesaj zorunludur.", 400)
                    return
                global CONTACT_ID, CONTACT_MESSAGES
                visitor_ip = _get_visitor_ip(self)
                # Not: konum tespiti + Telegram gönderimi dış ağ istekleri, sunucu tek
                # thread'li çalıştığı için burada senkron yapılmaz — kaydı boş konumla
                # oluşturup hemen yanıt veriyoruz, konum arka planda çözülüp kayda işleniyor.
                contact = {
                    "id": CONTACT_ID,
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "message": message,
                    "ipAddress": visitor_ip,
                    "city": "",
                    "country": "",
                    "region": "",
                    "userAgent": self.headers.get("User-Agent", ""),
                    "status": "new",
                    "adminNote": "",
                    "timestamp": datetime.now().isoformat()
                }
                CONTACT_MESSAGES.append(contact)
                db_id = db.save_contact_message_to_db(contact)
                if db_id:
                    contact["id"] = db_id
                    CONTACT_ID = db_id + 1
                else:
                    CONTACT_ID += 1
                save_contact_messages()
                _push_dashboard_notification(
                    f"📬 Yeni iletişim mesajı: {name} ({phone})",
                    ntype="contact",
                    reservation_id=None
                )
                print(f"[contact] Yeni iletisim formu: {name} / {phone} / IP={visitor_ip} "
                      f"| CF-Connecting-IP={self.headers.get('CF-Connecting-IP', '-')} "
                      f"XFF={self.headers.get('X-Forwarded-For', '-')}")
                self._send_json({"success": True, "message": "Mesajiniz alindi."})
                threading.Thread(target=_resolve_geo_and_notify_contact, args=(contact["id"], visitor_ip, name, phone, email, message, contact["timestamp"]), daemon=True).start()
            except json.JSONDecodeError:
                self._send_error("Gecersiz JSON.", 400)
            return
        if path == "/api/admin/flights/refresh":
            # Admin panelindeki "Uçuşları Şimdi Güncelle" butonu — 02:00/13:00'i
            # beklemeden veya sunucuyu yeniden başlatmadan manuel tetikleme.
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            threading.Thread(target=refresh_flights, daemon=True).start()
            self._send_json({"success": True, "message": "Güncelleme başlatıldı, birkaç saniye içinde tamamlanır."})
            return
        self._send_error("Bulunamadı", 404)

    def do_PUT(self):
        global RESERVATIONS
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
                save_prices()
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
                    save_slider_images()
                    self._send_json({"success": True, "images": SLIDER_IMAGES})
                elif action == "delete":
                    index = body.get("index")
                    if index is None or not isinstance(index, int) or index < 0 or index >= len(SLIDER_IMAGES):
                        self._send_error("Geçersiz index.", 400)
                        return
                    SLIDER_IMAGES.pop(index)
                    save_slider_images()
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
                        save_slider_images()
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
                    save_slider_images()
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
                if action == "update" or action == "edit":
                    # Not: admin.html 'edit' gönderir; 'update' de geriye dönük uyumluluk için kabul edilir.
                    res_id = body.get("id")
                    if res_id is None:
                        self._send_error("Rezervasyon ID gerekli.", 400)
                        return
                    for r in RESERVATIONS:
                        if r.get("id") == res_id:
                            # Not: alan adları reservation dict'iyle aynı (camelCase) olmalı —
                            # önceki snake_case liste hiçbir zaman eşleşmiyordu (sessiz bug, düzeltildi).
                            with reservations_lock:
                                for key in ("status", "customerName", "customerPhone", "customerEmail",
                                            "pickup", "destination", "flightNumber", "date", "time",
                                            "passengers", "notes", "price", "paymentMethod", "paymentStatus",
                                            "vehicleUnitId", "bufferMinutes", "estimatedDurationMinutes",
                                            "distanceKm", "isManual"):
                                    if key in body:
                                        r[key] = body[key]
                            save_reservations()
                            # DB'ye de kaydet — INSERT değil UPDATE (tekrar eden kayıt oluşmasın diye)
                            try:
                                db.update_reservation_in_db(res_id, body)
                            except Exception:
                                pass
                            self._send_json({"success": True, "reservation": r})
                            return
                    self._send_error("Rezervasyon bulunamadı.", 404)
                elif action == "update-status":
                    # Onayla / Tamamla / İptal Et butonları bu action'ı gönderir.
                    res_id = body.get("id")
                    new_status = body.get("status")
                    if res_id is None or not new_status:
                        self._send_error("Rezervasyon ID ve durum gerekli.", 400)
                        return
                    for r in RESERVATIONS:
                        if r.get("id") == res_id:
                            with reservations_lock:
                                r["status"] = new_status
                            save_reservations()
                            try:
                                db.update_reservation_status_in_db(res_id, new_status)
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
                    _reservations_replace([r for r in RESERVATIONS if r.get("id") != res_id])
                    save_reservations()
                    # DB'den de sil — önceden bu satır eksikti, silinen kayıtlar PostgreSQL'de
                    # kalıyordu ve sunucu DB'den yeniden yüklendiğinde geri gelebiliyordu.
                    try:
                        db.delete_reservation_from_db(res_id)
                    except Exception:
                        pass
                    self._send_json({"success": True, "message": "Rezervasyon silindi."})
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/contact-messages":
            global CONTACT_MESSAGES
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                msg_id = body.get("id")
                if msg_id is None:
                    self._send_error("Mesaj ID gerekli.", 400)
                    return
                if action == "update" or action == "edit":
                    for m in CONTACT_MESSAGES:
                        if m.get("id") == msg_id:
                            for key in ("status", "adminNote", "name", "phone", "email", "message"):
                                if key in body:
                                    m[key] = body[key]
                            save_contact_messages()
                            try:
                                db.update_contact_message_in_db(msg_id, body)
                            except Exception:
                                pass
                            self._send_json({"success": True, "contact": m})
                            return
                    self._send_error("Mesaj bulunamadı.", 404)
                elif action == "delete":
                    before_count = len(CONTACT_MESSAGES)
                    CONTACT_MESSAGES = [m for m in CONTACT_MESSAGES if m.get("id") != msg_id]
                    if len(CONTACT_MESSAGES) == before_count:
                        self._send_error("Mesaj bulunamadı.", 404)
                        return
                    save_contact_messages()
                    try:
                        db.delete_contact_message_from_db(msg_id)
                    except Exception:
                        pass
                    self._send_json({"success": True, "message": "Mesaj silindi."})
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/customers":
            # VIP Müşteri CRM Hafızası — müşteri notu/VIP durumu güncelleme
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                customer_id = body.get("id")
                if customer_id is None:
                    self._send_error("Müşteri ID gerekli.", 400)
                    return
                ok = db.update_customer(customer_id, body)
                if not ok:
                    self._send_error("Müşteri güncellenemedi (DB yok veya bulunamadı).", 400)
                    return
                customer = db.get_customer_by_id(customer_id)
                self._send_json({"success": True, "customer": customer})
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
        if path == "/api/admin/pages":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            # Admin: tüm sayfalar (DB + fallback)
            try:
                db_pages = db.get_all_pages()
                if db_pages:
                    self._send_json({"success": True, "pages": db_pages})
                    return
            except Exception:
                pass
            pages = []
            for slug, data in PAGE_CONTENT.items():
                pages.append({
                    "slug": slug,
                    "title": data.get("title", ""),
                    "subtitle": data.get("subtitle", ""),
                    "is_active": data.get("is_active", True),
                })
            self._send_json({"success": True, "pages": pages})
            return
        if path.startswith("/api/admin/page/") and path.endswith("/active"):
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            slug = path[len("/api/admin/page/"):-len("/active")]
            slug = SLUG_ALIASES.get(slug, slug)
            if slug not in PAGE_CONTENT:
                self._send_error("Sayfa bulunamadı.", 404)
                return
            try:
                body = json.loads(self._read_body())
                is_active = body.get("is_active", True)
                PAGE_CONTENT[slug]["is_active"] = is_active
                try:
                    db.set_page_active(slug, is_active)
                except Exception as e:
                    print(f"[!] Admin sayfa aktiflik ({slug}) DB hatası: {e}")
                save_page_content_to_json()
                self._send_json({"success": True, "slug": slug, "is_active": is_active})
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
                subtitle = body.get("subtitle", "")
                is_active = body.get("is_active", PAGE_CONTENT[slug].get("is_active", True))
                if not title or not content:
                    self._send_error("Başlık ve içerik gerekli.", 400)
                    return

                PAGE_CONTENT[slug] = {
                    "title": title,
                    "subtitle": subtitle,
                    "is_active": is_active,
                    "content": content,
                    "updatedAt": datetime.utcnow().isoformat()
                }
                # DB'ye de kaydet
                try:
                    db.save_page_content(slug, title, content, subtitle)
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
        if path == "/api/admin/fleet":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                global VEHICLES, VEHICLE_ID
                if action == "add":
                    vehicle = {
                        "id": VEHICLE_ID,
                        "name": body.get("name", ""),
                        "count": int(body.get("count", 1)),
                        "main_image": body.get("main_image", ""),
                        "gallery_images": body.get("gallery_images", ""),
                        "passenger_count": int(body.get("passenger_count", 6)),
                        "luggage_count": int(body.get("luggage_count", 6)),
                        "features": body.get("features", ""),
                        "order": len(VEHICLES)
                    }
                    if not vehicle["name"]:
                        self._send_error("Araç adı gerekli.", 400)
                        return
                    VEHICLE_ID += 1
                    VEHICLES.append(vehicle)
                    save_vehicles()
                    self._send_json({"success": True, "vehicle": vehicle, "vehicles": VEHICLES})
                elif action == "update":
                    vid = body.get("id")
                    for v in VEHICLES:
                        if v["id"] == vid:
                            if "name" in body: v["name"] = body["name"]
                            if "count" in body: v["count"] = int(body["count"])
                            if "main_image" in body: v["main_image"] = body["main_image"]
                            if "gallery_images" in body: v["gallery_images"] = body["gallery_images"]
                            if "passenger_count" in body: v["passenger_count"] = int(body["passenger_count"])
                            if "luggage_count" in body: v["luggage_count"] = int(body["luggage_count"])
                            if "features" in body: v["features"] = body["features"]
                            if "order" in body: v["order"] = int(body["order"])
                            save_vehicles()
                            self._send_json({"success": True, "vehicle": v, "vehicles": VEHICLES})
                            return
                    self._send_error("Araç bulunamadı.", 404)
                elif action == "delete":
                    vid = body.get("id")
                    VEHICLES = [v for v in VEHICLES if v["id"] != vid]
                    save_vehicles()
                    self._send_json({"success": True, "vehicles": VEHICLES})
                elif action == "reorder":
                    from_idx = body.get("fromIndex")
                    to_idx = body.get("toIndex")
                    if from_idx is None or to_idx is None:
                        self._send_error("fromIndex ve toIndex gerekli.", 400)
                        return
                    if 0 <= from_idx < len(VEHICLES) and 0 <= to_idx < len(VEHICLES):
                        item = VEHICLES.pop(from_idx)
                        VEHICLES.insert(to_idx, item)
                        save_vehicles()
                        self._send_json({"success": True, "vehicles": VEHICLES})
                    else:
                        self._send_error("Geçersiz index aralığı.", 400)
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                self._send_error(str(e), 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/vehicle-units":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                global VEHICLE_UNITS
                if action == "add":
                    next_id = (max((u.get("id", 0) for u in VEHICLE_UNITS), default=0)) + 1
                    unit = {
                        "id": next_id,
                        "name": body.get("name", ""),
                        "vehicleId": body.get("vehicleId"),
                        "plateNumber": body.get("plateNumber", ""),
                        "isActive": body.get("isActive", True),
                        "sortOrder": body.get("sortOrder", next_id),
                    }
                    if not unit["name"]:
                        self._send_error("Araç birimi adı gerekli.", 400)
                        return
                    VEHICLE_UNITS.append(unit)
                    save_vehicle_units()
                    self._send_json({"success": True, "unit": unit, "units": VEHICLE_UNITS})
                elif action == "update":
                    uid = body.get("id")
                    for u in VEHICLE_UNITS:
                        if u.get("id") == uid:
                            for key in ("name", "vehicleId", "plateNumber", "isActive", "sortOrder"):
                                if key in body:
                                    u[key] = body[key]
                            save_vehicle_units()
                            self._send_json({"success": True, "unit": u, "units": VEHICLE_UNITS})
                            return
                    self._send_error("Araç birimi bulunamadı.", 404)
                elif action == "delete":
                    uid = body.get("id")
                    VEHICLE_UNITS = [u for u in VEHICLE_UNITS if u.get("id") != uid]
                    save_vehicle_units()
                    self._send_json({"success": True, "units": VEHICLE_UNITS})
                elif action == "auto_generate":
                    # Mevcut filodaki (vehicles.json/DB) her araç TÜRÜ için, "count" adedince
                    # numaralı birim oluşturur (örn. count:3 → "Vito 1", "Vito 2", "Vito 3").
                    # Zaten birimi olan araç türleri için sadece eksik olan sayıda ekler — güvenle
                    # tekrar çalıştırılabilir.
                    existing_by_vehicle = {}
                    for u in VEHICLE_UNITS:
                        vid = u.get("vehicleId")
                        existing_by_vehicle[vid] = existing_by_vehicle.get(vid, 0) + 1
                    next_id = (max((u.get("id", 0) for u in VEHICLE_UNITS), default=0)) + 1
                    created = []
                    for v in VEHICLES:
                        vid = v.get("id")
                        already = existing_by_vehicle.get(vid, 0)
                        total_count = int(v.get("count", 1))
                        for i in range(already + 1, total_count + 1):
                            unit = {
                                "id": next_id,
                                "name": f"{v.get('name', 'Araç')} {i}",
                                "vehicleId": vid,
                                "plateNumber": "",
                                "isActive": True,
                                "sortOrder": next_id,
                            }
                            VEHICLE_UNITS.append(unit)
                            created.append(unit)
                            next_id += 1
                    save_vehicle_units()
                    self._send_json({"success": True, "created": created, "units": VEHICLE_UNITS})
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                self._send_error(str(e), 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        if path == "/api/admin/calendar/block":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                action = body.get("action", "")
                global CALENDAR_BLOCKS
                if action == "add":
                    if not body.get("vehicleUnitId") or not body.get("date") or not body.get("startTime") or not body.get("endTime"):
                        self._send_error("Araç, tarih, başlangıç ve bitiş saati gerekli.", 400)
                        return
                    next_id = (max((b.get("id", 0) for b in CALENDAR_BLOCKS), default=0)) + 1
                    block = {
                        "id": next_id,
                        "vehicleUnitId": body.get("vehicleUnitId"),
                        "date": body.get("date", ""),
                        "startTime": body.get("startTime", ""),
                        "endTime": body.get("endTime", ""),
                        "reason": body.get("reason", "Bakım / Şahsi Kullanım"),
                        "createdAt": datetime.now().isoformat(),
                    }
                    CALENDAR_BLOCKS.append(block)
                    save_calendar_blocks()
                    self._send_json({"success": True, "block": block})
                elif action == "delete":
                    bid = body.get("id")
                    CALENDAR_BLOCKS = [b for b in CALENDAR_BLOCKS if b.get("id") != bid]
                    save_calendar_blocks()
                    self._send_json({"success": True})
                else:
                    self._send_error("Geçersiz aksiyon.", 400)
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                self._send_error(str(e), 400)
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
                    result = db.update_destination(dest_id, body)
                    if result:
                        self._send_json({"success": True, "destination": db.get_destination(dest_id)})
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
                    self._send_error("Gecersiz aksiyon.", 400)
            except json.JSONDecodeError:
                self._send_error("Gecersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        self._send_error("Bulunamadı", 404)

# ─── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    db.init_db()  # DATABASE_URL varsa gerekli tabloları/config'i oluşturur; yoksa sessizce atlar
    load_page_content()
    load_prices()
    load_vehicles()
    load_slider_images()
    load_vehicle_units()
    load_calendar_blocks()
    load_reservations()
    load_chat_messages()
    load_contact_messages()
    load_dashboard_notifications()
    try:
        server = http.server.HTTPServer((HOST, PORT), GulizHandler)
        print(f"[v] Guliz VIP Backend running on http://{HOST}:{PORT}")

        # Uçuş verisi ilk kez arka planda çekilir — sunucu bunu beklemeden hemen
        # istekleri dinlemeye başlar (Railway health check'i geciktirmemek için).
        scheduler = threading.Thread(target=scheduler_loop, daemon=True)
        scheduler.start()

        visitor_cleanup = threading.Thread(target=visitor_cleanup_loop, daemon=True)
        visitor_cleanup.start()

        server.serve_forever()
    except Exception as e:
        print(f"[!] __main__ CRASH: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)