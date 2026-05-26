"""FastAPI server + PWA static hosting for Raaj-Jarvis."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import tempfile
import threading
import traceback
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Header, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.jarvis_tts import synthesize_bytes, set_disable_local_playback, warmup_tts

try:
    from actions.gmail_client import (
        APP_ORIGIN,
        gmail_configured,
        gmail_status,
        oauth_callback,
        oauth_redirect_uris,
        oauth_start,
        save_gmail_client_id,
        save_gmail_credentials,
    )
except ImportError:
    APP_ORIGIN = "https://raajarvis.netlify.app"
    def gmail_configured() -> bool:
        return False

    def gmail_status() -> dict:
        return {"configured": False, "client_id": "", "connected": False}

    def save_gmail_client_id(*_a, **_k) -> None:
        pass

    def save_gmail_credentials(*_a, **_k) -> None:
        pass

    def oauth_start(*_a, **_k) -> dict:
        return {}

    def oauth_callback(*_a, **_k) -> str:
        return ""

    def oauth_redirect_uris(*_a, **_k) -> list:
        return []

try:
    from actions.reminder import list_reminders
except ImportError:
    def list_reminders(*_a, **_k) -> list:
        return []
from core.client_memory import load_client_memory, load_chat_history, remember
from core.file_index import index_file
from core.llm_config import load_llm_config, save_llm_config
from core.voice_input import transcribe_file, warmup_stt
from core.web_ui import WebUIAdapter

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "web" / "static"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
PUBLIC_URL_FILE = BASE_DIR / "data" / "public_url.txt"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Raajarvis", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PWAService:
    def __init__(self):
        self.ui = WebUIAdapter()
        self.engine = None
        self._engine_thread: threading.Thread | None = None
        self._clients: set[WebSocket] = set()
        self._ws_client_ids: dict[WebSocket, str] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False
        self.ui.subscribe(self._on_ui_event)

    def _bind_ws_client(self, ws: WebSocket, client_id: str | None) -> None:
        if client_id:
            self._ws_client_ids[ws] = client_id

    def _set_active_client(self, client_id: str | None) -> None:
        if client_id:
            self.ui.client_id = client_id

    def _on_ui_event(self, event: dict) -> None:
        if not self._loop:
            return
        if event.get("type") == "speech":
            # Deliver to every connected client — phone may have multiple tabs/sockets.
            asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)
            return
        if event.get("type") == "alarm":
            target = event.get("client_id") or self.ui.client_id
            asyncio.run_coroutine_threadsafe(
                self._send_to_client(target, event), self._loop
            )
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)

    async def _send_to_client(self, client_id: str | None, event: dict) -> None:
        if not client_id:
            return
        payload = json.dumps(event)
        dead: list[WebSocket] = []
        sent = False
        for ws in list(self._clients):
            if self._ws_client_ids.get(ws) != client_id:
                continue
            try:
                await ws.send_text(payload)
                sent = True
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
            self._ws_client_ids.pop(ws, None)
        if not sent:
            # Fallback: single connected client (legacy)
            if len(self._clients) == 1:
                ws = next(iter(self._clients))
                try:
                    await ws.send_text(payload)
                except Exception:
                    pass

    async def _broadcast(self, event: dict) -> None:
        dead: list[WebSocket] = []
        payload = json.dumps(event)
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        self._loop = asyncio.get_event_loop()
        self.ui.bind_loop(self._loop)
        set_disable_local_playback(True)
        await asyncio.gather(
            asyncio.to_thread(warmup_stt),
            asyncio.to_thread(warmup_tts),
        )
        from main import TOOL_DECLARATIONS
        from core.local_engine import JarvisLocal

        self.engine = JarvisLocal(self.ui, TOOL_DECLARATIONS)
        self._engine_thread = threading.Thread(
            target=lambda: asyncio.run(self.engine.run()),
            daemon=True,
        )
        self._engine_thread.start()
        self.ui.write_log("SYS: PWA server online.")

    async def handle_chat(
        self,
        text: str,
        client_id: str | None = None,
        ws: WebSocket | None = None,
        source: str = "text",
    ) -> None:
        await self.ensure_started()
        self._set_active_client(client_id)
        if ws and client_id:
            self._bind_ws_client(ws, client_id)
        if self.ui.on_text_command:
            self.ui.on_text_command(text.strip(), source)
        else:
            await asyncio.sleep(0.3)
            if self.ui.on_text_command:
                self.ui.on_text_command(text.strip(), source)


service = PWAService()


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _server_port() -> int:
    return int(os.environ.get("JARVIS_PORT", "8765"))


def _public_url() -> str | None:
    env = os.environ.get("JARVIS_PUBLIC_URL", "").strip()
    if env.startswith("https://"):
        return env.rstrip("/")
    try:
        if PUBLIC_URL_FILE.exists():
            url = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip()
            if url.startswith("https://"):
                return url.rstrip("/")
    except Exception:
        pass
    return None


def _client_id(header: str | None = None, body: str | None = None) -> str | None:
    return (header or body or "").strip() or None


def _host_metrics() -> dict:
    try:
        import psutil

        mem = psutil.virtual_memory()
        return {
            "cpu": round(psutil.cpu_percent(interval=0.1), 1),
            "memory": round(mem.percent, 1),
            "disk": round(psutil.disk_usage("/").percent, 1),
        }
    except Exception:
        return {"cpu": 0, "memory": 0, "disk": 0}


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/metrics")
async def metrics(x_jarvis_client_id: str | None = Header(default=None)):
    await service.ensure_started()
    host = _host_metrics()
    client_mem = load_client_memory(x_jarvis_client_id)
    return {
        "host": host,
        "memory_entries": len((client_mem.get("entries") or {})),
        "file": service.ui.file_index,
    }


@app.get("/api/memory")
async def get_memory(x_jarvis_client_id: str | None = Header(default=None)):
    data = load_client_memory(x_jarvis_client_id)
    history = load_chat_history(x_jarvis_client_id)
    return {
        "entries": data.get("entries") or {},
        "chat_count": len(history),
    }


@app.post("/api/memory")
async def post_memory(payload: dict, x_jarvis_client_id: str | None = Header(default=None)):
    cid = _client_id(x_jarvis_client_id, payload.get("client_id"))
    key = (payload.get("key") or "").strip()
    value = (payload.get("value") or "").strip()
    if cid and key and value:
        remember(cid, key, value)
    return {"ok": True, "entries": load_client_memory(cid).get("entries") or {}}


@app.get("/api/status")
async def status():
    await service.ensure_started()
    cfg = load_llm_config()
    public = _public_url()
    return {
        "ok": True,
        "state": service.ui._state,
        "muted": service.ui.muted,
        "lan_url": f"http://{_lan_ip()}:{_server_port()}",
        "public_url": public,
        "model": cfg.get("ollama_model", "qwen2.5:7b"),
        "provider": "ollama",
        "has_file": bool(service.ui.current_file),
        "file_name": Path(service.ui.current_file).name if service.ui.current_file else None,
    }


@app.get("/api/tunnel")
async def tunnel_info():
    public = _public_url()
    port = _server_port()
    return {
        "public_url": public,
        "lan_url": f"http://{_lan_ip()}:{port}",
        "local_url": f"http://127.0.0.1:{port}",
        "ready": bool(public),
        "hint": (
            "Run ./run_remote.sh on your Mac, then paste public_url in Netlify PWA settings."
            if not public
            else None
        ),
    }


@app.get("/api/reminders")
async def get_reminders():
    return {"reminders": list_reminders(include_past=False)}


@app.get("/api/config")
async def config():
    cfg = load_llm_config()
    return {
        "provider": cfg.get("llm_provider", "ollama"),
        "model": cfg.get("ollama_model", "qwen2.5:7b"),
        "voice": cfg.get("tts_voice", "en-US-AndrewMultilingualNeural"),
    }


@app.get("/api/settings")
async def get_settings():
    cfg = load_llm_config()
    return {
        "voice": cfg.get("tts_voice", "en-US-AndrewMultilingualNeural"),
        "personality": cfg.get("assistant_personality", "professional"),
        "tts_rate": cfg.get("tts_rate", "+8%"),
        "owner": cfg.get("owner_name", "Raaj"),
        "gmail_configured": gmail_configured(),
        "gmail": gmail_status(),
    }


@app.post("/api/settings")
async def post_settings(payload: dict):
    data: dict = {}
    if payload.get("voice"):
        data["tts_voice"] = str(payload["voice"]).strip()
    if payload.get("personality"):
        data["assistant_personality"] = str(payload["personality"]).strip()
    if payload.get("tts_rate") is not None:
        data["tts_rate"] = str(payload["tts_rate"]).strip()
    if payload.get("owner"):
        data["owner_name"] = str(payload["owner"]).strip()
    if data:
        save_llm_config(data)
    return {"ok": True}


@app.get("/api/gmail/status")
async def get_gmail_status():
    return gmail_status()


@app.post("/api/gmail/settings")
async def post_gmail_settings(payload: dict):
    client_id = str(payload.get("client_id") or "").strip()
    if client_id:
        save_gmail_client_id(client_id)
    # Legacy full creds still supported
    client_secret = str(payload.get("client_secret") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if client_id and client_secret and refresh_token:
        save_gmail_credentials(client_id, client_secret, refresh_token)
    return {"ok": True, **gmail_status()}


def _oauth_redirect_base(request: Request) -> str:
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin.startswith("https://") and "netlify.app" in origin:
        return origin
    ref = request.headers.get("referer") or ""
    if "netlify.app" in ref:
        try:
            parsed = urlparse(ref)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass
    return APP_ORIGIN


@app.get("/api/gmail/oauth/start")
async def gmail_oauth_start(request: Request):
    try:
        data = oauth_start(_oauth_redirect_base(request))
        return RedirectResponse(data["auth_url"])
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/gmail/oauth/callback")
async def gmail_oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:2rem'>"
            f"<h2>Gmail connection failed</h2><p>{error}</p></body></html>",
            status_code=400,
        )
    try:
        msg = oauth_callback(code, state)
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:2rem;text-align:center'>"
            f"<h2>✓ {msg}</h2><p>Return to JARVIS — you can close this tab.</p></body></html>"
        )
    except RuntimeError as e:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:2rem'>"
            f"<h2>Connection failed</h2><p>{e}</p></body></html>",
            status_code=400,
        )


@app.get("/api/gmail/oauth/redirect-uris")
async def gmail_redirect_uris():
    return {"redirect_uris": oauth_redirect_uris(), "app_origin": APP_ORIGIN}


@app.post("/api/interrupt")
async def interrupt_speech(x_jarvis_client_id: str | None = Header(default=None)):
    await service.ensure_started()
    service.ui.cancel_speech()
    service.ui.set_state("LISTENING")
    return {"ok": True}


@app.post("/api/chat")
async def chat(payload: dict, x_jarvis_client_id: str | None = Header(default=None)):
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)
    cid = _client_id(x_jarvis_client_id, payload.get("client_id"))
    service._set_active_client(cid)
    source = str(payload.get("source") or "text")
    await service.handle_chat(text, cid, source=source)
    return {"ok": True}


@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    x_jarvis_client_id: str | None = Header(default=None),
):
    cid = _client_id(x_jarvis_client_id)
    if cid:
        service._set_active_client(cid)
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    data = await audio.read()
    if not data or len(data) < 1500:
        return JSONResponse({"error": "audio too short"}, status_code=400)

    path = tempfile.mktemp(suffix=suffix)
    try:
        Path(path).write_bytes(data)
        text = await asyncio.to_thread(transcribe_file, path)
    finally:
        Path(path).unlink(missing_ok=True)

    if not text:
        return JSONResponse({"error": "could not transcribe"}, status_code=422)
    return {"text": text}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    x_jarvis_client_id: str | None = Header(default=None),
):
    await service.ensure_started()
    cid = _client_id(x_jarvis_client_id)
    service._set_active_client(cid)
    if not file.filename:
        return JSONResponse({"error": "no filename"}, status_code=400)

    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    data = await file.read()
    if not data:
        return JSONResponse({"error": "empty file"}, status_code=400)
    dest.write_bytes(data)

    service.ui.set_current_file(str(dest))
    size_kb = len(data) / 1024
    size = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
    service.ui.write_log(f"FILE: {safe_name} ({size}) loaded")

    indexed = await asyncio.to_thread(index_file, dest)
    service.ui.set_file_index(indexed)
    if service.ui.client_id:
        remember(service.ui.client_id, "last_file", f"{safe_name}: {indexed.get('summary', '')[:200]}")

    summary = (indexed.get("summary") or "File uploaded.").strip()
    msg = (
        f"I've loaded '{safe_name}' ({size}). Summary: {summary} "
        f"What would you like to know about it?"
    )
    await service.handle_chat(
        f"[FILE_READY] Tell the user briefly: {msg}",
        service.ui.client_id,
    )

    return {
        "ok": True,
        "name": safe_name,
        "path": str(dest),
        "size": size,
        "summary": summary,
        "is_image": safe_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")),
    }


@app.delete("/api/upload")
async def clear_upload():
    await service.ensure_started()
    if service.ui.current_file:
        try:
            Path(service.ui.current_file).unlink(missing_ok=True)
        except Exception:
            pass
    service.ui.set_current_file(None)
    service.ui.write_log("SYS: File cleared.")
    return {"ok": True}


@app.post("/api/tts")
async def tts(payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty text"}, status_code=400)
    audio = await asyncio.to_thread(synthesize_bytes, text)
    if not audio:
        return JSONResponse({"error": "tts failed"}, status_code=500)
    from fastapi.responses import Response

    return Response(content=audio, media_type="audio/mpeg")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await service.ensure_started()
    service._clients.add(ws)
    await ws.send_json({"type": "state", "value": service.ui._state})
    await ws.send_json({"type": "hello", "lan_url": f"http://{_lan_ip()}:{_server_port()}"})
    if service.ui.current_file:
        await ws.send_json({
            "type": "file",
            "name": Path(service.ui.current_file).name,
        })
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if kind == "chat":
                cid = _client_id(msg.get("client_id"))
                source = str(msg.get("source") or "text")
                await service.handle_chat(msg.get("text", ""), cid, ws, source)
            elif kind == "mute":
                service.ui.muted = bool(msg.get("value"))
            elif kind == "register":
                cid = _client_id(msg.get("client_id"))
                service._bind_ws_client(ws, cid)
                service._set_active_client(cid)
                await ws.send_json({
                    "type": "memory",
                    "entries": load_client_memory(service.ui.client_id).get("entries") or {},
                    "chat_count": len(load_chat_history(service.ui.client_id)),
                })
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "interrupt":
                service.ui.cancel_speech()
                service.ui.set_state("LISTENING")
                await ws.send_json({"type": "interrupted"})
    except WebSocketDisconnect:
        pass
    finally:
        service._clients.discard(ws)
        service._ws_client_ids.pop(ws, None)


def _static_file(name: str, media_type: str | None = None) -> FileResponse:
    path = STATIC_DIR / name
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    headers = {"Cache-Control": "no-cache"} if name.endswith((".html", ".js")) else {}
    return FileResponse(path, media_type=media_type, headers=headers)


@app.get("/manifest.json")
async def manifest():
    return _static_file("manifest.json", "application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/")
async def index():
    return _static_file("index.html", "text/html")


@app.get("/app.js")
async def app_js():
    return _static_file("app.js", "application/javascript")


@app.get("/styles.css")
async def styles_css():
    return _static_file("styles.css", "text/css")


@app.get("/discovery.js")
async def discovery_js():
    return _static_file("discovery.js", "application/javascript")


@app.get("/config.js")
async def config_js():
    return _static_file("config.js", "application/javascript")


@app.get("/icons/{name}")
async def icons(name: str):
    path = STATIC_DIR / "icons" / name
    if path.exists():
        return FileResponse(path)
    return JSONResponse({"error": "not found"}, status_code=404)


# Legacy /static/* paths (backward compatible)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
