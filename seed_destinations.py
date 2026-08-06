"""
Popüler Turistik Bölgeler — PostgreSQL seed/güncelleme scripti.

Bu script, Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından hizmet verilen
popüler turistik bölgeleri/plajları/landmark'ları veritabanına (varsa PostgreSQL,
yoksa destinations.json'a) ekler veya (slug eşleşirse) günceller.

Ayrıca eski, daha genel şehir-bazlı seed kayıtlarını (ör. "Alanya Merkez", "Antalya")
ve "Test Dest" gibi test amaçlı kayıtları temizler — bu script artık daha spesifik,
landmark odaklı 6 bölgeyi tek doğruluk kaynağı (source of truth) olarak kullanır.

Kullanım (yerelde, DATABASE_URL Railway Postgres'e işaret ederken):
    railway run python3 seed_destinations.py

Kullanım (DATABASE_URL yoksa — sadece destinations.json fallback güncellenir):
    python3 seed_destinations.py
"""
import db

SEED_DESTINATIONS = [
    {
        "name": "Gazipaşa Delik Deniz & Kral Koyu",
        "slug": "gazipasa-delik-deniz-kral-koyu",
        "airport": "GZP",
        "sortOrder": 1,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1596394516093-501ba68a0ba6?w=800&q=80",
        "galleryImages": "https://images.unsplash.com/photo-1601581875309-fafbf2d3ed3a?w=800&q=80,https://images.unsplash.com/photo-1473116763249-2faaef81ccda?w=800&q=80,https://images.unsplash.com/photo-1500375592092-40eb2168fd21?w=800&q=80,https://images.unsplash.com/photo-1590523277543-a94d2e4eb00b?w=800&q=80",
        "description": "Gazipaşa'nın en özel koylarından Delik Deniz ve Kral Koyu, kayalık formasyonları ve turkuaz berraklığındaki suyuyla doğa tutkunlarının gözdesi. Gazipaşa Havalimanı'na (GZP) yalnızca dakikalar mesafesindeki bu saklı cennete Güliz VIP ile konforlu ve hızlı transfer sağlıyoruz.",
    },
    {
        "name": "Gazipaşa Koru Plajı & Doğal Havuzlar",
        "slug": "gazipasa-koru-plaji-dogal-havuzlar",
        "airport": "GZP",
        "sortOrder": 2,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1519046904884-53103b34b206?w=800&q=80",
        "galleryImages": "https://images.unsplash.com/photo-1440581572325-0bea30075d9d?w=800&q=80,https://images.unsplash.com/photo-1516214104703-d870798883c5?w=800&q=80,https://images.unsplash.com/photo-1500835556837-99ac94a94552?w=800&q=80,https://images.unsplash.com/photo-1473116763249-2faaef81ccda?w=800&q=80",
        "description": "Sık çam ormanlarının denizle buluştuğu Koru Plajı ve çevresindeki doğal kaya havuzları, sakinliği ve el değmemiş doğasıyla öne çıkıyor. Gazipaşa Havalimanı (GZP) çıkışlı VIP transferlerimizle bu huzurlu köşeye güvenli ve dakik ulaşım sunuyoruz.",
    },
    {
        "name": "Alanya Kalesi & Kleopatra Plajı",
        "slug": "alanya-kalesi-kleopatra-plaji",
        "airport": "both",
        "sortOrder": 3,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1591604466107-ec97de577aff?w=800&q=80",
        "galleryImages": "https://images.unsplash.com/photo-1558370781-d6196949e317?w=800&q=80,https://images.unsplash.com/photo-1471623320832-752e8bbf8413?w=800&q=80,https://images.unsplash.com/photo-1533105079780-92b9be482077?w=800&q=80,https://images.unsplash.com/photo-1548786811-dd6e453ccca7?w=800&q=80",
        "description": "Bizans döneminden kalma tarihi Alanya Kalesi ve dünyaca ünlü altın kumlu Kleopatra Plajı, Alanya'nın simgesi haline gelmiş iki eşsiz durak. Gazipaşa Havalimanı'ndan (GZP) 40 dakikada, Antalya Havalimanı'ndan (AYT) ise Güliz VIP konforuyla bu tarihi ve doğal mirasa ulaşabilirsiniz.",
    },
    {
        "name": "Side Antik Kenti & Manavgat",
        "slug": "side-antik-kenti-manavgat",
        "airport": "both",
        "sortOrder": 4,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1548786811-dd6e453ccca7?w=800&q=80",
        "galleryImages": "https://images.unsplash.com/photo-1558370781-d6196949e317?w=800&q=80,https://images.unsplash.com/photo-1471623320832-752e8bbf8413?w=800&q=80,https://images.unsplash.com/photo-1553342385-111fd6bc6ab3?w=800&q=80,https://images.unsplash.com/photo-1500835556837-99ac94a94552?w=800&q=80",
        "description": "Apollon Tapınağı ve antik tiyatrosuyla ünlü Side ile hemen yanı başındaki Manavgat Şelalesi, tarih ve doğayı tek rotada buluşturuyor. Antalya Havalimanı'ndan (AYT) doğrudan, Gazipaşa Havalimanı'ndan (GZP) da Güliz VIP ile konforlu transfer imkanı sunuyoruz.",
    },
    {
        "name": "Belek Lüks Golf & Resort Otelleri",
        "slug": "belek-luks-golf-resort-otelleri",
        "airport": "AYT",
        "sortOrder": 5,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1587922546307-776227941871?w=800&q=80",
        "galleryImages": "https://images.unsplash.com/photo-1602343168117-bb8ffe3e2e9f?w=800&q=80,https://images.unsplash.com/photo-1544984243-ec57ea16fe25?w=800&q=80,https://images.unsplash.com/photo-1528909514045-2fa4ac7a08ba?w=800&q=80,https://images.unsplash.com/photo-1590523277543-a94d2e4eb00b?w=800&q=80",
        "description": "Dünya standartlarında golf sahaları ve 5 yıldızlı lüks resort otelleriyle Belek, Akdeniz'in en prestijli tatil destinasyonlarından biri. Antalya Havalimanı'ndan (AYT) Belek'teki otelinize VIP Vito ile şık, sessiz ve konforlu bir transfer deneyimi yaşatıyoruz.",
    },
    {
        "name": "Kemer Marina & Göynük Kanyonu",
        "slug": "kemer-marina-goynuk-kanyonu",
        "airport": "AYT",
        "sortOrder": 6,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1553342385-111fd6bc6ab3?w=800&q=80",
        "galleryImages": "https://images.unsplash.com/photo-1516214104703-d870798883c5?w=800&q=80,https://images.unsplash.com/photo-1440581572325-0bea30075d9d?w=800&q=80,https://images.unsplash.com/photo-1533105079780-92b9be482077?w=800&q=80,https://images.unsplash.com/photo-1601581875309-fafbf2d3ed3a?w=800&q=80",
        "description": "Lüks yatların demirlediği şık Kemer Marina ile doğa tutkunlarının favorisi Göynük Kanyonu, Kemer'in hem sofistike hem vahşi doğa yüzünü yansıtıyor. Antalya Havalimanı'ndan (AYT) Kemer'e Güliz VIP güvencesiyle zamanında ve konforlu ulaşım sağlıyoruz.",
    },
]

# Eski / test amaçlı kayıtlar — bu script çalıştığında temizlenir.
# ("gazipasa", "alanya-merkez" vb. bir önceki, daha genel şehir-bazlı seed'den kalanlar)
REMOVE_SLUGS = {
    "test",
    "gazipasa", "alanya-merkez", "mahmutlar", "okurcalar",
    "antalya", "side", "manavgat", "belek", "kemer",
}


def main():
    db.init_db()  # tablo yoksa oluşturur, 'airport' kolonunu ekler (varsa dokunmaz)

    existing = db.get_destinations(active_only=False) or []
    by_slug = {d.get("slug"): d for d in existing if d.get("slug")}

    added, updated, removed = 0, 0, 0

    for item in SEED_DESTINATIONS:
        slug = item["slug"]
        if slug in by_slug:
            dest_id = by_slug[slug]["id"]
            ok = db.update_destination(dest_id, item)
            if ok:
                updated += 1
                print(f"  [~] güncellendi: {item['name']} ({slug})")
            else:
                print(f"  [!] güncellenemedi: {item['name']} ({slug})")
        else:
            new_id = db.save_destination(item)
            if new_id:
                added += 1
                print(f"  [+] eklendi: {item['name']} ({slug}) -> id={new_id}")
            else:
                print(f"  [!] eklenemedi: {item['name']} ({slug})")

    for slug in REMOVE_SLUGS:
        if slug in by_slug:
            dest_id = by_slug[slug]["id"]
            if db.delete_destination(dest_id):
                removed += 1
                print(f"  [-] silindi (eski/test kaydı): {slug}")

    print(f"\nTamamlandı — eklenen: {added}, güncellenen: {updated}, silinen: {removed}")


if __name__ == "__main__":
    main()
