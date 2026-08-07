# Güliz VIP — Proje Durumu (Kaldığımız Yer)

Son güncelleme: 2026-08-07 (öğleden sonra)

## Şu An Neredeyiz

CRM/Ödeme + Teknik SEO paketleri push edildi (Tolga kendi bilgisayarından push etti). Üstüne bugün sitemap'e 3 yeni sayfa eklendi: **`69a8eaa`** commit'i henüz push edilmedi.

### Hemen Yapılması Gereken

```
cd C:\proje\gulizvip
git push origin main
```

- `69a8eaa` — Sitemap'e İletişim, SSS, Hızlı Rezervasyon rota sayfaları eklendi (`/iletisim`, `/sss`, `/hizli-rezervasyon` — kendi title/description/canonical'ı var, ilgili anasayfa bölümüne otomatik kaydırıyor)

Push edince Railway otomatik deploy edecek (GitHub → Railway bağlı).

### Push Sonrası Yapılacaklar

1. **Google Search Console'a sitemap gönder**: Site Haritaları sekmesinde kutuya `sitemap.xml` yaz, Gönder'e bas (tam yolu Google otomatik tamamlıyor).
2. **admin.html indeks kontrolü**: URL denetimi'nden `https://gulizvip.com.tr/admin.html`'i kontrol et. "Dizine eklendi" çıkarsa → URL Kaldırma aracından tam adresi girip geçici (6 aylık) kaldırma talebi gönder. Çıkmıyorsa ekstra bir şey yapmana gerek yok (robots.txt zaten engelliyor, hiç indekslenmeyecek).
3. **JSON-LD aggregateRating'i güncelle**: `index.html` içindeki `"aggregateRating": {"ratingValue": "4.9", "reviewCount": "127"}` değerleri YER TUTUCUDUR. Google İşletme Profili'ndeki gerçek puan/yorum sayısıyla güncellemezsen ya da bu bloğu silmezsen, Google'ın structured-data (sahte yorum) politikasını ihlal etmiş olursun.

## Bu Oturumda Yapılanlar (Özet)

### 1. VIP CRM + Dövizli Ödeme Linki + WhatsApp (commit d3d2038)
- DB: `customers` tablosu + `reservations`'a `customer_id/currency/payment_link/stripe_payment_intent_id` kolonları
- Her rezervasyonda telefona göre otomatik müşteri eşleştirme/oluşturma (`find_or_create_customer`)
- `GET /api/admin/customers/search` — isim/telefon autocomplete
- `POST /api/admin/payments/create-link` — **provider-agnostic** ödeme linki (Stripe/PayTR HENÜZ SEÇİLMEDİ, sadece altyapı hazır — `PAYMENT_PROVIDER` env var + `_generate_payment_link()` içindeki TODO'lar doldurulunca gerçek entegrasyon eklenecek)
- `POST /api/webhooks/stripe` ve `/api/webhooks/paytr` — imza doğrulaması yok (altyapı hazırlığı), başarılı ödemede yeşil "Ödendi" + Telegram bildirimi
- Admin UI: rezervasyon kartında "Ödeme Linki Oluştur" + "WhatsApp'tan Gönder" butonları; Araç Takvimi hızlı rezervasyon formunda müşteri autocomplete + Müşteri Kimlik Kartı

### 2. Teknik SEO Altyapısı (commit d7b82d7)
- `index.html` head: genişletilmiş keywords, hreflang (tr + x-default — en/de/ru için gerçek sayfa yokken eklemek Search Console hatası üretir)
- JSON-LD: `LocalBusiness`+`TaxiService` şeması + görünür SSS ile eşleşen `FAQPage` şeması
- `GET /sitemap.xml`, `GET /robots.txt` — dinamik üretiliyor (server.py)
- `ROUTE_SEO_PAGES` — 7 popüler rota (`/gazipasa-alanya-transfer` vb.) kendi title/description/canonical'ıyla, aynı sayfa şablonunu paylaşıyor
- `admin.html` → çift korumalı noindex (meta + `X-Robots-Tag` header) + robots.txt disallow
- Eksik `alt`/`loading="lazy"` etiketleri tamamlandı, `/sayfa/` sayfalarındaki çift `<h1>` sorunu düzeltildi

### 3. Footer sosyal linkler
- WhatsApp (`wa.me/902426062548`) ve Instagram (`instagram.com/gulizviptransfer`) linkleri footer'a eklendi (önceden `#` idi, boş duruyordu)

## Açık Kalanlar / Konuşulan Ama Henüz Karar Verilmeyenler

- [ ] **Push + deploy** (yukarıda)
- [ ] **Ödeme sağlayıcısı seçimi**: Stripe mi PayTR mi? Karar verilince gerçek entegrasyon eklenecek
- [ ] **aggregateRating gerçek değerleri** (yukarıda)
- [ ] **Opsiyonel `/iletisim` sayfası**: İletişim şu an anasayfanın bir bölümü (#iletisim), ayrı URL değil — Tolga isterse rota-SEO tekniğiyle ayrı bir sayfa açılabilir, karar bekleniyor
- [ ] Task #37 (eski liste): "Her bölgeye 4 galeri resmi ekle" — durumu teyit edilmedi, muhtemelen hâlâ eksik
- [ ] Destinasyonların 4'er galeri resminin production DB'sine gerçekten yazıldığı hiç teyit edilmedi (çok eski açık madde)

## Önemli Notlar

- Backend Python stdlib `http.server` (server.py), PostgreSQL opsiyonel (`db.py`), yoksa JSON dosya fallback
- Admin login: `admin@guliztransfer.com` / `Guliz2025!`
- Assistant admin şifresini kendisi giremez (güvenlik kuralı) — login her zaman Tolga tarafından yapılmalı
- Assistant GitHub'a push edemez (kimlik bilgisi yok) — push her zaman Tolga'nın kendi bilgisayarından yapılmalı
