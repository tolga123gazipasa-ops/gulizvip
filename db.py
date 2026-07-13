"""
Güliz VIP — PostgreSQL Veritabanı Modülü
psycopg2-binary ile PostgreSQL bağlantısı, tablo yönetimi, CRUD işlemleri
"""
import os
import json
import time
from datetime import datetime

DESTINATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "destinations.json")
ADMIN_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_config.json")

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
    content TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS destinations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT DEFAULT '',
    image_url VARCHAR(500) DEFAULT '',
    slug VARCHAR(200) DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                         payment_method, payment_status, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    reservation.get("passengers", 1),
                    reservation.get("duration", ""),
                    reservation.get("notes", ""),
                    reservation.get("price", 0),
                    reservation.get("paymentMethod", ""),
                    reservation.get("paymentStatus", "pending"),
                    reservation.get("status", "pending"),
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
        }
        set_parts = []
        values = []
        for json_key, db_col in field_map.items():
            if json_key in fields:
                set_parts.append(f"{db_col} = %s")
                values.append(fields[json_key])
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
                cur.execute("SELECT slug, title, content, updated_at FROM page_content WHERE slug = %s", (slug,))
                row = cur.fetchone()
        conn.close()
        if row:
            return {
                "slug": row["slug"],
                "title": row["title"],
                "content": row["content"],
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else "",
            }
        return None
    except Exception as e:
        print(f"[!] Page content okuma hatası ({slug}): {e}")
        return None


def save_page_content(slug, title, content):
    """page_content tablosuna slug/title/content yaz (upsert)."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO page_content (slug, title, content, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (slug)
                    DO UPDATE SET title = %s, content = %s, updated_at = CURRENT_TIMESTAMP
                """, (slug, title, content, title, content))
        conn.close()
        return True
    except Exception as e:
        print(f"[!] Page content yazma hatası ({slug}): {e}")
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
                    INSERT INTO destinations (name, description, image_url, slug, sort_order, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    data.get("name", ""),
                    data.get("description", ""),
                    data.get("imageUrl", ""),
                    data.get("slug", ""),
                    data.get("sortOrder", 0),
                    data.get("isActive", True),
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
                for key in ("name", "description", "imageUrl", "slug", "sortOrder", "isActive"):
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
