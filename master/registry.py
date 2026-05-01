"""
In-memory registry of connected workers.
"""

from dataclasses import dataclass, field
from itertools import cycle
from typing import Iterator

from .petnames import pick


@dataclass
class WorkerInfo:
    id: int
    config_id: str
    host: str
    api_port: int
    scheme: str = "http"

    def __str__(self) -> str:
        return f"worker-{self.id} '{self.config_id}' ({self.scheme}://{self.host}:{self.api_port})"


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[int, WorkerInfo] = {}
        self._next_id: int = 1
        self._cycle: Iterator[WorkerInfo] | None = None

    def _used_config_ids(self) -> set[str]:
        return {w.config_id for w in self._workers.values()}

    def register(self, config_id: str, host: str, api_port: int, scheme: str = "http") -> WorkerInfo:
        if config_id:
            existing = next((s for s in self._workers.values() if s.config_id == config_id), None)
            if existing:
                existing.host = host
                existing.api_port = api_port
                existing.scheme = scheme
                self._rebuild_cycle()
                return existing
        else:
            config_id = pick(self._used_config_ids())

        worker = WorkerInfo(id=self._next_id, config_id=config_id, host=host, api_port=api_port, scheme=scheme)
        self._workers[self._next_id] = worker
        self._next_id += 1
        self._rebuild_cycle()
        return worker

    def remove(self, worker_id: int) -> bool:
        if worker_id in self._workers:
            del self._workers[worker_id]
            self._rebuild_cycle()
            return True
        return False

    def remove_by_config_id(self, config_id: str) -> bool:
        existing = self.get_by_config_id(config_id)
        if existing:
            return self.remove(existing.id)
        return False

    def get(self, worker_id: int) -> WorkerInfo | None:
        return self._workers.get(worker_id)

    def get_by_config_id(self, config_id: str) -> WorkerInfo | None:
        return next((s for s in self._workers.values() if s.config_id == config_id), None)

    def all(self) -> list[WorkerInfo]:
        return list(self._workers.values())

    def _rebuild_cycle(self) -> None:
        self._cycle = cycle(self._workers.values()) if self._workers else None


registry = WorkerRegistry()
