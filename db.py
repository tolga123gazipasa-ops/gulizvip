"""
Güliz VIP — PostgreSQL Veritabanı Modülü
psycopg2-binary ile PostgreSQL bağlantısı, tablo yönetimi, CRUD işlemleri
"""
import os
import json
import time

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
    pickup VARCHAR(500) NOT NULL,
    destination VARCHAR(500) DEFAULT '',
    flight_number VARCHAR(50) DEFAULT '',
    date VARCHAR(20) DEFAULT '',
    time VARCHAR(20) DEFAULT '',
    passengers INTEGER DEFAULT 1,
    duration VARCHAR(100) DEFAULT '',
    notes TEXT DEFAULT '',
    price DECIMAL(10,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
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
                "pickup": row["pickup"],
                "destination": row["destination"],
                "flightNumber": row["flight_number"],
                "date": row["date"],
                "time": row["time"],
                "passengers": row["passengers"],
                "duration": row["duration"],
                "notes": row["notes"],
                "price": float(row["price"]) if row["price"] else 0,
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
                        (type, customer_name, customer_phone, pickup, destination,
                         flight_number, date, time, passengers, duration, notes, price, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    reservation.get("type", "transfer"),
                    reservation.get("customerName", ""),
                    reservation.get("customerPhone", ""),
                    reservation.get("pickup", ""),
                    reservation.get("destination", ""),
                    reservation.get("flightNumber", ""),
                    reservation.get("date", ""),
                    reservation.get("time", ""),
                    reservation.get("passengers", 1),
                    reservation.get("duration", ""),
                    reservation.get("notes", ""),
                    reservation.get("price", 0),
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


def delete_reservation_from_db(res_id):
    """Rezervasyonu veritabanından sil."""
    if not HAS_PSYCOPG2:
        return False
    try:
        conn = get_conn()
        if not conn:
            return False
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM reservations WHERE id = %s", (res_id,))
                return cur.rowcount > 0
        conn.close()
    except Exception as e:
        print(f"[!] DB silme hatası: {e}")
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
