# -*- coding: utf-8 -*-
import re

with open('/sessions/tender-wizardly-edison/mnt/gulizvip/admin.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the renderBankAccounts function
idx_start = content.find('function renderBankAccounts')
if idx_start < 0:
    print("FAIL: renderBankAccounts not found")
    exit(1)

# Find the escapeHtml function to know where renderBankAccounts ends
idx_end = content.find('function escapeHtml', idx_start)
if idx_end < 0:
    print("FAIL: escapeHtml not found")
    exit(1)

old_section = content[idx_start:idx_end]

new_section = '''    function renderBankAccounts(accounts) {
        var container = document.getElementById('bank-accounts-form');
        var html = '';
        var order = ['halkbank', 'vakifbank'];
        var bankLabels = {
            'halkbank': 'Halkbank',
            'vakifbank': 'VakıfBank'
        };
        for(var i = 0; i < order.length; i++) {
            var key = order[i];
            var acct = accounts[key] || {name: '', iban: '', logo: ''};
            var logoUrl = acct.logo || '';
            html += '<div class="panel-section" style="margin-bottom:16px;">' +
                '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">' +
                '<img id="bank-logo-preview-' + key + '" src="' + escapeHtml(logoUrl) + '" style="width:48px;height:48px;object-fit:contain;border-radius:8px;border:1px solid var(--border);padding:4px;background:#fff;" onerror="this.style.display=\\'none\\'" onload="this.style.display=\\'\\'">' +
                '<h4 style="margin:0;font-size:16px;font-weight:700;">' + (bankLabels[key] || key) + '</h4></div>' +
                '<div class="form-row">' +
                '<div class="form-group" style="flex:1;"><label>Banka Adı</label>' +
                '<input type="text" id="bank-name-' + key + '" value="' + escapeHtml(acct.name) + '" style="font-size:15px;font-weight:600;padding:10px 12px;" placeholder="Örn: Halkbank"></div>' +
                '<div class="form-group" style="flex:2;"><label>IBAN</label>' +
                '<input type="text" id="bank-iban-' + key + '" value="' + escapeHtml(acct.iban) + '" style="font-size:14px;font-family:\\'Courier New\\',monospace;letter-spacing:0.5px;padding:10px 12px;" placeholder="TR12 0001 2009 4321 1234 5678 90"></div>' +
                '</div>' +
                '<div class="form-row" style="margin-top:8px;">' +
                '<div class="form-group" style="flex:3;"><label>Logo URL</label>' +
                '<input type="text" id="bank-logo-' + key + '" value="' + escapeHtml(logoUrl) + '" style="font-size:13px;padding:10px 12px;" placeholder="https://example.com/logo.png" oninput="previewBankLogo(\\'' + key + '\\')"></div>' +
                '<div class="form-group" style="flex:0 0 auto;align-self:flex-end;">' +
                '<button class="btn-secondary" style="padding:10px 16px;font-size:13px;" onclick="document.getElementById(\\'bank-logo-upload-' + key + '\\').click()"><i class="fa-solid fa-upload"></i> Yükle</button>' +
                '<input type="file" id="bank-logo-upload-' + key + '" accept="image/png,image/jpeg,image/svg+xml,image/webp" style="display:none;" onchange="uploadBankLogo(\\'' + key + '\\')">' +
                '</div></div></div>';
        }
        container.innerHTML = html;
    }

    function previewBankLogo(key) {
        var url = document.getElementById('bank-logo-' + key).value.trim();
        var img = document.getElementById('bank-logo-preview-' + key);
        if(url) {
            img.src = url;
            img.style.display = '';
        } else {
            img.style.display = 'none';
        }
    }

    function uploadBankLogo(key) {
        var fileInput = document.getElementById('bank-logo-upload-' + key);
        var file = fileInput.files[0];
        if(!file) return;
        var reader = new FileReader();
        reader.onload = function(e) {
            var dataUrl = e.target.result;
            document.getElementById('bank-logo-' + key).value = dataUrl;
            document.getElementById('bank-logo-preview-' + key).src = dataUrl;
            document.getElementById('bank-logo-preview-' + key).style.display = '';
        };
        reader.readAsDataURL(file);
    }

'''

content = content[:idx_start] + new_section + content[idx_end:]

with open('/sessions/tender-wizardly-edison/mnt/gulizvip/admin.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK: renderBankAccounts replaced with logo support")
