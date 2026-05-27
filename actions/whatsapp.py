"""Reliable WhatsApp messaging on Mac — URL scheme + UI automation."""

from __future__ import annotations

import json
import platform
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.08
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip

    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_BUNDLE_ID = "net.whatsapp.WhatsApp"
_CONTACTS_PATH = Path(__file__).resolve().parent.parent / "config" / "whatsapp_contacts.json"


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _is_mac() -> bool:
    try:
        cfg = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        os_name = (cfg.get("os_system") or "mac").lower()
        if os_name in ("mac", "darwin", "macos"):
            return True
    except Exception:
        pass
    return platform.system() == "Darwin"


def _require_automation() -> None:
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui pyperclip")


def load_contacts() -> dict[str, str]:
    if not _CONTACTS_PATH.exists():
        return {}
    try:
        data = json.loads(_CONTACTS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k).lower().strip(): str(v).strip() for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def save_contact(name: str, phone: str) -> None:
    contacts = load_contacts()
    contacts[name.lower().strip()] = phone.strip()
    _CONTACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONTACTS_PATH.write_text(json.dumps(contacts, indent=2), encoding="utf-8")


def save_contacts(contacts: dict[str, str]) -> None:
    cleaned = {
        str(k).lower().strip(): str(v).strip()
        for k, v in (contacts or {}).items()
        if k and v
    }
    _CONTACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONTACTS_PATH.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")


def remove_contact(name: str) -> None:
    contacts = load_contacts()
    contacts.pop(name.lower().strip(), None)
    save_contacts(contacts)


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def _lookup_phone(receiver: str) -> str | None:
    key = receiver.lower().strip()
    contacts = load_contacts()
    if key in contacts:
        return _normalize_phone(contacts[key])
    for name, phone in contacts.items():
        if name in key or key in name:
            return _normalize_phone(phone)
    if re.fullmatch(r"[\d+\s\-()]+", receiver.strip()):
        return _normalize_phone(receiver)
    return None


def open_whatsapp() -> bool:
    if not _is_mac():
        return False
    for cmd in (
        ["open", "-b", _BUNDLE_ID],
        ["open", "-a", "WhatsApp"],
        ["open", "-a", "WhatsApp.app"],
    ):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
            if result.returncode == 0:
                time.sleep(2.0)
                return True
        except Exception:
            continue
    return False


def _paste(text: str) -> None:
    _require_automation()
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.12)
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.write(text, interval=0.02)
    time.sleep(0.15)


def _focus_whatsapp_search() -> bool:
    """Activate WhatsApp and click the sidebar search field (not in-chat search)."""
    script = """
tell application "WhatsApp" to activate
delay 1.8
tell application "System Events"
    if not (exists process "WhatsApp") then return "missing"
    tell process "WhatsApp"
        set frontmost to true
        delay 0.4
        try
            set w to window 1
            repeat with tf in text fields of w
                try
                    set ph to value of attribute "AXPlaceholderValue" of tf
                    if ph contains "Search" or ph contains "search" or ph contains "Meta AI" then
                        click tf
                        return "ok"
                    end if
                end try
            end repeat
            try
                click text field 1 of w
                return "ok"
            end try
        end try
    end tell
end tell
return "fail"
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return "ok" in (result.stdout or "")
    except Exception:
        return False


def _send_via_url(phone: str, message: str) -> str:
    encoded = urllib.parse.quote(message)
    url = f"https://wa.me/{phone}?text={encoded}"
    try:
        subprocess.run(["open", url], check=True, timeout=10)
    except Exception as e:
        return f"Could not open WhatsApp link: {e}"
    time.sleep(3.0)
    if _PYAUTOGUI:
        pyautogui.press("enter")
        time.sleep(0.4)
    return f"Message sent to {phone} on WhatsApp."


def _send_via_ui(receiver: str, message: str) -> str:
    _require_automation()
    if not open_whatsapp():
        return "Could not open WhatsApp."

    if not _focus_whatsapp_search():
        return "Could not focus WhatsApp search. Add a phone number in config/whatsapp_contacts.json."

    pyautogui.hotkey("command", "a")
    time.sleep(0.08)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste(receiver)
    time.sleep(1.2)
    pyautogui.press("down")
    time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(1.0)
    _paste(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} on WhatsApp."


def send_whatsapp(receiver: str, message: str) -> str:
    receiver = (receiver or "").strip()
    message = (message or "").strip()
    if not receiver:
        return "Please specify who to message."
    if not message:
        return "Please specify the message text."

    if not _is_mac():
        return "WhatsApp desktop sending is configured for Mac only."

    phone = _lookup_phone(receiver)
    if phone:
        return _send_via_url(phone, message)

    return _send_via_ui(receiver, message)
