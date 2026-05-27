"""Local Ollama backend — always-on voice, fast intents, Jarvis male voice."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import traceback
from datetime import datetime
from typing import Any

import requests

from core.intent_router import try_fast_route
from core.jarvis_tts import set_speech_hooks, speak as jarvis_speak, warmup_tts
from core.llm_config import load_llm_config
from core.tool_executor import execute_tool
from core.voice_input import listen_once, set_listen_gate, warmup_stt
from core.client_memory import (
    append_chat_turn,
    auto_remember_from_text,
    format_for_prompt as format_client_memory,
    load_chat_history,
)
from memory.memory_manager import format_memory_for_prompt, load_memory
from memory.retrieval import format_relevant_for_prompt, get_relevant_memory
from memory.working import append_turn as working_append

FAST_MODEL = "qwen2.5:7b"

def _strip_model_noise(text: str) -> str:
    t = text or ""
    for tag in ("think", "thinking", "redacted_reasoning"):
        t = re.sub(rf"<{tag}>.*?</{tag}>", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _ollama_options(*, tools: bool = False) -> dict[str, Any]:
    cfg = load_llm_config()
    opts = cfg.get("ollama_options") or {}
    base: dict[str, Any] = {
        "temperature": float(opts.get("temperature", 0.45)),
        "num_predict": int(opts.get("num_predict_tools" if tools else "num_predict", 90 if tools else 48)),
        "num_ctx": int(opts.get("num_ctx", 1024)),
        "top_p": float(opts.get("top_p", 0.9)),
        "repeat_penalty": float(opts.get("repeat_penalty", 1.08)),
    }
    if opts.get("num_thread"):
        base["num_thread"] = int(opts["num_thread"])
    return base


def _fast_ack(tool_name: str, args: dict) -> str:
    if tool_name == "youtube_video":
        return "At once, sir. Pulling that up on YouTube."
    if tool_name == "browser_control" and "youtube" in (args.get("url") or "").lower():
        return "Opening YouTube now, sir."
    if tool_name == "open_app":
        return f"Certainly, sir. Launching {args.get('app_name', 'the application')}."
    if tool_name == "weather_report":
        return "One moment, sir. Checking the forecast."
    if tool_name == "reminder":
        return "Certainly, sir. Setting that timer now."
    if tool_name == "send_message":
        who = args.get("receiver", "them")
        return f"Right away, sir. Sending that WhatsApp message to {who}."
    if tool_name == "office_compose":
        return "Right away, sir. Opening Office and composing that for you."
    return "Very good, sir."

_TYPE_MAP = {
    "OBJECT": "object",
    "STRING": "string",
    "INTEGER": "integer",
    "NUMBER": "number",
    "BOOLEAN": "boolean",
    "ARRAY": "array",
}

_ACTION_RE = re.compile(
    r"\b(open|launch|start|play|put on|close|search|google|find|weather|remind|"
    r"volume|brightness|browser|website|go to|file|folder|delete|move|copy|"
    r"shutdown|restart|screenshot|youtube|you tube|song|music|video|message|send|"
    r"install|update|screen|camera|wifi|spotify|chrome|safari|email|gmail|mail|"
    r"alarm|timer|whatsapp|text|word|excel|document|spreadsheet|write)\b",
    re.I,
)

_FILE_Q_RE = re.compile(
    r"\b(this|the|uploaded|that)\s+file\b|\b(file|document|pdf|doc|mp3|audio)\b|"
    r"\bsummari[sz]e\b|\bwhat (?:does|is) (?:it|this|the file)\b|\bread (?:the|this)\b",
    re.I,
)
_JSON_TOOL_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _convert_schema(schema: dict) -> dict:
    out: dict[str, Any] = {}
    for key, val in schema.items():
        if key == "type" and isinstance(val, str):
            out[key] = _TYPE_MAP.get(val, val.lower())
        elif isinstance(val, dict):
            out[key] = _convert_schema(val)
        elif isinstance(val, list):
            out[key] = [
                _convert_schema(item) if isinstance(item, dict) else item for item in val
            ]
        else:
            out[key] = val
    return out


def to_ollama_tools(declarations: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": _convert_schema(d["parameters"]),
            },
        }
        for d in declarations
    ]


def _needs_tools(text: str) -> bool:
    return bool(_ACTION_RE.search(text))


def _build_system_message(client_id: str | None = None, file_ctx: str | None = None) -> str:
    now = datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
    mem = format_memory_for_prompt(load_memory())
    client_mem = format_client_memory(client_id)
    cfg = load_llm_config()
    personality = (cfg.get("assistant_personality") or "professional").lower()
    owner = cfg.get("owner_name") or "Raaj"
    if personality == "happy":
        tone = (
            f"You are Raajarvis — {owner}'s upbeat, cheerful personal assistant. "
            "Be warm, positive, and energetic while staying helpful. Light humor is fine."
        )
    else:
        tone = (
            f"You are Raajarvis — {owner}'s capable personal assistant. "
            "Be smart, warm, and proactive. Address the user as sir or by name when known."
        )
    base = (
        f"{tone} Today: {now}.\n"
        "Speak naturally in 1-3 short sentences. No markdown or bullet lists.\n"
        "You remember this device's recent conversation — refer back when the user says "
        '"that", "it", or "next time".\n'
        "TOOLS (use when needed):\n"
        "- gmail action=list|search|read|open|draft|send|calendar — email & calendar (when connected)\n"
        "- send_message — send WhatsApp messages (receiver + message_text; NOT open_app)\n"
        "- reminder — real alarms/reminders (date YYYY-MM-DD, time HH:MM)\n"
        "- office_compose — create Word/Excel docs visibly (topic, word_count, app=word|excel)\n"
        "- youtube_video action=play query=<song>\n"
        "- file_processor — uploaded file questions\n"
        "- save_memory — remember user facts\n"
        "- browser_control, open_app, weather_report, web_search\n"
        "Never open youtube.com homepage when user asked to PLAY — use youtube_video play."
    )
    parts = [base]
    if mem:
        parts.append(mem)
    if client_mem:
        parts.append(client_mem)
    if file_ctx:
        parts.append(f"[UPLOADED FILE]\n{file_ctx}")
    return "\n".join(parts)


def _trim_history(messages: list[dict], max_msgs: int = 10) -> list[dict]:
    if len(messages) <= max_msgs:
        return messages
    return messages[0:1] + messages[-(max_msgs - 1) :]


def _parse_json_tool(content: str) -> list[dict]:
    m = _JSON_TOOL_RE.search(content)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    name = data.get("name") or data.get("tool")
    args = data.get("arguments") or data.get("args") or {}
    if name:
        return [{"function": {"name": name, "arguments": args}}]
    return []


def _short_speak(text: str, max_len: int = 180) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "."


class JarvisLocal:
    def __init__(self, ui, tool_declarations: list[dict]):
        self.ui = ui
        self._all_tools = to_ollama_tools(tool_declarations)
        self._messages: list[dict] = [{"role": "system", "content": _build_system_message()}]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._input_queue: asyncio.Queue[str] | None = None
        self._is_speaking = False
        self._is_busy = False
        self._speaking_lock = threading.Lock()
        self._running = True
        self._greeted = False
        self._last_user_text = ""
        self._last_user_at = 0.0
        self._listen_blocked_until = 0.0
        self.ui.on_text_command = self._on_text_command
        self.ui.on_voice_request = self._on_voice_request
        self._text_source = "text"

        cfg = load_llm_config()
        self._base_url = cfg.get("ollama_base_url", "http://localhost:11434").rstrip("/")
        self._model = cfg.get("ollama_model") or FAST_MODEL
        self._active_provider = "ollama"
        self._active_model = self._model
        self._voice_mode = (cfg.get("voice_input_mode") or "always_on").lower()
        self._listen_cooldown = float(cfg.get("listen_cooldown_sec") or 1.5)

        set_speech_hooks(self._on_tts_start, self._on_tts_end)

    def _refresh_system(self) -> None:
        client_id = getattr(self.ui, "client_id", None)
        file_ctx = getattr(self.ui, "file_context", None)
        if self._messages:
            self._messages[0] = {
                "role": "system",
                "content": _build_system_message(client_id, file_ctx),
            }

    def _on_tts_start(self):
        self.set_speaking(True)
        self._listen_blocked_until = time.time() + 120.0

    def _on_tts_end(self):
        self.set_speaking(False)
        self._listen_blocked_until = time.time() + self._listen_cooldown

    def _can_listen(self) -> bool:
        with self._speaking_lock:
            speaking = self._is_speaking
        return (
            not speaking
            and not self._is_busy
            and not self.ui.muted
            and time.time() >= self._listen_blocked_until
        )

    def _load_client_session(self) -> None:
        client_id = getattr(self.ui, "client_id", None)
        self._refresh_system()
        history = load_chat_history(client_id)
        self._messages = [self._messages[0]] + history

    def _on_text_command(self, text: str, source: str = "text"):
        if not self._loop or not self._input_queue:
            return
        self._text_source = source if source in ("text", "voice") else "text"
        asyncio.run_coroutine_threadsafe(
            self._input_queue.put(text), self._loop
        )

    def _on_voice_request(self):
        if not self._loop or not self._input_queue:
            return
        if self._voice_mode == "push_to_talk":
            asyncio.run_coroutine_threadsafe(self._input_queue.put("__PTT__"), self._loop)
        else:
            asyncio.run_coroutine_threadsafe(self._input_queue.put("__ACTIVATE__"), self._loop)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted and not self._is_busy:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not text or not text.strip():
            return
        clean = _short_speak(text.strip())
        web = getattr(self.ui, "web_mode", False)
        if not web:
            self.ui.write_log(f"Jarvis: {clean}")
        if web:
            self._listen_blocked_until = time.time() + 120.0
            self.set_speaking(True)
            threading.Thread(target=self._web_tts, args=(clean,), daemon=True).start()
        else:
            jarvis_speak(clean)

    def speak_immediate(self, text: str) -> None:
        """Short ack while planning — text in UI immediately, TTS in parallel."""
        if not text or not text.strip():
            return
        clean = _short_speak(text.strip())
        web = getattr(self.ui, "web_mode", False)
        if web:
            self.ui.write_log(f"Jarvis: {clean}")
            threading.Thread(target=self._web_tts, args=(clean,), daemon=True).start()
        else:
            self.speak(clean)

    def speak_error(self, tool_name: str, error: str):
        self.ui.write_log(f"ERR: {tool_name} — {str(error)[:120]}")
        self.speak(f"Sorry sir, {tool_name} failed.")

    def _web_tts(self, text: str):
        try:
            if hasattr(self.ui, "emit_speech"):
                self.ui.emit_speech(text)
            elif hasattr(self.ui, "emit_speech_sync"):
                self.ui.emit_speech_sync(text)
        finally:
            self.set_speaking(False)
            self._listen_blocked_until = time.time() + self._listen_cooldown

    def _ollama_chat(self, messages: list[dict], use_tools: bool) -> dict:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": _trim_history(messages),
            "stream": False,
            "keep_alive": "30m",
            "options": _ollama_options(tools=use_tools),
        }
        if use_tools:
            payload["tools"] = self._all_tools
        resp = requests.post(f"{self._base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def _ollama_chat_stream(self, messages: list[dict]):
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": _trim_history(messages),
            "stream": True,
            "keep_alive": "30m",
            "options": _ollama_options(tools=False),
        }
        resp = requests.post(
            f"{self._base_url}/api/chat", json=payload, stream=True, timeout=120
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            chunk = (data.get("message") or {}).get("content") or ""
            if chunk:
                yield chunk
            thinking = (data.get("message") or {}).get("thinking") or ""
            if thinking and not chunk:
                continue
            if data.get("done"):
                break

    def _warmup_llm(self) -> None:
        try:
            requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"num_predict": 5},
                },
                timeout=30,
            )
        except Exception:
            pass

    def _tool_speak(self, text: str):
        if text and str(text).strip():
            short = str(text).strip()
            if len(short) > 120:
                short = short[:120] + "…"
            self.ui.write_log(f"Jarvis: {short}")

    async def _run_tool(self, name: str, args: dict) -> str:
        self.ui.write_log(f"SYS: Running {name}…")
        return await execute_tool(name, args, self.ui, self._tool_speak)

    def _speak_streamed(self, content: str) -> None:
        """Speak sentence-by-sentence so the first words start quickly."""
        text = _short_speak(content.strip())
        if not text:
            return
        if getattr(self.ui, "web_mode", False):
            self.speak(text)
            return
        if not getattr(self.ui, "web_mode", False):
            self.ui.write_log(f"Jarvis: {text}")
        sentences = [s.strip() for s in _SENTENCE_END_RE.split(text) if s.strip()]
        if not sentences:
            sentences = [text]
        for sentence in sentences:
            self.speak(sentence)

    def _emit_provider_status(self, provider: str, model: str, *, fallback: bool = False, latency_ms: int = 0) -> None:
        from core.llm.usage_tracker import total_cloud_tokens_today

        self._active_provider = provider
        self._active_model = model
        if hasattr(self.ui, "_broadcast"):
            self.ui._broadcast({
                "type": "provider",
                "provider": provider,
                "model": model,
                "fallback": fallback,
                "latency_ms": latency_ms,
                "cloud_tokens_today": total_cloud_tokens_today(),
            })

    def _cloud_routed_chat(
        self,
        user_text: str,
        client_id: str | None,
        reason=None,
    ) -> str:
        from core.llm.router import RouteReason
        from core.providers.manager import get_provider_manager

        system = self._messages[0]["content"] if self._messages else ""
        mgr = get_provider_manager()
        resp = mgr.complete(
            system=system,
            user_input=user_text,
            history=[m for m in self._messages if m.get("role") != "system"],
            client_id=client_id,
            use_tools=False,
            reason_override=reason or RouteReason.TIMEOUT_FALLBACK,
        )
        self._emit_provider_status(
            resp.provider, resp.model, fallback=resp.fallback, latency_ms=resp.latency_ms
        )
        text = _strip_model_noise(resp.content)
        if text:
            self.speak(text)
        return text

    def _fallback_cloud_chat(self, user_text: str, client_id: str | None) -> str:
        from core.llm.router import RouteReason

        return self._cloud_routed_chat(user_text, client_id, RouteReason.TIMEOUT_FALLBACK)

    def _stream_and_speak(self, messages: list[dict]) -> str:
        """Stream Ollama tokens; speak each finished sentence immediately."""
        cfg = load_llm_config()
        self._emit_provider_status("ollama", cfg.get("ollama_model") or FAST_MODEL)
        buffer = ""
        full = ""

        for token in self._ollama_chat_stream(messages):
            buffer += token
            full += token

            while True:
                m = re.search(r"[.!?](?:\s+|$)", buffer)
                if not m:
                    break
                sentence = buffer[: m.end()].strip()
                buffer = buffer[m.end() :].lstrip()
                if not sentence:
                    continue
                self.speak(sentence)

        text = _strip_model_noise(full)
        tail = buffer.strip()
        if tail and (not text or tail not in text):
            self.speak(tail)
            if not text:
                text = tail
        return text

    def _inject_semantic_memory(self, user_text: str, client_id: str | None) -> None:
        """Attach top-k semantic memories before LLM call (non-destructive)."""
        try:
            relevant = get_relevant_memory(user_text, client_id=client_id or "", top_k=5)
            block = format_relevant_for_prompt(relevant)
            if not block:
                return
            if self._messages and self._messages[0].get("role") == "system":
                base = self._messages[0]["content"]
                if block not in base:
                    self._messages[0]["content"] = base + "\n" + block
        except Exception:
            pass

    async def _handle_user_message(self, text: str):
        from core.stt_filters import prepare_user_text

        raw = text.strip()
        if not raw or raw.startswith("[FILE_READY]"):
            return

        source = getattr(self, "_text_source", "text")
        if source == "voice":
            text = prepare_user_text(raw)
            if not text:
                self.ui.write_log(
                    f"SYS: Ignored noise ({raw[:60]}…)" if len(raw) > 60 else f"SYS: Ignored noise ({raw})"
                )
                return
        else:
            text = raw

        now = time.time()
        if text == self._last_user_text and now - self._last_user_at < 2.0:
            return
        self._last_user_text = text
        self._last_user_at = now

        self._is_busy = True
        self._load_client_session()
        self.ui.write_log(f"You: {text}")
        self.ui.set_state("THINKING")

        client_id = getattr(self.ui, "client_id", None)
        auto_remember_from_text(client_id, text)
        working_append(client_id, "user", text)
        append_chat_turn(client_id, "user", text)
        self._messages.append({"role": "user", "content": text})

        # Confirm pending multi-step agent plan
        try:
            from agentic.orchestrator import run_pending_plan

            pending = await run_pending_plan(self, text)
            if pending:
                self._messages.append({"role": "assistant", "content": pending})
                append_chat_turn(client_id, "assistant", pending)
                working_append(client_id, "assistant", pending)
                self._is_busy = False
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return
        except Exception:
            traceback.print_exc()

        route = try_fast_route(text)
        if route:
            name, args = route
            self.speak(_fast_ack(name, args))
            try:
                result = await self._run_tool(name, args)
                if result and str(result).strip():
                    reply = _short_speak(str(result).strip())
                    append_chat_turn(client_id, "assistant", reply)
                    self._messages.append({"role": "assistant", "content": reply})
                    self.speak(reply)
            except Exception as e:
                traceback.print_exc()
                self.speak_error(name, str(e))
            self._is_busy = False
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return

        # Multi-step agent path (optional — falls back to normal chat)
        try:
            from agentic.orchestrator import run_agent_turn, should_use_agent

            if should_use_agent(text):
                self._inject_semantic_memory(text, client_id)
                agent_reply = await run_agent_turn(self, text)
                if agent_reply:
                    append_chat_turn(client_id, "assistant", agent_reply)
                    self._messages.append({"role": "assistant", "content": agent_reply})
                    working_append(client_id, "assistant", agent_reply)
                    self._is_busy = False
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    return
        except Exception:
            traceback.print_exc()

        current_file = getattr(self.ui, "current_file", None)
        if current_file and _FILE_Q_RE.search(text):
            from pathlib import Path

            from core.file_index import index_file
            from core.ollama_text import ollama_complete

            self.speak("One moment, sir. Reading the file.")
            try:
                indexed = getattr(self.ui, "file_index", None)
                if not indexed or indexed.get("path") != current_file:
                    indexed = await asyncio.to_thread(index_file, Path(current_file))
                    if hasattr(self.ui, "set_file_index"):
                        self.ui.set_file_index(indexed)
                prompt = (
                    f"File: {indexed.get('name')}\nSummary: {indexed.get('summary')}\n\n"
                    f"Content:\n{(indexed.get('text') or '')[:8000]}\n\n"
                    f"User question: {text}\nAnswer helpfully in 2-4 sentences."
                )
                answer = await asyncio.to_thread(ollama_complete, prompt, max_tokens=280)
                if answer.strip():
                    reply = _short_speak(answer.strip())
                    append_chat_turn(client_id, "assistant", reply)
                    self._messages.append({"role": "assistant", "content": reply})
                    self.speak(reply)
            except Exception as e:
                traceback.print_exc()
                self.speak_error("file", str(e))
            self._is_busy = False
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return

        use_tools = _needs_tools(text)
        self._inject_semantic_memory(text, client_id)

        if not use_tools:
            from core.llm.router import RouteReason, route

            client_id = getattr(self.ui, "client_id", None)
            decision = route(text)
            hard_task = decision.reason in (
                RouteReason.CODING,
                RouteReason.REASONING,
                RouteReason.LONG_CONTEXT,
                RouteReason.WEB,
            )
            try:
                if hard_task and decision.allow_cloud:
                    content = await asyncio.to_thread(
                        self._cloud_routed_chat, text, client_id, decision.reason
                    )
                else:
                    content = await asyncio.to_thread(
                        self._stream_and_speak, list(self._messages)
                    )
            except (requests.RequestException, RuntimeError):
                self.ui.write_log("SYS: Local model unavailable — trying cloud fallback.")
                try:
                    content = await asyncio.to_thread(
                        self._fallback_cloud_chat, text, client_id
                    )
                except Exception as e2:
                    self.ui.write_log(f"ERR: All providers — {e2}")
                    self.speak("Cannot reach AI providers, sir.")
                    self._is_busy = False
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    return

            if content and not content.startswith("```"):
                append_chat_turn(client_id, "assistant", content)
                self._messages.append({"role": "assistant", "content": content})
            else:
                self.ui.write_log("SYS: No reply — try again.")
            self._is_busy = False
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return

        for _ in range(4):
            try:
                data = await asyncio.to_thread(
                    self._ollama_chat, list(self._messages), use_tools
                )
            except requests.RequestException as e:
                self.ui.write_log(f"ERR: Ollama tools — {e}")
                try:
                    reply = await asyncio.to_thread(
                        self._fallback_cloud_chat, text, getattr(self.ui, "client_id", None)
                    )
                    if reply:
                        append_chat_turn(client_id, "assistant", reply)
                        self._messages.append({"role": "assistant", "content": reply})
                except Exception:
                    self.speak("Cannot reach Ollama, sir.")
                break

            message = data.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            if not tool_calls and message.get("content"):
                tool_calls = _parse_json_tool(message["content"])

            if tool_calls:
                use_tools = True
                self._messages.append(message)
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments") or {}
                    if isinstance(raw_args, str):
                        try:
                            raw_args = json.loads(raw_args) if raw_args else {}
                        except json.JSONDecodeError:
                            raw_args = {}
                    result = await self._run_tool(name, raw_args)
                    if result and str(result).strip():
                        reply = _short_speak(str(result).strip())
                        append_chat_turn(client_id, "assistant", reply)
                        self._messages.append({"role": "assistant", "content": reply})
                        self.speak(reply)
                continue

            content = (message.get("content") or "").strip()
            if content and not content.startswith("```"):
                append_chat_turn(client_id, "assistant", content)
                self._messages.append({"role": "assistant", "content": content})
                self._speak_streamed(content)
            elif not tool_calls:
                self.ui.write_log("SYS: No reply — try again.")
            break

        self._is_busy = False
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    async def _always_listen_loop(self):
        if getattr(self.ui, "web_mode", False):
            return
        self.ui.write_log("SYS: Always-on voice — speak naturally after JARVIS finishes.")
        while self._running:
            if (
                self.ui.muted
                or self._is_busy
                or self._is_speaking
                or time.time() < self._listen_blocked_until
            ):
                await asyncio.sleep(0.08)
                continue

            self.ui.set_state("LISTENING")
            text, err = await asyncio.to_thread(listen_once)

            if text and self._input_queue:
                await self._input_queue.put(text)
            elif err:
                self.ui.write_log(f"SYS: {err}")

            await asyncio.sleep(0.05)

    async def _process_input(self):
        assert self._input_queue is not None
        while self._running:
            text = await self._input_queue.get()
            if text == "__PTT__":
                text, err = await asyncio.to_thread(listen_once)
                if err:
                    self.ui.write_log(f"SYS: {err}")
                    continue
                if not text:
                    continue
            elif text == "__ACTIVATE__":
                if self.ui.muted:
                    self.ui.muted = False
                    self.ui.write_log("SYS: Voice activated — speak anytime.")
                self.ui.set_state("LISTENING")
                continue
            try:
                await self._handle_user_message(text)
            except Exception as e:
                traceback.print_exc()
                self.ui.write_log(f"ERR: {e}")
                self._is_busy = False
                self.ui.set_state("LISTENING")

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._input_queue = asyncio.Queue()

        while self._running:
            try:
                r = requests.get(f"{self._base_url}/api/tags", timeout=5)
                r.raise_for_status()
            except requests.RequestException as e:
                self.ui.set_state("THINKING")
                self.ui.write_log(f"ERR: Waiting for Ollama — {e}")
                await asyncio.sleep(3)
                continue

            self.ui.set_state("THINKING")
            self.ui.write_log("SYS: Loading voice engine…")
            await asyncio.gather(
                asyncio.to_thread(warmup_stt),
                asyncio.to_thread(warmup_tts),
                asyncio.to_thread(self._warmup_llm),
            )

            self.ui.set_state("LISTENING")
            self.ui.write_log(f"SYS: Online — {self._model}")
            set_listen_gate(self._can_listen)

            if getattr(self.ui, "web_mode", False):
                self.ui.write_log("SYS: PWA — hold mic button to speak.")
            elif self._voice_mode == "always_on":
                self.ui.write_log(
                    "SYS: Always-on voice — press 🎤 or F4 once to activate, then just talk."
                )
            else:
                self.ui.write_log("SYS: Press 🎤 or F3 to speak.")

            if not self._greeted:
                self._greeted = True
                self.ui.write_log("SYS: JARVIS online.")

            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._process_input())
                    if (
                        self._voice_mode == "always_on"
                        and not getattr(self.ui, "web_mode", False)
                    ):
                        tg.create_task(self._always_listen_loop())
            except Exception as e:
                traceback.print_exc()
                self.ui.write_log(f"ERR: Engine stopped — {e}")
                await asyncio.sleep(3)
