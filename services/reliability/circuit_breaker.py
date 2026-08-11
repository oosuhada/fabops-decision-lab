from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitBreakerOpen(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_timeout_seconds: float = 30.0
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.reset_timeout_seconds <= 0:
            raise ValueError("reset_timeout_seconds must be > 0")
        self.state = "closed"
        self.failure_count = 0
        self.opened_at: float | None = None

    def _refresh(self) -> None:
        if self.state == "open" and self.opened_at is not None and self.clock() - self.opened_at >= self.reset_timeout_seconds:
            self.state = "half_open"

    def call(self, operation: Callable[[], T]) -> T:
        self._refresh()
        if self.state == "open":
            raise CircuitBreakerOpen("external dependency circuit is open")
        try:
            result = operation()
        except Exception:
            self.failure_count += 1
            if self.state == "half_open" or self.failure_count >= self.failure_threshold:
                self.state = "open"
                self.opened_at = self.clock()
            raise
        self.failure_count = 0
        self.opened_at = None
        self.state = "closed"
        return result

    def snapshot(self) -> dict[str, object]:
        self._refresh()
        return {"state": self.state, "failure_count": self.failure_count, "opened_at": self.opened_at}
