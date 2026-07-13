#!/usr/bin/env python3
"""Merge tracking infrastructure into server.py"""
import sys

with open('/tmp/head_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add uuid and socket after 'import db'
content = content.replace(
    'import db  # PostgreSQL modülü',
    'import db  # PostgreSQL modülü\nimport uuid\nimport socket'
)

# 2. Add VISITOR_SESSIONS after BANK_ACCOUNTS dict (before # Telegram bot)
visitor_globals = '''
# ─── Visitor Tracking (Görünmez Ajan) ────────────────────────────────────────
VISITOR_SESSIONS = {}
visitor_lock = threading.Lock()
VISITOR_SESSION_TIMEOUT = 30  # seconds before marking offline
VISITOR_SESSION_CLEANUP = 300  # seconds before removing stale session

'''
content = content.replace(
    '}\n\n# Telegram bot konfigürasyonu',
    '}' + visitor_globals + '# Telegram bot konfigürasyonu'
)

# 3. Insert helper functions between send_telegram() and _classify_flight_type()
helper_funcs = '''

def _get_visitor_ip(handler):
    """Extract real visitor IP from request headers."""
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = handler.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    client, _ = handler.client_address
    return client


def _format_duration(seconds):
    """Format seconds to human-readable duration string."""
    if seconds < 60:
        return f"{int(seconds)}sn"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}d {secs:02d}sn"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}s {mins:02d}d {secs:02d}sn"


def _cleanup_offline_sessions():
    """Remove stale visitor sessions that have been offline too long."""
    now = time.time()
    with visitor_lock:
        stale = []
        for sid, visitor in VISITOR_SESSIONS.items():
            last = visitor.get("lastHeartbeat", 0)
            if last > 0 and (now - last) > VISITOR_SESSION_CLEANUP:
                stale.append(sid)
        for sid in stale:
            del VISITOR_SESSIONS[sid]
        if stale:
            print(f"[tracking] {len(stale)} eski ziyaretçi oturumu temizlendi")


def _send_telegram_visitor_identify(visitor):
    """Send Telegram notification when a visitor is identified."""
    msg = (
        f"\\U0001f441 <b>Görünmez Ajan — Yeni Ziyaretçi</b>\\n"
        f"\\U0001f310 <b>IP:</b> {visitor.get('ip', '?')}\\n"
        f"\\U0001f4cd <b>Konum:</b> {visitor.get('city', '?')}, {visitor.get('country', '?')}\\n"
        f"\\U0001f4f1 <b>Cihaz:</b> {visitor.get('device', '?')} / {visitor.get('os', '?')}\\n"
        f"\\U0001f30d <b>Tarayıcı:</b> {visitor.get('browser', '?')}\\n"
        f"\\U0001f6aa <b>Giriş:</b> {visitor.get('entryPage', '?')}\\n"
        f"\\U0001f517 <b>Yönlendiren:</b> {visitor.get('referrer', 'Doğrudan')}\\n"
        f"\\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}"
    )
    send_telegram(msg)


def _send_telegram_visitor_event(visitor, event):
    """Send Telegram notification for critical visitor events."""
    label = event.get("label", "Bilinmeyen")
    detail = event.get("detail", "")
    page = event.get("page", "?")
    msg = (
        f"⚠️ <b>Ziyaretçi Etkinliği: {label}</b>\\n"
        f"\\U0001f464 <b>IP:</b> {visitor.get('ip', '?')}\\n"
        f"\\U0001f4cd <b>Konum:</b> {visitor.get('city', '?')}, {visitor.get('country', '?')}\\n"
        f"\\U0001f4c4 <b>Sayfa:</b> {page}\\n"
    )
    if detail:
        msg += f"\\U0001f4dd <b>Detay:</b> {detail}\\n"
    msg += f"\\U0001f550 <b>Saat:</b> {datetime.now().isoformat()}"
    send_telegram(msg)


def visitor_cleanup_loop():
    while True:
        time.sleep(15)
        _cleanup_offline_sessions()
'''

content = content.replace(
    '        return False\n\ndef _classify_flight_type(flight):',
    '        return False\n' + helper_funcs + '\ndef _classify_flight_type(flight):'
)

# 4. Add /api/admin/dashboard endpoint after /api/admin/check block in do_GET
dashboard_block = '''

        if path == "/api/admin/dashboard":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            now = time.time()
            online_count = 0
            with visitor_lock:
                for v in VISITOR_SESSIONS.values():
                    last = v.get("lastHeartbeat", 0)
                    if last > 0 and (now - last) < VISITOR_SESSION_TIMEOUT:
                        online_count += 1
            pending = sum(1 for r in RESERVATIONS if r.get("status") == "pending")
            approved = sum(1 for r in RESERVATIONS if r.get("status") == "approved")
            completed = sum(1 for r in RESERVATIONS if r.get("status") == "completed")
            cancelled = sum(1 for r in RESERVATIONS if r.get("status") == "cancelled")
            unread_chat = sum(1 for m in CHAT_MESSAGES if not m.get("read") and not m.get("isAdmin"))
            self._send_json({
                "success": True,
                "stats": {
                    "totalReservations": len(RESERVATIONS),
                    "pending": pending,
                    "approved": approved,
                    "completed": completed,
                    "cancelled": cancelled,
                    "unreadChat": unread_chat,
                    "onlineVisitors": online_count,
                }
            })
            return
'''

content = content.replace(
    '            self._send_json({"success": True, "user": user})\n            else:\n                self._send_json({"success": False}, 401)\n            return\n        if path == "/api/admin/reservations":',
    '            self._send_json({"success": True, "user": user})\n            else:\n                self._send_json({"success": False}, 401)\n            return' + dashboard_block + '        if path == "/api/admin/reservations":'
)

# 5. Add /api/admin/radar and /api/track/location after /api/admin/telegram/config in do_GET
radar_block = '''

        if path == "/api/admin/radar":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            with visitor_lock:
                now = time.time()
                visitors_list = []
                for sid, v in VISITOR_SESSIONS.items():
                    entry_time = v.get("entryTime", 0)
                    last_heartbeat = v.get("lastHeartbeat", 0)
                    elapsed = (now - entry_time) if entry_time else 0
                    online = bool(last_heartbeat and (now - last_heartbeat) < VISITOR_SESSION_TIMEOUT)
                    events = v.get("events", [])
                    last_event = events[-1].get("label", "") if events else ""
                    visitor_data = {
                        "sessionId": sid, "ip": v.get("ip", ""),
                        "city": v.get("city", ""), "country": v.get("country", ""),
                        "region": v.get("region", ""), "device": v.get("device", ""),
                        "os": v.get("os", ""), "browser": v.get("browser", ""),
                        "currentPage": v.get("currentPage", ""), "entryPage": v.get("entryPage", ""),
                        "referrer": v.get("referrer", ""), "entryTime": entry_time,
                        "lastHeartbeat": last_heartbeat, "elapsed": elapsed,
                        "elapsedFormatted": _format_duration(elapsed),
                        "online": online, "duration": _format_duration(elapsed),
                        "lastEvent": last_event, "events": events,
                        "chatName": v.get("chatName", ""), "chatPhone": v.get("chatPhone", ""),
                    }
                    visitors_list.append(visitor_data)
                visitors_list.sort(key=lambda x: x.get("lastHeartbeat", 0), reverse=True)
            self._send_json({"success": True, "visitors": visitors_list, "onlineCount": sum(1 for v in visitors_list if v["online"])})
            return
        if path == "/api/track/location":
            ip = params.get("ip", "")
            if not ip:
                self._send_error("IP parametresi gerekli.", 400)
                return
            try:
                ip_url = f"http://ip-api.com/json/{ip}?fields=status,message,city,region,country,query,lat,lon,isp,org,as,timezone,mobile,proxy"
                req = urllib.request.Request(ip_url, headers={"User-Agent": "GulizVIP/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    geo_data = json.loads(resp.read().decode("utf-8"))
                self._send_json({"success": geo_data.get("status") == "success", "data": geo_data})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
            return
'''

content = content.replace(
    '            self._send_json({"success": True, "config": {"botToken": TELEGRAM_BOT_TOKEN[:8] + "..." if TELEGRAM_BOT_TOKEN else "", "chatId": TELEGRAM_CHAT_ID}})\n            return\n        if path == "/api/chat/messages":',
    '            self._send_json({"success": True, "config": {"botToken": TELEGRAM_BOT_TOKEN[:8] + "..." if TELEGRAM_BOT_TOKEN else "", "chatId": TELEGRAM_CHAT_ID}})\n            return' + radar_block + '        if path == "/api/chat/messages":'
)

# 6. Add tracking POST endpoints before the final 404 in do_POST
tracking_post = '''

        if path == "/api/track/identify":
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                if not session_id:
                    self._send_error("sessionId gerekli.", 400)
                    return
                ip = _get_visitor_ip(self)
                visitor = {
                    "sessionId": session_id,
                    "ip": ip,
                    "device": body.get("device", ""),
                    "os": body.get("os", ""),
                    "browser": body.get("browser", ""),
                    "city": body.get("city", ""),
                    "country": body.get("country", ""),
                    "region": body.get("region", ""),
                    "referrer": body.get("referrer", ""),
                    "entryPage": body.get("entryPage", ""),
                    "currentPage": body.get("entryPage", ""),
                    "entryTime": time.time(),
                    "lastHeartbeat": time.time(),
                    "events": [],
                    "chatName": "",
                    "chatPhone": "",
                }
                with visitor_lock:
                    VISITOR_SESSIONS[session_id] = visitor
                print(f"[tracking] Yeni ziyaretçi: {ip} / {body.get('city', '?')} / {body.get('device', '?')}")
                threading.Thread(target=_send_telegram_visitor_identify, args=(visitor,), daemon=True).start()
                self._send_json({"success": True, "visitorId": session_id})
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/track/heartbeat":
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                if not session_id:
                    self._send_error("sessionId gerekli.", 400)
                    return
                with visitor_lock:
                    if session_id in VISITOR_SESSIONS:
                        VISITOR_SESSIONS[session_id]["lastHeartbeat"] = time.time()
                        if body.get("currentPage"):
                            VISITOR_SESSIONS[session_id]["currentPage"] = body["currentPage"]
                        if body.get("chatName"):
                            VISITOR_SESSIONS[session_id]["chatName"] = body["chatName"]
                        if body.get("chatPhone"):
                            VISITOR_SESSIONS[session_id]["chatPhone"] = body["chatPhone"]
                        self._send_json({"success": True})
                    else:
                        self._send_json({"success": False, "error": "Oturum bulunamadı"}, 404)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/track/event":
            try:
                body = json.loads(self._read_body())
                session_id = body.get("sessionId", "")
                if not session_id:
                    self._send_error("sessionId gerekli.", 400)
                    return
                event = {
                    "label": body.get("label", ""),
                    "detail": body.get("detail", ""),
                    "page": body.get("page", ""),
                    "timestamp": datetime.now().isoformat(),
                    "is_critical": body.get("is_critical", False),
                }
                with visitor_lock:
                    if session_id in VISITOR_SESSIONS:
                        VISITOR_SESSIONS[session_id].setdefault("events", []).append(event)
                        self._send_json({"success": True})
                    else:
                        self._send_json({"success": False, "error": "Oturum bulunamadı"}, 404)
                if body.get("is_critical"):
                    visitor = dict(VISITOR_SESSIONS.get(session_id, {}))
                    threading.Thread(target=_send_telegram_visitor_event, args=(visitor, event), daemon=True).start()
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
        if path == "/api/admin/chat/delete":
            user = self._authenticate()
            if not user:
                self._send_error("Yetkisiz erişim.", 401)
                return
            try:
                body = json.loads(self._read_body())
                message_id = body.get("messageId")
                session_id = body.get("sessionId", "")
                if message_id is None:
                    self._send_error("messageId gerekli.", 400)
                    return
                global CHAT_MESSAGES
                initial_count = len(CHAT_MESSAGES)
                if session_id:
                    CHAT_MESSAGES = [m for m in CHAT_MESSAGES if not (m["id"] == message_id and m.get("sessionId") == session_id)]
                else:
                    CHAT_MESSAGES = [m for m in CHAT_MESSAGES if m["id"] != message_id]
                if len(CHAT_MESSAGES) < initial_count:
                    self._send_json({"success": True, "message": "Mesaj silindi."})
                else:
                    self._send_error("Mesaj bulunamadı.", 404)
            except json.JSONDecodeError:
                self._send_error("Geçersiz JSON.", 400)
            return
'''

content = content.replace(
    '        self._send_error("Bulunamadı", 404)\n\n    def do_PUT(self):',
    tracking_post + '        self._send_error("Bulunamadı", 404)\n\n    def do_PUT(self):'
)

# 7. Add visitor_cleanup thread after scheduler.start()
content = content.replace(
    '    scheduler.start()\n    server.serve_forever()',
    '    scheduler.start()\n    visitor_cleanup = threading.Thread(target=visitor_cleanup_loop, daemon=True)\n    visitor_cleanup.start()\n    server.serve_forever()'
)

# Write the merged file
out_path = '/sessions/tender-wizardly-edison/mnt/gulizvip/server.py'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(content)

lines = content.count('\n') + 1
print(f'Wrote {len(content)} bytes, {lines} lines to {out_path}')
