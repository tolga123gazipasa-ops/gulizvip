# Güliz VIP Projesi

## Proje Bilgisi
- **Sahibi:** Güliz VIP — Alanya/Gazipaşa merkezli VIP transfer hizmeti
- **Domain:** gulizvip.com.tr
- **Backend Sunucu:** Python stdlib (http.server) — port 8081
- **Status:** Aktif geliştirme — Railway rollback sonrası mock-only sürüm

## Backend (server.py)
- Çalıştırma: `python3 server.py` (WORKSPACE dizininde)
- Statik dosyaları `/sessions/.../mnt/gulizvip/` altından serve eder
- HMAC-SHA256 token tabanlı auth: `POST /api/admin/login`
- Uçuş verileri **OpenSky Network API** + mock fallback (GZP/LTGZ, AYT/LTAI)
- Scheduler: `threading.Timer` ile 5 dk'da bir `refresh_flights()`
- Status simulation: saat karşılaştırması (dakika bazında), %15 rötar ihtimali
- PostgreSQL entegrasyonu (`db.py`) — psycopg2-binary ile, `DATABASE_URL` env var üzerinden
  - reservations + config tabloları
  - Yoksa `reservations.json` fallback
- CORS tüm endpoint'lerde açık

### Konfigürasyon
- `ADMIN_USER=admin`, `ADMIN_PASS=gulizvip2026`
- `SECRET_KEY=guliz-vip-hmac-secret-2026`, `TOKEN_TTL=86400` (24s)
- `HOST=0.0.0.0`, `PORT=8081`
- `GOOGLE_MAPS_API_KEY=AIzaSyD-IGkbR6iyxvdeQ_Cfekjks3KOWMD7RKw` (Places + Distance Matrix + Geocoding)
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` env var veya admin paneli

### API Endpoints
| Endpoint | Method | Auth | Açıklama |
|---|---|---|---|
| `/api/flights` | GET | Hayır | Public uçuş verisi (mock) |
| `/api/maps/config` | GET | Hayır | Google Maps API key (frontend için) |
| `/api/maps/distance` | GET | Hayır | Distance Matrix API proxy |
| `/api/maps/geocode` | GET | Hayır | Geocoding API proxy |
| `/api/unit-price` | GET | Hayır | Güncel km başı birim fiyat |
| `/api/slider-images` | GET | Hayır | Public slider görsel listesi |
| `/api/bank-accounts` | GET | Hayır | Banka hesap bilgileri (Halkbank, VakıfBank) |
| `/api/reservations` | POST | Hayır | Yeni rezervasyon oluşturma |
| `/api/chat/send` | POST | Hayır | Ziyaretçi canlı destek mesajı gönderme |
| `/api/chat/messages` | GET | Hayır | Ziyaretçi kendi mesajlarını alma (since, sessionId) |
| `/api/admin/login` | POST | Hayır | Token al |
| `/api/admin/flights` | GET | Bearer | Admin uçuş verisi |
| `/api/admin/flights` | PUT | Bearer | Uçuş güncelle |
| `/api/admin/check` | GET | Bearer | Token doğrulama |
| `/api/admin/unit-price` | PUT | Bearer | Admin birim fiyat güncelleme |
| `/api/admin/bank-accounts` | PUT | Bearer | Banka hesap bilgilerini güncelleme |
| `/api/admin/slider-images` | PUT | Bearer | Slider yönetimi (add/delete/reorder/replace) |
| `/api/admin/slider-images/upload` | POST | Bearer | Slider dosya yükleme (multipart) |
| `/api/admin/reservations` | GET | Bearer | Tüm rezervasyonları listeleme |
| `/api/admin/reservations` | PUT | Bearer | Rezervasyon güncelleme (status/delete) |
| `/api/admin/chat/messages` | GET | Bearer | Admin tüm mesajları okuma |
| `/api/admin/chat/reply` | POST | Bearer | Admin yanıt gönderme |
| `/api/admin/chat/read` | POST | Bearer | Mesajları okundu işaretleme |
| `/api/admin/telegram/config` | GET | Bearer | Telegram yapılandırmasını okuma (masked token) |
| `/api/admin/telegram/config` | PUT | Bearer | Telegram bot token ve chat ID güncelleme |
| `/api/admin/telegram/test` | POST | Bearer | Test mesajı gönderme |
| Statik dosyalar | GET | Hayır | index.html, admin.html vs. |

## Frontend

### index.html
- Tek sayfa, slider + booking engine + GZP/AYT flight board
- **Slider:** `/api/slider-images`'dan dinamik yüklenir, 4sn aralıkla otomatik geçiş
- `renderFlights(airport)` -> `/api/flights` -> 4 tbody'yi doldur
- 120sn setInterval ile auto-refresh
- `switchGzpTab()` / `switchAytTab()` — gelen/giden tab geçişi
- **Google Maps Entegrasyonu:**
  - API key `/api/maps/config`'den alınır, client-side暴露 edilmez
  - Places Autocomplete: `dest-input` (varış) ve `tahsis-pickup-input` (tahsis alış) alanlarında
  - Mesafe hesaplama: `/api/maps/distance` proxy'si ile KM + süre + tahmini fiyat gösterimi
  - `priceFromDestFallback()` — API hatasında bölge bazlı sabit fiyat
- **İki booking formu:** "Havalimanı Transferi" ve "Şoförlü Günlük VIP" (tahsis) — 3 adımlı flow
- Fiyat: ~25₺/km taban (varsayılan), min 500₺
  - Admin paneli "Fiyat Ayarları" sekmesinden km başı birim fiyat değiştirilebilir
  - `/api/unit-price` (public GET) — güncel birim fiyatı döndürür
  - `/api/admin/unit-price` (auth PUT) — admin birim fiyatı günceller
- **Banka Havalesi:** `/api/bank-accounts`'tan hesap bilgileri çekilir, Halkbank + VakıfBank IBAN gösterilir
- **Canlı Destek:** Chat widget (sağ alt köşe), 3sn polling ile `/api/chat/messages?since=<id>&sessionId=<uuid>`
  - Ziyaretçi ad/soyad/telefon bilgisi alınır, UUID sessionId localStorage'da saklanır
  - Admin yanıtları 3sn'de bir poll edilir, yeni mesajlar toast bildirimi gösterir
- **Telegram Entegrasyonu:** Yeni canlı destek mesajı ve rezervasyonlarda admin Telegram kanalına bildirim
  - Bot token ve chat ID admin paneli → Ayarlar → Telegram Ayarları'ndan yapılandırılır
  - send_telegram() fonksiyonu HTML formatında mesaj gönderir

### admin.html
- Operasyon paneli — HMAC-SHA256 token ile login
- Login: admin/gulizvip2026 (öntanımlı)
- Dashboard, rezervasyonlar, fiyat ayarları, uçuşlar, slider, canlı destek, ayarlar sekmeleri
- **Slider yönetimi:** Görsel ekleme (URL veya dosya yükleme), silme, sıralama; `/api/admin/slider-images` API'si ile
- GZP ve AYT canlı uçuş tabloları (`gzp-admin-tbody`, `ayt-admin-tbody`)
- 120sn setInterval ile auto-refresh
- Token localStorage'da saklanır, `/api/admin/check` ile doğrulanır

## Önemli Notlar
- Uçuş verileri **OpenSky Network API** ile gerçek zamanlı (GZP/LTGZ, AYT/LTAI) — başarısız olursa **mock data** fallback
- OpenSky: anonim katmanda ~400 istek/gün, istekler arası 12sn minimum interval
- Callsign → havayolu adı eşleştirmesi: THY/TK → Turkish Airlines, PGT/PC → Pegasus, SXS/XQ → SunExpress, CAI/XC → Corendon
- ICAO → havalimanı adı dönüşümü: 40+ yaygın havalimanı kodu (Türkiye + Avrupa)
- PostgreSQL (`db.py`) mevcut ancak zorunlu değil — `DATABASE_URL` yoksa `reservations.json` fallback
- psycopg2-binary harici kütüphane olarak kullanılır, geri kalanı Python stdlib
- Sadece Python stdlib kullanılır (harici kütüphane yok)
- Çalışma dizini: `C:\Users\MSI\OneDrive\Desktop\gulizvip\`
- VM'de bash path: `/sessions/tender-wizardly-edison/mnt/gulizvip/`
