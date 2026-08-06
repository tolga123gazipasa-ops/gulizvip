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
- Uçuş verileri **canlı web scraping** ile havalimanlarının kendi resmi sitelerinden çekilir (mock veri tamamen kaldırıldı — bkz. "Uçuş Verisi (Canlı Scraping)")
- Scheduler: arka plan thread'i, sunucu başlarken 1 kez + günde 2 kez (02:00, 13:00) `refresh_flights()`
- PostgreSQL entegrasyonu (`db.py`) — psycopg2-binary ile, `DATABASE_URL` env var üzerinden
  - reservations + config tabloları
  - Yoksa `reservations.json` fallback
- CORS tüm endpoint'lerde açık

### Konfigürasyon
- `ADMIN_USER=admin@guliztransfer.com`, `ADMIN_PASS=Guliz2025!`
- `SECRET_KEY=guliz-vip-hmac-secret-2026`, `TOKEN_TTL=86400` (24s)
- `HOST=0.0.0.0`, `PORT=8081`
- `GOOGLE_MAPS_API_KEY=AIzaSyD-IGkbR6iyxvdeQ_Cfekjks3KOWMD7RKw` (Places + Distance Matrix + Geocoding)
- **Resend Email:** `RESEND_API_KEY` env var üzerinden, `resend` paketi ile. From: `info@gulizvip.com.tr`
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

### Email (Resend)
- **Paket:** `resend>=4.0` (`requirements.txt`)
- **API Key:** `RESEND_API_KEY` çevre değişkeni — `os.environ.get("RESEND_API_KEY")`
- **Gönderici:** `Güliz VIP Transfer <info@gulizvip.com.tr>`
- **Şablon:** `email_template.html` (çalışma dizininde)
- **7 dinamik yer tutucu:** `{musteri_isim}`, `{alis_noktasi}`, `{varis_noktasi}`, `{tarih}`, `{saat}`, `{yolcu_sayisi}`, `{tahmini_tutar}`
- **Tetikleme:** Rezervasyon başarıyla kaydedildikten sonra `send_confirmation_email(reservation)` çağrılır
- **From adresi:** `info@gulizvip.com.tr` (sabit) — DNS/Cloudflare MX kayıtları hazır
- **`resend` paketi opsiyonel:** `try/except ImportError` ile korunur, yoksa sessizce atlanır

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
- Login: admin@guliztransfer.com / Guliz2025! (öntanımlı)
- Dashboard, rezervasyonlar, fiyat ayarları, uçuşlar, slider, canlı destek, ayarlar sekmeleri
- **Slider yönetimi:** Görsel ekleme (URL veya dosya yükleme), silme, sıralama; `/api/admin/slider-images` API'si ile
- GZP ve AYT canlı uçuş tabloları (`gzp-admin-tbody`, `ayt-admin-tbody`)
- 120sn setInterval ile auto-refresh
- Token localStorage'da saklanır, `/api/admin/check` ile doğrulanır

## Önemli Notlar
### Uçuş Verisi (Canlı Scraping)
- Mock veri ve OpenSky entegrasyonu tamamen kaldırıldı. Uçuş bilgileri doğrudan havalimanlarının kendi resmi sitelerinden çekilir:
  - **GZP (Gazipaşa):** `gzpairport.com`'un dahili JSON API'si — `GET https://gzpairport.com/Home/getCurrentFlights?flightLeg=DEP|ARR`. Temiz JSON döner, HTML parse gerekmez.
  - **AYT (Antalya):** `antalya-airport.aero` sunucu tarafında render edilmiş HTML tablo (Telerik ASP.NET) — `BeautifulSoup4` ile parse edilir. Tablo `div#ContentPlaceHolder_ForNested_ContentPlaceHolder_ForNested_div_list` içinde; hücreler `td.flightnum`, `td.from`, `td.airline`, `td.scheduled`, `td.estimated`, `td.status` class'larıyla ayrıştırılır.
    - Gelen: `/yolcu-ve-ziyaretciler/ucus-bilgileri/tum-hatlar-gelis`
    - Giden: `/yolcu-ve-ziyaretciler/ucus-bilgileri/dis-hat-gidis`
- Scraping fonksiyonları: `scrape_gzp_flights(flight_leg)`, `scrape_ayt_flights(direction)` — `server.py`. Her ikisi de hata durumunda `None` döner, `refresh_flights()` bu durumda önbellekteki (`flight_cache`) son başarılı veriyi KORUR, sıfırlamaz.
- Zamanlama: sunucu başlarken arka planda (HTTP sunucusunu bloklamadan) 1 kez, sonrasında günde 2 kez (02:00 / 13:00) — `scheduler_loop()`. Ziyaretçi trafiği scraping'i tetiklemez, her istek `flight_cache`'teki hazır veriyi okur.
- İstekler arası 2-3sn rastgele bekleme + gerçek tarayıcı `User-Agent` header'ı (IP ban riskine karşı).
- Endpoint'ler: `/api/flights` (mevcut, GZP+AYT birleşik), `/api/flights/live?airport=gzp|ayt` (yeni, tek havalimanı), `/api/admin/flights` (admin, aynı cache'i okur).
- `beautifulsoup4` — `requirements.txt`'e eklendi, opsiyonel import (`try/except ImportError`), yüklü değilse sadece AYT scraping atlanır.
- PostgreSQL (`db.py`) mevcut ancak zorunlu değil — `DATABASE_URL` yoksa `reservations.json` fallback
  - Schema: `customer_name`, `customer_phone`, **`customer_email`**, `pickup`, `destination`, `flight_number`, `date`, `time`, `passengers`, `duration`, `notes`, `price`, `payment_method`, `payment_status`, `status`
- psycopg2-binary ve resend harici kütüphaneler olarak kullanılır, geri kalanı Python stdlib
- Sadece Python stdlib kullanılır (harici kütüphane yok)
- Çalışma dizini: `C:\Users\MSI\OneDrive\Desktop\gulizvip\`
- VM'de bash path: `/sessions/tender-wizardly-edison/mnt/gulizvip/`

### VIP CRM + Dövizli Ödeme Linki + WhatsApp (Ağustos 2026)
- **DB:** `customers` tablosu (`id, name, phone, email, notes, total_bookings, total_spent, is_vip`); `reservations` tablosuna `customer_id, currency, payment_link, stripe_payment_intent_id` kolonları eklendi (`payment_status` zaten mevcuttu).
- **CRM backend (`db.py`):** `search_customers()`, `get_customer_by_id/phone()`, `find_or_create_customer()` (telefona göre eşleştirir/oluşturur), `update_customer()`, `register_customer_booking()` (5+ rezervasyonda otomatik VIP).
- **Endpoint'ler:**
  - `GET /api/admin/customers/search?q=` — isim/telefon autocomplete (DB yoksa `RESERVATIONS`'tan fallback türetir)
  - `PUT /api/admin/customers` — müşteri notu/VIP güncelleme
  - `POST /api/admin/payments/create-link` — provider-agnostic ödeme linki (Stripe/PayTR henüz seçilmedi — `PAYMENT_PROVIDER` env var + `_generate_payment_link()` içindeki TODO'lar doldurulunca gerçek entegrasyon eklenir)
  - `POST /api/webhooks/stripe` / `POST /api/webhooks/paytr` — imza doğrulaması YOK (altyapı hazırlığı); başarılı ödemede `paymentStatus='paid'` + dashboard bildirimi + Telegram
  - `GET /api/admin/notifications`, `POST /api/admin/notifications/read` — ödeme vb. dashboard bildirimleri
  - `/api/reservations` (public) ve `/api/admin/calendar/quick-reservation` artık her rezervasyonda `find_or_create_customer()` çağırıyor
- **Admin UI:** Rezervasyon detay kartında "Ödeme Linki Oluştur" (currency+tutar) ve "WhatsApp'tan Gönder" (`wa.me` linki) butonları; takvimde ödenmiş rezervasyonlar yeşil (`paymentStatus==='paid'`); Araç Takvimi hızlı rezervasyon formunda isim/telefon autocomplete + "Müşteri Kimlik Kartı" (geçmiş transfer, toplam harcama, not kopyalama).

### SEO Altyapısı (Ağustos 2026)
- **index.html `<head>`:** title/description/keywords, canonical, hreflang (şu an sadece `tr` + `x-default` — en/de/ru için gerçek sunucu taraflı sayfa yokken hreflang eklemek Search Console hatası üretir), OG + Twitter Card etiketleri.
- **JSON-LD:** `LocalBusiness`+`TaxiService` şeması (areaServed, telephone, priceRange, `aggregateRating` — **DİKKAT:** 4.9/127 değerleri yer tutucudur, gerçek Google puanınızla güncellenmeli, aksi halde Google'ın structured-data politikalarını ihlal eder) + görünür SSS bölümüyle birebir eşleşen `FAQPage` şeması.
- **`/robots.txt`, `/sitemap.xml`:** `server.py`'de dinamik üretilir. robots.txt `/admin`, `/admin.html`, `/api/`, `/uploads/` disallow eder. sitemap.xml ana sayfa + aktif `/sayfa/*` + `ROUTE_SEO_PAGES` rotalarını listeler.
- **Dinamik Rota SEO:** `ROUTE_SEO_PAGES` (server.py) — `/gazipasa-alanya-transfer` gibi 7 popüler rota. `_render_route_seo_page()` index.html'i okuyup title/description/canonical/OG/Twitter etiketlerini rotaya özel yapar; görünür sayfa içeriği ana sayfayla aynıdır (gerçek benzersiz içerik değildir — ileride her rotaya özel metin eklenmesi daha güçlü SEO sağlar).
- **admin.html gizleme:** `<meta name="robots" content="noindex,...">` + sunucu tarafında `X-Robots-Tag: noindex, nofollow` header'ı (çift koruma) + robots.txt disallow.
