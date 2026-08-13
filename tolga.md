# Güliz VIP — Proje Durumu (Kaldığımız Yer)

Son güncelleme: 2026-08-12

## GÜNCEL: PayPas iptal edildi, Garanti BBVA Sanal POS'a geçildi

PayPas'ta 401 "Invalid API credentials" hatası mağaza onaylandıktan ve anahtarlar
teyit edildikten sonra bile çözülemedi (PayPas desteğine yönlendirilmişti). Senin
kararınla PayPas tamamen kaldırıldı, yerine **Garanti BBVA Sanal POS** (3D'li Peşin,
https://dev.garantibbva.com.tr/sanalpos-satis-pesin-3dli) entegre edildi — commit `8fa5d1a`.

### Nasıl çalışıyor
Garanti'nin modeli PayPas'tan tamamen farklı: PayPas'ta müşteriyi onların hazır ödeme
sayfasına yönlendiriyorduk. Garanti'de kart formu (isim/numara/SKT/CVV) **bizim
sitemizde** — ama kart bilgisi hiçbir zaman bizim sunucumuza uğramıyor: tarayıcı,
bizim ürettiğimiz "gizli" banka alanlarıyla (hash dahil) birlikte kart bilgisini
DOĞRUDAN Garanti'nin sunucusuna post ediyor.

- Müşteri booking formunda "Kredi Kartı (Online)" seçip rezervasyonu tamamladığında
  `/odeme/garanti/<rezervasyonId>` sayfasına yönlendiriliyor — orada kart formu var.
- Admin panelindeki "Ödeme Linki Oluştur" / "WhatsApp'tan Gönder" özelliği de aynı
  `/odeme/garanti/<id>` linkini üretiyor — müşteriye WhatsApp'tan gönderilebilir.
- Kart formu gönderildiğinde: `/api/payments/garanti/prepare` gizli alanları + hash'i
  üretir → tarayıcı bunları kart bilgisiyle birleştirip gerçek bir HTML form-post ile
  doğrudan Garanti'ye gönderir → Garanti işlemi yapıp `/api/payments/garanti/result`
  adresine geri post eder → biz `hash`/`hashparams`'ı StoreKey ile YENİDEN hesaplayıp
  doğruluyoruz (sahte istekler bu adımda elenir) → geçerliyse rezervasyon `paid`
  işaretlenir + dashboard bildirimi + Telegram mesajı gider → müşteri anasayfaya
  `?odeme=basarili|basarisiz|dogrulanamadi` ile döner.

### Doğrulama durumu — ✅ UÇTAN UCA BAŞARILI (12 Ağustos, canlı TEST ortamında)
Hash algoritması resmi dokümantasyondaki PHP/C# örnekleriyle karşılaştırıldı ve
local mock testlerden geçti, ama gerçek Garanti test sunucusuyla ilk denemelerde
`secure3dhash` sürekli reddediliyordu (procreturncode=99, "Güvenlik Kodu hatalı",
3D ekranına hiç ulaşmadan). Kök neden: hash hesaplamasında taksit sayısı (installment
count) alanı `0` olarak kullanılıyordu ama form alanına gönderilen gerçek değer boş
string (`""`) idi — Garanti hash'i form alanlarıyla karşılaştırdığı için tutmuyordu.
Bağımsız, çalışan bir prod referans entegrasyonu (github.com/bsevgin/garantipos)
incelenerek düzeltildi: artık hash ve form alanı aynı değeri paylaşıyor (commit `12e58a5`).

Düzeltme sonrası canlı TEST ortamında (resmi test kartı `4282209004348015`) tam bir
ödeme denemesi yapıldı: `mdstatus=1` (tam doğrulama), `procreturncode=00` (onaylandı),
hash doğrulandı, rezervasyon `paid` işaretlendi, dashboard bildirimi + Telegram mesajı
gitti, müşteri `?odeme=basarili` ile anasayfaya döndü. **Entegrasyon çalışıyor.**

Not: Test kartında 3D Secure OTP ekranı hiç çıkmadı — bu normal, Garanti'nin test
kartı "sürtünmesiz" (frictionless) modda otomatik doğruluyor. Gerçek müşteri
kartlarında normal şartlarda SMS/OTP ekranı çıkacaktır.

### Aktifleştirmek İçin Yapman Gerekenler (Railway → Variables)
Kod, tanımlanmazsa Garanti'nin **TEST ortamı** resmi öntanımlı değerleriyle çalışır
(gerçek para geçmez). Gerçek/canlı ödeme almak için Railway'e ekle:
1. `GARANTI_MODE` = `PROD`
2. `GARANTI_MERCHANT_ID` = gerçek üye işyeri numaran
3. `GARANTI_TERMINAL_ID` = gerçek terminal numaran
4. `GARANTI_PROV_USER_ID` = provizyon kullanıcı adın (genelde `PROVAUT`)
5. `GARANTI_TERMINAL_USER_ID` = banka sana verdiyse o değer (varsayılan `GARANTI`)
6. `GARANTI_PROVISION_PASSWORD` = provizyon şifren
7. `GARANTI_STORE_KEY` = 3D Secure mağaza anahtarın (storekey)

Bu bilgileri ben giremem/göremem — güvenlik kuralı gereği API anahtarlarını hiçbir
zaman kendim bir forma/panele girmiyorum, Railway Variables'a kendin eklemelisin.

### PROD kurulumu neden hâlâ eksik — Garanti'nin resmi "Sanal Pos İlk Adımlar" kitapçığı (13 Ağustos)
Tolga'nın attığı `sanalposilkadimlar.pdf` incelendi. Bu doküman bir API entegrasyon
kılavuzu DEĞİL — Garanti'nin yeni sanal POS müşterisi için hesap aktivasyon sürecini
anlatıyor. Yani eksik olan kod değil, **banka tarafında henüz tamamlanmamış bir kurulum
süreci**. Bu adımları sadece Tolga yapabilir (TCKN, şifre, admin portalı girişi
gerektiriyor — bunları benim güvenlik kuralı gereği kendim giremem).

**Adım adım (kitapçıktan):**
1. Başvuru onaylandıktan sonra `sanalpos@garantibbva.com.tr`'den "Garanti Sanal Pos
   Login Bilgileriniz" başlıklı bir e-posta gelir (aktivasyon linki **24 saat geçerli**).
2. E-postadaki "Giriş Yap" butonuna tıkla → `pos.garantibbva.com.tr` üzerinde telefon
   numaranı SMS koduyla doğrula → güvenlik sorusu belirle → parola oluştur.
3. Sonra `https://pos.garantibbva.com.tr/web/login` adresinden giriş yap:
   Kullanıcı Adı = **TCKN**, Parola = az önce oluşturduğun parola.
4. "Sanal Pos admin portalı" açılır — burada **PROVAUT / PROVOOS / PROVRFN**
   kullanıcıları için ayrı şifreler belirlemen isteniyor (özel karakter zorunlu:
   `#$%&*()-+=}[]\:,./`). **`GARANTI_PROVISION_PASSWORD` env var'ı = PROVAUT
   kullanıcısına verdiğin bu şifre.**
5. **KRİTİK — "3D Secure Key Değiştirme" bölümü:** Admin portalında oluşturacağın
   "3D SECURE KEY" **tam 24 karakter HEX** olmak zorunda (örnek:
   `123456789012345678901234`). Kitapçık, şifreni hex'e çevirip hem panelde hem
   kodda AYNI çevrilmiş hex değerinin kullanılması gerektiğini özellikle vurguluyor
   (çeviri için `http://codebeautify.org/string-hex-converter` öneriliyor). **Bu
   HEX değer = `GARANTI_STORE_KEY` env var'ı.** Şu an TEST modunda kodda varsayılan
   olarak `12345678` kullanılıyor (Garanti'nin herkese açık TEST ortamı sabiti) —
   bu PROD'da ASLA kullanılamaz, panelde ürettiğin gerçek 24-karakter hex değeriyle
   değiştirilmesi şart.
6. `GARANTI_MERCHANT_ID` ve `GARANTI_TERMINAL_ID` kitapçıkta açıkça geçmiyor — admin
   portalına (`pos.garantibbva.com.tr`) giriş yaptıktan sonra ayarlar/işyeri bilgileri
   ekranında görünmesi gerekiyor; bulamazsa `ETicaretDestek@garantibbva.com.tr`'e
   sorabilir.

**Özet — Tolga'nın yapması gerekenler:** (1) aktivasyon e-postasını bul/tıkla → henüz
gelmediyse veya süresi dolduysa `ETicaretDestek@garantibbva.com.tr`'den yeniden iste,
(2) `pos.garantibbva.com.tr/web/login`'e TCKN ile giriş yap, (3) PROVAUT şifresini
belirle, (4) admin panelinde 24-karakter HEX 3D Secure Key üret, (5) Merchant
ID/Terminal ID'yi panelden bul, (6) bu 7 değeri Railway Variables'a gir, (7)
`GARANTI_MODE=PROD` yap ve redeploy et. Kod tarafında yapılacak bir şey YOK, sistem
zaten bu değerleri okumaya hazır.

### Hemen Yapılması Gereken
```
cd C:\proje\gulizvip
git push origin main
```
Push edince Railway otomatik deploy edecek. Sonra TEST modunda (env var eklemeden,
varsayılan değerlerle) resmi test kartıyla bir kere uçtan uca dene, çalışırsa yukarıdaki
7 env var'ı ekleyip `GARANTI_MODE=PROD` ile canlıya geç.

---

## ESKİ (artık geçersiz) — PayPas "Invalid API credentials" (401) notları

Kredi kartı akışı kurulurken sırasıyla 3 gerçek bug bulunup düzeltildi:

1. ✅ Cloudflare 502'yi kendi hata sayfasıyla değiştiriyordu → hata kodları 400'e çekildi (commit `b95bf63`)
2. ✅ paypas.com.tr da Cloudflare arkasında, Python'ın User-Agent'sız isteği bot sanılıp 403/error 1010 ile reddediliyordu → `SCRAPE_USER_AGENT` eklendi (commit `f725db2`)
3. ✅ (muhtemel asıl sebep) **`urllib.request.Request(..., headers={...})` özel header isimlerini sessizce küçük harfe çeviriyordu** — `X-SECRET-KEY` aslında `X-secret-key` olarak gidiyordu, PayPas'ın sunucusu muhtemelen case-sensitive kontrol yaptığı için "Invalid API credentials" dönüyordu. `req.headers[...]` ile doğrudan atama yapılarak (add_header() atlanarak) düzeltildi, yerel testte header'ın artık doğru case ile gittiği doğrulandı (commit `05a70a1`).

Anahtarlarda boşluk/kopyala-yapıştır sorunu YOKTU (maskeli teşhis logu bunu netleştirdi — uzunluklar ve baş/son karakterler tam eşleşiyordu), mağaza da onaylıydı — demek ki hep bu header case sorunuymuş.

**Sıradaki adım:** Tolga push edip tekrar deneyecek. Eğer 401 hâlâ devam ederse, bir sonraki şüpheli: PayPas'ın "Beklemede" ekranındaki Merchant ID/Secret Key'in TEST moduna ait olması, mağaza onaylandıktan sonra panelde YENİ (LIVE) anahtarlar üretilmiş olabilir — panelden tekrar kontrol edilmeli.

## PayPas Sanal POS Entegrasyonu — Teknik Özet

Ödeme sağlayıcısı olarak **PayPas** (paypas.com.tr) seçildi ve gerçek entegrasyon yazıldı — commit `a2f48fb`.

- `_generate_payment_link()` içine `provider == "paypas"` dalı eklendi: `POST /checkout/sessions` ile gerçek PayPas checkout linki üretiyor (kart bilgisini biz hiç görmüyoruz, müşteri PayPas'ın kendi sayfasında giriyor)
- Yeni yardımcı fonksiyonlar: `_paypas_request`, `_paypas_create_checkout_session`, `_paypas_get_session`
- Yeni endpoint'ler:
  - `GET /api/payments/paypas/success/<res_id>` — PayPas'tan dönüşte `session_id` ile ödemeyi PayPas'a sorup doğrular (client_reference_id eşleşmesi + payment_status=paid), doğrulanırsa rezervasyonu `paid` işaretler + dashboard bildirimi + Telegram, sonra anasayfaya yönlendirir
  - `GET /api/payments/paypas/cancel/<res_id>` — iptalde anasayfaya yönlendirir
- Mevcut `/api/admin/payments/create-link` ve admin panelindeki "Ödeme Linki Oluştur" butonu **provider=paypas ile aynen çalışıyor**, admin UI'da değişiklik gerekmedi

### Aktifleştirmek İçin Yapman Gerekenler (Railway → Variables)
1. `PAYMENT_PROVIDER` = `paypas`
2. `PAYPAS_MERCHANT_KEY` = PayPas panelindeki gerçek **canlı** Merchant API Key (`PPMRC_...`)
3. `PAYPAS_SECRET_KEY` = PayPas panelindeki gerçek **canlı** Secret Key (`sk_live_...`)

Bu üç anahtarı ben giremem/göremem — güvenlik kuralı gereği API anahtarlarını hiçbir zaman kendim bir forma/panele girmiyorum. Railway Variables sekmesine kendin ekleyip deploy'u tetiklemen gerekiyor.

### Test Etmeden Önce
- PayPas panelinden **test** Merchant Key/Secret Key alınıp önce onlarla denenmesi öneriliyor (dokümantasyonda `PPMRC_123456` / `sk_test_abc123xyz789secret` örnek olarak geçiyor ama bunlar gerçek değil, sadece doküman örneği)
- Uçtan uca test: admin panelden bir rezervasyona "Ödeme Linki Oluştur" → PayPas ödeme sayfasına yönlenmeli → test kartla öde → `/api/payments/paypas/success/<id>` üzerinden anasayfaya dönmeli ve rezervasyon admin panelde "ödendi" görünmeli
- **Henüz gerçek bir PayPas hesabıyla uçtan uca test edilmedi** (Merchant Key yok) — sadece mock/sahte HTTP response ile birim testi yapıldı, gerçek API davranışı biraz farklı çıkabilir

### Hemen Yapılması Gereken
```
cd C:\proje\gulizvip
git push origin main
```
Push edince Railway otomatik deploy edecek. Sonra yukarıdaki 3 env var'ı ekleyip yeniden deploy et.

## Şu An Neredeyiz (7 Ağustos, eski notlar)

Bugün dört şey tamamlandı ve commit edildi, henüz **push edilmedi**:

1. Havalimanı transfer formunda yolcu seçeneği "1-4 Kişi" → "1-9 Kişi" (Vito gerçek kapasitesi)
2. Dashboard genişletildi: Araç Takvimi (bugün), Ödeme & CRM bildirimleri, Canlı Destek önizlemesi widget'ları anasayfaya eklendi
3. Canlı destek sistemi geliştirildi (2 ayrı adımda):
   - Ad/telefon artık native `prompt()` penceresi yerine sohbet kutusunun içinde, aynı pencerede soruluyor; girilen isim mesaj yazarken üstte görünüyor
   - **Ziyaretçi kimliği 12 saat sonra otomatik sıfırlanıyor** (sadece sitede/index.html'de — admin panelinde hiçbir değişiklik yok)
   - Yeni bir ziyaretçi/oturum mesaj yazdığında admin panelinde sohbet listesinde ve dashboard önizlemesinde yeşil **"YENİ"** rozeti çıkıyor (bir oturumu açıp okuyunca rozet kalkıyor)
   - Telegram bildirimleri artık ayrışıyor: yeni bir sohbet başladığında "🆕 YENİ ZİYARETÇİ SOHBETİ BAŞLADI", aynı kişi devam ettiğinde "💬 Devam Eden Sohbet — Yeni Mesaj" başlığıyla geliyor
4. **Canlı destek/iletişim formu/dashboard bildirimleri artık kalıcı** — daha önce sadece sunucu belleğinde tutuluyordu, Railway her redeploy/restart'ta hepsini siliyordu. Şimdi `db.py`'ye 3 yeni tablo (`chat_messages`, `contact_messages`, `dashboard_notifications`) + reservations/customers ile aynı DB-first + JSON-yedek deseni eklendi. Restart sonrası veri kaybolmuyor (canlı test edildi: mesaj gönder → sunucuyu yeniden başlat → mesaj hâlâ orada).
   - **Not:** Ödeme webhook'unun güvenlik açığı (imza doğrulaması yok) bilinçli olarak bu kapsamın dışında bırakıldı — Tolga ödeme sağlayıcısını (Stripe/PayTR) seçtiğinde ele alınacak.
5. **Admin paneli görsel yenileme** — panel çok "sade" görünüyordu, index.html'deki gerçek logo (`/logo.png`) admin.html'de hiç kullanılmıyordu (sadece metin logosu vardı). Yapılanlar:
   - Login ekranı ve sidebar artık gerçek logoyu gösteriyor (resim yüklenemezse otomatik metin logosuna döner)
   - Gölge/köşe yuvarlama ölçeği eklendi, sidebar'a gradient, stat kartlarına hover efekti + renkli ikon rozetleri, butonlara gradient/hover kalkma efekti, badge'ler pill şekline döndü
   - Mobil görünüm bozulmadı (değişiklikler responsive kurallardan önceki asıl tanımlar üzerinde yapıldı)
   - Bu sandboxta gerçek tarayıcı olmadığından ekran görüntüsüyle doğrulanamadı — deploy sonrası Tolga'nın gözden geçirmesi gerekiyor, beğenmediği bir şey olursa ince ayar yapılabilir.

### Hemen Yapılması Gereken

```
cd C:\proje\gulizvip
git push origin main
```

Push edince Railway otomatik deploy edecek (GitHub → Railway bağlı).

## Bugüne Kadar Yapılanlar (Özet)

### 1. VIP CRM + Dövizli Ödeme Linki + WhatsApp
- DB: `customers` tablosu + `reservations`'a `customer_id/currency/payment_link/stripe_payment_intent_id` kolonları
- Her rezervasyonda telefona göre otomatik müşteri eşleştirme/oluşturma
- `GET /api/admin/customers/search` — isim/telefon autocomplete
- `POST /api/admin/payments/create-link` — **provider-agnostic** ödeme linki (Stripe/PayTR HENÜZ SEÇİLMEDİ, altyapı hazır)
- `POST /api/webhooks/stripe` ve `/api/webhooks/paytr` — imza doğrulaması yok (altyapı hazırlığı)
- Admin UI: rezervasyon kartında "Ödeme Linki Oluştur" + "WhatsApp'tan Gönder" butonları; Araç Takvimi hızlı rezervasyon formunda müşteri autocomplete + Müşteri Kimlik Kartı

### 2. Teknik SEO Altyapısı
- Meta/OG/Twitter, hreflang (tr + x-default)
- JSON-LD: `LocalBusiness`+`TaxiService` + `FAQPage` şeması
- `GET /sitemap.xml`, `GET /robots.txt` — dinamik üretiliyor
- `ROUTE_SEO_PAGES` — 10 rota (7 transfer rotası + İletişim/SSS/Hızlı Rezervasyon)
- `admin.html` → çift korumalı noindex (meta + header) + robots.txt disallow
- Eksik `alt`/`lazy loading` tamamlandı, çift `<h1>` sorunu düzeltildi

### 3. Footer sosyal linkler
- WhatsApp ve Instagram linkleri footer'a eklendi

### 4. Dashboard genişletme + Canlı destek geliştirmeleri (bugün)
- Yukarıda anlatıldı

## Açık Kalanlar / Konuşulan Ama Henüz Karar Verilmeyenler

- [ ] **Push + deploy** (yukarıda)
- [ ] **Ödeme sağlayıcısı seçimi**: Stripe mi PayTR mi?
- [ ] **aggregateRating gerçek değerleri**: `index.html` içindeki `"aggregateRating": {"ratingValue": "4.9", "reviewCount": "127"}` YER TUTUCUDUR — Google İşletme Profili'ndeki gerçek puanla güncellenmeli, aksi halde Google'ın sahte-yorum politikasını ihlal eder
- [ ] **admin.html indeks kontrolü**: Search Console → URL denetimi'nden kontrol edilmedi, hâlâ açık
- [ ] **Google Search Console'a sitemap gönderimi**: teyit edilmedi
- [ ] **Opsiyonel `/iletisim` sayfası**: şu an anasayfanın bir bölümü, ayrı URL değil
- [ ] Task #37 (eski liste): "Her bölgeye 4 galeri resmi ekle" — durumu teyit edilmedi

## Önemli Notlar

- Backend Python stdlib `http.server` (server.py), PostgreSQL opsiyonel (`db.py`), yoksa JSON dosya fallback
- Admin login: `admin@guliztransfer.com` / `Guliz2025!`
- Assistant admin şifresini kendisi giremez (güvenlik kuralı) — login her zaman Tolga tarafından yapılmalı
- Assistant GitHub'a push edemez (kimlik bilgisi yok) — push her zaman Tolga'nın kendi bilgisayarından yapılmalı
