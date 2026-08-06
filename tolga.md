# Güliz VIP — Proje Durumu (Kaldığımız Yer)

Son güncelleme: 2026-08-06

## Şu An Neredeyiz

**FAZ 1 (Araç Takvimi ve Filo Yönetim Modülü) tamamlandı, deploy edilmeyi bekliyor.**

Detaylı özet: `faz1-arac-takvimi-ozet.md` dosyasında.

### Hemen Yapılması Gereken

```
cd C:\proje\gulizvip
git add .
git commit -m "Faz 1: Arac Takvimi ve Filo Yonetim Modulu + kritik syntax hatasi duzeltmesi"
git push
```

Deploy sonrası admin panelde **Araç Takvimi → Araçları Yönet → "Filodan Otomatik Oluştur"** ile araç birimlerini (Vito 1/2/3 vb.) bir kere oluşturman lazım.

⚠️ Bu deploy içinde production'ı çökertecek kritik bir syntax hatası da düzeltildi (`global RESERVATIONS` hatası) — o yüzden bu push'u geciktirme.

## Genel Proje Geçmişi (Bu Oturumda Yapılanlar)

1. **Popüler Turistik Bölgeler (SEO/Destinasyonlar) özelliği**: GZP + AYT kapsayan 6 landmark destinasyon (Gazipaşa Delik Deniz, Gazipaşa Koru Plajı, Alanya Kalesi, Side Antik Kenti, Belek, Kemer) — admin panelden tam CRUD, galeri resimleri, detay modalı. **Canlıya (Railway) eklendi.**
2. **Kritik altyapı sorunu bulundu ve düzeltildi**: Railway "web" servisinde `DATABASE_URL` hiç tanımlı değildi — bu yüzden destinasyonlar gibi DB-first özellikler production'da sessizce boş kalıyordu. `railway variables --set` ile düzeltildi.
3. **Admin panel bug'ları**: "Destinasyonlar gelmiyor" sorunu (duplicate `switchTab()` fonksiyonu, `view-destinations` dispatch eksikti) düzeltildi.
4. **FAZ 1 — Araç Takvimi ve Filo Yönetim Modülü** (bu oturumun büyük kısmı):
   - DB: `vehicle_units`, `calendar_blocks` (JSON config), `reservations` tablosuna 9 yeni kolon (lat/lng, distance_km, buffer_minutes, vehicle_unit_id, vb.)
   - Backend: `/api/admin/vehicle-units`, `/api/admin/calendar`, `/api/admin/calendar/block`, `/api/admin/calendar/quick-reservation`
   - Admin UI: Gantt-tarzı günlük takvim, renk kodlama, manuel blok/hızlı rezervasyon, araç birimi yönetimi
   - Bonus: rezervasyon düzenleme ve onay/iptal butonlarındaki 4 sessiz bug düzeltildi

## Açık Kalanlar / Sıradaki Adımlar

- [ ] Yukarıdaki deploy komutlarını çalıştır (git push)
- [ ] Deploy sonrası "Filodan Otomatik Oluştur" ile araç birimlerini oluştur
- [ ] Destinasyonların 4'er galeri resminin production DB'sine gerçekten yazıldığını admin panelden teyit et
- [ ] **Faz 2** (henüz başlanmadı): Google Maps ile mesafe/süre hesaplama — otomatik ve manuel rezervasyonlarda pickup/dropoff koordinatlarını doldurma
- [ ] **Faz 3** (henüz başlanmadı): Otomatik siparişlerin çakışmayan ilk müsait araca ataması + sitede "Dolu/Müsait Değil" gösterimi + o günkü rotaların harita görünümü

## Önemli Notlar

- Backend Python stdlib `http.server` (server.py), PostgreSQL opsiyonel (`db.py`), yoksa JSON dosya fallback.
- Admin login: `admin@guliztransfer.com` / `Guliz2025!`
- Railway proje: "easygoing-recreation", servisler: "web" + "Postgres"
- Assistant admin şifresini kendisi giremez (güvenlik kuralı) — login her zaman Tolga tarafından yapılmalı.
