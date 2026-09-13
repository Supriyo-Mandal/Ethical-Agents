from __future__ import annotations

import unittest
from unittest.mock import patch
import json

from app.services.llm_gateway import (
    OpenAICompatibleAdapter,
    LLMError,
    LLMErrorCode,
    LLMRequest,
    LLMService,
    LLMResponse,
)
from app.services.llm_config import DeploymentConfig, DeploymentConfigurationError, load_deployments
from app.services.llm_client import ProviderError


class FakeAdapter:
    provider_name = "fake"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content={"answer": "ok"}, provider=self.provider_name, model=request.model)


class FailingAdapter:
    provider_name = "fake"

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMError(LLMErrorCode.RATE_LIMITED, "limit reached", self.provider_name, 429)


class LLMGatewayTests(unittest.TestCase):
    @staticmethod
    def fake_deployment() -> DeploymentConfig:
        return DeploymentConfig("fake-1", "fake", "test-model", "FAKE_KEY")

    def test_service_returns_normalized_response(self) -> None:
        response = LLMService(FakeAdapter()).generate(
            LLMRequest(messages=[{"role": "user", "content": "hello"}], model="test-model", deployment=self.fake_deployment())
        )
        self.assertEqual(response.content, {"answer": "ok"})
        self.assertEqual(response.provider, "fake")
        self.assertEqual(response.model, "test-model")

    def test_service_preserves_normalized_provider_error(self) -> None:
        with self.assertRaises(LLMError) as raised:
            LLMService(FailingAdapter()).generate(LLMRequest(messages=[], model="test-model", deployment=self.fake_deployment()))
        self.assertEqual(raised.exception.code, LLMErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(raised.exception.details["attempted_deployments"][0]["category"], "RATE_LIMITED")

    @patch("app.services.llm_gateway.call_openai_compatible", return_value={"candidate_fields": []})
    def test_openai_compatible_adapter_delegates_to_configured_endpoint(self, call_provider) -> None:
        response = OpenAICompatibleAdapter().generate(
            LLMRequest(
                messages=[
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "user"},
                ],
                model="test-model",
                max_output_tokens=16384,
            )
        )
        self.assertEqual(response.content, {"candidate_fields": []})
        call_provider.assert_called_once_with(
            base_url="https://api.openai.com/v1",
            api_key="",
            model="test-model",
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            timeout=30.0,
            temperature=None,
            max_output_tokens=16384,
        )

    def test_streaming_is_rejected_until_provider_supports_it(self) -> None:
        with self.assertRaises(LLMError) as raised:
            OpenAICompatibleAdapter().generate(LLMRequest(messages=[], stream=True))
        self.assertEqual(raised.exception.code, LLMErrorCode.INVALID_REQUEST)

    @patch("app.services.llm_gateway.call_openai_compatible")
    def test_provider_errors_are_normalized(self, call_provider) -> None:
        cases = [
            (ProviderError("http", 401), LLMErrorCode.AUTHENTICATION_FAILED),
            (ProviderError("http", 429), LLMErrorCode.RATE_LIMITED),
            (ProviderError("quota", 402), LLMErrorCode.QUOTA_EXCEEDED),
            (ProviderError("timeout"), LLMErrorCode.TIMEOUT),
            (ProviderError("unavailable", 503), LLMErrorCode.PROVIDER_UNAVAILABLE),
            (ProviderError("http", 400), LLMErrorCode.INVALID_REQUEST),
        ]
        for provider_error, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                call_provider.side_effect = provider_error
                with self.assertRaises(LLMError) as raised:
                    OpenAICompatibleAdapter().generate(LLMRequest(messages=[{"role": "user", "content": "hello"}], model="test-model"))
                self.assertEqual(raised.exception.code, expected_code)

    def test_multiple_deployments_are_sorted_and_support_multiple_keys(self) -> None:
        deployments = load_deployments({
            "LLM_DEPLOYMENTS_JSON": json.dumps([
                {"id": "b", "provider": "openai-compatible", "model": "m", "api_key_ref": "LLM_API_KEY_2", "priority": 2},
                {"id": "a", "provider": "openai-compatible", "model": "m", "api_key_ref": "LLM_API_KEY_1", "priority": 1},
            ])
        })
        self.assertEqual([item.id for item in deployments], ["a", "b"])
        self.assertEqual([item.api_key_ref for item in deployments], ["LLM_API_KEY_1", "LLM_API_KEY_2"])

    def test_disabled_deployment_is_retained_but_not_selected(self) -> None:
        disabled = load_deployments({
            "LLM_DEPLOYMENTS_JSON": json.dumps([
                {"id": "disabled", "provider": "openai-compatible", "model": "m", "api_key_ref": "KEY", "enabled": False},
            ])
        })
        self.assertFalse(disabled[0].enabled)
        with patch("app.services.llm_gateway.load_deployments", return_value=disabled):
            self.assertIsNone(LLMService(FakeAdapter()).default_deployment)

    def test_invalid_deployment_fails_validation(self) -> None:
        with self.assertRaises(DeploymentConfigurationError):
            load_deployments({"LLM_DEPLOYMENTS_JSON": json.dumps([{"id": "bad"}])})

        with self.assertRaises(DeploymentConfigurationError):
            load_deployments({"LLM_DEPLOYMENTS_JSON": json.dumps([
                {"id": "same", "provider": "openai-compatible", "model": "m", "api_key_ref": "KEY_1"},
                {"id": "same", "provider": "openai-compatible", "model": "m", "api_key_ref": "KEY_2"},
            ])})

    def test_deployment_repr_does_not_contain_secret_value(self) -> None:
        deployments = load_deployments({
            "LLM_DEPLOYMENTS_JSON": json.dumps([
                {"id": "safe", "provider": "openai-compatible", "model": "m", "api_key_ref": "LLM_API_KEY_1"},
            ])
        })
        self.assertNotIn("secret-value", repr(deployments[0]))
        self.assertIn("LLM_API_KEY_1", repr(deployments[0]))


if __name__ == "__main__":
    unittest.main()
