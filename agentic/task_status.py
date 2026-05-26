"""Unified agent task status for PWA and background jobs."""

from __future__ import annotations

from typing import Any


def list_all_agent_tasks() -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []

    try:
        from agent.task_queue import get_queue

        for item in get_queue().get_all_statuses():
            tasks.append({
                "id": item.get("task_id"),
                "goal": item.get("goal", ""),
                "status": item.get("status", "unknown"),
                "source": "agent_queue",
            })
    except Exception:
        pass

    try:
        from memory.db import init_db, list_active_tasks

        init_db()
        for row in list_active_tasks(limit=15):
            tasks.append({
                "id": f"mem-{row['id']}",
                "goal": row.get("title") or row.get("content", "")[:80],
                "status": row.get("status", "pending"),
                "source": "memory",
            })
    except Exception:
        pass

    try:
        from agentic.daemon import list_jobs

        for job in list_jobs():
            tasks.append(job)
    except Exception:
        pass

    return tasks[:30]
