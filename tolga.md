# Güliz VIP — Proje Durumu (Kaldığımız Yer)

Son güncelleme: 2026-08-19 gece geç — **CANLI SİTEDE MÜŞTERİLER REZERVASYON
YAPAMIYORDU (502 Bad Gateway), GERÇEK KÖK NEDEN BULUNDU VE DÜZELTİLDİ** (aşağıdaki
ilgili bölüme bak — Tolga Railway loglarını paylaştı, kesin teşhis kondu). Ayrıca
502 düzeltmesinden SONRA iki form-sıfırlama bug'ı + bir GPS/fiyat UX eksiği daha
bulunup düzeltildi (bkz. aşağıdaki bölümler). **Tüm bu commit'ler hâlâ push/deploy
bekliyor — ACİLEN deploy edilmesi lazım, şu an canlıda müşteriler rezervasyon
YAPAMIYOR.**

## ÇÖZÜLDÜ (henüz deploy edilmedi) — /en veya /ru sayfasında menüye tıklayınca Türkçe'ye düşüyordu

**Bağlam:** Tolga fark etti: kullanıcı /en (İngilizce) sayfasındayken üst
menüden "Filomuz"a tıklayınca sayfa aniden Türkçe'ye dönüyordu — "kullanıcının
dil tercihi unutuluyor" dedi.

**Sebep:** Üst menü ve footer'daki TÜM bağlantılar (Hizmetler, Filomuz,
Bölgeler, Canlı Uçuşlar, İletişim, S.S.S — 11 link) HTML'de sabit `/#filo`
gibi Türkçe köke işaret ediyordu, hangi dildeki sayfada olunursa olsun. `/en/`
sayfasındayken bu linke tıklamak `/` ile FARKLI bir adrese (`/en/` değil `/`)
gerçek bir sayfa yüklemesi yaptırıyordu — ve "/" sunucu tarafında her zaman
Türkçe açılıyor (bu, önceki bir oturumda BİLİNÇLİ olarak öyle yapılmıştı —
dilin localStorage'da yanlışlıkla "yapışmasını" önlemek için, bkz. koddaki
`initLanguage()` yorum notu). Yani iki ayrı doğru karar bir araya gelince
(dil sadece URL'den okunsun + linkler sabit Türkçe köke gitsin) beklenmedik
bir yan etki doğurmuş: dil, tam da menüye tıklayınca kayboluyormuş.
Düzeltildi: sayfa İngilizce/Rusça ise, tüm bu `/#...` linkleri sayfa
yüklenirken otomatik olarak `/en/#...` veya `/ru/#...`'ya çevriliyor —
ziyaretçi hangi dildeyse menüde gezinirken de o dilde kalıyor. (commit `35069a8`)

## ÇÖZÜLDÜ (henüz deploy edilmedi) — "Konumumu Kullan" (GPS) sonrası fiyat hiç çıkmıyordu

**Bağlam:** Tolga, Telegram'daki "Görünmez Ajan" ziyaretçi bildirimlerinde
müşterilerin "Konumumu Kullan (GPS)" özelliğini kullandığını ama sonrasında
fiyat/rezervasyon akışının ilerlemediğini fark etti — "giriyorlar konumunu
çekiyorlar böyle kalıyorlar fiyat hesaplamıyorlar" dedi.

**Sebep (bug değil, eksik yönlendirme):** GPS düğmesi sadece ALIŞ noktasını
dolduruyor (müşterinin gerçek adresi — genelde ev/otel, havalimanına GİDİŞ
yönü demek). Fiyat hesaplaması için hem alış HEM varış gerekiyor; varış hâlâ
boşsa `calculateTransferDistance()` sessizce hiçbir şey göstermeden çıkıyordu
— ne hata, ne yönlendirme. Müşteri konumunu verdikten sonra "şimdi nereye
gideceğinizi de yazmanız lazım" adımını fark edemiyor, sistem donmuş/tepkisiz
sanıyordu. Düzeltildi: GPS ile alış dolar dolmaz, varış hâlâ boşsa kutu
otomatik odaklanıyor VE altında Gazipaşa/Alanya/Antalya Havalimanı hızlı öneri
çipleri hemen beliriyor — müşteri tek dokunuşla varışı seçip anında fiyatı
görebiliyor. (commit `5084c5b`)

## ÇÖZÜLDÜ (henüz deploy edilmedi) — Admin panelde "Yeni Rezervasyon Ekle" kapanınca sıfırlanmıyordu

**Bağlam:** Tolga admin panelinden bir müşteri için rezervasyon ekleyip
kaydetti, sorun yoktu — ama sonra tekrar "Yeni Rezervasyon Ekle" ekranını
açınca bir ÖNCEKİ müşterinin bilgilerinin (isim, telefon, alış/varış, tarih)
hâlâ formda dolu olduğunu fark etti.

**Sebep:** `toggleNewReservationForm()` fonksiyonu form kapanırken sadece
harita/koordinat state'ini sıfırlıyordu (`adminSelectedPickupLat` vb.) — metin
input'larına (`admin-customer-name`, `admin-customer-phone`,
`admin-pickup-input`, `admin-dest-input`, `admin-service-type`,
`admin-datetime`) hiç dokunmuyordu. Rezervasyon kaydedilince form otomatik
kapanıyor (`adminSaveReservation()` içinde `toggleNewReservationForm()`
çağrılıyor) ama alanlar temizlenmediği için bir dahaki açılışta eski veriler
duruyordu — dikkatsizce "Kaydet"e basılırsa aynı bilgilerle yanlışlıkla ikinci
bir rezervasyon oluşabilirdi. Düzeltildi: form kapanırken artık tüm alanlar
(isim, telefon, alış, varış, hizmet tipi, tarih-saat, mesafe/süre/fiyat
gösterimi) sıfırlanıyor. (commit `13eaf8c`)

## ÇÖZÜLDÜ (henüz deploy edilmedi) — Nakit/havale ile rezervasyon tamamlanınca form sıfırlanmıyordu

**Bağlam:** Tolga müşteri tarafında rezervasyonu "Araçta Nakit Öde" ile
tamamladı, "Talebiniz Alındı!" popup'ı çıktı, kapattı — ama altta hâlâ
doldurulmuş 3. adım (isim/telefon/ödeme seçimi) duruyordu, sanki hiçbir şey
sıfırlanmamış gibi. Kredi kartıyla denendiğinde sorun yoktu çünkü o zaten
tamamen ayrı bir ödeme sayfasına (`/odeme/garanti/<id>`) yönlendiriyor.

**Sebep:** `closeModal()` fonksiyonu sadece popup'ı gizliyordu
(`classList.remove('open')`), formu sıfırlayan hiçbir kod çağırmıyordu.
Sitede zaten hazır bir `resetToHomeState()` fonksiyonu vardı (logo tıklayınca
1. adıma dönen) — `closeModal()`'ın artık onu da çağırmasını sağladım, böylece
nakit/havale de kredi kartı gibi temiz bir başlangıca dönüyor, kafa
karışıklığı ve yanlışlıkla ikinci gönderim riski ortadan kalkıyor.
(commit `a78db40`)

## ÇÖZÜLDÜ (henüz deploy edilmedi) — Rezervasyon tamamlanamıyordu: `UnboundLocalError` → 502 Bad Gateway

**Bağlam:** Tolga hem admin panelinden hem normal müşteri olarak rezervasyon
denedi, ikisinde de hata aldığını bildirdi. Canlı siteye (gulizvip.com.tr)
gerçek tarayıcıyla girip uçtan uca test ettim, `POST /api/reservations` her
denemede (6 farklı denemede, UI + doğrudan `fetch()`) tutarlı şekilde
`502 Bad Gateway` (Cloudflare'in kendi hata sayfası — origin'den hiç yanıt
gelmiyor) verdiğini doğruladım. Önce "DB bağlantısı zaman aşımına uğruyor
olabilir" diye şüphelenip `db.py`'ye `connect_timeout=5` ekledim (makul bir
sağlamlaştırma ama asıl sebep değilmiş) — **sonra Tolga Railway'in Deploy
Logs'undan gerçek Python traceback'ini paylaştı, kesin kök neden ortaya çıktı:**

```
File "/app/server.py", line 3861, in do_POST
    phone_digits = re.sub(r"\D", "", raw_phone)
UnboundLocalError: cannot access local variable 're' where it is not associated with a value
```

**Gerçek sebep:** `do_POST` fonksiyonu TÜM POST endpoint'lerini tek dev bir
fonksiyon içinde `if path == ...` zinciriyle yönetiyor. Bu fonksiyonun çok daha
aşağısında, `/telegram-webhook` dalının içinde, gereksiz bir `import re` satırı
vardı (dosyanın en üstünde zaten `import re` var, satır 10). Python bir
fonksiyonun HERHANGİ bir yerinde bir isme atama/import yapılırsa o ismi TÜM
fonksiyon gövdesi için local sayar — kod akışında daha ÖNCE gelen kullanımlar
için bile. Sonuç: `/api/reservations` dalındaki (çok daha yukarıdaki) `re.sub()`
çağrısı, dosyanın en altındaki alakasız bir webhook kodundaki gereksiz import
yüzünden HER SEFERİNDE çöküyordu. Bu, yanıt hiç gönderilmeden bağlantının
düşmesine yol açıyordu — Cloudflare origin'den cevap alamayınca 502 döndürüyordu.
**Müşteri tarafında sonuç: "Sunucuya bağlanılamadı" hatası, rezervasyon hiç
kaydedilmiyordu.** Muhtemelen bu bug uzun süredir oradaydı (telefon validasyonu
kodu `re.sub` kullanmaya başladığından beri) — telefon validasyonu eklenene kadar
fark edilmemiş olabilir.

**Düzeltme (3 commit, sırayla):**
1. `44a46cf` — `db.py`: `psycopg2.connect()`'e `connect_timeout=5` eklendi (asıl
   sebep değilmiş ama makul bir sağlamlaştırma, DB gerçekten erişilemez olursa
   isteğin süresiz asılı kalmasını önlüyor, JSON yedeğe hızlıca düşüyor).
2. Aynı commit'te: `/api/reservations`'ta sadece `json.JSONDecodeError`
   yakalanıyordu, artık genel `except Exception` de var — gelecekte benzer bir
   hata çıkarsa yine temiz bir JSON hata dönecek, bağlantı asla sessizce
   asılı kalmayacak.
3. `cb17a8f` — **asıl kök neden**: `/telegram-webhook` içindeki gereksiz
   `import re` satırı silindi.

**Veri kaybı riski yok:** Test denemelerinin hepsi 502 ile başarısız oldu, sahte
bir rezervasyon kaydedilmedi. Ayrıca DB yazımı başarısız olursa rezervasyon
`reservations.json`'a düşüyor + admin paneline "DB'ye yazılamadı" uyarısı +
Telegram bildirimi zaten DB durumundan bağımsız gönderiliyor — yani "başarılı"
görünüp hiçbir yere kaydedilmeyen bir senaryo yok.

**ÇOK ÖNEMLİ: bu düzeltme henüz canlıya deploy edilmedi.** Push edip deploy
eder etmez canlıda tekrar test edip doğrulayacağım.

## GÜNCEL (19 Ağustos gece) — Canlı sitede "hızlı rezervasyon" testi, 3 gerçek bug bulundu

**Bağlam:** Tolga "bir kullanıcı gibi siteye gir, hızlı rezervasyon almak istiyorsun,
nerede eksiğimiz var" dedi. gulizvip.com.tr'ye canlı olarak (Chrome ile) gerçek bir
müşteri gibi girip önce normal formu, sonra üst menüdeki "Hızlı Rezervasyon" (popüler
rota kartları) akışını uçtan uca denedim. Normal form akışı (bu oturumda yapılan tüm
iyileştirmelerle — 3 çip, özet kutuları, fiyat notu) sorunsuz ve gayet iyi çalışıyor.
Ama "Hızlı Rezervasyon" — sitenin EN HIZLI rezervasyon yolu, tam da Tolga'nın sorduğu
kısım — ciddi şekilde bozuktu:

**1. GERÇEK BUG — Hızlı Rezervasyon'da müşteri hiçbir fiyat/güzergah görmeden
rezervasyon tamamlıyordu.** Üst menüden "Hızlı Rezervasyon"a basıp bir rota kartına
(örn. "Gazipaşa → Mahmutlar 2.500 TL") tıklayınca sistem doğrudan 2. adıma (İletişim
Bilgileri) atlıyor — bu kısmen normal (hız için tasarlanmış) ama iki şey eksikti:
(a) Alış noktası kutusuna "GZP" gibi ham bir kod yazılıyordu (müşteriye "Alış: GZP"
diye anlamsız bir metin gösteriliyordu, "Alanya Gazipaşa Havalimanı" değil).
(b) 2. adımdaki rezervasyon özeti (bu oturumda eklediğimiz güzergah/araç/KM/fiyat
kutusu) HİÇ doldurulmuyordu — çünkü bu akış `nextStep()` fonksiyonunu değil doğrudan
`goToStep()`'i çağırıyordu, özet fonksiyonu hiç tetiklenmiyordu. Sonuç: müşteri rota
kartına tıkladıktan "Rezervasyonu Tamamla"ya basana kadar HİÇBİR fiyat/güzergah teyidi
görmüyordu — 3. adım (Ödeme) ekranında bile sadece ödeme yöntemi seçenekleri vardı,
fiyat yoktu. Gerçek parayla test ettim (rezervasyon #149, nakit seçtim): arka planda
hesaplanan fiyat doğruydu (tam 2.500 TL, reklamdaki fiyatla birebir aynı) — yani
finansal bir hata yoktu, sadece müşteriye hiç GÖSTERİLMİYORDU. Düzeltildi: artık (a)
"GZP"/"AYT" gibi kodlar site genelinde kullanılan tam isimlere çevriliyor, (b) 2. adıma
geçince özet hemen dolduruluyor, fiyat hesaplaması bitince (Google Maps API asenkron
olduğu için) özet otomatik tazeleniyor. (commit `a462a41`)

**2. GERÇEK BUG — telefon numarası validasyonu neredeyse hiç yoktu.** Tek kontrol "en
az 10 karakter" idi, rakam dışı karakter filtrelenmiyordu, üst sınır yoktu. Test
sırasında tarayıcıda (önceki bir test oturumundan localStorage'da kalmış) 40 haneli
anlamsız bir "telefon numarası" otomatik doldu ve sistem bunu SORUNSUZ kabul etti. Bu
ciddi bir sorun çünkü rezervasyon onay ekranında "müşteri temsilcimiz 5 dakika içinde
sizinle iletişime geçecektir" yazıyor — geçersiz numarayla ekip müşteriyi arayamaz,
rezervasyon fiilen kaybolur. Hem formda (frontend) hem sunucuda (backend, API'ye
doğrudan istek atılsa bile) düzeltildi. İlk düzeltmede aralık TR formatına göre (10-13
hane) dardı — Tolga havalimanı transferinde yabancı müşteri oranının yüksek olduğunu
hatırlattı, aralık uluslararası E.164 standardına göre (8-15 hane) genişletildi; `+`
işareti (veya `00` ile başlayan uluslararası arama öneki) zaten sorunsuz kabul ediliyor
çünkü rakam olmayan her karakter sayımdan önce siliniyor. Telefon kutuları zaten
`type="tel"` ile tanımlı, mobilde otomatik telefon tuş takımı açılıyor (bu koddaydı,
yeni eklenmedi). (commit'ler: `15eb802`, `5239c16`)

**3. GERÇEK BUG (admin panel, ödeme onayı) — "Ödemeyi Onayla" butonu hiç
çalışmıyordu + otomatik ödenen kart rezervasyonlarında "Onayla" butonu yanlışlıkla
kilitliydi.** Bu tarama sırasında (canlı test değil, kod taraması) bulundu — ayrı bir
maddede yukarıda zaten var, tekrar burada anmıyorum. (commit `51d06b9`)

**Not — test verisi temizliği gerekiyor:** Yukarıdaki testler sırasında canlı sitede
gerçek bir rezervasyon oluştu: **#149** (Gazipaşa→Mahmutlar, "tolga baba" adına, nakit
ödeme, 2.500₺). Gerçek bir müşteri değil, benim testimdi — admin panelinden silmen
gerekiyor (ben kalıcı veri silemem). Daha önceki test kaydı #112 hâlâ duruyorsa onu da
aynı anda temizleyebilirsin.

## GÜNCEL (19 Ağustos akşam) — Ödeme yöntemlerine "Araçta Nakit Öde" eklendi

**Bağlam:** Tolga ödeme seçeneklerine ne eklenebileceğini sordu, kendisi "araçta
şoföre öde" fikrini önerdi. Konuşuldu: müşterinin gelmeyip aracın boşuna gitmesi
riski havale seçeneğinden farklı değil (ikisinde de ödeme önceden garanti değil,
havalede de admin elle onaylıyor) — bu yüzden ek bir doğrulama mekanizması
eklenmedi, sadece Telegram'da nakit rezervasyonlar ayırt edilebilir yapıldı.

**Havale/EFT ve Kredi Kartı'nın yanına 3. seçenek: "Araçta Nakit Öde".**
(1) Fiyat kutusu tasarımı: sadece başlık + ikon, açıklama metni YOK — birkaç tur
tartışıldı (önce uyarı notu eklendi, sonra "kredi kartı geçmez" bilgilendirmesi
eklendi, Tolga son kararında ikisini de istemedi, sade tutuldu). (2) Seçilince
banka/IBAN kutusu (daha önce hem havale hem karttan farklı davranıyordu, düzeltildi:
artık sadece havale'de gösteriliyor). (3) Sana giden Telegram bildiriminde nakit
seçilen rezervasyonlarda "💵 Ödeme: Araçta Nakit (ön ödeme yok — teyit için
müşteriyi aramanız önerilir)" satırı çıkıyor, havalede "🏦 Ödeme: Havale/EFT"
çıkıyor — böylece hangi rezervasyonun ön ödemesiz olduğunu Telegram'dan direkt
görüyorsun. (4) Admin panelde de "Nakit (Araçta)" olarak düzgün etiketleniyor.
TR/EN/RU üçünde de var. (commit'ler: `3b79788`, `6577857`, `be046ec`)

## GÜNCEL (19 Ağustos akşam) — "Fiyat araç başınadır" notu + Telegram bildirim detayı + 2. adım özeti

**3. 2. adımdaki (Kişisel Bilgiler) rezervasyon özetine araç/yolcu/çocuk satırı
eklendi.** Güzergahın hemen altında artık "1 Adet VIP Araç · 2 Yolcu · 1 Çocuk"
gibi bir satır görünüyor (çocuk 0 ise o kısım hiç yazılmıyor) — hem transfer hem
tahsis formunda, TR/EN/RU. (commit `3ef0fec`)

**Bağlam:** Tolga, kişi sayısı arttıkça fiyatın neden değişmediğini sordu (2 kişi de
9 kişi de aynı fiyat). Açıklandı: fiyat kişi başı değil ARAÇ başına hesaplanıyor
(transfer: KM × birim fiyat, tahsis: süreye göre sabit paket) — bu bilinçli bir
model, büyük gruplar kişi başı çok daha avantajlı çıkıyor (özel araç kişi başı
maliyeti düşürüyor). Kod değiştirilmedi, sadece bunu müşteriye netleştiren bir not
eklendi.

**1. Fiyat kutusunun altına "Fiyat araç başınadır, yolcu sayısına göre değişmez."
notu eklendi** — hem Havalimanı VIP Transfer hem Tahsis formunda, fiyat/tahmini
tutar gösteriminin hemen altında. TR/EN/RU üçünde de çevrildi. (commit `b945fcd`)

**2. Telegram "Fiyat Hesapla" bildirimi netleştirildi.** Müşteri 1. adımdan 2. adıma
geçtiğinde (yani fiyat hesaplanır hesaplanmaz) sana giden Telegram bildirimi artık
tek satıra sıkışmış bilgi yerine ayrı satırlarda gösteriyor: Alış, Varış (veya
Tahsis'te Süre), **Tarih, Saat**, ve doluysa **Uçuş No** — Tolga özellikle tarih/saat
ve uçuş numarasının görünmesini istedi, ödeme adımına gelmeden vazgeçen müşterileri
de artık net görebiliyorsun. (commit `7716d8f`)

### Hemen Yapılması Gereken
- **git push origin main** kendi bilgisayarından — bu oturumdaki tüm commit'ler
  (`b945fcd`'den `5239c16`'ya kadar, 12 commit) push bekliyor.
- Push+deploy sonrası admin panelinden test rezervasyonu **#149**'u sil (bkz. yukarıki
  not — canlı QA testi sırasında oluştu, gerçek müşteri değil).

## GÜNCEL (19 Ağustos) — Booking formu alış/varış alanları + mobil UX turu

**Oturum özeti:** Bugün üç ana başlık üzerinde çalışıldı: (1) alış/varış noktası
alanlarının kullanılabilirliği baştan aşağı iyileştirildi, (2) admin panel ve
site genelinde mobil deneyim iyileştirmeleri yapıldı, (3) küçük ama gerçek
birkaç bug bulunup düzeltildi. Hepsi push edildi, `git log origin/main..HEAD`
boş — branch senkron.

**1. Alış noktasına "temizle" (X) butonu eklendi.** Varsayılan "Gazipaşa
Havalimanı" metnini silmek isteyen müşteri artık kutunun sağındaki çarpıya
basıp tek tıkla temizleyebiliyor. İlk versiyonda CSS bozukluğu vardı (çarpı
ikonu kutunun dışına, sola fırlıyordu) — bulunup düzeltildi.

**2. Canlı destek iyileştirmeleri:** bildirim sesi kapatıldı, sayfa açılır
açılmaz 3 saniye sonra otomatik açılan canlı destek kutusu kaldırıldı — artık
sadece müşteri butona basınca açılıyor.

**3. "Havalimanı Transfer" sekmesi/başlığı → "Havalimanı VIP Transfer" oldu**
(marka vurgusu, "sıradan transferci değiliz" isteğiyle).

**4. Admin panel mobil kart görünümü:** Dashboard'daki "Son Gelen Rezervasyon
Talepleri" ve "Tüm Rezervasyonlar" tabloları artık telefonda yatay kaydırma
yerine tek sütun kart listesi olarak görünüyor (CSS-only, JS'e dokunulmadı).
Diğer tablolar (uçuş, radar, ayarlar) şimdilik eski halinde.

**5. Mobilde sabit "Rezervasyon Yap" barı:** booking formundan aşağı kaydırılıp
uzaklaşılınca ekranın altında beliriyor, tıklanınca forma geri dönüyor.
WhatsApp/canlı destek butonları üst üste binmesin diye yukarı kaydırıldı.

**6. Dönen müşteri form hatırlama:** rezervasyon tamamlanınca isim/telefon/
e-posta sadece o tarayıcıda (localStorage) saklanıyor, sonraki ziyarette 2.
adımdaki boş alanlar sessizce doluyor + küçük bir "önceki bilgileriniz
kullanıldı" notu çıkıyor.

**7. GERÇEK BUG BULUNDU VE ÇÖZÜLDÜ — alış noktasında "fiyat=0" bug'ının ikiz
kardeşi.** Varış noktasında zaten vardı: listeden seçim yapılmadan (elle
yazılıp) ilerlemeye çalışan müşteride fiyat hesaplanmıyordu, bu yüzden "listeden
seçim zorunlu" kuralı getirilmişti. Aynı risk alış noktasında da vardı — çarpıyla
temizleyip öneri listesinden seçmeden kendi adresini yazan müşteride ESKİ/
varsayılan koordinatlarla SESSİZCE YANLIŞ fiyat hesaplanabiliyordu (0 değil,
yanlış bir sayı — fark edilmesi çok daha zordu). Aynı kural artık alış noktası
için de var: listeden/GPS'ten gerçek seçim yapılmadan ileri gidilemiyor. Node
ile 3 senaryo (varsayılan/serbest yazım/gerçek seçim) simüle edilip doğrulandı.

**7b. Varsayılan alış metni** "Gazipaşa Havalimanı" → **"Alanya Gazipaşa
Havalimanı"** oldu (havalimanının nerede olduğu daha net olsun diye). Harita/
fiyat hesaplaması hâlâ doğru havalimanı koordinatlarına (36.2992, 32.3014)
çözümleniyor — gerçek kaynaklarla (Wikipedia, Travelmath) karşılaştırıp
doğruladım, ~10 metre farkla birebir aynı.

**7c. 2. adımda (İletişim Bilgileri) rezervasyon özeti eklendi** — güzergah,
KM/süre, tahmini fiyat (TL + $/€) artık kişisel bilgi girerken de görünüyor.
Önceden 1. adım gizlenince bu bilgiler tamamen kayboluyordu.

**7d. Alış + varış alanlarına 3'lü hızlı öneri çipi eklendi:** Alanya Gazipaşa
Havalimanı / Alanya / Antalya Havalimanı. Alış noktası çarpıyla temizlenince,
varış noktası da boşken tıklanınca (focus) çıkıyor. Üçü de doğru/farklı
koordinatlere çözümlendiği Node ile doğrulandı. Çiplerin "tek seçenekmiş gibi"
görünmemesi için üstlerine "✨ Hızlı seçim (ya da kendi adresinizi yazmaya
devam edin)" notu eklendi.

### Hemen Yapılması Gereken
- Railway deploy'unu kontrol et / canlıda hızlıca gözden geçir (özellikle alış
  noktası akışı — X butonu, 3 çip, "listeden seçim zorunlu" kuralı).
- Tartışılıp ertelenen: SMS bildirimi, dönen müşteri yorumu/değerlendirme
  bölümü (bilinçli olarak eklenmedi, istenmedi).

## GÜNCEL (18 Ağustos) — Booking formu iyileştirmeleri + kritik bug fix

**Oturum kapanışı:** Bugün üretken bir gündü — yolcu/çocuk stepper + kapasite
kilidi, rezervasyon fiyat=0 kritik bug'ı, harita/Telegram bildirim
iyileştirmeleri ve komple yeni bir özellik (Dönüş Rezervasyonu Linki) aynı
oturumda tasarlanıp kodlandı, test edildi, push edildi ve canlıda doğrulandı.
Açık kod tarafı sorun yok. Tek not: Tolga'nın kendi bilgisayarındaki Chrome
profilinde siteye giriş sorunu yaşandı (gizli pencerede/telefonda sorunsuzdu)
— proje/sunucu tarafıyla ilgisi yok, tarayıcı önbellek/çerez temizliğiyle
çözülüyor.

**1. Yolcu/Çocuk sayısı artık +/− stepper (önceden dropdown'dı).** Küçük, kompakt
butonlar (26px), min/maks'a gelince buton otomatik pasifleşiyor.

**2. Yolcu + Çocuk toplamı VIP Vito kapasitesini (9) hiçbir zaman aşamıyor —
uyarı mesajı bile yok, gerek kalmadan çalışıyor.** İkisi birbirine bağlı: biri
artınca diğerinin izin verilen üst sınırı otomatik daralıyor (örn. çocuk 4'teyken
yolcu en fazla 5'e çıkabiliyor), biri azalınca diğeri tekrar açılıyor. Değerler
asla arkadan otomatik değiştirilmiyor, sadece ileri gidiş sınırlanıyor. Çocuk
alanındaki kafa karıştırıcı "(maks. 4)" yazısı da kaldırıldı (artık tek referans
"maks 9").

**3. KRİTİK BUG BULUNDU VE ÇÖZÜLDÜ — bazı müşteriler fiyat=0 ile rezervasyon
yapabiliyordu (reservation #107 örneği bununla ortaya çıktı).** Kök neden: fiyat
hesaplaması sadece Google Places öneri listesinden bir adres SEÇİLDİĞİNDE
tetikleniyordu — müşteri adresi elle yazıp/yapıştırıp öneriye tıklamadan devam
ederse hiç hesaplanmıyordu, fiyat sessizce 0 gidiyordu. Çözüm (birkaç tur
tartışıp basitleştirdik — önceki "arka planda sessizce geocode et" yaklaşımını
sen reddettin, "neden kendini zorluyorsun" dedin, haklıydın): artık varış
alanı öneri listesinden seçilmeden bir sonraki adıma geçilemiyor, kırmızı
uyarı çıkıyor ("adresinizi bulamadık, öneri listesinden seçin"). Hiçbir
istisna/override yok — bilinçli olarak. Alış noktasındaki eski davranış
(anlık alan-dışı uyarısı) senin isteğinle aynen kaldı, sadece varış tarafı
değişti.

**4. Canlı site QA turu yapıldı (tüm yakın zamanlı değişiklikler tek tek test
edildi), 2 gerçek bug daha bulundu ve düzeltildi:**
   - Logoya tıklayıp forma sıfırlayınca Tahsis haritası bir daha hiç görünmüyordu
     (reset kodu haritayı gizliyor ama tekrar göstermiyordu) — düzeltildi.
   - Logoya tıklayınca tarih/saat alanları boşalıyor ve bir daha dolmuyordu —
     düzeltildi, artık "bugün + 1 saat" ile otomatik doluyor.

**5. Telegram bildirimleri iyileştirildi:**
   - "Harita yüklenemedi" uyarısı deploy sonrası yanlışlıkla tetikleniyordu
     (Railway'in konteyner değişim anındaki birkaç saniyelik kesintiye denk
     geliyordu) — artık 2.5sn arayla 3 kez deneniyor, gerçekten kalıcı sorun
     yoksa uyarı hiç gitmiyor.
   - "Fiyat Hesapla" bildirimine artık sadece form tipi değil, müşterinin
     seçtiği alış/varış (veya tahsiste alış+süre) ve tarih/saat de yazıyor —
     ödeme adımına gelmeden vazgeçen müşterileri de artık görebiliyorsun.

**6. SMS altyapısı konuşuldu** — şu an için kurulmadı, sadece fikir alışverişi
yapıldı.

**7. Şüpheli Google Cloud faturalandırma e-postası incelendi** — gerçek,
oturum açık console'a girilip kontrol edildi: bakiye 0, kart geçerli, e-postanın
iddiası doğrulanamadı. Muhtemelen phishing, aksiyon gerekmiyor.

**8. YENİ ÖZELLİK — Dönüş Rezervasyonu Linki:** Bir müşteri "dönüş hizmetini de
sizden almak istiyorum" dediğinde, admin panelinde rezervasyon detayına
"Dönüş Rezervasyonu Oluştur" butonu eklendi. Tıklayınca alış/varış ters
çevrilmiş (tahsiste süre aynen) önceden dolu bir form açılıyor, sen sadece
tarih/saat giriyorsun, fiyatı kontrol ediyorsun. Sistem müşteri ad/telefon/
e-postasını orijinal rezervasyondan kopyalayıp yeni bir rezervasyon oluşturuyor
ve tahmin edilemez, güvenli bir link üretiyor (linkteki numarayı değiştirerek
başka müşterinin bilgisine erişilemiyor — kriptografik olarak imzalı). Linki
WhatsApp'tan gönderiyorsun, müşteri açınca salt-okunur bir özet görüyor
(alış/varış/tarih/saat/yolcu/ücret), sadece telefonunu teyit edip ödeme
yöntemini (havale/kredi kartı) seçiyor — kredi kartı seçerse mevcut Garanti
ödeme sayfasına yönleniyor, havale seçerse IBAN bilgileri çıkıyor. Onay
gelince sana Telegram bildirimi + dashboard bildirimi gidiyor.

**8b. Dönüş Rezervasyonu Linki'nde 2 düzeltme yapıldı:** (1) Havale/kredi kartı
artık varsayılan seçili değil, müşteri bilinçli seçiyor; havale seçince IBAN
bilgileri submit beklemeden anında altta görünüyor; e-posta adresi alanı
eklendi. (2) **GERÇEK BUG:** kredi kartı seçildiğinde müşteri ödemeyi henüz
tamamlamadan sana "dönüş rezervasyonu onaylandı" diye Telegram gidiyordu —
yanıltıcıydı. Artık kart seçiminde sadece "ödeme bekleniyor" bildirimi
gidiyor, gerçek "ödendi" bildirimi + onay e-postası ödeme Garanti'den
doğrulandığında geliyor (normal rezervasyon akışıyla aynı mantık). Havale
seçiminde ise (müşteri kendi yatıracağını teyit ettiği için) bildirim +
e-posta hemen gidiyor, bu kısım aynı kaldı.

**8c. Dönüş Rezervasyonu Linki'nde son 3 iyileştirme (analiz sonrası):**
(1) Link artık 1 saat sonra otomatik geçersiz oluyor — bitiş zamanı token'ın
içine gömülü, sayfada da "saat X'e kadar geçerli" notu var. (2) Aynı linke
iki kez basma artık engelleniyor — rezervasyon zaten onaylanmışsa ikinci
istek reddediliyor, çift Telegram/e-posta gitmiyor. (3) Müşteri /donus
sayfasında telefon/e-posta düzeltirse artık admin panelindeki genel müşteri
kaydına (CRM) da işleniyor.

**8d. Dönüş Rezervasyonu Linki — CANLIDA DOĞRULANDI ✅ (18 Ağustos akşam).**
Tüm commit'ler push edildi, Railway deploy oldu. Canlı sitede test edildi:
ana sayfa ve `/donus/<id>/<token>` sayfası doğru çalışıyor, süresi dolmuş
linkte doğru "Bu Bağlantının Süresi Dolmuş" uyarı sayfası çıkıyor. Railway
loglarında (Tolga'nın paylaştığı) gerçek ziyaretçi trafiği (uçuş verisi,
canlı destek, Google Ads'ten gelen `gclid`'li ziyaretçiler) sorunsuz 200
dönüyor — sistem sağlıklı.

Not: Tolga bir ara kendi bilgisayarında siteye giremediğini bildirdi, telefonda
sorunsuz açılıyordu — bu sitenin sorunu değil, Tolga'nın bilgisayarındaki
tarayıcı/DNS önbelleği kaynaklıydı (sert yenileme / gizli pencere / DNS
flush ile çözülür), sunucu tarafında hiçbir sorun yoktu.

**9. GERÇEK BUG — filo galeri görselleri kayboldu, kök neden bulundu ve
kalıcı olarak düzeltildi.** Sebep: `load_vehicles()` fonksiyonu, veritabanına
ULAŞILAMADIĞINDA da (geçici Railway deploy kesintisi gibi) "veri hiç yok"
sanıp devreye giriyor ve varsayılan demo görselleri (1 gerçek + 2 stok
fotoğraf) veritabanının üzerine KALICI olarak yazıyordu. Bugünkü onlarca
deploy sırasındaki geçici bir bağlantı kesintisi tam bu şekilde gerçek
galeri verinizi silmiş. Düzeltme: artık "veri gerçekten yok" ile "veritabanına
şu an ulaşılamıyor" ayrı ayrı algılanıyor, sadece ilki için varsayılan
yazılıyor. **Önemli: kaybolan fotoğraf dosyalarını ben geri getiremem —
düzeltme canlıya çıktıktan sonra admin panelinden yeniden yüklemen gerekiyor.**
Kod tarandı, bu tehlikeli kalıp sadece `load_vehicles()`'ta vardı, başka
yerde yok.

**10. 2 gerçek bug daha bulundu ve düzeltildi (admin'in yeni rezervasyon
sistemi incelenirken ortaya çıktı):** (1) "Ödeme Linki Oluştur" butonu
tanımsız bir `PAYMENT_PROVIDER` değişkeni yüzünden her tıklandığında
sunucu hatası veriyordu, özellik tamamen çalışmıyordu — düzeltildi. (2)
Takvimden admin'in girdiği manuel rezervasyonlarda müşteriye hiçbir zaman
onay e-postası gitmiyordu (formda e-posta alanı bile yoktu) — forma e-posta
alanı eklendi, girilirse onay e-postası gidiyor.

**11. YENİ — "Ödeme Linki Oluştur" da Dönüş Rezervasyonu Linki gibi
genişletildi.** Önceden bu link doğrudan çıplak bir kredi kartı formuna
gidiyordu, havale seçeneği yoktu. Artık müşteri linke tıklayınca önce
rezervasyonun tam özetini (alış/varış/tarih/saat/tutar) görüyor, sonra
Kredi Kartı (Garanti BBVA) veya Havale/EFT seçiyor — havale seçerse IBAN
bilgileri anında görünüyor, kart seçerse gerçek ödeme formuna yönleniyor.
Aynı 1 saatlik süre sınırı ve çift-tıklama koruması burada da geçerli.

### Hemen Yapılması Gereken
- **git push origin main** kendi bilgisayarından — 2 commit push bekliyor
  (madde 9-10-11 dahil, kod tarafında test edildi ama Railway'e henüz
  deploy olmadı).
- Push sonrası admin panelinden filo galeri fotoğraflarını yeniden yükle
  (madde 9 — dosyalar kurtarılamıyor, sadece tekrar yükleme çözer).

### Açık / senin kararına kalan konular
- **404 sayfası:** var olmayan bir adrese gidince şu an düzgün tasarlanmış hata
  sayfası yerine ham JSON dönüyor (`{"error": "Dosya bulunamadı"}`). Küçük bir
  SEO/UX detayı, düzeltilsin mi diye sordum, henüz cevap vermedin.
- **Rezervasyon #107**: hâlâ fiyatsız duruyor, admin panelden "Düzenle" ile elle
  fiyat girmen gerekiyor (bug'dan önce oluşmuş, ben veri silemem/değiştiremem).
- **Rezervasyon #112**: benim test verim, silinmesi gerekiyor (ben kalıcı veri
  silemem, admin panelinden senin silmen lazım).

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
- [x] **Ödeme sağlayıcısı seçimi**: Garanti BBVA Sanal POS'a karar verildi, canlıda çalışıyor (Stripe/PayTR gündemden kalktı)
- [x] **aggregateRating sahte verisi**: kaldırıldı, kodda artık hiç yok (kontrol edildi — index.html/server.py'de aggregateRating/ratingValue/reviewCount hiçbir yerde geçmiyor). Gerçek yorum/puan bölümü Tolga'nın isteğiyle şimdilik eklenmiyor.
- [ ] **admin.html indeks kontrolü**: Search Console → URL denetimi'nden kontrol edilmedi, hâlâ açık
- [ ] **Google Search Console'a sitemap gönderimi**: teyit edilmedi
- [ ] **Opsiyonel `/iletisim` sayfası**: şu an anasayfanın bir bölümü, ayrı URL değil
- [ ] Task #37 (eski liste): "Her bölgeye 4 galeri resmi ekle" — durumu teyit edilmedi

## Önemli Notlar

- Backend Python stdlib `http.server` (server.py), PostgreSQL opsiyonel (`db.py`), yoksa JSON dosya fallback
- Admin login: `admin@guliztransfer.com` / `Guliz2025!`
- Assistant admin şifresini kendisi giremez (güvenlik kuralı) — login her zaman Tolga tarafından yapılmalı
- Assistant GitHub'a push edemez (kimlik bilgisi yok) — push her zaman Tolga'nın kendi bilgisayarından yapılmalı
