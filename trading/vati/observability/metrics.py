"""Minimal metrics registry with Prometheus text exposition (stdlib only).
OpenTelemetry export is added at adoption; the names here are the contract."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Iterable


class Metrics:
    def __init__(self) -> None:
        self._c: dict[tuple[str, tuple], float] = defaultdict(float)
        self._g: dict[tuple[str, tuple], float] = {}
        self._lock = Lock()

    @staticmethod
    def _key(name: str, labels: dict | None) -> tuple[str, tuple]:
        return name, tuple(sorted((labels or {}).items()))

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        with self._lock:
            self._c[self._key(name, labels)] += value

    def set(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._g[self._key(name, labels)] = value

    def get(self, name: str, **labels: str) -> float:
        k = self._key(name, labels)
        return self._c.get(k, self._g.get(k, 0.0))

    def exposition(self) -> str:
        lines: list[str] = []
        for store, typ in ((self._c, "counter"), (self._g, "gauge")):
            for (name, labels), v in sorted(store.items()):
                lab = ",".join(f'{k}="{val}"' for k, val in labels)
                lines.append(f"# TYPE {name} {typ}")
                lines.append(f"{name}{{{lab}}} {v}" if lab else f"{name} {v}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._c.clear(); self._g.clear()


metrics = Metrics()
