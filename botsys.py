"""
botsys.py — EXODUS SMS BOMBER Telegram Bot (Firebase Edition)
Developer: @exodus_own3r

Features:
  • India & Bangladesh SMS bombing
  • India tiers: Normal (50 APIs), Premium (100 APIs), Nuclear (150 APIs, premium only)
  • Bangladesh: all APIs
  • Referral system: 1 ref = 10 credits, 5 refs = 7d key, 10 refs = 15d key, 20 refs = 1 month key
  • Gift code redemption
  • Premium users only: Nuclear bomb tier
  • Force-join channels (admin-managed, instant apply)
  • API key gate with daily limit
  • Admin panel: stats, users, keys, channels, gift codes, broadcast, export/import, settings
  • Coloured inline buttons, menu buttons, developer footer on every message
  • Firebase Firestore backend (auto fallback to in-memory if not configured)
"""

import os, re, json, time, html, secrets, threading, copy
from concurrent.futures import ThreadPoolExecutor
import requests

# ═══════════════════════════════════════════════════════════════
#  ENV LOADER
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
_load_dotenv()

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
#  CONFIG
# ═══════════════════════════════════════════════════════════════
DEV_TAG          = os.environ.get("DEVELOPER_TAG", "@exodus_own3r")
DEV_URL          = os.environ.get("DEVELOPER_URL", "https://t.me/exodus_own3r")
CONTACT_USERNAME = os.environ.get("CONTACT_USERNAME", "exodus_own3r").lstrip("@")
CONTACT_URL      = f"https://t.me/{CONTACT_USERNAME}"
DEFAULT_DAILY    = int(os.environ.get("API_DAILY_LIMIT", "500"))

# Referral plans: (referrals needed, key days, label)
PLANS = [(5, 7, "7 Days"), (10, 15, "15 Days"), (20, 30, "1 Month")]

CREDITS_PER_REFERRAL     = int(os.environ.get("CREDITS_PER_REFERRAL", "10"))
CREDITS_PER_BOMB_NORMAL  = int(os.environ.get("CREDITS_PER_BOMB_NORMAL", "1"))
CREDITS_PER_BOMB_PREMIUM = int(os.environ.get("CREDITS_PER_BOMB_PREMIUM", "2"))
CREDITS_PER_BOMB_NUCLEAR = int(os.environ.get("CREDITS_PER_BOMB_NUCLEAR", "3"))

IND_NORMAL_APIS  = int(os.environ.get("IND_NORMAL_APIS", "50"))
IND_PREMIUM_APIS = int(os.environ.get("IND_PREMIUM_APIS", "100"))
IND_NUCLEAR_APIS = int(os.environ.get("IND_NUCLEAR_APIS", "150"))
BD_APIS_PER_BOMB = os.environ.get("BD_APIS_PER_BOMB", "all")

BOT_TOKEN    = ""
BOT_ID       = 0
BOT_USERNAME = ""
BASE_URL     = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
LOCAL_PORT   = 5000
ADMIN_IDS    = set()

E = html.escape
FOOTER = f"\n\n━━━━━━━━━━━━━━━━━━\n👨‍💻 <b>Developer:</b> {DEV_TAG}"
INTERNAL_TOKEN = secrets.token_hex(24)

# ═══════════════════════════════════════════════════════════════
#  FIREBASE HELPERS
# ═══════════════════════════════════════════════════════════════
def fb_user(uid):
    if not _db: return None
    try:
        doc = _db.collection("users").document(str(uid)).get()
        return doc.to_dict() if doc.exists else None
    except: return None

def fb_user_set(uid, data):
    if not _db: return False
    try:
        _db.collection("users").document(str(uid)).set(data, merge=True)
        return True
    except: return False

def fb_user_update(uid, **kwargs):
    if not _db: return False
    try:
        _db.collection("users").document(str(uid)).update(kwargs)
        return True
    except: return False

def fb_key_get(uid):
    if not _db: return None
    try:
        docs = _db.collection("keys").where("user_id", "==", str(uid)) \
            .where("revoked", "==", False) \
            .order_by("expires_at", direction=firestore.Query.DESCENDING).limit(1).stream()
        for d in docs:
            return d.to_dict()
        return None
    except: return None

def fb_key_set(uid, key, exp, plan=""):
    if not _db: return False
    try:
        _db.collection("keys").document(key).set({
            "key": key, "user_id": str(uid), "created_at": int(time.time()),
            "expires_at": exp, "revoked": False,
            "daily_limit": DEFAULT_DAILY, "plan": plan
        })
        return True
    except: return False

def fb_key_update(key, **kwargs):
    if not _db: return False
    try:
        _db.collection("keys").document(key).update(kwargs)
        return True
    except: return False

def fb_channels():
    if not _db: return []
    try:
        return [dict(d.to_dict(), id=d.id) for d in _db.collection("channels").stream()]
    except: return []

def fb_channel_add(chat_id, title, link):
    if not _db: return False
    try:
        _db.collection("channels").document(str(chat_id)).set({
            "chat_id": str(chat_id), "title": title, "link": link,
            "added_at": int(time.time())
        })
        return True
    except: return False

def fb_channel_del(chat_id):
    if not _db: return False
    try:
        _db.collection("channels").document(str(chat_id)).delete()
        return True
    except: return False

def fb_setting_get(k, default=None):
    if not _db: return default
    try:
        doc = _db.collection("settings").document(k).get()
        return doc.to_dict().get("v") if doc.exists else default
    except: return default

def fb_setting_set(k, v):
    if not _db: return False
    try:
        _db.collection("settings").document(k).set({"v": str(v)})
        return True
    except: return False

def fb_gift_get(code):
    if not _db: return None
    try:
        doc = _db.collection("gift_codes").document(code).get()
        return doc.to_dict() if doc.exists else None
    except: return None

def fb_gift_set(code, data):
    if not _db: return False
    try:
        _db.collection("gift_codes").document(code).set(data)
        return True
    except: return False

def fb_gift_claim_exists(code, uid):
    if not _db: return False
    try:
        doc = _db.collection("gift_claims").document(f"{code}_{uid}").get()
        return doc.exists
    except: return False

def fb_gift_claim(code, uid):
    if not _db: return False
    try:
        _db.collection("gift_claims").document(f"{code}_{uid}").set({
            "code": code, "user_id": str(uid), "claimed_at": int(time.time())
        })
        return True
    except: return False

def fb_usage_today(key):
    if not _db: return 0
    try:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        doc = _db.collection("usage").document(f"{key}_{today}").get()
        return doc.to_dict().get("count", 0) if doc.exists else 0
    except: return 0

def fb_users_all():
    if not _db: return []
    try:
        return [d.to_dict() for d in _db.collection("users").stream()]
    except: return []

# ═══════════════════════════════════════════════════════════════
#  DB WRAPPER
# ═══════════════════════════════════════════════════════════════
def get_setting(k, default=None):
    v = fb_setting_get(k, None)
    return v if v is not None else default

def set_setting(k, v):
    fb_setting_set(k, v)

def daily_limit():
    try: return int(get_setting("daily_limit", DEFAULT_DAILY))
    except: return DEFAULT_DAILY

def force_join_on():
    return get_setting("force_join", "1") == "1"

def get_user(uid):
    return fb_user(uid)

def upsert_user(frm, referred_by=None):
    uid = frm["id"]
    row = fb_user(uid)
    if row is None:
        rb = None
        if referred_by and referred_by != uid and fb_user(referred_by):
            rb = referred_by
        fb_user_set(uid, {
            "id": uid, "username": frm.get("username") or "",
            "first_name": frm.get("first_name") or "",
            "joined_at": int(time.time()), "referred_by": rb,
            "ref_counted": False, "ref_points": 0, "total_refs": 0,
            "credits": 0, "banned": False, "total_bombs": 0,
            "is_premium": False
        })
        return fb_user(uid), True
    fb_user_update(uid, username=frm.get("username") or "",
                   first_name=frm.get("first_name") or "")
    return row, False

def add_credits(uid, amount):
    if not _db: return
    try:
        _db.collection("users").document(str(uid)).set(
            {"credits": firestore.Increment(amount)}, merge=True)
    except: pass

def active_key(uid):
    k = fb_key_get(uid)
    if k and k.get("expires_at", 0) > int(time.time()):
        return k
    return None

def grant_key(uid, days, label=""):
    now = int(time.time())
    row = active_key(uid)
    if row:
        exp = max(now, row["expires_at"]) + days * 86400
        fb_key_update(row["key"], expires_at=exp)
        return row["key"], exp
    key = f"EXO-{secrets.token_hex(12).upper()}"
    exp = now + days * 86400
    fb_key_set(uid, key, exp, label)
    return key, exp

def claim_plan(uid, idx):
    cost, days, label = PLANS[idx]
    u = fb_user(uid)
    if not u or u.get("ref_points", 0) < cost: return None
    fb_user_update(uid, ref_points=u["ref_points"] - cost)
    return grant_key(uid, days, label)

def list_channels():
    return fb_channels()

# ═══════════════════════════════════════════════════════════════
#  TELEGRAM LAYER
# ═══════════════════════════════════════════════════════════════
class TGError(Exception):
    def __init__(self, desc, code=0, retry_after=0):
        super().__init__(desc)
        self.desc, self.code, self.retry_after = desc, code, retry_after

_tl = threading.local()

def tg(method, _t=30, **params):
    s = getattr(_tl, "s", None)
    if s is None: s = _tl.s = requests.Session()
    try:
        r = s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=params, timeout=_t)
        data = r.json()
    except Exception as e:
        raise TGError(f"network: {e}")
    if not data.get("ok"):
        raise TGError(data.get("description", "error"), data.get("error_code", 0),
                      (data.get("parameters") or {}).get("retry_after", 0))
    return data["result"]

def _strip_style(markup):
    m = copy.deepcopy(markup)
    for row in m.get("inline_keyboard", []):
        for b in row: b.pop("style", None)
    return m

def _call_markup(method, **params):
    try:
        return tg(method, **params)
    except TGError as e:
        if "message is not modified" in e.desc: return None
        if e.code == 400 and params.get("reply_markup"):
            low = e.desc.lower()
            if "style" in low or "button" in low or "unsupported" in low:
                params["reply_markup"] = _strip_style(params["reply_markup"])
                try:
                    return tg(method, **params)
                except TGError as e2:
                    if "message is not modified" in e2.desc: return None
                    raise
        raise

def send(cid, text, markup=None):
    p = dict(chat_id=cid, text=text, parse_mode="HTML", link_preview_options={"is_disabled": True})
    if markup: p["reply_markup"] = markup
    return _call_markup("sendMessage", **p)

def edit(cid, mid, text, markup=None):
    p = dict(chat_id=cid, message_id=mid, text=text, parse_mode="HTML",
             link_preview_options={"is_disabled": True})
    if markup: p["reply_markup"] = markup
    return _call_markup("editMessageText", **p)

def show(cid, mid, text, markup=None):
    if mid:
        try: return edit(cid, mid, text, markup)
        except TGError: pass
    return send(cid, text, markup)

def B(text, cb=None, url=None, style=None, copy_text=None):
    b = {"text": text}
    if url: b["url"] = url
    elif copy_text: b["copy_text"] = {"text": copy_text}
    else: b["callback_data"] = cb or "noop"
    if style: b["style"] = style
    return b

def KB(*rows):
    return {"inline_keyboard": [list(r) for r in rows if r]}

# ═══════════════════════════════════════════════════════════════
#  FORCE JOIN
# ═══════════════════════════════════════════════════════════════
_member_cache = {}
_CACHE_TTL = 60

def _is_member(uid, chat_id):
    ck = (uid, chat_id)
    if time.time() - _member_cache.get(ck, 0) < _CACHE_TTL: return True
    try:
        m = tg("getChatMember", chat_id=chat_id, user_id=uid)
    except TGError:
        return True
    st = m.get("status")
    ok = st in ("creator", "administrator", "member") or (st == "restricted" and m.get("is_member", False))
    if ok: _member_cache[ck] = time.time()
    return ok

def missing_channels(uid):
    if uid in ADMIN_IDS or not force_join_on(): return []
    return [c for c in list_channels() if not _is_member(uid, c["chat_id"])]

_pending_action = {}

def join_prompt(cid, mid, miss):
    lines = "\n".join(f"  📢 <b>{E(c['title'] or 'Channel')}</b>" for c in miss)
    text = ("<b>🔒 JOIN REQUIRED</b>\n━━━━━━━━━━━━━━━━━━\n"
            "To use this bot you must join:\n\n"
            f"{lines}\n\n"
            "<blockquote>After joining, tap <b>✅ Verify</b>.</blockquote>" + FOOTER)
    rows, styles = [], ["primary", "success"]
    for i, c in enumerate(miss):
        if c.get("link"):
            rows.append([B(f"📢 Join {c['title'] or 'Channel'}", url=c["link"], style=styles[i % 2])])
    rows.append([B("✅ Verify", cb="verify", style="success")])
    rows.append([B("💎 Buy Premium", url=CONTACT_URL, style="danger")])
    show(cid, mid, text, KB(*rows))

def gate(uid, cid, mid=None, pending=None):
    miss = missing_channels(uid)
    if not miss: return True
    if pending: _pending_action[uid] = pending
    join_prompt(cid, mid, miss)
    return False

def try_count_referral(uid):
    row = fb_user(uid)
    if not row or not row.get("referred_by") or row.get("ref_counted"): return
    if missing_channels(uid): return
    fb_user_update(uid, ref_counted=True)
    ref = row["referred_by"]
    fb_user_set(ref, {
        "ref_points": firestore.Increment(1),
        "total_refs": firestore.Increment(1),
        "credits": firestore.Increment(CREDITS_PER_REFERRAL)
    })
    r = fb_user(ref)
    if r:
        name = E(row.get("first_name") or "Someone")
        try:
            send(ref, f"<b>🎉 NEW REFERRAL!</b>\n<blockquote>{name} joined using your link.\n"
                      f"🎁 +{CREDITS_PER_REFERRAL} credits\n"
                      f"⭐ Referral points: <b>{(r.get('ref_points') or 0) + 1}</b></blockquote>" + FOOTER,
                 KB([B("🎁 Refer & Earn", cb="refer", style="success")]))
        except TGError: pass

# ═══════════════════════════════════════════════════════════════
#  SCREENS
# ═══════════════════════════════════════════════════════════════
def fmt_exp(ts):
    left = ts - int(time.time())
    d, h = left // 86400, (left % 86400) // 3600
    return f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))} UTC  ({d}d {h}h left)"

def menu_markup(uid):
    row = fb_user(uid)
    is_premium = row and row.get("is_premium", False)
    rows = [
        [B("🇮🇳 India Bomb", cb="bomb_ind", style="primary"), B("🇧🇩 BD Bomb", cb="bomb_bd", style="success")],
        [B("🎁 Refer & Earn", cb="refer", style="success"), B("💳 My Credits", cb="credits", style="primary")],
        [B("🔑 My API Key", cb="mykey", style="primary"), B("📖 API Guide", cb="docs", style="primary")],
        [B("🎟️ Redeem Gift", cb="gift", style="primary"), B("💎 Buy", cb="buy", style="danger")],
        [B("👨‍💻 Developer", url=DEV_URL, style="success")],
    ]
    if is_premium:
        rows.insert(1, [B("☢️ Nuclear Bomb (Premium)", cb="bomb_ind_nuclear", style="danger")])
    if uid in ADMIN_IDS:
        rows.append([B("🛡️ Admin Panel", cb="adm:home", style="danger")])
    return KB(*rows)

def screen_menu(uid, name):
    row = fb_user(uid)
    credits = row.get("credits", 0) if row else 0
    is_premium = row and row.get("is_premium", False)
    premium_tag = " 💎 PREMIUM" if is_premium else ""
    text = (f"<b>💣 EXODUS SMS BOMBER{premium_tag}</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Hey <b>{E(name or 'there')}</b> 👋\n\n"
            f"💰 Credits: <b>{credits}</b>\n"
            f"💣 1 bomb = {CREDITS_PER_BOMB_NORMAL} credit (India)\n"
            f"🎁 1 referral = {CREDITS_PER_REFERRAL} credits\n\n"
            "<blockquote>Choose an option below ↓</blockquote>" + FOOTER)
    return text, menu_markup(uid)

def screen_credits(uid):
    row = fb_user(uid)
    credits = row.get("credits", 0) if row else 0
    is_premium = row and row.get("is_premium", False)
    text = (f"<b>💳 MY CREDITS</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"💰 Available: <b>{credits}</b>\n"
            f"💎 Premium: <b>{'✅ Yes' if is_premium else '❌ No'}</b>\n\n"
            f"<b>💣 Bomb Costs:</b>\n"
            f"🇮🇳 Normal — {CREDITS_PER_BOMB_NORMAL} credit ({IND_NORMAL_APIS} APIs)\n"
            f"🇮🇳 Premium — {CREDITS_PER_BOMB_PREMIUM} credits ({IND_PREMIUM_APIS} APIs)\n"
            f"🇮🇳 Nuclear — {CREDITS_PER_BOMB_NUCLEAR} credits ({IND_NUCLEAR_APIS} APIs) {'🔒 Premium only' if not is_premium else '✅'}\n"
            f"🇧🇩 BD Bomb — {CREDITS_PER_BOMB_NORMAL} credit\n\n"
            f"<b>🎁 Earn Credits:</b>\n"
            f"• Refer friends: +{CREDITS_PER_REFERRAL} per referral\n"
            f"• Redeem gift code\n"
            f"• Buy from developer" + FOOTER)
    return text, KB(
        [B("🎁 Refer & Earn", cb="refer", style="success"), B("🎟️ Redeem Gift", cb="gift", style="primary")],
        [B("💎 Buy Credits", url=CONTACT_URL, style="danger")],
        [B("💎 Get Premium", url=CONTACT_URL, style="danger")],
        [B("🔙 Menu", cb="menu", style="primary")])

def screen_refer(uid):
    u = fb_user(uid)
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    pts = u.get("ref_points", 0) if u else 0
    tiers = []
    for cost, days, label in PLANS:
        mark = "✅" if pts >= cost else "🔒"
        tiers.append(f"{mark} <b>{cost}</b> referrals → <b>{label}</b> API key")
    text = (f"<b>🎁 REFER & EARN</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Invite friends — you get <b>{CREDITS_PER_REFERRAL} credits</b> per referral.\n\n"
            f"🔗 <b>Your link</b>\n<code>{E(link)}</code>\n\n"
            f"👥 Total referrals: <b>{u.get('total_refs',0) if u else 0}</b>\n"
            f"⭐ Referral points: <b>{pts}</b>\n\n"
            "<b>🏆 API Key Rewards</b>\n" + "\n".join(tiers) +
            "\n\n<blockquote>Claiming a reward spends the points. Days add to existing key.</blockquote>" + FOOTER)
    rows = []
    for i, (cost, days, label) in enumerate(PLANS):
        if pts >= cost:
            rows.append([B(f"🔑 Claim {label}  (−{cost} pts)", cb=f"claim:{i}", style="success")])
    share = ("https://t.me/share/url?url=" + requests.utils.quote(link, safe="") +
             "&text=" + requests.utils.quote("💣 Bomb SMS free with Exodus Bomber!", safe=""))
    rows.append([B("📤 Share", url=share, style="primary"), B("📋 Copy", copy_text=link, style="primary")])
    rows.append([B("🔙 Menu", cb="menu", style="danger")])
    return text, KB(*rows)

def api_guide(key=None):
    k = key or "YOUR_API_KEY"
    base = BASE_URL
    get_url = f"{base}/ind?key={k}&number=91XXXXXXXXXX&tier=normal"
    get_bd = f"{base}/bd?key={k}&number=88XXXXXXXXXX"
    return ("<b>📖 API GUIDE</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Base URL</b>\n<code>{E(base)}</code>\n\n"
            f"🇮🇳 <b>India</b>\n<code>{E(get_url)}</code>\n"
            f"🇧🇩 <b>Bangladesh</b>\n<code>{E(get_bd)}</code>\n\n"
            "📊 <b>Tiers (India)</b>:\n"
            f"<code>normal</code> — {IND_NORMAL_APIS} APIs (1 credit)\n"
            f"<code>premium</code> — {IND_PREMIUM_APIS} APIs (2 credits)\n"
            f"<code>nuclear</code> — {IND_NUCLEAR_APIS} APIs (3 credits, premium only)\n\n"
            "📦 <b>Response</b>\n"
            '<pre>{"status": true, "sent": 48, "total_apis": 50}</pre>\n'
            "⚠️ <b>Errors</b>: <code>401</code> invalid/expired key · <code>429</code> daily limit"
            + FOOTER)

def screen_docs(uid):
    row = active_key(uid)
    return api_guide(row["key"] if row else None), KB(
        [B("🔑 My API Key", cb="mykey", style="primary"), B("🎁 Get Key", cb="refer", style="success")],
        [B("🔙 Menu", cb="menu", style="danger")])

def screen_key(uid):
    row = active_key(uid)
    if not row:
        text = ("<b>🔑 MY API KEY</b>\n━━━━━━━━━━━━━━━━━━\n"
                "You don't have an active key yet.\n\n"
                "<blockquote>Refer <b>5</b> friends → 7 days\nRefer <b>10</b> friends → 15 days\n"
                "Refer <b>20</b> friends → 1 month</blockquote>" + FOOTER)
        return text, KB([B("🎁 Refer & Earn", cb="refer", style="success")],
                        [B("💎 Buy Key", url=CONTACT_URL, style="danger")],
                        [B("🔙 Menu", cb="menu", style="primary")])
    lim = row.get("daily_limit") or daily_limit()
    text = ("<b>🔑 MY API KEY</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"<code>{row['key']}</code>\n\n"
            f"⏳ Expires: <b>{fmt_exp(row['expires_at'])}</b>\n"
            f"📊 Today: <b>{fb_usage_today(row['key'])}/{lim}</b>\n\n"
            + api_guide(row["key"]).split("━━━━━━━━━━━━━━━━━━\n", 1)[1])
    return text, KB(
        [B("📋 Copy Key", copy_text=row["key"], style="success"), B("📖 Full Guide", cb="docs", style="primary")],
        [B("💎 Upgrade", url=CONTACT_URL, style="danger"), B("🔙 Menu", cb="menu", style="primary")])

def key_card(key, exp, label=""):
    text = ("<b>🎉 API KEY READY!</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"<code>{key}</code>\n\n"
            f"🏷 Plan: <b>{E(label or 'Custom')}</b>\n"
            f"⏳ Expires: <b>{fmt_exp(exp)}</b>\n\n"
            + api_guide(key).split("━━━━━━━━━━━━━━━━━━\n", 1)[1])
    return text, KB([B("📋 Copy Key", copy_text=key, style="success")],
                    [B("📖 API Guide", cb="docs", style="primary"), B("🔙 Menu", cb="menu", style="danger")])

def screen_buy(uid):
    text = ("<b>💎 BUY PREMIUM</b>\n━━━━━━━━━━━━━━━━━━\n"
            "Want more credits or a direct API key without referrals?\n\n"
            "<b>Options:</b>\n"
            "• Buy credits\n"
            "• Buy API key (instant)\n"
            "• Get Premium (Nuclear bomb access)\n\n"
            f"<blockquote>Contact <b>@{E(CONTACT_USERNAME)}</b> to purchase.</blockquote>" + FOOTER)
    return text, KB(
        [B("💬 Message to Buy", url=CONTACT_URL, style="success")],
        [B("🔙 Menu", cb="menu", style="primary")])

def screen_gift(uid):
    text = ("<b>🎟️ REDEEM GIFT CODE</b>\n━━━━━━━━━━━━━━━━━━\n"
            "Send a gift code to claim credits.\n\n"
            "<blockquote>Example: <code>EXO-GIFT-ABCD1234</code></blockquote>" + FOOTER)
    return text, KB([B("🔙 Menu", cb="menu", style="primary")])

def handle_gift_code(uid, cid, code):
    code = code.strip().upper()
    gc = fb_gift_get(code)
    if not gc:
        return send(cid, "❌ <b>Invalid gift code.</b>" + FOOTER, KB([B("🔙 Menu", cb="menu", style="primary")]))
    if gc.get("expires_at") and gc["expires_at"] < int(time.time()):
        return send(cid, "❌ <b>This gift code has expired.</b>" + FOOTER, KB([B("🔙 Menu", cb="menu", style="primary")]))
    if gc.get("max_users", 0) > 0 and gc.get("claimed_count", 0) >= gc["max_users"]:
        return send(cid, "❌ <b>This gift code has reached its maximum users.</b>" + FOOTER,
                    KB([B("🔙 Menu", cb="menu", style="primary")]))
    if fb_gift_claim_exists(code, uid):
        return send(cid, "❌ <b>You already claimed this code.</b>" + FOOTER,
                    KB([B("🔙 Menu", cb="menu", style="primary")]))
    fb_gift_claim(code, uid)
    fb_gift_set(code, {**gc, "claimed_count": gc.get("claimed_count", 0) + 1})
    add_credits(uid, gc["credits"])
    send(cid, f"<b>🎉 GIFT CLAIMED!</b>\n<blockquote>+{gc['credits']} credits added to your account.</blockquote>" + FOOTER,
         KB([B("💳 My Credits", cb="credits", style="success"), B("🔙 Menu", cb="menu", style="primary")]))

# ═══════════════════════════════════════════════════════════════
#  BOMB FLOW
# ═══════════════════════════════════════════════════════════════
_inflight = set()
_inflight_lock = threading.Lock()

def call_bomb_api(country, number, tier="normal"):
    try:
        url = f"http://127.0.0.1:{LOCAL_PORT}/{country}"
        r = requests.get(url, params={"key": "INTERNAL", "number": number, "tier": tier},
                         headers={"X-Internal-Token": INTERNAL_TOKEN}, timeout=120)
        return r.json(), None
    except Exception as e:
        return None, f"API unreachable ({type(e).__name__})"

def handle_bomb(uid, cid, country, tier, number):
    if not gate(uid, cid, pending={"action": "bomb", "country": country, "tier": tier, "number": number}):
        return
    with _inflight_lock:
        if uid in _inflight:
            send(cid, "⏳ <b>Please wait</b> — your previous bomb is still processing." + FOOTER)
            return
        _inflight.add(uid)
    try:
        wait = send(cid, f"<b>💣 BOMBING {country.upper()}…</b>\n<blockquote>Target: <code>{E(number)}</code>\nTier: <b>{tier.upper()}</b></blockquote>" + FOOTER)
        mid = wait["message_id"] if wait else None
        data, err = call_bomb_api(country, number, tier)
        buy_row = [B("💎 Buy Credits", url=CONTACT_URL, style="danger"), B("👨‍💻 Developer", url=DEV_URL, style="primary")]
        ok = bool(data) and data.get("status") is True
        if not ok:
            reason = err or (data or {}).get("message") or "All APIs failed"
            text = (f"<b>❌ BOMB FAILED</b>\n━━━━━━━━━━━━━━━━━━\n<blockquote>{E(str(reason))}</blockquote>\n"
                    "Try again or use a different number." + FOOTER)
            show(cid, mid, text, KB(buy_row))
            return
        sent = data.get("sent", 0)
        total = data.get("total_apis", 0)
        rate = (sent / total * 100) if total else 0
        text = (f"<b>✅ BOMB COMPLETE!</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"🌍 Country: <b>{E(country.upper())}</b>\n"
                f"📱 Target: <code>{E(number)}</code>\n"
                f"📊 APIs: <b>{sent}/{total}</b> ({rate:.1f}%)\n\n"
                f"💣 <b>DESTRUCTION COMPLETE!</b>" + FOOTER)
        show(cid, mid, text, KB([B("💣 Bomb Again", cb="bomb_ind" if country == "ind" else "bomb_bd", style="success")],
                                buy_row))
        fb_user_set(uid, {"total_bombs": firestore.Increment(1)})
    finally:
        with _inflight_lock:
            _inflight.discard(uid)

def start_bomb_flow(uid, cid, mid, country, tier=None):
    row = fb_user(uid)
    if not row: return
    is_premium = row.get("is_premium", False)

    if tier == "nuclear" and not is_premium:
        return show(cid, mid, "<b>🔒 PREMIUM ONLY</b>\n━━━━━━━━━━━━━━━━━━\n"
                    "<blockquote>Nuclear Bomb is available only for premium users.\n"
                    f"Contact @{E(CONTACT_USERNAME)} to upgrade.</blockquote>" + FOOTER,
                    KB([B("💎 Get Premium", url=CONTACT_URL, style="danger")],
                       [B("🔙 Menu", cb="menu", style="primary")]))

    cost = CREDITS_PER_BOMB_NORMAL
    if tier == "premium": cost = CREDITS_PER_BOMB_PREMIUM
    elif tier == "nuclear": cost = CREDITS_PER_BOMB_NUCLEAR
    if country == "bd": cost = CREDITS_PER_BOMB_NORMAL

    if row.get("credits", 0) < cost:
        return show(cid, mid, f"<b>❌ Insufficient credits!</b>\nNeed <b>{cost}</b>, you have <b>{row.get('credits',0)}</b>.\n\nRefer friends or buy credits." + FOOTER,
                    KB([B("🎁 Refer & Earn", cb="refer", style="success")],
                       [B("💎 Buy Credits", url=CONTACT_URL, style="danger")],
                       [B("🔙 Menu", cb="menu", style="primary")]))

    if country == "ind" and not tier:
        nuclear_btn = B(f"☢️ Nuclear ({CREDITS_PER_BOMB_NUCLEAR}c)", cb="bomb_ind_nuclear", style="danger")
        if not is_premium:
            nuclear_btn = B(f"🔒 Nuclear ({CREDITS_PER_BOMB_NUCLEAR}c) — Premium", cb="premium_only", style="danger")
        return show(cid, mid, f"<b>🇮🇳 INDIA BOMB — Select Tier</b>\n━━━━━━━━━━━━━━━━━━\n"
                    f"<b>Normal</b> — {CREDITS_PER_BOMB_NORMAL} credit ({IND_NORMAL_APIS} APIs)\n"
                    f"<b>Premium</b> — {CREDITS_PER_BOMB_PREMIUM} credits ({IND_PREMIUM_APIS} APIs)\n"
                    f"<b>Nuclear</b> — {CREDITS_PER_BOMB_NUCLEAR} credits ({IND_NUCLEAR_APIS} APIs) {'🔒 Premium only' if not is_premium else '✅'}" + FOOTER,
                    KB([B(f"💣 Normal ({CREDITS_PER_BOMB_NORMAL}c)", cb="bomb_ind_normal", style="primary"),
                        B(f"⚡ Premium ({CREDITS_PER_BOMB_PREMIUM}c)", cb="bomb_ind_premium", style="success"),
                        nuclear_btn],
                       [B("🔙 Menu", cb="menu", style="primary")]))

    fb_user_set(uid, {"credits": firestore.Increment(-cost)})
    _pending_action[uid] = {"action": "bomb", "country": country, "tier": tier or "normal"}
    return show(cid, mid, f"<b>📱 Enter {country.upper()} number</b>\n<blockquote>Include country code (e.g., 91XXXXXXXXXX or 88XXXXXXXXXX)</blockquote>" + FOOTER,
                KB([B("🔙 Cancel", cb="menu", style="danger")]))

# ═══════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════
admin_state = {}

def _stats():
    if not _db: return {}
    now = int(time.time())
    users = fb_users_all()
    keys = list(_db.collection("keys").stream())
    chans = list(_db.collection("channels").stream())
    day0 = now - 86400
    return {
        "users": len(users),
        "new24": sum(1 for u in users if u.get("joined_at", 0) > day0),
        "banned": sum(1 for u in users if u.get("banned")),
        "keys": sum(1 for k in keys if k.to_dict().get("expires_at", 0) > now and not k.to_dict().get("revoked")),
        "chans": len(chans),
        "bombs": sum(u.get("total_bombs", 0) for u in users),
        "refs": sum(u.get("total_refs", 0) for u in users),
        "credits": sum(u.get("credits", 0) for u in users),
        "premium": sum(1 for u in users if u.get("is_premium")),
    }

def adm_home():
    s = _stats()
    text = ("<b>🛡️ ADMIN CONTROL PANEL</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👥 Users: <b>{s.get('users',0)}</b>   🆕 24h: <b>{s.get('new24',0)}</b>\n"
            f"🔑 Active keys: <b>{s.get('keys',0)}</b>   📢 Channels: <b>{s.get('chans',0)}</b>\n"
            f"💣 Total bombs: <b>{s.get('bombs',0)}</b>   🚫 Banned: <b>{s.get('banned',0)}</b>\n"
            f"💰 Total credits: <b>{s.get('credits',0)}</b>   💎 Premium: <b>{s.get('premium',0)}</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<i>Force-join: {'ON ✅' if force_join_on() else 'OFF ❌'}</i>" + FOOTER)
    return text, KB(
        [B("📊 Statistics", cb="adm:stats", style="primary"), B("👥 Users", cb="adm:users", style="primary")],
        [B("📢 Channels", cb="adm:ch", style="success"), B("📣 Broadcast", cb="adm:bc", style="success")],
        [B("🔑 API Keys", cb="adm:keys", style="primary"), B("⚙️ Settings", cb="adm:set", style="primary")],
        [B("🎟️ Gift Codes", cb="adm:gift", style="success"), B("💾 Export/Import", cb="adm:export", style="primary")],
        [B("💎 Premium Users", cb="adm:prem", style="danger")],
        [B("🌐 Web Panel", url=BASE_URL + "/admin", style="success"), B("💎 Contact", url=CONTACT_URL, style="danger")],
        [B("🔙 Close", cb="menu", style="danger")])

def adm_stats():
    s = _stats()
    text = ("<b>📊 STATISTICS</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total users: <b>{s.get('users',0)}</b>\n🆕 Joined (24h): <b>{s.get('new24',0)}</b>\n"
            f"🚫 Banned: <b>{s.get('banned',0)}</b>\n💣 Total bombs: <b>{s.get('bombs',0)}</b>\n"
            f"🎁 Total referrals: <b>{s.get('refs',0)}</b>\n🔑 Active keys: <b>{s.get('keys',0)}</b>\n"
            f"💰 Total credits: <b>{s.get('credits',0)}</b>\n📢 Channels: <b>{s.get('chans',0)}</b>\n"
            f"💎 Premium users: <b>{s.get('premium',0)}</b>")
    return text, KB([B("🔄 Refresh", cb="adm:stats", style="success"), B("🔙 Back", cb="adm:home", style="danger")])

def adm_channels():
    chans = list_channels()
    lines = [f"{i}. <b>{E(c.get('title') or c.get('chat_id'))}</b>  <code>{E(c.get('chat_id'))}</code>" for i, c in enumerate(chans, 1)]
    text = ("<b>📢 FORCE-JOIN CHANNELS</b>\n━━━━━━━━━━━━━━━━━━\n" +
            ("\n".join(lines) if lines else "<i>No channels yet.</i>") +
            "\n\n<blockquote>The bot must be an <b>admin</b> in every channel. "
            "New channels apply to all users immediately.</blockquote>")
    rows = [[B(f"❌ Remove {c.get('title') or c.get('chat_id')}"[:60], cb=f"adm:chdel:{c.get('chat_id')}", style="danger")] for c in chans]
    rows.append([B("➕ Add Channel", cb="adm:chadd", style="success")])
    rows.append([B("🔙 Back", cb="adm:home", style="primary")])
    return text, KB(*rows)

def adm_users():
    text = ("<b>👥 USER MANAGER</b>\n━━━━━━━━━━━━━━━━━━\nFind a user by ID to ban, unban, give credits, or toggle premium.")
    return text, KB([B("🔍 Find User", cb="adm:ufind", style="success")],
                    [B("🔙 Back", cb="adm:home", style="primary")])

def adm_user_card(uid):
    u = fb_user(uid)
    if not u:
        return "<b>❌ User not found.</b>", KB([B("🔙 Back", cb="adm:users", style="primary")])
    k = active_key(uid)
    text = ("<b>👤 USER</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <code>{uid}</code>\n📛 {E(u.get('first_name') or '-')}  "
            f"{('@' + E(u.get('username'))) if u.get('username') else ''}\n"
            f"📅 Joined: {time.strftime('%Y-%m-%d', time.gmtime(u.get('joined_at', 0)))}\n"
            f"💰 Credits: <b>{u.get('credits',0)}</b>\n"
            f"💎 Premium: <b>{'✅ Yes' if u.get('is_premium') else '❌ No'}</b>\n"
            f"🎁 Refs: <b>{u.get('total_refs',0)}</b> • points <b>{u.get('ref_points',0)}</b>\n"
            f"💣 Bombs: <b>{u.get('total_bombs',0)}</b>\n"
            f"🚫 Banned: <b>{'Yes' if u.get('banned') else 'No'}</b>\n"
            f"🔑 Key: {('<code>' + k['key'] + '</code> — ' + fmt_exp(k['expires_at'])) if k else '<i>none</i>'}")
    ban_btn = (B("✅ Unban", cb=f"adm:uunban:{uid}", style="success") if u.get("banned")
               else B("🚫 Ban", cb=f"adm:uban:{uid}", style="danger"))
    prem_btn = (B("🔓 Remove Premium", cb=f"adm:uunprem:{uid}", style="danger") if u.get("is_premium")
                else B("💎 Make Premium", cb=f"adm:uprem:{uid}", style="success"))
    return text, KB(
        [ban_btn, B("🗑 Revoke Key", cb=f"adm:urev:{uid}", style="danger")],
        [prem_btn],
        [B("💰 +10 Credits", cb=f"adm:ucred:{uid}:10", style="success"),
         B("💰 +50 Credits", cb=f"adm:ucred:{uid}:50", style="success"),
         B("💰 +100 Credits", cb=f"adm:ucred:{uid}:100", style="success")],
        [B("🔑 +7d Key", cb=f"adm:ukey:{uid}:7", style="primary"),
         B("🔑 +30d Key", cb=f"adm:ukey:{uid}:30", style="primary")],
        [B("🔙 Back", cb="adm:users", style="success")])

def adm_keys():
    if not _db: return "❌ Firebase not connected", KB()
    keys = list(_db.collection("keys").order_by("created_at", direction=firestore.Query.DESCENDING).limit(10).stream())
    now = int(time.time())
    lines = []
    for k in keys:
        d = k.to_dict()
        st = "🚫" if d.get("revoked") else ("✅" if d.get("expires_at",0) > now else "⌛")
        lines.append(f"{st} <code>{d['key']}</code> • <code>{d['user_id']}</code>")
    text = ("<b>🔑 API KEYS</b>\n━━━━━━━━━━━━━━━━━━\n" +
            ("\n".join(lines) if lines else "<i>No keys yet.</i>") +
            "\n\n<i>Showing the 10 most recent.</i>")
    return text, KB(
        [B("➕ Generate Key", cb="adm:kgen", style="success"), B("🗑 Revoke Key", cb="adm:krev", style="danger")],
        [B("🔙 Back", cb="adm:home", style="primary")])

def adm_gift():
    if not _db: return "❌ Firebase not connected", KB()
    gifts = list(_db.collection("gift_codes").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream())
    lines = []
    for g in gifts:
        d = g.to_dict()
        st = "✅" if not d.get("expires_at") or d["expires_at"] > int(time.time()) else "⌛"
        lines.append(f"{st} <code>{d['code']}</code> • {d['credits']} credits • {d.get('claimed_count',0)}/{d.get('max_users') or '∞'}")
    text = ("<b>🎟️ GIFT CODES</b>\n━━━━━━━━━━━━━━━━━━\n" +
            ("\n".join(lines) if lines else "<i>No gift codes yet.</i>"))
    return text, KB(
        [B("➕ Create Gift Code", cb="adm:giftadd", style="success")],
        [B("🔙 Back", cb="adm:home", style="primary")])

def adm_prem():
    if not _db: return "❌ Firebase not connected", KB()
    users = [d.to_dict() for d in _db.collection("users").where("is_premium", "==", True).limit(20).stream()]
    lines = []
    for u in users:
        lines.append(f"💎 <code>{u['id']}</code> — {E(u.get('first_name') or '-')} (@{E(u.get('username') or 'N/A')})")
    text = ("<b>💎 PREMIUM USERS</b>\n━━━━━━━━━━━━━━━━━━\n" +
            ("\n".join(lines) if lines else "<i>No premium users yet.</i>"))
    return text, KB([B("🔙 Back", cb="adm:home", style="primary")])

def adm_settings():
    text = ("<b>⚙️ SETTINGS</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🔒 Force-join: <b>{'ON ✅' if force_join_on() else 'OFF ❌'}</b>\n"
            f"📊 Daily API limit / key: <b>{daily_limit()}</b>\n"
            f"💰 Credits per referral: <b>{CREDITS_PER_REFERRAL}</b>\n"
            f"💣 Bomb costs: Normal <b>{CREDITS_PER_BOMB_NORMAL}</b> · Premium <b>{CREDITS_PER_BOMB_PREMIUM}</b> · Nuclear <b>{CREDITS_PER_BOMB_NUCLEAR}</b>\n"
            f"💬 Contact: <b>@{E(CONTACT_USERNAME)}</b>\n"
            f"🌐 Base URL: <code>{E(BASE_URL)}</code>\n\n"
            "<b>🏆 Referral Plans</b>\n" +
            "\n".join(f"• {c} refs → {l} API key" for c, d, l in PLANS))
    return text, KB(
        [B("🔒 Toggle Force-Join", cb="adm:settog", style="primary"), B("📊 Set Daily Limit", cb="adm:setlim", style="success")],
        [B("🔙 Back", cb="adm:home", style="danger")])

def _broadcast(admin_cid, text):
    users = fb_users_all()
    ok = bad = 0
    for u in users:
        if u.get("banned"): continue
        uid = u["id"]
        for _ in range(2):
            try:
                send(uid, text + FOOTER)
                ok += 1
                break
            except TGError as e:
                if e.retry_after:
                    time.sleep(e.retry_after + 1)
                    continue
                bad += 1
                break
        time.sleep(0.05)
    send(admin_cid, f"<b>📣 BROADCAST DONE</b>\n✅ Sent: <b>{ok}</b>\n❌ Failed: <b>{bad}</b>",
         KB([B("🔙 Admin Panel", cb="adm:home", style="primary")]))

def on_admin_callback(uid, cid, mid, data, ack):
    parts = data.split(":")
    act = parts[1] if len(parts) > 1 else "home"
    prev_state = admin_state.pop(uid, None)

    if act == "home": return show(cid, mid, *adm_home())
    if act == "stats": return show(cid, mid, *adm_stats())
    if act == "ch": return show(cid, mid, *adm_channels())
    if act == "chadd":
        admin_state[uid] = {"mode": "add_channel"}
        return show(cid, mid, "<b>➕ ADD CHANNEL</b>\n━━━━━━━━━━━━━━━━━━\nSend the channel <code>@username</code> or "
                    "<code>-100…</code> ID.\nPrivate channel? Send <code>-100ID https://t.me/+invite</code>.\n\n"
                    "<i>The bot must already be an admin there.</i>",
                    KB([B("❌ Cancel", cb="adm:ch", style="danger")]))
    if act == "chdel":
        fb_channel_del(parts[2])
        ack("Channel removed")
        return show(cid, mid, *adm_channels())
    if act == "bc":
        admin_state[uid] = {"mode": "broadcast"}
        return show(cid, mid, "<b>📣 BROADCAST</b>\n━━━━━━━━━━━━━━━━━━\nSend the message to broadcast "
                    "(HTML allowed: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;a href&gt;</code>).",
                    KB([B("❌ Cancel", cb="adm:home", style="danger")]))
    if act == "bcgo":
        txt = (prev_state or {}).get("text")
        if not txt: return ack("Nothing to send", True)
        ack("Broadcast started")
        threading.Thread(target=_broadcast, args=(cid, txt), daemon=True).start()
        return show(cid, mid, "<b>📣 Broadcasting…</b> you'll get a report when finished.")
    if act == "users": return show(cid, mid, *adm_users())
    if act == "ufind":
        admin_state[uid] = {"mode": "find_user"}
        return show(cid, mid, "<b>🔍 FIND USER</b>\nSend the user's numeric Telegram ID.",
                    KB([B("❌ Cancel", cb="adm:users", style="danger")]))
    if act in ("uban", "uunban"):
        t = parts[2]
        fb_user_update(t, banned=(act == "uban"))
        ack("Done")
        return show(cid, mid, *adm_user_card(t))
    if act in ("uprem", "uunprem"):
        t = parts[2]
        fb_user_update(t, is_premium=(act == "uprem"))
        ack("Premium updated")
        return show(cid, mid, *adm_user_card(t))
    if act == "urev":
        t = parts[2]
        if _db:
            for k in _db.collection("keys").where("user_id", "==", str(t)).stream():
                k.reference.update({"revoked": True})
        ack("Keys revoked")
        return show(cid, mid, *adm_user_card(t))
    if act == "ukey":
        t, days = parts[2], int(parts[3])
        grant_key(t, days, f"Admin {days}d")
        ack("Key granted")
        return show(cid, mid, *adm_user_card(t))
    if act == "ucred":
        t, amt = parts[2], int(parts[3])
        add_credits(t, amt)
        ack(f"+{amt} credits")
        return show(cid, mid, *adm_user_card(t))
    if act == "keys": return show(cid, mid, *adm_keys())
    if act == "kgen":
        admin_state[uid] = {"mode": "gen_key"}
        return show(cid, mid, "<b>➕ GENERATE KEY</b>\nSend: <code>USER_ID DAYS</code>  (e.g. <code>123456789 30</code>)",
                    KB([B("❌ Cancel", cb="adm:keys", style="danger")]))
    if act == "krev":
        admin_state[uid] = {"mode": "revoke_key"}
        return show(cid, mid, "<b>🗑 REVOKE KEY</b>\nSend the full key to revoke.",
                    KB([B("❌ Cancel", cb="adm:keys", style="danger")]))
    if act == "gift": return show(cid, mid, *adm_gift())
    if act == "giftadd":
        admin_state[uid] = {"mode": "create_gift"}
        return show(cid, mid, "<b>🎟️ CREATE GIFT CODE</b>\nSend: <code>CREDITS MAX_USERS DAYS_VALID</code>\n"
                    "Example: <code>50 100 7</code> (50 credits, 100 users, valid 7 days)",
                    KB([B("❌ Cancel", cb="adm:gift", style="danger")]))
    if act == "prem": return show(cid, mid, *adm_prem())
    if act == "set": return show(cid, mid, *adm_settings())
    if act == "settog":
        set_setting("force_join", "0" if force_join_on() else "1")
        return show(cid, mid, *adm_settings())
    if act == "setlim":
        admin_state[uid] = {"mode": "set_limit"}
        return show(cid, mid, "<b>📊 DAILY LIMIT</b>\nSend a number (requests per key per day).",
                    KB([B("❌ Cancel", cb="adm:set", style="danger")]))
    if act == "export":
        if _db:
            users = [d.to_dict() for d in _db.collection("users").stream()]
            keys = [d.to_dict() for d in _db.collection("keys").stream()]
            gifts = [d.to_dict() for d in _db.collection("gift_codes").stream()]
            chans = [d.to_dict() for d in _db.collection("channels").stream()]
            payload = json.dumps({"users": users, "keys": keys, "gifts": gifts, "channels": chans}, default=str)
            _send_document(cid, "exodus_export.json", payload.encode())
        return show(cid, mid, "<b>✅ Export sent!</b>", KB([B("🔙 Admin Panel", cb="adm:home", style="primary")]))
    return ack()

def _send_document(cid, filename, data_bytes):
    try:
        tg("sendDocument", chat_id=cid, document=("upload", filename, data_bytes))
    except TGError as e:
        print(f"[Bot] sendDocument error: {e.desc}", flush=True)

def on_admin_input(uid, cid, text):
    st = admin_state.get(uid) or {}
    mode = st.get("mode")
    back = lambda cb: KB([B("🔙 Back", cb=cb, style="primary")])
    try:
        if mode == "add_channel":
            parts = text.split()
            if not parts: raise ValueError("Send @username or -100ID")
            ref, link_in = parts[0], (parts[1] if len(parts) > 1 else None)
            m = re.match(r"https?://t\.me/([A-Za-z0-9_]{4,})/?$", ref)
            if m: ref = "@" + m.group(1)
            if re.fullmatch(r"-?\d+", ref): chat_ref = int(ref)
            elif ref.startswith("@"): chat_ref = ref
            else: raise ValueError("Use @username or -100ID")
            try:
                chat = tg("getChat", chat_id=chat_ref)
            except TGError as e:
                raise ValueError(f"Cannot access: {e.desc}")
            try:
                me = tg("getChatMember", chat_id=chat["id"], user_id=BOT_ID)
            except TGError as e:
                raise ValueError(f"Bot not in chat: {e.desc}")
            if me.get("status") not in ("administrator", "creator"):
                raise ValueError("Make bot admin first")
            if chat.get("username"): link = f"https://t.me/{chat['username']}"
            elif link_in and link_in.startswith("http"): link = link_in
            else:
                try: link = tg("createChatInviteLink", chat_id=chat["id"], name="Exodus")["invite_link"]
                except TGError: raise ValueError("Private channel: send -100ID https://t.me/+invite")
            title = chat.get("title") or chat.get("username") or str(chat["id"])
            fb_channel_add(str(chat["id"]), title, link)
            admin_state.pop(uid, None)
            send(cid, f"<b>✅ CHANNEL ADDED</b>\n<b>{E(title)}</b>", back("adm:ch"))
        elif mode == "broadcast":
            try: send(cid, "<b>👀 PREVIEW</b>\n\n" + text + FOOTER)
            except TGError as e:
                return send(cid, f"❌ Invalid HTML: {E(e.desc)}")
            st["text"] = text
            send(cid, "Send to all users?", KB([B("✅ Send Now", cb="adm:bcgo", style="success"), B("❌ Cancel", cb="adm:home", style="danger")]))
            st["mode"] = "confirm"
        elif mode == "find_user":
            if not text.strip().isdigit(): return send(cid, "❌ Numeric ID only")
            admin_state.pop(uid, None)
            send(cid, *adm_user_card(text.strip()))
        elif mode == "gen_key":
            p = text.split()
            if len(p) != 2 or not (p[0].isdigit() and p[1].isdigit()) or not (1 <= int(p[1]) <= 3650):
                return send(cid, "❌ Format: USER_ID DAYS")
            if not fb_user(p[0]): return send(cid, "❌ User not found")
            key, exp = grant_key(p[0], int(p[1]), f"Admin {p[1]}d")
            admin_state.pop(uid, None)
            send(cid, f"<b>✅ KEY READY</b>\n<code>{key}</code>\n⏳ {fmt_exp(exp)}", back("adm:keys"))
            try:
                kt, km = key_card(key, exp, f"{p[1]} Days")
                send(p[0], kt, km)
            except TGError: pass
        elif mode == "revoke_key":
            if _db:
                _db.collection("keys").document(text.strip()).update({"revoked": True})
            admin_state.pop(uid, None)
            send(cid, "✅ Revoked.", back("adm:keys"))
        elif mode == "create_gift":
            p = text.split()
            if len(p) != 3 or not all(x.isdigit() for x in p):
                return send(cid, "❌ Format: CREDITS MAX_USERS DAYS")
            credits, max_users, days = int(p[0]), int(p[1]), int(p[2])
            if credits <= 0: return send(cid, "❌ Credits must be > 0")
            code = "EXO-GIFT-" + secrets.token_hex(4).upper()
            exp = int(time.time()) + days * 86400 if days > 0 else 0
            fb_gift_set(code, {"code": code, "credits": credits, "max_users": max_users,
                               "claimed_count": 0, "expires_at": exp, "created_at": int(time.time())})
            admin_state.pop(uid, None)
            send(cid, f"<b>✅ GIFT CODE CREATED</b>\n<code>{code}</code>\n💰 {credits} credits\n"
                      f"👥 {max_users or '∞'} users\n⏳ {fmt_exp(exp) if exp else 'No expiry'}", back("adm:gift"))
        elif mode == "set_limit":
            if not text.strip().isdigit() or int(text) < 1: return send(cid, "❌ Positive number only")
            set_setting("daily_limit", int(text))
            admin_state.pop(uid, None)
            send(cid, f"✅ Daily limit set to <b>{int(text)}</b>.", back("adm:set"))
    except ValueError as e:
        send(cid, f"❌ {e}", KB([B("🔙 Cancel", cb="adm:ch" if mode == "add_channel" else "adm:home", style="danger")]))

# ═══════════════════════════════════════════════════════════════
#  UPDATE ROUTER
# ═══════════════════════════════════════════════════════════════
def on_message(m):
    chat = m.get("chat") or {}
    if chat.get("type") != "private" or not m.get("from"): return
    frm, cid = m["from"], chat["id"]
    uid = frm["id"]
    text = (m.get("text") or "").strip()
    if not text: return

    ref = None
    if text.startswith("/start"):
        p = text.split(maxsplit=1)
        if len(p) > 1 and p[1].startswith("ref_") and p[1][4:].isdigit():
            ref = int(p[1][4:])
    row, _new = upsert_user(frm, ref)
    if row and row.get("banned") and uid not in ADMIN_IDS:
        return send(cid, "🚫 <b>You are banned.</b>" + FOOTER)

    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0].lower()
        if cmd == "/cancel":
            admin_state.pop(uid, None); _pending_action.pop(uid, None)
            return send(cid, "✅ Cancelled.")
        if cmd == "/admin":
            if uid not in ADMIN_IDS: return
            admin_state.pop(uid, None)
            return send(cid, *adm_home())
        if cmd == "/buy":
            return send(cid, *screen_buy(uid))
        if not gate(uid, cid): return
        if cmd in ("/start", "/menu", "/help"):
            try_count_referral(uid)
            return send(cid, *screen_menu(uid, frm.get("first_name")))
        if cmd == "/refer": return send(cid, *screen_refer(uid))
        if cmd in ("/key", "/mykey"): return send(cid, *screen_key(uid))
        if cmd in ("/api", "/docs"): return send(cid, *screen_docs(uid))
        if cmd == "/credits": return send(cid, *screen_credits(uid))
        if cmd == "/gift": return send(cid, *screen_gift(uid))
        return send(cid, *screen_menu(uid, frm.get("first_name")))

    if uid in ADMIN_IDS and uid in admin_state:
        return on_admin_input(uid, cid, text)

    pend = _pending_action.get(uid)
    if pend and pend.get("action") == "bomb" and text.isdigit():
        country = pend["country"]
        tier = pend["tier"]
        _pending_action.pop(uid, None)
        return handle_bomb(uid, cid, country, tier, text)

    if text.upper().startswith("EXO-GIFT-"):
        return handle_gift_code(uid, cid, text)

    if not gate(uid, cid): return
    send(cid, "<b>💣 Choose an option from the menu</b>" + FOOTER, menu_markup(uid))

def on_callback(cq):
    uid = cq["from"]["id"]
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    cid = (msg.get("chat") or {}).get("id")
    mid = msg.get("message_id")
    done = {"v": False}

    def ack(text=None, alert=False):
        if done["v"]: return
        done["v"] = True
        p = {"callback_query_id": cq["id"]}
        if text: p.update(text=text, show_alert=alert)
        try: tg("answerCallbackQuery", **p)
        except TGError: pass

    if not cid: return ack()
    row, _ = upsert_user(cq["from"])
    if row and row.get("banned") and uid not in ADMIN_IDS:
        return ack("🚫 Banned.", True)

    if data.startswith("adm:"):
        if uid not in ADMIN_IDS: return ack("Admins only", True)
        on_admin_callback(uid, cid, mid, data, ack)
        return ack()

    if data == "verify":
        _member_cache.clear()
        miss = missing_channels(uid)
        if miss:
            ack("❌ Join all channels first!", True)
            return join_prompt(cid, mid, miss)
        ack("✅ Verified!")
        try_count_referral(uid)
        pend = _pending_action.pop(uid, None)
        if pend and pend.get("action") == "bomb":
            return start_bomb_flow(uid, cid, mid, pend["country"], pend.get("tier"))
        return show(cid, mid, *screen_menu(uid, cq["from"].get("first_name")))

    if data == "noop": return ack()
    if not gate(uid, cid, mid): return ack()

    if data == "menu": return show(cid, mid, *screen_menu(uid, cq["from"].get("first_name")))
    if data == "credits": return show(cid, mid, *screen_credits(uid))
    if data == "refer": return show(cid, mid, *screen_refer(uid))
    if data == "mykey": return show(cid, mid, *screen_key(uid))
    if data == "docs": return show(cid, mid, *screen_docs(uid))
    if data == "buy": return show(cid, mid, *screen_buy(uid))
    if data == "gift": return show(cid, mid, *screen_gift(uid))
    if data == "premium_only":
        ack("💎 Premium only", True)
        return show(cid, mid, "<b>🔒 PREMIUM ONLY</b>\n━━━━━━━━━━━━━━━━━━\n"
                    "<blockquote>Nuclear Bomb is available only for premium users.\n"
                    f"Contact @{E(CONTACT_USERNAME)} to upgrade.</blockquote>" + FOOTER,
                    KB([B("💎 Get Premium", url=CONTACT_URL, style="danger")],
                       [B("🔙 Menu", cb="menu", style="primary")]))

    if data == "bomb_ind": return start_bomb_flow(uid, cid, mid, "ind")
    if data == "bomb_bd": return start_bomb_flow(uid, cid, mid, "bd")
    if data == "bomb_ind_normal": return start_bomb_flow(uid, cid, mid, "ind", "normal")
    if data == "bomb_ind_premium": return start_bomb_flow(uid, cid, mid, "ind", "premium")
    if data == "bomb_ind_nuclear": return start_bomb_flow(uid, cid, mid, "ind", "nuclear")

    if data.startswith("claim:"):
        try:
            idx = int(data.split(":")[1])
            if not 0 <= idx < len(PLANS): return ack()
            res = claim_plan(uid, idx)
        except (ValueError, IndexError): return ack()
        if not res:
            ack("Not enough referral points", True)
            return show(cid, mid, *screen_refer(uid))
        ack("🎉 Key unlocked!")
        key, exp = res
        return show(cid, mid, *key_card(key, exp, PLANS[idx][2]))

def _safe(fn, obj):
    try: fn(obj)
    except Exception as e:
        print(f"[Bot] handler error: {type(e).__name__}: {e}", flush=True)

def _poll_loop():
    pool = ThreadPoolExecutor(max_workers=24, thread_name_prefix="tgbot")
    offset = None
    try: tg("deleteWebhook", drop_pending_updates=False)
    except TGError: pass
    print(f"[Bot] @{BOT_USERNAME} polling…", flush=True)
    while True:
        try:
            params = dict(timeout=50, allowed_updates=["message", "callback_query"])
            if offset is not None: params["offset"] = offset
            for u in tg("getUpdates", _t=70, **params):
                offset = u["update_id"] + 1
                if "message" in u: pool.submit(_safe, on_message, u["message"])
                elif "callback_query" in u: pool.submit(_safe, on_callback, u["callback_query"])
        except TGError as e:
            print(f"[Bot] poll error: {e.desc}", flush=True)
            time.sleep(max(3, e.retry_after))
        except Exception as e:
            print(f"[Bot] poll crash: {e}", flush=True)
            time.sleep(5)

def start_bot(port):
    global BOT_TOKEN, BOT_ID, BOT_USERNAME, BASE_URL, LOCAL_PORT, ADMIN_IDS
    LOCAL_PORT = port
    BASE_URL = os.environ.get("BASE_URL", f"http://localhost:{port}").strip().rstrip("/")
    ADMIN_IDS = {int(x) for x in re.findall(r"-?\d+", os.environ.get("ADMIN_IDS", ""))}
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
    if not BOT_TOKEN:
        print("⚠️  BOT_TOKEN not set — Telegram bot disabled.", flush=True)
        return False
    try: me = tg("getMe")
    except TGError as e:
        print(f"⚠️  Bot token rejected: {e.desc}", flush=True)
        return False
    BOT_ID, BOT_USERNAME = me["id"], me.get("username", "")
    if not ADMIN_IDS:
        print("⚠️  ADMIN_IDS empty — nobody can open the bot admin panel.", flush=True)
    threading.Thread(target=_poll_loop, daemon=True, name="tg-poll").start()
    return True