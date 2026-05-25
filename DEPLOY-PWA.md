# Deploy MARK XXXIX PWA (Netlify + Local Ollama)

The PWA has **two parts**:

| Part | Where it runs | What it does |
|------|---------------|--------------|
| **Frontend (PWA)** | Netlify (free) | UI on phone/desktop — installable app |
| **Backend** | Your Mac | Ollama, Whisper, TTS, tools (YouTube, apps, files…) |

Netlify cannot run Ollama. Your Mac is the brain; Netlify is the remote control screen.

---

## 1. Run the backend on your Mac

```bash
cd /Users/raaj/Raaj-Jarvis
ollama serve          # or open Ollama app
./run_pwa.sh
```

Backend listens on **http://0.0.0.0:8765** (all devices on your Wi‑Fi can reach it).

---

## 2. Deploy frontend to Netlify

### Option A — Git connect (recommended)

1. Push this repo to GitHub
2. [Netlify](https://app.netlify.com) → **Add new site** → Import from Git
3. Build settings (auto-detected from `netlify.toml`):
   - **Publish directory:** `web/static`
   - **Build command:** `bash scripts/prepare-pwa-assets.sh`
4. Deploy

### Option A — Manual drag & drop

```bash
bash scripts/prepare-pwa-assets.sh
# Drag the web/static folder to Netlify Drop
```

---

## 3. Connect phone to your Mac

### Same Wi‑Fi (easiest)

**Option 1 — skip Netlify on phone:** open `http://YOUR-MAC-IP:8765` in Safari/Chrome (backend serves the PWA). Install to home screen from there.

**Option 2 — Netlify PWA:** requires **HTTPS backend** (browsers block http from https pages). Use Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://localhost:8765
```

Paste the `https://….trycloudflare.com` URL in PWA settings.

### Away from home (optional)

Expose your Mac backend with a tunnel:

```bash
# Cloudflare Tunnel (free)
cloudflared tunnel --url http://localhost:8765

# or ngrok
ngrok http 8765
```

Use the HTTPS URL in PWA settings.

---

## 4. Install on phone

- **iPhone:** Safari → Share → **Add to Home Screen**
- **Android:** Chrome → menu → **Install app**

Tap **🎤 once** to activate voice, then speak naturally.

---

## Features (same as desktop)

- Local **Ollama** LLM (config in `config/api_keys.json`)
- All **tools** run on your Mac (open apps, YouTube, browser, weather, files…)
- **Voice:** browser mic → server Whisper → chat
- **TTS:** Andrew neural voice → plays on phone
- **File upload:** drag/drop or tap file zone
- **Text chat** fallback

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Could not connect" | Is `./run_pwa.sh` running? Same Wi‑Fi? |
| No voice on phone | Allow mic permission; tap 🎤 to activate |
| Tools do nothing | Tools control the **Mac**, not the phone |
| Old UI after update | Remove home-screen icon, reinstall PWA |

---

## Local-only (no Netlify)

Open **http://localhost:8765** after `./run_pwa.sh` — backend serves the PWA directly.
