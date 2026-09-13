from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Protocol

from app.services.llm_client import DEFAULT_BASE_URL, ProviderError, call_openai_compatible
from app.services.llm_config import DeploymentConfig, load_deployments, load_routing_config


class LLMErrorCode(str, Enum):
    RATE_LIMITED = "RATE_LIMITED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INVALID_REQUEST = "INVALID_REQUEST"
    CONTENT_POLICY_ERROR = "CONTENT_POLICY_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass
class LLMError(Exception):
    code: LLMErrorCode
    message: str
    provider: str | None = None
    status_code: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


@dataclass(frozen=True)
class LLMRequest:
    messages: list[dict[str, str]]
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    deployment: DeploymentConfig | None = None
    logical_model: str | None = None
    request_id: str | None = None
    deadline: float | None = None


@dataclass
class LLMResponse:
    content: Any
    provider: str
    model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(Protocol):
    provider_name: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        ...

    def supports(self, request: LLMRequest) -> bool:
        ...


class OpenAICompatibleAdapter:
    provider_name = "openai-compatible"

    def supports(self, request: LLMRequest) -> bool:
        return not request.stream and not request.tools and not request.response_format

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.stream:
            raise LLMError(LLMErrorCode.INVALID_REQUEST, "Streaming is not supported by the current provider integration", self.provider_name)
        if request.tools or request.response_format:
            raise LLMError(LLMErrorCode.INVALID_REQUEST, "Tools and response formats are not supported by the current provider integration", self.provider_name)

        deployment = request.deployment
        timeout = deployment.request_timeout if deployment else 30.0
        if request.deadline is not None:
            timeout = min(timeout, max(0.001, request.deadline - time.monotonic()))
        model = deployment.model if deployment else request.model
        if not model:
            raise LLMError(LLMErrorCode.INVALID_REQUEST, "A model must be configured", self.provider_name)
        base_url = deployment.settings.get("base_url", DEFAULT_BASE_URL) if deployment else DEFAULT_BASE_URL
        api_key = deployment.api_key if deployment else ""
        try:
            content = call_openai_compatible(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=request.messages,
                timeout=timeout,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
            )
        except ProviderError as exc:
            details = {"retry_after_seconds": exc.retry_after} if exc.retry_after is not None else {}
            raise LLMError(_provider_error_code(exc), "LLM provider request failed", self.provider_name, exc.status_code, details) from exc
        if content is None:
            raise LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE, "The LLM provider did not return a response", self.provider_name)
        return LLMResponse(content=content, provider=self.provider_name, model=model, raw={})


class LLMService:
    def __init__(
        self,
        adapter: ProviderAdapter | None = None,
        deployments: tuple[DeploymentConfig, ...] | None = None,
    ) -> None:
        from app.services.llm_router import DeploymentRouter

        selected_adapter = adapter or OpenAICompatibleAdapter()
        configured_deployments = deployments or load_deployments()
        self.adapters: dict[str, ProviderAdapter] = {
            deployment.provider: selected_adapter for deployment in configured_deployments
        }
        self.adapters[selected_adapter.provider_name] = selected_adapter
        self.default_deployment = next((deployment for deployment in configured_deployments if deployment.enabled and deployment.provider in self.adapters), None)
        routing = load_routing_config()
        self.router = DeploymentRouter(
            configured_deployments,
            self.adapters,
            max_attempts=routing.max_attempts,
            cooldown_seconds=routing.cooldown_seconds,
            failure_threshold=routing.failure_threshold,
            authentication_cooldown=routing.authentication_cooldown,
            quota_cooldown=routing.quota_cooldown,
            rate_limit_cooldown=routing.rate_limit_cooldown,
            provider_failure_cooldown=routing.provider_failure_cooldown,
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        return self.router.generate(request)


_default_service = LLMService()


def get_llm_service() -> LLMService:
    return _default_service


def _provider_error_code(error: ProviderError) -> LLMErrorCode:
    if error.kind == "timeout":
        return LLMErrorCode.TIMEOUT
    if error.kind == "authentication" or error.status_code in {401, 403}:
        return LLMErrorCode.AUTHENTICATION_FAILED
    if error.kind == "quota":
        return LLMErrorCode.QUOTA_EXCEEDED
    if error.status_code == 429:
        return LLMErrorCode.RATE_LIMITED
    if error.status_code in {402, 409}:
        return LLMErrorCode.QUOTA_EXCEEDED
    if error.status_code == 400:
        return LLMErrorCode.INVALID_REQUEST
    if error.kind == "unavailable" or (error.status_code is not None and error.status_code >= 500):
        return LLMErrorCode.PROVIDER_UNAVAILABLE
    return LLMErrorCode.UNKNOWN
