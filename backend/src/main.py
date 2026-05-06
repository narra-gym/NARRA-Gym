import asyncio
import csv
import secrets

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Request, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, Optional, List, Any, Union
import uuid
from datetime import datetime
import json
import logging
import os
import re
import sys
import pathlib
import io
import time
from urllib.parse import urlsplit

# Add the parent directory to sys.path to enable relative imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now import from local modules
from config import BENCHMARK_CANONICAL_MODEL_IDS, settings
from llm_client import get_llm_completion, LLMClient, configure_llm_trace_logger
import prompt_templates
from context_manager import ContextManager
from utils import extract_json_from_response, get_protagonist, is_story_stagnating, fix_story_character_ids, normalize_character_id, standardize_story_response
from story_advancement import advance_story, enhance_act_structure
from meta_planner import generate_story_reflection, generate_interactive_element, remove_background
from experiment_store import ExperimentStore
from benchmark_speed import (
    build_pacing_description,
    build_pacing_level,
    build_runtime_story_flags,
    can_offer_end_story_choice,
    count_exchanges_from_dialogue_count,
    count_story_exchanges,
    get_progression_count_for_dialogue_count,
    get_story_speed_profile,
    has_scene_transition_occurred,
    is_benchmark_story,
    latency_bucket_ms,
    resolve_story_mode,
)
from benchmark_judge import (
    build_benchmark_judge_messages,
    build_judge_input_summary,
    compute_slop_stats,
    normalize_benchmark_judge_payload,
    parse_benchmark_judge_result,
)
from models import (
    EmotionalNeedInput, 
    QuickTestStoryInput,
    QuestionsResponse, 
    StoryAnswersInput, 
    StoryResponse, 
    MessageInput, 
    ChoiceInput, 
    ContextActionRequest,
    StoryStep1Input,
    StoryStep1Response,
    StoryStep2Input,
    StoryStep2Response,
    StoryStep3Input,
    StoryStep3Response,
    StoryStep4Input,
    StoryStep4Response,
    StoryStep5Input,
    StoryStep5Response,
    FeedbackInput,
    BenchmarkModelOptionResponse,
    BenchmarkJudgeRequest,
    BenchmarkJudgeResponse,
    ExperimentSessionStartInput,
    ExperimentSessionStartResponse,
    ExperimentConditionResponse,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://35.188.121.245:3000",
    "http://10.128.0.2:3000",
    "http://47.82.208.37",
    "http://47.82.208.37:3000",
]


def _get_cors_allowed_origins() -> List[str]:
    raw_value = os.getenv("CORS_ALLOWED_ORIGINS", "")
    configured_origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return configured_origins or DEFAULT_CORS_ALLOWED_ORIGINS


def _get_frontend_access_enabled() -> bool:
    raw_value = os.getenv("FRONTEND_ACCESS_GATE_ENABLED", "true").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _get_frontend_access_allowed_origins() -> List[str]:
    raw_value = os.getenv("FRONTEND_ACCESS_ALLOWED_ORIGINS", "")
    configured_origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return configured_origins or _get_cors_allowed_origins()


FRONTEND_ACCESS_GATE_ENABLED = _get_frontend_access_enabled()
FRONTEND_ACCESS_ALLOWED_ORIGINS = _get_frontend_access_allowed_origins()
FRONTEND_ACCESS_COOKIE_NAME = os.getenv("FRONTEND_ACCESS_COOKIE_NAME", "storygame_frontend_session")
FRONTEND_ACCESS_HEADER_NAME = os.getenv("FRONTEND_ACCESS_HEADER_NAME", "X-Storygame-Access")
FRONTEND_ACCESS_SESSION_TTL_SECONDS = int(os.getenv("FRONTEND_ACCESS_SESSION_TTL_SECONDS", "21600"))
FRONTEND_ACCESS_COOKIE_SECURE = os.getenv("FRONTEND_ACCESS_COOKIE_SECURE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
FRONTEND_ACCESS_PUBLIC_PATHS = frozenset({"/", "/access/session"})
FRONTEND_ACCESS_EXEMPT_PREFIXES = ("/images",)
frontend_access_sessions: Dict[str, Dict[str, Any]] = {}


def _purge_expired_frontend_access_sessions() -> None:
    now = time.time()
    expired_ids = [
        session_id
        for session_id, session in frontend_access_sessions.items()
        if float(session.get("expires_at", 0)) <= now
    ]
    for session_id in expired_ids:
        frontend_access_sessions.pop(session_id, None)


def _extract_origin(header_value: Optional[str]) -> Optional[str]:
    if not header_value:
        return None
    parts = urlsplit(header_value)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _resolve_request_origin(request: Request) -> Optional[str]:
    origin = _extract_origin(request.headers.get("origin"))
    if origin in FRONTEND_ACCESS_ALLOWED_ORIGINS:
        return origin
    referer_origin = _extract_origin(request.headers.get("referer"))
    if referer_origin in FRONTEND_ACCESS_ALLOWED_ORIGINS:
        return referer_origin
    return None


def _extract_request_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if first_hop:
            return first_hop
    client = request.client.host if request.client else ""
    return client or ""


def _get_request_fingerprint(request: Request) -> Dict[str, str]:
    return {
        "ip": _extract_request_client_ip(request),
        "user_agent": request.headers.get("user-agent", ""),
    }


def _is_frontend_access_public_path(path: str) -> bool:
    normalized = path or "/"
    if normalized in FRONTEND_ACCESS_PUBLIC_PATHS:
        return True
    return any(normalized.startswith(prefix) for prefix in FRONTEND_ACCESS_EXEMPT_PREFIXES)


def _frontend_access_error(detail: str) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": detail})

app = FastAPI(
    title="EmoNest API",
    description="API for the emotional healing interactive story application."
)

# CORS middleware to allow frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_frontend_access_gate(request: Request, call_next):
    if not FRONTEND_ACCESS_GATE_ENABLED or request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path or "/"
    if _is_frontend_access_public_path(path):
        if path == "/access/session" and _resolve_request_origin(request) is None:
            return _frontend_access_error(
                "Frontend session bootstrap requires a same-origin request from the StoryGame site."
            )
        return await call_next(request)

    _purge_expired_frontend_access_sessions()

    request_origin = _resolve_request_origin(request)
    if request_origin is None:
        return _frontend_access_error(
            "API access is restricted to same-origin requests from the StoryGame frontend."
        )

    session_id = request.cookies.get(FRONTEND_ACCESS_COOKIE_NAME)
    header_token = request.headers.get(FRONTEND_ACCESS_HEADER_NAME)
    if not session_id or not header_token:
        return _frontend_access_error("Frontend access session is missing or incomplete.")

    session = frontend_access_sessions.get(session_id)
    if not session:
        return _frontend_access_error("Frontend access session is missing or expired.")

    if session.get("csrf_token") != header_token:
        return _frontend_access_error("Frontend access token is invalid.")

    if session.get("origin") != request_origin:
        return _frontend_access_error("Frontend access origin does not match the active session.")

    fingerprint = _get_request_fingerprint(request)
    if session.get("ip") != fingerprint["ip"] or session.get("user_agent") != fingerprint["user_agent"]:
        return _frontend_access_error("Frontend access session fingerprint does not match this client.")

    request.state.frontend_access_session = session
    return await call_next(request)


# --- In-Memory Storage ---
# Replace with a proper database in production
stories_db: Dict[str, Dict] = {}
feedback_db: List[Dict] = []
experiment_store = ExperimentStore(settings.EXPERIMENT_DB_PATH)
configure_llm_trace_logger(experiment_store.log_llm_call)

# Create images directory for static file serving
os.makedirs("images", exist_ok=True)
os.makedirs("images/characters", exist_ok=True)

# Mount static file directory
app.mount("/images", StaticFiles(directory="images"), name="images")


def _normalize_blind_invite_code_text(raw_value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(raw_value or "").upper())


BLIND_BENCHMARK_MAPPING_VERSION = "invite-v2"
BLIND_BENCHMARK_TOTAL_SLOTS = 4
BLIND_BENCHMARK_TEST_CODE = 0
BLIND_BENCHMARK_TEST_MAPPING_VERSION = "quick-test-v1"
BLIND_BENCHMARK_TEST_TOTAL_SLOTS = BLIND_BENCHMARK_TOTAL_SLOTS
BLIND_BENCHMARK_TEST_SEQUENCE: tuple[str, ...] = BENCHMARK_CANONICAL_MODEL_IDS[:BLIND_BENCHMARK_TEST_TOTAL_SLOTS]
BLIND_BENCHMARK_CODE_MAP: Dict[int, tuple[int, int, int, int]] = {
    1: (1, 2, 3, 4),
    2: (2, 3, 4, 5),
    3: (3, 4, 5, 6),
    4: (4, 5, 6, 7),
    5: (5, 6, 7, 8),
    6: (6, 7, 8, 1),
    7: (7, 8, 1, 2),
    8: (8, 1, 2, 3),
    9: (1, 2, 3, 4),
    10: (2, 3, 4, 5),
    11: (3, 4, 5, 6),
    12: (4, 5, 6, 7),
    13: (5, 6, 7, 8),
    14: (6, 7, 8, 1),
    15: (7, 8, 1, 2),
    16: (8, 1, 2, 3),
    17: (1, 3, 5, 7),
    18: (2, 4, 6, 8),
    19: (1, 4, 5, 8),
    20: (2, 3, 6, 7),
}
BLIND_BENCHMARK_INVITE_CODE_MAP: Dict[int, str] = {
    1: "JUMF-TVDL",
    2: "3C2B-LUWZ",
    3: "LY7H-H8W8",
    4: "EJ22-XVL9",
    5: "X37W-4V2T",
    6: "EJFT-4VWA",
    7: "NCN7-CV5X",
    8: "GHWA-RP7E",
    9: "U7UP-PH79",
    10: "R5FM-JJYF",
    11: "BWET-X9UQ",
    12: "DBDY-A2A9",
    13: "RNPF-QJAA",
    14: "48FD-86AY",
    15: "PJCR-KPJZ",
    16: "G3SQ-HM4Y",
    17: "33SE-2TQ6",
    18: "VJ2Y-8NFF",
    19: "5E9U-FEGN",
    20: "7F9Y-N8F2",
}
if set(BLIND_BENCHMARK_INVITE_CODE_MAP) != set(BLIND_BENCHMARK_CODE_MAP):
    raise RuntimeError("Blind benchmark invite codes must cover the same 20 benchmark lanes.")

BLIND_BENCHMARK_INVITE_CODE_LOOKUP: Dict[str, int] = {
    _normalize_blind_invite_code_text(invite_code): blind_code
    for blind_code, invite_code in BLIND_BENCHMARK_INVITE_CODE_MAP.items()
}
if len(BLIND_BENCHMARK_INVITE_CODE_LOOKUP) != len(BLIND_BENCHMARK_INVITE_CODE_MAP):
    raise RuntimeError("Blind benchmark invite codes must be unique after normalization.")


def is_blind_benchmark_mode_enabled() -> bool:
    return str(os.getenv("BENCHMARK_RANDOM_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}


def is_blind_quick_test_code(blind_code: int) -> bool:
    return blind_code == BLIND_BENCHMARK_TEST_CODE


def get_blind_invite_code(blind_code: Optional[int]) -> Optional[str]:
    if blind_code is None:
        return None
    try:
        normalized_blind_code = int(blind_code)
    except (TypeError, ValueError):
        return None
    if is_blind_quick_test_code(normalized_blind_code):
        return None
    return BLIND_BENCHMARK_INVITE_CODE_MAP.get(normalized_blind_code)


def get_blind_access_label(blind_code: Optional[int]) -> str:
    if blind_code is None:
        return "unknown"
    try:
        normalized_blind_code = int(blind_code)
    except (TypeError, ValueError):
        return str(blind_code)
    if is_blind_quick_test_code(normalized_blind_code):
        return str(BLIND_BENCHMARK_TEST_CODE)
    return get_blind_invite_code(normalized_blind_code) or str(normalized_blind_code)


def normalize_blind_code(raw_value: Any) -> int:
    text = "" if raw_value is None else str(raw_value).strip()
    if not text:
        raise ValueError("Blind benchmark mode requires an invite code. Enter 0 for quick test.")
    if text == str(BLIND_BENCHMARK_TEST_CODE):
        return BLIND_BENCHMARK_TEST_CODE
    if text.isdigit():
        blind_code = int(text)
        if blind_code in BLIND_BENCHMARK_CODE_MAP:
            return blind_code
    blind_code = BLIND_BENCHMARK_INVITE_CODE_LOOKUP.get(_normalize_blind_invite_code_text(text))
    if blind_code is not None:
        return blind_code
    raise ValueError("Blind benchmark invite code is invalid. Enter one of the issued invite codes, or 0 for quick test.")


def build_blind_participant_id(blind_code: int) -> str:
    return f"blind-{blind_code:02d}"


def get_blind_benchmark_sequence_for_code(blind_code: int) -> List[str]:
    if is_blind_quick_test_code(blind_code):
        return list(BLIND_BENCHMARK_TEST_SEQUENCE)
    return [
        BENCHMARK_CANONICAL_MODEL_IDS[index - 1]
        for index in BLIND_BENCHMARK_CODE_MAP[blind_code]
    ]


def validate_blind_benchmark_configuration() -> List[str]:
    options = settings.get_benchmark_model_options()
    available_ids = [option.get("id") for option in options if option.get("available", True)]
    canonical_ids = list(BENCHMARK_CANONICAL_MODEL_IDS)
    if len(available_ids) != len(canonical_ids):
        raise ValueError(
            f"Blind benchmark mode requires exactly {len(canonical_ids)} available benchmark models; "
            f"found {len(available_ids)}."
        )
    if set(available_ids) != set(canonical_ids):
        raise ValueError("Blind benchmark mode requires the canonical 8 benchmark models to be available.")
    return canonical_ids


def get_session_context(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    return experiment_store.get_session(session_id)


def make_json_safe(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def ensure_mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_participant_evaluation(feedback_logs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not feedback_logs:
        return None

    latest_feedback = feedback_logs[-1]
    benchmark_feedbacks = [
        log for log in feedback_logs
        if log.get("feedback_type") == "benchmark_session_end"
    ]
    benchmark_feedback = benchmark_feedbacks[-1] if benchmark_feedbacks else None
    primary_feedback = benchmark_feedback or latest_feedback
    if not primary_feedback:
        return None

    return {
        "feedback_count": len(feedback_logs),
        "latest_feedback": make_json_safe(latest_feedback),
        "benchmark_feedback": make_json_safe(benchmark_feedback),
        "rating": primary_feedback.get("rating"),
        "scores": make_json_safe(primary_feedback.get("scores") or {}),
        "comment": primary_feedback.get("comment"),
        "feelings": make_json_safe(primary_feedback.get("feelings") or []),
        "feedback_type": primary_feedback.get("feedback_type"),
        "form_version": primary_feedback.get("form_version"),
        "created_at": primary_feedback.get("created_at"),
    }


def build_benchmark_result_export_payload(
    *,
    session: Optional[Dict[str, Any]],
    story: Optional[Dict[str, Any]],
    dialogue_source: str,
    dialogue: List[Dict[str, Any]],
    turn_logs: List[Dict[str, Any]],
    story_events: List[Dict[str, Any]],
    llm_call_logs: List[Dict[str, Any]],
    feedback_logs: List[Dict[str, Any]],
    story_snapshot: Optional[Dict[str, Any]],
    final_view_story: Optional[Dict[str, Any]],
    template_mode: bool = False,
) -> Dict[str, Any]:
    return {
        "schema_version": "benchmark_result_v1",
        "export_type": "benchmark_result",
        "exported_at": datetime.utcnow().isoformat(),
        "session": make_json_safe(session),
        "story": make_json_safe(story),
        "dialogue_source": dialogue_source,
        "dialogue": make_json_safe(dialogue),
        "turn_logs": make_json_safe(turn_logs),
        "story_events": make_json_safe(story_events),
        "llm_call_logs": make_json_safe(llm_call_logs),
        "feedback_logs": make_json_safe(feedback_logs),
        "participant_evaluation": make_json_safe(build_participant_evaluation(feedback_logs)),
        "story_snapshot": make_json_safe(story_snapshot),
        "final_view_story": make_json_safe(final_view_story),
        "template_mode": template_mode,
    }


def sanitize_story_snapshot_for_client(snapshot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return make_json_safe(snapshot)
    sanitized = make_json_safe(snapshot)
    if isinstance(sanitized, dict):
        sanitized.pop("llm_config", None)
        sanitized["selected_model"] = None
    return sanitized


def sanitize_story_event_payload_for_client(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = make_json_safe(payload) or {}
    for key in ("final_story_snapshot", "story_snapshot"):
        if isinstance(sanitized.get(key), dict):
            sanitized[key] = sanitize_story_snapshot_for_client(sanitized.get(key))
    return sanitized


def sanitize_turn_log_for_client(turn_log: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = make_json_safe(turn_log) or {}
    sanitized["llm_config"] = {}
    sanitized["model_provider"] = None
    return sanitized


def sanitize_llm_call_log_for_client(llm_call_log: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = make_json_safe(llm_call_log) or {}
    sanitized["model_name"] = None
    sanitized["model_provider"] = None
    return sanitized


def build_blind_progress_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    if not session.get("blind_mode"):
        return {
            "blind_mode": False,
            "blind_code": None,
            "blind_invite_code": None,
            "blind_session_index": None,
            "blind_total_sessions": None,
            "blind_completed_count": 0,
            "blind_remaining_count": 0,
            "blind_finished": False,
            "quick_test_mode": False,
            "quick_test_completed_runs": 0,
        }

    progress_rows = experiment_store.get_blind_session_progress(session["participant_id"], mode=session.get("mode") or "benchmark")
    completed_count = sum(1 for item in progress_rows if item.get("status") == "completed")
    quick_test_mode = bool(session.get("quick_test_mode"))
    blind_code = int(session.get("blind_code")) if session.get("blind_code") is not None else None
    blind_invite_code = None if quick_test_mode else get_blind_invite_code(blind_code)
    blind_total_sessions = int(
        session.get("blind_total_slots")
        or (BLIND_BENCHMARK_TEST_TOTAL_SLOTS if quick_test_mode else BLIND_BENCHMARK_TOTAL_SLOTS)
    )
    blind_slot_index = session.get("blind_slot_index")
    blind_session_index = int(blind_slot_index) + 1 if blind_slot_index is not None else None
    blind_finished = completed_count >= blind_total_sessions
    blind_remaining_count = max(blind_total_sessions - completed_count, 0)

    return {
        "blind_mode": True,
        "blind_code": blind_code,
        "blind_invite_code": blind_invite_code,
        "blind_session_index": blind_session_index,
        "blind_total_sessions": blind_total_sessions,
        "blind_completed_count": completed_count,
        "blind_remaining_count": blind_remaining_count,
        "blind_finished": blind_finished,
        "quick_test_mode": quick_test_mode,
        "quick_test_completed_runs": completed_count if quick_test_mode else 0,
    }


def sanitize_session_for_client(session: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = make_json_safe(session) or {}
    progress_payload = build_blind_progress_payload(session)
    sanitized.update(progress_payload)
    if sanitized.get("blind_mode"):
        sanitized["selected_model"] = None
        sanitized["llm_config_override"] = {}
        metadata = sanitized.get("metadata") if isinstance(sanitized.get("metadata"), dict) else {}
        metadata.pop("selected_model", None)
        sanitized["metadata"] = metadata
    return sanitized


def sanitize_export_bundle_for_client(export_bundle: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = make_json_safe(export_bundle) or {}
    if session.get("blind_mode"):
        sanitized["session"] = sanitize_session_for_client(session)
        sanitized["story"] = sanitize_story_snapshot_for_client(sanitized.get("story"))
        sanitized["story_snapshot"] = sanitize_story_snapshot_for_client(sanitized.get("story_snapshot"))
        sanitized["final_view_story"] = sanitize_story_snapshot_for_client(sanitized.get("final_view_story"))
        sanitized["turn_logs"] = [
            sanitize_turn_log_for_client(item)
            for item in ensure_list(sanitized.get("turn_logs"))
        ]
        sanitized["llm_call_logs"] = [
            sanitize_llm_call_log_for_client(item)
            for item in ensure_list(sanitized.get("llm_call_logs"))
        ]
        sanitized["story_events"] = [
            {
                **make_json_safe(item),
                "payload": sanitize_story_event_payload_for_client(ensure_mapping(item.get("payload"))),
            }
            for item in ensure_list(sanitized.get("story_events"))
        ]
    return sanitized


def build_uniform_llm_config(selected_model: Optional[str]) -> Dict[str, str]:
    if not selected_model:
        return {}
    return {
        task: selected_model
        for task in settings.BENCHMARK_TASKS
    }


def resolve_benchmark_selected_model(selected_model: Optional[str]) -> str:
    options = settings.get_benchmark_model_options()
    if not options:
        raise ValueError("No benchmark models configured")
    available_options = [option for option in options if option.get("available", True)]
    if not selected_model:
        if not available_options:
            raise ValueError("No benchmark models are currently available. Configure OpenRouter or Doubao credentials first.")
        return available_options[0]["id"]

    option_map = {option["id"]: option for option in options}
    option = option_map.get(selected_model)
    if option is None:
        raise ValueError(f"Model '{selected_model}' is not available for benchmark mode")
    if option.get("available", True) is False:
        raise ValueError(
            option.get("availability_reason")
            or f"Model '{selected_model}' is not currently configured for benchmark mode"
        )
    return selected_model


def build_quick_test_story_payload(
    *,
    story_id: str,
    session: Dict[str, Any],
    participant_id: Optional[str],
) -> Dict[str, Any]:
    now = datetime.now().isoformat()
    setting = {
        "primary_location": "The Lantern Room, a compact observatory prepared for benchmark smoke tests.",
        "time_period": "A still midnight between one test run and the next.",
        "atmosphere": "Calm, intentional, and already leaning toward resolution.",
        "unique_elements": [
            "A brass console that resets itself after every completed benchmark run.",
            "A hanging lantern that shifts color whenever a new hidden model slot begins.",
            "A paper logbook where each finished run is marked with a single stroke of ink.",
        ],
    }
    characters = [
        {
            "id": "protagonist",
            "name": "You",
            "role": "protagonist",
            "description": "A benchmark runner moving through a compact test world.",
            "personality": "Observant, efficient, and focused on validation.",
            "backstory": "You entered this room to verify the blind benchmark flow without sitting through the full story setup.",
            "relationship": "Self",
        },
        {
            "id": "keeper",
            "name": "The Lantern Keeper",
            "role": "npc",
            "description": "A calm guide who only appears when a run is ready to begin or end.",
            "personality": "Measured, reassuring, and practical.",
            "backstory": "The Keeper oversees transitions between quick test runs and points you toward the cleanest ending path.",
            "relationship": "Guide",
        },
    ]
    return {
        "id": story_id,
        "user_id": participant_id,
        "participant_id": participant_id,
        "session_id": session.get("session_id"),
        "condition_id": session.get("condition", {}).get("id"),
        "condition_name": session.get("condition", {}).get("name"),
        "selected_model": session.get("selected_model"),
        "llm_config": session.get("llm_config_override", {}) or session.get("condition", {}).get("llm_config", {}),
        "story_mode": session.get("mode") or "benchmark",
        "benchmark_speed_profile": True,
        "speed_profile": build_runtime_story_flags(session=session).get("speed_profile"),
        "title": "Lantern Room Test Run",
        "theme": "A controlled ending for benchmark verification.",
        "high_concept_premise": "You step into a resettable chamber designed to verify blind benchmark progression one hidden model slot at a time.",
        "cinematic_theme": "Closure can be deliberate, minimal, and repeatable when the goal is validation.",
        "emotional_undercurrent": "Steady confidence.",
        "emotional_goal": "Confirm that the benchmark session can enter, conclude, and advance cleanly.",
        "protagonist_objective": "Finish this run cleanly and move on to the next hidden model slot.",
        "setting": setting,
        "characters": characters,
        "acts": [
            {
                "id": "act-1",
                "act_number": 1,
                "title": "The Ready Signal",
                "purpose": "Provide a controlled final-decision scene for quick benchmark testing.",
                "climactic_moment": "You confirm the flow, close the room, and let the next hidden run begin.",
                "emotional_transformation": "a calm sense of completion rather than narrative uncertainty",
            }
        ],
        "current_act": 0,
        "current_scene": {
            "id": "scene-quick-test",
            "title": "The Lantern Room",
            "description": "A quiet chamber hums to life as the lantern shifts to the color of the next hidden slot.",
            "location": "The Lantern Room",
            "setting": "The Lantern Room",
            "mood": "ready",
            "emotional_tone": "composed",
            "inciting_incident": "The Keeper confirms that this run is already at its final decision point.",
            "scene_transition_caption": "LATER - THE LANTERN ROOM OPENS FOR A FINAL CHECK",
            "messages": [
                {
                    "id": f"msg-{uuid.uuid4()}",
                    "character_id": "system",
                    "content": "The lantern room is configured for a fast blind benchmark check. This run starts at the final decision point.",
                    "timestamp": now,
                    "type": "system",
                },
                {
                    "id": f"msg-{uuid.uuid4()}",
                    "character_id": "keeper",
                    "content": "Everything is ready. You can end this story immediately, or take one small action before closing the room.",
                    "timestamp": now,
                    "type": "text",
                },
            ],
            "choices": [
                {
                    "id": "choice-end-now",
                    "text": "End the story now",
                    "dramatic_impact": "Concludes this test run immediately.",
                    "visual_representation": "Close the lantern room and record the result.",
                },
                {
                    "id": "choice-check-logbook",
                    "text": "Check the logbook before ending",
                    "dramatic_impact": "Takes one extra interaction before the close.",
                    "visual_representation": "Read the marks from earlier test runs.",
                },
                {
                    "id": "choice-step-forward",
                    "text": "Take one more step into the light",
                    "dramatic_impact": "Keeps the test world moving for one more beat.",
                    "visual_representation": "Approach the lantern and decide after a final pause.",
                },
            ],
            "hidden_elements": {
                "easter_egg": "The lantern briefly echoes the hidden model slot, but only in the export trail.",
                "foreshadowing": "Another run is already waiting behind the next reset.",
            },
            "scene_elements": {
                "atmosphere": "Focused and low-friction.",
                "visual_details": ["brass console", "suspended lantern", "ink-marked logbook"],
                "symbolic_motifs": ["circles", "resets", "quiet endings"],
            },
            "scene_dynamics": {
                "transition_required": True,
                "new_location": "The Lantern Room",
                "time_progression": "The room is already in its last beat.",
                "narrative_advancement": "This quick test run is poised to end immediately.",
                "scene_transition_caption": "LATER - THE LANTERN ROOM OPENS FOR A FINAL CHECK",
            },
            "story_state": {
                "current_objective": "End the run cleanly and verify the next session can begin.",
                "current_tension": "Whether to conclude immediately or inspect one last detail first.",
                "immediate_stakes": "A clean ending confirms the blind benchmark flow is ready for the next slot.",
                "location_status": "Stable and ready for teardown.",
                "relationship_shift": "The Keeper is no longer guiding discovery, only closure.",
                "latest_reveal": "This world exists purely to validate the session pipeline.",
                "emotional_beat": "Resolved anticipation.",
            },
        },
        "story_memory": {
            "what_just_happened": "The test chamber prepared a final-decision scene.",
            "current_goal": "Conclude this run and move to the next hidden slot.",
            "open_tensions": ["Whether you end immediately or take one more small action first."],
            "active_clues": ["The logbook tracks completed runs.", "The lantern color changes for each hidden slot."],
            "last_major_turning_point": "The Keeper opened the lantern room in endgame mode.",
        },
        "story_progress": {
            "current_act_index": 1,
            "act_count": 1,
            "current_act_title": "The Ready Signal",
            "current_act_purpose": "Finish the quick test cleanly.",
            "scene_location": "The Lantern Room",
        },
        "scene_info_panel": {
            "recap": "You entered a default benchmark test world that begins at the final decision point.",
            "scene_location": "The Lantern Room",
            "objective": "Conclude this run cleanly.",
            "current_tension": "End now or take one final step before closing.",
            "immediate_stakes": "A clean ending advances the hidden test sequence.",
            "location_status": "Reset-ready.",
            "clue_summary": ["The lantern color marks a hidden slot.", "The logbook tracks run completion."],
            "tension_summary": ["You can end immediately.", "You can also validate one extra interaction first."],
        },
        "cast_statuses": [
            {
                "character_id": "protagonist",
                "name": "You",
                "role": "protagonist",
                "relationship": "Self",
                "current_status": "Ready to conclude the run.",
                "last_seen": "Standing beneath the lantern.",
            },
            {
                "character_id": "keeper",
                "name": "The Lantern Keeper",
                "role": "guide",
                "relationship": "Guide",
                "current_status": "Waiting for your final confirmation.",
                "last_seen": "Beside the brass console.",
            },
        ],
        "interactive_element_history": [],
        "dialogue_summaries": ["The Keeper opened a controlled final-decision scene for benchmarking."],
        "dialogue_count": 1,
        "exchange_count": 0,
        "conclusion_countdown": 1,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "emotional_need": "Quick blind benchmark smoke test",
        "experiment_mode": True,
        "keywords": ["benchmark", "lantern room", "final check"],
        "profile_keywords": {},
    }


def get_llm_config_for_session(session_id: Optional[str]) -> Dict[str, str]:
    session = get_session_context(session_id)
    if session and session.get("llm_config_override"):
        return session["llm_config_override"]
    if session and session.get("condition"):
        return session["condition"].get("llm_config", {})
    return {}


def get_story_llm_config(story: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not story:
        return {}
    return story.get("llm_config") or {}


def get_story_session(story: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not story:
        return None
    session_id = story.get("session_id")
    if not session_id:
        return None
    return get_session_context(session_id)


def resolve_model_for_task(
    task: str,
    story: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> str:
    story_config = get_story_llm_config(story)
    if story_config.get(task):
        return story_config[task]
    session_config = get_llm_config_for_session(session_id)
    if session_config.get(task):
        return session_config[task]
    return settings.get_llm_model(task)


def resolve_provider_for_task(
    task: str,
    story: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> str:
    resolved_model = resolve_model_for_task(task, story=story, session_id=session_id)
    route = settings.get_model_route(model=resolved_model, task=task)
    return str(route.get("provider") or settings.LLM_PROVIDER)


def build_story_experiment_metadata(
    session_id: Optional[str],
    participant_id: Optional[str],
) -> Dict[str, Any]:
    session = get_session_context(session_id)
    condition = session.get("condition") if session else None
    llm_config = get_llm_config_for_session(session_id)
    story_mode = resolve_story_mode(session=session)
    runtime_flags = build_runtime_story_flags(session=session)
    return {
        "experiment_mode": bool(session),
        "session_id": session_id,
        "participant_id": participant_id or (session.get("participant_id") if session else None),
        "condition_id": condition.get("id") if condition else None,
        "condition_name": condition.get("name") if condition else None,
        "mode": session.get("mode") if session else story_mode,
        "selected_model": session.get("selected_model") if session else None,
        "llm_config": llm_config,
        "story_mode": runtime_flags["story_mode"],
        "benchmark_speed_profile": runtime_flags["benchmark_speed_profile"],
        "speed_profile": runtime_flags["speed_profile"],
    }


def build_llm_trace_context(
    source: str,
    task: str,
    *,
    story: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    participant_id: Optional[str] = None,
    story_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    resolved_story_id = story_id or (story.get("id") if story else None)
    resolved_session_id = session_id or (story.get("session_id") if story else None)
    if not resolved_session_id:
        return None
    resolved_participant = participant_id or (story.get("participant_id") if story else None)
    if not resolved_participant:
        session = get_session_context(resolved_session_id)
        resolved_participant = session.get("participant_id") if session else None
    return {
        "session_id": resolved_session_id,
        "participant_id": resolved_participant,
        "story_id": resolved_story_id,
        "source": source,
        "task": task,
        "metadata": metadata or {},
    }


async def run_llm_completion(**kwargs) -> Dict[str, Any]:
    """Run blocking LLM work off the event loop so progress polling stays responsive."""
    return await asyncio.to_thread(get_llm_completion, **kwargs)


def _save_story_snapshot_locally_sync(story_id: str, story_data: Dict[str, Any]) -> None:
    save_dir = pathlib.Path("saved_stories")
    save_dir.mkdir(exist_ok=True)
    file_path = save_dir / f"{story_id}.json"
    with file_path.open("w", encoding="utf-8") as file_handle:
        json.dump(story_data, file_handle, ensure_ascii=False, indent=2)
    logger.info(f"Saved completed story {story_id} to {file_path}")


async def _save_story_snapshot_locally(story_id: str, story_data: Dict[str, Any]) -> None:
    try:
        await asyncio.to_thread(_save_story_snapshot_locally_sync, story_id, story_data)
    except Exception as exc:
        logger.error(f"Failed to save story {story_id} locally: {exc}")


async def _generate_scene_background_image(story_id: str, scene_prompt: str) -> None:
    if not scene_prompt.strip():
        return

    try:
        from pathlib import Path
        from src.meta_planner import generate_image

        image_dir = Path(f"images/scenes/{story_id}")
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / "scene0.png"

        gen_result = await generate_image(
            prompt=scene_prompt,
            output_path=str(image_path),
            api_provider=settings.IMAGE_API_PROVIDER,
            model="gemini-2.5-flash-image-preview" if settings.IMAGE_API_PROVIDER == "gemini" else "gpt-image-1",
            size="1792x1024",
            quality="medium",
        )

        if not gen_result.get("success"):
            logger.warning(
                "Failed to generate background image for story %s: %s",
                story_id,
                gen_result.get("error"),
            )
            return

        relative_path = f"images/scenes/{story_id}/scene0.png"
        story_data = stories_db.get(story_id)
        if not story_data:
            return

        current_scene = story_data.get("current_scene") or {}
        current_scene["backgroundImage"] = relative_path
        story_data["current_scene"] = current_scene
        stories_db[story_id] = story_data
        await _save_story_snapshot_locally(story_id, story_data)
        experiment_store.log_story_event(
            event_type="story_scene_background_generated",
            story_id=story_id,
            session_id=story_data.get("session_id"),
            participant_id=story_data.get("participant_id"),
            payload=make_json_safe({"background_image": relative_path}),
        )
        logger.info(f"Background image generated for story {story_id}")
    except Exception as exc:
        logger.error(f"Error generating background image for story {story_id}: {exc}")


def extract_story_snapshot_from_events(
    story_events: List[Dict[str, Any]],
    preferred_event_types: Optional[List[str]] = None,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    preferred = preferred_event_types or [
        "story_ended",
        "story_turn_completed",
        "story_choice_completed",
        "story_created_full",
        "story_completed_generation",
    ]
    for preferred_type in preferred:
        for event in reversed(story_events):
            if event.get("event_type") != preferred_type:
                continue
            payload = event.get("payload") or {}
            for key in ("final_story_snapshot", "story_snapshot"):
                snapshot = payload.get(key)
                if isinstance(snapshot, dict) and snapshot.get("current_scene"):
                    return snapshot, event.get("event_type")
    for event in reversed(story_events):
        payload = event.get("payload") or {}
        for key in ("final_story_snapshot", "story_snapshot"):
            snapshot = payload.get(key)
            if isinstance(snapshot, dict) and snapshot.get("current_scene"):
                return snapshot, event.get("event_type")
    return None, None


def build_dialogue_records_from_snapshot(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    characters = snapshot.get("characters", []) or []
    character_map = {
        char.get("id"): char.get("name") or char.get("id")
        for char in characters
        if char.get("id")
    }
    protagonist_id = next(
        (char.get("id") for char in characters if char.get("role") == "protagonist" and char.get("id")),
        None,
    )

    records: List[Dict[str, Any]] = []
    for index, message in enumerate(snapshot.get("current_scene", {}).get("messages", []) or []):
        character_id = message.get("character_id") or "system"
        if character_id == "system":
            role = "system"
            speaker = "System"
        elif character_id == protagonist_id:
            role = "user"
            speaker = character_map.get(character_id, "Protagonist")
        else:
            role = "assistant"
            speaker = character_map.get(character_id, character_id)

        records.append(
            {
                "id": message.get("id") or f"snapshot-msg-{index}",
                "speaker": speaker,
                "role": role,
                "character_id": character_id,
                "content": message.get("content", ""),
                "timestamp": message.get("timestamp"),
                "message_type": message.get("type", "text"),
                "source": "story_snapshot",
            }
        )
    return records


def merge_adjacent_dialogue_records(dialogue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for raw_record in dialogue:
        record = ensure_mapping(raw_record)
        content = str(record.get("content") or "").strip()
        if not content:
            continue

        normalized = dict(record)
        normalized["content"] = content

        if merged:
            previous = merged[-1]
            same_group = (
                previous.get("speaker") == normalized.get("speaker")
                and previous.get("role") == normalized.get("role")
                and previous.get("character_id") == normalized.get("character_id")
                and previous.get("turn_index") == normalized.get("turn_index")
                and previous.get("message_type") == normalized.get("message_type")
            )
            if same_group:
                previous["content"] = f"{previous.get('content', '').rstrip()}\n\n{content}"
                continue

        merged.append(normalized)

    return merged


BENCHMARK_STATE_KEYS = (
    "scene_shift",
    "act_advance",
    "ending_ready",
    "objective",
    "tension",
    "immediate_stakes",
    "latest_reveal",
    "relationship_shift",
    "emotional_beat",
    "location_status",
    "next_location",
)
BENCHMARK_STATE_PATTERN = re.compile(
    rf"^\s*(?:{'|'.join(BENCHMARK_STATE_KEYS)})\s*:",
    re.IGNORECASE | re.MULTILINE,
)


def strip_benchmark_state_leak(content: str) -> str:
    if not content:
        return ""
    match = BENCHMARK_STATE_PATTERN.search(content)
    if not match:
        return content.strip()
    return content[:match.start()].strip()


def strip_trailing_choice_block(content: str) -> str:
    if not content:
        return ""
    lines = content.rstrip().splitlines()
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    start = end
    while start > 0 and lines[start - 1].strip().startswith("- "):
        start -= 1
    if start < end:
        return "\n".join(lines[:start]).rstrip()
    return content.rstrip()


def normalize_dialogue_record_content(content: str, speaker_aliases: Optional[List[str]] = None) -> str:
    normalized = strip_trailing_choice_block(strip_benchmark_state_leak(content or ""))
    aliases = [alias.strip() for alias in (speaker_aliases or []) if alias and alias.strip()]
    for alias in aliases:
        prefix = f"{alias}:"
        if normalized.lower().startswith(prefix.lower()):
            normalized = normalized[len(prefix):].strip()
            break
    return normalized.strip()


def build_dialogue_records_from_turn_logs(
    turn_logs: List[Dict[str, Any]],
    character_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    resolved_character_map = character_map or {}
    for turn in turn_logs:
        turn_id = turn.get("id") or f"turn-{turn.get('turn_index', len(records))}"
        created_at = turn.get("created_at")
        action_type = (turn.get("action_type") or "message").lower()

        if turn.get("user_input"):
            records.append(
                {
                    "id": f"{turn_id}-user",
                    "speaker": "User",
                    "role": "user",
                    "character_id": None,
                    "content": turn.get("user_input"),
                    "timestamp": created_at,
                    "message_type": action_type,
                    "turn_index": turn.get("turn_index"),
                    "source": "turn_log",
                }
            )

        response_messages = ensure_list(ensure_mapping(turn.get("metadata")).get("response_messages"))
        if response_messages:
            for idx, raw_message in enumerate(response_messages):
                message = ensure_mapping(raw_message)
                character_id = message.get("character_id") or message.get("characterId") or "system"
                message_type = message.get("type") or "text"
                speaker_aliases = [str(character_id)]
                if character_id == "system":
                    role = "system"
                    speaker = "System"
                else:
                    role = "assistant"
                    speaker = resolved_character_map.get(str(character_id), str(character_id))
                    speaker_aliases.insert(0, speaker)
                content = normalize_dialogue_record_content(str(message.get("content") or ""), speaker_aliases=speaker_aliases)
                if not content:
                    continue
                records.append(
                    {
                        "id": message.get("id") or f"{turn_id}-response-{idx}",
                        "speaker": speaker,
                        "role": role,
                        "character_id": character_id,
                        "content": content,
                        "timestamp": message.get("timestamp") or created_at,
                        "message_type": message_type,
                        "turn_index": turn.get("turn_index"),
                        "source": "turn_log_message",
                    }
                )
            continue

        response_text = (turn.get("response_text") or "").strip()
        if response_text:
            speaker = turn.get("response_character_id") or "Story"
            display_speaker = "System" if speaker == "system" else resolved_character_map.get(str(speaker), str(speaker))
            role = "system" if speaker == "system" else "assistant"
            normalized_response_text = normalize_dialogue_record_content(
                response_text,
                speaker_aliases=[display_speaker, str(speaker)],
            )
            if not normalized_response_text:
                continue
            records.append(
                {
                    "id": f"{turn_id}-response",
                    "speaker": display_speaker,
                    "role": role,
                    "character_id": turn.get("response_character_id"),
                    "content": normalized_response_text,
                    "timestamp": created_at,
                    "message_type": "text",
                    "turn_index": turn.get("turn_index"),
                    "source": "turn_log",
                }
            )
    return records


def build_dialogue_records_for_session(
    story_events: List[Dict[str, Any]],
    turn_logs: List[Dict[str, Any]],
    story_snapshot: Optional[Dict[str, Any]],
    snapshot_event_type: Optional[str],
) -> tuple[List[Dict[str, Any]], str]:
    snapshot_dialogue = build_dialogue_records_from_snapshot(story_snapshot) if story_snapshot else []
    opening_snapshot, opening_event_type = extract_story_snapshot_from_events(
        story_events,
        preferred_event_types=["story_completed_generation", "story_created_full"],
    )
    opening_dialogue = build_dialogue_records_from_snapshot(opening_snapshot) if opening_snapshot else []
    character_map: Dict[str, str] = {}
    for snapshot in [opening_snapshot, story_snapshot]:
        snapshot_mapping = {
            str(char.get("id")): str(char.get("name") or char.get("id"))
            for char in ensure_list(ensure_mapping(snapshot).get("characters"))
            if ensure_mapping(char).get("id")
        }
        character_map.update(snapshot_mapping)
    turn_dialogue = build_dialogue_records_from_turn_logs(turn_logs, character_map=character_map)

    if snapshot_event_type in {"story_ended", "story_turn_completed", "story_choice_completed"} and snapshot_dialogue:
        return merge_adjacent_dialogue_records(snapshot_dialogue), snapshot_event_type

    if opening_dialogue or turn_dialogue:
        combined = merge_adjacent_dialogue_records(opening_dialogue + turn_dialogue)
        if opening_dialogue and turn_dialogue:
            return combined, "opening_snapshot_plus_turn_logs"
        if turn_dialogue:
            return combined, "turn_logs"
        return combined, opening_event_type or "story_snapshot"

    return merge_adjacent_dialogue_records(snapshot_dialogue), snapshot_event_type or "story_snapshot"


def log_completed_story_snapshot(
    event_type: str,
    story_id: str,
    story: Dict[str, Any],
    extra_payload: Optional[Dict[str, Any]] = None,
) -> None:
    final_story_snapshot = make_json_safe(attach_story_runtime_metadata(story_id, dict(story)))
    payload = {
        "final_story_snapshot": final_story_snapshot,
    }
    payload.update(extra_payload or {})
    experiment_store.log_story_event(
        event_type=event_type,
        story_id=story_id,
        session_id=story.get("session_id"),
        participant_id=story.get("participant_id"),
        payload=payload,
    )


def extract_response_messages(story: Dict[str, Any], previous_count: int) -> List[Dict[str, Any]]:
    messages = story.get("current_scene", {}).get("messages", [])
    new_messages = messages[previous_count:]
    response_messages = [
        msg for msg in new_messages
        if msg.get("character_id") != "system" or msg.get("type") not in {"typing"}
    ]
    # Exclude the optimistic user turn we append during advancement.
    if response_messages and response_messages[0].get("type") in {"message", "choice"}:
        response_messages = response_messages[1:]
    return response_messages


def log_turn_if_needed(
    story: Dict[str, Any],
    action_type: str,
    user_input: Optional[str],
    response_messages: List[Dict[str, Any]],
    latency_ms: Optional[float],
    choice_id: Optional[str] = None,
    choice_text: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    session_id = story.get("session_id")
    participant_id = story.get("participant_id")
    if not session_id and not participant_id:
        return
    session = get_story_session(story)
    profile = get_story_speed_profile(story=story, session=session)
    response_text = "\n".join(msg.get("content", "") for msg in response_messages).strip() or None
    response_character_id = response_messages[0].get("character_id") if response_messages else None
    turn_metadata = {
        "benchmark_speed_profile": profile.benchmark_speed_profile,
        "story_mode": profile.story_mode,
        "exchange_count": count_story_exchanges(story.get("current_scene", {}).get("messages", []) or []),
        "latency_bucket_ms": latency_bucket_ms(latency_ms),
        "generation_mode": story.get("generation_mode") or (
            "chat_native" if profile.benchmark_speed_profile else "legacy_json"
        ),
        "state_freshness": story.get("state_freshness") or (
            "derived" if profile.benchmark_speed_profile else "stale"
        ),
        "response_messages": make_json_safe(response_messages),
    }
    if extra_metadata:
        turn_metadata.update(extra_metadata)
    experiment_store.log_turn(
        session_id=session_id,
        participant_id=participant_id,
        story_id=story.get("id"),
        action_type=action_type,
        user_input=user_input,
        response_text=response_text,
        choice_id=choice_id,
        choice_text=choice_text,
        response_character_id=response_character_id,
        latency_ms=latency_ms,
        llm_config=story.get("llm_config", {}),
        model_provider=resolve_provider_for_task("story", story=story, session_id=session_id),
        metadata=turn_metadata,
    )


def get_story_speed_context(story: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Any]:
    session = get_story_session(story)
    profile = get_story_speed_profile(story=story, session=session)
    return session, profile


def get_effective_fast_forward(story: Dict[str, Any], requested_fast_forward: bool) -> bool:
    _, profile = get_story_speed_context(story)
    return bool(requested_fast_forward or profile.auto_fast_forward)


def maybe_start_conclusion_countdown(story: Dict[str, Any]) -> None:
    _, profile = get_story_speed_context(story)
    state = context_manager.story_states.get(story.get("id"))
    if not state or state.conclusion_countdown > 0:
        return
    dialogue_count = len(
        [
            message
            for message in story.get("current_scene", {}).get("messages", []) or []
            if message.get("type") != "system"
        ]
    )
    progression_count = get_progression_count_for_dialogue_count(profile, dialogue_count)
    if profile.benchmark_speed_profile and not has_scene_transition_occurred(story):
        return
    if progression_count >= profile.conclusion_start:
        state.conclusion_countdown = profile.conclusion_countdown_turns
        logger.warning(
            "[Endpoint Countdown] Started %s-turn countdown for %s at %s %s units",
            profile.conclusion_countdown_turns,
            story.get("id"),
            progression_count,
            profile.pacing_unit,
        )

# --- API Endpoints ---

@app.get("/access/session")
async def bootstrap_frontend_access_session(request: Request):
    request_origin = _resolve_request_origin(request)
    if request_origin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Frontend session bootstrap requires a same-origin request from the StoryGame site.",
        )

    _purge_expired_frontend_access_sessions()

    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    fingerprint = _get_request_fingerprint(request)
    now = time.time()
    frontend_access_sessions[session_id] = {
        "csrf_token": csrf_token,
        "origin": request_origin,
        "ip": fingerprint["ip"],
        "user_agent": fingerprint["user_agent"],
        "created_at": now,
        "expires_at": now + FRONTEND_ACCESS_SESSION_TTL_SECONDS,
    }

    response = JSONResponse(
        {
            "csrf_token": csrf_token,
            "expires_in": FRONTEND_ACCESS_SESSION_TTL_SECONDS,
        }
    )
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=FRONTEND_ACCESS_COOKIE_NAME,
        value=session_id,
        max_age=FRONTEND_ACCESS_SESSION_TTL_SECONDS,
        httponly=True,
        secure=FRONTEND_ACCESS_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return response


@app.get("/")
async def root():
    return {"message": "Start Your Journey API"}


@app.get("/experiments/conditions", response_model=List[ExperimentConditionResponse])
async def list_experiment_conditions():
    return experiment_store.list_conditions()


@app.get("/experiments/models", response_model=List[BenchmarkModelOptionResponse])
async def list_benchmark_models():
    return settings.get_benchmark_model_options()


@app.post("/experiments/judge", response_model=BenchmarkJudgeResponse)
async def judge_benchmark_session(input: BenchmarkJudgeRequest):
    try:
        selected_model = resolve_benchmark_selected_model(input.selected_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        normalized_payload = normalize_benchmark_judge_payload(input.benchmark_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    judge_messages = build_benchmark_judge_messages(normalized_payload)
    judge_response = await run_llm_completion(
        messages=judge_messages,
        model=selected_model,
        task="default",
    )
    if judge_response.get("error"):
        raise HTTPException(status_code=502, detail=judge_response["error"])

    try:
        parsed_judge = parse_benchmark_judge_result(judge_response.get("content", ""), model=selected_model)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to parse judge response: {exc}")

    return {
        "input_summary": build_judge_input_summary(normalized_payload, selected_model=selected_model),
        "judge_scores": parsed_judge["judge_scores"],
        "judge_summary": parsed_judge["judge_summary"],
        "slop_stats": compute_slop_stats(normalized_payload["dialogue"]),
    }


@app.post("/experiments/session/start", response_model=ExperimentSessionStartResponse)
async def start_experiment_session(input: ExperimentSessionStartInput):
    mode = input.mode or "benchmark"

    if is_blind_benchmark_mode_enabled():
        try:
            validate_blind_benchmark_configuration()
            blind_code = normalize_blind_code(input.blind_code)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        participant_id = build_blind_participant_id(blind_code)
        blind_invite_code = get_blind_invite_code(blind_code)
        participant_metadata = dict(input.participant_metadata or {})
        participant_metadata["blind_mode"] = True
        participant_metadata["blind_code"] = blind_code
        if blind_invite_code:
            participant_metadata["blind_invite_code"] = blind_invite_code
        participant_id = experiment_store.ensure_participant(
            participant_id=participant_id,
            metadata=participant_metadata,
        )

        existing_session = experiment_store.get_latest_active_blind_session(participant_id, mode=mode)
        if existing_session is not None:
            return sanitize_session_for_client(existing_session)

        completed_count = experiment_store.count_completed_blind_sessions(participant_id, mode=mode)
        quick_test_mode = is_blind_quick_test_code(blind_code)
        blind_access_label = get_blind_access_label(blind_code)
        if completed_count >= (BLIND_BENCHMARK_TEST_TOTAL_SLOTS if quick_test_mode else BLIND_BENCHMARK_TOTAL_SLOTS):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Quick test sequence for code {blind_access_label} is already complete."
                    if quick_test_mode
                    else f"Blind benchmark for invite code {blind_access_label} is already complete."
                ),
            )

        blind_sequence = get_blind_benchmark_sequence_for_code(blind_code)
        blind_total_slots = BLIND_BENCHMARK_TEST_TOTAL_SLOTS if quick_test_mode else BLIND_BENCHMARK_TOTAL_SLOTS
        blind_slot_index = completed_count
        selected_model = blind_sequence[blind_slot_index]
        session_metadata = dict(input.session_metadata or {})
        session_metadata.update(
            {
                "blind_mode": True,
                "blind_code": blind_code,
                "blind_slot_index": blind_slot_index,
                "blind_total_slots": blind_total_slots,
                "blind_mapping_version": (
                    BLIND_BENCHMARK_TEST_MAPPING_VERSION if quick_test_mode else BLIND_BENCHMARK_MAPPING_VERSION
                ),
                "quick_test_mode": quick_test_mode,
            }
        )
        if blind_invite_code:
            session_metadata["blind_invite_code"] = blind_invite_code
        session = experiment_store.create_session(
            participant_id=participant_id,
            mode=mode,
            requested_condition_id=input.requested_condition_id,
            metadata=session_metadata,
            selected_model=selected_model,
        )
        return sanitize_session_for_client(session)

    try:
        selected_model = resolve_benchmark_selected_model(input.selected_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    participant_id = experiment_store.ensure_participant(
        participant_id=input.participant_id,
        metadata=input.participant_metadata or {},
    )
    session = experiment_store.create_session(
        participant_id=participant_id,
        mode=mode,
        requested_condition_id=input.requested_condition_id,
        metadata=input.session_metadata or {},
        selected_model=selected_model,
    )
    return sanitize_session_for_client(session)


@app.get("/experiments/export")
async def export_experiment_data(format: str = Query("json", pattern="^(json|csv)$"), table: Optional[str] = None):
    if format == "json":
        if table:
            return {"table": table, "rows": experiment_store.export_table_rows(table)}
        return experiment_store.export_bundle()

    if not table:
        raise HTTPException(status_code=400, detail="CSV export requires a table query parameter")

    csv_content = experiment_store.export_table_csv(table)
    filename = f"{table}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Feedback ────────────────────────────────────────────────────────────────

@app.get("/experiments/sessions")
async def list_experiment_sessions(
    mode: Optional[str] = Query("benchmark"),
    limit: int = Query(50, ge=1, le=200),
):
    sessions = experiment_store.list_sessions(mode=mode, limit=limit)
    return [sanitize_session_for_client(session) for session in sessions]


def build_experiment_session_detail(session_id: str) -> Dict[str, Any]:
    session = experiment_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Experiment session not found")

    turn_logs = experiment_store.list_turn_logs(session_id)
    story_events = experiment_store.list_story_events(session_id)
    feedback_logs = experiment_store.list_feedback_logs(session_id)
    llm_call_logs = experiment_store.list_llm_call_logs(session_id)
    story_snapshot, snapshot_event_type = extract_story_snapshot_from_events(story_events)
    dialogue, dialogue_source = build_dialogue_records_for_session(
        story_events=story_events,
        turn_logs=turn_logs,
        story_snapshot=story_snapshot,
        snapshot_event_type=snapshot_event_type,
    )
    final_view_story = story_snapshot if snapshot_event_type in {"story_ended", "story_turn_completed", "story_choice_completed"} else None
    primary_story = final_view_story or story_snapshot
    participant_evaluation = build_participant_evaluation(feedback_logs)
    export_bundle = build_benchmark_result_export_payload(
        session=session,
        story=primary_story,
        dialogue_source=dialogue_source,
        dialogue=dialogue,
        turn_logs=turn_logs,
        story_events=story_events,
        llm_call_logs=llm_call_logs,
        feedback_logs=feedback_logs,
        story_snapshot=story_snapshot,
        final_view_story=final_view_story,
    )

    return {
        "session": session,
        "dialogue_source": dialogue_source,
        "dialogue": dialogue,
        "story_snapshot": make_json_safe(story_snapshot),
        "final_view_story": make_json_safe(final_view_story),
        "turn_logs": turn_logs,
        "feedback_logs": feedback_logs,
        "participant_evaluation": make_json_safe(participant_evaluation),
        "story_events": story_events,
        "llm_call_logs": llm_call_logs,
        "export_bundle": export_bundle,
    }


def sanitize_experiment_session_detail(detail: Dict[str, Any]) -> Dict[str, Any]:
    session = detail["session"]
    if not session.get("blind_mode"):
        sanitized = dict(detail)
        sanitized["session"] = sanitize_session_for_client(session)
        return sanitized

    return {
        **detail,
        "session": sanitize_session_for_client(session),
        "story_snapshot": sanitize_story_snapshot_for_client(detail.get("story_snapshot")),
        "final_view_story": sanitize_story_snapshot_for_client(detail.get("final_view_story")),
        "turn_logs": [sanitize_turn_log_for_client(item) for item in detail.get("turn_logs", [])],
        "story_events": [
            {
                **make_json_safe(item),
                "payload": sanitize_story_event_payload_for_client(ensure_mapping(item.get("payload"))),
            }
            for item in detail.get("story_events", [])
        ],
        "llm_call_logs": [sanitize_llm_call_log_for_client(item) for item in detail.get("llm_call_logs", [])],
        "export_bundle": sanitize_export_bundle_for_client(detail.get("export_bundle") or {}, session),
    }


def build_blind_review_session_details(current_session_id: str) -> Dict[str, Any]:
    session = experiment_store.get_session(current_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Experiment session not found")
    if not session.get("blind_mode"):
        raise HTTPException(status_code=400, detail="Blind review is only available for blind benchmark sessions")

    sibling_sessions = experiment_store.list_blind_sessions_for_participant(
        session["participant_id"],
        mode=session.get("mode") or "benchmark",
    )
    review_details: List[Dict[str, Any]] = []

    for sibling in sibling_sessions:
        sibling_session_id = sibling.get("session_id")
        if not sibling_session_id:
            continue

        detail = build_experiment_session_detail(sibling_session_id)
        has_story_data = bool(
            detail.get("session", {}).get("story_id")
            or detail.get("dialogue")
            or detail.get("turn_logs")
            or detail.get("story_snapshot")
            or detail.get("final_view_story")
            or detail.get("feedback_logs")
        )
        if not has_story_data:
            continue

        review_details.append(sanitize_experiment_session_detail(detail))

    review_details.sort(
        key=lambda item: (
            item.get("session", {}).get("blind_session_index") or 0,
            item.get("session", {}).get("started_at") or "",
        )
    )

    return {
        "current_session_id": current_session_id,
        "sessions": review_details,
    }


@app.get("/experiments/config")
async def get_experiment_config():
    return {
        "blind_benchmark_mode_enabled": is_blind_benchmark_mode_enabled(),
    }


@app.get("/experiments/sessions/{session_id}")
async def get_experiment_session_detail(session_id: str):
    detail = build_experiment_session_detail(session_id)
    return sanitize_experiment_session_detail(detail)


@app.get("/experiments/sessions/{session_id}/blind-review")
async def get_blind_review_session_details(session_id: str):
    return build_blind_review_session_details(session_id)


@app.get("/experiments/sessions/{session_id}/export")
async def export_experiment_session_result(session_id: str):
    detail = build_experiment_session_detail(session_id)
    return JSONResponse(content=detail["export_bundle"])


def _coerce_feedback_rating(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if 1 <= parsed <= 5:
        return parsed
    return None


def _normalize_feedback_payload(input: FeedbackInput) -> Dict[str, Any]:
    legacy_feedback_value = input.feedback_value if isinstance(input.feedback_value, dict) else {}
    normalized_scores: Dict[str, int] = {}

    if isinstance(input.scores, dict):
        for key, value in input.scores.items():
            coerced = _coerce_feedback_rating(value)
            if coerced is not None:
                normalized_scores[str(key)] = coerced

    if not normalized_scores:
        for key, value in legacy_feedback_value.items():
            if key in {"comment", "rating", "overall", "overall_rating"}:
                continue
            coerced = _coerce_feedback_rating(value)
            if coerced is not None:
                normalized_scores[str(key)] = coerced

    normalized_rating = (
        _coerce_feedback_rating(input.rating)
        or _coerce_feedback_rating(legacy_feedback_value.get("rating"))
        or _coerce_feedback_rating(legacy_feedback_value.get("overall"))
        or _coerce_feedback_rating(legacy_feedback_value.get("overall_rating"))
    )
    if normalized_rating is None:
        raise HTTPException(status_code=422, detail="Feedback rating is required.")

    normalized_comment = input.comment
    if normalized_comment is None:
        legacy_comment = legacy_feedback_value.get("comment")
        if isinstance(legacy_comment, str):
            normalized_comment = legacy_comment

    return {
        "rating": normalized_rating,
        "scores": normalized_scores,
        "comment": normalized_comment,
    }


@app.post("/feedback")
async def submit_feedback(input: FeedbackInput):
    """收集用户对本次故事旅程的评分与感受。"""
    normalized_feedback = _normalize_feedback_payload(input)
    entry = {
        "id": str(uuid.uuid4()),
        "story_id": input.story_id,
        "user_id": input.user_id,
        "participant_id": input.participant_id,
        "session_id": input.session_id,
        "rating": normalized_feedback["rating"],
        "feelings": input.feelings or [],
        "scores": normalized_feedback["scores"],
        "comment": normalized_feedback["comment"],
        "feedback_type": input.feedback_type or "general",
        "form_version": input.form_version,
        "created_at": datetime.now().isoformat(),
    }
    stored_feedback = experiment_store.save_feedback(
        feedback_id=entry["id"],
        session_id=input.session_id,
        participant_id=input.participant_id,
        story_id=input.story_id,
        user_id=input.user_id,
        rating=normalized_feedback["rating"],
        feelings=input.feelings or [],
        comment=normalized_feedback["comment"],
        feedback_type=input.feedback_type or "general",
        scores=normalized_feedback["scores"],
        form_version=input.form_version,
    )
    entry.update(stored_feedback or {})
    feedback_db[:] = [item for item in feedback_db if item.get("id") != entry["id"] and not (
        item.get("session_id") == input.session_id and item.get("feedback_type") == (input.feedback_type or "general")
    )]
    feedback_db.append(entry)
    experiment_store.log_story_event(
        event_type="feedback_submitted",
        story_id=input.story_id,
        session_id=input.session_id,
        participant_id=input.participant_id,
        payload=make_json_safe(
            {
                "user_id": input.user_id,
                "rating": normalized_feedback["rating"],
                "feelings": input.feelings or [],
                "scores": normalized_feedback["scores"],
                "comment": normalized_feedback["comment"],
                "feedback_type": input.feedback_type or "general",
                "form_version": input.form_version,
                "feedback_log_id": entry["id"],
            }
        ),
    )
    logger.info(f"[Feedback] Received entry: rating={entry['rating']} feelings={entry['feelings']}")
    return {"success": True, "message": "感谢你的反馈！", "id": entry["id"], "feedback": entry}


@app.get("/feedback")
async def list_feedback(story_id: Optional[str] = None):
    """查询已收集的反馈（可按 story_id 过滤）。"""
    data = feedback_db if story_id is None else [f for f in feedback_db if f.get("story_id") == story_id]
    return {
        "total": len(data),
        "items": data,
        "avg_rating": round(sum(f["rating"] for f in data) / len(data), 2) if data else None,
    }

@app.post("/stories/quickstart", response_model=StoryResponse)
async def create_quick_test_story(input: QuickTestStoryInput):
    session = get_session_context(input.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Experiment session not found")
    if not session.get("quick_test_mode"):
        raise HTTPException(status_code=400, detail="Quick test stories are only available for quick test code 0.")

    existing_story_id = session.get("story_id")
    existing_story = stories_db.get(existing_story_id) if existing_story_id else None
    if existing_story and existing_story.get("status") != "completed":
        story = attach_story_runtime_metadata(existing_story_id, dict(existing_story))
        stories_db[existing_story_id] = story
        return story

    participant_id = input.participant_id or session.get("participant_id")
    user_id = input.user_id or participant_id
    story_id = str(uuid.uuid4())
    story = build_quick_test_story_payload(
        story_id=story_id,
        session=session,
        participant_id=participant_id,
    )
    story["user_id"] = user_id
    story = standardize_story_response(story)
    stories_db[story_id] = story

    if user_id:
        context_manager.create_user_profile(
            user_id,
            {
                "quick_test_mode": True,
                "keywords": story.get("keywords", []),
            },
        )
    context_manager.create_story_state(story_id, story)
    state = context_manager.story_states.get(story_id)
    if state:
        state.conclusion_countdown = 1
        state.what_just_happened = "The lantern room opened directly at the final decision point."
        state.current_goal = "Conclude this run and verify the next hidden slot can start cleanly."
        state.open_tensions = ["Whether to end immediately or take one extra validation step first."]
        state.active_clues = ["The logbook tracks completed runs.", "The lantern color changes with each hidden slot."]
        state.last_major_turning_point = "The Keeper configured the room for a fast benchmark ending."

    story = attach_story_runtime_metadata(story_id, story)
    stories_db[story_id] = story
    experiment_store.attach_story_to_session(
        session_id=input.session_id,
        story_id=story_id,
        emotional_need=story.get("emotional_need"),
        metadata={"quick_test_story": True},
    )
    experiment_store.log_story_event(
        event_type="story_created_full",
        story_id=story_id,
        session_id=input.session_id,
        participant_id=participant_id,
        payload=make_json_safe(
            {
                "title": story.get("title"),
                "status": story.get("status"),
                "quick_test_mode": True,
                "final_story_snapshot": story,
            }
        ),
    )
    return story

@app.post("/story/initiate", response_model=QuestionsResponse)
async def initiate_story_creation(input: EmotionalNeedInput):
    """
    Step 1: Takes the user's emotional need and generates clarifying questions.
    """
    story_id = str(uuid.uuid4())
    experiment_meta = build_story_experiment_metadata(input.session_id, input.participant_id)
    participant_id = experiment_meta.get("participant_id")
    
    # Create or get user profile
    if input.user_id:
        if input.user_id not in context_manager.user_profiles:
            context_manager.create_user_profile(input.user_id)
    
    # 1. Prepare the prompt for the LLM
    prompt = prompt_templates.CLARIFYING_QUESTIONS_PROMPT_TEMPLATE.format(
        emotional_need=input.emotional_need
    )
    
    messages = [{"role": "system", "content": "You are an empathetic therapeutic storyteller who asks specific, practical questions to understand users' emotional situations. Your questions help gather concrete details to create personalized healing stories."}, 
                {"role": "user", "content": prompt}]

    keyword_prompt = prompt_templates.KEYWORD_SUGGESTION_PROMPT_TEMPLATE.format(
        emotional_need=input.emotional_need
    )
    profile_prompt = prompt_templates.PROFILE_KEYWORDS_PROMPT_TEMPLATE.format(
        emotional_need=input.emotional_need
    )

    # 2. Run the startup text-generation calls in parallel.
    if settings.QUESTIONS_GENERATION_TEMPERATURE == -1:
        question_task = asyncio.create_task(run_llm_completion(
            messages=messages,
            model=resolve_model_for_task("questions", session_id=input.session_id),
            trace_context=build_llm_trace_context(
                "clarifying_questions",
                "questions",
                session_id=input.session_id,
                participant_id=participant_id,
                story_id=story_id,
                metadata={"emotional_need": input.emotional_need},
            ),
        ))
    else:
        question_task = asyncio.create_task(run_llm_completion(
            messages=messages,
            model=resolve_model_for_task("questions", session_id=input.session_id),
            temperature=settings.QUESTIONS_GENERATION_TEMPERATURE,
            trace_context=build_llm_trace_context(
                "clarifying_questions",
                "questions",
                session_id=input.session_id,
                participant_id=participant_id,
                story_id=story_id,
                metadata={"emotional_need": input.emotional_need},
            ),
        ))

    keyword_task = asyncio.create_task(run_llm_completion(
        messages=[
            {"role": "system", "content": "You are a creative assistant."},
            {"role": "user", "content": keyword_prompt},
        ],
        model=resolve_model_for_task("keywords", session_id=input.session_id),
        trace_context=build_llm_trace_context(
            "keyword_suggestion",
            "keywords",
            session_id=input.session_id,
            participant_id=participant_id,
            story_id=story_id,
            metadata={"emotional_need": input.emotional_need},
        ),
    ))
    profile_task = asyncio.create_task(run_llm_completion(
        messages=[
            {"role": "system", "content": "You are a creative assistant."},
            {"role": "user", "content": profile_prompt},
        ],
        model=resolve_model_for_task("profile_keywords", session_id=input.session_id),
        trace_context=build_llm_trace_context(
            "profile_keyword_suggestion",
            "profile_keywords",
            session_id=input.session_id,
            participant_id=participant_id,
            story_id=story_id,
            metadata={"emotional_need": input.emotional_need},
        ),
    ))

    response, kw_resp, profile_resp = await asyncio.gather(
        question_task,
        keyword_task,
        profile_task,
    )

    if response["error"]:
        raise HTTPException(status_code=500, detail=response["error"])

    try:
        content_to_parse = response["content"]
        # If the response is wrapped in markdown, extract the JSON part
        if '```json' in content_to_parse:
            start_index = content_to_parse.find('[')
            end_index = content_to_parse.rfind(']') + 1
            content_to_parse = content_to_parse[start_index:end_index]

        questions_data = json.loads(content_to_parse)
        if not isinstance(questions_data, list):
            raise json.JSONDecodeError("Response is not a list", content_to_parse, 0)
        
        # Build question text list after fallback
        questions = [q.get("question", "") for q in questions_data]
        
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        # Fallback: extract individual JSON objects with regex and parse one-by-one
        import re
        obj_strs = re.findall(r"\{[^{}]*\}", content_to_parse, re.S)
        questions_data=[]
        for s in obj_strs:
            try:
                questions_data.append(json.loads(s))
            except Exception:
                continue
        if len(questions_data) < 5:  # still bad
            logger.error(f"Failed to parse LLM response for questions: {response['content']} - Error: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to generate valid questions.")
        # Build question text list in fallback as well
        questions = [q.get("question", "") for q in questions_data]

    # 3. Store the initial data
    stories_db[story_id] = {
        "id": story_id,
        "user_id": input.user_id or experiment_meta.get("participant_id"),
        "participant_id": experiment_meta.get("participant_id"),
        "session_id": input.session_id,
        "condition_id": experiment_meta.get("condition_id"),
        "condition_name": experiment_meta.get("condition_name"),
        "selected_model": experiment_meta.get("selected_model"),
        "llm_config": experiment_meta.get("llm_config", {}),
        "emotional_need": input.emotional_need,
        "clarifying_questions": questions_data,  # Store the full question objects with options
        "status": "pending_answers",
        "experiment_mode": experiment_meta.get("experiment_mode", False),
    }
    
    logger.info(f"Initiated story {story_id} for user {input.user_id}.")
    logger.debug(f"Story {story_id} created with questions: {questions}")

    keywords: list = []
    if kw_resp["error"]:
        logger.warning(f"Keyword generation failed: {kw_resp['error']}")
    else:
        try:
            kw_content = kw_resp["content"]
            if '```json' in kw_content:
                start = kw_content.find('[')
                end = kw_content.rfind(']') + 1
                kw_content = kw_content[start:end]
            parsed = json.loads(kw_content)
            if isinstance(parsed, list):
                keywords = [str(k) for k in parsed]
        except Exception as e:
            logger.warning(f"Failed to parse keyword JSON: {e}")

    stories_db[story_id]["keywords"] = keywords

    profile_keywords: Dict[str, List[str]] = {}
    if profile_resp["error"]:
        logger.warning(f"Profile keyword generation failed: {profile_resp['error']}")
    else:
        try:
            prof_content = profile_resp["content"]
            if '```json' in prof_content:
                start = prof_content.find('{')
                end = prof_content.rfind('}') + 1
                prof_content = prof_content[start:end]
            parsed_prof = json.loads(prof_content)
            if isinstance(parsed_prof, dict):
                profile_keywords = {k: [str(x) for x in v] for k, v in parsed_prof.items() if isinstance(v, list)}
        except Exception as e:
            logger.warning(f"Failed to parse profile keyword JSON: {e}")

    stories_db[story_id]["profile_keywords"] = profile_keywords

    if input.session_id:
        experiment_store.attach_story_to_session(
            session_id=input.session_id,
            story_id=story_id,
            emotional_need=input.emotional_need,
            metadata={"story_initialized": True},
        )
        experiment_store.log_story_event(
            event_type="story_initiated",
            story_id=story_id,
            session_id=input.session_id,
            participant_id=participant_id,
            payload=make_json_safe(
                {
                    "emotional_need": input.emotional_need,
                    "questions": questions,
                    "questions_data": questions_data,
                    "keywords": keywords,
                    "profile_keywords": profile_keywords,
                }
            ),
        )

    # Return including profile_keywords
    return QuestionsResponse(
        story_id=story_id, 
        questions=questions,  # For backward compatibility
        questions_data=questions_data,  # New field with full question objects
        keywords=keywords,
        profile_keywords=profile_keywords
    )

@app.post("/story/create/step1", response_model=StoryStep1Response)
async def create_story_step1(input: StoryStep1Input):
    """
    步骤1: 创建故事的基础框架 - 标题、概念、主题和情感基调
    """
    story_id = input.story_id
    guidance_sentence = input.guidance_sentence or ""
    experiment_meta = build_story_experiment_metadata(input.session_id, input.participant_id)
    
    # 检查story_id是否存在
    if story_id not in stories_db:
        if not input.emotional_need:
            raise HTTPException(status_code=400, detail="For new stories, emotional_need is required")
        # 创建新的故事记录
        story_id = str(uuid.uuid4())
        stories_db[story_id] = {
            "id": story_id,
            "user_id": input.user_id or experiment_meta.get("participant_id"),
            "participant_id": experiment_meta.get("participant_id"),
            "session_id": input.session_id,
            "condition_id": experiment_meta.get("condition_id"),
            "condition_name": experiment_meta.get("condition_name"),
            "selected_model": experiment_meta.get("selected_model"),
            "llm_config": experiment_meta.get("llm_config", {}),
            "emotional_need": input.emotional_need,
            "status": "in_progress",
            "current_step": 1,
            "experiment_mode": experiment_meta.get("experiment_mode", False),
        }
    else:
        # 更新现有故事
        stories_db[story_id]["status"] = "in_progress"
        stories_db[story_id]["current_step"] = 1
    
    # 处理答案 - 支持多选题的逗号分隔答案
    processed_answers = {}
    if hasattr(input, 'answers') and input.answers:
        # 检查是否有问题数据可用
        if story_id in stories_db and "clarifying_questions" in stories_db[story_id]:
            questions_data = stories_db[story_id]["clarifying_questions"]
            for q_data in questions_data:
                question = q_data.get("question", "")
                if question in input.answers:
                    answer = input.answers[question]
                    # 检查是否为多选题答案（逗号分隔的字符串）
                    if "," in answer and q_data.get("questionType") == "multiple":
                        # 拆分为列表并处理
                        answer_list = [a.strip() for a in answer.split(",")]
                        processed_answers[question] = answer_list
                    else:
                        processed_answers[question] = answer
        else:
            # 如果没有问题数据，直接使用原始答案
            processed_answers = input.answers
    
    # 准备提示词
    prompt = prompt_templates.STORY_STEP1_PROMPT.format(
        emotional_need=input.emotional_need,
        keywords=", ".join(input.selected_keywords or []),
        guidance_sentence=guidance_sentence
    )
    
    # 如果有处理后的答案，添加到提示中
    if processed_answers:
        # 将答案转换为易于阅读的格式
        answers_text = ""
        for question, answer in processed_answers.items():
            if isinstance(answer, list):
                # 如果是列表（多选题答案），以项目符号形式展示
                answers_text += f"\n- {question}\n  * {' * '.join(answer)}"
            else:
                # 如果是单个答案
                answers_text += f"\n- {question}: {answer}"
        
        # 添加到提示中
        prompt += f"\n\nUser's answers to clarifying questions:{answers_text}"
    
    system_prompt = f"{prompt_templates.SYSTEM_PROMPT}\n\nIMPORTANT: This story MUST prominently feature the following user-selected keywords as central elements: {', '.join(input.selected_keywords or [])}."
    
    messages = [
        {"role": "system", "content": system_prompt}, 
        {"role": "user", "content": f"Please generate the story foundation based on this prompt:\n\n{prompt}\n\nThe response must be a valid JSON object matching this schema: {prompt_templates.STORY_STEP1_SCHEMA}"}
    ]

    # 调用LLM
    logger.info(f"Step 1: Generating story foundation for story {story_id}")
    response = await run_llm_completion(
        messages=messages,
        model=resolve_model_for_task("story", story=stories_db.get(story_id), session_id=input.session_id),
        trace_context=build_llm_trace_context(
            "story_step1",
            "story",
            story=stories_db.get(story_id),
            session_id=input.session_id,
            participant_id=stories_db.get(story_id, {}).get("participant_id"),
            story_id=story_id,
            metadata={"selected_keywords": input.selected_keywords or []},
        ),
    )

    if response["error"]:
        raise HTTPException(status_code=500, detail=response["error"])
    
    # 解析响应
    try:
        content_to_parse = extract_json_from_response(response["content"])
        foundation_data = json.loads(content_to_parse)
        logger.info(f"Successfully generated story foundation for {story_id}")
    except (ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse LLM response: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate valid story foundation")
    
    # 保存到故事数据
    stories_db[story_id].update({
        "title": foundation_data.get("title", "Untitled Story"),
        "high_concept_premise": foundation_data.get("high_concept_premise", ""),
        "cinematic_theme": foundation_data.get("cinematic_theme", ""),
        "emotional_undercurrent": foundation_data.get("emotional_undercurrent", ""),
        "protagonist_objective": foundation_data.get("protagonist_objective", ""),
        "profile_keywords": input.profile_keywords or stories_db[story_id].get("profile_keywords", {})
    })

    experiment_store.log_story_event(
        event_type="story_step1_completed",
        story_id=story_id,
        session_id=stories_db[story_id].get("session_id"),
        participant_id=stories_db[story_id].get("participant_id"),
        payload=make_json_safe(
            {
                "request": {
                    "emotional_need": input.emotional_need,
                    "answers": processed_answers,
                    "selected_keywords": input.selected_keywords or [],
                    "guidance_sentence": guidance_sentence,
                },
                "response": foundation_data,
            }
        ),
    )
    
    return StoryStep1Response(
        story_id=story_id,
        title=foundation_data.get("title", "Untitled Story"),
        high_concept_premise=foundation_data.get("high_concept_premise", ""),
        cinematic_theme=foundation_data.get("cinematic_theme", ""),
        emotional_undercurrent=foundation_data.get("emotional_undercurrent", ""),
        protagonist_objective=foundation_data.get("protagonist_objective", "")
    )

@app.post("/story/create/step2", response_model=StoryStep2Response)
async def create_story_step2(input: StoryStep2Input):
    """
    步骤2: 世界构建 - 创建故事的设定和环境
    """
    story_id = input.story_id
    
    # 检查story_id是否存在
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story_data = stories_db[story_id]
    
    # 检查前一步是否完成
    if "title" not in story_data:
        raise HTTPException(status_code=400, detail="Step 1 must be completed first")
    
    # 更新故事状态
    story_data["current_step"] = 2
    
    # 准备提示词
    prompt = prompt_templates.STORY_STEP2_PROMPT.format(
        title=story_data.get("title", ""),
        high_concept_premise=story_data.get("high_concept_premise", ""),
        cinematic_theme=story_data.get("cinematic_theme", ""),
        emotional_undercurrent=story_data.get("emotional_undercurrent", "")
    )
    
    messages = [
        {"role": "system", "content": prompt_templates.SYSTEM_PROMPT}, 
        {"role": "user", "content": f"Please generate the story setting based on this prompt:\n\n{prompt}\n\nThe response must be a valid JSON object matching this schema: {prompt_templates.STORY_STEP2_SCHEMA}"}
    ]

    # 调用LLM
    logger.info(f"Step 2: Generating setting for story {story_id}")
    response = await run_llm_completion(
        messages=messages,
        model=resolve_model_for_task("story", story=story_data),
        trace_context=build_llm_trace_context(
            "story_step2",
            "story",
            story=story_data,
            story_id=story_id,
        ),
    )

    if response["error"]:
        raise HTTPException(status_code=500, detail=response["error"])
        
    # 解析响应
    try:
        content_to_parse = extract_json_from_response(response["content"])
        setting_data = json.loads(content_to_parse)
        logger.info(f"Successfully generated setting for {story_id}")
    except (ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse LLM response: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate valid setting")
    
    # 保存到故事数据
    setting = setting_data.get("setting", {})
    story_data["setting"] = setting
    experiment_store.log_story_event(
        event_type="story_step2_completed",
        story_id=story_id,
        session_id=story_data.get("session_id"),
        participant_id=story_data.get("participant_id"),
        payload=make_json_safe(
            {
                "request": {
                    "title": story_data.get("title"),
                    "high_concept_premise": story_data.get("high_concept_premise"),
                    "cinematic_theme": story_data.get("cinematic_theme"),
                    "emotional_undercurrent": story_data.get("emotional_undercurrent"),
                },
                "response": {"setting": setting},
            }
        ),
    )
    
    return StoryStep2Response(
        story_id=story_id,
        setting=setting
    )

@app.post("/story/create/step3", response_model=StoryStep3Response)
async def create_story_step3(input: StoryStep3Input):
    """
    步骤3: 角色创建 - 生成故事中的角色
    """
    story_id = input.story_id
    
    # 检查story_id是否存在
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story_data = stories_db[story_id]
    
    # 检查前一步是否完成
    if "setting" not in story_data:
        raise HTTPException(status_code=400, detail="Step 2 must be completed first")
    
    # 更新故事状态
    story_data["current_step"] = 3
    
    # 准备提示词
    prompt = prompt_templates.STORY_STEP3_PROMPT.format(
        title=story_data.get("title", ""),
        high_concept_premise=story_data.get("high_concept_premise", ""),
        cinematic_theme=story_data.get("cinematic_theme", ""),
        emotional_undercurrent=story_data.get("emotional_undercurrent", ""),
        setting=json.dumps(story_data.get("setting", {}), indent=2)
    )
    
    messages = [
        {"role": "system", "content": prompt_templates.SYSTEM_PROMPT}, 
        {"role": "user", "content": f"Please generate characters based on this prompt:\n\n{prompt}\n\nThe response must be a valid JSON array matching this schema: {prompt_templates.STORY_STEP3_SCHEMA}"}
    ]

    # 调用LLM
    logger.info(f"Step 3: Generating characters for story {story_id}")
    response = await run_llm_completion(
        messages=messages,
        model=resolve_model_for_task("story", story=story_data),
        trace_context=build_llm_trace_context(
            "story_step3",
            "story",
            story=story_data,
            story_id=story_id,
        ),
    )

    if response["error"]:
        raise HTTPException(status_code=500, detail=response["error"])
        
    # 解析响应
    try:
        content_to_parse = extract_json_from_response(response["content"])
        characters = json.loads(content_to_parse)
        logger.info(f"Successfully generated characters for {story_id}")
    except (ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse LLM response: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate valid characters")
    
    # 验证角色数据
    if not isinstance(characters, list):
        raise HTTPException(status_code=500, detail="Invalid characters format")
    
    # 规范化所有角色ID
    for char in characters:
        if "name" in char:
            # 确保角色ID是规范化的
            if "id" not in char or not char["id"]:
                # 如果没有ID，根据名称生成
                char["id"] = normalize_character_id(char["name"])
        else:
                # 确保ID是规范化的
                char["id"] = normalize_character_id(char["id"])
    
    # 确保有一个主角色
    protagonists = [c for c in characters if c.get("role") == "protagonist"]
    if len(protagonists) == 0 and len(characters) > 0:
        characters[0]["role"] = "protagonist"
        logger.warning(f"No protagonist found in story {story_id}. Assigning role to first character.")
    elif len(protagonists) > 1:
        for i in range(1, len(protagonists)):
            protagonists[i]["role"] = "supporting"
        logger.warning(f"Multiple protagonists found in story {story_id}. Corrected to one.")
    
    # 生成角色图像 - 添加并发图像生成
    await generate_character_images(characters, story_id)
    
    # 保存到故事数据
    story_data["characters"] = characters
    
    # 应用标准化
    story_data = standardize_story_response(story_data)
    stories_db[story_id] = story_data
    experiment_store.log_story_event(
        event_type="story_step3_completed",
        story_id=story_id,
        session_id=story_data.get("session_id"),
        participant_id=story_data.get("participant_id"),
        payload=make_json_safe(
            {
                "request": {
                    "title": story_data.get("title"),
                    "setting": story_data.get("setting"),
                    "cinematic_theme": story_data.get("cinematic_theme"),
                    "emotional_undercurrent": story_data.get("emotional_undercurrent"),
                },
                "response": {"characters": story_data["characters"]},
            }
        ),
    )
    
    return StoryStep3Response(
        story_id=story_id,
        characters=story_data["characters"]
    )

def _image_api_key_available() -> bool:
    """Check whether the configured image generation provider has a valid API key."""
    provider = (settings.IMAGE_API_PROVIDER or "openai").lower()
    if provider == "gemini":
        key = settings.GEMINI_API_KEY
    else:
        key = settings.OPENAI_API_KEY or settings.LLM_API_KEY
    return bool(key and not key.startswith("your_"))


def _template_avatar_url(name: str, role: str = "supporting") -> str:
    """Return a deterministic template avatar URL based on character name/role."""
    import urllib.parse
    seed = urllib.parse.quote(name)
    bg_colors = {
        "protagonist": "7db8a2",
        "mentor": "a0b4d8",
        "antagonist": "c87870",
        "supporting": "b0a8d8",
    }
    bg = bg_colors.get(role, "b0a8d8")
    return f"https://api.dicebear.com/9.x/adventurer/svg?seed={seed}&backgroundColor={bg}"


async def generate_character_images(characters, story_id):
    """
    Generate AI character portraits and write them to disk, falling back to
    template avatars when the image API key is missing or generation fails.
    """
    import asyncio
    from pathlib import Path

    # Fast path: if no image API key is configured, skip generation entirely
    if not _image_api_key_available():
        logger.info(f"[Character Images] No image API key configured — using template avatars for story {story_id}")
        for char in characters:
            name = char.get("name") or "Character"
            role = char.get("role") or "supporting"
            char["imageUrl"] = _template_avatar_url(name, role)
        return characters

    base_dir = Path(f"images/characters/{story_id}")
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        from src.meta_planner import generate_image
    except Exception as e:
        logger.error(f"Failed to import generate_image: {e}")
        generate_image = None

    async def generate_for_character(char):
        character_name = char.get("name") or "Character"
        character_id = char.get("id") or normalize_character_id(character_name)
        role = char.get("role") or "supporting"

        try:
            if not generate_image:
                char["imageUrl"] = _template_avatar_url(character_name, role)
                return

            description = char.get("description") or char.get("backstory") or ""
            traits = ", ".join(char.get("traits", []) if isinstance(char.get("traits"), list) else [])

            prompt_parts = [
                f"Professional studio photograph of {character_name}, {role}",
                "full body standing pose, complete figure from head to toe",
                "transparent background, PNG format, isolated subject",
                "IMPORTANT: photorealistic human, NOT illustration, NOT cartoon, NOT anime, NOT digital art",
                "real person photography, professional studio lighting setup",
                "warm and gentle lighting, soft natural skin tones, cinematic portrait photography",
                "authentic human features, genuine compassionate expression, healing atmosphere",
                "approachable and kind demeanor, natural welcoming posture",
                "high-end portrait photography, fashion editorial style",
            ]
            if description:
                prompt_parts.append(f"character details: {description}")
            if traits:
                prompt_parts.append(f"personality: {traits}")
            prompt_parts.append("emotional warmth, therapeutic presence, calming ambiance, real human subject")
            prompt = ", ".join([p for p in prompt_parts if p])

            output_path = str(base_dir / f"{character_id}.png")
            relative_url = f"images/characters/{story_id}/{character_id}.png"

            result = await generate_image(
                prompt=prompt,
                output_path=output_path,
                api_provider=settings.IMAGE_API_PROVIDER,
                model="gemini-2.5-flash-image-preview" if settings.IMAGE_API_PROVIDER == "gemini" else "gpt-image-1",
                size="1024x1024",
                quality="medium",
                save_image=True,
            )

            if result.get("success"):
                bg_result = await remove_background(output_path)
                if bg_result.get("success"):
                    logger.info(f"Background removed for {character_name}")
                else:
                    logger.warning(f"Background removal failed for {character_name}: {bg_result.get('error')}")
                char["imageUrl"] = relative_url
                logger.info(f"Character image generated: {relative_url}")
            else:
                char["imageUrl"] = _template_avatar_url(character_name, role)
                logger.warning(f"Fallback to template avatar for {character_name}: {result.get('error')}")
        except Exception as e:
            char["imageUrl"] = _template_avatar_url(character_name, role)
            logger.error(f"Failed to generate character image for {character_name}: {e}")

    await asyncio.gather(*(generate_for_character(char) for char in characters))
    return characters


def attach_story_runtime_metadata(story_id: str, story_data: dict) -> dict:
    """Attach recap/progress metadata used by the live interaction UI."""
    if not story_data or not isinstance(story_data, dict):
        return story_data

    story_data["story_id"] = story_data.get("story_id") or story_data.get("id") or story_id
    story_data["theme"] = story_data.get("theme") or story_data.get("cinematic_theme") or ""
    story_data["emotional_goal"] = story_data.get("emotional_goal") or story_data.get("emotional_undercurrent") or ""
    session = get_story_session(story_data)
    runtime_flags = build_runtime_story_flags(story=story_data, session=session)
    story_data.update(runtime_flags)
    story_data["generation_mode"] = story_data.get("generation_mode") or (
        "chat_native" if story_data.get("benchmark_speed_profile") else "legacy_json"
    )
    story_data["state_freshness"] = story_data.get("state_freshness") or (
        "derived" if story_data.get("benchmark_speed_profile") else "stale"
    )
    story_data.setdefault("state_updated_at", None)
    story_data["characters"] = ensure_list(story_data.get("characters"))
    story_data["acts"] = ensure_list(story_data.get("acts"))
    current_scene = ensure_mapping(story_data.get("current_scene"))
    story_data["current_scene"] = current_scene
    current_scene["messages"] = ensure_list(current_scene.get("messages"))
    current_scene["choices"] = ensure_list(current_scene.get("choices"))

    mixed_pattern = re.compile(r"\*[^*]+\*")
    for message in current_scene["messages"]:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content", "") or "")
        inferred_render_mode = (
            "rp_mixed"
            if mixed_pattern.search(content) or message.get("action") or message.get("direction")
            else "plain"
        )
        message["render_mode"] = message.get("render_mode") or message.get("renderMode") or inferred_render_mode
        message["renderMode"] = message["render_mode"]

    def _character_tokens(*values: Any) -> List[str]:
        tokens: List[str] = []
        seen = set()
        for value in values:
            raw_text = str(value or "").strip()
            if not raw_text:
                continue
            normalized_text = normalize_character_id(raw_text)
            for candidate in (raw_text, normalized_text):
                token = re.sub(r"[^a-z0-9]+", "", str(candidate or "").lower())
                if token and token not in seen:
                    seen.add(token)
                    tokens.append(token)
        return tokens

    character_aliases: Dict[str, str] = {}
    protagonist_id = ""
    for character in story_data.get("characters", []):
        canonical_id = str(character.get("id", "") or "").strip()
        if not canonical_id:
            continue
        for token in _character_tokens(canonical_id, character.get("name")):
            character_aliases[token] = canonical_id
        if character.get("role") == "protagonist" and not protagonist_id:
            protagonist_id = canonical_id
    if protagonist_id:
        character_aliases.setdefault("protagonist", protagonist_id)

    def _resolve_character_id(raw_value: Any) -> str:
        raw_text = str(raw_value or "").strip()
        if not raw_text or raw_text == "system":
            return ""
        for token in _character_tokens(raw_text):
            canonical_id = character_aliases.get(token)
            if canonical_id:
                return canonical_id
        return ""

    last_transition_index = -1
    for index, message in enumerate(current_scene.get("messages", [])):
        if not isinstance(message, dict):
            continue
        message_content = str(message.get("content", "") or "").strip()
        if str(message.get("id", "") or "").startswith("transition-") or (
            message.get("type") == "system"
            and message_content.startswith("[")
            and message_content.endswith("]")
            and " - " in message_content
        ):
            last_transition_index = index

    in_scene_character_ids = {protagonist_id} if protagonist_id else set()
    for message in current_scene.get("messages", [])[last_transition_index + 1:]:
        if not isinstance(message, dict) or message.get("type") != "text":
            continue
        resolved_character_id = _resolve_character_id(
            message.get("character_id") or message.get("characterId")
        )
        if resolved_character_id:
            in_scene_character_ids.add(resolved_character_id)

    def _recent_character_line(character_id: str) -> str:
        messages = list(reversed(current_scene.get("messages", [])))
        for message in messages:
            resolved_character_id = _resolve_character_id(
                message.get("character_id") or message.get("characterId")
            )
            if resolved_character_id == character_id and message.get("type") == "text":
                return str(message.get("content", "")).strip()
        return ""

    state = context_manager.story_states.get(story_id)
    if state:
        story_data["dialogue_summaries"] = state.dialogue_summaries[-6:]
        story_data["dialogue_count"] = state.dialogue_counter
        story_data["conclusion_countdown"] = state.conclusion_countdown
        story_data["story_memory"] = {
            "what_just_happened": state.what_just_happened,
            "current_goal": state.current_goal or story_data.get("protagonist_objective", ""),
            "open_tensions": state.open_tensions,
            "active_clues": state.active_clues,
            "last_major_turning_point": state.last_major_turning_point,
        }
    else:
        story_data.setdefault("dialogue_summaries", [])
        story_data.setdefault("dialogue_count", 0)
        story_data.setdefault("conclusion_countdown", 0)
        story_data.setdefault("story_memory", {
            "what_just_happened": "",
            "current_goal": story_data.get("protagonist_objective", ""),
            "open_tensions": [],
            "active_clues": [],
            "last_major_turning_point": "",
        })

    story_memory = ensure_mapping(story_data.get("story_memory"))
    story_data["story_memory"] = story_memory

    current_messages = current_scene.get("messages", []) or []
    exchange_count = count_story_exchanges(current_messages)
    story_data["exchange_count"] = exchange_count
    profile = get_story_speed_profile(story=story_data, session=session)
    progression_count = get_progression_count_for_dialogue_count(profile, story_data.get("dialogue_count"))
    pacing_level = build_pacing_level(profile, progression_count)
    story_data["pacing_profile"] = {
        "level": pacing_level,
        "description": build_pacing_description(profile, pacing_level),
        "progression_count": progression_count,
        "progression_unit": profile.pacing_unit,
        "exchange_count": exchange_count,
        "dialogue_count": story_data.get("dialogue_count", 0),
        "thresholds": {
            "acceleration_start": profile.acceleration_start,
            "critical_start": profile.critical_start,
            "mandatory_shift_start": profile.mandatory_shift_start,
            "structure_guard_start": profile.structure_guard_start,
            "conclusion_start": profile.conclusion_start,
            "conclusion_countdown_turns": profile.conclusion_countdown_turns,
        },
    }

    story_state = ensure_mapping(story_data.get("story_state"))
    story_data["story_state"] = story_state
    story_state.setdefault("current_objective", story_memory.get("current_goal", story_data.get("protagonist_objective", "")))
    story_state.setdefault("current_tension", "")
    story_state.setdefault("immediate_stakes", "")
    story_state.setdefault("location_status", current_scene.get("location", ""))
    story_state.setdefault("relationship_shift", "")
    story_state.setdefault("latest_reveal", "")
    story_state.setdefault("emotional_beat", current_scene.get("emotional_tone", ""))

    acts = story_data.get("acts") or []
    current_act_index = min(max(story_data.get("current_act", 0), 0), max(len(acts) - 1, 0)) if acts else 0
    current_act = acts[current_act_index] if acts and current_act_index < len(acts) else {}
    story_data["story_progress"] = {
        "current_act_index": current_act_index,
        "act_count": len(acts),
        "current_act_title": current_act.get("title", ""),
        "current_act_purpose": current_act.get("purpose", ""),
        "scene_location": current_scene.get("location", ""),
    }

    story_data["scene_info_panel"] = {
        "recap": story_memory.get("what_just_happened", ""),
        "scene_location": current_scene.get("location", ""),
        "objective": story_state.get("current_objective", ""),
        "current_tension": story_state.get("current_tension", ""),
        "immediate_stakes": story_state.get("immediate_stakes", ""),
        "location_status": story_state.get("location_status", ""),
        "clue_summary": story_memory.get("active_clues", []),
        "tension_summary": story_memory.get("open_tensions", []),
    }

    story_data["cast_statuses"] = [
        {
            "character_id": character.get("id", ""),
            "name": character.get("name", ""),
            "role": character.get("role", ""),
            "relationship": character.get("relationship") or character.get("relationship_to_protagonist", ""),
            "current_status": _recent_character_line(character.get("id", ""))[:180],
            "last_seen": _recent_character_line(character.get("id", ""))[:180],
            "in_scene_now": character.get("id", "") in in_scene_character_ids,
        }
        for character in story_data.get("characters", [])
        if character.get("id")
    ]

    summaries = story_data.get("interactive_element_summaries", []) or []
    novelty_tags = story_data.get("interactive_element_tags", []) or []
    similarity_scores = story_data.get("interactive_element_similarity_scores", []) or []
    story_data["interactive_element_history"] = [
        {
            "summary": summaries[idx] if idx < len(summaries) else "",
            "novelty_tags": novelty_tags[idx] if idx < len(novelty_tags) and isinstance(novelty_tags[idx], list) else [],
            "similarity_score": similarity_scores[idx] if idx < len(similarity_scores) else 0.0,
        }
        for idx in range(max(len(summaries), len(novelty_tags)))
    ][-6:]

    if "hidden_elements" not in current_scene:
        current_scene["hidden_elements"] = story_data.get("hidden_elements", {})
    if not isinstance(current_scene.get("scene_elements"), dict):
        current_scene["scene_elements"] = {}
    if not isinstance(current_scene.get("scene_dynamics"), dict):
        current_scene["scene_dynamics"] = {}
    current_scene.setdefault("location", current_scene.get("setting", ""))
    if not isinstance(current_scene.get("story_state"), dict):
        current_scene["story_state"] = dict(story_state)
    return story_data

async def critique_and_refine_story(story_id: str, story_data: dict) -> dict:
    """
    Use a critic LLM to evaluate the story blueprint on novelty, engagement,
    cinematic quality, etc., then use a refiner LLM to polish the story based
    on the critic's feedback.  Called after step 4 generates the act structure.

    Returns the (potentially updated) story_data dict.  On any failure the
    original data is returned unchanged so the pipeline is never blocked.
    """
    setting_str = json.dumps(story_data.get("setting", {}), indent=2)
    characters_str = json.dumps(story_data.get("characters", []), indent=2)
    acts_str = json.dumps(story_data.get("acts", []), indent=2)

    # ── Phase 1: Critic evaluation ──
    critic_prompt = prompt_templates.STORY_CRITIC_PROMPT.format(
        title=story_data.get("title", ""),
        high_concept_premise=story_data.get("high_concept_premise", ""),
        cinematic_theme=story_data.get("cinematic_theme", ""),
        emotional_undercurrent=story_data.get("emotional_undercurrent", ""),
        setting=setting_str,
        characters=characters_str,
        acts=acts_str,
    )

    critic_messages = [
        {"role": "system", "content": "You are a demanding but constructive story critic. Be specific and actionable. Respond only with JSON."},
        {"role": "user", "content": critic_prompt},
    ]

    logger.info(f"[Story Critic] Evaluating story blueprint for {story_id}")
    critic_response = await run_llm_completion(
        messages=critic_messages,
        model=resolve_model_for_task("story", story=story_data),
        trace_context=build_llm_trace_context(
            "story_step4_critic",
            "story",
            story=story_data,
            story_id=story_id,
        ),
    )

    if critic_response.get("error"):
        logger.warning(f"[Story Critic] LLM call failed: {critic_response['error']}")
        return story_data

    try:
        critic_content = extract_json_from_response(critic_response["content"])
        critic_data = json.loads(critic_content)
        overall_score = critic_data.get("overall_score", 10)
        logger.info(f"[Story Critic] Overall score: {overall_score}/10 for story {story_id}")
        for dim, info in critic_data.get("dimensions", {}).items():
            logger.info(f"[Story Critic]   {dim}: {info.get('score', '?')}/10 — {info.get('feedback', '')[:80]}")
    except Exception as e:
        logger.warning(f"[Story Critic] Failed to parse critic response: {e}")
        return story_data

    story_data["critic_evaluation"] = critic_data

    # ── Phase 2: Refine based on critic feedback ──
    refine_prompt = prompt_templates.STORY_REFINE_PROMPT.format(
        title=story_data.get("title", ""),
        high_concept_premise=story_data.get("high_concept_premise", ""),
        cinematic_theme=story_data.get("cinematic_theme", ""),
        emotional_undercurrent=story_data.get("emotional_undercurrent", ""),
        setting=setting_str,
        characters=characters_str,
        acts=acts_str,
        critic_feedback=json.dumps(critic_data, indent=2),
    )

    refine_messages = [
        {"role": "system", "content": "You are a master screenwriter. Refine the story to address the critic's feedback. Respond only with JSON."},
        {"role": "user", "content": refine_prompt},
    ]

    logger.info(f"[Story Refine] Refining story blueprint for {story_id}")
    refine_response = await run_llm_completion(
        messages=refine_messages,
        model=resolve_model_for_task("story", story=story_data),
        trace_context=build_llm_trace_context(
            "story_step4_refiner",
            "story",
            story=story_data,
            story_id=story_id,
        ),
    )

    if refine_response.get("error"):
        logger.warning(f"[Story Refine] LLM call failed: {refine_response['error']}")
        return story_data

    try:
        refine_content = extract_json_from_response(refine_response["content"])
        refined_data = json.loads(refine_content)
    except Exception as e:
        logger.warning(f"[Story Refine] Failed to parse refine response: {e}")
        return story_data

    # ── Apply refinements ──
    if refined_data.get("refined_high_concept_premise"):
        story_data["high_concept_premise"] = refined_data["refined_high_concept_premise"]
    if refined_data.get("refined_cinematic_theme"):
        story_data["cinematic_theme"] = refined_data["refined_cinematic_theme"]
    if refined_data.get("refined_acts") and isinstance(refined_data["refined_acts"], list):
        story_data["acts"] = refined_data["refined_acts"]
    if refined_data.get("refinement_notes"):
        story_data["refinement_notes"] = refined_data["refinement_notes"]

    logger.info(
        f"[Story Refine] Successfully refined story {story_id}. "
        f"Notes: {refined_data.get('refinement_notes', '')[:120]}"
    )
    return story_data


@app.post("/story/create/step4", response_model=StoryStep4Response)
async def create_story_step4(input: StoryStep4Input):
    """
    步骤4: 故事结构 - 创建故事的分幕结构
    """
    story_id = input.story_id
    
    # 检查story_id是否存在
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story_data = stories_db[story_id]
    
    # 检查前一步是否完成
    if "characters" not in story_data:
        raise HTTPException(status_code=400, detail="Step 3 must be completed first")
    
    # 更新故事状态
    story_data["current_step"] = 4
    
    # 准备提示词
    prompt = prompt_templates.STORY_STEP4_PROMPT.format(
        title=story_data.get("title", ""),
        high_concept_premise=story_data.get("high_concept_premise", ""),
        cinematic_theme=story_data.get("cinematic_theme", ""),
        emotional_undercurrent=story_data.get("emotional_undercurrent", ""),
        setting=json.dumps(story_data.get("setting", {}), indent=2),
        characters=json.dumps(story_data.get("characters", []), indent=2)
    )
    
    messages = [
        {"role": "system", "content": prompt_templates.SYSTEM_PROMPT}, 
        {"role": "user", "content": f"Please generate the story structure based on this prompt:\n\n{prompt}\n\nThe response must be a valid JSON array matching this schema: {prompt_templates.STORY_STEP4_SCHEMA}"}
    ]

    # 调用LLM
    logger.info(f"Step 4: Generating acts for story {story_id}")
    response = await run_llm_completion(
        messages=messages,
        model=resolve_model_for_task("story", story=story_data),
        trace_context=build_llm_trace_context(
            "story_step4",
            "story",
            story=story_data,
            story_id=story_id,
        ),
    )

    if response["error"]:
        raise HTTPException(status_code=500, detail=response["error"])
    
    # 解析响应
    try:
        content_to_parse = extract_json_from_response(response["content"])
        acts = json.loads(content_to_parse)
        logger.info(f"Successfully generated acts for {story_id}")
    except (ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse LLM response: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate valid acts")
    
    # 验证分幕数据
    if not isinstance(acts, list):
        raise HTTPException(status_code=500, detail="Invalid acts format")
    
    # 保存到故事数据
    story_data["acts"] = acts
    story_data["current_act"] = 0

    # ── Critic + Refine: evaluate and polish the full story blueprint ──
    if settings.ENABLE_STORY_BLUEPRINT_REVIEW:
        try:
            story_data = await critique_and_refine_story(story_id, story_data)
            stories_db[story_id] = story_data
            acts = story_data["acts"]
            logger.info(f"[Step 4] Critic+Refine completed for story {story_id}")
        except Exception as e:
            logger.error(f"[Step 4] Critic+Refine failed (non-blocking): {e}")
    else:
        logger.info(f"[Step 4] Critic+Refine skipped for story {story_id} (disabled)")

    experiment_store.log_story_event(
        event_type="story_step4_completed",
        story_id=story_id,
        session_id=story_data.get("session_id"),
        participant_id=story_data.get("participant_id"),
        payload=make_json_safe(
            {
                "request": {
                    "title": story_data.get("title"),
                    "setting": story_data.get("setting"),
                    "characters": story_data.get("characters", []),
                },
                "response": {
                    "acts": acts,
                    "critic_evaluation": story_data.get("critic_evaluation"),
                },
            }
        ),
    )
    
    return StoryStep4Response(
        story_id=story_id,
        acts=acts
    )

@app.post("/story/create/step5", response_model=StoryStep5Response)
async def create_story_step5(input: StoryStep5Input):
    """
    步骤5: 开场和互动元素 - 创建故事的开场和互动选择
    """
    story_id = input.story_id
    
    # 检查story_id是否存在
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story_data = stories_db[story_id]
    
    # 检查前一步是否完成
    if "acts" not in story_data:
        raise HTTPException(status_code=400, detail="Step 4 must be completed first")
    
    # 更新故事状态
    story_data["current_step"] = 5
    
    # 准备提示词
    prompt = prompt_templates.STORY_STEP5_PROMPT.format(
        title=story_data.get("title", ""),
        high_concept_premise=story_data.get("high_concept_premise", ""),
        cinematic_theme=story_data.get("cinematic_theme", ""),
        emotional_undercurrent=story_data.get("emotional_undercurrent", ""),
        setting=json.dumps(story_data.get("setting", {}), indent=2),
        characters=json.dumps(story_data.get("characters", []), indent=2),
        acts=json.dumps(story_data.get("acts", []), indent=2)
    )
    
    messages = [
        {"role": "system", "content": prompt_templates.SYSTEM_PROMPT}, 
        {"role": "user", "content": f"Please generate the opening and interactive elements based on this prompt:\n\n{prompt}\n\nThe response must be a valid JSON object matching this schema: {prompt_templates.STORY_STEP5_SCHEMA}"}
    ]

    # 调用LLM
    logger.info(f"Step 5: Generating opening and interactive elements for story {story_id}")
    response = await run_llm_completion(
        messages=messages,
        model=resolve_model_for_task("story", story=story_data),
        trace_context=build_llm_trace_context(
            "story_step5",
            "story",
            story=story_data,
            story_id=story_id,
        ),
    )

    if response["error"]:
        raise HTTPException(status_code=500, detail=response["error"])
    
    # 解析响应
    try:
        content_to_parse = extract_json_from_response(response["content"])
        interactive_elements = json.loads(content_to_parse)
        logger.info(f"Successfully generated interactive elements for {story_id}")
    except (ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse LLM response: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate valid interactive elements")
    
    # 保存到故事数据
    opening_sequence = interactive_elements.get("opening_sequence", {})
    initial_dialogue = interactive_elements.get("initial_dialogue", [])
    branching_choices = interactive_elements.get("branching_choices", [])
    hidden_elements = interactive_elements.get("hidden_elements", [])
    
    # 确保初始对话中每个消息都有ID
    for message in initial_dialogue:
        if not message.get("id"):
            message["id"] = f"msg-{uuid.uuid4()}"
        if not message.get("type"):
            message["type"] = "text"
    
    # 创建初始场景
    initial_scene = {
        "id": str(uuid.uuid4()),
        "description": opening_sequence.get("description"),
        "location": opening_sequence.get("location"),
        "mood": opening_sequence.get("mood"),
        "inciting_incident": opening_sequence.get("inciting_incident", ""),
        "messages": initial_dialogue,
        "choices": branching_choices,
    }
    
    # ---------------- Scene Background Image Generation ----------------
    scene_prompt = opening_sequence.get("description", "") or ""
    if False:
        try:
            from pathlib import Path
            from src.meta_planner import generate_image

            scene_prompt: str = opening_sequence.get("description", "") or ""
            if scene_prompt.strip():
                image_dir = Path(f"images/scenes/{story_id}")
                image_dir.mkdir(parents=True, exist_ok=True)
                image_path = image_dir / "scene0.png"

                gen_result = await generate_image(
                    prompt=scene_prompt,
                    output_path=str(image_path),
                    api_provider=settings.IMAGE_API_PROVIDER,
                    model="gemini-2.5-flash-image-preview" if settings.IMAGE_API_PROVIDER == "gemini" else "gpt-image-1",
                    size="1792x1024",
                    quality="medium",
                )

                if gen_result.get("success"):
                    relative_path = f"images/scenes/{story_id}/scene0.png"
                    initial_scene["backgroundImage"] = relative_path
                    logger.info(f"Background image generated for story {story_id}")
                else:
                    logger.warning(f"Failed to generate background image for story {story_id}: {gen_result.get('error')}")
        except Exception as e:
            logger.error(f"Error generating background image for story {story_id}: {e}")
    elif not _image_api_key_available():
        logger.info(f"[Scene Image] No image API key configured — skipping background generation for story {story_id}")
    
    # 更新故事数据
    story_data.update({
        "status": "active",
        "opening_sequence": opening_sequence,
        "current_scene": initial_scene,
        "previous_scenes": [],
        "hidden_elements": hidden_elements,
    })
    
    # 应用标准化
    story_data = standardize_story_response(story_data)
    stories_db[story_id] = story_data
    if _image_api_key_available() and scene_prompt.strip():
        asyncio.create_task(_generate_scene_background_image(story_id, scene_prompt))
    experiment_store.log_story_event(
        event_type="story_step5_completed",
        story_id=story_id,
        session_id=story_data.get("session_id"),
        participant_id=story_data.get("participant_id"),
        payload=make_json_safe(
            {
                "request": {
                    "title": story_data.get("title"),
                    "setting": story_data.get("setting"),
                    "characters": story_data.get("characters", []),
                    "acts": story_data.get("acts", []),
                },
                "response": {
                    "opening_sequence": opening_sequence,
                    "initial_dialogue": initial_dialogue,
                    "branching_choices": branching_choices,
                    "hidden_elements": hidden_elements,
                },
            }
        ),
    )
    
    # 初始化故事在上下文管理器中
    user_id = story_data.get("user_id")
    if user_id and story_data.get("title"):
        context_manager.initialize_story(
            user_id=user_id,
            story_id=story_id,
            title=story_data.get("title", ""),
            theme=story_data.get("cinematic_theme", ""),
            setting=story_data.get("setting", {}),
            emotional_goal=story_data.get("emotional_undercurrent", ""),
            characters=story_data.get("characters", [])
        )
        
        # 添加初始对话到上下文
        if story_id in context_manager.story_states:
            state = context_manager.story_states[story_id]
            for message in initial_dialogue:
                state.add_message(
                    character_id=message.get("character_id", ""),
                    content=message.get("content", ""),
                    message_type=message.get("type", "text")
                )
    
    await _save_story_snapshot_locally(story_id, story_data)

    experiment_store.log_story_event(
        event_type="story_completed_generation",
        story_id=story_id,
        session_id=story_data.get("session_id"),
        participant_id=story_data.get("participant_id"),
        payload=make_json_safe(
            {
                "title": story_data.get("title"),
                "status": story_data.get("status"),
                "final_story_snapshot": story_data,
            }
        ),
    )
    
    return StoryStep5Response(
        story_id=story_id,
        opening_sequence=opening_sequence,
        initial_dialogue=initial_dialogue,
        branching_choices=branching_choices,
        hidden_elements=hidden_elements
    )

@app.get("/story/progress/{story_id}")
async def get_story_progress(story_id: str):
    """
    获取故事生成的进度
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story_data = stories_db[story_id]
    current_step = story_data.get("current_step", 0)

    generation_complete = bool(story_data.get("current_scene")) and story_data.get("status") == "active"

    # Only report 100% once step 5 has actually finished and the opening scene exists.
    progress = 0
    if current_step == 1:
        progress = 20
    elif current_step == 2:
        progress = 40
    elif current_step == 3:
        progress = 60
    elif current_step == 4:
        progress = 80
    elif current_step >= 5:
        progress = 100 if generation_complete else 90

    raw_status = story_data.get("status", "pending")
    if generation_complete:
        normalized_status = "done"
    elif current_step > 0 or raw_status in {"in_progress", "active"}:
        normalized_status = "running"
    elif raw_status == "error":
        normalized_status = "error"
    else:
        normalized_status = "pending"

    return {
        "story_id": story_id,
        "current_step": current_step,
        "progress": progress,
        "status": normalized_status,
    }

@app.post("/story/complete/{story_id}", response_model=StoryResponse)
async def complete_story(story_id: str):
    """
    完成分步骤生成后，返回完整的故事数据
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story_data = stories_db[story_id]
    
    # 检查所有步骤是否完成
    if "current_scene" not in story_data:
        raise HTTPException(status_code=400, detail="Story generation is not complete")
    
    # 应用角色ID修复和标准化
    story_data = standardize_story_response(story_data)
    story_data = attach_story_runtime_metadata(story_id, story_data)
    stories_db[story_id] = story_data
    
    await _save_story_snapshot_locally(story_id, story_data)
    
    return story_data

_END_STORY_PATTERN = re.compile(
    r"\b("
    r"end\s*(the\s*)?story|stop\s*(the\s*)?story|finish\s*(the\s*)?story|"
    r"quit\s*(the\s*)?story|exit\s*(the\s*)?story|"
    r"i\s*want\s*to\s*(end|stop|finish|quit)\s*(the\s*)?(story|game|this)|"
    r"let'?s?\s*(end|stop|finish)\s*(the\s*)?(story|game|this|here)|"
    r"结束故事|停止故事|退出故事"
    r")\b",
    re.IGNORECASE,
)


def _user_wants_to_end(text: str) -> bool:
    """Return True if the user's message signals intent to end the story."""
    return bool(_END_STORY_PATTERN.search(text))


@app.post("/messages")
async def send_message(input: MessageInput):
    """
    发送消息并推进故事
    """
    story_id = input.story_id
    
    if story_id not in stories_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    
    story = stories_db[story_id]
    session = get_story_session(story)
    profile = get_story_speed_profile(story=story, session=session)
    
    if story["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Story is not active")

    # Auto-end: if the user explicitly asks to end the story, trigger conclusion
    if _user_wants_to_end(input.content):
        logger.info(f"[Auto-End] User requested story end via message: {input.content!r}")
        await end_story(story_id)
        stories_db[story_id] = attach_story_runtime_metadata(story_id, stories_db[story_id])
        return stories_db[story_id]
    if input.session_id and not story.get("session_id"):
        story["session_id"] = input.session_id
    if input.participant_id and not story.get("participant_id"):
        story["participant_id"] = input.participant_id
    _, profile = get_story_speed_context(story)
    previous_message_count = len(story.get("current_scene", {}).get("messages", []))
    started_at = time.perf_counter()
    
    # 获取反思数据（如果有）
    reflection = None
    ui_element_generated = False
    
    if input.with_reflection and not profile.skip_optional_llm:
        try:
            # 获取反思
            reflection_request = {"request_type": "story_advancement"}
            reflection_response = await generate_reflection(story_id, reflection_request)
            reflection = reflection_response.get("reflection", {})
            logger.info(f"Generated reflection for story advancement: {reflection}")

            # 如果反思建议需要UI元素，则尝试预生成（不插入消息，前端控制展示时机）
            ui_info = reflection_response.get("ui_element", {})
            if ui_info.get("needed") and not ui_element_generated:
                element_type = ui_info.get("element_type") or "generic"
                element_desc = ui_info.get("description") or "Interactive story element"
                element_result = await generate_interactive_element(
                    element_type=element_type,
                    element_description=element_desc,
                    content_details="Auto-generated via reflection",
                    story_context=story
                )
                
                # 不将交互元素直接写入消息，交由前端按时机插入
                if element_result.get("success"):
                    ui_element_generated = True
                    logger.info("Pre-generated interactive UI element; frontend will display after dialogue")
        except Exception as e:
            logger.error(f"Failed to generate reflection or UI element: {e}")
    
    # 使用反思数据增强故事生成（如果有的话）
    user_reflection = None
    pacing_data = None
    if (input.with_reflection or input.reflection) and not profile.skip_optional_llm:
        if input.reflection:
            user_reflection = input.reflection
            logger.info(f"Using client-provided reflection data for story advancement")
        else:
            # 生成反思数据
            reflection_request = {
                "user_input": input.content
            }
            reflection_response = await generate_reflection(story_id, reflection_request)
            if reflection_response.get("success", False):
                user_reflection = reflection_response.get("reflection", {})
                # 添加pacing信息到反思数据中
                if not user_reflection.get("pacing_data") and "pacing_level" in reflection_response:
                    pacing_data = {
                        "level": reflection_response.get("pacing_level", 0),
                        "description": reflection_response.get("pacing_description", ""),
                        "dialogue_count": reflection_response.get("dialogue_count", 0)
                    }
                    # 深拷贝以避免修改原始对象
                    import copy
                    user_reflection = copy.deepcopy(user_reflection)
                    user_reflection["pacing_data"] = pacing_data
                logger.info(f"Using server-generated reflection data for story advancement with pacing level {pacing_data.get('level', 'unknown') if pacing_data else 'unknown'}")
    
    # 如果 fast_forward 为 True，则在上下文中设置强制推进标志
    try:
        if get_effective_fast_forward(story, getattr(input, "fast_forward", False)) and story_id in context_manager.story_states:
            context_manager.story_states[story_id].force_advance = True
            logger.info(f"[Fast Forward] User requested fast-forward for story {story_id}")
    except Exception as e:
        logger.error(f"[Fast Forward] Failed to set fast-forward flag: {e}")

    try:
        maybe_start_conclusion_countdown(story)
    except Exception as e:
        logger.error(f"[Endpoint Countdown] Error evaluating countdown start: {e}")

    # 推进故事
    try:
        updated_scene = await advance_story(
            story_id=story_id,
            user_input=input.content,
            action_type="Message",
            context_manager=context_manager,
            stories_db=stories_db,
            reflection=user_reflection
        )
        
        # 应用角色ID修复和标准化
        stories_db[story_id] = standardize_story_response(stories_db[story_id])
        stories_db[story_id] = attach_story_runtime_metadata(story_id, stories_db[story_id])
        turn_generation_meta = {
            "generation_mode": stories_db[story_id].get("generation_mode"),
            "state_freshness": stories_db[story_id].get("state_freshness"),
            "state_patch_scheduled": bool(stories_db[story_id].get("_benchmark_state_patch_scheduled")),
        }

        response_messages = extract_response_messages(stories_db[story_id], previous_message_count)
        log_turn_if_needed(
            story=stories_db[story_id],
            action_type="message",
            user_input=input.content,
            response_messages=response_messages,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            extra_metadata={
                "with_reflection": bool(input.with_reflection or input.reflection),
                "reflection_used": bool(user_reflection),
                "interactive_used": bool(ui_element_generated),
                "benchmark_speed_profile": profile.benchmark_speed_profile,
                **turn_generation_meta,
            },
        )
        if stories_db[story_id].get("status") == "completed":
            log_completed_story_snapshot(
                event_type="story_turn_completed",
                story_id=story_id,
                story=stories_db[story_id],
                extra_payload={"user_input": input.content},
            )
        
        return stories_db[story_id]
    except Exception as e:
        logger.error(f"Error advancing story with message: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/messages/stream")
async def stream_story_message(input: MessageInput):
    """
    流式版本的 /messages 端点，通过 SSE 实时推送 NPC 对话字符。
    事件格式:
      data: {"type": "delta", "text": "..."}   — 对话片段
      data: {"type": "done",  "story": {...}}   — 故事最终状态
      data: {"type": "error", "message": "..."}  — 错误信息
    """
    story_id = input.story_id

    if story_id not in stories_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")

    story = stories_db[story_id]
    if story["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Story is not active")

    # Auto-end: if the user explicitly asks to end the story, return a done event immediately
    if _user_wants_to_end(input.content):
        logger.info(f"[Auto-End/Stream] User requested story end via message: {input.content!r}")
        await end_story(story_id)
        completed_story = attach_story_runtime_metadata(story_id, stories_db.get(story_id, {}))

        async def _end_events():
            payload = json.dumps({"type": "done", "story": completed_story}, default=str)
            yield f"data: {payload}\n\n"

        return StreamingResponse(_end_events(), media_type="text/event-stream")

    if input.session_id and not story.get("session_id"):
        story["session_id"] = input.session_id
    if input.participant_id and not story.get("participant_id"):
        story["participant_id"] = input.participant_id
    _, profile = get_story_speed_context(story)
    previous_message_count = len(story.get("current_scene", {}).get("messages", []))
    started_at = time.perf_counter()

    # 设置快进标志
    try:
        if get_effective_fast_forward(story, getattr(input, "fast_forward", False)) and story_id in context_manager.story_states:
            context_manager.story_states[story_id].force_advance = True
    except Exception:
        pass

    try:
        maybe_start_conclusion_countdown(story)
    except Exception:
        pass

    streaming_queue: asyncio.Queue = asyncio.Queue()

    async def _run_advance():
        try:
            await advance_story(
                story_id=story_id,
                user_input=input.content,
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
                reflection=getattr(input, "reflection", None),
                streaming_queue=streaming_queue,
            )
            stories_db[story_id] = standardize_story_response(stories_db[story_id])
            stories_db[story_id] = attach_story_runtime_metadata(story_id, stories_db[story_id])
            turn_generation_meta = {
                "generation_mode": stories_db[story_id].get("generation_mode"),
                "state_freshness": stories_db[story_id].get("state_freshness"),
                "state_patch_scheduled": bool(stories_db[story_id].get("_benchmark_state_patch_scheduled")),
            }
            response_messages = extract_response_messages(stories_db[story_id], previous_message_count)
            log_turn_if_needed(
                story=stories_db[story_id],
                action_type="message_stream",
                user_input=input.content,
                response_messages=response_messages,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                extra_metadata={
                    "streaming": True,
                    "reflection_used": False,
                    "interactive_used": False,
                    "benchmark_speed_profile": profile.benchmark_speed_profile,
                    **turn_generation_meta,
                },
            )
            if stories_db[story_id].get("status") == "completed":
                log_completed_story_snapshot(
                    event_type="story_turn_completed",
                    story_id=story_id,
                    story=stories_db[story_id],
                    extra_payload={"user_input": input.content, "streaming": True},
                )
            await streaming_queue.put({"type": "done", "story": stories_db[story_id]})
        except Exception as exc:
            logger.error(f"[stream] advance_story error: {exc}")
            await streaming_queue.put({"type": "error", "message": str(exc)})

    asyncio.create_task(_run_advance())

    async def _event_generator():
        while True:
            try:
                event = await asyncio.wait_for(streaming_queue.get(), timeout=90.0)
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield 'data: {"type": "error", "message": "timeout"}\n\n'
                break

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "http://localhost:3000",
        },
    )


@app.post("/choices")
async def select_choice(input: ChoiceInput):
    """
    选择一个选项并推进故事
    """
    story_id = input.story_id
    choice_id = input.choice_id
    
    if story_id not in stories_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    
    story = stories_db[story_id]
    
    if story["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Story is not active")
    if input.session_id and not story.get("session_id"):
        story["session_id"] = input.session_id
    if input.participant_id and not story.get("participant_id"):
        story["participant_id"] = input.participant_id
    _, profile = get_story_speed_context(story)
    previous_message_count = len(story.get("current_scene", {}).get("messages", []))
    started_at = time.perf_counter()
    
    # 验证选项ID
    choice_text = None
    for choice in story["current_scene"]["choices"]:
        if choice["id"] == choice_id:
            choice_text = choice["text"]
            break
    
    if not choice_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid choice ID")
    
    # 使用反思数据增强故事生成（如果有的话）
    user_reflection = None
    pacing_data = None
    if (input.with_reflection or input.reflection) and not profile.skip_optional_llm:
        if input.reflection:
            user_reflection = input.reflection
            logger.info(f"Using client-provided reflection data for choice advancement")
        else:
            # 生成反思数据
            reflection_request = {
                "user_input": choice_text
            }
            reflection_response = await generate_reflection(story_id, reflection_request)
            if reflection_response.get("success", False):
                user_reflection = reflection_response.get("reflection", {})
                # 添加pacing信息到反思数据中
                if not user_reflection.get("pacing_data") and "pacing_level" in reflection_response:
                    pacing_data = {
                        "level": reflection_response.get("pacing_level", 0),
                        "description": reflection_response.get("pacing_description", ""),
                        "dialogue_count": reflection_response.get("dialogue_count", 0)
                    }
                    # 深拷贝以避免修改原始对象
                    import copy
                    user_reflection = copy.deepcopy(user_reflection)
                    user_reflection["pacing_data"] = pacing_data
                logger.info(f"Using server-generated reflection data for choice advancement with pacing level {pacing_data.get('level', 'unknown') if pacing_data else 'unknown'}")
    
    # 如果 fast_forward 为 True，则在上下文中设置强制推进标志
    try:
        if get_effective_fast_forward(story, getattr(input, "fast_forward", False)) and story_id in context_manager.story_states:
            context_manager.story_states[story_id].force_advance = True
            logger.info(f"[Fast Forward] User requested fast-forward for story {story_id} (choice)")
    except Exception as e:
        logger.error(f"[Fast Forward] Failed to set fast-forward flag for choice: {e}")

    try:
        maybe_start_conclusion_countdown(story)
    except Exception as e:
        logger.error(f"[Endpoint Countdown] Error evaluating countdown start (choice): {e}")

    # 若选择为“立即结尾”类选项，直接完成
    if choice_text and choice_text.strip().lower() == "end the story now":
        state = context_manager.story_states.get(story_id)
        if profile.benchmark_speed_profile and not can_offer_end_story_choice(
            story,
            getattr(state, "conclusion_countdown", story.get("conclusion_countdown", 0)),
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ending is not available yet")
        story["status"] = "completed"
        if story.get("session_id"):
            experiment_store.complete_session(story["session_id"], metadata={"ended_via_choice": True})
        logger.info(f"[Endpoint End] Story {story_id} completed via explicit end choice")
        stories_db[story_id] = attach_story_runtime_metadata(story_id, stories_db[story_id])
        log_completed_story_snapshot(
            event_type="story_ended",
            story_id=story_id,
            story=stories_db[story_id],
            extra_payload={"message": "Story completed via explicit end choice."},
        )
        return stories_db[story_id]

    # 推进故事
    try:
        updated_scene = await advance_story(
            story_id=story_id,
            user_input=choice_text,
            action_type="Choice",
            context_manager=context_manager,
            stories_db=stories_db,
            reflection=user_reflection
        )
        
        # 应用角色ID修复和标准化
        stories_db[story_id] = standardize_story_response(stories_db[story_id])
        stories_db[story_id] = attach_story_runtime_metadata(story_id, stories_db[story_id])
        turn_generation_meta = {
            "generation_mode": stories_db[story_id].get("generation_mode"),
            "state_freshness": stories_db[story_id].get("state_freshness"),
            "state_patch_scheduled": bool(stories_db[story_id].get("_benchmark_state_patch_scheduled")),
        }

        response_messages = extract_response_messages(stories_db[story_id], previous_message_count)
        log_turn_if_needed(
            story=stories_db[story_id],
            action_type="choice",
            user_input=choice_text,
            response_messages=response_messages,
            choice_id=choice_id,
            choice_text=choice_text,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            extra_metadata={
                "with_reflection": bool(input.with_reflection or input.reflection),
                "reflection_used": bool(user_reflection),
                "interactive_used": False,
                "benchmark_speed_profile": profile.benchmark_speed_profile,
                **turn_generation_meta,
            },
        )
        if stories_db[story_id].get("status") == "completed":
            log_completed_story_snapshot(
                event_type="story_choice_completed",
                story_id=story_id,
                story=stories_db[story_id],
                extra_payload={"choice_id": choice_id, "choice_text": choice_text},
            )
        
        return stories_db[story_id]
    except Exception as e:
        logger.error(f"Error advancing story with choice: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/choices/stream")
async def stream_story_choice(input: ChoiceInput):
    """
    流式版本的 /choices 端点，通过 SSE 实时推送 NPC 对话片段。
    事件格式:
      data: {"type": "delta", "text": "..."}   — 对话片段
      data: {"type": "done",  "story": {...}}   — 故事最终状态
      data: {"type": "error", "message": "..."}  — 错误信息
    """
    story_id = input.story_id
    choice_id = input.choice_id

    if story_id not in stories_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")

    story = stories_db[story_id]

    if story["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Story is not active")

    if input.session_id and not story.get("session_id"):
        story["session_id"] = input.session_id
    if input.participant_id and not story.get("participant_id"):
        story["participant_id"] = input.participant_id
    _, profile = get_story_speed_context(story)
    previous_message_count = len(story.get("current_scene", {}).get("messages", []))
    started_at = time.perf_counter()

    choice_text = None
    for choice in story["current_scene"]["choices"]:
        if choice["id"] == choice_id:
            choice_text = choice["text"]
            break

    if not choice_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid choice ID")

    user_reflection = None
    pacing_data = None
    if (input.with_reflection or input.reflection) and not profile.skip_optional_llm:
        if input.reflection:
            user_reflection = input.reflection
            logger.info("Using client-provided reflection data for streaming choice advancement")
        else:
            reflection_request = {
                "user_input": choice_text
            }
            reflection_response = await generate_reflection(story_id, reflection_request)
            if reflection_response.get("success", False):
                user_reflection = reflection_response.get("reflection", {})
                if not user_reflection.get("pacing_data") and "pacing_level" in reflection_response:
                    pacing_data = {
                        "level": reflection_response.get("pacing_level", 0),
                        "description": reflection_response.get("pacing_description", ""),
                        "dialogue_count": reflection_response.get("dialogue_count", 0)
                    }
                    import copy
                    user_reflection = copy.deepcopy(user_reflection)
                    user_reflection["pacing_data"] = pacing_data
                logger.info(
                    "Using server-generated reflection data for streaming choice advancement with pacing level %s",
                    pacing_data.get("level", "unknown") if pacing_data else "unknown",
                )

    try:
        if get_effective_fast_forward(story, getattr(input, "fast_forward", False)) and story_id in context_manager.story_states:
            context_manager.story_states[story_id].force_advance = True
            logger.info(f"[Fast Forward] User requested fast-forward for story {story_id} (choice stream)")
    except Exception as e:
        logger.error(f"[Fast Forward] Failed to set fast-forward flag for streaming choice: {e}")

    try:
        maybe_start_conclusion_countdown(story)
    except Exception as e:
        logger.error(f"[Endpoint Countdown] Error evaluating countdown start (choice stream): {e}")

    if choice_text and choice_text.strip().lower() == "end the story now":
        state = context_manager.story_states.get(story_id)
        if profile.benchmark_speed_profile and not can_offer_end_story_choice(
            story,
            getattr(state, "conclusion_countdown", story.get("conclusion_countdown", 0)),
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ending is not available yet")
        story["status"] = "completed"
        if story.get("session_id"):
            experiment_store.complete_session(story["session_id"], metadata={"ended_via_choice": True, "streaming": True})
        logger.info(f"[Endpoint End] Story {story_id} completed via explicit end choice (stream)")
        stories_db[story_id] = attach_story_runtime_metadata(story_id, stories_db[story_id])

        async def _end_events():
            payload = json.dumps({"type": "done", "story": stories_db[story_id]}, default=str)
            yield f"data: {payload}\n\n"

        return StreamingResponse(_end_events(), media_type="text/event-stream")

    streaming_queue: asyncio.Queue = asyncio.Queue()

    async def _run_advance():
        try:
            await advance_story(
                story_id=story_id,
                user_input=choice_text,
                action_type="Choice",
                context_manager=context_manager,
                stories_db=stories_db,
                reflection=user_reflection,
                streaming_queue=streaming_queue,
            )
            stories_db[story_id] = standardize_story_response(stories_db[story_id])
            stories_db[story_id] = attach_story_runtime_metadata(story_id, stories_db[story_id])
            turn_generation_meta = {
                "generation_mode": stories_db[story_id].get("generation_mode"),
                "state_freshness": stories_db[story_id].get("state_freshness"),
                "state_patch_scheduled": bool(stories_db[story_id].get("_benchmark_state_patch_scheduled")),
            }
            response_messages = extract_response_messages(stories_db[story_id], previous_message_count)
            log_turn_if_needed(
                story=stories_db[story_id],
                action_type="choice_stream",
                user_input=choice_text,
                response_messages=response_messages,
                choice_id=choice_id,
                choice_text=choice_text,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                extra_metadata={
                    "streaming": True,
                    "with_reflection": bool(input.with_reflection or input.reflection),
                    "reflection_used": bool(user_reflection),
                    "interactive_used": False,
                    "benchmark_speed_profile": profile.benchmark_speed_profile,
                    **turn_generation_meta,
                },
            )
            if stories_db[story_id].get("status") == "completed":
                log_completed_story_snapshot(
                    event_type="story_choice_completed",
                    story_id=story_id,
                    story=stories_db[story_id],
                    extra_payload={"choice_id": choice_id, "choice_text": choice_text, "streaming": True},
                )
            await streaming_queue.put({"type": "done", "story": stories_db[story_id]})
        except Exception as exc:
            logger.error(f"[choice-stream] advance_story error: {exc}")
            await streaming_queue.put({"type": "error", "message": str(exc)})

    asyncio.create_task(_run_advance())

    async def _event_generator():
        while True:
            try:
                event = await asyncio.wait_for(streaming_queue.get(), timeout=90.0)
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield 'data: {"type": "error", "message": "timeout"}\n\n'
                break

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "http://localhost:3000",
        },
    )

@app.post("/stories/{story_id}/end")
async def end_story(story_id: str):
    """
    End a story and provide a conclusion based on the enhanced act structure.
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story = stories_db[story_id]
    
    # Get the final act to inform the conclusion
    acts = story.get("acts", [])
    final_act = None
    if acts:
        # Find the act with the highest act_number, or take the last one
        try:
            final_act = max(acts, key=lambda act: act.get("act_number", 0))
        except (ValueError, TypeError):
            final_act = acts[-1] if acts else None
    
    conclusion_message = "Your story has concluded."
    
    # If we have a final act with rich details, use it to create a more meaningful conclusion
    if final_act and isinstance(final_act, dict):
        # Extract meaningful details from the enhanced act
        act_title = final_act.get("title", "")
        climactic_moment = final_act.get("climactic_moment", "")
        emotional_transformation = final_act.get("emotional_transformation", "")
        
        # Create a more meaningful conclusion message
        if act_title and (climactic_moment or emotional_transformation):
            conclusion_message = f"""Your journey through "{act_title}" has concluded. """
            
            if climactic_moment:
                conclusion_message += f"In the final moments, {climactic_moment} "
                
            if emotional_transformation:
                conclusion_message += f"This experience has brought about {emotional_transformation}."
    
    # Mark the story as completed
    story["status"] = "completed"
    final_story_snapshot = make_json_safe(attach_story_runtime_metadata(story_id, dict(story)))
    if story.get("session_id"):
        experiment_store.complete_session(story["session_id"], metadata={"ended_via_endpoint": True})
    experiment_store.log_story_event(
        event_type="story_ended",
        story_id=story_id,
        session_id=story.get("session_id"),
        participant_id=story.get("participant_id"),
        payload={
            "final_act": make_json_safe(final_act),
            "message": conclusion_message,
            "final_story_snapshot": final_story_snapshot,
        },
    )
    stories_db[story_id] = attach_story_runtime_metadata(story_id, story)
    
    return {
        "status": "completed", 
        "message": conclusion_message,
        "final_act": final_act
    }

@app.post("/stories/{story_id}/complete-summary")
async def generate_complete_story_summary(story_id: str):
    """
    Generate a comprehensive summary and analysis of the entire story.
    This is different from journey_summary as it analyzes the complete story arc,
    character development, and narrative progression, not just the user's journey.
    
    Returns a detailed story analysis suitable for a "take away" section.
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story = stories_db[story_id]
    
    # Extract all messages to analyze the full story
    all_messages = story.get("current_scene", {}).get("messages", [])
    
    # Get protagonist and key characters
    characters = story.get("characters", [])
    protagonist = next((c for c in characters if c.get("role") == "protagonist"), None)
    key_npcs = [c for c in characters if c.get("role") == "npc"]
    
    # Extract key story elements
    title = story.get("title", "Untitled Story")
    theme = story.get("cinematic_theme", story.get("theme", ""))
    emotional_goal = story.get("emotional_undercurrent", story.get("emotional_goal", ""))
    acts = story.get("acts", [])
    
    # Format conversation history
    conversation_history = "\n".join([
        f"{msg.get('character_id', 'unknown')}: {msg.get('content', '')}" 
        for msg in all_messages if msg.get("type") != "system"
    ])
    
    # Build prompt for comprehensive story analysis
    prompt = f"""
    You are a literary analyst and therapist specializing in narrative therapy. 
    Please provide a comprehensive analysis of this completed story:
    
    Title: {title}
    Theme: {theme}
    Emotional Goal: {emotional_goal}
    
    Story Structure:
    {json.dumps([{
        "act_number": act.get("act_number", i),
        "title": act.get("title", ""),
        "description": act.get("description", "")
    } for i, act in enumerate(acts)], indent=2)}
    
    Protagonist: {protagonist.get("name", "Unknown") if protagonist else "Unknown"}
    
    Key Characters:
    {", ".join([c.get("name", "") for c in key_npcs[:3]])}
    
    Story Conversation (excerpt):
    {conversation_history[-2000:] if len(conversation_history) > 2000 else conversation_history}
    
    Please provide:
    1. Story Arc Summary: A concise summary of the main narrative arc
    2. Character Development: How the protagonist and key characters evolved
    3. Emotional Journey: The emotional progression throughout the story
    4. Key Insights: 3-5 meaningful takeaways or lessons from this story
    5. Therapeutic Value: How this story addressed the emotional goal: "{emotional_goal}"
    
    Format your response as a well-structured JSON with these sections. Keep the total analysis under 500 words,
    focusing on depth rather than length. Make it personal and meaningful as a "take away" for the reader.
    """
    
    # Call the LLM for analysis
    messages = [
        {"role": "system", "content": "You are a literary analyst and therapist specializing in narrative therapy."},
        {"role": "user", "content": prompt}
    ]
    
    logger.info(f"Generating complete story analysis for story '{title}'")
    
    response = await run_llm_completion(
        messages=messages,
        model=resolve_model_for_task("story", story=story),
    )
    
    if response["error"]:
        logger.error(f"Error generating story analysis: {response['error']}")
        return {
            "success": False,
            "error": f"Failed to generate analysis: {response['error']}",
            "summary": None
        }
    
    # Extract JSON from response
    content = response.get("content", "")
    try:
        # Clean up the content - remove any markdown formatting or extra text
        content = content.strip()
        if "```json" in content:
            # Extract from markdown code block
            start_idx = content.find("```json") + 7
            end_idx = content.find("```", start_idx)
            if end_idx > start_idx:
                content = content[start_idx:end_idx].strip()
        elif "```" in content:
            # Extract from generic code block
            start_idx = content.find("```") + 3
            end_idx = content.find("```", start_idx)
            if end_idx > start_idx:
                content = content[start_idx:end_idx].strip()
        
        # Find JSON object boundaries
        start_idx = content.find('{')
        end_idx = content.rfind('}') + 1
        
        if start_idx >= 0 and end_idx > start_idx:
            json_str = content[start_idx:end_idx]
            # Try to parse the JSON
            story_analysis = json.loads(json_str)
            logger.info("Successfully extracted JSON story analysis data")
        else:
            # If no JSON object found, create a default structure
            logger.warning("No valid JSON structure found in story analysis response")
            story_analysis = {
                "story_arc_summary": content[:500] if content else "Analysis could not be structured properly.",
                "character_development": "Unable to parse structured analysis.",
                "emotional_journey": "Unable to parse structured analysis.",
                "key_insights": ["The story has concluded, but structured analysis is unavailable."],
                "therapeutic_value": "Please refer to the unstructured analysis text."
            }
    except Exception as e:
        logger.error(f"Failed to parse story analysis JSON: {e}")
        # Fallback to returning the raw content
        story_analysis = {
            "story_arc_summary": content[:500] if content else "Analysis generation failed.",
            "error": str(e),
            "raw_content": content
        }
    
    # Store the analysis in the story data for future reference
    story["complete_story_analysis"] = story_analysis
    stories_db[story_id] = story
    
    # Save the updated story with analysis to file
    try:
        save_dir = pathlib.Path("saved_stories")
        save_dir.mkdir(exist_ok=True)
        file_path = save_dir / f"{story_id}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(story, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved story with analysis to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save story with analysis: {e}")
    
    return {
        "success": True,
        "story_id": story_id,
        "analysis": story_analysis
    }

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file (image or document) to be used in the story.
    """
    # In a real implementation, this would save the file and process it
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "status": "uploaded"
    }

@app.post("/context")
async def manage_context(request: ContextActionRequest):
    """
    Save or load context data to/from a JSON file.
    """
    if request.action == "save":
        try:
            context_manager.save_to_json(request.filepath)
            return {"status": "success", "message": f"Context saved to {request.filepath}"}
        except Exception as e:
            logger.error(f"Error saving context: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save context: {str(e)}")
    
    elif request.action == "load":
        try:
            context_manager.load_from_json(request.filepath)
            return {"status": "success", "message": f"Context loaded from {request.filepath}"}
        except Exception as e:
            logger.error(f"Error loading context: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to load context: {str(e)}")
    
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'save' or 'load'.")

@app.get("/stories/{story_id}/context")
async def get_story_context(story_id: str, user_id: str):
    """
    Get the full context for a story, including user profile, narrative state, and emotional journey.
    """
    try:
        context = context_manager.get_full_context(story_id, user_id)
        return context
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving context: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve context: {str(e)}")

@app.post("/story/create/", response_model=StoryResponse)
async def create_story_with_answers(input: StoryAnswersInput):
    """
    使用用户回答创建完整故事
    """
    user_id = input.user_id
    experiment_meta = build_story_experiment_metadata(input.session_id, input.participant_id)
    original_answers = input.answers
    keywords = input.selected_keywords or []
    
    # 处理答案 - 支持多选题的逗号分隔答案
    processed_answers = {}
    story_id = input.story_id
    
    # 如果提供了story_id，则检查是否有问题数据可用
    if story_id and story_id in stories_db and "clarifying_questions" in stories_db[story_id]:
        questions_data = stories_db[story_id]["clarifying_questions"]
        for q_data in questions_data:
            question = q_data.get("question", "")
            if question in original_answers:
                answer = original_answers[question]
                # 检查是否为多选题答案（逗号分隔的字符串）
                if "," in answer and q_data.get("questionType") == "multiple":
                    # 拆分为列表并处理
                    answer_list = [a.strip() for a in answer.split(",")]
                    processed_answers[question] = answer_list
                else:
                    processed_answers[question] = answer
    else:
        # 如果没有问题数据，直接使用原始答案
        processed_answers = original_answers
    
    # 创建一个新的story_id (如果未提供)
    if not story_id:
        story_id = str(uuid.uuid4())
    
    # 步骤1：故事基础
    logger.info(f"Step 1: Creating story foundation for new story {story_id}")
    step1_input = StoryStep1Input(
        story_id=story_id,
        user_id=user_id or experiment_meta.get("participant_id"),
        participant_id=input.participant_id,
        session_id=input.session_id,
        emotional_need=input.emotional_need,
        answers=original_answers,
        selected_keywords=keywords
    )
    step1_response = await create_story_step1(step1_input)
    story_foundation = step1_response.dict()
    
    # 步骤2：故事场景
    logger.info(f"Step 2: Creating story setting for story {story_id}")
    step2_input = StoryStep2Input(story_id=story_id)
    step2_response = await create_story_step2(step2_input)
    story_setting = step2_response.setting
    
    # 步骤3：角色
    logger.info(f"Step 3: Creating story characters for story {story_id}")
    step3_input = StoryStep3Input(story_id=story_id)
    step3_response = await create_story_step3(step3_input)
    characters = step3_response.characters
    
    # 步骤4：故事结构
    logger.info(f"Step 4: Creating story structure for story {story_id}")
    step4_input = StoryStep4Input(story_id=story_id)
    step4_response = await create_story_step4(step4_input)
    acts = step4_response.acts
    
    # 步骤5：开场和互动元素
    logger.info(f"Step 5: Creating opening and interactive elements for story {story_id}")
    step5_input = StoryStep5Input(story_id=story_id)
    step5_response = await create_story_step5(step5_input)
    opening = step5_response.dict()
    
    # 处理初始对话
    initial_messages = []
    
    # 添加开场叙述
    if "opening_sequence" in opening and "narrative_text" in opening["opening_sequence"]:
        narrative_message = {
            "id": f"msg-{uuid.uuid4()}",
            "character_id": "system",
            "content": opening["opening_sequence"]["narrative_text"],
            "timestamp": datetime.now().isoformat(),
            "type": "system",
        }
        initial_messages.append(narrative_message)
    
    # 添加初始对话
    if "initial_dialogue" in opening:
        for dialogue in opening["initial_dialogue"]:
            message = {
                "id": f"msg-{uuid.uuid4()}",
                "character_id": dialogue.get("character_id", "system"),
                "content": dialogue.get("content", ""),
                "timestamp": datetime.now().isoformat(),
                "type": dialogue.get("type", "text"),
            }
            initial_messages.append(message)
    
    # 创建完整故事
    story = {
        "id": story_id,
        "user_id": input.user_id or experiment_meta.get("participant_id"),
        "participant_id": experiment_meta.get("participant_id"),
        "session_id": input.session_id,
        "condition_id": experiment_meta.get("condition_id"),
        "condition_name": experiment_meta.get("condition_name"),
        "selected_model": experiment_meta.get("selected_model"),
        "llm_config": experiment_meta.get("llm_config", {}),
        "story_mode": experiment_meta.get("story_mode", "default"),
        "benchmark_speed_profile": bool(experiment_meta.get("benchmark_speed_profile")),
        "speed_profile": experiment_meta.get("speed_profile"),
        "title": story_foundation.get("title", ""),
        "high_concept_premise": story_foundation.get("high_concept_premise", ""),
        "cinematic_theme": story_foundation.get("cinematic_theme", ""),
        "emotional_undercurrent": story_foundation.get("emotional_undercurrent", ""),
        "emotional_goal": story_foundation.get("emotional_undercurrent", ""),  # 兼容性
        "setting": story_setting,
        "characters": characters,
        "acts": acts,
        "current_act": 0,
        "current_scene": {
            "id": f"scene-{uuid.uuid4()}",
            "title": "Opening Scene",
            "description": opening.get("opening_sequence", {}).get("description", ""),
            "location": opening.get("opening_sequence", {}).get("location", ""),
            "mood": opening.get("opening_sequence", {}).get("mood", ""),
            "messages": initial_messages,
            "choices": opening.get("branching_choices", []),
            "hidden_elements": opening.get("hidden_elements", []),
        },
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "processed_answers": processed_answers,  # 保存处理后的答案，包括多选题答案列表
        "experiment_mode": experiment_meta.get("experiment_mode", False),
    }
    
    # 应用角色ID修复和标准化
    story = standardize_story_response(story)
    
    # 保存故事
    stories_db[story_id] = story
    
    # 初始化上下文管理器
    if input.user_id or experiment_meta.get("participant_id"):
        try:
            # 创建用户档案
            context_manager.create_user_profile(input.user_id or experiment_meta.get("participant_id"), {
                "answers": processed_answers,  # 使用处理后的答案
                "keywords": keywords
            })
            
            # 创建故事状态
            context_manager.create_story_state(story_id, story)
            
            logger.info(f"Context manager initialized for user {input.user_id or experiment_meta.get('participant_id')}, story {story_id}")
        except Exception as e:
            logger.error(f"Failed to initialize context manager: {e}")

    if input.session_id:
        experiment_store.attach_story_to_session(
            session_id=input.session_id,
            story_id=story_id,
            emotional_need=input.emotional_need,
            metadata={"created_via_full_story_endpoint": True},
        )
    experiment_store.log_story_event(
        event_type="story_created_full",
        story_id=story_id,
        session_id=input.session_id,
        participant_id=experiment_meta.get("participant_id"),
        payload=make_json_safe(
            {
                "title": story.get("title"),
                "status": story.get("status"),
                "processed_answers": processed_answers,
                "selected_keywords": keywords,
                "final_story_snapshot": story,
            }
        ),
    )
    story = attach_story_runtime_metadata(story_id, story)
    stories_db[story_id] = story
    return story

@app.post("/story/{story_id}/reflection")
async def generate_reflection(
    story_id: str, 
    request: dict,
    max_history_messages: int = 10
):
    """
    Generate a meta-planner reflection on the current story state to guide
    the narrative progression and enhance user engagement.
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story = stories_db[story_id]
    
    # Get recent conversation history
    recent_messages = story.get("current_scene", {}).get("messages", [])[-max_history_messages:]
    conversation_history = "\n".join([
        f"{msg.get('character_id', 'unknown')}: {msg.get('content', '')}" 
        for msg in recent_messages
    ])
    
    # Count dialogue messages in current scene (excluding system messages)
    dialogue_messages = [msg for msg in story.get("current_scene", {}).get("messages", []) 
                         if msg.get("type") != "system"]
    dialogue_count = len(dialogue_messages)
    exchange_count = count_exchanges_from_dialogue_count(dialogue_count)
    progression_count = get_progression_count_for_dialogue_count(profile, dialogue_count)
    logger.info(
        "Current pacing counts for story %s: dialogue=%s exchange=%s progression=%s (%s)",
        story_id,
        dialogue_count,
        exchange_count,
        progression_count,
        profile.pacing_unit,
    )
    
    # Generate reflection
    reflection_result = await generate_story_reflection(
        story_data=story,
        user_input=request.get("user_input", ""),
        conversation_history=conversation_history,
        dialogue_count=dialogue_count
    )
    
    # Log the full reflection data
    logger.info(f"--- Generated Reflection for Story {story_id} ---")
    logger.info(json.dumps(reflection_result, indent=2))
    
    # Check if a UI element is recommended
    ui_element_needed = False
    ui_element_type = None
    ui_element_desc = None
    ui_element_purpose = None
    
    # Check if story pacing needs acceleration based on dialogue count
    pacing_recommendation = None
    pacing_level = build_pacing_level(profile, progression_count)
    
    if reflection_result.get("success") and reflection_result.get("reflection"):
        reflection_data = reflection_result.get("reflection", {})
        
        # Extract pacing assessment if available
        if reflection_data.get("story_advancement_strategy", {}).get("pacing_assessment"):
            pacing_recommendation = reflection_data.get("story_advancement_strategy", {}).get("pacing_assessment")
            logger.info(f"Pacing assessment: {pacing_recommendation}")
        
        # Check for UI element recommendation
        ui_recommendation = reflection_data.get("ui_element_recommendation")
        
        if ui_recommendation:
            ui_element_needed = True
            # 适应新的JSON schema格式
            if isinstance(ui_recommendation, dict):
                ui_element_type = ui_recommendation.get("element_type")
                ui_element_desc = ui_recommendation.get("description")
                ui_element_purpose = ui_recommendation.get("purpose", "Enhance story experience")
                logger.info(f"UI element recommended: {ui_element_type} - {ui_element_desc} - {ui_element_purpose}")
            else:
                # 向后兼容旧格式
                ui_element_desc = ui_recommendation
                logger.warning(f"UI recommendation in deprecated format: {ui_recommendation}")
    
    # Add UI element information to the response
    response = {
        "reflection": reflection_result.get("reflection", {}),
        "success": reflection_result.get("success", False),
        "story_mode": profile.story_mode,
        "benchmark_speed_profile": profile.benchmark_speed_profile,
        "dialogue_count": dialogue_count,
        "exchange_count": exchange_count,
        "progression_count": progression_count,
        "progression_unit": profile.pacing_unit,
        "pacing_level": pacing_level,
        "pacing_recommendation": pacing_recommendation,
        "pacing_description": build_pacing_description(profile, pacing_level),
        "pacing_profile": {
            "level": pacing_level,
            "description": build_pacing_description(profile, pacing_level),
            "progression_count": progression_count,
            "progression_unit": profile.pacing_unit,
            "exchange_count": exchange_count,
            "dialogue_count": dialogue_count,
            "thresholds": {
                "acceleration_start": profile.acceleration_start,
                "critical_start": profile.critical_start,
                "mandatory_shift_start": profile.mandatory_shift_start,
                "structure_guard_start": profile.structure_guard_start,
                "conclusion_start": profile.conclusion_start,
                "conclusion_countdown_turns": profile.conclusion_countdown_turns,
            },
        },
        "ui_element": {
            "needed": ui_element_needed,
            "element_type": ui_element_type,
            "description": ui_element_desc,
            "purpose": ui_element_purpose if ui_element_needed and isinstance(ui_recommendation, dict) else None,
            "usage_instructions": "If a UI element is needed, make a separate request to /story/{story_id}/interactive-element with these parameters."
        }
    }
    
    return response

@app.post("/story/{story_id}/interactive-element")
async def create_interactive_element(
    story_id: str,
    element_type: str = None,
    element_description: str = None,
    content_details: str = None,
    request: Request = None
):
    """
    Generate an interactive UI element (HTML/CSS/JS) to enhance the story experience.
    支持查询参数和JSON请求体两种方式
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story = stories_db[story_id]
    
    # 如果参数为None，尝试从请求体中获取
    if request and (element_type is None or element_description is None):
        try:
            body = await request.json()
            element_type = element_type or body.get("element_type", "generic")
            element_description = element_description or body.get("element_description", "Interactive story element")
            content_details = content_details or body.get("content_details", "No specific content provided")
        except:
            # 如果请求体为空或解析失败，使用默认值
            element_type = element_type or "generic" 
            element_description = element_description or "Interactive story element"
            content_details = content_details or "No specific content provided"
    
    # 打印接收到的参数以便调试
    logger.info(f"Generating interactive element: type={element_type}, desc={element_description}")
    
    # Generate the interactive element
    # Determine purpose to guide frontend hint
    inferred_purpose = None
    try:
        # Prefer purpose from latest reflection if present
        reflection_req = {"user_input": element_description or "Interactive story element"}
        reflection_data = await generate_reflection(story_id, reflection_req)
        ui_meta = reflection_data.get("ui_element", {}) if reflection_data else {}
        inferred_purpose = ui_meta.get("purpose") or None
    except Exception as e:
        logger.warning(f"Could not infer purpose from reflection: {e}")

    result = await generate_interactive_element(
        element_type=element_type or "generic",
        element_description=element_description or "Interactive story element",
        content_details=content_details or "No specific content provided",
        story_context=story,
        element_purpose=inferred_purpose,
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    
    # ------------------ NEW: Persist interactive element ------------------
    try:
        if result.get("code"):
            interactive_msg = {
                "id": f"ie-{uuid.uuid4()}",
                "character_id": "system",
                "content": result["code"],
                "timestamp": datetime.now().isoformat(),
                "type": "interactive"
            }
            story.setdefault("current_scene", {}).setdefault("messages", []).append(interactive_msg)
            logger.info(f"Inserted interactive element into story {story_id} messages for persistence")
            experiment_store.log_story_event(
                event_type="interactive_element_generated",
                story_id=story_id,
                session_id=story.get("session_id"),
                participant_id=story.get("participant_id"),
                payload={
                    "element_type": result.get("element_type", element_type),
                    "element_description": result.get("element_description", element_description),
                    "purpose": result.get("purpose"),
                    "prompt": result.get("prompt"),
                    "summary": result.get("summary"),
                    "novelty_tags": result.get("novelty_tags", []),
                    "similarity_score": result.get("similarity_score"),
                },
            )
    except Exception as e:
        logger.error(f"Failed to persist interactive element in story messages: {e}")
    
    return result

@app.get("/story/{story_id}", response_model=StoryResponse)
async def get_story(story_id: str):
    """
    获取故事详情
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    
    story = stories_db[story_id]
    
    # 应用角色ID修复和标准化
    story = standardize_story_response(story)
    story = attach_story_runtime_metadata(story_id, story)
    # 更新修复后的故事数据
    stories_db[story_id] = story
    
    return story

# Create llm_client and context_manager instances
llm_client = LLMClient()
context_manager = ContextManager(llm_client)

# 添加一个新的端点来修复所有故事的角色ID
@app.post("/admin/fix-character-ids", response_model=Dict[str, Any])
async def fix_all_character_ids():
    """
    管理员端点：修复所有故事的角色ID
    """
    fixed_count = 0
    
    for story_id, story in stories_db.items():
        # 应用角色ID修复和标准化
        fixed_story = standardize_story_response(story)
        # 更新修复后的故事数据
        stories_db[story_id] = fixed_story
        fixed_count += 1
    
    return {
        "status": "success",
        "message": f"Fixed character IDs in {fixed_count} stories",
        "fixed_count": fixed_count
    }

if __name__ == "__main__":
    import uvicorn
    # 端口硬编码为11454，与启动脚本保持一致
    host = os.getenv("EMO_BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("EMO_BACKEND_PORT", "11454"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
