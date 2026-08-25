from __future__ import annotations

import asyncio
import hmac
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class GatewayMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=40_000)


class GatewayChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[GatewayMessage] = Field(min_length=1, max_length=12)
    temperature: float = Field(default=0.1, ge=0.0, le=0.5)
    response_format: Optional[dict[str, Any]] = None
    max_tokens: Optional[int] = Field(default=None, ge=1)


app = FastAPI(
    title="FabOps Private Narration Gateway",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
_concurrency = asyncio.Semaphore(max(1, int(os.getenv("FABOPS_GATEWAY_MAX_CONCURRENCY", "1"))))
_queue_timeout_seconds = max(0.05, float(os.getenv("FABOPS_GATEWAY_QUEUE_TIMEOUT_SECONDS", "1")))


def _shared_secret() -> str:
    value = os.getenv("FABOPS_GATEWAY_SHARED_SECRET", "")
    if len(value) < 24:
        raise RuntimeError("FABOPS_GATEWAY_SHARED_SECRET must contain at least 24 characters")
    return value


def _authorize(authorization: Optional[str]) -> None:
    supplied = ""
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied, _shared_secret()):
        raise HTTPException(status_code=401, detail="invalid gateway credential")


def _upstream_json(path: str, *, body: Optional[bytes] = None, timeout: float = 5.0) -> dict[str, Any]:
    base = os.getenv("FABOPS_GATEWAY_UPSTREAM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    request = urllib.request.Request(
        f"{base}/{path.lstrip('/')}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _lms_cli() -> str:
    return os.getenv("FABOPS_GATEWAY_LMS_CLI", str(Path.home() / ".lmstudio/bin/lms"))


def _gateway_model() -> str:
    """Client-facing model alias accepted by the private FabOps gateway."""

    return os.getenv("FABOPS_GATEWAY_MODEL", "local-review-qwen-next")


def _model_key() -> str:
    """Installed LM Studio model key.

    The gateway alias and LM Studio runtime identifier are intentionally allowed
    to differ. This lets FabOps keep a stable private contract while reusing a
    model that the user already loaded interactively under LM Studio's normal
    identifier.
    """

    return os.getenv("FABOPS_GATEWAY_MODEL_KEY", "qwen_qwen3-coder-next")


def _loaded_models() -> list[dict[str, Any]]:
    try:
        completed = subprocess.run(
            [_lms_cli(), "ps", "--json"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if completed.returncode != 0:
            return []
        loaded = json.loads(completed.stdout or "[]")
    except Exception:  # noqa: BLE001 - health/load detection must fail closed
        return []
    return [item for item in loaded if isinstance(item, dict)]


def _configured_model_state() -> dict[str, Any] | None:
    alias = _gateway_model()
    model_key = _model_key()
    for item in _loaded_models():
        if str(item.get("identifier") or "") == alias or str(item.get("modelKey") or "") == model_key:
            return item
    return None


def _model_loaded() -> bool:
    return _configured_model_state() is not None


def _model_busy(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    queued = int(item.get("queued") or 0)
    return queued > 0 or status not in {"", "idle", "ready"}


def _interactive_inference_busy() -> bool:
    """Return True when any local LM Studio generation is already active.

    FabOps never inspects prompts or conversation content. Only process-level
    availability metadata is used so an already-running interactive generation
    always wins over a new FabOps request.
    """

    return any(_model_busy(item) for item in _loaded_models())


def _ensure_model() -> str:
    existing = _configured_model_state()
    if existing is not None:
        return str(existing.get("identifier") or _model_key())
    if _interactive_inference_busy():
        raise HTTPException(status_code=429, detail="local model busy")
    model_key = _model_key()
    identifier = _gateway_model()
    context_length = os.getenv("FABOPS_GATEWAY_MODEL_CONTEXT", "8192")
    ttl_seconds = os.getenv("FABOPS_GATEWAY_MODEL_TTL_SECONDS", "900")
    timeout = float(os.getenv("FABOPS_GATEWAY_MODEL_LOAD_TIMEOUT_SECONDS", "120"))
    completed = subprocess.run(
        [
            _lms_cli(),
            "load",
            model_key,
            "--identifier",
            identifier,
            "--context-length",
            context_length,
            "--gpu",
            "max",
            "--parallel",
            "1",
            "--ttl",
            ttl_seconds,
            "--yes",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    loaded = _configured_model_state()
    if completed.returncode != 0 or loaded is None:
        raise RuntimeError("configured local model could not be loaded")
    return str(loaded.get("identifier") or identifier)


@app.get("/health")
async def health() -> dict[str, Any]:
    configured_model = _gateway_model()
    model_key = _model_key()
    try:
        result = await asyncio.to_thread(_upstream_json, "/models", timeout=3.0)
        upstream = "ready"
        model_installed = any(str(item.get("id")) == model_key for item in result.get("data", []))
        state = _configured_model_state()
        model_loaded = state is not None
        model_busy = bool(state and _model_busy(state))
        upstream_identifier = str(state.get("identifier")) if state else None
        queued = int(state.get("queued") or 0) if state else 0
    except Exception:  # noqa: BLE001 - health must remain queryable when LM Studio is unavailable
        upstream = "unavailable"
        model_installed = False
        model_loaded = False
        model_busy = False
        upstream_identifier = None
        queued = 0
    return {
        "status": "ready" if upstream == "ready" and model_loaded and not model_busy else "busy" if model_busy else "degraded",
        "service": "fabops-private-narration-gateway",
        "upstream": upstream,
        "configured_model": configured_model,
        "configured_model_key": model_key,
        "upstream_model_identifier": upstream_identifier,
        "configured_model_installed": model_installed,
        "configured_model_loaded": model_loaded,
        "local_inference_busy": model_busy,
        "local_queued_requests": queued,
        "tools_enabled": False,
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    body: GatewayChatRequest,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    _authorize(authorization)
    configured_model = _gateway_model()
    if body.model != configured_model:
        raise HTTPException(status_code=422, detail="model selection is fixed by the gateway")
    max_output_tokens = max(1, int(os.getenv("FABOPS_GATEWAY_MAX_OUTPUT_TOKENS", "900")))
    timeout = float(os.getenv("FABOPS_GATEWAY_UPSTREAM_TIMEOUT_SECONDS", "45"))
    try:
        await asyncio.wait_for(_concurrency.acquire(), timeout=_queue_timeout_seconds)
    except TimeoutError as exc:
        raise HTTPException(status_code=429, detail="local model busy") from exc
    try:
        if await asyncio.to_thread(_interactive_inference_busy):
            raise HTTPException(status_code=429, detail="local model busy")
        upstream_model = await asyncio.to_thread(_ensure_model)
        # A short second check closes most of the race where an interactive
        # request starts just before FabOps dispatches its own generation.
        await asyncio.sleep(0.12)
        state = await asyncio.to_thread(_configured_model_state)
        if state is not None and _model_busy(state):
            raise HTTPException(status_code=429, detail="local model busy")
        payload = {
            "model": upstream_model,
            "messages": [message.model_dump() for message in body.messages],
            "temperature": body.temperature,
            "stream": False,
            "max_tokens": min(body.max_tokens or max_output_tokens, max_output_tokens),
        }
        if body.response_format is not None:
            payload["response_format"] = body.response_format
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        max_request_bytes = max(1024, int(os.getenv("FABOPS_GATEWAY_MAX_REQUEST_BYTES", "65536")))
        if len(encoded) > max_request_bytes:
            raise HTTPException(status_code=413, detail="request exceeds gateway size limit")
        return await asyncio.wait_for(asyncio.to_thread(_upstream_json, "/chat/completions", body=encoded, timeout=timeout), timeout=timeout + 1)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="local model timeout") from exc
    except urllib.error.HTTPError as exc:
        if exc.code in {409, 429}:
            raise HTTPException(status_code=429, detail="local model busy") from exc
        raise HTTPException(status_code=502, detail=f"local model rejected request ({exc.code})") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - do not leak upstream details
        raise HTTPException(status_code=502, detail="local model unavailable") from exc
    finally:
        _concurrency.release()
