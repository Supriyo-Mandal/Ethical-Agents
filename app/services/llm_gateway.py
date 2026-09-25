from __future__ import annotations

import json
import logging
import random
import time
from enum import Enum
from typing import Any
from urllib import error, request

from dotenv import load_dotenv

from app.services.llm_config import load_config


logger = logging.getLogger("llm_gateway")
logger.setLevel(logging.INFO)


class LLMGatewayErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CONFIG_ERROR = "CONFIG_ERROR"
    UNKNOWN = "UNKNOWN"


class LLMGatewayError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider_id: str | None = None,
        model: str | None = None,
        code: LLMGatewayErrorCode = LLMGatewayErrorCode.UNKNOWN,
        retryable: bool = False,
        status_code: int | None = None,
        raw_detail: str | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.raw_detail = raw_detail
        super().__init__(message)


def _classify_error(status_code: int | None, message: str) -> LLMGatewayErrorCode:
    if status_code == 401:
        return LLMGatewayErrorCode.AUTHENTICATION_FAILED
    if status_code == 429:
        return LLMGatewayErrorCode.RATE_LIMITED
    if status_code == 402:
        return LLMGatewayErrorCode.QUOTA_EXCEEDED
    if status_code in {408, 504}:
        return LLMGatewayErrorCode.TIMEOUT
    if status_code in {500, 502, 503}:
        return LLMGatewayErrorCode.PROVIDER_UNAVAILABLE
    if "timeout" in message.lower():
        return LLMGatewayErrorCode.TIMEOUT
    if "invalid" in message.lower() or "bad request" in message.lower():
        return LLMGatewayErrorCode.INVALID_REQUEST
    return LLMGatewayErrorCode.UNKNOWN


def _normalize_response(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_text": content}
    if content is None:
        return {"raw_text": ""}
    return content


def _candidate_models_for_provider(provider: Any) -> list[str]:
    text_generation = provider.models.get("text_generation")
    chosen_models: list[str] = []

    if isinstance(text_generation, list):
        chosen_models = [
            item.model
            for item in text_generation
            if getattr(item, "enabled", True) and getattr(item, "model", None)
        ]
    elif text_generation is not None:
        if getattr(text_generation, "enabled", True) and getattr(text_generation, "model", None):
            chosen_models = [text_generation.model]

    return chosen_models


def _get_provider_candidates(provider_id: str | None = None):
    load_dotenv()
    providers = load_config()
    logger.info("loading config")
    logger.info("providers loaded: %s", [p.id for p in providers])

    if not providers:
        raise LLMGatewayError(
            "No LLM providers found in config",
            code=LLMGatewayErrorCode.CONFIG_ERROR,
        )

    if provider_id:
        providers = [p for p in providers if p.id == provider_id]

    candidates: list[tuple[Any, Any, str]] = []

    for provider in providers:
        if not provider.credentials:
            continue

        enabled_credentials = [
            c
            for c in provider.credentials
            if getattr(c, "enabled", False) and getattr(c, "api_key", "")
        ]
        if not enabled_credentials:
            continue

        models = _candidate_models_for_provider(provider)
        if not models:
            continue

        for credential in enabled_credentials:
            for model in models:
                candidates.append((provider, credential, model))

    if not candidates:
        msg = (
            f"No enabled provider or model configuration found for {provider_id}"
            if provider_id
            else "No enabled provider or model configuration found"
        )
        raise LLMGatewayError(msg, code=LLMGatewayErrorCode.CONFIG_ERROR)

    return candidates


def generate_text(
    messages: list[dict[str, str]],
    *,
    provider_id: str | None = None,
    temperature: float = 0.2,
    max_output_tokens: int = 512,
    retries: int = 3,
    timeout_seconds: int = 30,
) -> Any:
    if not isinstance(messages, list) or not messages:
        raise LLMGatewayError(
            "LLM request requires at least one message",
            code=LLMGatewayErrorCode.INVALID_REQUEST,
        )

    last_error: LLMGatewayError | None = None

    logger.info(
        "llm_generate_start",
        extra={
            "provider_id": provider_id,
            "message_count": len(messages),
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "retries": retries,
            "timeout_seconds": timeout_seconds,
        },
    )

    for attempt in range(retries):
        for provider, credential, model in _get_provider_candidates(provider_id):
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_output_tokens,
            }

            endpoint = f"{provider.base_url.rstrip('/')}/chat/completions"

            logger.info(
                "llm_request_attempt",
                extra={
                    "provider_id": provider.id,
                    "model": model,
                    "attempt": attempt + 1,
                    "endpoint": endpoint,
                },
            )

            req = request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {credential.api_key}",
                },
                method="POST",
            )

            started = time.monotonic()
            logger.info("LLM: sending request to %s", endpoint)

            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    body = response.read().decode("utf-8")
                    data = json.loads(body)

                choices = data.get("choices", [])
                if not choices:
                    raise LLMGatewayError(
                        "LLM provider returned no choices",
                        provider_id=provider.id,
                        model=model,
                        code=LLMGatewayErrorCode.PROVIDER_UNAVAILABLE,
                        retryable=False,
                    )

                first = choices[0]
                message = first.get("message", {})
                content = message.get("content")

                if content is None:
                    logger.info(
                        "llm_response_empty",
                        extra={"provider_id": provider.id, "model": model},
                    )
                    return {"raw_text": ""}

                result = _normalize_response(content)

                logger.info(
                    "llm_response_success",
                    extra={
                        "provider_id": provider.id,
                        "model": model,
                        "result_type": type(result).__name__,
                    },
                )
                logger.info("LLM: provider=%s model=%s succeeded in %.2fs", provider.id, model, time.monotonic() - started)
                return result

            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                status_code = getattr(exc, "code", None)
                mapped_code = _classify_error(status_code, detail)
                err = LLMGatewayError(
                    f"LLM provider error: {status_code} {detail}",
                    provider_id=provider.id,
                    model=model,
                    code=mapped_code,
                    retryable=mapped_code in {
                        LLMGatewayErrorCode.RATE_LIMITED,
                        LLMGatewayErrorCode.TIMEOUT,
                        LLMGatewayErrorCode.PROVIDER_UNAVAILABLE,
                    },
                    status_code=status_code,
                    raw_detail=detail,
                )
                last_error = err
                logger.warning(
                    "llm_http_error",
                    extra={
                        "provider_id": provider.id,
                        "model": model,
                        "status_code": status_code,
                        "code": mapped_code.value,
                        "retryable": err.retryable,
                        "detail": detail[:500],
                    },
                )
                continue

            except TimeoutError as exc:
                err = LLMGatewayError(
                    f"LLM provider timeout: {exc}",
                    provider_id=provider.id,
                    model=model,
                    code=LLMGatewayErrorCode.TIMEOUT,
                    retryable=True,
                )
                last_error = err
                logger.warning(
                    "llm_timeout",
                    extra={"provider_id": provider.id, "model": model},
                )
                continue

            except Exception as exc:
                err = LLMGatewayError(
                    f"Failed to call LLM provider: {exc}",
                    provider_id=provider.id,
                    model=model,
                    code=_classify_error(None, str(exc)),
                    retryable=True,
                )
                last_error = err
                logger.exception(
                    "llm_call_exception",
                    extra={
                        "provider_id": provider.id,
                        "model": model,
                        "code": err.code.value,
                        "retryable": True,
                    },
                )
                continue

        if last_error and last_error.retryable and attempt < retries - 1:
            backoff = (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(
                "llm_retry_wait",
                extra={
                    "attempt": attempt + 1,
                    "backoff_seconds": round(backoff, 2),
                    "provider_id": last_error.provider_id,
                    "model": last_error.model,
                    "code": last_error.code.value,
                },
            )
            time.sleep(backoff)
            continue

        break

    if last_error:
        logger.error(
            "llm_all_attempts_failed",
            extra={
                "provider_id": last_error.provider_id,
                "model": last_error.model,
                "code": last_error.code.value,
                "retryable": last_error.retryable,
                "status_code": last_error.status_code,
            },
        )
        raise last_error

    raise LLMGatewayError(
        "Failed to call LLM provider",
        code=LLMGatewayErrorCode.UNKNOWN,
    )