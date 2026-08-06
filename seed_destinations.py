"""
Popüler Turistik Bölgeler — PostgreSQL seed/güncelleme scripti.

Bu script, Gazipaşa (GZP) ve Antalya (AYT) havalimanlarından hizmet verilen
popüler turistik bölgeleri veritabanına (varsa PostgreSQL, yoksa destinations.json'a)
ekler veya (slug eşleşirse) günceller. "Test Dest" gibi test amaçlı eski kayıtları temizler.

Kullanım (yerelde, DATABASE_URL Railway Postgres'e işaret ederken):
    railway run python3 seed_destinations.py

Kullanım (DATABASE_URL yoksa — sadece destinations.json fallback güncellenir):
    python3 seed_destinations.py
"""
import db

SEED_DESTINATIONS = [
    {
        "name": "Gazipaşa",
        "slug": "gazipasa",
        "airport": "GZP",
        "sortOrder": 1,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1596394516093-501ba68a0ba6?w=800&q=80",
        "description": "Merkez üssümüz Gazipaşa Havalimanı (GZP), bakir koyları ve doğal güzellikleriyle Akdeniz'in saklı cennetine açılan kapınız. Uçağınız iner inmez VIP Vito'muzla karşılanır, Alanya ve çevresine dakikalar içinde ulaşırsınız.",
    },
    {
        "name": "Alanya Merkez",
        "slug": "alanya-merkez",
        "airport": "both",
        "sortOrder": 2,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1591604466107-ec97de577aff?w=800&q=80",
        "description": "Kalesi, tarihi Kızıl Kule'si ve kilometrelerce uzanan sahilleriyle Alanya, Akdeniz'in en gözde tatil merkezlerinden biri. Gazipaşa Havalimanı'na (GZP) yalnızca 40 km mesafedeki Alanya merkeze Güliz VIP ile konforlu ve doğrudan transfer hizmeti sunuyoruz; Antalya Havalimanı'ndan (AYT) gelen misafirlerimiz için de aynı ayrıcalıklı hizmet geçerlidir.",
    },
    {
        "name": "Mahmutlar",
        "slug": "mahmutlar",
        "airport": "GZP",
        "sortOrder": 3,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1602002418082-a4443e081dd1?w=800&q=80",
        "description": "Alanya'nın doğusunda yer alan Mahmutlar, geniş plajları ve sakin atmosferiyle özellikle uzun süreli tatilcilerin gözdesi. Gazipaşa Havalimanı'ndan (GZP) Mahmutlar'daki otel veya rezidansınıza kapıdan kapıya, konforlu VIP ulaşım sağlıyoruz.",
    },
    {
        "name": "Okurcalar",
        "slug": "okurcalar",
        "airport": "GZP",
        "sortOrder": 4,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1519046904884-53103b34b206?w=800&q=80",
        "description": "Alanya'ya bağlı sakin bir sahil beldesi olan Okurcalar, aile dostu tatil köyleri ve huzurlu plajlarıyla dikkat çekiyor. Gazipaşa Havalimanı (GZP) çıkışlı transferlerimizle Okurcalar'a güvenli, zamanında ve konforlu ulaşım garantisi veriyoruz.",
    },
    {
        "name": "Antalya",
        "slug": "antalya",
        "airport": "AYT",
        "sortOrder": 5,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=800&q=80",
        "description": "Türkiye'nin turizm başkenti Antalya, tarihi Kaleiçi'si, Düden Şelalesi ve canlı şehir merkeziyle her yıl milyonlarca ziyaretçiyi ağırlıyor. Antalya Havalimanı'ndan (AYT) şehir merkezine ve otelinize Güliz VIP güvencesiyle direkt ve ayrıcalıklı transfer sunuyoruz.",
    },
    {
        "name": "Side",
        "slug": "side",
        "airport": "AYT",
        "sortOrder": 6,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1590129892140-01e15fe07ce1?w=800&q=80",
        "description": "Antik tiyatrosu, Apollon Tapınağı ve uzun kumsallarıyla ünlü Side, tarih ve denizin iç içe geçtiği büyüleyici bir tatil beldesi. Antalya Havalimanı'ndan (AYT) Side'deki otelinize konforlu VIP transferiniz için Güliz VIP yanınızda.",
    },
    {
        "name": "Manavgat",
        "slug": "manavgat",
        "airport": "AYT",
        "sortOrder": 7,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1500534623283-312aade485b7?w=800&q=80",
        "description": "Manavgat Şelalesi ve yemyeşil doğasıyla ünlü bu şirin ilçe, doğa tutkunlarının vazgeçilmez rotası. Antalya Havalimanı (AYT) çıkışlı transferlerimizle Manavgat'a konforlu ve zamanında ulaşım sağlıyoruz.",
    },
    {
        "name": "Belek",
        "slug": "belek",
        "airport": "AYT",
        "sortOrder": 8,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1587922546307-776227941871?w=800&q=80",
        "description": "Dünyaca ünlü golf sahaları ve 5 yıldızlı lüks tatil köyleriyle Belek, Akdeniz'in en ayrıcalıklı tatil destinasyonlarından biri. Antalya Havalimanı'ndan (AYT) Belek'teki resort veya otelinize VIP Vito ile şık ve konforlu ulaşım sunuyoruz.",
    },
    {
        "name": "Kemer",
        "slug": "kemer",
        "airport": "AYT",
        "sortOrder": 9,
        "isActive": True,
        "imageUrl": "https://images.unsplash.com/photo-1569517282132-25d22f4573e6?w=800&q=80",
        "description": "Toroslar'ın eteklerinde, Olimpos Beydağları Milli Parkı sınırlarındaki Kemer; yemyeşil doğası ve berrak deniziyle Akdeniz'in en gözde tatil merkezlerinden biri. Antalya Havalimanı'ndan (AYT) Kemer'e VIP transfer hizmetimizle güvenli ve konforlu bir yolculuk sizi bekliyor.",
    },
]

REMOVE_SLUGS = {"test"}  # eski test kayıtları


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
                print(f"  [-] silindi (test kaydı): {slug}")

    print(f"\nTamamlandı — eklenen: {added}, güncellenen: {updated}, silinen: {removed}")


if __name__ == "__main__":
    main()
