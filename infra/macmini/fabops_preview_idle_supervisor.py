#!/usr/bin/env python3
"""Wake/sleep controller for the public FabOps preview runtime.

The public nginx proxy stays online.  This host-only service starts the
allow-listed preview containers on demand and stops them after an idle window.
It never accepts arbitrary container names or shell commands from HTTP input.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_SERVICES = (
    "live-postgres",
    "live-redpanda",
    "api",
    "inference-worker",
    "projection-worker",
    "intelligence-worker",
    "web",
)
DATA_SERVICES = ("live-postgres", "live-redpanda")
WORKER_SERVICES = ("inference-worker", "projection-worker", "intelligence-worker")


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 1)
    except ValueError:
        return default


@dataclass(slots=True)
class SupervisorStatus:
    state: str
    last_activity: float
    last_wake: float
    idle_seconds: int
    min_up_seconds: int
    project: str


class DockerPreviewRuntime:
    def __init__(
        self,
        *,
        docker_bin: str,
        project: str,
        services: tuple[str, ...] = DEFAULT_SERVICES,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.docker_bin = docker_bin
        self.project = project
        self.services = services
        self.runner = runner

    def _run(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.runner(
            [self.docker_bin, *args],
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def service_map(self) -> dict[str, str]:
        result = self._run(
            [
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                "--format",
                '{{.Label "com.docker.compose.service"}}|{{.Names}}',
            ]
        )
        mapping: dict[str, str] = {}
        for raw in result.stdout.splitlines():
            service, separator, name = raw.partition("|")
            if separator and service and name:
                mapping[service.strip()] = name.strip()
        return mapping

    def _container_state(self, name: str) -> tuple[str, str | None]:
        result = self._run(
            [
                "inspect",
                name,
                "--format",
                '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}',
            ]
        )
        status, _, health = result.stdout.strip().partition("|")
        return status, health or None

    def _container_ready(self, name: str) -> bool:
        status, health = self._container_state(name)
        return status == "running" and health in {None, "healthy"}

    def is_ready(self) -> bool:
        mapping = self.service_map()
        for service in ("api", "web", *DATA_SERVICES):
            name = mapping.get(service)
            if not name or not self._container_ready(name):
                return False
        return True

    def has_any_running(self) -> bool:
        mapping = self.service_map()
        for service in self.services:
            name = mapping.get(service)
            if not name:
                continue
            status, _ = self._container_state(name)
            if status == "running":
                return True
        return False

    def _wait_ready(self, services: tuple[str, ...], timeout: int = 120) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            mapping = self.service_map()
            if all(mapping.get(service) and self._container_ready(mapping[service]) for service in services):
                return
            time.sleep(2)
        raise TimeoutError(f"Timed out waiting for FabOps services: {', '.join(services)}")

    def _start_services(self, services: tuple[str, ...]) -> None:
        mapping = self.service_map()
        missing = [service for service in services if service not in mapping]
        if missing:
            raise RuntimeError(f"FabOps preview containers are missing services: {', '.join(missing)}")
        names = [mapping[service] for service in services]
        self._run(["start", *names])

    def _stop_services(self, services: tuple[str, ...]) -> None:
        mapping = self.service_map()
        names = [mapping[service] for service in services if service in mapping]
        if names:
            self._run(["stop", "--time", "20", *names])

    def start(self) -> None:
        # Data services first, then API/workers, then web.  This avoids exposing
        # a half-ready UI while PostgreSQL/Redpanda are still recovering.
        self._start_services(DATA_SERVICES)
        self._wait_ready(DATA_SERVICES)
        self._start_services(("api", *WORKER_SERVICES))
        self._wait_ready(("api",))
        self._start_services(("web",))
        self._wait_ready(("web",))

    def stop(self) -> None:
        # Stop ingress first and data stores last so in-flight writes can drain.
        self._stop_services(("web",))
        self._stop_services((*WORKER_SERVICES, "api"))
        self._stop_services(("live-redpanda",))
        self._stop_services(("live-postgres",))


class PreviewSupervisor:
    def __init__(
        self,
        runtime: DockerPreviewRuntime,
        *,
        idle_seconds: int,
        min_up_seconds: int,
        state_path: Path,
        disabled_file: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.runtime = runtime
        self.idle_seconds = idle_seconds
        self.min_up_seconds = min_up_seconds
        self.state_path = state_path
        self.disabled_file = disabled_file
        self.clock = clock
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._last_persist = 0.0
        self._last_activity = 0.0
        self._last_wake = 0.0
        self._state = "unknown"
        self._load_state()
        now = self.clock()
        try:
            ready = self.runtime.is_ready()
            any_running = self.runtime.has_any_running()
        except Exception:
            ready = False
            any_running = False
        if ready:
            self._state = "running"
            if self._last_activity <= 0:
                self._last_activity = now
            if self._last_wake <= 0:
                self._last_wake = now
        elif any_running:
            self._state = "partial"
        else:
            self._state = "sleeping"
        self._persist(force=True)

    def _load_state(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._last_activity = float(payload.get("last_activity") or 0.0)
        self._last_wake = float(payload.get("last_wake") or 0.0)

    def _persist(self, *, force: bool = False) -> None:
        now = self.clock()
        if not force and now - self._last_persist < 15:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self.status())
        temp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(self.state_path)
        self._last_persist = now

    def status(self) -> SupervisorStatus:
        with self._lock:
            return SupervisorStatus(
                state=self._state,
                last_activity=self._last_activity,
                last_wake=self._last_wake,
                idle_seconds=self.idle_seconds,
                min_up_seconds=self.min_up_seconds,
                project=self.runtime.project,
            )

    def activity(self) -> str:
        now = self.clock()
        with self._lock:
            self._last_activity = now
            state = self._state
            self._persist()
        if state in {"sleeping", "partial", "error", "unknown"} and not self.disabled_file.exists():
            self.request_wake()
            return "starting"
        return state

    def request_wake(self) -> None:
        with self._lock:
            if self._state == "starting" or self.disabled_file.exists():
                return
            self._state = "starting"
            self._last_activity = self.clock()
            self._persist(force=True)
        threading.Thread(target=self._wake, name="fabops-preview-wake", daemon=True).start()

    def _wake(self) -> None:
        with self._operation_lock:
            try:
                self.runtime.start()
            except Exception as exc:
                with self._lock:
                    self._state = "error"
                    self._persist(force=True)
                print(f"fabops preview wake failed: {type(exc).__name__}: {exc}", flush=True)
                return
            with self._lock:
                now = self.clock()
                self._state = "running"
                self._last_wake = now
                self._last_activity = now
                self._persist(force=True)

    def request_sleep(self) -> None:
        with self._lock:
            if self._state in {"sleeping", "stopping"}:
                return
            self._state = "stopping"
            self._persist(force=True)
        threading.Thread(target=self._sleep, name="fabops-preview-sleep", daemon=True).start()

    def _sleep(self) -> None:
        with self._operation_lock:
            try:
                self.runtime.stop()
            except Exception as exc:
                with self._lock:
                    self._state = "error"
                    self._persist(force=True)
                print(f"fabops preview sleep failed: {type(exc).__name__}: {exc}", flush=True)
                return
            with self._lock:
                self._state = "sleeping"
                self._persist(force=True)
                wake_again = self._last_activity > self.clock() - 30 and not self.disabled_file.exists()
            if wake_again:
                self.request_wake()

    def monitor_once(self) -> None:
        now = self.clock()
        with self._lock:
            state = self._state
            last_activity = self._last_activity
            last_wake = self._last_wake
        if state != "running":
            return
        if now - last_wake < self.min_up_seconds:
            return
        if now - last_activity >= self.idle_seconds:
            self.request_sleep()


class SupervisorHandler(BaseHTTPRequestHandler):
    supervisor: PreviewSupervisor

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/activity":
            state = self.supervisor.activity()
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("X-FabOps-Wake-State", state)
            self.end_headers()
            return
        if self.path == "/status":
            self._json(HTTPStatus.OK, asdict(self.supervisor.status()))
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/wake":
            if self.supervisor.disabled_file.exists():
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"state": "maintenance"})
                return
            self.supervisor.activity()
            self._json(HTTPStatus.ACCEPTED, asdict(self.supervisor.status()))
            return
        if self.path == "/sleep":
            self.supervisor.request_sleep()
            self._json(HTTPStatus.ACCEPTED, asdict(self.supervisor.status()))
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})


def _build_supervisor() -> PreviewSupervisor:
    docker_bin = os.environ.get(
        "FABOPS_DOCKER_BIN",
        "/Applications/OrbStack.app/Contents/MacOS/xbin/docker",
    )
    project = os.environ.get("FABOPS_PREVIEW_PROJECT", "fabops-decision-lab-preview-v07")
    state_path = Path(
        os.environ.get(
            "FABOPS_PREVIEW_IDLE_STATE_PATH",
            str(Path.home() / "Services/fabops-decision-lab-data/public-preview/idle-state.json"),
        )
    )
    disabled_file = Path(
        os.environ.get(
            "FABOPS_PREVIEW_WAKE_DISABLED_FILE",
            str(Path.home() / "Services/fabops-decision-lab-data/public-preview/wake-disabled"),
        )
    )
    runtime = DockerPreviewRuntime(docker_bin=docker_bin, project=project)
    return PreviewSupervisor(
        runtime,
        idle_seconds=_env_int("FABOPS_PREVIEW_IDLE_SECONDS", 2700),
        min_up_seconds=_env_int("FABOPS_PREVIEW_MIN_UP_SECONDS", 300),
        state_path=state_path,
        disabled_file=disabled_file,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    supervisor = _build_supervisor()
    if args.check:
        print(json.dumps(asdict(supervisor.status()), indent=2))
        return 0

    host = os.environ.get("FABOPS_PREVIEW_SUPERVISOR_HOST", "127.0.0.1")
    port = _env_int("FABOPS_PREVIEW_SUPERVISOR_PORT", 8231)
    SupervisorHandler.supervisor = supervisor
    server = ThreadingHTTPServer((host, port), SupervisorHandler)

    def monitor() -> None:
        while True:
            try:
                supervisor.monitor_once()
            except Exception as exc:
                print(f"fabops preview monitor failed: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(15)

    threading.Thread(target=monitor, name="fabops-preview-monitor", daemon=True).start()
    server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
