#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  EXODUS SMS BOMBER — Universal Startup
#  Works on: Termux (Android) · Linux VPS · Ubuntu · Debian · WSL
# ═══════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

PYTHON=""
for cmd in python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c 'import sys; print(sys.version_info >= (3,9))' 2>/dev/null)
        if [ "$VER" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ Python 3.9+ not found. Install it first:"
    echo "   Termux:    pkg install python"
    echo "   Ubuntu:    sudo apt install python3 python3-pip -y"
    echo "   Fedora:    sudo dnf install python3 python3-pip -y"
    exit 1
fi

echo "✅ Using $PYTHON ($($PYTHON --version))"

# ─── Install dependencies ────────────────────────────────────
echo "📦 Installing dependencies…"
$PYTHON -m pip install --upgrade pip -q
$PYTHON -m pip install flask requests firebase-admin urllib3 --break-system-packages -q 2>/dev/null \
    || $PYTHON -m pip install flask requests firebase-admin urllib3 -q

# ─── Create .env if missing ──────────────────────────────────
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env from template…"
    cp .env.example .env 2>/dev/null || cat > .env << 'ENVEOF'
BOT_TOKEN=
ADMIN_IDS=
ADMIN_PASSWORD=Exodus_OWN3R
DEVELOPER_TAG=@exodus_own3r
DEVELOPER_URL=https://t.me/exodus_own3r
CONTACT_USERNAME=exodus_own3r
BASE_URL=http://localhost:5000
PORT=5000
PROXY_FILE=Proxies.txt
USE_PROXY=true
REQUIRE_API_KEY=true
API_DAILY_LIMIT=500
PROXY_MULTIPLIER=10
SQLITE_PATH=exodus_bot.db
ENVEOF
    echo "⚠️  Fill in .env before running (BOT_TOKEN and ADMIN_IDS required)"
    read -p "Open .env now? [Y/n] " yn
    if [[ "$yn" != "n" && "$yn" != "N" ]]; then
        ${EDITOR:-nano} .env
    fi
fi

# ─── Launch ──────────────────────────────────────────────────
echo ""
echo "🚀 Starting Exodus Bomber…"
echo "   Press Ctrl+C to stop"
echo ""
exec $PYTHON Main.py
