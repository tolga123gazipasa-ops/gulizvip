#!/usr/bin/env python3
"""
Rebuild server.py from .bak with:
1. CONTACT_MESSAGES globals
2. /api/contact POST handler
3. Fix .bak truncation at end
4. Add __main__ startup block
"""
BAK = '/sessions/laughing-charming-albattani/mnt/gulizvip/server.py.bak'
OUT = '/sessions/laughing-charming-albattani/mnt/gulizvip/server.py'

with open(BAK, 'r', encoding='utf-8') as f:
    c = f.read()

# ─── Fix 1: CONTACT_MESSAGES after CHAT_ID = 1, before Telegram Bot ───
old1 = 'CHAT_ID = 1\n\n# ─── Telegram Bot ────────────────────────────────────────────────'
new1 = 'CHAT_ID = 1\n\n# ─── Contact Form ────────────────────────────────────────────────\nCONTACT_MESSAGES = []\nCONTACT_ID = 1\n\n# ─── Telegram Bot ────────────────────────────────────────────────'
assert c.count(old1) == 1
c = c.replace(old1, new1, 1)
print("[1/4] Added CONTACT_MESSAGES globals")

# ─── Fix 2: Add /api/contact POST handler before do_PUT ───
old2 = '        self._send_error("Bulunamadı", 404)\n\n    def do_PUT(self):'

handler_lines = []
handler_lines.append('')
handler_lines.append('        if path == "/api/contact":')
handler_lines.append('            try:')
handler_lines.append('                body = json.loads(self._read_body())')
handler_lines.append('                name = body.get("name", "").strip()')
handler_lines.append('                phone = body.get("phone", "").strip()')
handler_lines.append('                email = body.get("email", "").strip()')
handler_lines.append('                message = body.get("message", "").strip()')
handler_lines.append('                if not name or not phone or not message:')
handler_lines.append('                    self._send_error("Ad, telefon ve mesaj zorunludur.", 400)')
handler_lines.append('                    return')
handler_lines.append('                global CONTACT_ID, CONTACT_MESSAGES')
handler_lines.append('                contact = {')
handler_lines.append('                    "id": CONTACT_ID,')
handler_lines.append('                    "name": name,')
handler_lines.append('                    "phone": phone,')
handler_lines.append('                    "email": email,')
handler_lines.append('                    "message": message,')
handler_lines.append('                    "timestamp": datetime.now().isoformat()')
handler_lines.append('                }')
handler_lines.append('                CONTACT_MESSAGES.append(contact)')
handler_lines.append('                CONTACT_ID += 1')
handler_lines.append('                tg_msg = "📬 <b>Yeni Iletisim Mesaji</b>\\n"')
handler_lines.append('                tg_msg += "👤 <b>Isim:</b> " + name + "\\n"')
handler_lines.append('                tg_msg += "📞 <b>Telefon:</b> " + phone + "\\n"')
handler_lines.append('                tg_msg += "📧 <b>E-posta:</b> " + (email or "Belirtilmemis") + "\\n"')
handler_lines.append('                tg_msg += "💬 <b>Mesaj:</b> " + (message[:200] + ("..." if len(message) > 200 else "")) + "\\n"')
handler_lines.append('                tg_msg += "🕐 <b>Saat:</b> " + contact["timestamp"]')
handler_lines.append('                send_telegram(tg_msg)')
handler_lines.append('                print(f"[contact] Yeni iletisim formu: {name} / {phone}")')
handler_lines.append('                self._send_json({"success": True, "message": "Mesajiniz alindi."})')
handler_lines.append('            except json.JSONDecodeError:')
handler_lines.append('                self._send_error("Gecersiz JSON.", 400)')
handler_lines.append('            return')
handler_lines.append('        self._send_error("Bulunamadı", 404)')
handler_lines.append('')
handler_lines.append('    def do_PUT(self):')

contact_handler = '\n'.join(handler_lines)

assert c.count(old2) == 1
c = c.replace(old2, contact_handler, 1)
print("[2/4] Added /api/contact POST handler")

# ─── Fix 3: Fix truncation  ───
# The .bak ends mid-function-call: "                    result = db.delete_des"
# We need to replace the ENTIRE truncated line with the complete call
old3 = '                    result = db.delete_des'
new3 = '''                    result = db.delete_destination(dest_id)
                    if result:
                        self._send_json({"success": True, "message": "Destinasyon silindi."})
                    else:
                        self._send_error("Destinasyon silinemedi.", 500)
                else:
                    self._send_error("Gecersiz aksiyon.", 400)
            except json.JSONDecodeError:
                self._send_error("Gecersiz JSON.", 400)
            except Exception as e:
                self._send_error(str(e), 500)
            return
        self._send_error("Bulunamadı", 404)'''

if old3 in c:
    # old3 appears exactly once — the last line of the file
    c = c.replace(old3, new3, 1)
    print("[3/4] Fixed .bak truncation")
else:
    print("[3/4] No truncation found (checking without indent)...")
    # Try with different whitespace
    old3_stripped = 'result = db.delete_des'
    idx = c.rfind(old3_stripped)
    if idx >= 0:
        # Get the full line
        line_start = c.rfind('\n', 0, idx) + 1
        original_line = c[line_start:idx + len(old3_stripped)]
        replacement = '                    result = db.delete_destination(dest_id)\n' \
                      '                    if result:\n' \
                      '                        self._send_json({"success": True, "message": "Destinasyon silindi."})\n' \
                      '                    else:\n' \
                      '                        self._send_error("Destinasyon silinemedi.", 500)\n' \
                      '                else:\n' \
                      '                    self._send_error("Gecersiz aksiyon.", 400)\n' \
                      '            except json.JSONDecodeError:\n' \
                      '                self._send_error("Gecersiz JSON.", 400)\n' \
                      '            except Exception as e:\n' \
                      '                self._send_error(str(e), 500)\n' \
                      '            return\n' \
                      '        self._send_error("Bulunamadı", 404)'
        c = c[:line_start] + replacement
        print("[3/4] Fixed .bak truncation (alt method)")

# ─── Fix 4: Add __main__ startup block ───
if 'server.serve_forever()' not in c:
    c += '''

# ─── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    server = http.server.HTTPServer((HOST, PORT), GulizHandler)
    print(f"[v] Guliz VIP Backend running on http://{HOST}:{PORT}")

    refresh_flights()
    scheduler = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler.start()

    visitor_cleanup = threading.Thread(target=visitor_cleanup_loop, daemon=True)
    visitor_cleanup.start()

    server.serve_forever()
'''
    print("[4/4] Added __main__ startup block")
else:
    print("[4/4] Startup code exists, skipping")

# ─── Write ───
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(c)
print(f"Wrote {len(c)} bytes, {c.count(chr(10))} lines")

# ─── Validate ───
import py_compile, sys
try:
    py_compile.compile(OUT, doraise=True)
    print("PASS: Python syntax valid")
except py_compile.PyCompileError as e:
    print(f"FAIL: {e}")
    sys.exit(1)
