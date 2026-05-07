"""Thin OpenAI-compatible LLM wrapper used by the simulated user and judge.

Reads credentials from environment variables (or backend/.env) so the
simulation framework can be configured independently of the backend's
internal LLM router.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV = PROJECT_ROOT / "backend" / ".env"


def _load_dotenv_into_environ(path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file without overwriting real env vars."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_into_environ(BACKEND_ENV)


_PROVIDER_DEFAULT_BASE_URL = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "ark": os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
}


@dataclass
class LLMConfig:
    """Configuration for one LLM role (e.g. simulated user or judge)."""

    api_key: str
    base_url: str
    model: str
    provider: str = "openrouter"
    extra_headers: Optional[Dict[str, str]] = None
    temperature: Optional[float] = 0.9

    @classmethod
    def from_env(
        cls,
        role: str,
        default_model: Optional[str] = None,
        default_temperature: float = 0.9,
    ) -> "LLMConfig":
        """Build config for either 'sim_user' or 'judge'.

        Honors per-role env vars first (e.g. SIM_USER_API_KEY), then falls
        back to the backend's LLM_API_KEY / LLM_PROVIDER / LLM_DEFAULT_MODEL.
        """
        prefix = role.upper()
        provider = (
            os.environ.get(f"{prefix}_PROVIDER")
            or os.environ.get("LLM_PROVIDER")
            or "openrouter"
        ).lower()

        api_key = (
            os.environ.get(f"{prefix}_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or (os.environ.get("OPENROUTER_API_KEY") if provider == "openrouter" else None)
            or os.environ.get("OPENAI_API_KEY")
        )
        if not api_key:
            raise RuntimeError(
                f"No API key found for role '{role}'. Set {prefix}_API_KEY or LLM_API_KEY."
            )

        base_url = (
            os.environ.get(f"{prefix}_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or _PROVIDER_DEFAULT_BASE_URL.get(provider, "https://openrouter.ai/api/v1")
        )

        model = (
            os.environ.get(f"{prefix}_MODEL")
            or default_model
            or os.environ.get("LLM_DEFAULT_MODEL")
            or "openai/gpt-4o-mini"
        )

        extra_headers: Dict[str, str] = {}
        if provider == "openrouter":
            app_name = os.environ.get("OPENROUTER_APP_NAME") or "NARRA-Gym-Simulation"
            site_url = os.environ.get("OPENROUTER_SITE_URL") or ""
            extra_headers["X-Title"] = app_name
            if site_url:
                extra_headers["HTTP-Referer"] = site_url

        temperature_env = os.environ.get(f"{prefix}_TEMPERATURE")
        try:
            temperature = float(temperature_env) if temperature_env is not None else default_temperature
        except ValueError:
            temperature = default_temperature

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider=provider,
            extra_headers=extra_headers or None,
            temperature=temperature,
        )


class LLMClient:
    """Synchronous OpenAI-compatible chat client with simple retries."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=120.0,
            default_headers=config.extra_headers or None,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        retries: int = 2,
        json_mode: bool = False,
    ) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": model or self.config.model,
                    "messages": messages,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                resolved_temperature = (
                    temperature if temperature is not None else self.config.temperature
                )
                if resolved_temperature is not None and not _model_rejects_temperature(kwargs["model"]):
                    kwargs["temperature"] = resolved_temperature
                # Drop json_mode on the final retry so a model that rejects the
                # response_format param can still produce a parseable answer.
                if json_mode and attempt < retries:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                return content.strip()
            except Exception as exc:  # noqa: BLE001 — broad on purpose for retry
                last_error = exc
                logger.warning(
                    "LLM chat attempt %d/%d failed: %s", attempt + 1, retries + 1, exc
                )
        raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last_error}")

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        retries: int = 2,
    ) -> Dict[str, Any]:
        """Chat and parse the response as JSON, with light tolerance for code fences."""
        raw = self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=retries,
            json_mode=True,
        )
        return _extract_json(raw)


def _model_rejects_temperature(model_name: str) -> bool:
    blocklist = os.environ.get("LLM_TEMPERATURELESS_MODELS", "")
    needles = [item.strip().lower() for item in blocklist.split(",") if item.strip()]
    lowered = model_name.lower()
    return any(needle in lowered for needle in needles)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM output:\n{raw}")
