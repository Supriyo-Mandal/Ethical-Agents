from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
import yaml
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "llm-gateway.yaml"


@dataclass
class Credential:
    id: str
    api_key: str
    enabled: bool = True


@dataclass
class ModelSpec:
    kind: str
    model: str | None = None
    enabled: bool = True
    auto_discover: bool = False


@dataclass
class Provider:
    id: str
    base_url: str
    credentials: list[Credential] = field(default_factory=list)
    models: dict[str, list[ModelSpec] | ModelSpec] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)

def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            key = value[2:-1].strip()
            return os.getenv(key, "")
        return value
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    return value

def load_providers(path: str | Path = CONFIG_PATH) -> list[Provider]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    providers_raw = raw.get("providers", [])
    providers: list[Provider] = []

    for entry in providers_raw:
        entry = _resolve_env(entry)

        provider_id = entry.get("id")
        base_url = entry.get("base_url", "")
        credentials_raw = entry.get("credentials", [])
        discovery = entry.get("discovery", {})

        credentials = []
        for cred in credentials_raw:
            if not cred.get("enabled", True):
                continue
            credentials.append(
                Credential(
                    id=str(cred.get("id", "")),
                    api_key=str(cred.get("api_key", "")),
                    enabled=bool(cred.get("enabled", True)),
                )
            )

        models: dict[str, list[ModelSpec] | ModelSpec] = {}

        raw_models = entry.get("models", {})
        for kind, spec in raw_models.items():
            if isinstance(spec, dict):
                if spec.get("enabled") is False:
                    continue

                if spec.get("auto_discover") is True:
                    models[kind] = ModelSpec(
                        kind=kind,
                        model=None,
                        enabled=bool(spec.get("enabled", True)),
                        auto_discover=True,
                    )
                else:
                    models[kind] = ModelSpec(
                        kind=kind,
                        model=str(spec.get("model", "")) if spec.get("model") else None,
                        enabled=bool(spec.get("enabled", True)),
                        auto_discover=False,
                    )
            elif isinstance(spec, list):
                models[kind] = [
                    ModelSpec(
                        kind=kind,
                        model=str(item.get("model", "")) if item.get("model") else None,
                        enabled=bool(item.get("enabled", True)),
                        auto_discover=False,
                    )
                    for item in spec
                    if item.get("enabled", True)
                ]

        providers.append(
            Provider(
                id=str(provider_id),
                base_url=str(base_url),
                credentials=credentials,
                models=models,
                discovery=discovery,
            )
        )

    return providers

def validate_provider(provider: Provider) -> None:
    if not provider.id:
        raise ValueError("Provider id is required")

    if not provider.base_url:
        raise ValueError(f"Provider {provider.id} is missing base_url")

    if not provider.credentials:
        raise ValueError(f"Provider {provider.id} has no enabled credentials")

    if not provider.models:
        raise ValueError(f"Provider {provider.id} has no model configuration")

    for kind, model_spec in provider.models.items():
        if isinstance(model_spec, list):
            if not model_spec:
                raise ValueError(f"Provider {provider.id} has no enabled models for {kind}")
            for item in model_spec:
                if item.enabled is False:
                    continue
                if not item.model and not item.auto_discover:
                    raise ValueError(f"Provider {provider.id} model for {kind} is missing")
            continue

        if model_spec.enabled is False:
            continue

        if model_spec.auto_discover:
            continue

        if not model_spec.model:
            raise ValueError(f"Provider {provider.id} model for {kind} is missing")

def load_config() -> list[Provider]:
    load_dotenv()
    providers = load_providers()
    for provider in providers:
        validate_provider(provider)
    return providers