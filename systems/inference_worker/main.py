from __future__ import annotations

import json
import os
import signal
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime
from threading import Event
from typing import Any

from adapters.postgres import PostgresConfig, PostgresRepository
from services.intelligence.inference import persist_completed_inference
from services.narration.queue import retry_backoff_seconds
from services.narration.service import LocalNarrationBusyError, NarrationService


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _job_age_seconds(job: dict[str, Any]) -> float:
    created_at = _parse_timestamp(str(job.get("created_at") or ""))
    if created_at is None:
        return 0.0
    return max(0.0, (datetime.now(created_at.tzinfo) - created_at).total_seconds())


def _local_gateway_health(narration: NarrationService) -> dict[str, Any]:
    provider = next((item for item in narration.providers or [] if item.name == "local-qwen"), None)
    if provider is None:
        return {"state": "OFFLINE", "model": None, "loaded": False, "metadata": {}, "error_class": "LocalProviderUnconfigured"}
    base_url = str(getattr(provider, "base_url", "")).rstrip("/")
    health_root = base_url[:-3] if base_url.endswith("/v1") else base_url
    try:
        with urllib.request.urlopen(f"{health_root}/health", timeout=3.0) as response:
            payload = json.load(response)
        loaded = bool(payload.get("configured_model_loaded"))
        busy = bool(payload.get("local_inference_busy"))
        state = "BUSY" if busy else "READY" if loaded and payload.get("upstream") == "ready" else "LOADING" if payload.get("upstream") == "ready" else "DEGRADED"
        return {
            "state": state,
            "model": payload.get("configured_model"),
            "loaded": loaded,
            "metadata": {
                "upstream": payload.get("upstream"),
                "upstream_model_identifier": payload.get("upstream_model_identifier"),
                "local_queued_requests": payload.get("local_queued_requests", 0),
            },
            "error_class": None,
        }
    except urllib.error.HTTPError as exc:
        return {"state": "DEGRADED", "model": getattr(provider, "model", None), "loaded": None, "metadata": {"http_status": exc.code}, "error_class": "HTTPError"}
    except Exception as exc:  # noqa: BLE001 - provider status must remain bounded and non-secret
        return {"state": "OFFLINE", "model": getattr(provider, "model", None), "loaded": None, "metadata": {}, "error_class": type(exc).__name__}


def _record_health(repository: PostgresRepository, narration: NarrationService, *, active_jobs: int = 0, success: bool = False, error_class: str | None = None) -> dict[str, Any]:
    health = _local_gateway_health(narration)
    repository.update_inference_runtime_state(
        "local-qwen",
        state=str(health["state"]),
        model=health.get("model"),
        model_loaded=health.get("loaded"),
        active_jobs=active_jobs,
        metadata=dict(health.get("metadata", {})),
        success=success,
        error_class=error_class or health.get("error_class"),
    )
    return health


def _persist_terminal_fallback(
    repository: PostgresRepository,
    narration: NarrationService,
    job: dict[str, Any],
    *,
    error_class: str,
) -> dict[str, Any]:
    request_document = job["request_document"]
    packet = request_document["packet"]
    audience = str(request_document.get("audience") or "engineer")
    intent = str(request_document.get("intent") or "situation_update")
    brief = narration.cached_or_deterministic(packet, audience, intent=intent)
    persisted = persist_completed_inference(repository, job, brief)
    result = {
        "brief": brief,
        "assessment_persisted": bool(persisted),
        "queue_wait_ms": round(_job_age_seconds(job) * 1000.0, 3),
    }
    repository.finish_inference_job(
        str(job["job_id"]),
        status="FALLBACK",
        result_document=result,
        error_class=error_class,
        error_detail_bounded="local inference attempts exhausted; deterministic assessment persisted",
    )
    return result


def main() -> None:
    dsn = os.getenv("FABOPS_POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError("FABOPS_POSTGRES_DSN is required")
    repository = PostgresRepository(PostgresConfig(dsn))
    narration = NarrationService()
    stop_event = Event()
    poll_interval = max(0.5, float(os.getenv("FABOPS_INFERENCE_QUEUE_POLL_SECONDS", "1.5")))
    lease_seconds = max(30, int(os.getenv("FABOPS_INFERENCE_LEASE_SECONDS", "120")))
    worker_id = f"{socket.gethostname()}:{os.getpid()}"

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_health_at = 0.0
    while not stop_event.is_set():
        try:
            now = time.monotonic()
            if now - last_health_at >= 5.0:
                _record_health(repository, narration)
                last_health_at = now
            job = repository.claim_inference_job(worker_id, lease_seconds=lease_seconds)
            if job is None:
                stop_event.wait(poll_interval)
                continue
            request_document = job["request_document"]
            packet = request_document["packet"]
            audience = str(request_document.get("audience") or "engineer")
            intent = str(request_document.get("intent") or "situation_update")
            age_seconds = _job_age_seconds(job)
            fallback_after = job.get("fallback_after_seconds")
            cloud_wait_elapsed = bool(
                job.get("allow_vertex_fallback")
                and fallback_after is not None
                and age_seconds >= float(fallback_after)
            )
            try:
                _record_health(repository, narration, active_jobs=1)
                brief = narration.generate(
                    packet,
                    audience,
                    intent=intent,
                    allow_cloud_fallback=cloud_wait_elapsed,
                    defer_on_local_busy=not cloud_wait_elapsed,
                )
            except LocalNarrationBusyError:
                repository.requeue_inference_job(
                    str(job["job_id"]),
                    status="WAITING_FOR_LOCAL",
                    backoff_seconds=retry_backoff_seconds(int(job["attempt_count"]), busy=True),
                    error_class="LocalModelBusy",
                    error_detail_bounded="interactive/local inference is active; FabOps deferred without cloud fallback",
                    busy=True,
                )
                _record_health(repository, narration, error_class=None)
                continue
            except Exception as exc:  # noqa: BLE001 - durable queue retries bounded provider failures
                if int(job["attempt_count"]) < int(job["max_attempts"]):
                    repository.requeue_inference_job(
                        str(job["job_id"]),
                        status="RETRY",
                        backoff_seconds=retry_backoff_seconds(int(job["attempt_count"]), busy=False),
                        error_class=type(exc).__name__,
                        error_detail_bounded="local inference worker provider failure",
                    )
                    _record_health(repository, narration, error_class=type(exc).__name__)
                    continue
                _persist_terminal_fallback(repository, narration, job, error_class=type(exc).__name__)
                _record_health(repository, narration, error_class=type(exc).__name__)
                continue

            local_failure_without_cloud = (
                brief.get("mode") == "deterministic_fallback"
                and "local-qwen" in str(brief.get("fallback_reason") or "")
                and not cloud_wait_elapsed
            )
            if local_failure_without_cloud and int(job["attempt_count"]) < int(job["max_attempts"]):
                repository.requeue_inference_job(
                    str(job["job_id"]),
                    status="RETRY",
                    backoff_seconds=retry_backoff_seconds(int(job["attempt_count"]), busy=False),
                    error_class="LocalProviderFailure",
                    error_detail_bounded="local provider failed before cloud fallback wait budget elapsed",
                )
                _record_health(repository, narration, error_class="LocalProviderFailure")
                continue

            persisted = persist_completed_inference(repository, job, brief)
            provider = str(brief.get("provider") or "deterministic")
            terminal_status = "COMPLETED" if provider == "local-qwen" and brief.get("mode") == "llm" else "FALLBACK"
            result = {
                "brief": brief,
                "assessment_persisted": bool(persisted),
                "queue_wait_ms": round(age_seconds * 1000.0, 3),
            }
            repository.finish_inference_job(str(job["job_id"]), status=terminal_status, result_document=result)
            _record_health(repository, narration, success=provider == "local-qwen")
            print(
                json.dumps(
                    {
                        "service": "fabops-inference-worker",
                        "job_id": job["job_id"],
                        "case_id": job["case_id"],
                        "status": terminal_status,
                        "provider": provider,
                        "queue_wait_ms": result["queue_wait_ms"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - long-running worker remains observable and retries next cycle
            print(
                json.dumps(
                    {"service": "fabops-inference-worker", "error": type(exc).__name__, "detail": str(exc)[:200]},
                    sort_keys=True,
                ),
                flush=True,
            )
            stop_event.wait(poll_interval)


if __name__ == "__main__":
    main()
