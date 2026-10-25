"""In-process screening job manager.

Screening may need to fetch financial data for hundreds of candidates, so the
frontend creates a job and polls progress instead of holding a long HTTP
request open.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..engine import run_screen
from ..providers.base import DataNotReady, DataProvider


@dataclass
class ScreenJob:
    id: str
    status: str = "queued"
    progress: dict[str, Any] = field(default_factory=lambda: {"stage": "queued", "done": 0, "total": 1, "message": "排队中"})
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        payload = {
            "job_id": self.id,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_result:
            payload["result"] = self.result
        return payload


class ScreenJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, ScreenJob] = {}
        self._tasks: set[asyncio.Task] = set()

    def _cleanup(self) -> None:
        now = time.time()
        stale = [
            job_id
            for job_id, job in self._jobs.items()
            if now - job.updated_at > 3600 and job.status in {"done", "failed"}
        ]
        for job_id in stale:
            self._jobs.pop(job_id, None)

    async def create(self, dsl: dict[str, Any], provider: DataProvider) -> ScreenJob:
        self._cleanup()
        job = ScreenJob(id=uuid.uuid4().hex[:12])
        self._jobs[job.id] = job
        task = asyncio.create_task(self._run(job, dsl, provider))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: ScreenJob, dsl: dict[str, Any], provider: DataProvider) -> None:
        job.status = "running"
        job.updated_at = time.time()

        async def progress(stage: str, done: int, total: int, message: str) -> None:
            job.progress = {
                "stage": stage,
                "done": done,
                "total": total,
                "message": message,
            }
            job.updated_at = time.time()

        try:
            result = await run_screen(dsl, provider, fetch=True, progress=progress)
            job.result = result
            job.status = "done"
            job.progress = {"stage": "done", "done": 1, "total": 1, "message": "筛选完成"}
        except DataNotReady as exc:
            job.status = "failed"
            job.error = {"code": exc.code, "message": exc.message, "hint": exc.hint}
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = {"code": "SCREEN_FAILED", "message": str(exc)}
        finally:
            job.updated_at = time.time()

    def get(self, job_id: str) -> ScreenJob | None:
        return self._jobs.get(job_id)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()


jobs = ScreenJobManager()
