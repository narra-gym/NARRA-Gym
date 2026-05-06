from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional


STORY_MODE_DEFAULT = "default"
STORY_MODE_BENCHMARK = "benchmark"


@dataclass(frozen=True)
class StorySpeedProfile:
    story_mode: str
    benchmark_speed_profile: bool
    pacing_unit: str
    acceleration_start: int
    critical_start: int
    mandatory_shift_start: int
    structure_guard_start: int
    conclusion_start: int
    conclusion_countdown_turns: int
    max_choices: Optional[int]
    auto_fast_forward: bool
    skip_optional_llm: bool
    transition_display_ms: int


DEFAULT_SPEED_PROFILE = StorySpeedProfile(
    story_mode=STORY_MODE_DEFAULT,
    benchmark_speed_profile=False,
    pacing_unit="dialogue",
    acceleration_start=10,
    critical_start=13,
    mandatory_shift_start=15,
    structure_guard_start=12,
    conclusion_start=30,
    conclusion_countdown_turns=5,
    max_choices=None,
    auto_fast_forward=False,
    skip_optional_llm=False,
    transition_display_ms=5000,
)


BENCHMARK_SPEED_PROFILE = StorySpeedProfile(
    story_mode=STORY_MODE_BENCHMARK,
    benchmark_speed_profile=True,
    pacing_unit="exchange",
    acceleration_start=4,
    critical_start=6,
    mandatory_shift_start=7,
    structure_guard_start=6,
    conclusion_start=16,
    conclusion_countdown_turns=3,
    max_choices=3,
    auto_fast_forward=False,
    skip_optional_llm=True,
    transition_display_ms=3000,
)


def is_benchmark_session(session: Optional[Dict[str, Any]]) -> bool:
    return bool(session and str(session.get("mode") or "").lower() == STORY_MODE_BENCHMARK)


def resolve_story_mode(
    story: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
) -> str:
    if story:
        story_mode = str(story.get("story_mode") or "").strip().lower()
        if story_mode in {STORY_MODE_DEFAULT, STORY_MODE_BENCHMARK}:
            return story_mode
        if story.get("benchmark_speed_profile") is True:
            return STORY_MODE_BENCHMARK
    if is_benchmark_session(session):
        return STORY_MODE_BENCHMARK
    return STORY_MODE_DEFAULT


def is_benchmark_story(
    story: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
) -> bool:
    return resolve_story_mode(story=story, session=session) == STORY_MODE_BENCHMARK


def get_story_speed_profile(
    story: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
) -> StorySpeedProfile:
    return BENCHMARK_SPEED_PROFILE if is_benchmark_story(story=story, session=session) else DEFAULT_SPEED_PROFILE


def count_non_system_messages(messages: Optional[Iterable[Dict[str, Any]]]) -> int:
    if not messages:
        return 0
    return sum(1 for message in messages if message.get("type") != "system")


def count_story_exchanges(messages: Optional[Iterable[Dict[str, Any]]]) -> int:
    return count_non_system_messages(messages) // 2


def has_scene_transition_occurred(story: Optional[Dict[str, Any]]) -> bool:
    if not story or not isinstance(story, dict):
        return False

    current_scene = story.get("current_scene")
    if not isinstance(current_scene, dict):
        return False

    if str(current_scene.get("scene_transition_caption") or "").strip():
        return True

    scene_dynamics = current_scene.get("scene_dynamics")
    if isinstance(scene_dynamics, dict) and str(scene_dynamics.get("scene_transition_caption") or "").strip():
        return True

    for message in current_scene.get("messages") or []:
        if not isinstance(message, dict):
            continue

        message_id = str(message.get("id") or "")
        if message_id.startswith("transition-"):
            return True

        content = str(message.get("content") or "").strip()
        if (
            message.get("type") == "system"
            and content.startswith("[")
            and content.endswith("]")
            and "THE STORY REACHES ITS CONCLUSION" not in content
            and "The narrative accelerates toward a resolution." not in content
        ):
            return True

    return False


def can_offer_end_story_choice(
    story: Optional[Dict[str, Any]],
    conclusion_countdown: Optional[int] = 0,
) -> bool:
    return bool(int(conclusion_countdown or 0) > 0 and has_scene_transition_occurred(story))


def count_exchanges_from_dialogue_count(dialogue_count: Optional[int]) -> int:
    return max(int(dialogue_count or 0), 0) // 2


def get_progression_count_for_messages(
    profile: StorySpeedProfile,
    messages: Optional[Iterable[Dict[str, Any]]],
) -> int:
    if profile.pacing_unit == "exchange":
        return count_story_exchanges(messages)
    return count_non_system_messages(messages)


def get_progression_count_for_dialogue_count(
    profile: StorySpeedProfile,
    dialogue_count: Optional[int],
) -> int:
    if profile.pacing_unit == "exchange":
        return count_exchanges_from_dialogue_count(dialogue_count)
    return max(int(dialogue_count or 0), 0)


def build_pacing_level(profile: StorySpeedProfile, progression_count: int) -> int:
    if progression_count < profile.acceleration_start:
        return 0
    if progression_count < profile.critical_start:
        return 1
    if progression_count < profile.mandatory_shift_start:
        return 2
    if progression_count < profile.conclusion_start:
        return 3
    return 4


def build_pacing_description(profile: StorySpeedProfile, pacing_level: int) -> str:
    unit = "exchanges" if profile.pacing_unit == "exchange" else "dialogue turns"
    descriptions = {
        0: f"Normal pacing - continue natural story progression within the current {unit} window.",
        1: f"Accelerated pacing needed - start introducing sharper developments before the next {unit} threshold.",
        2: f"Critical pacing point - prepare a strong shift, reveal, or transition within the next {unit}.",
        3: f"Mandatory transition required - implement a concrete reveal, conflict shift, or scene change now.",
        4: f"Endgame pacing - drive directly toward resolution and conclusion within the remaining {unit}.",
    }
    return descriptions.get(pacing_level, descriptions[0])


def serialize_speed_profile(profile: StorySpeedProfile) -> Dict[str, Any]:
    return asdict(profile)


def build_runtime_story_flags(
    story: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    profile = get_story_speed_profile(story=story, session=session)
    return {
        "story_mode": profile.story_mode,
        "benchmark_speed_profile": profile.benchmark_speed_profile,
        "speed_profile": serialize_speed_profile(profile),
    }


def latency_bucket_ms(latency_ms: Optional[float]) -> Optional[str]:
    if latency_ms is None:
        return None
    if latency_ms < 1000:
        return "<1s"
    if latency_ms < 2000:
        return "1-2s"
    if latency_ms < 4000:
        return "2-4s"
    if latency_ms < 8000:
        return "4-8s"
    return "8s+"
