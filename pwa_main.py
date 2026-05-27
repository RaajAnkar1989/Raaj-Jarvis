"""Run Raaj-Jarvis as an installable PWA (mobile + desktop browsers)."""

import os

# Remote-only mode: never use Mac speakers or Mac mic — phone is the UI.
os.environ.setdefault("JARVIS_PWA", "1")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "core.pwa_server:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
    )
