from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from app.services.llm_config import DeploymentConfig


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class _FailureState:
    state: HealthState = HealthState.HEALTHY
    failure_count: int = 0
    cooldown_until: float = 0.0
    failure_category: str | None = None
    last_failure_timestamp: float | None = None
    half_open_probe: bool = False
    deployment_fingerprint: tuple[str, str, str] = ("", "", "")


class DeploymentRouter:
    """Select deployments in priority order and fail over boundedly."""

    RETRYABLE_CODES = {
        "RATE_LIMITED",
        "QUOTA_EXCEEDED",
        "PROVIDER_UNAVAILABLE",
        "TIMEOUT",
        "AUTHENTICATION_FAILED",
    }

    def __init__(
        self,
        deployments: tuple[DeploymentConfig, ...],
        adapters: dict[str, Any],
        max_attempts: int = 3,
        cooldown_seconds: float = 60.0,
        failure_threshold: int = 2,
        authentication_cooldown: float = 300.0,
        quota_cooldown: float = 300.0,
        rate_limit_cooldown: float = 60.0,
        provider_failure_cooldown: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts < 1 or failure_threshold < 1:
            raise ValueError("routing limits must be positive")
        self.deployments = tuple(sorted(deployments, key=lambda item: (item.priority, item.id)))
        self.adapters = adapters
        self.max_attempts = max_attempts
        self.failure_threshold = failure_threshold
        self.cooldowns = {
            "AUTHENTICATION_FAILED": authentication_cooldown,
            "QUOTA_EXCEEDED": quota_cooldown,
            "RATE_LIMITED": rate_limit_cooldown,
            "PROVIDER_UNAVAILABLE": provider_failure_cooldown if provider_failure_cooldown is not None else cooldown_seconds,
            "TIMEOUT": provider_failure_cooldown if provider_failure_cooldown is not None else cooldown_seconds,
        }
        if any(value < 0 for value in self.cooldowns.values()):
            raise ValueError("cooldowns cannot be negative")
        self._clock = clock
        self._states: dict[str, _FailureState] = {}
        self._lock = threading.RLock()

    def generate(self, request: Any) -> Any:
        from app.services.llm_gateway import LLMError, LLMErrorCode, LLMRequest, LLMResponse

        request_id = request.request_id or str(uuid.uuid4())
        attempted: list[dict[str, Any]] = []
        attempt_count = 0
        started = self._clock()

        candidates = (request.deployment,) if request.deployment is not None else self.deployments
        for deployment in candidates:
            if attempt_count >= self.max_attempts:
                break
            adapter = self.adapters.get(deployment.provider)
            if not self._eligible(deployment, adapter, request):
                continue

            attempt_count += 1
            try:
                routed_request = request if request.deployment is deployment else LLMRequest(
                    messages=request.messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_output_tokens=request.max_output_tokens,
                    response_format=request.response_format,
                    stream=request.stream,
                    tools=request.tools,
                    deployment=deployment,
                    logical_model=request.logical_model,
                    request_id=request_id,
                )
                response = adapter.generate(routed_request)
            except LLMError as exc:
                category = exc.code.value
                attempted.append({"deployment_id": deployment.id, "provider": deployment.provider, "category": exc.code.value})
                if exc.code.value not in self.RETRYABLE_CODES:
                    raise
                self._mark_failure(deployment, category, exc.details.get("retry_after_seconds"))
                continue

            self._mark_success(deployment.id)
            response.metadata.update({
                "request_id": request_id,
                "logical_model": request.logical_model or request.model,
                "selected_deployment": deployment.id,
                "provider": deployment.provider,
                "number_of_attempts": attempt_count,
                "fallback_used": attempt_count > 1,
                "previous_failure_category": attempted[-1]["category"] if attempted else None,
                "total_latency_seconds": round(self._clock() - started, 6),
            })
            return response

        details = {
            "request_id": request_id,
            "attempted_deployments": attempted,
            "number_of_attempts": attempt_count,
            "max_attempts": self.max_attempts,
        }
        raise LLMError(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            "All eligible LLM deployments failed or were unavailable",
            details=details,
        )

    def _eligible(self, deployment: DeploymentConfig, adapter: Any, request: Any) -> bool:
        if not deployment.enabled or adapter is None:
            return False
        expected_model = request.logical_model or request.model
        configured_model = deployment.settings.get("logical_model", deployment.model)
        if expected_model and expected_model != configured_model:
            return False
        supports = getattr(adapter, "supports", None)
        if supports is not None and not supports(request):
            return False
        now = self._clock()
        fingerprint = (deployment.provider, deployment.model, deployment.api_key_ref)
        with self._lock:
            state = self._states.get(deployment.id)
            if state is None or state.deployment_fingerprint != fingerprint:
                self._states[deployment.id] = _FailureState(deployment_fingerprint=fingerprint)
                return True
            if state.state == HealthState.HEALTHY:
                return True
            if state.state == HealthState.UNHEALTHY and now >= state.cooldown_until and not state.half_open_probe:
                state.state = HealthState.HALF_OPEN
                state.half_open_probe = True
                return True
            return False

    def _mark_failure(self, deployment: DeploymentConfig, category: str, retry_after: float | None = None) -> None:
        now = self._clock()
        with self._lock:
            fingerprint = (deployment.provider, deployment.model, deployment.api_key_ref)
            state = self._states.setdefault(deployment.id, _FailureState(deployment_fingerprint=fingerprint))
            state.deployment_fingerprint = fingerprint
            state.failure_count += 1
            state.failure_category = category
            state.last_failure_timestamp = now
            state.half_open_probe = False
            immediate = category in {"AUTHENTICATION_FAILED", "QUOTA_EXCEEDED", "RATE_LIMITED"}
            if immediate or state.failure_count >= self.failure_threshold or state.state == HealthState.HALF_OPEN:
                state.state = HealthState.UNHEALTHY
                configured = self.cooldowns.get(category, self.cooldowns["PROVIDER_UNAVAILABLE"])
                state.cooldown_until = now + max(configured, retry_after or 0.0)

    def _mark_success(self, deployment_id: str) -> None:
        with self._lock:
            self._states.pop(deployment_id, None)

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                deployment_id: {
                    "state": state.state.value,
                    "failure_category": state.failure_category,
                    "failure_count": state.failure_count,
                    "cooldown_until": state.cooldown_until,
                    "last_failure_timestamp": state.last_failure_timestamp,
                }
                for deployment_id, state in self._states.items()
            }
