from flask import Flask, request, jsonify
import requests
import secrets
import string
from datetime import datetime, timedelta
import json
import os
import time
import hashlib

app = Flask(__name__)

# ========== КОНФИГ ==========
BOT_TOKEN = "8506004079:AAGaXmW_Av460lTLCI2vpCwkR_BpJuTKDTc"
ADMIN_IDS = [8264651597]

# Хранилище
licenses = []
users = []
admins = []
temp_data = {}
license_logs = []
online_users = {}

# ========== ЛИЦЕНЗИИ ==========
def generate_key(time_value, time_unit):
    if time_unit == "days":
        suffix = f"{time_value}D"
    elif time_unit == "hours":
        suffix = f"{time_value}H"
    elif time_unit == "minutes":
        suffix = f"{time_value}M"
    else:
        suffix = "1D"
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    return f"AsolMod-{suffix}-{random_part}"

def add_license(key, devices, time_value, time_unit, expires_at, admin_id, admin_name):
    licenses.append({
        'key': key.upper().strip(),
        'devices_limit': devices,
        'is_unlimited': devices is None,
        'time_value': time_value,
        'time_unit': time_unit,
        'created_at': datetime.now().isoformat(),
        'expires_at': expires_at.isoformat(),
        'status': 'active',
        'created_by': str(admin_id),
        'created_by_name': admin_name,
        'hwid': None,
        'hwids': [],
        'attempts': [],
        'users_used': [],
        'frozen': False,
        'frozen_until': None,
        'last_used': None
    })

def get_all_licenses():
    return licenses

def get_license_info(key):
    key_upper = key.upper().strip()
    for lic in licenses:
        if lic['key'] == key_upper:
            return lic
    return None

def check_license(key, hwid=None, user_id=None, username=None, ip=None):
    key_upper = key.upper().strip()
    
    for lic in licenses:
        if lic['key'] == key_upper:
            attempt = {
                'timestamp': datetime.now().isoformat(),
                'hwid': hwid,
                'user_id': user_id,
                'username': username,
                'ip': ip,
                'success': False
            }
            lic['attempts'].append(attempt)
            
            if lic['status'] == 'blocked':
                return "BLOCKED"
            
            if lic['status'] == 'frozen':
                if lic.get('frozen_until'):
                    frozen_until = datetime.fromisoformat(lic['frozen_until'])
                    if datetime.now() < frozen_until:
                        return f"FROZEN_UNTIL_{frozen_until.timestamp()}"
                    else:
                        lic['status'] = 'active'
                        lic['frozen'] = False
                        lic['frozen_until'] = None
                else:
                    return "FROZEN"
            
            expires_at = datetime.fromisoformat(lic['expires_at'])
            if expires_at < datetime.now():
                return "EXPIRED"
            
            if lic.get('is_unlimited', False):
                db_hwids = lic.get('hwids', [])
                if hwid:
                    if hwid not in db_hwids:
                        lic['hwids'].append(hwid)
                    if user_id and user_id not in [u.get('user_id') for u in lic['users_used']]:
                        lic['users_used'].append({
                            'user_id': user_id,
                            'username': username,
                            'first_used': datetime.now().isoformat(),
                            'last_used': datetime.now().isoformat(),
                            'hwid': hwid,
                            'ip': ip
                        })
                    else:
                        for u in lic['users_used']:
                            if u.get('user_id') == user_id:
                                u['last_used'] = datetime.now().isoformat()
                attempt['success'] = True
                lic['last_used'] = datetime.now().isoformat()
                return "ACTIVATED"
            
            db_hwid = lic.get('hwid')
            if hwid and db_hwid and db_hwid != hwid:
                attempt['success'] = False
                return "INVALID"
            if hwid and not db_hwid:
                lic['hwid'] = hwid
                if user_id and user_id not in [u.get('user_id') for u in lic['users_used']]:
                    lic['users_used'].append({
                        'user_id': user_id,
                        'username': username,
                        'first_used': datetime.now().isoformat(),
                        'last_used': datetime.now().isoformat(),
                        'hwid': hwid,
                        'ip': ip
                    })
                else:
                    for u in lic['users_used']:
                        if u.get('user_id') == user_id:
                            u['last_used'] = datetime.now().isoformat()
            attempt['success'] = True
            lic['last_used'] = datetime.now().isoformat()
            return "ACTIVATED"
    return "INVALID"

def freeze_license(key, hours=None):
    key_upper = key.upper().strip()
    for lic in licenses:
        if lic['key'] == key_upper:
            if lic['status'] == 'blocked':
                return False, "Ключ заблокирован"
            lic['status'] = 'frozen'
            lic['frozen'] = True
            if hours:
                lic['frozen_until'] = (datetime.now() + timedelta(hours=hours)).isoformat()
            else:
                lic['frozen_until'] = None
            return True, "Заморожен" + (f" до {hours}ч" if hours else " навсегда")
    return False, "Ключ не найден"

def unfreeze_license(key):
    key_upper = key.upper().strip()
    for lic in licenses:
        if lic['key'] == key_upper:
            lic['status'] = 'active'
            lic['frozen'] = False
            lic['frozen_until'] = None
            return True
    return False

def block_license(key):
    key_upper = key.upper().strip()
    for lic in licenses:
        if lic['key'] == key_upper:
            lic['status'] = 'blocked'
            return True
    return False

def unblock_license(key):
    key_upper = key.upper().strip()
    for lic in licenses:
        if lic['key'] == key_upper:
            lic['status'] = 'active'
            return True
    return False

def reset_license(key):
    key_upper = key.upper().strip()
    for lic in licenses:
        if lic['key'] == key_upper:
            if lic.get('is_unlimited', False):
                lic['hwids'] = []
            else:
                lic['hwid'] = None
            lic['attempts'] = []
            lic['users_used'] = []
            now = datetime.now()
            if lic['time_unit'] == "minutes":
                expires = now + timedelta(minutes=lic['time_value'])
            elif lic['time_unit'] == "hours":
                expires = now + timedelta(hours=lic['time_value'])
            else:
                expires = now + timedelta(days=lic['time_value'])
            lic['expires_at'] = expires.isoformat()
            lic['status'] = 'active'
            lic['frozen'] = False
            lic['frozen_until'] = None
            return True
    return False

def delete_license(key):
    global licenses
    key_upper = key.upper().strip()
    licenses = [l for l in licenses if l['key'] != key_upper]

def get_license_stats(key):
    lic = get_license_info(key)
    if not lic:
        return None
    return {
        'devices': len(lic.get('hwids', [])) if lic.get('is_unlimited', False) else (1 if lic.get('hwid') else 0),
        'users': len(lic.get('users_used', [])),
        'attempts': len(lic.get('attempts', [])),
        'is_activated': bool(lic.get('hwid') or lic.get('hwids', [])),
        'is_frozen': lic.get('frozen', False),
        'status': lic.get('status', 'active')
    }

# ========== ПОЛЬЗОВАТЕЛИ ==========
def save_user_info(user_id, username, first_name, last_name, ip_address, hwid, key_used, user_agent):
    now = datetime.now().isoformat()
    
    online_users[user_id] = now
    
    for user in users:
        if user.get('user_id') == user_id:
            user['username'] = username
            user['first_name'] = first_name
            user['last_name'] = last_name
            user['ip_address'] = ip_address
            user['key_used'] = key_used
            user['last_seen'] = now
            user['request_count'] = user.get('request_count', 0) + 1
            user['user_agent'] = user_agent
            user['is_online'] = True
            return
    
    users.append({
        'user_id': user_id,
        'username': username,
        'first_name': first_name,
        'last_name': last_name,
        'ip_address': ip_address,
        'hwid': hwid,
        'key_used': key_used,
        'first_seen': now,
        'last_seen': now,
        'request_count': 1,
        'user_agent': user_agent,
        'is_blocked': 0,
        'is_online': True
    })

def get_all_users():
    now = datetime.now()
    for user in users:
        last_seen = datetime.fromisoformat(user['last_seen'])
        if (now - last_seen).total_seconds() > 300:
            user['is_online'] = False
        else:
            user['is_online'] = True
    return users

def get_online_count():
    users = get_all_users()
    online_count = sum(1 for user in users if user.get('is_online', False))
    return online_count

def block_user(index):
    if index < len(users):
        users[index]['is_blocked'] = 1
        return True
    return False

def unblock_user(index):
    if index < len(users):
        users[index]['is_blocked'] = 0
        return True
    return False

# ========== АДМИНЫ ==========
def is_admin(user_id):
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        return False
    
    if user_id_int in ADMIN_IDS:
        return True
    
    for admin in admins:
        try:
            if int(admin.get('user_id', 0)) == user_id_int:
                return True
        except (ValueError, TypeError):
            continue
    return False

def add_admin(user_id, added_by, username):
    admins.append({
        'user_id': str(user_id),
        'added_by': str(added_by),
        'added_at': datetime.now().isoformat(),
        'username': username
    })

def remove_admin(user_id):
    global admins
    admins = [a for a in admins if a['user_id'] != str(user_id)]

def get_all_admins():
    return admins

# ========== TELEGRAM ФУНКЦИИ ==========
def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")

def edit_message(chat_id, message_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Edit error: {e}")

def answer_callback(callback_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
    except:
        pass

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🎲 Случайный ключ", "callback_data": "gen_random"}],
            [{"text": "✏️ Свой ключ", "callback_data": "gen_custom"}],
            [{"text": "📋 Список ключей", "callback_data": "list_keys"}],
            [{"text": "👥 Юзеры", "callback_data": "show_users"}],
            [{"text": "👑 Админы", "callback_data": "show_admins"}],
            [{"text": "🔄 Сбросить ключ", "callback_data": "reset_key"}],
            [{"text": "❌ Удалить ключ", "callback_data": "delete_key"}],
            [{"text": "📊 Статистика", "callback_data": "stats"}]
        ]
    }

def get_license_detail_keyboard(key):
    return {
        "inline_keyboard": [
            [{"text": "❄️ Заморозить", "callback_data": f"freeze_{key}"},
             {"text": "🔥 Разморозить", "callback_data": f"unfreeze_{key}"}],
            [{"text": "🔒 Заблокировать", "callback_data": f"block_{key}"},
             {"text": "🔓 Разблокировать", "callback_data": f"unblock_{key}"}],
            [{"text": "🔄 Сбросить", "callback_data": f"reset_{key}"}],
            [{"text": "📊 Статистика", "callback_data": f"stats_{key}"}],
            [{"text": "🔙 Назад к списку", "callback_data": "list_keys"}]
        ]
    }

def get_freeze_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "1 час", "callback_data": "freeze_1"},
             {"text": "3 часа", "callback_data": "freeze_3"},
             {"text": "6 часов", "callback_data": "freeze_6"}],
            [{"text": "12 часов", "callback_data": "freeze_12"},
             {"text": "24 часа", "callback_data": "freeze_24"},
             {"text": "48 часов", "callback_data": "freeze_48"}],
            [{"text": "♾️ Навсегда", "callback_data": "freeze_forever"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_main"}]
        ]
    }

def get_time_type_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📅 Дни", "callback_data": "time_days"}, {"text": "⏰ Часы", "callback_data": "time_hours"}],
            [{"text": "⏱️ Минуты", "callback_data": "time_minutes"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_main"}]
        ]
    }

def get_days_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "1 день", "callback_data": "val_1_days"}, {"text": "3 дня", "callback_data": "val_3_days"}, {"text": "7 дней", "callback_data": "val_7_days"}],
            [{"text": "14 дней", "callback_data": "val_14_days"}, {"text": "30 дней", "callback_data": "val_30_days"}, {"text": "60 дней", "callback_data": "val_60_days"}],
            [{"text": "90 дней", "callback_data": "val_90_days"}, {"text": "180 дней", "callback_data": "val_180_days"}, {"text": "365 дней", "callback_data": "val_365_days"}],
            [{"text": "✏️ Своё значение", "callback_data": "custom_days"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_time"}]
        ]
    }

def get_hours_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "1 час", "callback_data": "val_1_hours"}, {"text": "3 часа", "callback_data": "val_3_hours"}, {"text": "6 часов", "callback_data": "val_6_hours"}],
            [{"text": "12 часов", "callback_data": "val_12_hours"}, {"text": "24 часа", "callback_data": "val_24_hours"}, {"text": "48 часов", "callback_data": "val_48_hours"}],
            [{"text": "72 часа", "callback_data": "val_72_hours"}, {"text": "168 часов", "callback_data": "val_168_hours"}],
            [{"text": "✏️ Своё значение", "callback_data": "custom_hours"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_time"}]
        ]
    }

def get_minutes_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "5 минут", "callback_data": "val_5_minutes"}, {"text": "10 минут", "callback_data": "val_10_minutes"}, {"text": "15 минут", "callback_data": "val_15_minutes"}],
            [{"text": "30 минут", "callback_data": "val_30_minutes"}, {"text": "45 минут", "callback_data": "val_45_minutes"}, {"text": "60 минут", "callback_data": "val_60_minutes"}],
            [{"text": "90 минут", "callback_data": "val_90_minutes"}, {"text": "120 минут", "callback_data": "val_120_minutes"}],
            [{"text": "✏️ Своё значение", "callback_data": "custom_minutes"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_time"}]
        ]
    }

def get_devices_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "1 устройство", "callback_data": "dev_1"}, {"text": "2 устройства", "callback_data": "dev_2"}, {"text": "3 устройства", "callback_data": "dev_3"}],
            [{"text": "5 устройств", "callback_data": "dev_5"}, {"text": "10 устройств", "callback_data": "dev_10"}, {"text": "20 устройств", "callback_data": "dev_20"}],
            [{"text": "♾️ Безлимит", "callback_data": "dev_unlimited"}],
            [{"text": "✏️ Своё значение", "callback_data": "custom_devices"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_time"}]
        ]
    }

def get_keys_list_keyboard(keys, page=0):
    keyboard = []
    per_page = 10
    start = page * per_page
    
    if not keys or not isinstance(keys, list):
        return {"inline_keyboard": [[{"text": "❌ Ошибка", "callback_data": "back_to_main"}]]}
    
    sorted_keys = sorted(keys, key=lambda x: (
        0 if x.get('status', '') == 'active' else (1 if x.get('status', '') == 'frozen' else 2)
    ))
    
    for lic in sorted_keys[start:start+per_page]:
        key = lic.get('key', 'UNKNOWN')
        devices = "♾️" if lic.get('is_unlimited', False) else lic.get('devices_limit', 0)
        expires = lic.get('expires_at', '')[:10]
        
        status_icon = {
            'active': '✅',
            'frozen': '❄️',
            'blocked': '🔴'
        }.get(lic.get('status', ''), '❓')
        
        hwid_icon = "🔒" if (lic.get('hwid') or lic.get('hwids', [])) else "🔓"
        keyboard.append([{"text": f"{status_icon} {hwid_icon} {key} | {devices} уст | до {expires}", "callback_data": f"view_{key}"}])
    
    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"page_{page-1}"})
    if start + per_page < len(sorted_keys):
        nav.append({"text": "▶️", "callback_data": f"page_{page+1}"})
    if nav:
        keyboard.append(nav)
    keyboard.append([{"text": "🔙 Главное меню", "callback_data": "back_to_main"}])
    return {"inline_keyboard": keyboard}

def get_users_keyboard(users, page=0, filter_type="all"):
    keyboard = []
    per_page = 10
    start = page * per_page
    
    online_count = get_online_count()
    offline_count = len(users) - online_count
    total_count = len(users)
    
    if filter_type == "blocked":
        users = [u for u in users if u.get('is_blocked', 0) == 1]
    elif filter_type == "active":
        day_ago = (datetime.now() - timedelta(days=1)).isoformat()
        users = [u for u in users if u.get('last_seen', '') > day_ago]
    elif filter_type == "online":
        users = [u for u in users if u.get('is_online', False)]
    elif filter_type == "offline":
        users = [u for u in users if not u.get('is_online', False)]
    
    for idx, user in enumerate(users[start:start+per_page]):
        user_id = user.get('user_id', 'Unknown')
        first_name = user.get('first_name', 'Unknown')
        username = user.get('username', 'Unknown')
        requests_count = user.get('request_count', 0)
        hwid = user.get('hwid', '—')
        is_blocked = user.get('is_blocked', 0)
        is_online = user.get('is_online', False)
        
        status_icon = "🟢" if is_online else "🔴"
        blocked_icon = "🔴" if is_blocked else "🟢"
        
        name = first_name if first_name != 'Unknown' else (username or "Unknown")
        if len(name) > 15:
            name = name[:12] + "..."
        hwid_short = hwid[:8] + "..." if hwid and len(hwid) > 8 else (hwid or "—")
        
        keyboard.append([{"text": f"{status_icon} {blocked_icon} {name} | {requests_count} зап | {hwid_short}", "callback_data": f"view_user_{idx}"}])
    
    header_text = f"👥 *ПОЛЬЗОВАТЕЛИ*\n📊 Всего: {total_count} | 🟢 Онлайн: {online_count} | 🌙 Оффлайн: {offline_count}"
    
    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"users_page_{page-1}_{filter_type}"})
    if start + per_page < len(users):
        nav.append({"text": "▶️", "callback_data": f"users_page_{page+1}_{filter_type}"})
    if nav:
        keyboard.append(nav)
    
    keyboard.append([
        {"text": "📋 Все", "callback_data": "users_filter_all"},
        {"text": "🟢 Онлайн", "callback_data": "users_filter_online"},
        {"text": "🌙 Оффлайн", "callback_data": "users_filter_offline"}
    ])
    keyboard.append([
        {"text": "🟢 Активные", "callback_data": "users_filter_active"},
        {"text": "🔴 Заблок", "callback_data": "users_filter_blocked"}
    ])
    keyboard.append([{"text": "🔙 Главное меню", "callback_data": "back_to_main"}])
    return {"inline_keyboard": keyboard, "header": header_text}

def get_admins_keyboard():
    admins = get_all_admins()
    keyboard = []
    for admin in admins:
        admin_id = admin['user_id']
        username = admin.get('username', admin_id)
        keyboard.append([{"text": f"👑 {username}", "callback_data": f"admin_{admin_id}"}])
    keyboard.append([{"text": "➕ Добавить админа", "callback_data": "add_admin"}])
    keyboard.append([{"text": "🔙 Главное меню", "callback_data": "back_to_main"}])
    return {"inline_keyboard": keyboard}

def get_reset_keyboard(keys):
    keyboard = []
    for lic in keys:
        if lic['status'] != 'blocked':
            key = lic['key']
            hwid = lic.get('hwid')
            hwids = lic.get('hwids', [])
            hwid_icon = "🔒" if (hwid or hwids) else "🔓"
            status_icon = "❄️" if lic['status'] == 'frozen' else ""
            keyboard.append([{"text": f"🔄 {status_icon} {hwid_icon} {key}", "callback_data": f"reset_{key}"}])
    keyboard.append([{"text": "🔙 Главное меню", "callback_data": "back_to_main"}])
    return {"inline_keyboard": keyboard}

def get_delete_keyboard(keys):
    keyboard = []
    for lic in keys:
        key = lic['key']
        keyboard.append([{"text": f"❌ {key}", "callback_data": f"delete_{key}"}])
    keyboard.append([{"text": "🔙 Главное меню", "callback_data": "back_to_main"}])
    return {"inline_keyboard": keyboard}

def get_user_detail_keyboard(user_idx):
    return {
        "inline_keyboard": [
            [{"text": "🚫 Заблокировать", "callback_data": f"block_user_{user_idx}"},
             {"text": "✅ Разблокировать", "callback_data": f"unblock_user_{user_idx}"}],
            [{"text": "🔙 Назад к списку", "callback_data": "back_to_users"}]
        ]
    }

# ========== API ЭНДПОИНТ ==========
@app.route('/api/check', methods=['GET', 'POST'])
def api_check():
    if request.method == 'GET':
        key = request.args.get('key', '').strip()
        hwid = request.args.get('hwid', None)
        user_id = request.args.get('user_id', 'Unknown')
        username = request.args.get('username', 'Unknown')
        first_name = request.args.get('first_name', 'Unknown')
        last_name = request.args.get('last_name', '')
    else:
        data = request.get_json()
        if not data:
            return jsonify({"status": "ERROR"}), 400
        key = data.get('key', '').strip()
        hwid = data.get('hwid', None)
        user_id = data.get('user_id', 'Unknown')
        username = data.get('username', 'Unknown')
        first_name = data.get('first_name', 'Unknown')
        last_name = data.get('last_name', '')
    
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_address and ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()
    
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    for user in users:
        if user.get('hwid') == hwid and user.get('is_blocked') == 1:
            return jsonify({"status": "BLOCKED"})
    
    save_user_info(user_id, username, first_name, last_name, ip_address, hwid, key, user_agent)
    result = check_license(key, hwid, user_id, username, ip_address)
    
    response_data = {"status": result}
    if result == "ACTIVATED":
        key_upper = key.upper().strip()
        for lic in licenses:
            if lic['key'] == key_upper:
                response_data["expires_at"] = lic['expires_at']
                response_data["is_unlimited"] = lic.get('is_unlimited', False)
                break
    
    return jsonify(response_data)

@app.route('/')
def index():
    return "Key system works!"

# ========== ВЕБХУК ==========
@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        user_id = msg['from']['id']
        user_name = msg['from'].get('username', msg['from'].get('first_name', 'Unknown'))
        
        if not is_admin(user_id):
            send_message(chat_id, "❌ Нет доступа")
            return 'ok', 200
        
        if user_id in temp_data and temp_data[user_id].get('waiting_for') == 'add_admin':
            try:
                new_admin_id = int(text.strip())
                add_admin(new_admin_id, user_id, user_name)
                send_message(chat_id, f"✅ Админ добавлен!")
                temp_data.pop(user_id, None)
                send_message(chat_id, "🔐 *КЛЮЧ-СИСТЕМА*\n\nВыберите действие:", get_main_keyboard())
            except:
                send_message(chat_id, "❌ Введите корректный ID")
            return 'ok', 200
        
        if user_id in temp_data and temp_data[user_id].get('waiting_for') == 'custom_key':
            custom_key = text.strip().upper()
            if len(custom_key) < 3:
                send_message(chat_id, "❌ Ключ слишком короткий (минимум 3 символа)")
                return 'ok', 200
            
            for lic in licenses:
                if lic['key'] == custom_key:
                    send_message(chat_id, f"❌ Ключ уже существует!")
                    return 'ok', 200
            
            temp_data[user_id]['custom_key'] = custom_key
            temp_data[user_id]['waiting_for'] = 'custom_time'
            send_message(chat_id, "⏰ *Выберите тип времени:*", get_time_type_keyboard())
            return 'ok', 200
        
        if text == '/start':
            send_message(chat_id, "🔐 *КЛЮЧ-СИСТЕМА*\n\nВыберите действие:", get_main_keyboard())
    
    elif 'callback_query' in data:
        callback = data['callback_query']
        callback_id = callback['id']
        callback_data = callback['data']
        chat_id = callback['message']['chat']['id']
        message_id = callback['message']['message_id']
        user_id = callback['from']['id']
        user_name = callback['from'].get('username', callback['from'].get('first_name', 'Unknown'))
        
        answer_callback(callback_id)
        
        if not is_admin(user_id):
            send_message(chat_id, "❌ Нет доступа")
            return 'ok', 200
        
        if callback_data == "back_to_main":
            edit_message(chat_id, message_id, "🔐 *КЛЮЧ-СИСТЕМА*\n\nВыберите действие:", get_main_keyboard())
        
        elif callback_data == "back_to_time":
            edit_message(chat_id, message_id, "⏰ *Выберите тип времени:*", get_time_type_keyboard())
        
        elif callback_data == "back_to_users":
            users_list = get_all_users()
            keyboard_data = get_users_keyboard(users_list)
            edit_message(chat_id, message_id, keyboard_data["header"], keyboard_data)
        
        elif callback_data == "stats":
            total_licenses = len(licenses)
            active_licenses = sum(1 for l in licenses if l['status'] == 'active')
            frozen_licenses = sum(1 for l in licenses if l['status'] == 'frozen')
            blocked_licenses = sum(1 for l in licenses if l['status'] == 'blocked')
            online_count = get_online_count()
            
            text = f"""📊 *СТАТИСТИКА*
━━━━━━━━━━━━━━━━━
🔑 *Ключи:* {total_licenses}
✅ Активные: {active_licenses}
❄️ Заморожены: {frozen_licenses}
🔴 Заблокированы: {blocked_licenses}
👥 *Пользователи:* {len(users)}
🟢 Онлайн: {online_count}
🌙 Оффлайн: {len(users) - online_count}"""
            send_message(chat_id, text, get_main_keyboard())
        
        elif callback_data == "show_admins":
            text = "👑 *АДМИНЫ*\n\n📌 Главные:\n" + "\n".join([f"• `{aid}`" for aid in ADMIN_IDS]) + "\n\n📋 Дополнительные:"
            edit_message(chat_id, message_id, text, get_admins_keyboard())
        
        elif callback_data == "add_admin":
            temp_data[user_id] = {"waiting_for": "add_admin"}
            edit_message(chat_id, message_id, "➕ Введите Telegram ID:", get_main_keyboard())
        
        elif callback_data.startswith("admin_"):
            admin_id = callback_data.replace("admin_", "")
            if int(admin_id) not in ADMIN_IDS:
                kb = {"inline_keyboard": [[{"text": "❌ Удалить", "callback_data": f"remove_admin_{admin_id}"}], [{"text": "🔙 Назад", "callback_data": "show_admins"}]]}
                edit_message(chat_id, message_id, f"👑 Действия с админом `{admin_id}`", kb)
            else:
                send_message(chat_id, "❌ Нельзя удалить главного админа!")
        
        elif callback_data.startswith("remove_admin_"):
            admin_id = callback_data.replace("remove_admin_", "")
            remove_admin(admin_id)
            edit_message(chat_id, message_id, f"✅ Админ удален!", get_admins_keyboard())
        
        elif callback_data == "gen_random":
            temp_data[user_id] = {"type": "random"}
            edit_message(chat_id, message_id, "🎲 *Случайный ключ*\n\nВыберите тип времени:", get_time_type_keyboard())
        
        elif callback_data == "gen_custom":
            temp_data[user_id] = {"type": "custom", "waiting_for": "custom_key"}
            edit_message(chat_id, message_id, "✏️ *Свой ключ*\n\nВведите любой ключ (минимум 3 символа):", get_main_keyboard())
        
        elif callback_data == "time_days":
            temp_data[user_id]["time_unit"] = "days"
            edit_message(chat_id, message_id, "📅 Выберите дни:", get_days_keyboard())
        
        elif callback_data == "time_hours":
            temp_data[user_id]["time_unit"] = "hours"
            edit_message(chat_id, message_id, "⏰ Выберите часы:", get_hours_keyboard())
        
        elif callback_data == "time_minutes":
            temp_data[user_id]["time_unit"] = "minutes"
            edit_message(chat_id, message_id, "⏱️ Выберите минуты:", get_minutes_keyboard())
        
        elif callback_data.startswith("val_"):
            parts = callback_data.split("_")
            value = int(parts[1])
            unit = parts[2]
            temp_data[user_id]["time_value"] = value
            temp_data[user_id]["time_unit"] = unit
            edit_message(chat_id, message_id, f"💻 Выберите устройства:\n⏰ {value} {unit}", get_devices_keyboard())
        
        elif callback_data.startswith("custom_"):
            unit = callback_data.replace("custom_", "")
            temp_data[user_id]["waiting_for"] = f"time_{unit}"
            temp_data[user_id]["time_unit"] = unit
            edit_message(chat_id, message_id, f"✏️ Введите количество {unit} (макс: дни-365, часы-720, минуты-1440):", get_main_keyboard())
        
        elif callback_data == "dev_unlimited":
            data = temp_data.get(user_id, {})
            key_type = data.get("type")
            time_value = data.get("time_value")
            time_unit = data.get("time_unit")
            custom_key = data.get("custom_key")
            
            now = datetime.now()
            if time_unit == "minutes":
                expires = now + timedelta(minutes=time_value)
            elif time_unit == "hours":
                expires = now + timedelta(hours=time_value)
            else:
                expires = now + timedelta(days=time_value)
            
            if key_type == "random":
                key = generate_key(time_value, time_unit)
                add_license(key, None, time_value, time_unit, expires, user_id, user_name)
                edit_message(chat_id, message_id,
                    f"✅ *КЛЮЧ СОЗДАН!*\n\n🔑 `{key}`\n⏰ {time_value} {time_unit}\n💻 ♾️ Безлимит устройств\n📅 Истекает: {expires.strftime('%d.%m.%Y %H:%M')}",
                    get_main_keyboard())
                temp_data.pop(user_id, None)
            elif key_type == "custom" and custom_key:
                add_license(custom_key, None, time_value, time_unit, expires, user_id, user_name)
                edit_message(chat_id, message_id,
                    f"✅ *КЛЮЧ СОЗДАН!*\n\n🔑 `{custom_key}`\n⏰ {time_value} {time_unit}\n💻 ♾️ Безлимит устройств\n📅 Истекает: {expires.strftime('%d.%m.%Y %H:%M')}",
                    get_main_keyboard())
                temp_data.pop(user_id, None)
        
        elif callback_data.startswith("dev_"):
            if callback_data == "custom_devices":
                temp_data[user_id]["waiting_for"] = "devices"
                edit_message(chat_id, message_id, "✏️ Введите количество устройств (1-100) или 0 для безлимита:", get_main_keyboard())
                return 'ok', 200
            
            devices = int(callback_data.split("_")[1])
            temp_data[user_id]["devices"] = devices
            
            data = temp_data.get(user_id, {})
            key_type = data.get("type")
            time_value = data.get("time_value")
            time_unit = data.get("time_unit")
            devices_val = data.get("devices")
            custom_key = data.get("custom_key")
            
            now = datetime.now()
            if time_unit == "minutes":
                expires = now + timedelta(minutes=time_value)
            elif time_unit == "hours":
                expires = now + timedelta(hours=time_value)
            else:
                expires = now + timedelta(days=time_value)
            
            if key_type == "random":
                key = generate_key(time_value, time_unit)
                add_license(key, devices_val, time_value, time_unit, expires, user_id, user_name)
                edit_message(chat_id, message_id,
                    f"✅ *КЛЮЧ СОЗДАН!*\n\n🔑 `{key}`\n⏰ {time_value} {time_unit}\n💻 {devices_val} устройств\n📅 Истекает: {expires.strftime('%d.%m.%Y %H:%M')}",
                    get_main_keyboard())
                temp_data.pop(user_id, None)
            elif key_type == "custom" and custom_key:
                add_license(custom_key, devices_val, time_value, time_unit, expires, user_id, user_name)
                edit_message(chat_id, message_id,
                    f"✅ *КЛЮЧ СОЗДАН!*\n\n🔑 `{custom_key}`\n⏰ {time_value} {time_unit}\n💻 {devices_val} устройств\n📅 Истекает: {expires.strftime('%d.%m.%Y %H:%M')}",
                    get_main_keyboard())
                temp_data.pop(user_id, None)
        
        elif callback_data == "list_keys":
            keys = get_all_licenses()
            if not keys:
                edit_message(chat_id, message_id, "📋 Ключей пока нет", get_main_keyboard())
            else:
                edit_message(chat_id, message_id, "📋 *СПИСОК КЛЮЧЕЙ*\n✅ Актив | ❄️ Заморожен | 🔴 Заблокирован", get_keys_list_keyboard(keys))
        
        elif callback_data.startswith("page_"):
            page = int(callback_data.split("_")[1])
            keys = get_all_licenses()
            edit_message(chat_id, message_id, "📋 *СПИСОК КЛЮЧЕЙ*\n✅ Актив | ❄️ Заморожен | 🔴 Заблокирован", get_keys_list_keyboard(keys, page))
        
        elif callback_data.startswith("view_"):
            key = callback_data.replace("view_", "").upper().strip()
            lic = get_license_info(key)
            if lic:
                devices_text = "♾️ Безлимит" if lic.get('is_unlimited', False) else f"{lic['devices_limit']} устройств"
                
                hwid_text = "🔓 Свободен"
                if lic.get('is_unlimited', False) and lic.get('hwids', []):
                    hwid_text = f"🔒 Привязан ({len(lic.get('hwids', []))} устройств)"
                elif lic.get('hwid'):
                    hwid_text = "🔒 Привязан"
                
                status_icon = {
                    'active': '✅ Активен',
                    'frozen': '❄️ Заморожен',
                    'blocked': '🔴 Заблокирован'
                }.get(lic['status'], '❓')
                
                stats = get_license_stats(key)
                users_used = lic.get('users_used', [])
                attempts = lic.get('attempts', [])
                
                unique_users = len(set(u.get('user_id') for u in users_used if u.get('user_id')))
                unique_devices = len(set(u.get('hwid') for u in users_used if u.get('hwid')))
                
                text = f"""🔑 *КЛЮЧ*
━━━━━━━━━━━━━━━━━
📌 `{key}`
📊 Статус: {status_icon}
👤 Создал: {lic['created_by_name']}
💻 Устройств: {devices_text}
⏰ Срок: {lic['time_value']} {lic['time_unit']}
📅 Истекает: {lic['expires_at'][:10]}

📈 *Использование:*
👥 Уникальных юзеров: {unique_users}
🖥 Уникальных устройств: {unique_devices}
📊 Попыток: {len(attempts)}
🕐 Последний раз: {lic['last_used'][:16] if lic.get('last_used') else 'Никогда'}"""

                if users_used:
                    text += "\n\n👤 *Пользователи:*"
                    for u in users_used[-5:]:
                        username = u.get('username', 'Unknown')
                        text += f"\n• @{username} ({u.get('hwid', '—')[:8]}...)"
                
                edit_message(chat_id, message_id, text, get_license_detail_keyboard(key))
        
        elif callback_data.startswith("freeze_"):
            key = callback_data.replace("freeze_", "")
            temp_data[user_id] = {"freeze_key": key}
            edit_message(chat_id, message_id, f"❄️ Выберите время заморозки для `{key}`:", get_freeze_keyboard())
        
        elif callback_data.startswith("freeze_") and callback_data != "freeze_":
            parts = callback_data.split("_")
            hours = parts[1]
            key = temp_data.get(user_id, {}).get("freeze_key")
            
            if not key:
                send_message(chat_id, "❌ Ошибка")
                temp_data.pop(user_id, None)
                return 'ok', 200
            
            if hours == "forever":
                success, msg = freeze_license(key, None)
            else:
                success, msg = freeze_license(key, int(hours))
            
            if success:
                edit_message(chat_id, message_id, f"✅ Ключ `{key}` {msg}", get_main_keyboard())
            else:
                send_message(chat_id, f"❌ {msg}")
            
            temp_data.pop(user_id, None)
        
        elif callback_data.startswith("unfreeze_"):
            key = callback_data.replace("unfreeze_", "")
            if unfreeze_license(key):
                edit_message(chat_id, message_id, f"✅ Ключ `{key}` разморожен", get_main_keyboard())
            else:
                send_message(chat_id, "❌ Ошибка")
        
        elif callback_data.startswith("block_"):
            key = callback_data.replace("block_", "")
            if block_license(key):
                edit_message(chat_id, message_id, f"🔒 Ключ `{key}` заблокирован", get_main_keyboard())
            else:
                send_message(chat_id, "❌ Ошибка")
        
        elif callback_data.startswith("unblock_"):
            key = callback_data.replace("unblock_", "")
            if unblock_license(key):
                edit_message(chat_id, message_id, f"🔓 Ключ `{key}` разблокирован", get_main_keyboard())
            else:
                send_message(chat_id, "❌ Ошибка")
        
        elif callback_data == "reset_key":
            keys = get_all_licenses()
            if not keys:
                edit_message(chat_id, message_id, "🔄 Нет активных ключей", get_main_keyboard())
            else:
                edit_message(chat_id, message_id, "🔄 Выберите ключ для сброса:\n(Сброс очищает привязку и обновляет время)", get_reset_keyboard(keys))
        
        elif callback_data.startswith("reset_"):
            key = callback_data.replace("reset_", "")
            if reset_license(key):
                edit_message(chat_id, message_id, f"✅ Ключ `{key}` сброшен!\n🔓 Привязка удалена, время обновлено", get_main_keyboard())
            else:
                send_message(chat_id, "❌ Ошибка")
        
        elif callback_data == "delete_key":
            keys = get_all_licenses()
            if not keys:
                edit_message(chat_id, message_id, "❌ Нет ключей", get_main_keyboard())
            else:
                edit_message(chat_id, message_id, "❌ Выберите ключ для УДАЛЕНИЯ:", get_delete_keyboard(keys))
        
        elif callback_data.startswith("delete_"):
            key = callback_data.replace("delete_", "").upper().strip()
            delete_license(key)
            edit_message(chat_id, message_id, f"✅ Ключ `{key}` удалён", get_main_keyboard())
        
        elif callback_data == "show_users":
            users_list = get_all_users()
            if not users_list:
                edit_message(chat_id, message_id, "👥 Пользователей пока нет", get_main_keyboard())
            else:
                keyboard_data = get_users_keyboard(users_list)
                edit_message(chat_id, message_id, keyboard_data["header"], keyboard_data)
        
        elif callback_data.startswith("users_page_"):
            parts = callback_data.split("_")
            page = int(parts[2])
            filter_type = parts[3] if len(parts) > 3 else "all"
            users_list = get_all_users()
            keyboard_data = get_users_keyboard(users_list, page, filter_type)
            edit_message(chat_id, message_id, keyboard_data["header"], keyboard_data)
        
        elif callback_data.startswith("users_filter_"):
            filter_type = callback_data.replace("users_filter_", "")
            users_list = get_all_users()
            keyboard_data = get_users_keyboard(users_list, 0, filter_type)
            edit_message(chat_id, message_id, keyboard_data["header"], keyboard_data)
        
        elif callback_data.startswith("view_user_"):
            user_idx = int(callback_data.replace("view_user_", ""))
            users_list = get_all_users()
            if user_idx < len(users_list):
                u = users_list[user_idx]
                is_online = u.get('is_online', False)
                online_status = "🟢 Онлайн" if is_online else "🌙 Оффлайн"
                
                key_used = u.get('key_used', '—')
                lic = get_license_info(key_used) if key_used != '—' else None
                
                text = f"""👤 *ПОЛЬЗОВАТЕЛЬ*
━━━━━━━━━━━━━━━━━
🆔 *ID:* `{u.get('user_id', '—')}`
📝 *Username:* @{u.get('username', '—')}
👤 *Имя:* {u.get('first_name', '—')}

🔑 *Ключ:* `{key_used}`
🔐 *HWID:* `{u.get('hwid', '—')}`
📊 *Запросов:* {u.get('request_count', 0)}
📶 *Статус:* {online_status}

📅 *Первый раз:* {u.get('first_seen', '—')[:16]}
🕐 *Последний раз:* {u.get('last_seen', '—')[:16]}
🌐 *IP:* {u.get('ip_address', '—')}
⚡ *Блокировка:* {'🔴 ЗАБЛОКИРОВАН' if u.get('is_blocked') else '🟢 АКТИВЕН'}"""
                
                if lic:
                    stats = get_license_stats(key_used)
                    if stats:
                        text += f"\n\n📊 *Статистика ключа:*\n👥 Юзеров: {stats['users']}\n🖥 Устройств: {stats['devices']}\n📊 Попыток: {stats['attempts']}"
                
                send_message(chat_id, text, get_user_detail_keyboard(user_idx))
        
        elif callback_data.startswith("block_user_"):
            user_idx = int(callback_data.replace("block_user_", ""))
            block_user(user_idx)
            send_message(chat_id, f"✅ Пользователь заблокирован")
        
        elif callback_data.startswith("unblock_user_"):
            user_idx = int(callback_data.replace("unblock_user_", ""))
            unblock_user(user_idx)
            send_message(chat_id, f"✅ Пользователь разблокирован")
        
        elif callback_data.startswith("stats_"):
            key = callback_data.replace("stats_", "")
            lic = get_license_info(key)
            if not lic:
                send_message(chat_id, "❌ Ключ не найден")
                return 'ok', 200
            
            stats = get_license_stats(key)
            attempts = lic.get('attempts', [])
            users_used = lic.get('users_used', [])
            
            text = f"""📊 *СТАТИСТИКА КЛЮЧА `{key}`*
━━━━━━━━━━━━━━━━━
📊 *Общее:*
👥 Юзеров: {stats['users']}
🖥 Устройств: {stats['devices']}
📊 Попыток: {stats['attempts']}
🔒 Статус: {stats['status']}

📈 *Попытки (последние 5):*"""
            
            for attempt in attempts[-5:]:
                timestamp = datetime.fromisoformat(attempt['timestamp']).strftime('%H:%M')
                success = "✅" if attempt['success'] else "❌"
                hwid = attempt.get('hwid', '—')[:8] + "..."
                text += f"\n{timestamp} {success} {hwid}"
            
            if users_used:
                text += "\n\n👤 *Пользователи:*"
                for u in users_used[-5:]:
                    username = u.get('username', 'Unknown')
                    text += f"\n• @{username}"
            
            send_message(chat_id, text)
    
    return 'ok', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
