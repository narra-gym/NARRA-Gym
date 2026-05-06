import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from src.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Optional proxy wiring, only enabled when explicitly configured.
proxy = None
if settings.HTTP_PROXY or settings.HTTPS_PROXY:
    proxy = {}
    if settings.HTTP_PROXY:
        proxy["http"] = settings.HTTP_PROXY
    if settings.HTTPS_PROXY:
        proxy["https"] = settings.HTTPS_PROXY
else:
    logger.info("No proxy configured. API calls will be made directly.")


llm_trace_logger: Optional[Callable[[Dict[str, Any]], None]] = None
_client_cache: Dict[Tuple[str, str, Tuple[Tuple[str, str], ...]], OpenAI] = {}
_client_cache_lock = threading.Lock()


def configure_llm_trace_logger(logger_fn: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    global llm_trace_logger
    llm_trace_logger = logger_fn


def _build_client(route: Dict[str, Any]) -> OpenAI:
    client_kwargs: Dict[str, Any] = {
        "api_key": route["api_key"],
        "base_url": route["base_url"],
        "timeout": settings.LLM_REQUEST_TIMEOUT_SECONDS,
    }
    default_headers = route.get("default_headers") or {}
    if default_headers:
        client_kwargs["default_headers"] = default_headers

    if proxy:
        logger.info(
            "LLM client initialized with configured proxy settings for provider=%s",
            route.get("provider"),
        )
    else:
        logger.info(
            "LLM client initialized without proxy for provider=%s",
            route.get("provider"),
        )
    return OpenAI(**client_kwargs)


def _get_client_for_route(route: Dict[str, Any]) -> OpenAI:
    cache_key = (
        route["api_key"],
        route["base_url"],
        tuple(sorted((route.get("default_headers") or {}).items())),
    )
    with _client_cache_lock:
        client = _client_cache.get(cache_key)
        if client is None:
            client = _build_client(route)
            _client_cache[cache_key] = client
        return client


def _build_route_trace_metadata(route: Dict[str, Any]) -> Dict[str, Any]:
    metadata = {
        "api_model": route.get("api_model"),
        "transport_provider": route.get("transport_provider"),
    }
    if route.get("api_model") and route.get("api_model") != route.get("model_name"):
        metadata["transport_model"] = route.get("api_model")
    return metadata


def _merge_request_options(
    base_kwargs: Dict[str, Any],
    extra_options: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not extra_options:
        return base_kwargs

    merged = dict(base_kwargs)
    for key, value in extra_options.items():
        if key == "extra_body" and value:
            merged_extra_body = dict(merged.get("extra_body") or {})
            merged_extra_body.update(value)
            merged["extra_body"] = merged_extra_body
        else:
            merged[key] = value
    return merged


def _extract_completion_content(completion: Any, model: str) -> str:
    """Safely extract text from a chat.completions response.

    Some OpenRouter-proxied models (notably Gemini) can return an empty
    choices list, a message with content=None, or a content_filter finish
    reason. We log what happened and return an empty string so the caller
    can surface a parse error instead of crashing on a NoneType subscript.
    """
    choices = getattr(completion, "choices", None) or []
    if not choices:
        logger.warning("LLM response had no choices for model=%s", model)
        return ""
    first = choices[0]
    finish_reason = getattr(first, "finish_reason", None)
    message = getattr(first, "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if not content:
        logger.warning(
            "LLM response had empty content for model=%s finish_reason=%s",
            model,
            finish_reason,
        )
        return ""
    return content


def _emit_llm_trace(
    *,
    trace_context: Optional[Dict[str, Any]],
    messages: List[Dict[str, str]],
    model_name: str,
    model_provider: str,
    response_text: Optional[str],
    error: Optional[str],
    latency_ms: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not trace_context or not trace_context.get("session_id") or not llm_trace_logger:
        return

    merged_metadata = dict(trace_context.get("metadata") or {})
    merged_metadata.update(metadata or {})
    payload = {
        "session_id": trace_context.get("session_id"),
        "participant_id": trace_context.get("participant_id"),
        "story_id": trace_context.get("story_id"),
        "source": trace_context.get("source", "unknown"),
        "task": trace_context.get("task", "default"),
        "model_provider": model_provider,
        "model_name": model_name,
        "request_messages": messages,
        "response_text": response_text,
        "error": error,
        "latency_ms": latency_ms,
        "metadata": merged_metadata,
    }
    try:
        llm_trace_logger(payload)
    except Exception as exc:
        logger.warning("Failed to persist LLM trace: %s", exc)


def _resolve_model_route(
    *,
    model: Optional[str],
    task: str,
) -> Dict[str, Any]:
    return settings.get_model_route(model=model, task=task)


def get_llm_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    task: str = "default",
    temperature: Optional[float] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Get a completion from the configured OpenAI-compatible API.

    Args:
        messages: A list of messages in chat format.
        model: Optional explicit model override.
        task: Logical task used for default model routing.
        temperature: Optional generation temperature.
        trace_context: Optional benchmark trace metadata.
    """
    route = _resolve_model_route(model=model, task=task)
    resolved_model = route["model_name"]
    started_at = time.perf_counter()
    response_content: Optional[str] = None
    error_text: Optional[str] = None

    if not route.get("available", True):
        error_text = route.get("availability_reason") or f"Model '{resolved_model}' is not configured."
        _emit_llm_trace(
            trace_context=trace_context,
            messages=messages,
            model_name=resolved_model,
            model_provider=route.get("provider", settings.LLM_PROVIDER),
            response_text=None,
            error=error_text,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            metadata=_build_route_trace_metadata(route),
        )
        return {"error": error_text}

    try:
        client = _get_client_for_route(route)
    except Exception as exc:
        error_text = f"Failed to initialize LLM client: {exc}"
        _emit_llm_trace(
            trace_context=trace_context,
            messages=messages,
            model_name=resolved_model,
            model_provider=route.get("provider", settings.LLM_PROVIDER),
            response_text=None,
            error=error_text,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            metadata=_build_route_trace_metadata(route),
        )
        return {"error": error_text}

    try:
        logger.info(
            "Sending request to LLM API with model=%s provider=%s task=%s transport_model=%s",
            resolved_model,
            route.get("provider"),
            task,
            route.get("api_model"),
        )

        kwargs = {"model": route["api_model"], "messages": messages}
        if temperature is not None and settings.is_temperature_supported(resolved_model):
            kwargs["temperature"] = temperature
        elif temperature is not None:
            logger.info("Skipping temperature for model %s", resolved_model)
        kwargs = _merge_request_options(kwargs, settings.get_llm_request_options(route))

        completion = client.chat.completions.create(**kwargs)

        response_content = _extract_completion_content(completion, resolved_model)
        logger.info("Successfully received response from LLM API.")
        return {"content": response_content, "error": None}

    except APITimeoutError as exc:
        logger.error("LLM API request timed out: %s", exc)
        error_text = (
            f"LLM request timed out after {settings.LLM_REQUEST_TIMEOUT_SECONDS:.0f}s. "
            "Please try again."
        )
        return {"error": error_text}
    except RateLimitError as exc:
        logger.error("LLM API rate limit exceeded: %s", exc)
        error_text = "API rate limit exceeded. Please try again later."
        return {"error": error_text}
    except APIError as exc:
        logger.error("LLM API error: %s", exc)
        error_text = "An error occurred with the LLM API."
        return {"error": error_text}
    except Exception as exc:
        logger.error("An unexpected error occurred: %s", exc)
        error_text = f"An unexpected error occurred: {str(exc)}"
        return {"error": error_text}
    finally:
        _emit_llm_trace(
            trace_context=trace_context,
            messages=messages,
            model_name=resolved_model,
            model_provider=route.get("provider", settings.LLM_PROVIDER),
            response_text=response_content,
            error=error_text,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            metadata=_build_route_trace_metadata(route),
        )


def stream_story_completion_sync(
    messages: List[Dict[str, str]],
    model: Optional[str],
    on_chunk: Callable[[str], None],
    task: str = "story",
    trace_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Synchronous streaming LLM call safe to run inside asyncio.to_thread().
    Calls on_chunk(text) for every text delta received and returns the full
    accumulated response string.
    """
    route = _resolve_model_route(model=model, task=task)
    resolved_model = route["model_name"]
    full_response = ""
    started_at = time.perf_counter()
    error_text: Optional[str] = None

    if not route.get("available", True):
        error_text = route.get("availability_reason") or f"Model '{resolved_model}' is not configured."
        logger.error(error_text)
        _emit_llm_trace(
            trace_context=trace_context,
            messages=messages,
            model_name=resolved_model,
            model_provider=route.get("provider", settings.LLM_PROVIDER),
            response_text=None,
            error=error_text,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            metadata={**_build_route_trace_metadata(route), "streaming": True},
        )
        return ""

    try:
        client = _get_client_for_route(route)
        kwargs = _merge_request_options(
            {
                "model": route["api_model"],
                "messages": messages,
                "stream": True,
            },
            settings.get_llm_request_options(route),
        )
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_response += delta.content
                on_chunk(delta.content)
    except Exception as exc:
        logger.error("Streaming LLM error: %s", exc)
        error_text = str(exc)
    finally:
        _emit_llm_trace(
            trace_context=trace_context,
            messages=messages,
            model_name=resolved_model,
            model_provider=route.get("provider", settings.LLM_PROVIDER),
            response_text=full_response or None,
            error=error_text,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            metadata={**_build_route_trace_metadata(route), "streaming": True},
        )
    return full_response


class LLMClient:
    """
    Client class for interacting with LLM APIs.
    Provides methods for various types of LLM operations needed by the
    context manager.
    """

    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = model or settings.get_llm_model("default")
        self.story_model = settings.get_llm_model("story")
        self.proxy = proxy
        self.initialized = True

    def get_completion(
        self,
        prompt: str,
        model=None,
        temperature: Optional[float] = 0.7,
        task: str = "default",
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        return self._call_api(messages, temperature, model, task, trace_context)

    def get_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model=None,
        temperature: Optional[float] = 0.7,
        task: str = "default",
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._call_api(messages, temperature, model, task, trace_context)

    def get_story_completion(
        self,
        messages: List[Dict[str, str]],
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._call_api(
            messages,
            temperature=None,
            model=self.story_model,
            task="story",
            trace_context=trace_context,
        )

    def summarize_text(
        self,
        text: str,
        max_length=200,
        temperature: Optional[float] = 0.5,
        model: Optional[str] = None,
        task: str = "default",
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prompt = f"""
        Summarize the following text in {max_length} words or less:
        
        {text}
        
        Make the summary concise but comprehensive, focusing on the most important information.
        """
        messages = [{"role": "user", "content": prompt}]
        return self._call_api(
            messages,
            temperature,
            model=model,
            task=task,
            trace_context=trace_context,
        )

    def _resolve_route(self, model: Optional[str], task: str) -> Dict[str, Any]:
        resolved_model = model or (self.story_model if task == "story" else self.default_model)
        route = settings.get_model_route(model=resolved_model, task=task)
        if self.api_key or self.base_url:
            route = dict(route)
            route["api_key"] = self.api_key or route["api_key"]
            route["base_url"] = self.base_url or route["base_url"]
            route["available"] = bool(route.get("api_key"))
            if not route["available"]:
                route["availability_reason"] = (
                    route.get("availability_reason")
                    or "Custom LLM route is unavailable: provide an API key."
                )
        return route

    def _call_api(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        model=None,
        task: str = "default",
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.initialized:
            return {"error": "LLM client is not initialized.", "content": ""}

        route = self._resolve_route(model=model, task=task)
        resolved_model = route["model_name"]
        started_at = time.perf_counter()
        response_content: Optional[str] = None
        error_text: Optional[str] = None

        if not route.get("available", True):
            error_text = route.get("availability_reason") or f"Model '{resolved_model}' is not configured."
            _emit_llm_trace(
                trace_context=trace_context,
                messages=messages,
                model_name=resolved_model,
                model_provider=route.get("provider", settings.LLM_PROVIDER),
                response_text=None,
                error=error_text,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                metadata=_build_route_trace_metadata(route),
            )
            return {"error": error_text, "content": ""}

        try:
            client = _get_client_for_route(route)
            logger.info(
                "Sending request to LLM API with model=%s provider=%s transport_model=%s",
                resolved_model,
                route.get("provider"),
                route.get("api_model"),
            )

            kwargs = {
                "model": route["api_model"],
                "messages": messages,
            }
            if temperature is not None and settings.is_temperature_supported(resolved_model):
                kwargs["temperature"] = temperature
            elif temperature is None and settings.is_temperature_supported(resolved_model):
                kwargs["temperature"] = 0.7
            kwargs = _merge_request_options(kwargs, settings.get_llm_request_options(route))

            completion = client.chat.completions.create(**kwargs)

            response_content = _extract_completion_content(completion, resolved_model)
            logger.info("Successfully received response from LLM API.")
            return {"content": response_content, "error": None}

        except APITimeoutError as exc:
            logger.error("LLM API request timed out: %s", exc)
            error_text = (
                f"LLM request timed out after {settings.LLM_REQUEST_TIMEOUT_SECONDS:.0f}s. "
                "Please try again."
            )
            return {"error": error_text, "content": ""}
        except RateLimitError as exc:
            logger.error("LLM API rate limit exceeded: %s", exc)
            error_text = "API rate limit exceeded. Please try again later."
            return {"error": error_text, "content": ""}
        except APIError as exc:
            logger.error("LLM API error: %s", exc)
            error_text = "An error occurred with the LLM API."
            return {"error": error_text, "content": ""}
        except Exception as exc:
            logger.error("An unexpected error occurred: %s", exc)
            error_text = f"An unexpected error occurred: {str(exc)}"
            return {"error": error_text, "content": ""}
        finally:
            _emit_llm_trace(
                trace_context=trace_context,
                messages=messages,
                model_name=resolved_model,
                model_provider=route.get("provider", settings.LLM_PROVIDER),
                response_text=response_content,
                error=error_text,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                metadata=_build_route_trace_metadata(route),
            )
