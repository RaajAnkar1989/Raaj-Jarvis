"""Shared tool execution for Gemini Live and local Ollama backends."""

from __future__ import annotations

import asyncio
import threading
import traceback
from typing import Any, Callable

from memory.memory_manager import update_memory

from actions.file_processor import file_processor
from actions.flight_finder import flight_finder
from actions.open_app import open_app
from actions.weather_report import weather_action
from actions.send_message import send_message
from actions.reminder import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor import screen_process
from actions.youtube_video import youtube_video
from actions.desktop import desktop_control
from actions.browser_control import browser_control
from actions.file_controller import file_controller
from actions.code_helper import code_helper
from actions.dev_agent import dev_agent
from actions.web_search import web_search as web_search_action
from actions.computer_control import computer_control
from actions.game_updater import game_updater
from actions.gmail_client import gmail_action


async def execute_tool(
    name: str,
    args: dict[str, Any],
    ui,
    speak: Callable[[str], None],
) -> str:
    print(f"[JARVIS] tool {name} {args}")
    ui.set_state("THINKING")

    if name == "save_memory":
        category = args.get("category", "notes")
        key = args.get("key", "")
        value = args.get("value", "")
        if key and value:
            update_memory({category: {key: {"value": value}}})
            print(f"[Memory] save_memory: {category}/{key} = {value}")
        if not ui.muted:
            ui.set_state("LISTENING")
        return "ok"

    loop = asyncio.get_event_loop()
    result = "Done."

    try:
        if name == "open_app":
            r = await loop.run_in_executor(
                None, lambda: open_app(parameters=args, response=None, player=ui)
            )
            result = r or f"Opened {args.get('app_name')}."

        elif name == "weather_report":
            r = await loop.run_in_executor(
                None, lambda: weather_action(parameters=args, player=ui)
            )
            result = r or "Weather delivered."

        elif name == "browser_control":
            r = await loop.run_in_executor(
                None, lambda: browser_control(parameters=args, player=ui)
            )
            result = r or "Done."

        elif name == "file_controller":
            r = await loop.run_in_executor(
                None, lambda: file_controller(parameters=args, player=ui)
            )
            result = r or "Done."

        elif name == "send_message":
            r = await loop.run_in_executor(
                None,
                lambda: send_message(
                    parameters=args, response=None, player=ui, session_memory=None
                ),
            )
            result = r or f"Message sent to {args.get('receiver')}."

        elif name == "reminder":
            r = await loop.run_in_executor(
                None, lambda: reminder(parameters=args, response=None, player=ui)
            )
            result = r or "Reminder set."
            if getattr(ui, "web_mode", False) and hasattr(ui, "emit_alarm"):
                ui.emit_alarm(
                    args.get("date", ""),
                    args.get("time", ""),
                    args.get("message", ""),
                )

        elif name == "gmail":
            r = await loop.run_in_executor(
                None, lambda: gmail_action(parameters=args, player=ui)
            )
            result = r or "Done."

        elif name == "youtube_video":
            r = await loop.run_in_executor(
                None, lambda: youtube_video(parameters=args, response=None, player=ui)
            )
            result = r or "Done."

        elif name == "screen_process":
            threading.Thread(
                target=screen_process,
                kwargs={
                    "parameters": args,
                    "response": None,
                    "player": ui,
                    "session_memory": None,
                },
                daemon=True,
            ).start()
            result = (
                "Vision module activated. Stay completely silent — "
                "vision module will speak directly."
            )

        elif name == "computer_settings":
            r = await loop.run_in_executor(
                None,
                lambda: computer_settings(parameters=args, response=None, player=ui),
            )
            result = r or "Done."

        elif name == "desktop_control":
            r = await loop.run_in_executor(
                None, lambda: desktop_control(parameters=args, player=ui)
            )
            result = r or "Done."

        elif name == "code_helper":
            r = await loop.run_in_executor(
                None,
                lambda: code_helper(parameters=args, player=ui, speak=speak),
            )
            result = r or "Done."

        elif name == "dev_agent":
            r = await loop.run_in_executor(
                None, lambda: dev_agent(parameters=args, player=ui, speak=speak),
            )
            result = r or "Done."

        elif name == "agent_task":
            from agent.task_queue import get_queue, TaskPriority

            priority_map = {
                "low": TaskPriority.LOW,
                "normal": TaskPriority.NORMAL,
                "high": TaskPriority.HIGH,
            }
            priority = priority_map.get(
                args.get("priority", "normal").lower(), TaskPriority.NORMAL
            )
            task_id = get_queue().submit(
                goal=args.get("goal", ""), priority=priority, speak=speak
            )
            result = f"Task started (ID: {task_id})."

        elif name == "web_search":
            r = await loop.run_in_executor(
                None, lambda: web_search_action(parameters=args, player=ui)
            )
            result = r or "Done."

        elif name == "file_processor":
            if not args.get("file_path") and ui.current_file:
                args["file_path"] = ui.current_file
            r = await loop.run_in_executor(
                None,
                lambda: file_processor(parameters=args, player=ui, speak=speak),
            )
            result = r or "Done."

        elif name == "computer_control":
            r = await loop.run_in_executor(
                None, lambda: computer_control(parameters=args, player=ui)
            )
            result = r or "Done."

        elif name == "game_updater":
            r = await loop.run_in_executor(
                None,
                lambda: game_updater(parameters=args, player=ui, speak=speak),
            )
            result = r or "Done."

        elif name == "flight_finder":
            r = await loop.run_in_executor(
                None, lambda: flight_finder(parameters=args, player=ui)
            )
            result = r or "Done."

        elif name == "shutdown_jarvis":
            ui.write_log("SYS: Shutdown requested.")
            speak("Goodbye, sir.")

            if not getattr(ui, "web_mode", False):
                def _shutdown():
                    import os
                    import time

                    time.sleep(1)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
            result = "Shutting down."

        else:
            result = f"Unknown tool: {name}"

    except Exception as e:
        result = f"Tool '{name}' failed: {e}"
        traceback.print_exc()
        short = str(e)[:120]
        ui.write_log(f"ERR: {name} — {short}")
        speak(f"Sir, {name} encountered an error. {short}")

    if not ui.muted:
        ui.set_state("LISTENING")

    print(f"[JARVIS] {name} -> {str(result)[:80]}")
    return str(result)
