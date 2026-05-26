# Setup for https://raajarvis.netlify.app

Your Netlify site is the **frontend** (UI). Your Mac is the **backend** (Ollama, voice, tools).  
You keep using [raajarvis.netlify.app](https://raajarvis.netlify.app/) — users never enter a URL once configured.

---

## Step 1 — Permanent backend URL on your Mac (one time)

You need a **fixed HTTPS URL** for your Mac backend (e.g. `https://jarvis.yourdomain.com`).

Requirements: a domain on Cloudflare (free plan).

```bash
cd /Users/raaj/Raaj-Jarvis
./scripts/setup-named-tunnel.sh
# Enter e.g. jarvis.yourdomain.com when prompted

./scripts/install-autostart.sh
# Starts backend + tunnel when you log in
```

Copy the HTTPS URL printed at the end (example: `https://jarvis.yourdomain.com`).

---

## Step 2 — Configure Netlify (one time)

1. Open [Netlify → raajarvis → Environment variables](https://app.netlify.com/)
2. Add variable:
   - **Key:** `JARVIS_API_URL`
   - **Value:** `https://jarvis.yourdomain.com` (your URL from step 1)
3. **Deploys → Trigger deploy → Deploy site**

After redeploy, [raajarvis.netlify.app](https://raajarvis.netlify.app/) will:

- Skip the “Connect to JARVIS Core” screen
- Proxy API calls through Netlify (same origin)
- Connect WebSocket directly to your Mac backend (automatic)

---

## Step 3 — Use on phone

1. Open https://raajarvis.netlify.app/
2. Add to Home Screen (Safari → Share → Add to Home Screen)
3. Tap 🎤 once — speak naturally

No backend URL to paste. Works for anyone you share the Netlify link with.

---

## Without a custom domain

If you don't have a domain yet, you can still use Netlify with a **temporary** tunnel:

```bash
./run_remote.sh
```

Paste the `https://….trycloudflare.com` URL into Netlify `JARVIS_API_URL` and redeploy.  
The URL changes every restart — not recommended for daily use.

**Same Wi‑Fi shortcut (no Netlify):** http://192.168.0.64:8765

---

## Checklist

| Step | Done? |
|------|-------|
| Named tunnel on Mac | ☐ |
| Autostart installed | ☐ |
| `JARVIS_API_URL` in Netlify | ☐ |
| Netlify redeployed | ☐ |
| Mac on + Ollama running | ☐ |
