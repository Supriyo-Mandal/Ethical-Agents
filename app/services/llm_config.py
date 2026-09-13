from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DeploymentConfigurationError(ValueError):
    """Raised when LLM deployment configuration is malformed."""


@dataclass(frozen=True)
class RoutingConfig:
    max_attempts: int = 3
    cooldown_seconds: float = 60.0
    failure_threshold: int = 2
    authentication_cooldown: float = 300.0
    quota_cooldown: float = 300.0
    rate_limit_cooldown: float = 60.0
    provider_failure_cooldown: float = 60.0
    max_retries: int = 1
    base_retry_delay: float = 0.1
    max_retry_delay: float = 2.0
    overall_timeout: float = 30.0


@dataclass(frozen=True)
class DeploymentConfig:
    id: str
    provider: str
    model: str
    api_key_ref: str
    api_key: str = field(default="", repr=False, compare=False)
    enabled: bool = True
    priority: int = 100
    timeout_seconds: float = 30.0
    connect_timeout: float = 30.0
    request_timeout: float = 30.0
    overall_request_timeout: float = 30.0
    settings: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            "DeploymentConfig("
            f"id={self.id!r}, provider={self.provider!r}, model={self.model!r}, "
            f"api_key_ref={self.api_key_ref!r}, enabled={self.enabled!r}, "
            f"priority={self.priority!r}, timeout_seconds={self.timeout_seconds!r})"
        )


def load_deployments(environ: dict[str, str] | None = None) -> tuple[DeploymentConfig, ...]:
    env = environ if environ is not None else os.environ
    raw = env.get("LLM_DEPLOYMENTS_JSON", "").strip()
    if not raw:
        return (_default_deployment(env),)

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeploymentConfigurationError("LLM_DEPLOYMENTS_JSON must be valid JSON") from exc
    if not isinstance(entries, list) or not entries:
        raise DeploymentConfigurationError("LLM_DEPLOYMENTS_JSON must be a non-empty list")

    deployments = tuple(_deployment_from_mapping(entry, index, env) for index, entry in enumerate(entries, 1))
    ids = [deployment.id for deployment in deployments]
    if len(ids) != len(set(ids)):
        raise DeploymentConfigurationError("Deployment ids must be unique")
    return tuple(sorted(deployments, key=lambda item: (item.priority, item.id)))


def load_routing_config(environ: dict[str, str] | None = None) -> RoutingConfig:
    env = environ if environ is not None else os.environ
    try:
        max_attempts = int(env.get("LLM_MAX_ATTEMPTS", "3"))
        cooldown_seconds = float(env.get("LLM_DEPLOYMENT_COOLDOWN_SECONDS", "60"))
        failure_threshold = int(env.get("LLM_FAILURE_THRESHOLD", "2"))
        authentication_cooldown = float(env.get("LLM_AUTHENTICATION_COOLDOWN_SECONDS", "300"))
        quota_cooldown = float(env.get("LLM_QUOTA_COOLDOWN_SECONDS", "300"))
        rate_limit_cooldown = float(env.get("LLM_RATE_LIMIT_COOLDOWN_SECONDS", "60"))
        provider_failure_cooldown = float(env.get("LLM_PROVIDER_FAILURE_COOLDOWN_SECONDS", str(cooldown_seconds)))
        max_retries = int(env.get("LLM_MAX_RETRIES", "1"))
        base_retry_delay = float(env.get("LLM_BASE_RETRY_DELAY_SECONDS", "0.1"))
        max_retry_delay = float(env.get("LLM_MAX_RETRY_DELAY_SECONDS", "2"))
        overall_timeout = float(env.get("LLM_OVERALL_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise DeploymentConfigurationError("LLM routing limits must be numeric") from exc
    values = (cooldown_seconds, authentication_cooldown, quota_cooldown, rate_limit_cooldown, provider_failure_cooldown, base_retry_delay, max_retry_delay, overall_timeout)
    if max_attempts < 1 or failure_threshold < 1 or max_retries < 0 or max_retry_delay < base_retry_delay or overall_timeout <= 0 or any(value < 0 for value in values):
        raise DeploymentConfigurationError("LLM routing limits are out of range")
    return RoutingConfig(
        max_attempts=max_attempts,
        cooldown_seconds=cooldown_seconds,
        failure_threshold=failure_threshold,
        authentication_cooldown=authentication_cooldown,
        quota_cooldown=quota_cooldown,
        rate_limit_cooldown=rate_limit_cooldown,
        provider_failure_cooldown=provider_failure_cooldown,
        max_retries=max_retries,
        base_retry_delay=base_retry_delay,
        max_retry_delay=max_retry_delay,
        overall_timeout=overall_timeout,
    )


def _default_deployment(env: dict[str, str]) -> DeploymentConfig:
    api_key_ref = "OPENAI_API_KEY"
    return DeploymentConfig(
        id="openai-compatible-default",
        provider="openai-compatible",
        model=env.get("LLM_MODEL", "gpt-4o-mini"),
        api_key_ref=api_key_ref,
        api_key=_resolve_api_key(api_key_ref, env),
        enabled=True,
        priority=1,
        timeout_seconds=30.0,
        settings={"base_url": env.get("LLM_BASE_URL", "https://api.openai.com/v1")},
    )


def _deployment_from_mapping(value: Any, index: int, environ: dict[str, str]) -> DeploymentConfig:
    if not isinstance(value, dict):
        raise DeploymentConfigurationError(f"Deployment {index} must be an object")
    required = ("id", "provider", "model", "api_key_ref")
    missing = [key for key in required if not isinstance(value.get(key), str) or not value[key].strip()]
    if missing:
        raise DeploymentConfigurationError(f"Deployment {index} is missing: {', '.join(missing)}")

    enabled = value.get("enabled", True)
    priority = value.get("priority", 100)
    timeout = value.get("timeout_seconds", 30.0)
    request_timeout = value.get("request_timeout", timeout)
    connect_timeout = value.get("connect_timeout", request_timeout)
    overall_timeout = value.get("overall_request_timeout", 30.0)
    settings = value.get("settings", {})
    if not isinstance(enabled, bool):
        raise DeploymentConfigurationError(f"Deployment {index} enabled must be boolean")
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise DeploymentConfigurationError(f"Deployment {index} priority must be an integer")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or item <= 0 for item in (timeout, request_timeout, connect_timeout, overall_timeout)):
        raise DeploymentConfigurationError(f"Deployment {index} timeout values must be positive")
    if not isinstance(settings, dict):
        raise DeploymentConfigurationError(f"Deployment {index} settings must be an object")

    return DeploymentConfig(
        id=value["id"].strip(),
        provider=value["provider"].strip(),
        model=value["model"].strip(),
        api_key_ref=value["api_key_ref"].strip(),
        api_key=_resolve_api_key(value["api_key_ref"].strip(), environ),
        enabled=enabled,
        priority=priority,
        timeout_seconds=float(request_timeout),
        connect_timeout=float(connect_timeout),
        request_timeout=float(request_timeout),
        overall_request_timeout=float(overall_timeout),
        settings=settings,
    )


def _resolve_api_key(reference: str, environ: dict[str, str]) -> str:
    value = environ.get(reference, "")
    if value:
        return value
    config_path = Path(__file__).resolve().parents[2] / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    if reference == "OPENAI_API_KEY" and isinstance(config.get("api_key"), str):
        return config["api_key"].strip()
    return ""
