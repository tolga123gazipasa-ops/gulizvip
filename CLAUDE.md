# Güliz VIP Projesi

## Proje Bilgisi
- **Sahibi:** Güliz VIP — Alanya/Gazipaşa merkezli VIP transfer hizmeti
- **Domain:** gulizvip.com.tr
- **Backend Sunucu:** Python stdlib (http.server) — port 8081
- **Status:** Aktif geliştirme

## Backend (server.py)
- Çalıştırma: `python3 server.py` (WORKSPACE dizininde)
- Statik dosyaları `/sessions/.../mnt/gulizvip/` altından serve eder
- HMAC-SHA256 token tabanlı auth: `POST /api/admin/login`
- Uçuş verileri **in-memory** — persist edilmez, DB yok
- Uçuş listesi 4 diziden oluşur: GZP gelen/giden (9+9) + AYT gelen/giden (13+13) = 44 uçuş
- Scheduler: `threading.Timer` ile 5 dk'da bir `refresh_flights()`
- Status simulation: saat karşılaştırması (dakika bazında), %15 rötar ihtimali
- CORS tüm endpoint'lerde açık

### Konfigürasyon
- `ADMIN_USER=admin`, `ADMIN_PASS=gulizvip2026`
- `SECRET_KEY=guliz-vip-hmac-secret-2026`, `TOKEN_TTL=86400` (24s)
- `HOST=0.0.0.0`, `PORT=8081`
- `GOOGLE_MAPS_API_KEY=AIzaSyD-IGkbR6iyxvdeQ_Cfekjks3KOWMD7RKw` (Places + Distance Matrix + Geocoding)

### API Endpoints
| Endpoint | Method | Auth | Açıklama |
|---|---|---|---|
| `/api/flights` | GET | Hayır | Public uçuş verisi |
| `/api/admin/login` | POST | Hayır | Token al |
| `/api/admin/flights` | GET | Bearer | Admin uçuş verisi |
| `/api/admin/flights` | PUT | Bearer | Uçuş güncelle |
| `/api/admin/check` | GET | Bearer | Token doğrulama |
| `/api/maps/config` | GET | Hayır | Google Maps API key (frontend için) |
| `/api/maps/distance` | GET | Hayır | Distance Matrix API proxy (origins, destinations, mode) |
| `/api/maps/geocode` | GET | Hayır | Geocoding API proxy (address parametresi) |
| `/api/unit-price` | GET | Hayır | Güncel km başı birim fiyat |
| `/api/admin/unit-price` | PUT | Bearer | Admin birim fiyat güncelleme |
| `/api/slider-images` | GET | Hayır | Public slider görsel listesi |
| `/api/admin/slider-images` | PUT | Bearer | Slider yönetimi (add/delete/reorder/replace) |
| `/api/admin/slider-images/upload` | POST | Bearer | Slider dosya yükleme (multipart) |
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
- Fiyat: ~25₺/km taban (varsayılan), min 500₺
  - Admin paneli "Fiyat Ayarları" sekmesinden km başı birim fiyat değiştirilebilir
  - `/api/unit-price` (public GET) — güncel birim fiyatı döndürür
  - `/api/admin/unit-price` (auth PUT) — admin birim fiyatı günceller

### admin.html
- Operasyon paneli — HMAC-SHA256 token ile login
- Login: admin/gulizvip2026 (öntanımlı)
- Dashboard, rezervasyonlar, fiyat ayarları, uçuşlar, slider, canlı destek, ayarlar sekmeleri
- **Slider yönetimi:** Görsel ekleme (URL veya dosya yükleme), silme, sıralama; `/api/admin/slider-images` API'si ile
- GZP ve AYT canlı uçuş tabloları (`gzp-admin-tbody`, `ayt-admin-tbody`)
- 120sn setInterval ile auto-refresh
- Token localStorage'da saklanır, `/api/admin/check` ile doğrulanır

## Önemli Notlar
- Uçuş verileri **simüle edilmiştir** (mock data) — gerçek API/scraper yok
- Sadece Python stdlib kullanılır (harici kütüphane yok)
- Çalışma dizini: `C:\Users\MSI\OneDrive\Desktop\gulizvip\`
- VM'de bash path: `/sessions/tender-wizardly-edison/mnt/gulizvip/`
