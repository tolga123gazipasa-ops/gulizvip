# Prompt: Garanti BBVA Sanal POS ile Kredi Kartı Ödeme Ekranı Kurulumu

Aşağıdaki metni, kredi kartıyla ödeme alınacak başka bir sistemde (örn. Güliz Lojistik)
çalışan bir Claude/AI asistanına aynen verebilirsin. Güliz VIP Transfer projesinde
bu entegrasyonu uçtan uca kurup canlıda test ettik, aşağıdaki prompt o deneyimin
özeti ve karşılaştığımız gerçek hataların çözümlerini içeriyor.

---

## PROMPT (kopyala-yapıştır)

Bu sistemde Garanti BBVA Sanal POS ile "3D'li Peşin" kredi kartı ödeme akışı kurmanı istiyorum. Bu entegrasyonu daha önce başka bir projede (Güliz VIP Transfer) uçtan uca kurup canlıda gerçek parayla test ettik — aşağıdaki mimariyi ve öğrendiğimiz dersleri aynen uygula.

### Genel Model
Kart bilgisi (numara/isim/SKT/CVV) hiçbir zaman bizim sunucumuza uğramaz. Kart formu bizim sitemizde gösterilir ama form, bizim ürettiğimiz "gizli" banka alanlarıyla (hash dahil) BİRLİKTE tarayıcıdan DOĞRUDAN Garanti'nin sunucusuna post edilir. Garanti işlemi yapar (3D Secure/SMS OTP dahil) ve sonucu, önceden belirlediğimiz `successurl`/`errorurl` adresine (ikisi de aynı adres olabilir) form-post ile geri gönderir.

Akış:
1. Müşteri "Kredi Kartı ile Öde" seçer → backend'e sipariş/rezervasyon ID'si gönderilir
2. Backend `POST /api/payments/prepare` — sipariş ID'sini alır, TUTARI KENDİ VERİTABANINDAN okur (istemciden ASLA tutar kabul etme, biri isteği değiştirip 1₺ ödeyebilir), Garanti'nin istediği gizli form alanlarını + hash'i üretip döner
3. Frontend, dönen alanları kullanıcının girdiği kart bilgileriyle birleştirip gerçek bir `<form>` ile doğrudan Garanti'ye post eder
4. Garanti 3D Secure/SMS OTP akışını kendi sayfasında yürütür
5. İşlem bitince Garanti, `successurl`/`errorurl`'e (aynı adres olabilir) sonucu form-post eder
6. Backend `POST /api/payments/result` — gelen `hash`/`hashparams` alanlarını StoreKey ile YENİDEN hesaplayıp doğrular, `procreturncode == "00"` ise sipariş "ödendi" işaretlenir

### Gerekli Ortam Değişkenleri (env var)
```
GARANTI_MODE               "TEST" | "PROD"
GARANTI_MERCHANT_ID        Üye işyeri numarası
GARANTI_TERMINAL_ID        Terminal numarası
GARANTI_PROV_USER_ID       Provizyon kullanıcı adı (genelde "PROVAUT")
GARANTI_TERMINAL_USER_ID   Terminal kullanıcı adı
GARANTI_PROVISION_PASSWORD PROVAUT kullanıcısının şifresi
GARANTI_STORE_KEY          3D Secure mağaza anahtarı (HEX)
```
Bu değerleri ASLA sen (AI) bir forma/panele girme — kullanıcı Garanti'nin admin portalından (pos.garantibbva.com.tr) kendisi oluşturup env var'lara kendisi ekler. Sen sadece kod tarafını hazırlarsın.

**ÖNEMLİ — StoreKey formatı:** Garanti panelinde "3D Secure Key" oluşturulurken resmi PDF dokümantasyonu "24 karakter HEX" diyor ama bu yanıltıcı — gerçek sistem **24 BAYT (=48 hex karakter)** istiyor. "24 byte Hex data girilmelidir" hatası alırsan 48 karakterlik bir hex string üret (örn. `secrets.token_hex(24)` Python'da).

### Hash Algoritması (dokümantasyondan doğrulandı, aynen uygula)
```python
import hashlib

def sha1_hex(text):
    # ISO-8859-9 (Türkçe) encoding + SHA1, BÜYÜK harf hex
    return hashlib.sha1(text.encode("iso-8859-9", errors="replace")).hexdigest().upper()

def sha512_hex(text):
    return hashlib.sha512(text.encode("iso-8859-9", errors="replace")).hexdigest().upper()

def secure3dhash(terminal_id, order_id, amount_minor, currency_code, success_url, error_url, txn_type, installment_count, store_key, provision_password):
    # hashedpassword = SHA1(provizyon şifresi + terminal ID'nin 9 haneye SOLDAN SIFIRLA doldurulmuş hali)
    hashed_password = sha1_hex(provision_password + terminal_id.zfill(9))
    data = (
        f"{terminal_id}{order_id}{amount_minor}{currency_code}"
        f"{success_url}{error_url}{txn_type}{installment_count}{store_key}{hashed_password}"
    )
    return sha512_hex(data)
```
- `amount_minor`: tutar kuruş/cent cinsinden tam sayı (örn. 150.50 TL → 15050)
- `currency_code`: TRY=949, USD=840, EUR=978, GBP=826, JPY=392
- `txn_type`: peşin satış için sabit `"sales"`
- **KRİTİK HATA KAYNAĞI:** `installment_count` (taksit sayısı) peşin işlemde BOŞ STRING (`""`) olmalı — hash hesaplamasında da, form alanına gönderilen değerde de AYNI değer (boş string) kullanılmalı. İkisi farklı olursa (örn. hash'te `0` yazıp forma `""` gönderirsen) Garanti hash'i reddeder, `procreturncode=99` "Güvenlik Kodu hatalı" hatası alırsın, 3D ekranına hiç ulaşmadan.

### Form Alanları (Garanti'ye post edilecek)
```
mode, apiversion (512), secure3dsecuritylevel (3D_PAY), terminalprovuserid,
terminaluserid, terminalmerchantid, terminalid, orderid, successurl, errorurl,
customeremailaddress, companyname, lang (tr), txntimestamp, refreshtime,
secure3dhash, txnamount, txntype (sales), txncurrencycode, txninstallmentcount
```
Post URL:
- TEST: `https://sanalposprovtest.garantibbva.com.tr/servlet/gt3dengine`
- PROD: `https://sanalposprov.garanti.com.tr/servlet/gt3dengine`

### Sonuç Doğrulama (banka geri dönüşü)
Garanti'nin geri post ettiği alanlar arasında `hash` ve `hashparams` var. `hashparams`, hangi alanların hangi sırayla hash'e girdiğini belirten `:` ile ayrılmış bir liste (örn. `clientid:oid:authcode:procreturncode:response:mdstatus:cavv:eci:md:rnd:`). **ASLA bu sırayı hardcode etme** — gelen `hashparams` alanını PARSE EDİP, o sıradaki alan adlarına göre YİNE GELEN VERİDEN değerleri al, sonuna StoreKey ekleyip SHA512 al, gelen `hash` ile karşılaştır:
```python
param_names = [p for p in hashparams.split(":") if p]
digest_data = "".join(data.get(p, "") or "" for p in param_names) + STORE_KEY
calculated = sha512_hex(digest_data)
verified = (calculated == response_hash.upper())
```
Sadece `verified == True` VE `procreturncode == "00"` ise siparişi "ödendi" işaretle. Hash tutmuyorsa bu sahte bir istek olabilir — logla ama işleme onaylama.

### KRİTİK — Sipariş Eşleştirme Kalıcılığı (canlıda gerçek bir bug'a sebep oldu)
Prepare adımında ürettiğin `orderid`'i, siparişin/rezervasyonun HANGİ kalıcı veritabanı sen kullanıyorsan ORAYA hemen kaydet (sadece in-memory değişken veya sadece dosya yedeği DEĞİL). Bizim projede bu alan sadece JSON yedeğine yazılıyordu, PostgreSQL'e kaydedilmiyordu — tam bir canlı test sırasında sunucu (Railway) redeploy olunca, taze başlayan sunucu bu alanı kaybetti, Garanti'nin geri dönüşü hiçbir siparişle eşleşemedi ("eşleşen kayıt bulunamadı" hatası). Prepare adımında üretilen `orderid` MUTLAKA ana veritabanına senkron şekilde yazılmalı.

### Ödeme Sayfası UX
- `?odeme=basarili|basarisiz|dogrulanamadi` gibi bir query param ile ana sayfaya/durum sayfasına yönlendir
- `basarisiz`: banka reddetti (procreturncode ≠ 00) — kullanıcıya "kartınızdan ödeme alınamadı" göster, alternatif ödeme yöntemi (havale vb.) öner
- `dogrulanamadi`: hash tutmadı veya sipariş eşleşmedi — "ödemenizi kontrol ediyoruz, size dönüş yapılacak" göster, arka planda destek ekibine bildirim gönder

### Test/Teşhis Notları
- Kart formu gönderilip SMS/OTP ekranı HİÇ açılmadan hata alınıyorsa → sorun muhtemelen bizim ilk isteğimizde (hash/terminal/mod uyuşmazlığı), Garanti'nin gateway'i isteği daha bankaya iletmeden reddediyor demektir
- SMS/OTP ekranı açılıp kod girildikten SONRA "ödeme reddedildi" çıkıyorsa → bu gerçek bir banka/kart reddi, kod sorunu değil — `procreturncode` ve `mderrormessage`/`errmsg` alanlarını logla, teşhis için kullan
- Garanti resmi test kartı: `4282209004348015` (TEST modunda "sürtünmesiz" doğrular, SMS ekranı çıkmayabilir — bu normal)

### Güvenlik
- Kart alanları (numara/CVV/SKT) backend'e ASLA post edilmemeli, sadece tarayıcı → Garanti arasında kalmalı
- `/api/payments/result` endpoint'i public olabilir (Garanti auth header göndermiyor) ama hash doğrulaması ZORUNLU — bu adım atlanırsa herkes sahte "ödendi" isteği gönderebilir
- Tutar her zaman backend'deki kayıttan okunur, istemciden gelen tutar asla kullanılmaz

---

*Bu prompt, Güliz VIP Transfer (gulizvip.com.tr) projesinde 13 Ağustos 2026'da Garanti BBVA Sanal POS entegrasyonunun canlıya alınması sürecinde edinilen deneyimden özetlenmiştir.*
