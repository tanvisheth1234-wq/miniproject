"""Runs simulator scenarios for the API without blocking the live lab.

Each run is CPU-bound (a whole mesh on a virtual clock), so they go to a
pool of worker *processes*: the event loop that serves the WebSocket never
stalls, and several runs use several cores at once. The caller gets a job
id straight away and polls ``get`` for progress, then for the aggregated
section 16 table."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

from sim.scenarios import SCENARIOS, aggregate, run_once


class JobManager:
    def __init__(self, workers: Optional[int] = None) -> None:
        self._workers = workers or max(1, min(4, (os.cpu_count() or 2) - 1))
        self._pool: Optional[ProcessPoolExecutor] = None
        self._jobs: dict[str, dict] = {}
        self._tasks: set[asyncio.Task] = set()

    def _executor(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self._workers)
        return self._pool

    def submit(self, scenario: str, runs: int, nodes: Optional[int], loss: Optional[float], seed: int) -> dict:
        sc = SCENARIOS[scenario]
        modes = ["weighted", "hopcount"] if sc.compare_routing else ["weighted"]
        job = {
            "id": uuid.uuid4().hex[:10], "scenario": scenario, "title": sc.title, "status": "running",
            "runs": runs, "nodes": nodes, "loss": loss, "seed": seed, "modes": modes,
            "completed": 0, "total": runs * len(modes), "started": time.time(), "finished": None,
            "summary": None, "per_run": [], "error": None,
        }
        self._jobs[job["id"]] = job
        task = asyncio.create_task(self._run(job, sc.id, modes))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return self._public(job)

    async def _run(self, job: dict, scenario: str, modes: list[str]) -> None:
        loop = asyncio.get_running_loop()
        results: dict[str, list[dict]] = {m: [] for m in modes}

        async def one(mode: str, i: int) -> None:
            result = await loop.run_in_executor(
                self._executor(), run_once, scenario, job["seed"] + i, job["nodes"], job["loss"], mode
            )
            results[mode].append(result)
            job["completed"] += 1
            job["per_run"].append({
                "mode": mode, "seed": result["seed"], "delivery_ratio": result["metrics"]["delivery_ratio"],
                "sent": result["metrics"]["sent"], "delivered": result["metrics"]["delivered"],
                "wall_s": result["wall_s"],
            })

        try:
            await asyncio.gather(*(one(m, i) for m in modes for i in range(job["runs"])))
            job["summary"] = {m: aggregate(results[m]) for m in modes}
            job["nodes_in_mesh"] = next(iter(results[modes[0]]))["nodes"]
            job["status"] = "done"
        except Exception as exc:  # surface to the UI rather than losing it in a task
            job["status"], job["error"] = "error", f"{type(exc).__name__}: {exc}"
        finally:
            job["finished"] = time.time()

    @staticmethod
    def _public(job: dict) -> dict:
        return {**job, "per_run": sorted(job["per_run"], key=lambda r: (r["mode"], r["seed"]))}

    def get(self, job_id: str) -> Optional[dict]:
        job = self._jobs.get(job_id)
        return self._public(job) if job else None

    def list(self) -> list[dict]:
        ordered = sorted(self._jobs.values(), key=lambda j: -j["started"])
        return [{k: v for k, v in self._public(j).items() if k != "per_run"} for j in ordered[:20]]

    def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
