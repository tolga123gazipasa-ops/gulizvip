# Güliz VIP — Proje Durumu (Kaldığımız Yer)

Son güncelleme: 2026-08-17 (GTM eklendi, Railway build hatası araştırılıyor — ÇÖZÜLMEDİ ⚠️)

## AÇIK SORUN — Railway deploy build hatası (17 Ağustos)
17 Ağustos'ta Google Tag Manager kodu eklendi (`GTM-58F7GC87`, commit `ff75e58`) ve
push edildi. Deploy denemesi **"Build image" adımında başarısız oldu**
("Failed to build an image. Please check the build logs for more details.") —
gerçek hata metni hâlâ görülmedi, Tolga build log'un tamamını paylaşmadı
(sadece "scheduling build on Metal builder..." satırlarını gönderdi, bunlar
sadece hangi sunucuya atandığını gösteriyor, hatayı içermiyor).

**Yapılanlar:**
- Railway MCP connector'ı bağlamayı denedik (loglara doğrudan erişip teşhis
  koymak için) — Railway'in OAuth giriş sistemi hata verdi
  ("Couldn't register with Railway's sign-in service", ref: `ofid_c2653ca9697a1dfa`),
  bağlantı kurulamadı.
- Şüphelenilen sebep: bu oturumda (16 Ağustos, AYT scraping fix'i sırasında)
  eklenen `curl_cffi` paketi — derleme gerektiren (native) bir kütüphane,
  Railway'in build ortamında kurulumu başarısız olmuş olabilir. Önce
  `requirements.txt`'ten geçici olarak kaldırıldı (commit `325575b`) — kod
  zaten `_CURL_CFFI_AVAILABLE` kontrolüyle korumalı, bu paket olmasa bile
  site çalışır, sadece AYT uçuş verisi eski urllib yöntemine geri düşer.
- Deploy tekrar denenirken bu sefer Railway/GitHub tarafında **ayrı, alakasız
  bir arıza** çıktı: "GitHub is experiencing elevated error rates"
  (bkz. status.railway.com/incident/W4MIGEVT) — Railway'in GitHub'dan kod
  çekememesiyle ilgili, bizim kodumuzla alakasız, GitHub'ın kendi genel
  altyapı sorunu.
- Tolga bunu görünce "sorun GitHub'daymış, curl_cffi'de sorun yoktu" diyerek
  curl_cffi'nin geri eklenmesini istedi — **geri eklendi** (commit `2030436`),
  `requirements.txt` tekrar `curl_cffi>=0.16` içeriyor.
- **ÖNEMLİ NOT:** GitHub arızası ile ilk "Build image" hatası muhtemelen
  FARKLI şeyler — GitHub kesintisi sadece en son deploy denemesinde (kodu
  çekerken) yaşandı, ama ilk başarısız deployment "Build image" aşamasında
  (kod çekildikten SONRAKI bir adımda) patlamıştı. Yani curl_cffi'nin gerçekten
  suçlu olup olmadığı hâlâ NETLEŞMEDİ — sadece varsayımla geri eklendi.

**Sıradaki adım:** Tolga deploy'u tekrar deneyecek. Başarılı olursa mesele
kalmaz. Başarısız olursa **build log'un TAMAMININ** (özellikle "Build Logs"
sekmesindeki kırmızı/error satırlarının) paylaşılması şart — o olmadan kesin
teşhis konulamıyor, tahmin yürütülüyor. Alternatif: Railway MCP connector'ı
tekrar bağlanmayı denemek (bir süre sonra OAuth sorunu geçmiş olabilir),
bağlanırsa loglara doğrudan erişilip net teşhis konabilir.

## GÜNCEL — Kredi kartı ödemesi CANLIDA ÇALIŞIYOR, döviz sorusu Garanti'ye soruldu (16 Ağustos)

**✅ Garanti BBVA Sanal POS PROD'da gerçek parayla test edildi ve BAŞARILI oldu**
(14 Ağustos gecesi, rezervasyon #80). SMS/OTP onayı + banka onayı + hash doğrulama
uçtan uca çalıştı, rezervasyon "ödendi" işaretlendi. Yol boyunca çıkan `garantiOrderId`
DB'ye kaydedilmeme bug'ı düzeltildi (commit `b5c9170`) — asıl kilit buydu.

**16 Ağustos'ta yapılan ek işler (commit'lendi, deploy edildi):**
1. Google Ads telefon arama dönüşüm takibi eklendi (`AW-18372593815/MuZuCM6Gr-EcEJeR3rhE`)
2. Google Analytics 4 (GA4) kuruldu (`G-ZV9Q8PX2QL`)
3. Ziyaretçi trafik kaynağı takibi: `gclid`/`utm_*`/`fbclid` yakalanıyor, Telegram'daki
   "Yönlendiren" alanı artık gerçek kaynağı gösteriyor (Google Ads / organik / kampanya)
   — önceden `document.referrer` genelde boş geliyordu, reklam tıklamalarında hep boş
   çıkıyordu, bu düzeltildi
4. Alış Noktası alanları (hem Havalimanı Transferi hem Tahsis formu) artık varsayılan
   olarak "Gazipaşa Havalimanı" ile başlıyor, kullanıcı değiştirebiliyor
5. **Gerçek bug bulundu ve düzeltildi:** Google Maps API anahtarı "HTTP referrer"
   kısıtlamalı olduğu için sunucu-taraflı çağrılar (`/api/maps/distance`,
   `/api/maps/geocode`) Google tarafından reddediliyordu — admin panelindeki
   "Google ile Hesapla" (rota fiyat önerisi) özelliği bu yüzden çalışmıyordu. Ayrı,
   kısıtlamasız bir sunucu anahtarı (`GOOGLE_MAPS_SERVER_API_KEY`) oluşturulup env
   var olarak eklendi, kod güncellendi
6. Hizmet bölgesi dışındaki (örn. Eskişehir) alış/varış noktaları için artık mesafe/
   fiyat hiç hesaplanmıyor/gösterilmiyor (önceden kafa karıştırıcı şekilde yine de bir
   fiyat çıkıyordu)
7. **AYT (Antalya) uçuş verisi çekilememe sorunu teşhis edildi:** Railway loglarında
   kesin hata bulundu — `Connection reset by peer` (muhtemelen sitenin bot koruması).
   Sayfa yapısı bozulmamıştı, sorun ağ/erişim seviyesindeydi. Daha gerçekçi tarayıcı
   header'ları + otomatik yeniden deneme eklendi; başarısız olursa artık Telegram'a da
   uyarı düşüyor (önceden sessizce günlerce fark edilmeden kalmıştı)
8. Admin panele "Uçuşları Şimdi Güncelle" butonu eklendi (02:00/13:00'i beklemeden
   veya sunucuyu yeniden başlatmadan manuel tetikleme) — `POST /api/admin/flights/refresh`
9. Uçuş güncellemelerinde Telegram'a değişiklik özeti gidiyor (yeni uçuşlar + durum
   değişiklikleri) — sadece bilgilendirme, canlı tablo onay beklemeden anında güncelleniyor
10. **TL fiyatların yanında bilgilendirme amaçlı $ / € karşılığı gösteriliyor** (TCMB
    günlük kur, günde 2 kez otomatik güncelleniyor). Ödeme akışı TAMAMEN TL olarak
    devam ediyor, bu sadece görsel bilgilendirme.
11. **Sunucu saat dilimi düzeltildi:** Railway varsayılan olarak UTC çalışıyordu, `TZ`
    hiç set edilmemişti — yani "02:00/13:00" aslında Türkiye saatiyle 05:00/16:00'da
    tetikleniyordu. `TZ=Europe/Istanbul` + `time.tzset()` eklendi, artık gerçekten
    02:00/13:00'te çalışıyor (commit `5e553da`).
12. **AYT sorunu ÇÖZÜLDÜ — curl_cffi:** Header/retry düzeltmesi (madde 7) tek başına
    yetmemişti, "yine çekemedi" raporlanmıştı. `curl_cffi` kütüphanesi eklendi
    (`requirements.txt`) — Chrome'un TLS/JA3 parmak izini taklit ederek sitenin bot
    korumasını aşıyor. Yeni `_http_get_ayt()` fonksiyonu önce curl_cffi ile dener,
    kütüphane yoksa veya başarısız olursa eski urllib yöntemine (`_http_get`) geri
    düşer — GZP hiç etkilenmedi (kendi JSON API'sini kullanıyor). Deploy sonrası
    Tolga onayladı: **artık çalışıyor** (commit `8baeff0`). Sandbox'ta doğrudan test
    edilememişti (sandbox'ın kendi ağ kısıtlaması antalya-airport.aero'yu
    engelliyordu), gerçek doğrulama Railway'de yapıldı.
13. **YENİ ÖZELLİK — "Konumumu Kullan" (GPS ile alış noktası):** Hem Havalimanı
    Transferi hem Tahsis formundaki alış noktası kutusunun altına kırmızı bir buton
    eklendi. Müşteri tıklayınca tarayıcı GPS izni ister; onaylarsa gerçek konum
    okunur adrese çevrilip kutuya yazılır, ham enlem/boylam da rezervasyona ekleniyor
    (şoför tam pin'e gidebilsin diye). Aynı anda `gulizTracker` sistemi (zaten bilinen
    IP + şehir/ülke ile birlikte) GPS pin'ini Telegram'a "Haritada Gör" linkiyle
    kritik olay olarak bildiriyor — yani butona her basıldığında sana anlık bildirim
    gidiyor.
    - **Hizmet bölgesi dışı davranışı (Ankara/İstanbul/yurt dışı vb.):** Kutu kırmızı
      hataya düşmüyor, otomatik "Gazipaşa Havalimanı"na dönüyor, 8 saniyeliğine mavi
      bilgilendirici bir not gösteriyor ("ileri tarihli rezervasyon yapıyorsanız sorun
      yok..."). Müşteri hiç engellenmiyor. Telegram bildirimi yine gidiyor, notunda
      "(hizmet bölgesi dışı, form varsayılana döndürüldü)" yazıyor — yani kutuda ne
      görünürse görünsün, müşterinin gerçekte nerede olduğunu her zaman biliyoruz.
    - **İzin reddedilirse / tarayıcı desteklemiyorsa / zaman aşımı:** Sadece uygun bir
      uyarı mesajı çıkıyor, Telegram'a hiçbir şey gitmiyor (konum hiç alınamadığı için).
    - Tüm buton/tooltip/uyarı metinleri TR/EN/RU olarak çevrildi (I18N sistemine
      bağlandı) — sana giden Telegram bildirimi ise kasıtlı olarak her zaman Türkçe.
14. **Tahsis (Şoförlü VIP/Günlük) formuna harita eklendi:** Daha önce sadece
    Havalimanı Transferi formunda harita vardı — kod tahsis formunu da güncellemeye
    çalışıyordu ama o formda haritanın gösterileceği bir kutu hiç yoktu, yani hiçbir
    şey görünmüyordu. Artık tahsis formunun kendi harita kutusu var; alış noktası
    seçilince (veya "Konumumu Kullan" ile) tek bir pin gösteriyor (varış noktası
    toplanmadığı için rota çizilmiyor, sadece alış pin'i).
15. **Logo tıklaması artık formu gerçekten sıfırlıyor:** Önceden logoya basınca (ana
    sayfadayken) sadece sayfa en üste kayıyordu, form verisine hiç dokunulmuyordu —
    "başa dönme" diye bir mekanizma yoktu. Şimdi logo tıklaması (ve 404/403
    sayfalarındaki "Ana Sayfaya Dön" linki) alış/varış noktalarını, tarih/saati,
    kişisel bilgileri, fiyat tahminini ve haritayı ilk haline döndürüyor, Havalimanı
    Transferi sekmesine geri geçiyor. Canlı destek/sohbet oturumuna (gulizTracker,
    mesaj geçmişi) kasıtlı olarak dokunulmuyor.

16. **Google Search Console uyarısı incelendi:** Tolga'ya "sayfa içeriklerinizin dizine
    eklenmesini engelleyen yeni nedenler" e-postası geldi. İncelenip URL örnekleri
    tek tek kontrol edildi:
    - "Robots.txt tarafından engellendi" (5 örnek) → hepsi `/api/...` endpoint'leri
      (paypas/create-session, page/, fleet, availability). Tamamen normal/istenen —
      bunlar zaten indekslenmemeli, aksiyon gerekmiyor.
    - "Doğru standart etikete sahip alternatif sayfa" (3 örnek) → `www.gulizvip.com.tr/en/`
      ve `/ru/` (www'lı versiyon), ayrıca `/?odeme=basarili|iptal|dogrulanamadi` gibi
      garip bir URL. İkisi de teşhis edildi:
      1. www'lı adres de siteyi aynı içerikle sunuyordu, canonical www'sız adresi
         gösteriyordu ama gerçek bir yönlendirme yoktu — Google doğru karar veriyordu
         ama temiz değildi.
      2. `/?odeme=basarili|iptal|dogrulanamadi` gerçek bir link değildi — index.html
         içindeki bir kod yorumunda bu tam metin URL gibi yazılmıştı, Google bunu
         literal bir adres sanıp taramıştı (zararsızdı, indekslenmemişti zaten).
    - **Düzeltmeler:** `server.py`'ye www → www'sız VE http → https 301 yönlendirmesi
      eklendi (artık `http://www.gulizvip.com.tr` dahil her kombinasyon otomatik
      `https://gulizvip.com.tr`'ye düşüyor — Tolga'nın notu: "zaten o şekildeydi"
      yani muhtemelen Cloudflare tarafında zaten bir düzey koruma vardı, ama kod
      seviyesinde garanti altına alındı, zararı yok). Yanıltıcı kod yorumu da
      URL gibi görünmeyecek şekilde yeniden yazıldı.
    - **Kontrol edilmemiş kalan tek şey:** Search Console tablosunda "Yönlendirmeli
      sayfa — Doğrulama: Başarısız oldu" (2 sayfa) satırı vardı, bu diğerlerinden
      farklı olarak gerçek bir sorun olabilir — hangi 2 URL olduğu henüz görülmedi,
      ileride Search Console'dan bakılıp incelenmesi gerekiyor.

**AÇIK KONU — Dövizli (USD/EUR) gerçek ödeme alma:**
Tolga, gerçekten USD/EUR ile kredi kartı ödemesi almak istiyor (sadece bilgilendirme
değil, gerçek tahsilat). Kod tarafı buna zaten hazır — `_garanti_prepare_form` hangi
para biriminde göndereceğini parametre olarak alıyor, `GARANTI_CURRENCY_CODES` içinde
USD/EUR tanımlı. **Ama asıl soru bankada:** Merchant ID 3724930 / Terminal 10470591
hesabı döviz ile 3D'li Peşin satış yapmaya yetkili mi, yoksa ayrı bir başvuru mu
gerekiyor? Tolga bu soruyu 16 Ağustos'ta Garanti'ye (`eticaretdestek@garantibbva.com.tr`)
e-posta ile sordu, **cevap bekleniyor**.

**Cevap geldiğinde:**
- Evet, yetkiliyse → ödeme ekranına gerçek TL/USD/EUR seçici eklenir (alt yapı hazır,
  sadece frontend'de bir para birimi toggle'ı + reservation'ın currency alanının doğru
  set edilmesi gerekiyor), TCMB kuru ile TL fiyat USD/EUR'ya çevrilip o tutar/para
  biriminde Garanti'ye gönderilir
- Hayır, yetkili değilse → ek başvuru/sözleşme gerekip gerekmediği netleşince ona göre
  ilerlenir

### Hemen Yapılması Gereken
Yok — 16 Ağustos'ta biriken tüm commit'ler (Google Ads/GA4/trafik takibi/Gazipaşa
varsayılan/Google Maps server key/hizmet bölgesi fiyat düzeltmesi/AYT scraping fix/
uçuş yenile butonu/uçuş değişiklik özeti/döviz gösterimi/timezone fix/Konumumu Kullan
GPS özelliği/tahsis harita/logo sıfırlama/www-http yönlendirmesi) Tolga tarafından
push edildi ve Railway'e deploy edildi ✅. Branch origin ile senkron.

Tek açık madde: Search Console'daki "Yönlendirmeli sayfa — Doğrulama: Başarısız
oldu" (2 sayfa) satırının hangi URL'ler olduğu henüz görülmedi — Tolga fırsat
bulunca Search Console'dan bakıp paylaşırsa incelenecek.

## ESKİ — Garanti BBVA PROD env var'ları Railway'e eklendi (13 Ağustos, gece)
Tolga, Railway → Variables'a 7 Garanti env var'ını ekledi:
`GARANTI_MODE=PROD`, `GARANTI_MERCHANT_ID=3724930`, `GARANTI_TERMINAL_ID=10470591`,
`GARANTI_PROV_USER_ID=PROVAUT`, `GARANTI_TERMINAL_USER_ID`, `GARANTI_PROVISION_PASSWORD`
(PROVAUT şifresi), `GARANTI_STORE_KEY` (3D Secure Key — 24 bayt/48 hex karakter,
ilk denemede "24 byte Hex data girilmelidir" hatası aldı çünkü PDF'teki "24 karakter"
ifadesi yanıltıcıydı, gerçekte 48 hex karakter/24 bayt gerekiyormuş — düzeltilmiş
değerle sorun çözüldü). PROVRFN tanımlanmadı (opsiyonel, iade işlemleri API üzerinden
otomatik yapılmıyor, portaldan manuel yapılıyor — sorun değil).

**Canlıya almak için kalanlar:**
1. Railway'in değişkenleri alıp otomatik redeploy ettiğini doğrula (Deploy Logs'ta
   yeni bir deploy görünmeli, "GARANTI_MODE" TEST değil PROD olarak yüklenmiş olmalı)
2. **Gerçek/küçük tutarlı canlı test işlemi** — siteden gerçek bir kredi kartıyla
   küçük bir rezervasyon ödemesi dene, `mdstatus`/`procreturncode` başarılı dönmeli,
   admin panelde rezervasyon "ödendi" (paid) görünmeli, banka hesabına gerçek para
   düşmeli (birkaç gün içinde hesaba yansır)
3. `GARANTI_TERMINAL_USER_ID` için panelde ayrı bir alan bulunup bulunmadığı netleşmedi
   — bulunamadıysa varsayılan `GARANTI` ile devam edilebilir, sorun çıkarsa
   `ETicaretDestek@garantibbva.com.tr`'e sorulabilir
4. `git push origin main` — sandboxtan push edilemiyor, Tolga'nın kendi bilgisayarından
   yapması gerekiyor (2 commit bekliyor: `8590c24`, `ad19084`)

**GERÇEK BUG BULUNDU VE DÜZELTİLDİ (13 Ağustos, gece — commit `b5c9170`):**
İlk canlı test denemesinde Tolga "Dönüş için işyeri URL bulunamıyor... PARes mesajı" hatası
aldı. Railway loglarını inceleyince ayrı bir gerçek bug ortaya çıktı: `garantiOrderId`
(rezervasyonu Garanti'nin geri dönüşüyle eşleştiren kimlik) sadece JSON yedeğine
yazılıyordu, PostgreSQL'e HİÇ kaydedilmiyordu. Tam o test sırasında Railway env
var'ları kaydedilince otomatik bir redeploy tetiklendi — yeni container DB'den taze
rezervasyon listesini yükledi ama garanti_order_id sütunu DB'de olmadığı için bu alan
kayboldu. Garanti işlemi tamamlayıp `/api/payments/garanti/result`'a geri post
ettiğinde ("orderid=GULIZ76-16FDA3DD") sunucu eşleşen rezervasyon bulamadı →
`outcome=dogrulanamadi`. Düzeltildi: `db.py`'ye `garanti_order_id` kolonu eklendi,
`update_reservation_in_db`/`load_reservations_from_db` bu alanı artık okuyup yazıyor.

Not: Bu bug, kullanıcının gördüğü "İşyeri URL bulunamıyor" hata METNİNİ tam olarak
açıklamıyor olabilir (o mesaj muhtemelen Garanti'nin kendi sayfasından geliyor) — ama
loglardaki somut eşleşme hatasını kesin çözüyor. Push + redeploy sonrası tekrar test
edilmeli; aynı "İşyeri URL bulunamıyor" hatası YİNE çıkarsa bu artık kesin bankanın
kendi terminal/routing tarafında bir sorun demektir, Garanti'ye e-posta ile bildirilmeli.

Kod tarafında başka yapılacak bir şey yok — sistem PROD env var'ları okumaya hazır,
yukarıdaki doğrulama/test adımları ve bu yeni düzeltmenin push edilmesi kaldı.

## ESKİ — Garanti BBVA PROD kurulumu aktif ilerliyor (13 Ağustos, akşam)
Tolga, `eticaretdestek@garantibbva.com.tr` ile yazışıyordu (Müşteri Kodu: 61308591).
13 Ağustos'ta "Başvurunuz ilerletilmiştir" maili geldi, ardından aynı gün akşam
aktivasyon maili de geldi (`sanalpos@garantibbva.com.tr`) — Tolga `pos.garantibbva.com.tr`
admin portalına giriş yaptı ve "Kullanıcı Aktivasyonu için Şifre Tanımlama" ekranına
ulaştı (ekran görüntüsüyle doğrulandı).

**GERÇEK PROD DEĞERLERİ ELE GEÇTİ (ekran görüntüsünden okundu):**
- `GARANTI_MERCHANT_ID` = **3724930** (İş Yeri: GÜLİZ LOJİSTİK MİMARLIK İNŞAAT TURİZM Tİ)
- `GARANTI_TERMINAL_ID` = **10470591**

**Sırada:** Tolga PROVAUT + PROVOOS kullanıcı şifrelerini admin portalında kendisi
belirleyecek (asistan şifre alanına giremez — güvenlik kuralı). PROVAUT şifresi
= `GARANTI_PROVISION_PASSWORD` olacak. PROVRFN opsiyonel, atlandı. Sonraki adım
PDF'in 3.2 bölümü: "3D Secure Key Değiştirme" — 24 haneli HEX değer üretilecek,
bu da `GARANTI_STORE_KEY` olacak.

Hâlâ eksik olan 7 env var'dan kalan: `GARANTI_PROVISION_PASSWORD`, `GARANTI_STORE_KEY`
(PROVAUT/OOS şifreleri + HEX anahtar belirlenince tamamlanacak), `GARANTI_PROV_USER_ID`
(muhtemelen `PROVAUT` — kod zaten bunu varsayılan alıyor), `GARANTI_TERMINAL_USER_ID`
(panelde ayrıca bir "kullanıcı adı" alanı olabilir, netleşince teyit edilecek).
Bu bilgiler tamamlanınca Railway'e 7 env var eklenip `GARANTI_MODE=PROD` yapılacak.

### Bu oturumda tamamlanan işler (henüz push edilmedi — bkz. en alt)
1. Kredi kartı ödemesinde onay maili/Telegram artık sadece gerçek ödeme onayından
   sonra gidiyor (önceden rezervasyon oluşur oluşmaz, ödeme tamamlanmadan gidiyordu)
2. Mesafeli Satış Sözleşmesi'ne satıcı bilgileri eklendi: unvan, merkez adres,
   Gazipaşa Havalimanı ofis adresi, vergi dairesi (Gazipaşa Mal Müdürlüğü),
   VKN (4200721970), telefon, e-posta — Garanti BBVA'nın talebi üzerine
3. **KRİTİK KÖK NEDEN BUG DÜZELTİLDİ:** `load_page_content()` sunucu başlangıcında
   hiç çağrılmıyordu — page_content.json'daki HİÇBİR değişiklik (ne git'ten ne admin
   panelinden) kalıcı olmuyordu, her redeploy'da kod içine gömülü orijinal varsayılan
   metne dönüyordu. Artık düzeltildi.
4. **Mimari değişiklik:** `/api/page/<slug>` artık önce VERİTABANINI okuyor (JSON
   dosyası sadece ilk kurulum/yedek). Artık admin panelinden yapılan sayfa
   düzenlemeleri kalıcı — hiçbir redeploy onları silmiyor.
5. Admin panelinden tek sayfa düzenlenince diğer sayfaların footer/listeden
   kaybolduğu bug düzeltildi (`_get_merged_pages()` — DB+JSON birleştirme)
6. /sayfa/<slug> sayfalarında dil değiştirince anasayfaya atılma sorunu düzeltildi
7. "Son Güncelleme" tarihinin iki kez görünmesi düzeltildi
8. **5 içerik sayfası (Hakkımızda, Gizlilik, Mesafeli Satış, Teslimat, İade
   Şartları) gerçekten İngilizce ve Rusçaya çevrildi** — `/en/sayfa/<slug>`,
   `/ru/sayfa/<slug>` route'ları eklendi. NOT: Bu çeviriler AI çevirisidir, admin
   panelinden düzenlenemez, koda gömülüdür (`PAGE_TRANSLATIONS` — server.py).
   Türkçe içerik admin panelinden değişirse çeviriler OTOMATİK GÜNCELLENMEZ —
   Tolga admin panelinden bu 5 sayfadan birini değiştirirse bana haber vermesi
   gerekiyor ki çeviriyi elle senkronize edip yeniden deploy edeyim.
9. İade Şartları sayfasındaki eski "iyzico altyapısı" referansı "Garanti BBVA
   Sanal POS altyapısı" olarak düzeltildi (hem TR hem EN/RU)
10. Kapsamlı SEO çalışması: her /sayfa/<slug> artık kendi canonical/title/meta
    description/hreflang/OG etiketlerine sahip (önceden hepsi anasayfanınkini
    gösteriyordu — duplicate content riski). Olmayan sayfalar artık gerçek 404
    dönüyor. sitemap.xml güncellendi (DB'den besleniyor, 3 dil + hreflang
    alternate linkleri var, 28 URL/72 hreflang). robots.txt'ye /odeme/ disallow
    eklendi. Sahte aggregateRating (4.9/127 yer tutucu) kaldırıldı — Tolga'nın
    Google İşletme Profili'nde gerçek puanı var (5,0 - 8 yorum, "gazipaşa alanya
    transfer" işletmesi) ama structured data'ya hiç eklememeyi tercih etti.

### Hemen Yapılması Gereken
```
cd C:\proje\gulizvip
git push origin main
```
Push + Railway redeploy sonrası yukarıdaki TÜM değişiklikler (13 commit) canlıya çıkar.

## GÜNCEL (12 Ağustos): PayPas iptal edildi, Garanti BBVA Sanal POS'a geçildi

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
