from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, TypeVar

T = TypeVar("T")


class BulkheadRejected(RuntimeError):
    pass


@dataclass
class Bulkhead:
    max_concurrency: int = 4
    acquire_timeout_seconds: float = 0.25
    _semaphore: threading.BoundedSemaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if self.acquire_timeout_seconds < 0:
            raise ValueError("acquire_timeout_seconds must be >= 0")
        self._semaphore = threading.BoundedSemaphore(self.max_concurrency)

    def call(self, operation: Callable[[], T]) -> T:
        acquired = self._semaphore.acquire(timeout=self.acquire_timeout_seconds)
        if not acquired:
            raise BulkheadRejected("external dependency concurrency limit reached")
        try:
            return operation()
        finally:
            self._semaphore.release()
