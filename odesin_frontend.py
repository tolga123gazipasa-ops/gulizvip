base = '/sessions/laughing-charming-albattani/mnt/gulizvip'

with open(base + '/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# ─── 1. submitForm() Odesin redirect ───
anchor1 = "                    if(payload.price) details.push('Tahmini: ' + payload.price + ' ₺');"
anchor2 = "                    document.getElementById('successModal').classList.add('open');"

idx = html.find(anchor1)
if idx < 0:
    print("ERROR: anchor1 not found!")
    exit(1)

# Find the block: from anchor1 line start to anchor2 end
start = html.find('\n', html.rfind('\n', 0, idx)) + 1
end = html.find(anchor2, idx) + len(anchor2)

old_block = html[start:end]
print(f"Found submitForm block at {start}-{end}")

# Build the new block with Odesin redirect inserted before details.push
new_block = (
    "                    // Kredi karti -> Odesin hosted checkout'a yonlendir\n"
    "                    if (payload.paymentMethod === 'kredi_karti' && data.checkout_url) {\n"
    "                        window.location.href = data.checkout_url;\n"
    "                        return;\n"
    "                    }\n"
    "                    // Havale/EFT -> basari modal'ini goster\n"
    "                    details.push('Tahmini: ' + payload.price + ' ₺');\n"
    "                    if(payload.notes) details.push('Not: ' + payload.notes);\n"
    "\n"
    "                    if(summaryEl) {\n"
    "                        summaryEl.innerHTML = details.map(function(d) {\n"
    "                            return '<div style=\"padding:6px 0;border-bottom:1px solid #E2E8F0;font-size:14px;color:#1B2B4C;font-weight:500;\">' + d + '</div>';\n"
    "                        }).join('');\n"
    "                    }\n"
    "                    // --- Görünmez Ajan: rezervasyon başarılı ---\n"
    "                    if (typeof gulizTracker !== 'undefined') {\n"
    "                        gulizTracker.trackEvent('Rezervasyon Tamamlandi', '#' + data.reservation.id + ' | ' + payload.pickup + ' -> ' + (payload.destination || payload.duration || ''), true);\n"
    "                    }\n"
    "                    document.getElementById('successModal').classList.add('open');"
)

html = html[:start] + new_block + html[end:]
print("submitForm() block replaced successfully.")

# ─── 2. Odesin CSS styles ───
css_anchor = "        /* --- CREDIT CARD FORM --- */"
css_idx = html.find(css_anchor)
if css_idx < 0:
    print("ERROR: CSS anchor not found!")
    exit(1)

# Find the end of the card-form CSS block — after .card-type-hint line
aft_anchor = "        .card-type-hint { font-size: 11px; color: #94A3B8; font-weight: 500; margin-top: 4px; }"
aft_idx = html.find(aft_anchor, css_idx)
if aft_idx < 0:
    print("ERROR: .card-type-hint anchor not found!")
    exit(1)

aft_line_end = html.find('\n', aft_idx)
if aft_line_end < 0:
    aft_line_end = len(html)

odesin_css = (
    "\n"
    "        /* --- ODESIN SANAL POS (HOSTED CHECKOUT) --- */\n"
    "        .odesin-payment-info { display: flex; align-items: flex-start; gap: 12px; background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 10px; padding: 16px; margin-bottom: 14px; }\n"
    "        .odesin-payment-icon { flex-shrink: 0; width: 36px; height: 36px; background: #DCFCE7; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; }\n"
    "        .odesin-payment-text { font-size: 13px; line-height: 1.5; color: #166534; }\n"
    "        .odesin-payment-text strong { font-size: 14px; }\n"
    "        .odesin-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }\n"
    "        .odesin-badge { display: inline-flex; align-items: center; gap: 5px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 5px 10px; font-size: 12px; color: #475569; }\n"
)

html = html[:aft_line_end] + odesin_css + html[aft_line_end:]
print("Odesin CSS styles added successfully.")

with open(base + '/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("\nAll changes applied successfully!")
