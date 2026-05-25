# Raaj-Jarvis / MARK XXXIX (Local)

Fork of [FatihMakes/Mark-XXXIX](https://github.com/FatihMakes/Mark-XXXIX) with **free local Ollama** support — same desktop app, same tools, same UI. Optional Gemini cloud mode if you add an API key.

---

## Two modes (same app)

| Mode | Command | Voice | Cost |
|------|---------|-------|------|
| **Local (recommended)** | `llm_provider: ollama` | Whisper STT + neural JARVIS TTS | Free |
| **Cloud (original)** | `llm_provider: gemini` | Gemini Live real-time audio (Charon voice) | Gemini API usage |

Use **`python main.py`** for the full MARK XXXIX desktop experience (HUD, file drop, system monitor).  
Use **`./run_pwa.sh`** for phone/tablet access. Deploy the UI to **Netlify** (see **`DEPLOY-PWA.md`**) — backend with Ollama runs on your Mac.

---

## Quick Start (Local Ollama — no API key)

```bash
cd Raaj-Jarvis
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-macos.txt   # macOS
pip install -r requirements-desktop.txt # Windows/Linux
playwright install chromium
cp config/api_keys.example.json config/api_keys.json
```

Start Ollama and pull a model:

```bash
ollama serve          # or open the Ollama app
ollama pull llama3.2
```

Launch JARVIS:

```bash
python main.py
```

On first boot, choose **Local Ollama** in the setup overlay (default). No Gemini key required.

---

## Quick Start (Gemini — original upstream behaviour)

Edit `config/api_keys.json`:

```json
{
  "llm_provider": "gemini",
  "gemini_api_key": "AIza…",
  "os_system": "mac"
}
```

Get a free key: [Google AI Studio](https://aistudio.google.com/apikey)

```bash
python main.py
```

---

## Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice |
| **Ollama** | Required for local mode ([ollama.com](https://ollama.com)) |
| **Gemini key** | Optional — only for cloud mode |

---

## Upstream

Based on [FatihMakes/Mark-XXXIX](https://github.com/FatihMakes/Mark-XXXIX).  
License: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — personal, non-commercial use.
