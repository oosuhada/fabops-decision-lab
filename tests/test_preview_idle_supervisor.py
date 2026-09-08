from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "infra/macmini/fabops_preview_idle_supervisor.py"
SPEC = importlib.util.spec_from_file_location("fabops_preview_idle_supervisor", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeRuntime:
    project = "fabops-decision-lab-preview-v07"

    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.started = 0
        self.stopped = 0

    def is_ready(self) -> bool:
        return self.ready

    def has_any_running(self) -> bool:
        return self.ready

    def start(self) -> None:
        self.started += 1
        self.ready = True

    def stop(self) -> None:
        self.stopped += 1
        self.ready = False


def _supervisor(tmp_path: Path, runtime: FakeRuntime, now: list[float]):
    return MODULE.PreviewSupervisor(
        runtime,
        idle_seconds=2700,
        min_up_seconds=300,
        state_path=tmp_path / "state.json",
        disabled_file=tmp_path / "disabled",
        clock=lambda: now[0],
    )


def test_running_preview_sleeps_after_45_idle_minutes(tmp_path: Path) -> None:
    now = [10_000.0]
    runtime = FakeRuntime(ready=True)
    supervisor = _supervisor(tmp_path, runtime, now)
    now[0] += 2701

    # Test the policy decision synchronously; request_sleep itself remains async
    # in production so HTTP requests never block on Docker shutdown.
    supervisor.request_sleep = supervisor._sleep  # type: ignore[method-assign]
    supervisor.monitor_once()

    assert runtime.stopped == 1
    assert supervisor.status().state == "sleeping"


def test_activity_wakes_sleeping_preview(tmp_path: Path) -> None:
    now = [20_000.0]
    runtime = FakeRuntime(ready=False)
    supervisor = _supervisor(tmp_path, runtime, now)
    supervisor.request_wake = supervisor._wake  # type: ignore[method-assign]

    state = supervisor.activity()

    assert state == "starting"
    assert runtime.started == 1
    assert supervisor.status().state == "running"


def test_minimum_uptime_prevents_immediate_sleep(tmp_path: Path) -> None:
    now = [30_000.0]
    runtime = FakeRuntime(ready=True)
    supervisor = _supervisor(tmp_path, runtime, now)
    supervisor._last_activity = now[0] - 4000
    supervisor._last_wake = now[0] - 299

    supervisor.monitor_once()

    assert runtime.stopped == 0
    assert supervisor.status().state == "running"
