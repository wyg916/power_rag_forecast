from __future__ import annotations

import uuid
from datetime import datetime
from time import perf_counter
from typing import Any


class TraceManager:
    def __init__(self, question: str):
        self.trace_id = "trace_" + uuid.uuid4().hex[:12]
        self._started = perf_counter()
        self.payload: dict[str, Any] = {
            "trace_id": self.trace_id,
            "question": question,
            "started_at": datetime.now().isoformat(sep=" ", timespec="milliseconds"),
            "steps": [],
        }

    def set(self, **kwargs: Any) -> None:
        self.payload.update(kwargs)

    def step(self, name: str, **kwargs: Any) -> None:
        self.payload["steps"].append({"name": name, "elapsed_ms": round((perf_counter() - self._started) * 1000), **kwargs})

    def finish(self, **kwargs: Any) -> dict[str, Any]:
        self.payload.update(
            {
                "ended_at": datetime.now().isoformat(sep=" ", timespec="milliseconds"),
                "duration_ms": round((perf_counter() - self._started) * 1000),
                **kwargs,
            }
        )
        return self.payload
