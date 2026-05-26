# Deploy MARK XXXIX PWA (Netlify + Local Ollama)

The PWA has **two parts**:

| Part | Where it runs | What it does |
|------|---------------|--------------|
| **Frontend (PWA)** | Netlify (free) | UI on phone/desktop — installable app |
| **Backend** | Your Mac | Ollama, Whisper, TTS, tools (YouTube, apps, files…) |

Netlify cannot run Ollama. Your Mac is the brain; Netlify is the remote control screen.

---

## Recommended: permanent setup (no URL prompt, auto-start)

Quick Cloudflare tunnels (`trycloudflare.com`) change every restart and need a terminal open. **Use a named tunnel + your own domain instead.**

### One-time setup (~15 minutes)

**Requirements:** a domain on Cloudflare (free plan is fine), e.g. `jarvis.yourdomain.com`

```bash
cd /Users/raaj/Raaj-Jarvis

# 1. Create permanent HTTPS URL (never changes)
./scripts/setup-named-tunnel.sh

# 2. Auto-start backend + tunnel when Mac logs in (no manual terminal)
./scripts/install-autostart.sh
```

**Netlify (one-time):**

1. Site settings → **Environment variables**
2. Add `JARVIS_API_URL` = `https://jarvis.yourdomain.com` (your subdomain from step 1)
3. **Redeploy** the site

After that:

- Phone app **connects automatically** — no backend URL screen
- URL **never changes** for you or anyone using the app
- Mac login **starts JARVIS** — you don't run `./run_remote.sh` manually
- App works whenever your Mac is on and awake (Ollama runs locally)

### When the Mac is off

The backend is on your Mac. If the Mac sleeps or is powered off, the app is offline — that is expected with free local Ollama.

To use JARVIS **without your Mac on**, you'd need an always-on server (VPS with Ollama, ~$5–10/mo) — different architecture.

---

## Quick / dev setup (temporary tunnel)

For testing only:

```bash
./run_remote.sh   # temporary https://….trycloudflare.com — changes each restart
```

Paste the URL in PWA settings. Not suitable for daily use.

---

## Run the backend on your Mac

```bash
cd /Users/raaj/Raaj-Jarvis
ollama serve          # or open Ollama app
./run_pwa.sh          # manual start (or use install-autostart.sh)
```

Backend listens on **http://0.0.0.0:8765**.

---

## Deploy frontend to Netlify

### Option A — Git connect (recommended)

1. Push this repo to GitHub
2. [Netlify](https://app.netlify.com) → **Add new site** → Import from Git
3. Build settings (auto-detected from `netlify.toml`):
   - **Publish directory:** `web/static`
   - **Build command:** `npm run build`
4. Set `JARVIS_API_URL` env var (see permanent setup above)
5. Deploy

### Option B — Manual drag & drop

```bash
JARVIS_API_URL=https://jarvis.yourdomain.com npm run build
# Drag web/static to Netlify Drop
```

---

## Connect phone to your Mac

### Same Wi‑Fi (no Netlify, no tunnel)

Open `http://YOUR-MAC-IP:8765` in Safari/Chrome → **Add to Home Screen**. Works only on your home network.

### Netlify PWA (anywhere)

Use the **permanent setup** above. The app auto-connects via `JARVIS_API_URL` baked in at build time.

---

## Install on phone

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
| "Could not connect" | Mac on and awake? Run `./scripts/jarvis-stack.sh status` |
| Setup URL screen still shows | Set `JARVIS_API_URL` in Netlify and redeploy |
| HTTPS / mixed content | Use named tunnel HTTPS URL, not `http://192.168.x.x` |
| No voice on phone | Allow mic permission; tap 🎤 to activate |
| Tools do nothing | Tools control the **Mac**, not the phone |

---

## Local-only (no Netlify)

Open **http://localhost:8765** after `./run_pwa.sh` — backend serves the PWA directly.
