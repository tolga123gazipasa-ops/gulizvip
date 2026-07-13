# Railway Deployment Rehberi — Güliz VIP

## 1. GitHub'a Push (Kendi Bilgisayarınızdan)

VM proxy'i engellediği için push'u sizin yapmanız gerekiyor. Proje dizininde (`C:\Users\MSI\OneDrive\Desktop\gulizvip`) şu komutları çalıştırın:

```bash
git push
```

Eğer GitHub kimlik bilgisi sorarsa:

```bash
# Windows'ta GitHub CLI varsa:
gh auth login

# Veya Personal Access Token (PAT) ile:
# Kullanıcı adı: tolga123gazipasa-ops
# Şifre: <GitHub'dan aldığınız PAT token>
```

---

## 2. Railway Hesabına GitHub Depoyu Bağlama

1. **[railway.app](https://railway.app)** adresine gidin ve GitHub ile giriş yapın
2. "New Project" → "Deploy from GitHub repo" seçin
3. `tolga123gazipasa-ops/gulizvip` reposunu seçin
4. Railway otomatik olarak `railway.json`'daki yapılandırmayı okuyacak ve deploy edecek

---

## 3. PostgreSQL Veritabanını Ekleme

1. Railway proje dashboard'unda **"New"** butonuna tıklayın
2. **"Database"** → **"PostgreSQL"** seçin
3. PostgreSQL eklendikten sonra, otomatik olarak bir `DATABASE_URL` environment variable'ı oluşacak

---

## 4. Environment Variable'ları Ayarlama

Railway'de proje dashboard'unda **Variables** sekmesine gidin. Aşağıdaki değişkenleri ekleyin:

| Variable | Değer |
|---|---|
| `ADMIN_USER` | `admin` |
| `ADMIN_PASS` | `gulizvip2026` |
| `SECRET_KEY` | `guliz-vip-hmac-secret-2026` |
| `TOKEN_TTL` | `86400` |
| `GOOGLE_MAPS_API_KEY` | `AIzaSyD-IGkbR6iyxvdeQ_Cfekjks3KOWMD7RKw` |
| `TELEGRAM_BOT_TOKEN` | *(Telegram bot token'ınız, varsa)* |
| `TELEGRAM_CHAT_ID` | *(Telegram chat ID'niz, varsa)* |
| `HOST` | `0.0.0.0` |
| `PORT` | `8081` |

> **Not:** `DATABASE_URL` otomatik olarak Railway PostgreSQL tarafından sağlanır. Elle eklemeniz gerekmez.

---

## 5. Deploy Etme

1. Variables ayarlandıktan sonra Railway otomatik deploy başlatacaktır
2. **Deploy Logs** sekmesinden süreci takip edebilirsiniz
3. `pip install psycopg2-binary` adımında başarılı olmalı
4. `python3 server.py` ile sunucu başlayacak

---

## 6. Domain Ayarı (gulizvip.com.tr)

1. Railway proje dashboard'ında **Settings** → **Domains**
2. `gulizvip.com.tr` alan adını ekleyin
3. DNS ayarları için Railway'in verdiği `*.railway.app` adresine CNAME kaydı oluşturun
4. Railway SSL sertifikasını otomatik yönetir (Let's Encrypt)

---

## 7. Sağlık Kontrolü

Deploy tamamlandıktan sonra:

```
https://gulizvip.com.tr/api/flights        — Uçuş verisi
https://gulizvip.com.tr/api/unit-price     — Birim fiyat
https://gulizvip.com.tr/api/bank-accounts  — Banka hesapları
https://gulizvip.com.tr/                   — Ana sayfa
https://gulizvip.com.tr/admin.html         — Admin paneli
```

---

## 8. Railway Monitoring

- **Metrics** sekmesi: CPU/RAM kullanımı
- **Deploy Logs**: Sunucu çıktısı ve hatalar
- **Settings** → **Restart**: Sunucuyu yeniden başlatma
- **Settings** → **Rollback**: Sorun durumunda önceki sürüme dönme

---

## Sık Sorunlar ve Çözümleri

| Sorun | Çözüm |
|---|---|
| `psycopg2-binary` yüklenemiyor | `requirements.txt`'de `psycopg2-binary>=2.9` satırı var mı kontrol edin |
| Veritabanı bağlantı hatası | DATABASE_URL env var'ının doğru ayarlandığından emin olun |
| 502 Bad Gateway | Healthcheck yanıt vermiyor — `railway.json`'daki `healthcheckPath` `/api/flights` |
| Sayfa açılmıyor | Railway'de domain + SSL yayılması 5-10 dk sürebilir |

---

## Proje Durumu

- ✅ **Git commit:** `cd8dcc5` — "feat: service area validation, quick reservation, cleanup"
- ⏳ **Git push:** Bilgisayarınızdan yapmanız gerekiyor (`git push`)
- ⏳ **Railway deploy:** Push sonrası Railway'de proje oluşturup bağlayın
- ⏳ **Veritabanı:** Railway PostgreSQL eklendiğinde otomatik çalışacak
