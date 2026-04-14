"""
In-memory registry of connected slaves.
Round-robin distribution via next_slave().
"""

from dataclasses import dataclass
from itertools import cycle
from typing import Iterator


@dataclass
class SlaveInfo:
    id: int
    config_id: str
    host: str
    api_port: int
    file_port: int

    def __str__(self) -> str:
        return f"slave-{self.id} '{self.config_id}' ({self.host}  api={self.api_port})"


class SlaveRegistry:
    def __init__(self) -> None:
        self._slaves: dict[int, SlaveInfo] = {}
        self._next_id: int = 1
        self._cycle: Iterator[SlaveInfo] | None = None

    def register(self, config_id: str, host: str, api_port: int, file_port: int) -> SlaveInfo:
        slave = SlaveInfo(id=self._next_id, config_id=config_id, host=host, api_port=api_port, file_port=file_port)
        self._slaves[self._next_id] = slave
        self._next_id += 1
        self._rebuild_cycle()
        return slave

    def remove(self, slave_id: int) -> bool:
        if slave_id in self._slaves:
            del self._slaves[slave_id]
            self._rebuild_cycle()
            return True
        return False

    def get(self, slave_id: int) -> SlaveInfo | None:
        return self._slaves.get(slave_id)

    def all(self) -> list[SlaveInfo]:
        return list(self._slaves.values())

    def next_slave(self) -> SlaveInfo | None:
        """Returns the next slave in round-robin order, or None if empty."""
        if not self._slaves or self._cycle is None:
            return None
        return next(self._cycle)

    def _rebuild_cycle(self) -> None:
        self._cycle = cycle(self._slaves.values()) if self._slaves else None


registry = SlaveRegistry()
