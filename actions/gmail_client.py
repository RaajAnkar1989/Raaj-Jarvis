"""Gmail + Calendar API — OAuth (Client ID + PKCE, no secret required)."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests

from core.llm_config import load_llm_config, save_llm_config

_BASE = Path(__file__).resolve().parent.parent
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
_CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_PKCE_FILE = _BASE / "data" / "gmail_pkce.json"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def _creds() -> dict[str, str]:
    cfg = load_llm_config()
    return {
        "client_id": (cfg.get("gmail_client_id") or "").strip(),
        "client_secret": (cfg.get("gmail_client_secret") or "").strip(),
        "refresh_token": (cfg.get("gmail_refresh_token") or "").strip(),
    }


def save_gmail_client_id(client_id: str) -> None:
    save_llm_config({"gmail_client_id": client_id.strip()})


def save_gmail_tokens(refresh_token: str, access_token: str = "") -> None:
    data: dict[str, str] = {"gmail_refresh_token": refresh_token.strip()}
    if access_token:
        data["gmail_access_token"] = access_token.strip()
    save_llm_config(data)


def save_gmail_credentials(client_id: str, client_secret: str, refresh_token: str) -> None:
    """Legacy — still accepts full creds if user has them."""
    save_llm_config({
        "gmail_client_id": client_id.strip(),
        "gmail_client_secret": client_secret.strip(),
        "gmail_refresh_token": refresh_token.strip(),
    })


def gmail_configured() -> bool:
    c = _creds()
    return bool(c["client_id"] and c["refresh_token"])


def gmail_status() -> dict[str, Any]:
    c = _creds()
    return {
        "configured": gmail_configured(),
        "client_id": c["client_id"],
        "has_client_id": bool(c["client_id"]),
        "connected": bool(c["refresh_token"]),
    }


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _save_pkce(state: str, verifier: str, redirect_uri: str) -> None:
    _PKCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PKCE_FILE.write_text(
        json.dumps({
            "state": state,
            "verifier": verifier,
            "redirect_uri": redirect_uri,
            "created": datetime.now(timezone.utc).isoformat(),
        }),
        encoding="utf-8",
    )


def _load_pkce() -> dict | None:
    if not _PKCE_FILE.exists():
        return None
    try:
        data = json.loads(_PKCE_FILE.read_text(encoding="utf-8"))
        created = datetime.fromisoformat(data["created"])
        if datetime.now(timezone.utc) - created > timedelta(minutes=15):
            return None
        return data
    except Exception:
        return None


def oauth_redirect_uris(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    uris = [
        f"{base}/api/gmail/oauth/callback",
        "http://127.0.0.1:8765/api/gmail/oauth/callback",
        "http://localhost:8765/api/gmail/oauth/callback",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for u in uris:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def oauth_start(base_url: str) -> dict[str, str]:
    c = _creds()
    client_id = c["client_id"]
    if not client_id:
        raise RuntimeError("Add your Google OAuth Client ID in Settings first.")

    redirect_uri = f"{base_url.rstrip('/')}/api/gmail/oauth/callback"
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    _save_pkce(state, verifier, redirect_uri)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url, "redirect_uri": redirect_uri}


def oauth_callback(code: str, state: str) -> str:
    pkce = _load_pkce()
    if not pkce or pkce.get("state") != state:
        raise RuntimeError("OAuth session expired — tap Connect Gmail again.")

    c = _creds()
    client_id = c["client_id"]
    redirect_uri = pkce["redirect_uri"]
    verifier = pkce["verifier"]

    data: dict[str, str] = {
        "client_id": client_id,
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if c["client_secret"]:
        data["client_secret"] = c["client_secret"]

    resp = requests.post(_TOKEN_URL, data=data, timeout=30)
    if not resp.ok:
        err = resp.text[:200]
        raise RuntimeError(
            f"Google token exchange failed. Use a Desktop OAuth client or add redirect URI "
            f"{redirect_uri} in Google Cloud Console. ({err})"
        )

    body = resp.json()
    refresh = body.get("refresh_token")
    if not refresh:
        raise RuntimeError(
            "No refresh token returned. Remove JARVIS from "
            "https://myaccount.google.com/permissions and connect again."
        )
    save_gmail_tokens(refresh, body.get("access_token", ""))
    _PKCE_FILE.unlink(missing_ok=True)
    return "Gmail and Calendar connected successfully."


def _access_token() -> str:
    cfg = load_llm_config()
    cached = (cfg.get("gmail_access_token") or "").strip()
    c = _creds()
    if not c["client_id"]:
        raise RuntimeError("Gmail not configured — add Client ID in Settings.")
    if not c["refresh_token"]:
        raise RuntimeError("Gmail not connected — tap Connect Gmail in Settings.")

    data: dict[str, str] = {
        "client_id": c["client_id"],
        "refresh_token": c["refresh_token"],
        "grant_type": "refresh_token",
    }
    if c["client_secret"]:
        data["client_secret"] = c["client_secret"]

    resp = requests.post(_TOKEN_URL, data=data, timeout=30)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Gmail token refresh failed — tap Connect Gmail again.")
    save_llm_config({"gmail_access_token": token})
    return token


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_access_token()}"}


def list_messages(max_results: int = 8, query: str = "") -> list[dict[str, Any]]:
    params: dict[str, Any] = {"maxResults": min(max_results, 20)}
    if query:
        params["q"] = query
    r = requests.get(f"{_GMAIL}/messages", headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    items = r.json().get("messages") or []
    out: list[dict[str, Any]] = []
    for item in items[:max_results]:
        mid = item.get("id")
        if not mid:
            continue
        detail = requests.get(
            f"{_GMAIL}/messages/{mid}",
            headers=_headers(),
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            timeout=30,
        )
        if not detail.ok:
            continue
        data = detail.json()
        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        out.append({
            "id": mid,
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "snippet": data.get("snippet", ""),
        })
    return out


def read_message(message_id: str = "", query: str = "") -> str:
    mid = message_id
    if not mid and query:
        hits = list_messages(max_results=1, query=query)
        if not hits:
            return "No email found for that search."
        mid = hits[0]["id"]
    if not mid:
        return "Need a message id or search query to read."

    r = requests.get(
        f"{_GMAIL}/messages/{mid}",
        headers=_headers(),
        params={"format": "full"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    body = _extract_body(data.get("payload", {})) or data.get("snippet", "")
    body = body.strip()[:2000]
    return (
        f"From: {headers.get('From', '')}\n"
        f"Subject: {headers.get('Subject', '')}\n"
        f"Date: {headers.get('Date', '')}\n\n"
        f"{body}"
    )


def _extract_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts") or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts") or []:
        text = _extract_body(part)
        if text:
            return text
    return ""


def create_draft(to: str, subject: str, body: str) -> str:
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    r = requests.post(
        f"{_GMAIL}/drafts",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"message": {"raw": raw}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("id", "draft created")


def send_email(to: str, subject: str, body: str) -> str:
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    r = requests.post(
        f"{_GMAIL}/messages/send",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("id", "sent")


def open_gmail(query: str = "") -> str:
    import subprocess

    q = urllib.parse.quote(query) if query else ""
    url = f"https://mail.google.com/mail/u/0/{'#search/' + q if q else ''}"
    subprocess.run(["open", url], check=False)
    return f"Opened Gmail{f' searching {query}' if query else ''}, sir."


def list_calendar_events(max_results: int = 8) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    r = requests.get(
        _CALENDAR,
        headers=_headers(),
        params={
            "timeMin": now,
            "timeMax": end,
            "maxResults": min(max_results, 20),
            "singleEvents": True,
            "orderBy": "startTime",
        },
        timeout=30,
    )
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    for ev in r.json().get("items") or []:
        start = ev.get("start", {})
        when = start.get("dateTime") or start.get("date") or ""
        out.append({
            "summary": ev.get("summary", "(no title)"),
            "when": when,
            "location": ev.get("location", ""),
        })
    return out


def gmail_action(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "list").lower().strip()
    if player:
        player.write_log(f"[Gmail] {action}")

    if not gmail_configured():
        return (
            "Gmail is not connected. Open Settings → Gmail, paste your Client ID, "
            "then tap Connect Gmail."
        )

    try:
        if action in ("list", "search", "find"):
            query = parameters.get("query") or parameters.get("q") or "is:inbox"
            msgs = list_messages(max_results=int(parameters.get("max") or 8), query=query)
            if not msgs:
                return "No emails found."
            lines = [f"- {m['subject']} — from {m['from']}" for m in msgs]
            return "Mail results:\n" + "\n".join(lines)

        if action == "read":
            return read_message(
                message_id=parameters.get("id") or parameters.get("message_id") or "",
                query=parameters.get("query") or parameters.get("q") or "",
            )

        if action == "open":
            return open_gmail(parameters.get("query") or parameters.get("q") or "")

        if action in ("draft", "create_draft"):
            to = parameters.get("to") or parameters.get("recipient") or ""
            subject = parameters.get("subject") or ""
            body = parameters.get("body") or parameters.get("message") or ""
            if not to or not subject:
                return "Need recipient and subject to draft."
            draft_id = create_draft(to, subject, body)
            return f"Draft saved ({draft_id})."

        if action == "send":
            to = parameters.get("to") or parameters.get("recipient") or ""
            subject = parameters.get("subject") or ""
            body = parameters.get("body") or parameters.get("message") or ""
            if not to or not subject or not body:
                return "Need recipient, subject, and body to send."
            mid = send_email(to, subject, body)
            return f"Email sent to {to} (id {mid})."

        if action in ("calendar", "events"):
            events = list_calendar_events(max_results=int(parameters.get("max") or 8))
            if not events:
                return "No upcoming calendar events in the next two weeks."
            lines = [f"- {e['summary']} at {e['when']}" for e in events]
            return "Upcoming calendar:\n" + "\n".join(lines)

        return (
            "Gmail actions: list, search, read, open, draft, send, calendar. "
            "Example: search query from:boss subject:invoice"
        )
    except Exception as e:
        return f"Gmail error: {e}"
