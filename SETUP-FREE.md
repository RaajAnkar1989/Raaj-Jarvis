# Free HTTPS — no domain, no URL prompt

Use **[raajarvis.netlify.app](https://raajarvis.netlify.app/)** with **zero manual backend URL**.

## How it works

```
Mac (on login)                    GitHub                         Phone
─────────────                    ───────                         ─────
1. Start Ollama + backend
2. Start free Cloudflare HTTPS
3. Publish URL ──────────────►  data/public-backend-url.txt
                                                                4. Netlify app fetches URL
                                                                5. Connects automatically
```

- **No domain** to buy
- **No URL** to paste in the app
- **No Netlify env vars** required
- Mac manages everything via `./scripts/setup-free-https.sh`

## One-time setup (~5 min)

```bash
cd /Users/raaj/Raaj-Jarvis
./scripts/setup-free-https.sh
```

This will:

1. Log in to GitHub (`gh auth login`) — used to publish your backend URL
2. Install autostart (backend + tunnel when you log in)
3. Enable free tunnel mode

Then push to GitHub (so Netlify gets the discovery code):

```bash
git add -A
git commit -m "free https auto-discovery"
git push
```

Netlify redeploys automatically.

## Daily use

1. Mac is on (JARVIS starts on login)
2. Open https://raajarvis.netlify.app/
3. Wait ~30 seconds first time (tunnel + GitHub update)
4. App connects — speak or type

## Manual start

```bash
./scripts/jarvis-stack.sh start
./scripts/jarvis-stack.sh status
```

## Tradeoffs (honest)

| | Free auto-discovery | Paid domain |
|--|---------------------|-------------|
| Cost | Free | ~$10/yr domain |
| URL in app | Automatic | Automatic |
| URL stability | Changes if tunnel restarts* | Never changes |
| Mac must be on | Yes | Yes |

\*When the tunnel restarts, your Mac republishes the new URL to GitHub. The phone app picks it up within ~30s. You never paste anything.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Looking for JARVIS…" forever | Mac on? Run `./scripts/jarvis-stack.sh status` |
| GitHub publish failed | Run `gh auth login` |
| Old URL cached | Close app, reopen (or wait 30s) |
| Same Wi‑Fi shortcut | http://192.168.0.64:8765 — no GitHub needed |
