# 💣 Exodus SMS Bomber — Setup Guide

## Files

```
Main.py              — Flask API server + bomb engine
bot.py               — Telegram bot (long-poll)
.env                 — Your config (copy from .env.example)
Proxies.txt          — ip:port:user:pass (one per line)
requirements.txt     — Python deps
pterodactyl_egg.json — Import this into Pterodactyl panel
start.sh             — Run on Termux / Linux VPS
start.bat            — Run on Windows CMD
```

---

## ─── VERSION 1 — Termux / VPS / CMD ───────────────────────

### Termux (Android)
```bash
pkg update && pkg install python git -y
cd ~/storage/shared          # or wherever you put the files
chmod +x start.sh
./start.sh
```

### Linux VPS (Ubuntu / Debian)
```bash
sudo apt update && sudo apt install python3 python3-pip -y
chmod +x start.sh
./start.sh
```
```
### Manual (any platform)
```bash
pip install flask requests firebase-admin urllib3 --break-system-packages
cp .env.example .env
# Edit .env — set BOT_TOKEN and ADMIN_IDS at minimum
python Main.py
```