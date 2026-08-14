from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

DECISION_BRIEF_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": "decision-brief-v1"},
        "case_id": {"type": "string"},
        "audience": {"type": "string", "enum": ["manager", "engineer"]},
        "headline": {"type": "string", "maxLength": 80},
        "summary": {"type": "string", "maxLength": 240},
        "recommended_option_id": {"type": "string"},
        "sections": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section_id": {"type": "string"},
                    "title": {"type": "string", "maxLength": 60},
                    "body": {"type": "string", "maxLength": 240},
                    "evidence_refs": {"type": "array", "maxItems": 2, "items": {"type": "string"}},
                },
                "required": ["section_id", "title", "body", "evidence_refs"],
            },
        },
        "citations": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
        "uncertainties": {"type": "array", "maxItems": 2, "items": {"type": "string", "maxLength": 240}},
        "limitations": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string", "maxLength": 240}},
    },
    "required": [
        "schema_version",
        "case_id",
        "audience",
        "headline",
        "summary",
        "recommended_option_id",
        "sections",
        "citations",
        "uncertainties",
        "limitations",
    ],
}


class NarrationProviderPort(Protocol):
    name: str

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def _extract_json(content: str) -> dict[str, Any]:
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1]
        value = value.rsplit("```", 1)[0]
    return json.loads(value)


class _UrllibAuthResponse:
    def __init__(self, response: Any) -> None:
        self.status = int(response.status)
        self.data = response.read()
        self.headers = response.headers


class _UrllibAuthRequest:
    """google-auth transport backed only by Python's HTTPS-capable stdlib."""

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **_: Any,
    ) -> _UrllibAuthResponse:
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        return _UrllibAuthResponse(response)


@dataclass
class OpenAICompatibleNarrationProvider:
    base_url: str
    model: str
    bearer_token: str | None = None
    timeout_seconds: float = 45.0
    max_output_tokens: int = 900
    name: str = "local-openai-compatible"

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0.1,
                "max_tokens": self.max_output_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "fabops_decision_brief",
                        "strict": True,
                        "schema": DECISION_BRIEF_RESPONSE_SCHEMA,
                    },
                },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
                ],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = urllib.request.Request(f"{self.base_url.rstrip('/')}/chat/completions", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            result = json.load(response)
        choice = result["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("provider output token limit reached")
        content = choice["message"]["content"]
        return _extract_json(str(content))


@dataclass
class VertexAINarrationProvider:
    project_id: str
    location: str = "global"
    model: str = "gemini-2.5-flash-lite"
    timeout_seconds: float = 20.0
    max_output_tokens: int = 700
    auth_mode: str = "adc"
    name: str = "vertex-ai-gemini"

    def _access_token(self) -> str:
        if self.auth_mode == "gcloud":
            completed = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                raise RuntimeError("gcloud user credential is unavailable for Vertex AI narration")
            return completed.stdout.strip()
        try:
            import google.auth
        except ImportError as exc:  # pragma: no cover - exercised only when optional provider is configured
            raise RuntimeError("google-auth is required for Vertex AI narration") from exc
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(_UrllibAuthRequest())
        if not credentials.token:
            raise RuntimeError("Vertex AI ADC returned no access token")
        return str(credentials.token)

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        hostname = "aiplatform.googleapis.com" if self.location == "global" else f"{self.location}-aiplatform.googleapis.com"
        provider = OpenAICompatibleNarrationProvider(
            base_url=(
                f"https://{hostname}/v1/projects/{self.project_id}/locations/"
                f"{self.location}/endpoints/openapi"
            ),
            model=f"google/{self.model}",
            bearer_token=self._access_token(),
            timeout_seconds=self.timeout_seconds,
            max_output_tokens=self.max_output_tokens,
            name=self.name,
        )
        return provider.generate_json(system_prompt, payload)


def providers_from_env() -> list[NarrationProviderPort]:
    mode = os.getenv("FABOPS_NARRATION_MODE", "deterministic").strip().lower()
    if mode == "deterministic":
        return []
    providers: list[NarrationProviderPort] = []
    local_enabled = os.getenv("FABOPS_LOCAL_LLM_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
    local_url = os.getenv("FABOPS_LOCAL_LLM_BASE_URL", "").strip()
    local_model = os.getenv("FABOPS_LOCAL_LLM_MODEL", "local-review-qwen-next").strip()
    if local_enabled and local_url and mode in {"auto", "local"}:
        providers.append(
            OpenAICompatibleNarrationProvider(
                base_url=local_url,
                model=local_model,
                bearer_token=os.getenv("FABOPS_LOCAL_LLM_TOKEN") or None,
                timeout_seconds=float(os.getenv("FABOPS_LOCAL_LLM_TIMEOUT_SECONDS", "45")),
                max_output_tokens=int(os.getenv("FABOPS_LOCAL_LLM_MAX_OUTPUT_TOKENS", "700")),
                name="local-qwen",
            )
        )
    vertex_enabled = os.getenv("FABOPS_VERTEX_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
    vertex_project = os.getenv("FABOPS_VERTEX_PROJECT", "").strip()
    if vertex_enabled and vertex_project and mode in {"auto", "vertex"}:
        providers.append(
            VertexAINarrationProvider(
                project_id=vertex_project,
                location=os.getenv("FABOPS_VERTEX_LOCATION", "global").strip() or "global",
                model=os.getenv("FABOPS_VERTEX_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite",
                max_output_tokens=int(os.getenv("FABOPS_VERTEX_MAX_OUTPUT_TOKENS", "600")),
                auth_mode=os.getenv("FABOPS_VERTEX_AUTH_MODE", "adc").strip().lower() or "adc",
            )
        )
    return providers
