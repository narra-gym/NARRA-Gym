import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

try:
    from pydantic_settings import BaseSettings
except Exception:  # pragma: no cover - compatibility fallback for pydantic v1 environments
    from pydantic import BaseSettings

# Load environment variables from .env file
load_dotenv()


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_SEED_CANONICAL_MODEL = "doubao/seed-2.0-pro"
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}

DEFAULT_BENCHMARK_MODEL_OPTIONS: tuple[Dict[str, str], ...] = (
    {
        "id": "openai/gpt-5.4",
        "label": "OpenAI GPT-5.4",
        "description": "OpenRouter benchmark route for GPT-5.4.",
    },
    {
        "id": "openai/gpt-5.4-mini",
        "label": "OpenAI GPT-5.4 Mini",
        "description": "OpenRouter benchmark route for GPT-5.4 Mini.",
    },
    {
        "id": "anthropic/claude-opus-4.6",
        "label": "Anthropic Claude Opus 4.6",
        "description": "OpenRouter benchmark route for Claude Opus 4.6.",
    },
    {
        "id": "anthropic/claude-sonnet-4.6",
        "label": "Anthropic Claude Sonnet 4.6",
        "description": "OpenRouter benchmark route for Claude Sonnet 4.6.",
    },
    {
        "id": "google/gemini-3.1-pro-preview",
        "label": "Google Gemini 3.1 Pro Preview",
        "description": "OpenRouter benchmark route for Gemini 3.1 Pro Preview.",
    },
    {
        "id": "deepseek/deepseek-v3.2",
        "label": "DeepSeek V3.2",
        "description": "OpenRouter benchmark route for DeepSeek V3.2.",
    },
    {
        "id": "deepseek/deepseek-v4-pro",
        "label": "DeepSeek V4 Pro",
        "description": "OpenRouter benchmark route for DeepSeek V4 Pro.",
    },
    {
        "id": "z-ai/glm-5.1",
        "label": "Z.AI GLM-5.1",
        "description": "OpenRouter benchmark route for GLM-5.1.",
    },
    {
        "id": "qwen/qwen3.5-397b-a17b",
        "label": "Qwen 3.5 397B A17B",
        "description": "OpenRouter benchmark route for Qwen 3.5 397B A17B.",
    },
    {
        "id": DOUBAO_SEED_CANONICAL_MODEL,
        "label": "Doubao Seed 2.0 Pro (Official)",
        "description": "Official Doubao Seed 2.0 Pro route via Volcengine Ark.",
    },
    {
        "id": "z-ai/glm-5",
        "label": "Z.AI GLM-5",
        "description": "OpenRouter benchmark route for GLM-5.",
    },
)

BENCHMARK_CANONICAL_MODEL_IDS: tuple[str, ...] = tuple(
    option["id"] for option in DEFAULT_BENCHMARK_MODEL_OPTIONS
)

BENCHMARK_MODEL_ROUTE_REGISTRY: Dict[str, Dict[str, str]] = {
    "openai/gpt-5.4": {"provider": "openrouter"},
    "openai/gpt-5.4-mini": {"provider": "openrouter"},
    "anthropic/claude-opus-4.6": {"provider": "openrouter"},
    "anthropic/claude-sonnet-4.6": {"provider": "openrouter"},
    "google/gemini-3.1-pro-preview": {"provider": "openrouter"},
    "deepseek/deepseek-v3.2": {"provider": "openrouter"},
    "deepseek/deepseek-v4-pro": {"provider": "openrouter"},
    "z-ai/glm-5.1": {"provider": "openrouter"},
    "qwen/qwen3.5-397b-a17b": {"provider": "openrouter"},
    DOUBAO_SEED_CANONICAL_MODEL: {
        "provider": "doubao",
        "transport_provider": "ark",
        "endpoint_env": "DOUBAO_SEED_2_0_PRO_ENDPOINT_ID",
    },
    "z-ai/glm-5": {"provider": "openrouter"},
}


def _env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in TRUE_ENV_VALUES


class Settings(BaseSettings):
    """Application settings."""

    BENCHMARK_TASKS: tuple[str, ...] = (
        "default",
        "story",
        "interactive_element",
        "questions",
        "keywords",
        "profile_keywords",
        "reflection",
    )

    # Unified LLM configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # "openai" | "openrouter"
    LLM_API_KEY: Optional[str] = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL")
    LLM_DEFAULT_MODEL: str = os.getenv("LLM_DEFAULT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    LLM_STORY_MODEL: str = os.getenv("LLM_STORY_MODEL") or os.getenv("STORY_MODEL", "gpt-5.4")
    LLM_INTERACTIVE_ELEMENT_MODEL: str = (
        os.getenv("LLM_INTERACTIVE_ELEMENT_MODEL")
        or os.getenv("INTERACTIVE_ELEMENT_MODEL", "gpt-5.4")
    )
    LLM_QUESTIONS_MODEL: Optional[str] = os.getenv("LLM_QUESTIONS_MODEL")
    LLM_KEYWORDS_MODEL: Optional[str] = os.getenv("LLM_KEYWORDS_MODEL")
    LLM_PROFILE_KEYWORDS_MODEL: Optional[str] = os.getenv("LLM_PROFILE_KEYWORDS_MODEL")
    LLM_REFLECTION_MODEL: Optional[str] = os.getenv("LLM_REFLECTION_MODEL")
    LLM_TEMPERATURELESS_MODELS: str = os.getenv("LLM_TEMPERATURELESS_MODELS", "")
    LLM_REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "240"))
    ENABLE_STORY_BLUEPRINT_REVIEW: bool = _env_flag("ENABLE_STORY_BLUEPRINT_REVIEW", False)
    LLM_DISABLE_REASONING_WHEN_POSSIBLE: bool = _env_flag(
        "LLM_DISABLE_REASONING_WHEN_POSSIBLE",
        True,
    )
    LLM_MIN_REASONING_EFFORT: str = os.getenv("LLM_MIN_REASONING_EFFORT", "minimal")
    EXPERIMENT_DB_PATH: str = os.getenv("EXPERIMENT_DB_PATH", "data/emobenchmark.sqlite3")
    EXPERIMENT_CONDITIONS_JSON: Optional[str] = os.getenv("EXPERIMENT_CONDITIONS_JSON")
    BENCHMARK_MODEL_OPTIONS_JSON: Optional[str] = os.getenv("BENCHMARK_MODEL_OPTIONS_JSON")
    BENCHMARK_RANDOM_MODE: bool = _env_flag("BENCHMARK_RANDOM_MODE", False)
    EXPORT_OUTPUT_DIR: str = os.getenv("EXPORT_OUTPUT_DIR", "exports")

    # OpenRouter benchmark routing
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_SITE_URL: Optional[str] = os.getenv("OPENROUTER_SITE_URL")
    OPENROUTER_APP_NAME: Optional[str] = os.getenv("OPENROUTER_APP_NAME", "EmoNest")

    # Volcengine Ark / Doubao benchmark routing
    ARK_API_KEY: Optional[str] = os.getenv("ARK_API_KEY")
    ARK_BASE_URL: str = os.getenv("ARK_BASE_URL", DEFAULT_ARK_BASE_URL)
    DOUBAO_SEED_2_0_PRO_ENDPOINT_ID: Optional[str] = os.getenv("DOUBAO_SEED_2_0_PRO_ENDPOINT_ID")
    DOUBAO_SEED_2_0_PRO_MODEL_NAME: str = os.getenv(
        "DOUBAO_SEED_2_0_PRO_MODEL_NAME",
        "doubao-seed-2-0-pro-260215",
    )

    # Backward-compatible aliases used elsewhere in the codebase
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    STORY_MODEL: str = os.getenv("STORY_MODEL", "gpt-5.4")
    INTERACTIVE_ELEMENT_MODEL: str = os.getenv("INTERACTIVE_ELEMENT_MODEL", "gpt-5.4")
    STORY_GENERATION_TEMPERATURE: float = -1
    QUESTIONS_GENERATION_TEMPERATURE: float = -1

    # Other providers and media configuration
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    IMAGE_API_PROVIDER: str = os.getenv("IMAGE_API_PROVIDER", "openai")  # "openai" | "gemini"
    REMOVEBG_API_KEY: Optional[str] = os.getenv("REMOVEBG_API_KEY")
    REPLICATE_API_TOKEN: Optional[str] = os.getenv("REPLICATE_API_TOKEN")
    BG_REMOVAL_PROVIDER: str = os.getenv("BG_REMOVAL_PROVIDER", "removebg")  # "removebg" | "replicate"
    HTTP_PROXY: Optional[str] = os.getenv("HTTP_PROXY")
    HTTPS_PROXY: Optional[str] = os.getenv("HTTPS_PROXY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_llm_base_url(self) -> str:
        if self.LLM_BASE_URL:
            return self.LLM_BASE_URL
        if self.LLM_PROVIDER.lower() == "openrouter":
            return DEFAULT_OPENROUTER_BASE_URL
        return self.OPENAI_BASE_URL or DEFAULT_OPENAI_BASE_URL

    def get_llm_api_key(self) -> str:
        api_key = self.LLM_API_KEY or self.OPENROUTER_API_KEY or self.OPENAI_API_KEY
        if not api_key:
            raise ValueError(
                "No LLM API key configured. Set LLM_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY."
            )
        return api_key

    def get_llm_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.LLM_PROVIDER.lower() == "openrouter":
            headers.update(self.get_openrouter_headers())
        return headers

    def get_openrouter_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.OPENROUTER_SITE_URL:
            headers["HTTP-Referer"] = self.OPENROUTER_SITE_URL
        if self.OPENROUTER_APP_NAME:
            headers["X-Title"] = self.OPENROUTER_APP_NAME
        return headers

    def get_openrouter_api_key(self) -> Optional[str]:
        if self.OPENROUTER_API_KEY:
            return self.OPENROUTER_API_KEY
        if self.LLM_PROVIDER.lower() == "openrouter":
            return self.LLM_API_KEY or self.OPENAI_API_KEY
        return None

    def get_llm_model(self, task: str = "default") -> str:
        model_map = {
            "default": self.LLM_DEFAULT_MODEL,
            "story": self.LLM_STORY_MODEL,
            "interactive_element": self.LLM_INTERACTIVE_ELEMENT_MODEL,
            "questions": self.LLM_QUESTIONS_MODEL or self.LLM_DEFAULT_MODEL,
            "keywords": self.LLM_KEYWORDS_MODEL or self.LLM_DEFAULT_MODEL,
            "profile_keywords": self.LLM_PROFILE_KEYWORDS_MODEL or self.LLM_DEFAULT_MODEL,
            "reflection": self.LLM_REFLECTION_MODEL or self.LLM_INTERACTIVE_ELEMENT_MODEL or self.LLM_DEFAULT_MODEL,
        }
        return model_map.get(task, self.LLM_DEFAULT_MODEL)

    def is_temperature_supported(self, model: str) -> bool:
        normalized_variants = {
            model.strip()
            for model in {
                model,
                model.split("/", 1)[-1] if "/" in model else model,
            }
            if isinstance(model, str) and model.strip()
        }
        templess_models = {
            name.strip()
            for name in self.LLM_TEMPERATURELESS_MODELS.split(",")
            if name.strip()
        }
        if normalized_variants & templess_models:
            return False
        return not any(
            candidate.startswith(("o1", "o3", "o4", "gpt-5"))
            for candidate in normalized_variants
        )

    def _normalized_model_variants(self, model_name: Optional[str]) -> set[str]:
        if not isinstance(model_name, str):
            return set()
        normalized = model_name.strip().lower()
        if not normalized:
            return set()
        bare = normalized.split("/", 1)[-1]
        return {normalized, bare}

    def _model_matches_any_prefix(self, model_name: Optional[str], prefixes: tuple[str, ...]) -> bool:
        variants = self._normalized_model_variants(model_name)
        return any(
            variant.startswith(prefix)
            for variant in variants
            for prefix in prefixes
        )

    def get_llm_request_options(self, route: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build provider-specific request overrides for low-latency generation.

        We push reasoning effort down to the lowest supported level, or disable
        it entirely when the transport supports that explicitly.
        """
        model_name = route.get("model_name") or route.get("api_model") or ""
        provider = str(route.get("provider") or "").lower()
        transport_provider = str(route.get("transport_provider") or provider).lower()

        extra_body: Dict[str, Any] = {}

        if transport_provider == "ark":
            extra_body["thinking"] = {
                "type": "disabled" if self.LLM_DISABLE_REASONING_WHEN_POSSIBLE else "enabled"
            }
        elif provider == "openrouter":
            reasoning = self._build_openrouter_reasoning_config(model_name)
            if reasoning:
                extra_body["reasoning"] = reasoning
        elif provider == "openai":
            reasoning_effort = self._build_openai_reasoning_effort(model_name)
            if reasoning_effort:
                extra_body["reasoning_effort"] = reasoning_effort

        return {"extra_body": extra_body} if extra_body else {}

    def _build_openrouter_reasoning_config(self, model_name: Optional[str]) -> Dict[str, Any]:
        minimal_effort = self.LLM_MIN_REASONING_EFFORT or "minimal"

        if self._model_matches_any_prefix(model_name, ("openai/gpt-5", "gpt-5")):
            return {"effort": "none"}

        if self._model_matches_any_prefix(
            model_name,
            ("anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4.6"),
        ):
            return {"enabled": False}

        if self._model_matches_any_prefix(model_name, ("google/gemini-3", "gemini-3")):
            return {"effort": minimal_effort, "exclude": True}

        if self._model_matches_any_prefix(
            model_name,
            (
                "deepseek/",
                "deepseek-",
                "z-ai/",
                "glm-",
                "qwen/",
                "qwen3",
            ),
        ):
            return {"enabled": False}

        return {}

    def _build_openai_reasoning_effort(self, model_name: Optional[str]) -> Optional[str]:
        if self._model_matches_any_prefix(model_name, ("gpt-5.1", "gpt-5.1-mini", "gpt-5.1-nano")):
            return "none"
        if self._model_matches_any_prefix(model_name, ("gpt-5",)):
            return self.LLM_MIN_REASONING_EFFORT or "minimal"
        return None

    def get_benchmark_model_options(self) -> List[Dict[str, Any]]:
        default_lookup = {
            option["id"]: dict(option)
            for option in DEFAULT_BENCHMARK_MODEL_OPTIONS
        }
        parsed_options = self._parse_benchmark_model_options_json(default_lookup)
        options = parsed_options or [dict(option) for option in DEFAULT_BENCHMARK_MODEL_OPTIONS]

        enriched_options: List[Dict[str, Any]] = []
        for option in options:
            route = self.get_model_route(option["id"])
            enriched_options.append(
                {
                    **option,
                    "provider": route.get("provider"),
                    "available": route.get("available", True),
                    "availability_reason": route.get("availability_reason"),
                }
            )
        return enriched_options

    def get_model_route(self, model: Optional[str] = None, task: str = "default") -> Dict[str, Any]:
        resolved_model = model or self.get_llm_model(task)
        known_route = BENCHMARK_MODEL_ROUTE_REGISTRY.get(resolved_model)

        if known_route:
            provider = known_route.get("provider", "openrouter")
            if provider == "openrouter":
                api_key = self.get_openrouter_api_key()
                available = bool(api_key)
                availability_reason = None if available else (
                    "OpenRouter model is unavailable: set OPENROUTER_API_KEY."
                )
                return {
                    "model_name": resolved_model,
                    "provider": "openrouter",
                    "transport_provider": "openrouter",
                    "base_url": DEFAULT_OPENROUTER_BASE_URL,
                    "api_key": api_key or "",
                    "api_model": resolved_model,
                    "default_headers": self.get_openrouter_headers(),
                    "available": available,
                    "availability_reason": availability_reason,
                }

            if provider == "doubao":
                api_key = self.ARK_API_KEY
                api_model = (
                    self.DOUBAO_SEED_2_0_PRO_ENDPOINT_ID
                    or self.DOUBAO_SEED_2_0_PRO_MODEL_NAME
                    or ""
                )
                available = bool(api_key and api_model)
                missing_bits: List[str] = []
                if not api_key:
                    missing_bits.append("ARK_API_KEY")
                availability_reason = None if available else (
                    "Doubao model is unavailable: set " + " and ".join(missing_bits) + "."
                )
                return {
                    "model_name": resolved_model,
                    "provider": "doubao",
                    "transport_provider": known_route.get("transport_provider", "ark"),
                    "base_url": self.ARK_BASE_URL or DEFAULT_ARK_BASE_URL,
                    "api_key": api_key or "",
                    "api_model": api_model,
                    "default_headers": {},
                    "available": available,
                    "availability_reason": availability_reason,
                }

        provider = self.LLM_PROVIDER.lower()
        api_key = self.LLM_API_KEY or self.OPENAI_API_KEY or self.OPENROUTER_API_KEY
        available = bool(api_key)
        availability_reason = None if available else (
            "Global LLM route is unavailable: set LLM_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY."
        )
        return {
            "model_name": resolved_model,
            "provider": provider,
            "transport_provider": provider,
            "base_url": self.get_llm_base_url(),
            "api_key": api_key or "",
            "api_model": resolved_model,
            "default_headers": self.get_llm_headers(),
            "available": available,
            "availability_reason": availability_reason,
        }

    def _parse_benchmark_model_options_json(
        self,
        default_lookup: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        raw = self.BENCHMARK_MODEL_OPTIONS_JSON
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []

        options: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in parsed:
            if isinstance(item, str):
                model_id = item.strip()
                base_option = default_lookup.get(model_id, {})
                if not model_id or model_id in seen:
                    continue
                options.append(
                    {
                        "id": model_id,
                        "label": base_option.get("label", model_id),
                        "description": base_option.get(
                            "description",
                            f"Use {model_id} for all benchmark LLM text tasks.",
                        ),
                    }
                )
                seen.add(model_id)
                continue

            if not isinstance(item, dict):
                continue

            model_id = str(item.get("id") or "").strip()
            if not model_id or model_id in seen:
                continue

            base_option = default_lookup.get(model_id, {})
            option = {
                "id": model_id,
                "label": str(item.get("label") or base_option.get("label") or model_id),
                "description": str(
                    item.get("description")
                    or base_option.get("description")
                    or f"Use {model_id} for all benchmark LLM text tasks."
                ),
            }
            options.append(option)
            seen.add(model_id)
        return options


settings = Settings()

# Keep legacy fields aligned with unified configuration for older call sites.
try:
    settings.OPENAI_API_KEY = settings.OPENAI_API_KEY or settings.get_llm_api_key()
except ValueError:
    settings.OPENAI_API_KEY = settings.OPENAI_API_KEY or None
settings.OPENAI_BASE_URL = settings.OPENAI_BASE_URL or DEFAULT_OPENAI_BASE_URL
settings.OPENAI_MODEL = settings.get_llm_model("default")
settings.STORY_MODEL = settings.get_llm_model("story")
settings.INTERACTIVE_ELEMENT_MODEL = settings.get_llm_model("interactive_element")
