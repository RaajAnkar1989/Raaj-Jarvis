"""Background job queue for agent tasks."""

from __future__ import annotations

import asyncio
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

_lock = threading.Lock()
_jobs: dict[str, "AgentJob"] = {}


@dataclass
class AgentJob:
    goal: str
    client_id: str = ""
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "queued"


def submit_job(goal: str, coro_factory: Callable[[], Awaitable[None]], *, client_id: str = "") -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = AgentJob(goal=goal, client_id=client_id)

    async def _run() -> None:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        try:
            await coro_factory()
            job.status = "done"
        except Exception:
            traceback.print_exc()
            job.status = "failed"

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        threading.Thread(target=lambda: asyncio.run(_run()), daemon=True).start()
    return job_id


def job_status(job_id: str) -> dict[str, Any] | None:
    job = _jobs.get(job_id)
    if not job:
        return None
    return {"id": job_id, "goal": job.goal, "status": job.status, "created": job.created, "source": "daemon"}


def list_jobs() -> list[dict[str, Any]]:
    with _lock:
        return [
            {
                "id": jid,
                "goal": j.goal[:80],
                "status": j.status,
                "source": "daemon",
            }
            for jid, j in _jobs.items()
        ]
