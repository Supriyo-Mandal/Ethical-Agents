from __future__ import annotations

import threading
import unittest

from app.services.llm_config import DeploymentConfig
from app.services.llm_gateway import LLMError, LLMErrorCode, LLMRequest, LLMResponse
from app.services.llm_router import DeploymentRouter


class ScriptedAdapter:
    def __init__(self, provider_name: str, outcomes: list[object], supports: bool = True) -> None:
        self.provider_name = provider_name
        self.outcomes = list(outcomes)
        self.calls = 0
        self._supports = supports

    def supports(self, request: LLMRequest) -> bool:
        return self._supports

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, LLMError):
            raise outcome
        return LLMResponse(content=outcome, provider=self.provider_name, model=request.deployment.model)


def deployment(identifier: str, priority: int, provider: str = "fake", enabled: bool = True) -> DeploymentConfig:
    return DeploymentConfig(identifier, provider, "model", "KEY", enabled=enabled, priority=priority)


def error(code: LLMErrorCode) -> LLMError:
    return LLMError(code, "provider failure")


class DeploymentRouterTests(unittest.TestCase):
    def request(self) -> LLMRequest:
        return LLMRequest(messages=[{"role": "user", "content": "hello"}])

    def test_success_uses_first_deployment(self) -> None:
        first = ScriptedAdapter("fake", ["a"])
        second = ScriptedAdapter("fake", ["b"])
        router = DeploymentRouter((deployment("a", 1), deployment("b", 2)), {"fake": first}, max_attempts=2)
        response = router.generate(self.request())
        self.assertEqual(response.content, "a")
        self.assertEqual(first.calls, 1)
        self.assertEqual(response.metadata["fallback_used"], False)

    def test_retryable_errors_fall_back(self) -> None:
        for code in (LLMErrorCode.RATE_LIMITED, LLMErrorCode.QUOTA_EXCEEDED, LLMErrorCode.AUTHENTICATION_FAILED, LLMErrorCode.TIMEOUT):
            with self.subTest(code=code):
                first = ScriptedAdapter("first", [error(code)])
                second = ScriptedAdapter("second", ["ok"])
                router = DeploymentRouter((deployment("a", 1, "first"), deployment("b", 2, "second")), {"first": first, "second": second}, max_attempts=2, cooldown_seconds=60)
                response = router.generate(self.request())
                self.assertEqual(response.content, "ok")
                self.assertEqual(response.metadata["previous_failure_category"], code.value)

    def test_non_retryable_error_does_not_call_next(self) -> None:
        first = ScriptedAdapter("first", [error(LLMErrorCode.INVALID_REQUEST)])
        second = ScriptedAdapter("second", ["should-not-run"])
        router = DeploymentRouter((deployment("a", 1, "first"), deployment("b", 2, "second")), {"first": first, "second": second})
        with self.assertRaises(LLMError) as raised:
            router.generate(self.request())
        self.assertEqual(raised.exception.code, LLMErrorCode.INVALID_REQUEST)
        self.assertEqual(second.calls, 0)

    def test_all_failures_preserve_attempts(self) -> None:
        adapters = {
            "a": ScriptedAdapter("a", [error(LLMErrorCode.TIMEOUT)]),
            "b": ScriptedAdapter("b", [error(LLMErrorCode.PROVIDER_UNAVAILABLE)]),
            "c": ScriptedAdapter("c", [error(LLMErrorCode.QUOTA_EXCEEDED)]),
        }
        router = DeploymentRouter(tuple(deployment(key, index, key) for index, key in enumerate(adapters, 1)), adapters, max_attempts=3)
        with self.assertRaises(LLMError) as raised:
            router.generate(self.request())
        self.assertEqual(raised.exception.code, LLMErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(len(raised.exception.details["attempted_deployments"]), 3)

    def test_max_attempts_stops_before_fourth(self) -> None:
        adapters = {key: ScriptedAdapter(key, [error(LLMErrorCode.TIMEOUT)]) for key in ("a", "b", "c", "d")}
        deployments = tuple(deployment(key, index, key) for index, key in enumerate(adapters, 1))
        router = DeploymentRouter(deployments, adapters, max_attempts=3)
        with self.assertRaises(LLMError):
            router.generate(self.request())
        self.assertEqual(adapters["d"].calls, 0)

    def test_disabled_unhealthy_and_incompatible_are_skipped(self) -> None:
        disabled = ScriptedAdapter("disabled", ["bad"])
        unhealthy = ScriptedAdapter("unhealthy", ["bad"])
        incompatible = ScriptedAdapter("incompatible", ["bad"], supports=False)
        healthy = ScriptedAdapter("healthy", ["ok"])
        clock = [100.0]
        deployments = (
            deployment("disabled", 1, "disabled", enabled=False),
            deployment("unhealthy", 2, "unhealthy"),
            deployment("incompatible", 3, "incompatible"),
            deployment("healthy", 4, "healthy"),
        )
        router = DeploymentRouter(deployments, {"disabled": disabled, "unhealthy": unhealthy, "incompatible": incompatible, "healthy": healthy}, failure_threshold=1, cooldown_seconds=60, clock=lambda: clock[0])
        router._mark_failure(deployments[1], "PROVIDER_UNAVAILABLE")
        response = router.generate(self.request())
        self.assertEqual(response.content, "ok")
        self.assertEqual(disabled.calls, 0)
        self.assertEqual(unhealthy.calls, 0)
        self.assertEqual(incompatible.calls, 0)

    def test_concurrent_health_updates_are_safe(self) -> None:
        router = DeploymentRouter((), {}, clock=lambda: 100.0)
        target = deployment("a", 1)
        threads = [threading.Thread(target=router._mark_failure, args=(target, "PROVIDER_UNAVAILABLE")) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(router.health_snapshot()["a"]["failure_count"], 20)

    def test_retry_after_extends_cooldown(self) -> None:
        now = [100.0]
        adapter = ScriptedAdapter("fake", [error(LLMErrorCode.RATE_LIMITED), "ok"])
        target = deployment("a", 1)
        router = DeploymentRouter((target,), {"fake": adapter}, cooldown_seconds=5, rate_limit_cooldown=5, clock=lambda: now[0])
        with self.assertRaises(LLMError):
            router.generate(self.request())
        snapshot = router.health_snapshot()["a"]
        self.assertEqual(snapshot["cooldown_until"], 105.0)
        router._mark_failure(target, "RATE_LIMITED", retry_after=60)
        self.assertEqual(router.health_snapshot()["a"]["cooldown_until"], 160.0)

    def test_half_open_success_recovers(self) -> None:
        now = [100.0]
        target = deployment("a", 1)
        adapter = ScriptedAdapter("fake", [error(LLMErrorCode.AUTHENTICATION_FAILED), "ok"])
        router = DeploymentRouter((target,), {"fake": adapter}, authentication_cooldown=10, clock=lambda: now[0])
        with self.assertRaises(LLMError):
            router.generate(self.request())
        now[0] = 111.0
        response = router.generate(self.request())
        self.assertEqual(response.content, "ok")
        self.assertEqual(router.health_snapshot(), {})

    def test_half_open_failure_returns_to_unhealthy(self) -> None:
        now = [100.0]
        target = deployment("a", 1)
        adapter = ScriptedAdapter("fake", [error(LLMErrorCode.AUTHENTICATION_FAILED), error(LLMErrorCode.TIMEOUT)])
        router = DeploymentRouter((target,), {"fake": adapter}, authentication_cooldown=10, clock=lambda: now[0])
        with self.assertRaises(LLMError):
            router.generate(self.request())
        now[0] = 111.0
        with self.assertRaises(LLMError):
            router.generate(self.request())
        self.assertEqual(router.health_snapshot()["a"]["state"], "UNHEALTHY")

    def test_transient_failures_require_threshold_before_cooldown(self) -> None:
        now = [100.0]
        target = deployment("a", 1)
        adapter = ScriptedAdapter("fake", [error(LLMErrorCode.TIMEOUT), "ok"])
        router = DeploymentRouter((target,), {"fake": adapter}, failure_threshold=2, clock=lambda: now[0])
        with self.assertRaises(LLMError):
            router.generate(self.request())
        self.assertEqual(router.health_snapshot()["a"]["state"], "HEALTHY")
        self.assertEqual(router.generate(self.request()).content, "ok")

    def test_failed_deployment_is_not_retried_in_same_request(self) -> None:
        first = ScriptedAdapter("first", [error(LLMErrorCode.AUTHENTICATION_FAILED)])
        second = ScriptedAdapter("second", ["ok"])
        router = DeploymentRouter((deployment("a", 1, "first"), deployment("b", 2, "second")), {"first": first, "second": second}, max_attempts=3)
        response = router.generate(self.request())
        self.assertEqual(response.content, "ok")
        self.assertEqual(first.calls, 1)


if __name__ == "__main__":
    unittest.main()
