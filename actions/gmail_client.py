"""Gmail API — list, draft, and send (optional; credentials in config or PWA settings)."""

from __future__ import annotations

import base64
import json
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests

from core.llm_config import load_llm_config, save_llm_config

_BASE = Path(__file__).resolve().parent.parent
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"


def _creds() -> dict[str, str]:
    cfg = load_llm_config()
    return {
        "client_id": (cfg.get("gmail_client_id") or "").strip(),
        "client_secret": (cfg.get("gmail_client_secret") or "").strip(),
        "refresh_token": (cfg.get("gmail_refresh_token") or "").strip(),
    }


def save_gmail_credentials(client_id: str, client_secret: str, refresh_token: str) -> None:
    save_llm_config({
        "gmail_client_id": client_id.strip(),
        "gmail_client_secret": client_secret.strip(),
        "gmail_refresh_token": refresh_token.strip(),
    })


def gmail_configured() -> bool:
    c = _creds()
    return bool(c["client_id"] and c["client_secret"] and c["refresh_token"])


def _access_token() -> str:
    c = _creds()
    if not gmail_configured():
        raise RuntimeError(
            "Gmail not configured. Add Client ID, Secret, and Refresh Token in Settings."
        )
    resp = requests.post(
        _TOKEN_URL,
        data={
            "client_id": c["client_id"],
            "client_secret": c["client_secret"],
            "refresh_token": c["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Gmail token refresh failed — check refresh token.")
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


def gmail_action(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "list").lower().strip()
    if player:
        player.write_log(f"[Gmail] {action}")

    if not gmail_configured():
        return (
            "Gmail is not set up. Open Raajarvis Settings → Gmail and add API credentials. "
            "See: https://console.cloud.google.com/apis/credentials"
        )

    try:
        if action == "list":
            query = parameters.get("query") or parameters.get("q") or "is:inbox"
            msgs = list_messages(max_results=int(parameters.get("max") or 8), query=query)
            if not msgs:
                return "No emails found."
            lines = [f"- {m['subject']} — from {m['from']}" for m in msgs]
            return "Recent mail:\n" + "\n".join(lines)

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

        return "Gmail actions: list, draft, send."
    except Exception as e:
        return f"Gmail error: {e}"
