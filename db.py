"""
Güliz VIP — PostgreSQL Veritabanı Modülü
psycopg2-binary ile PostgreSQL bağlantısı, tablo yönetimi, CRUD işlemleri
"""
import os
import re
import json
import time
from datetime import datetime

DESTINATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "destinations.json")
ADMIN_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_config.json")


def _coerce_passenger_count(value, default=1):
    """'passengers' alanı bazen sayısal değil, açıklayıcı bir metin olabilir
    (örn. frontend'deki tek seçenekli bilgilendirme select'inden gelen
    "1 - 9 Kişi (VIP Vito)" gibi bir string — bkz. index.html #transfer-passengers).
    PostgreSQL'deki passengers sütunu INTEGER olduğu için ham metin doğrudan
    yazılırsa "invalid input syntax for type integer" hatasıyla INSERT/UPDATE
    başarısız olur (canlıda tespit edildi). Burada metinden İLK sayıyı çıkarıp
    veritabanına onu yazıyoruz; e-posta/Telegram/admin gösterimlerinde kullanılan
    orijinal metin (reservation dict / JSON / RESERVATIONS listesi) DEĞİŞMİYOR,
    sadece bu fonksiyondan geçen değer veritabanı sütununa gidiyor."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if value is None:
        return default
    match = re.search(r"\d+", str(value))
    if match:
        try:
            return int(match.group())
        except ValueError:
            return default
    return default

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# ─── Connection ─────────────────────────────────────────────────────────────────

def get_conn():
    """DATABASE_URL environment variable'ından PostgreSQL bağlantısı al."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    return psycopg2.connect(db_url, sslmode="require")


# ─── Table Creation ─────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS reservations (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) DEFAULT 'transfer',
    customer_name VARCHAR(200) NOT NULL,
    customer_phone VARCHAR(50) DEFAULT '',
    customer_email VARCHAR(200) DEFAULT '',
    pickup VARCHAR(500) NOT NULL,
    destination VARCHAR(500) DEFAULT '',
    flight_number VARCHAR(50) DEFAULT '',
    date VARCHAR(20) DEFAULT '',
    time VARCHAR(20) DEFAULT '',
    passengers INTEGER DEFAULT 1,
    duration VARCHAR(100) DEFAULT '',
    notes TEXT DEFAULT '',
    price DECIMAL(10,2) DEFAULT 0,
    payment_method VARCHAR(20) DEFAULT '',
    payment_status VARCHAR(20) DEFAULT 'pending',
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS page_content (
    slug VARCHAR(100) PRIMARY KEY,
    title VARCHAR(200) NOT NULL DEFAULT '',
    subtitle VARCHAR(300) DEFAULT '',
    content TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS destinations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT DEFAULT '',
    image_url VARCHAR(500) DEFAULT '',
    gallery_images TEXT DEFAULT '',
    slug VARCHAR(200) DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    airport VARCHAR(20) DEFAULT 'both',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL DEFAULT '',
    phone VARCHAR(50) DEFAULT '',
    email VARCHAR(200) DEFAULT '',
    notes TEXT DEFAULT '',
    total_bookings INTEGER DEFAULT 0,
    total_spent DECIMAL(10,2) DEFAULT 0,
    is_vip BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) DEFAULT '',
    name VARCHAR(200) DEFAULT '',
    phone VARCHAR(50) DEFAULT '',
    message TEXT DEFAULT '',
    is_admin BOOLEAN DEFAULT FALSE,
    admin_name VARCHAR(100) DEFAULT '',
    is_read BOOLEAN DEFAULT FALSE,
    is_new_session BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

CREATE TABLE IF NOT EXISTS contact_messages (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) DEFAULT '',
    phone VARCHAR(50) DEFAULT '',
    email VARCHAR(200) DEFAULT '',
    message TEXT DEFAULT '',
    ip_address VARCHAR(64) DEFAULT '',
    city VARCHAR(100) DEFAULT '',
    country VARCHAR(100) DEFAULT '',
    region VARCHAR(100) DEFAULT '',
    user_agent VARCHAR(500) DEFAULT '',
    status VARCHAR(20) DEFAULT 'new',
    admin_note TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dashboard_notifications (
    id SERIAL PRIMARY KEY,
    message TEXT DEFAULT '',
    ntype VARCHAR(30) DEFAULT 'info',
    reservation_id INTEGER,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def init_db():
    """Veritabanı tablolarını oluştur."""
    if not HAS_PSYCOPG2:
        print("[!] psycopg2-binary kurulu değil. DB modülü devre dışı.")
        return False
    try:
        conn = get_conn()
        if not conn:
            print("[!] DATABASE_URL bulunamadı. DB bağlantısı kurulamadı.")
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLES_SQL)
                # Mevcut tablolarda eksik olabilecek yeni kolonlar için güvenli migration
                cur.execute("ALTER TABLE destinations ADD COLUMN IF NOT EXISTS airport VARCHAR(20) DEFAULT 'both';")
                cur.execute("ALTER TABLE destinations ADD COLUMN IF NOT EXISTS gallery_images TEXT DEFAULT '';")
                # Araç Takvim ve Filo Yönetim Modülü (FAZ 1) — reservations tablosuna
                # takvim/harita alanları. Hepsi nullable/varsayılanlı, mevcut kayıtları bozmaz.
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS vehicle_unit_id INTEGER;")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS buffer_minutes INTEGER DEFAULT 45;")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS estimated_duration_minutes INTEGER;")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS pickup_lat DECIMAL(10,7);")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS pickup_lng DECIMAL(10,7);")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS dropoff_lat DECIMAL(10,7);")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS dropoff_lng DECIMAL(10,7);")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS distance_km DECIMAL(6,2);")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS is_manual BOOLEAN DEFAULT FALSE;")
                # CRM / Ödeme Modülü — müşteri eşleştirme + döviz + ödeme linki altyapısı.
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS customer_id INTEGER;")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'TRY';")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS payment_link VARCHAR(500) DEFAULT '';")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS stripe_payment_intent_id VARCHAR(200) DEFAULT '';")
                # Garanti BBVA Sanal POS — prepare adımında üretilen orderid'nin DB'ye kalıcı
                # yazılması için (önceden sadece JSON yedeğine yazılıyordu; sunucu bir redeploy
                # ile yeniden başladığında DB'den taze yüklenen rezervasyon bu alanı kaybediyor,
                # Garanti'nin /api/payments/garanti/result geri dönüşü eşleşemiyordu — 13 Ağustos
                # canlı testte tam bu senaryo yaşandı).
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS garanti_order_id VARCHAR(100) DEFAULT '';")
                # Çocuk sayısı + bebek/çocuk koltuğu ihtiyacı — 17 Ağustos'ta eklendi, isim
                # toplamadan sadece operasyonel planlama (şoförün koltuk hazırlaması) için.
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS child_count INTEGER DEFAULT 0;")
                cur.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS needs_child_seat BOOLEAN DEFAULT FALSE;")
                # İletişim mesajları — IP/coğrafya/cihaz bilgisi + durum/not (admin panel detaylı yönetim)
                cur.execute("ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64) DEFAULT '';")
                cur.execute("ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS city VARCHAR(100) DEFAULT '';")
                cur.execute("ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS country VARCHAR(100) DEFAULT '';")
                cur.execute("ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS region VARCHAR(100) DEFAULT '';")
                cur.execute("ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS user_agent VARCHAR(500) DEFAULT '';")
                cur.execute("ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'new';")
                cur.execute("ALTER TABLE contact_messages ADD COLUMN IF NOT EXISTS admin_note TEXT DEFAULT '';")
        conn.close()
        print("[✓] PostgreSQL tabloları hazır.")
        return True
    except Exception as e:
        print(f"[!] DB başlatılamadı: {e}")
        return False


# ─── Reservations ───────────────────────────────────────────────────────────────

def load_reservations_from_db():
    """Tüm rezervasyonları veritabanından yükle."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM reservations ORDER BY created_at DESC")
                rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "type": row["type"],
                "customerName": row["customer_name"],
                "customerPhone": row["customer_phone"],
                "customerEmail": row["customer_email"],
                "pickup": row["pickup"],
                "destination": row["destination"],
                "flightNumber": row["flight_number"],
                "date": row["date"],
                "time": row["time"],
                "passengers": row["passengers"],
                "duration": row["duration"],
                "notes": row["notes"],
                "price": float(row["price"]) if row["price"] else 0,
                "paymentMethod": row.get("payment_method", ""),
                "paymentStatus": row.get("payment_status", "pending"),
                "status": row["status"],
                "vehicleUnitId": row.get("vehicle_unit_id"),
                "bufferMinutes": row.get("buffer_minutes") if row.get("buffer_minutes") is not None else 45,
                "estimatedDurationMinutes": row.get("estimated_duration_minutes"),
                "pickupLat": float(row["pickup_lat"]) if row.get("pickup_lat") is not None else None,
                "pickupLng": float(row["pickup_lng"]) if row.get("pickup_lng") is not None else None,
                "dropoffLat": float(row["dropoff_lat"]) if row.get("dropoff_lat") is not None else None,
                "dropoffLng": float(row["dropoff_lng"]) if row.get("dropoff_lng") is not None else None,
                "distanceKm": float(row["distance_km"]) if row.get("distance_km") is not None else None,
                "isManual": row.get("is_manual", False),
                "customerId": row.get("customer_id"),
                "currency": row.get("currency") or "TRY",
                "paymentLink": row.get("payment_link") or "",
                "stripePaymentIntentId": row.get("stripe_payment_intent_id") or "",
                "garantiOrderId": row.get("garanti_order_id") or "",
                "childCount": row.get("child_count") if row.get("child_count") is not None else 0,
                "needsChildSeat": bool(row.get("needs_child_seat", False)),
                "createdAt": row["created_at"].isoformat() if row["created_at"] else "",
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else "",
            })
        return result
    except Exception as e:
        print(f"[!] DB rezervasyon yükleme hatası: {e}")
        return None


def save_reservation_to_db(reservation):
    """Yeni rezervasyonu veritabanına ekle. Eklenen kaydın id'sini döndür."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO reservations
                        (type, customer_name, customer_phone, customer_email, pickup, destination,
                         flight_number, date, time, passengers, duration, notes, price,
                         payment_method, payment_status, status,
                         vehicle_unit_id, buffer_minutes, estimated_duration_minutes,
                         pickup_lat, pickup_lng, dropoff_lat, dropoff_lng, distance_km, is_manual,
                         customer_id, currency, payment_link, stripe_payment_intent_id,
                         child_count, needs_child_seat)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s)
                    RETURNING id
                """, (
                    reservation.get("type", "transfer"),
                    reservation.get("customerName", ""),
                    reservation.get("customerPhone", ""),
                    reservation.get("customerEmail", ""),
                    reservation.get("pickup", ""),
                    reservation.get("destination", ""),
                    reservation.get("flightNumber", ""),
                    reservation.get("date", ""),
                    reservation.get("time", ""),
                    _coerce_passenger_count(reservation.get("passengers", 1)),
                    reservation.get("duration", ""),
                    reservation.get("notes", ""),
                    reservation.get("price", 0),
                    reservation.get("paymentMethod", ""),
                    reservation.get("paymentStatus", "pending"),
                    reservation.get("status", "pending"),
                    reservation.get("vehicleUnitId"),
                    reservation.get("bufferMinutes", 45),
                    reservation.get("estimatedDurationMinutes"),
                    reservation.get("pickupLat"),
                    reservation.get("pickupLng"),
                    reservation.get("dropoffLat"),
                    reservation.get("dropoffLng"),
                    reservation.get("distanceKm"),
                    reservation.get("isManual", False),
                    reservation.get("customerId"),
                    reservation.get("currency", "TRY"),
                    reservation.get("paymentLink", ""),
                    reservation.get("stripePaymentIntentId", ""),
                    _coerce_passenger_count(reservation.get("childCount", 0), default=0),
                    bool(reservation.get("needsChildSeat", False)),
                ))
                new_id = cur.fetchone()["id"]
        conn.close()
        return new_id
    except Exception as e:
        print(f"[!] DB rezervasyon kaydetme hatası: {e}")
        return None


def update_reservation_status_in_db(res_id, new_status):
    """Rezervasyon durumunu güncelle."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE reservations
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_status, res_id))
                return cur.rowcount > 0
        conn.close()
    except Exception as e:
        print(f"[!] DB durum güncelleme hatası: {e}")
        return False


def _reservations_file():
    """Rezervasyon JSON dosyasının yolunu döndür."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "reservations.json")


def _delete_reservation_from_json(res_id):
    """JSON dosyasından rezervasyon sil. Bulunduysa True döndür."""
    rfile = _reservations_file()
    if not os.path.exists(rfile):
        return False
    try:
        with open(rfile, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("reservations", [])
        new_items = [r for r in items if r.get("id") != res_id]
        if len(new_items) == len(items):
            return False
        data["reservations"] = new_items
        with open(rfile, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[!] JSON rezervasyon silme hatası: {e}")
        return False


def delete_reservation_from_db(res_id):
    """Rezervasyonu veritabanından sil. PostgreSQL yoksa/yetki yoksa JSON fallback."""
    if not HAS_PSYCOPG2:
        return _delete_reservation_from_json(res_id)
    try:
        conn = get_conn()
        if not conn:
            return _delete_reservation_from_json(res_id)
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM reservations WHERE id = %s", (res_id,))
                return cur.rowcount > 0
        conn.close()
    except Exception as e:
        print(f"[!] DB silme hatası: {e}")
        return _delete_reservation_from_json(res_id)


def update_reservation_in_db(res_id, fields):
    """Rezervasyon alanlarını güncelle. fields dict içinde güncellenecek alanlar."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        field_map = {
            "customerName": "customer_name",
            "customerPhone": "customer_phone",
            "customerEmail": "customer_email",
            "pickup": "pickup",
            "destination": "destination",
            "flightNumber": "flight_number",
            "date": "date",
            "time": "time",
            "passengers": "passengers",
            "duration": "duration",
            "notes": "notes",
            "price": "price",
            "type": "type",
            "status": "status",
            "paymentMethod": "payment_method",
            "paymentStatus": "payment_status",
            "vehicleUnitId": "vehicle_unit_id",
            "bufferMinutes": "buffer_minutes",
            "estimatedDurationMinutes": "estimated_duration_minutes",
            "pickupLat": "pickup_lat",
            "pickupLng": "pickup_lng",
            "dropoffLat": "dropoff_lat",
            "dropoffLng": "dropoff_lng",
            "distanceKm": "distance_km",
            "isManual": "is_manual",
            "customerId": "customer_id",
            "currency": "currency",
            "paymentLink": "payment_link",
            "stripePaymentIntentId": "stripe_payment_intent_id",
            "garantiOrderId": "garanti_order_id",
            "childCount": "child_count",
            "needsChildSeat": "needs_child_seat",
        }
        set_parts = []
        values = []
        for json_key, db_col in field_map.items():
            if json_key in fields:
                set_parts.append(f"{db_col} = %s")
                val = fields[json_key]
                if json_key == "passengers":
                    val = _coerce_passenger_count(val)
                elif json_key == "childCount":
                    val = _coerce_passenger_count(val, default=0)
                values.append(val)
        if not set_parts:
            return False
        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        values.append(res_id)
        sql = f"UPDATE reservations SET {', '.join(set_parts)} WHERE id = %s"
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(values))
                return cur.rowcount > 0
        conn.close()
    except Exception as e:
        print(f"[!] DB güncelleme hatası: {e}")
        return False


def get_next_reservation_id():
    """Bir sonraki rezervasyon ID'sini al (sequence'dan)."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT nextval('reservations_id_seq')")
                val = cur.fetchone()[0]
        conn.close()
        return val
    except Exception as e:
        print(f"[!] DB sequence hatası: {e}")
        return None


# ─── Customers (VIP CRM Hafızası) ────────────────────────────────────────────────

def _customer_row_to_dict(row):
    return {
        "id": row["id"],
        "name": row.get("name", "") or "",
        "phone": row.get("phone", "") or "",
        "email": row.get("email", "") or "",
        "notes": row.get("notes", "") or "",
        "totalBookings": row.get("total_bookings", 0) or 0,
        "totalSpent": float(row["total_spent"]) if row.get("total_spent") is not None else 0,
        "isVip": row.get("is_vip", False),
        "createdAt": row["created_at"].isoformat() if row.get("created_at") else "",
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else "",
    }


def search_customers(query, limit=8):
    """İsim veya telefona göre müşteri ara (autocomplete için). Boş query'de son eklenenleri döner."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                q = (query or "").strip()
                if q:
                    like = f"%{q}%"
                    cur.execute(
                        "SELECT * FROM customers WHERE name ILIKE %s OR phone ILIKE %s "
                        "ORDER BY is_vip DESC, total_bookings DESC LIMIT %s",
                        (like, like, limit)
                    )
                else:
                    cur.execute("SELECT * FROM customers ORDER BY updated_at DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
        conn.close()
        return [_customer_row_to_dict(r) for r in rows]
    except Exception as e:
        print(f"[!] DB müşteri arama hatası: {e}")
        return None


def get_customer_by_id(customer_id):
    if not HAS_PSYCOPG2 or not customer_id:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
                row = cur.fetchone()
        conn.close()
        return _customer_row_to_dict(row) if row else None
    except Exception as e:
        print(f"[!] DB müşteri okuma hatası: {e}")
        return None


def get_customer_by_phone(phone):
    if not HAS_PSYCOPG2 or not phone:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE phone = %s LIMIT 1", (phone,))
                row = cur.fetchone()
        conn.close()
        return _customer_row_to_dict(row) if row else None
    except Exception as e:
        print(f"[!] DB müşteri okuma hatası: {e}")
        return None


def find_or_create_customer(phone, name, email=""):
    """Telefon numarasına göre müşteri bul, yoksa yeni oluştur. Müşteri dict'ini döner (id dahil)."""
    if not HAS_PSYCOPG2:
        return None
    phone = (phone or "").strip()
    if not phone:
        return None
    try:
        existing = get_customer_by_phone(phone)
        if existing:
            # İsim/e-posta değişmişse (ör. yeni rezervasyonda farklı yazılmış) güncelle
            conn = get_conn()
            if conn:
                with conn:
                    with conn.cursor() as cur:
                        if name and name.strip() and name.strip() != existing["name"]:
                            cur.execute("UPDATE customers SET name = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (name.strip(), existing["id"]))
                        if email and not existing["email"]:
                            cur.execute("UPDATE customers SET email = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (email, existing["id"]))
                conn.close()
            return existing
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO customers (name, phone, email) VALUES (%s, %s, %s) RETURNING *",
                    (name or "", phone, email or "")
                )
                row = cur.fetchone()
        conn.close()
        return _customer_row_to_dict(row)
    except Exception as e:
        print(f"[!] DB müşteri oluşturma hatası: {e}")
        return None


def update_customer(customer_id, fields):
    """Müşteri alanlarını güncelle (name, phone, email, notes, isVip)."""
    if not HAS_PSYCOPG2:
        return False
    field_map = {"name": "name", "phone": "phone", "email": "email", "notes": "notes", "isVip": "is_vip"}
    set_parts, values = [], []
    for json_key, db_col in field_map.items():
        if json_key in fields:
            set_parts.append(f"{db_col} = %s")
            values.append(fields[json_key])
    if not set_parts:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        values.append(customer_id)
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE customers SET {', '.join(set_parts)} WHERE id = %s", tuple(values))
                ok = cur.rowcount > 0
        conn.close()
        return ok
    except Exception as e:
        print(f"[!] DB müşteri güncelleme hatası: {e}")
        return False


def register_customer_booking(customer_id, amount):
    """Bir rezervasyon onaylandığında/tamamlandığında müşterinin total_bookings ve
    total_spent alanlarını artırır. 5+ rezervasyonda otomatik VIP işaretler."""
    if not HAS_PSYCOPG2 or not customer_id:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE customers SET total_bookings = total_bookings + 1, "
                    "total_spent = total_spent + %s, "
                    "is_vip = CASE WHEN total_bookings + 1 >= 5 THEN TRUE ELSE is_vip END, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (amount or 0, customer_id)
                )
                ok = cur.rowcount > 0
        conn.close()
        return ok
    except Exception as e:
        print(f"[!] DB müşteri rezervasyon sayacı güncelleme hatası: {e}")
        return False


# ─── Live Chat Messages (Canlı Destek) ───────────────────────────────────────────

def load_chat_messages_from_db():
    """Tüm sohbet mesajlarını veritabanından yükle (id sırasına göre)."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM chat_messages ORDER BY id ASC")
                rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "sessionId": row.get("session_id") or "",
                "name": row.get("name") or "",
                "phone": row.get("phone") or "",
                "message": row.get("message") or "",
                "isAdmin": bool(row.get("is_admin", False)),
                "adminName": row.get("admin_name") or "",
                "read": bool(row.get("is_read", False)),
                "isNewSession": bool(row.get("is_new_session", False)),
                "timestamp": row["created_at"].isoformat() if row.get("created_at") else "",
            })
        return result
    except Exception as e:
        print(f"[!] DB sohbet mesajları yükleme hatası: {e}")
        return None


def save_chat_message_to_db(msg):
    """Yeni sohbet mesajını veritabanına ekle. Eklenen kaydın id'sini döndür."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO chat_messages
                        (session_id, name, phone, message, is_admin, admin_name, is_read, is_new_session)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    msg.get("sessionId", ""),
                    msg.get("name", ""),
                    msg.get("phone", ""),
                    msg.get("message", ""),
                    msg.get("isAdmin", False),
                    msg.get("adminName", ""),
                    msg.get("read", False),
                    msg.get("isNewSession", False),
                ))
                new_id = cur.fetchone()["id"]
        conn.close()
        return new_id
    except Exception as e:
        print(f"[!] DB sohbet mesajı kaydetme hatası: {e}")
        return None


def mark_chat_session_read_in_db(session_id):
    """Bir oturumdaki ziyaretçi mesajlarını okundu olarak işaretle."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE chat_messages SET is_read = TRUE WHERE session_id = %s AND is_admin = FALSE",
                    (session_id,)
                )
        conn.close()
        return True
    except Exception as e:
        print(f"[!] DB sohbet okundu güncelleme hatası: {e}")
        return False


def delete_chat_message_from_db(message_id, session_id=None):
    """Bir sohbet mesajını sil. session_id verilirse eşleşme ek şart olarak aranır."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                if session_id:
                    cur.execute("DELETE FROM chat_messages WHERE id = %s AND session_id = %s", (message_id, session_id))
                else:
                    cur.execute("DELETE FROM chat_messages WHERE id = %s", (message_id,))
                ok = cur.rowcount > 0
        conn.close()
        return ok
    except Exception as e:
        print(f"[!] DB sohbet mesajı silme hatası: {e}")
        return False


def get_next_chat_id():
    """chat_messages sequence'ından bir sonraki id'yi al (başlangıç sayacı için)."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT nextval('chat_messages_id_seq')")
                val = cur.fetchone()[0]
        conn.close()
        return val
    except Exception as e:
        print(f"[!] DB sohbet sequence hatası: {e}")
        return None


# ─── İletişim Formu Mesajları ─────────────────────────────────────────────────────

def load_contact_messages_from_db():
    """Tüm iletişim formu mesajlarını veritabanından yükle."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM contact_messages ORDER BY id ASC")
                rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "name": row.get("name") or "",
                "phone": row.get("phone") or "",
                "email": row.get("email") or "",
                "message": row.get("message") or "",
                "ipAddress": row.get("ip_address") or "",
                "city": row.get("city") or "",
                "country": row.get("country") or "",
                "region": row.get("region") or "",
                "userAgent": row.get("user_agent") or "",
                "status": row.get("status") or "new",
                "adminNote": row.get("admin_note") or "",
                "timestamp": row["created_at"].isoformat() if row.get("created_at") else "",
            })
        return result
    except Exception as e:
        print(f"[!] DB iletişim mesajları yükleme hatası: {e}")
        return None


def save_contact_message_to_db(contact):
    """Yeni iletişim formu mesajını veritabanına ekle. Eklenen kaydın id'sini döndür."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO contact_messages (name, phone, email, message, ip_address, city, country, region, user_agent, status, admin_note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    contact.get("name", ""),
                    contact.get("phone", ""),
                    contact.get("email", ""),
                    contact.get("message", ""),
                    contact.get("ipAddress", ""),
                    contact.get("city", ""),
                    contact.get("country", ""),
                    contact.get("region", ""),
                    contact.get("userAgent", ""),
                    contact.get("status", "new"),
                    contact.get("adminNote", ""),
                ))
                new_id = cur.fetchone()["id"]
        conn.close()
        return new_id
    except Exception as e:
        print(f"[!] DB iletişim mesajı kaydetme hatası: {e}")
        return None


def update_contact_message_in_db(message_id, fields):
    """Bir iletişim mesajının admin tarafından düzenlenebilir alanlarını güncelle."""
    if not HAS_PSYCOPG2:
        return False
    allowed = {
        "name": "name", "phone": "phone", "email": "email", "message": "message",
        "status": "status", "adminNote": "admin_note",
        "city": "city", "country": "country", "region": "region",
    }
    set_parts = []
    values = []
    for key, col in allowed.items():
        if key in fields:
            set_parts.append(f"{col} = %s")
            values.append(fields[key])
    if not set_parts:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                values.append(message_id)
                cur.execute(f"UPDATE contact_messages SET {', '.join(set_parts)} WHERE id = %s", values)
        conn.close()
        return True
    except Exception as e:
        print(f"[!] DB iletişim mesajı güncelleme hatası: {e}")
        return False


def delete_contact_message_from_db(message_id):
    """Bir iletişim mesajını veritabanından sil."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM contact_messages WHERE id = %s", (message_id,))
        conn.close()
        return True
    except Exception as e:
        print(f"[!] DB iletişim mesajı silme hatası: {e}")
        return False


def get_next_contact_id():
    """contact_messages sequence'ından bir sonraki id'yi al (başlangıç sayacı için)."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT nextval('contact_messages_id_seq')")
                val = cur.fetchone()[0]
        conn.close()
        return val
    except Exception as e:
        print(f"[!] DB iletişim sequence hatası: {e}")
        return None


# ─── Dashboard Bildirimleri ───────────────────────────────────────────────────────

def load_dashboard_notifications_from_db():
    """Son 50 dashboard bildirimini veritabanından yükle (en yeni önce)."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM dashboard_notifications ORDER BY id DESC LIMIT 50")
                rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "type": row.get("ntype") or "info",
                "message": row.get("message") or "",
                "reservationId": row.get("reservation_id"),
                "read": bool(row.get("is_read", False)),
                "createdAt": row["created_at"].isoformat() if row.get("created_at") else "",
            })
        return result
    except Exception as e:
        print(f"[!] DB dashboard bildirimleri yükleme hatası: {e}")
        return None


def save_dashboard_notification_to_db(notif):
    """Yeni dashboard bildirimini veritabanına ekle. Eklenen kaydın id'sini döndür."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO dashboard_notifications (message, ntype, reservation_id, is_read)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (
                    notif.get("message", ""),
                    notif.get("type", "info"),
                    notif.get("reservationId"),
                    notif.get("read", False),
                ))
                new_id = cur.fetchone()["id"]
        conn.close()
        return new_id
    except Exception as e:
        print(f"[!] DB dashboard bildirimi kaydetme hatası: {e}")
        return None


def mark_dashboard_notification_read_in_db(notification_id):
    """Bir dashboard bildirimini okundu olarak işaretle."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE dashboard_notifications SET is_read = TRUE WHERE id = %s", (notification_id,))
                ok = cur.rowcount > 0
        conn.close()
        return ok
    except Exception as e:
        print(f"[!] DB dashboard bildirimi okundu güncelleme hatası: {e}")
        return False


def get_next_dashboard_notification_id():
    """dashboard_notifications sequence'ından bir sonraki id'yi al (başlangıç sayacı için)."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT nextval('dashboard_notifications_id_seq')")
                val = cur.fetchone()[0]
        conn.close()
        return val
    except Exception as e:
        print(f"[!] DB dashboard sequence hatası: {e}")
        return None


# ─── Config (anahtar-değer deposu) ──────────────────────────────────────────────

def get_config(key, default=None):
    """Config tablosundan bir değer oku."""
    if not HAS_PSYCOPG2:
        return default
    try:
        conn = get_conn()
        if not conn:
            return default
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM config WHERE key = %s", (key,))
                row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
        return default
    except Exception as e:
        print(f"[!] Config okuma hatası ({key}): {e}")
        return default


def get_config_safe(key):
    """get_config ile aynı sorguyu yapar ama 'veri yok' ile 'DB'ye hiç
    ulaşılamadı' durumlarını AYIRT EDER — get_config'in ikisini de None
    döndürmesi tehlikeli bir örüntüye yol açıyordu: bazı çağıranlar (örn.
    load_vehicles) 'None döndüyse hiç veri yok, varsayılanları YAZ' mantığı
    kuruyordu. Ama None, DB'nin container yeni başlarken henüz hazır olmadığı
    kısa bir anda da dönebiliyordu — bu durumda gerçek veri hâlâ tabloda
    duruyorken, üzerine varsayılan/demo veri kalıcı olarak yazılıp GERÇEK
    VERİ KAYBOLUYORDU (18 Ağustos'ta filo galeri görsellerinin sıfırlanması
    tam bu senaryoyla açıklandı — birden çok art arda deploy sırasında bir
    container başlangıcında DB'ye erişim anlık aksamış, kod bunu 'veri hiç
    yok' sanıp demo varsayılanı DB'ye geri yazmış).
    Dönüş: (found: bool, value: str|None, db_reachable: bool)"""
    if not HAS_PSYCOPG2:
        return (False, None, False)
    try:
        conn = get_conn()
        if not conn:
            return (False, None, False)
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM config WHERE key = %s", (key,))
                row = cur.fetchone()
        conn.close()
        if row:
            return (True, row[0], True)
        return (False, None, True)
    except Exception as e:
        print(f"[!] Config okuma hatası ({key}): {e}")
        return (False, None, False)


def get_json_config_safe(key):
    """get_config_safe'in JSON'a çevrilmiş hali. Dönüş: (found, value, db_reachable)."""
    found, raw, db_reachable = get_config_safe(key)
    if not found:
        return (False, None, db_reachable)
    try:
        return (True, json.loads(raw), db_reachable)
    except Exception as e:
        print(f"[!] JSON config parse hatası ({key}): {e}")
        return (False, None, db_reachable)


def set_config(key, value):
    """Config tablosuna bir değer yaz (upsert)."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO config (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key)
                    DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
                """, (key, value, value))
        conn.close()
        return True
    except Exception as e:
        print(f"[!] Config yazma hatası ({key}): {e}")
        return False


# ─── Genel JSON Config Blokları (araçlar, fiyatlar, slider görselleri) ──────────
# Küçük, admin panelinden yönetilen listeler/nesneler için: config tablosuna
# tek bir satır olarak JSON serialize edilip yazılır. Yeni bir SQL tablosu
# gerektirmez — vehicles.json, prices.json, slider_images.json gibi dosyaların
# PostgreSQL karşılığı budur.

def get_json_config(key, default=None):
    """config tablosundan bir JSON değeri okuyup Python nesnesine çevirir."""
    raw = get_config(key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[!] JSON config parse hatası ({key}): {e}")
        return default


def set_json_config(key, value):
    """Bir Python nesnesini JSON'a çevirip config tablosuna yazar (upsert)."""
    try:
        raw = json.dumps(value, ensure_ascii=False)
    except Exception as e:
        print(f"[!] JSON config serialize hatası ({key}): {e}")
        return False
    return set_config(key, raw)


# ─── Admin Credentials (JSON fallback) ─────────────────────────────────────────────

def _load_admin_config():
    """admin_config.json dosyasından yönetici bilgilerini yükle."""
    if os.path.exists(ADMIN_CONFIG_FILE):
        try:
            with open(ADMIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Admin config JSON okuma hatası: {e}")
    return {"username": "admin@guliztransfer.com", "password": "Guliz2025!"}


def _save_admin_config(data):
    """Yönetici bilgilerini admin_config.json'a yaz."""
    try:
        with open(ADMIN_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[!] Admin config JSON yazma hatası: {e}")
        return False


def get_admin_user():
    """Admin kullanıcı adını döndürür. Önce PostgreSQL config, yoksa JSON fallback."""
    if HAS_PSYCOPG2:
        val = get_config("admin_user")
        if val:
            return val
    data = _load_admin_config()
    return data.get("username", "admin@guliztransfer.com")


def get_admin_pass():
    """Admin şifresini döndürür. Önce PostgreSQL config, yoksa JSON fallback."""
    if HAS_PSYCOPG2:
        val = get_config("admin_password")
        if val:
            return val
    data = _load_admin_config()
    return data.get("password", "Guliz2025!")


def set_admin_credentials(username, password):
    """Admin kullanıcı adı ve şifresini günceller. PostgreSQL + JSON fallback."""
    if not username or not password:
        return False
    pg_ok = True
    if HAS_PSYCOPG2:
        pg_ok = set_config("admin_user", username)
        pg_ok = set_config("admin_password", password) and pg_ok
    json_ok = _save_admin_config({"username": username, "password": password})
    return pg_ok or json_ok


# ─── Page Content (Dinamik Sayfa Yönetimi) ───────────────────────────────────────

def get_page_content(slug):
    """page_content tablosundan slug'a göre içerik oku. dict veya None döndür."""
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT slug, title, subtitle, content, is_active, updated_at FROM page_content WHERE slug = %s", (slug,))
                row = cur.fetchone()
        conn.close()
        if row:
            return {
                "slug": row["slug"],
                "title": row["title"],
                "subtitle": row.get("subtitle", "") or "",
                "content": row["content"],
                "is_active": row.get("is_active", True) if row.get("is_active") is not None else True,
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else "",
            }
        return None
    except Exception as e:
        print(f"[!] Page content okuma hatası ({slug}): {e}")
        return None


def save_page_content(slug, title, content, subtitle=""):
    """page_content tablosuna slug/title/subtitle/content yaz (upsert)."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO page_content (slug, title, subtitle, content, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (slug)
                    DO UPDATE SET title = %s, subtitle = %s, content = %s, updated_at = CURRENT_TIMESTAMP
                """, (slug, title, subtitle, content, title, subtitle, content))
        conn.close()
        return True
    except Exception as e:
        print(f"[!] Page content yazma hatası ({slug}): {e}")
        return False


def get_all_pages():
    """page_content tablosundaki tüm sayfaları listele. list of dict veya boş liste döndür."""
    if not HAS_PSYCOPG2:
        return []
    try:
        conn = get_conn()
        if not conn:
            return []
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT slug, title, subtitle, is_active, updated_at FROM page_content ORDER BY slug")
                rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "slug": row["slug"],
                "title": row["title"],
                "subtitle": row.get("subtitle", "") or "",
                "is_active": row.get("is_active", True) if row.get("is_active") is not None else True,
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else "",
            })
        return result
    except Exception as e:
        print(f"[!] Page content listeleme hatası: {e}")
        return []


def set_page_active(slug, is_active):
    """page_content'te bir sayfanın is_active durumunu güncelle."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE page_content SET is_active = %s, updated_at = CURRENT_TIMESTAMP WHERE slug = %s", (is_active, slug))
        conn.close()
        return True
    except Exception as e:
        print(f"[!] Page content aktiflik güncelleme hatası ({slug}): {e}")
        return False


# ─── Destinations (Turistik Bölgeler) ────────────────────────────────────────────

# ── JSON fallback helpers ────────────────────────────────────────────────────

def _load_destinations_from_json():
    """destinations.json dosyasından destinasyonları yükle."""
    if not os.path.exists(DESTINATIONS_FILE):
        return []
    try:
        with open(DESTINATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("destinations", [])
    except Exception as e:
        print(f"[!] Destinasyon JSON okuma hatası: {e}")
        return []


def _save_destinations_to_json(destinations):
    """Destinasyon listesini destinations.json'a yaz."""
    try:
        with open(DESTINATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"destinations": destinations}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[!] Destinasyon JSON yazma hatası: {e}")
        return False


def get_destinations(active_only=True):
    """Tüm destinasyonları sıralı şekilde getir. active_only=True ise sadece aktif olanlar."""
    if not HAS_PSYCOPG2:
        items = _load_destinations_from_json()
        if active_only:
            items = [d for d in items if d.get("isActive", True)]
        items.sort(key=lambda d: (d.get("sortOrder", 0), d.get("id", 0)))
        return items
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if active_only:
                    cur.execute("""
                        SELECT * FROM destinations
                        WHERE is_active = TRUE
                        ORDER BY sort_order ASC, id ASC
                    """)
                else:
                    cur.execute("""
                        SELECT * FROM destinations
                        ORDER BY sort_order ASC, id ASC
                    """)
                rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "imageUrl": row["image_url"],
                "slug": row["slug"],
                "sortOrder": row["sort_order"],
                "isActive": row["is_active"],
                "airport": row.get("airport") or "both",
                "galleryImages": row.get("gallery_images") or "",
                "createdAt": row["created_at"].isoformat() if row["created_at"] else "",
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else "",
            })
        return result
    except Exception as e:
        print(f"[!] Destinations okuma hatası: {e}")
        return None


def get_destination(dest_id):
    """ID'ye göre tek bir destinasyon getir."""
    if not HAS_PSYCOPG2:
        items = _load_destinations_from_json()
        for d in items:
            if d.get("id") == dest_id:
                return d
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM destinations WHERE id = %s", (dest_id,))
                row = cur.fetchone()
        conn.close()
        if row:
            return {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "imageUrl": row["image_url"],
                "slug": row["slug"],
                "sortOrder": row["sort_order"],
                "isActive": row["is_active"],
                "airport": row.get("airport") or "both",
                "galleryImages": row.get("gallery_images") or "",
                "createdAt": row["created_at"].isoformat() if row["created_at"] else "",
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else "",
            }
        return None
    except Exception as e:
        print(f"[!] Destination okuma hatası ({dest_id}): {e}")
        return None


def save_destination(data):
    """Yeni destinasyon ekle. Eklenen kaydın id'sini döndür."""
    if not HAS_PSYCOPG2:
        items = _load_destinations_from_json()
        new_id = 1
        if items:
            new_id = max(d.get("id", 0) for d in items) + 1
        now = datetime.utcnow().isoformat()
        entry = {
            "id": new_id,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "imageUrl": data.get("imageUrl", ""),
            "slug": data.get("slug", ""),
            "sortOrder": data.get("sortOrder", 0),
            "isActive": data.get("isActive", True),
            "airport": data.get("airport", "both"),
            "galleryImages": data.get("galleryImages", ""),
            "createdAt": now,
            "updatedAt": now,
        }
        items.append(entry)
        if _save_destinations_to_json(items):
            return new_id
        return None
    try:
        conn = get_conn()
        if not conn:
            return None
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO destinations (name, description, image_url, slug, sort_order, is_active, airport, gallery_images)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    data.get("name", ""),
                    data.get("description", ""),
                    data.get("imageUrl", ""),
                    data.get("slug", ""),
                    data.get("sortOrder", 0),
                    data.get("isActive", True),
                    data.get("airport", "both"),
                    data.get("galleryImages", ""),
                ))
                new_id = cur.fetchone()["id"]
        conn.close()
        return new_id
    except Exception as e:
        print(f"[!] Destination ekleme hatası: {e}")
        return None


def update_destination(dest_id, data):
    """Destinasyon alanlarını güncelle. data dict içinde güncellenecek alanlar."""
    if not HAS_PSYCOPG2:
        items = _load_destinations_from_json()
        updated = False
        for d in items:
            if d.get("id") == dest_id:
                for key in ("name", "description", "imageUrl", "slug", "sortOrder", "isActive", "airport", "galleryImages"):
                    if key in data:
                        d[key] = data[key]
                d["updatedAt"] = datetime.utcnow().isoformat()
                updated = True
                break
        if updated:
            return _save_destinations_to_json(items)
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        field_map = {
            "name": "name",
            "description": "description",
            "imageUrl": "image_url",
            "slug": "slug",
            "sortOrder": "sort_order",
            "isActive": "is_active",
            "airport": "airport",
            "galleryImages": "gallery_images",
        }
        set_parts = []
        values = []
        for json_key, db_col in field_map.items():
            if json_key in data:
                set_parts.append(f"{db_col} = %s")
                values.append(data[json_key])
        if not set_parts:
            return False
        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        values.append(dest_id)
        sql = f"UPDATE destinations SET {', '.join(set_parts)} WHERE id = %s"
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(values))
                return cur.rowcount > 0
        conn.close()
    except Exception as e:
        print(f"[!] Destination güncelleme hatası ({dest_id}): {e}")
        return False


def delete_destination(dest_id):
    """Destinasyonu veritabanından sil."""
    if not HAS_PSYCOPG2:
        items = _load_destinations_from_json()
        items = [d for d in items if d.get("id") != dest_id]
        return _save_destinations_to_json(items)
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM destinations WHERE id = %s", (dest_id,))
                return cur.rowcount > 0
        conn.close()
    except Exception as e:
        print(f"[!] Destination silme hatası ({dest_id}): {e}")
        return False
