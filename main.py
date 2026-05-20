from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import datetime
import random
import string
import os

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS licenses (
        license_key TEXT PRIMARY KEY,
        max_devices INTEGER DEFAULT 1,
        expire_date TEXT,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS activations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT,
        hwid TEXT,
        activated_at TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def generate_key():
    chars = string.ascii_uppercase + string.digits
    return "TOOL-" + ''.join(random.choices(chars, k=8))

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>PUBG License Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; color: #fff; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .login-box { max-width: 400px; margin: 100px auto; background: rgba(255,255,255,0.05); border-radius: 20px; padding: 40px; backdrop-filter: blur(10px); }
        .input-group { margin-bottom: 20px; }
        .input-group input { width: 100%; padding: 12px 15px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 10px; color: white; font-size: 16px; }
        .btn { width: 100%; padding: 12px; background: linear-gradient(90deg, #00d4ff, #7c3aed); border: none; border-radius: 10px; color: white; font-size: 16px; font-weight: bold; cursor: pointer; }
        .dashboard { display: none; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: rgba(255,255,255,0.05); border-radius: 15px; padding: 20px; text-align: center; }
        .stat-card .value { font-size: 32px; font-weight: bold; background: linear-gradient(90deg, #00d4ff, #7c3aed); -webkit-background-clip: text; background-clip: text; color: transparent; }
        .card { background: rgba(255,255,255,0.05); border-radius: 15px; padding: 25px; margin-bottom: 30px; }
        .form-row { display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px; align-items: center; }
        .form-row select, .form-row input { flex: 1; padding: 10px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: white; }
        .unit-select { display: flex; gap: 10px; }
        .unit-btn { padding: 10px 20px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: white; cursor: pointer; }
        .unit-btn.active { background: linear-gradient(90deg, #00d4ff, #7c3aed); }
        .key-item { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px; margin-bottom: 10px; }
        .key-item .key { font-family: monospace; }
        .status { padding: 4px 10px; border-radius: 20px; font-size: 12px; }
        .status.valid { background: #10b981; }
        .status.expired { background: #ef4444; }
        .actions button { background: rgba(255,255,255,0.1); border: none; padding: 5px 10px; border-radius: 5px; color: white; cursor: pointer; margin-left: 5px; }
        .toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 10px; display: none; z-index: 1000; }
        .toast.success { background: #10b981; }
        .toast.error { background: #ef4444; }
        .logout-btn { background: rgba(255,255,255,0.1); border: none; padding: 8px 16px; border-radius: 8px; color: white; cursor: pointer; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div id="loginForm" class="login-box">
            <h2 style="text-align:center; margin-bottom:30px;">🔐 Вход в панель</h2>
            <div class="input-group"><input type="text" id="username" placeholder="Логин"></div>
            <div class="input-group"><input type="password" id="password" placeholder="Пароль"></div>
            <button class="btn" onclick="login()">Войти</button>
        </div>
        <div id="dashboard" class="dashboard">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2>📊 Панель управления</h2>
                <button class="logout-btn" onclick="logout()">🚪 Выйти</button>
            </div>
            <div class="stats">
                <div class="stat-card"><h3>Всего ключей</h3><div class="value" id="totalKeys">0</div></div>
                <div class="stat-card"><h3>Активных</h3><div class="value" id="activeKeys">0</div></div>
                <div class="stat-card"><h3>Просроченных</h3><div class="value" id="expiredKeys">0</div></div>
            </div>
            <div class="card">
                <h3>🎲 Создать ключ</h3>
                <div class="form-row">
                    <div class="unit-select">
                        <button class="unit-btn" data-unit="minutes" onclick="setUnit('minutes')">⏱️ Минуты</button>
                        <button class="unit-btn" data-unit="hours" onclick="setUnit('hours')">⏰ Часы</button>
                        <button class="unit-btn active" data-unit="days" onclick="setUnit('days')">📅 Дни</button>
                    </div>
                </div>
                <div class="form-row" id="valueRow">
                    <select id="timeValue"></select>
                    <span id="unitLabel">дней</span>
                    <select id="keyDevices">
                        <option value="1">1 устройство</option><option value="2">2 устройства</option><option value="3">3 устройства</option><option value="5">5 устройств</option><option value="10">10 устройств</option><option value="0">♾️ Безлимит</option>
                    </select>
                    <button class="btn" onclick="createKey()" style="width:auto; padding:10px 30px;">Создать</button>
                </div>
                <div id="newKeyResult" style="display:none; margin-top:15px; padding:10px; background:rgba(0,0,0,0.3); border-radius:8px; font-family:monospace;"></div>
            </div>
            <div class="card"><h3>📋 Список ключей</h3><div id="keyList"></div></div>
        </div>
    </div>
    <div id="toast" class="toast"></div>
    <script>
        const API = window.location.origin;
        let currentUnit = 'days';
        function setUnit(unit) {
            currentUnit = unit;
            document.querySelectorAll('.unit-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelector(`.unit-btn[data-unit="${unit}"]`).classList.add('active');
            let select = document.getElementById('timeValue');
            let label = document.getElementById('unitLabel');
            if (unit === 'minutes') { select.innerHTML = '<option value="1">1</option><option value="5">5</option><option value="10">10</option><option value="15">15</option><option value="30">30</option><option value="45">45</option><option value="60">60</option>'; label.textContent = 'минут'; }
            else if (unit === 'hours') { select.innerHTML = '<option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="6">6</option><option value="12">12</option><option value="24">24</option>'; label.textContent = 'часов'; }
            else { select.innerHTML = '<option value="1">1</option><option value="3">3</option><option value="7">7</option><option value="14">14</option><option value="30" selected>30</option><option value="60">60</option><option value="90">90</option><option value="180">180</option><option value="365">365</option>'; label.textContent = 'дней'; }
        }
        function showToast(msg, type) { let t=document.getElementById('toast'); t.textContent=msg; t.className='toast '+type; t.style.display='block'; setTimeout(()=>t.style.display='none',3000); }
        async function login() { let user=document.getElementById('username').value, pass=document.getElementById('password').value; if(user==='Admin' && pass==='LICENSEKEY122') { localStorage.setItem('loggedIn','true'); document.getElementById('loginForm').style.display='none'; document.getElementById('dashboard').style.display='block'; loadStats(); loadKeys(); showToast('Успешный вход!','success'); } else showToast('Неверный логин или пароль!','error'); }
        function logout() { localStorage.removeItem('loggedIn'); document.getElementById('loginForm').style.display='block'; document.getElementById('dashboard').style.display='none'; }
        async function loadStats() { let res=await fetch(API+'/api/stats'); let data=await res.json(); document.getElementById('totalKeys').innerText=data.total; document.getElementById('activeKeys').innerText=data.active; document.getElementById('expiredKeys').innerText=data.expired; }
        async function loadKeys() { let res=await fetch(API+'/api/licenses'); let keys=await res.json(); let container=document.getElementById('keyList'); if(keys.length===0) { container.innerHTML='<div style="text-align:center;padding:20px;color:#888;">Нет ключей</div>'; return; } container.innerHTML=keys.map(k=>{ let devicesText = k.max_devices === 0 ? '♾️ Безлимит' : k.max_devices + ' уст'; return `<div class="key-item"><div><div class="key">🔑 ${k.license_key}</div><div style="font-size:12px;color:#888;">До ${k.expire_date} | ${devicesText}</div></div><div><span class="status ${k.expire_date>=new Date().toISOString().split('T')[0]?'valid':'expired'}">${k.expire_date>=new Date().toISOString().split('T')[0]?'Активен':'Просрочен'}</span><div class="actions"><button onclick="copyKey('${k.license_key}')">📋</button><button onclick="deleteKey('${k.license_key}')">🗑</button></div></div></div>`; }).join(''); }
        async function createKey() { let value = parseInt(document.getElementById('timeValue').value); let devices = parseInt(document.getElementById('keyDevices').value); let unit = currentUnit; let res=await fetch(API+'/api/licenses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:value, unit:unit, devices:devices})}); let data=await res.json(); let unitText = {minutes:'минут', hours:'часов', days:'дней'}[unit]; let devicesText = devices === 0 ? '♾️ Безлимит' : devices + ' устройств'; document.getElementById('newKeyResult').innerHTML=`✅ Ключ создан!<br>🔑 ${data.key}<br>⏱️ ${value} ${unitText}<br>💻 ${devicesText}<br>⏰ До ${data.expire}`; document.getElementById('newKeyResult').style.display='block'; setTimeout(()=>document.getElementById('newKeyResult').style.display='none',5000); loadStats(); loadKeys(); showToast('Ключ создан!','success'); }
        function copyKey(key) { navigator.clipboard.writeText(key); showToast('Ключ скопирован!','success'); }
        async function deleteKey(key) { if(confirm(`Удалить ${key}?`)) { await fetch(API+'/api/licenses/'+key,{method:'DELETE'}); loadStats(); loadKeys(); showToast('Ключ удален','success'); } }
        setUnit('days');
        if(localStorage.getItem('loggedIn')==='true') { document.getElementById('loginForm').style.display='none'; document.getElementById('dashboard').style.display='block'; loadStats(); loadKeys(); }
    </script>
</body>
</html>
'''

init_db()

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/check')
def check_license():
    key = request.args.get('key')
    hwid = request.args.get('hwid', 'unknown')
    if not key: return "ERROR", 400
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT max_devices, expire_date FROM licenses WHERE license_key = ?", (key,))
    result = c.fetchone()
    if not result: conn.close(); return "INVALID"
    max_devices, expire_date = result
    if datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") > expire_date: conn.close(); return "EXPIRED"
    c.execute("SELECT COUNT(*) FROM activations WHERE license_key = ?", (key,))
    count = c.fetchone()[0]
    c.execute("SELECT * FROM activations WHERE license_key = ? AND hwid = ?", (key, hwid))
    exists = c.fetchone()
    if exists: conn.close(); return "VALID"
    elif max_devices == 0 or count < max_devices:
        c.execute("INSERT INTO activations (license_key, hwid, activated_at) VALUES (?, ?, ?)", (key, hwid, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close(); return "ACTIVATED"
    else: conn.close(); return "DEVICE_LIMIT"

@app.route('/api/stats')
def get_stats():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM licenses")
    total = c.fetchone()[0]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT COUNT(*) FROM licenses WHERE expire_date >= ?", (now,))
    active = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM licenses WHERE expire_date < ?", (now,))
    expired = c.fetchone()[0]
    conn.close()
    return jsonify({"total": total, "active": active, "expired": expired})

@app.route('/api/licenses', methods=['GET'])
def get_licenses():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("SELECT license_key, max_devices, expire_date, created_at FROM licenses ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"license_key": r[0], "max_devices": r[1], "expire_date": r[2], "created_at": r[3]} for r in rows])

@app.route('/api/licenses', methods=['POST'])
def create_license():
    data = request.json
    value = data.get('value', 30)
    unit = data.get('unit', 'days')
    devices = data.get('devices', 1)
    key = generate_key()
    if unit == 'minutes': expire_date = (datetime.datetime.now() + datetime.timedelta(minutes=value)).strftime("%Y-%m-%d %H:%M:%S")
    elif unit == 'hours': expire_date = (datetime.datetime.now() + datetime.timedelta(hours=value)).strftime("%Y-%m-%d %H:%M:%S")
    else: expire_date = (datetime.datetime.now() + datetime.timedelta(days=value)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("INSERT INTO licenses (license_key, max_devices, expire_date, created_at) VALUES (?, ?, ?, ?)", (key, devices, expire_date, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return jsonify({"key": key, "expire": expire_date})

@app.route('/api/licenses/<key>', methods=['DELETE'])
def delete_license(key):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute("DELETE FROM licenses WHERE license_key = ?", (key,))
    c.execute("DELETE FROM activations WHERE license_key = ?", (key,))
    conn.commit()
    conn.close()
    return "OK"

if __name__ == '__main__':
    init_db()
    print("🚀 Сервер запущен!")
    app.run(host='0.0.0.0', port=8080)
