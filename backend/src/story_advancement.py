import asyncio
import logging
import json
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from fastapi import HTTPException, status

from src.utils import extract_json_from_response, get_protagonist, is_story_stagnating, normalize_character_id, parse_json_response, validate_story_advancement_payload
from src.llm_client import get_llm_completion, stream_story_completion_sync
from src.config import settings
from src.benchmark_speed import (
    build_pacing_level,
    can_offer_end_story_choice,
    count_story_exchanges,
    get_progression_count_for_messages,
    get_story_speed_profile,
    has_scene_transition_occurred,
)
from src import prompt_templates


class DialogueStreamExtractor:
    """
    Extracts the first NPC dialogue text from a streaming JSON response.
    Scans for the pattern  "dialogue": "..."  and yields characters
    as they arrive, stopping after the first dialogue field.
    """
    _TRIGGERS = ('"dialogue": "', '"dialogue":"')

    def __init__(self):
        self._tail: str = ""   # Rolling window for pattern matching
        self._in_dial: bool = False
        self._esc: bool = False
        self._captured: bool = False  # Stop after first dialogue

    def feed(self, chunk: str) -> str:
        """Process one text chunk. Returns any dialogue characters found."""
        result: list[str] = []
        for ch in chunk:
            if self._captured:
                break
            if self._in_dial:
                if self._esc:
                    result.append(ch)
                    self._esc = False
                elif ch == "\\":
                    self._esc = True
                elif ch == '"':
                    self._in_dial = False
                    self._captured = True
                else:
                    result.append(ch)
            else:
                self._tail = (self._tail + ch)[-25:]
                for trigger in self._TRIGGERS:
                    if self._tail.endswith(trigger):
                        self._in_dial = True
                        self._esc = False
                        break
        return "".join(result)

# Configure logging
logger = logging.getLogger(__name__)


def _build_story_trace_context(
    story: Dict[str, Any],
    source: str,
    task: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    session_id = story.get("session_id")
    if not session_id:
        return None
    return {
        "session_id": session_id,
        "participant_id": story.get("participant_id"),
        "story_id": story.get("id"),
        "source": source,
        "task": task,
        "metadata": metadata or {},
    }


def _build_benchmark_prompt_guidance(exchange_count: int) -> str:
    guidance = [
        "[BENCHMARK SPEED PROFILE]",
        "This story is running in benchmark fast-play mode.",
        "Respond with exactly one meaningful dramatic beat.",
        "Your response must add at least one of: a reveal, a conflict shift, or a concrete next objective.",
        "Do not linger in atmospheric filler, slow reassurance loops, or circular emotional reflection.",
        "Do not force a location change unless the turn genuinely earns one.",
        "Provide up to 3 branching choices.",
    ]
    if exchange_count >= 4:
        guidance.append("The benchmark pace is accelerating. The turn should feel sharp and consequential.")
    if exchange_count >= 6:
        guidance.append("A hard progression guard is active. Force a real shift, not a soft continuation.")
    if exchange_count >= 7:
        guidance.append("A mandatory scene shift/reveal window is active. Change the situation now.")
    if exchange_count >= 16:
        guidance.append("The story is in endgame mode. Aim choices directly at resolution.")
    return "\n".join(guidance)


BENCHMARK_RESPONSE_MARKERS = {
    "character_id": "<<CHARACTER_ID>>",
    "response": "<<RESPONSE>>",
    "choices": "<<CHOICES>>",
    "tags": "<<TAGS>>",
}
BENCHMARK_STATE_TAG_KEYS = (
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
BENCHMARK_STATE_TAG_PATTERN = re.compile(
    r"(?im)^\s*(?:"
    + "|".join(re.escape(key) for key in BENCHMARK_STATE_TAG_KEYS)
    + r")\s*:"
)
MIXED_NARRATION_PATTERN = re.compile(r"\*[^*]+\*")


class BenchmarkTaggedStreamExtractor:
    """Streams only the visible response block from the benchmark tagged format."""

    def __init__(self):
        self._buffer = ""
        self._started = False
        self._done = False
        self._emitted_chars = 0

    def feed(self, chunk: str) -> str:
        if self._done:
            return ""

        self._buffer += chunk
        response_marker = BENCHMARK_RESPONSE_MARKERS["response"]
        choices_marker = BENCHMARK_RESPONSE_MARKERS["choices"]
        tags_marker = BENCHMARK_RESPONSE_MARKERS["tags"]

        if not self._started:
            start_idx = self._buffer.find(response_marker)
            if start_idx < 0:
                return ""
            self._started = True
            self._buffer = self._buffer[start_idx + len(response_marker):]
            if self._buffer.startswith("\r\n"):
                self._buffer = self._buffer[2:]
            elif self._buffer.startswith("\n"):
                self._buffer = self._buffer[1:]

        end_indexes = [
            idx
            for idx in (
                self._buffer.find(choices_marker),
                self._buffer.find(tags_marker),
            )
            if idx >= 0
        ]
        if end_indexes:
            end_idx = min(end_indexes)
            visible = self._buffer[:end_idx]
            delta = visible[self._emitted_chars:]
            self._done = True
            return delta

        safe_flush_upto = max(len(self._buffer) - 32, 0)
        visible = self._buffer[:safe_flush_upto]
        delta = visible[self._emitted_chars:]
        self._emitted_chars += len(delta)
        return delta

    def finalize(self) -> str:
        if not self._started or self._done:
            return ""
        visible = self._buffer
        delta = visible[self._emitted_chars:]
        self._done = True
        return delta


def _format_setting_text(setting: Any) -> str:
    if isinstance(setting, dict):
        location = str(setting.get("primary_location") or "").strip()
        period = str(setting.get("time_period") or "").strip()
        atmosphere = str(setting.get("atmosphere") or "").strip()
        unique = ", ".join(
            str(item).strip()
            for item in (setting.get("unique_elements") or [])
            if str(item).strip()
        )
        parts = [part for part in (location, period, atmosphere, unique) if part]
        return " | ".join(parts) if parts else json.dumps(setting, ensure_ascii=False)
    return str(setting or "").strip()


def _as_mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_inline_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_display_text(value: Any) -> str:
    if value is None:
        return ""

    normalized_lines: List[str] = []
    for raw_line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        compact = re.sub(r"\s+", " ", raw_line).strip()
        if compact:
            normalized_lines.append(compact)
        elif normalized_lines and normalized_lines[-1] != "":
            normalized_lines.append("")

    return "\n".join(normalized_lines).strip()


def _detect_render_mode(content: str, preferred: str = "plain") -> str:
    if MIXED_NARRATION_PATTERN.search(content or ""):
        return "rp_mixed"
    return preferred


def _build_visible_turn_content(
    spoken_text: Any,
    *,
    action: Any = "",
    direction: Any = "",
    preferred_mode: str = "plain",
) -> tuple[str, str]:
    spoken = _normalize_display_text(spoken_text)
    if spoken and MIXED_NARRATION_PATTERN.search(spoken):
        return spoken, _detect_render_mode(spoken, preferred_mode)

    narrative_parts = [
        part
        for part in (
            _normalize_display_text(direction),
            _normalize_display_text(action),
        )
        if part
    ]
    if narrative_parts:
        combined = f"*{' '.join(narrative_parts)}*"
        if spoken:
            combined = f"{combined}\n\n{spoken}"
        return combined.strip(), "rp_mixed"

    if spoken:
        return spoken, _detect_render_mode(spoken, preferred_mode)

    return "", preferred_mode


def _pick_default_benchmark_responder(
    story: Dict[str, Any],
    protagonist_id: str,
    target_character_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if target_character_id:
        return next(
            (char for char in story.get("characters", []) if char.get("id") == target_character_id),
            None,
        )

    for message in reversed(story.get("current_scene", {}).get("messages", []) or []):
        char_id = message.get("character_id")
        if char_id and char_id not in {protagonist_id, "system"}:
            matched = next(
                (char for char in story.get("characters", []) if char.get("id") == char_id),
                None,
            )
            if matched:
                return matched

    return next(
        (
            char
            for char in story.get("characters", [])
            if char.get("id") not in {protagonist_id, "system"}
        ),
        None,
    )


def _build_character_voice_block(
    story: Dict[str, Any],
    protagonist: Dict[str, Any],
    responder: Optional[Dict[str, Any]],
) -> str:
    lines = []
    for character in story.get("characters", []):
        if character.get("id") == "system":
            continue
        role = character.get("role", "")
        parts = [
            f"- {character.get('id', '')} / {character.get('name', 'Unknown')} ({role})",
        ]
        if character.get("personality"):
            parts.append(f"voice: {_normalize_inline_text(character.get('personality'))}")
        if character.get("relationship") or character.get("relationship_to_protagonist"):
            parts.append(
                f"relationship: {_normalize_inline_text(character.get('relationship') or character.get('relationship_to_protagonist'))}"
            )
        if character.get("description") or character.get("visual_description"):
            parts.append(
                f"description: {_normalize_inline_text(character.get('description') or character.get('visual_description'))}"
            )
        lines.append(" | ".join(parts))

    responder_instruction = (
        f"Reply as {responder.get('name', 'the most relevant character')} ({responder.get('id', '')})."
        if responder
        else "Reply as the single most relevant non-protagonist character."
    )
    protagonist_instruction = (
        f"The user is {protagonist.get('name', 'the protagonist')} ({protagonist.get('id', 'protagonist')})."
    )
    return "\n".join([responder_instruction, protagonist_instruction, *lines])


def _select_benchmark_voice_anchors(
    story: Dict[str, Any],
    protagonist_id: str,
    responder_id: Optional[str],
    max_items: int = 3,
) -> List[str]:
    anchors: List[str] = []
    messages = story.get("current_scene", {}).get("messages", []) or []
    character_map = {char.get("id"): char for char in story.get("characters", []) if char.get("id")}

    candidate_ids = [responder_id] if responder_id else []
    if not candidate_ids:
        candidate_ids = [
            char.get("id")
            for char in story.get("characters", [])
            if char.get("id") not in {protagonist_id, "system"}
        ]

    for message in reversed(messages):
        char_id = message.get("character_id")
        if char_id not in candidate_ids or message.get("type") != "text":
            continue
        content = str(message.get("content", "")).strip()
        if len(content) < 40:
            continue
        speaker = character_map.get(char_id, {}).get("name", char_id)
        anchors.append(f"{speaker}: {content}")
        if len(anchors) >= max_items:
            break

    opening_dialogue = story.get("opening_sequence", {}).get("initial_dialogue") or story.get("initial_dialogue") or []
    if len(anchors) < max_items and isinstance(opening_dialogue, list):
        for message in opening_dialogue:
            char_id = message.get("character_id")
            if char_id not in candidate_ids:
                continue
            content = str(message.get("content", "")).strip()
            if len(content) < 40:
                continue
            speaker = character_map.get(char_id, {}).get("name", char_id)
            line = f"{speaker}: {content}"
            if line not in anchors:
                anchors.append(line)
            if len(anchors) >= max_items:
                break

    return list(reversed(anchors[-max_items:]))


def _select_benchmark_memory_lines(
    story: Dict[str, Any],
    max_items: int = 6,
) -> List[str]:
    memory_lines: List[str] = []
    story_memory = _as_mapping(story.get("story_memory"))
    story_state = _as_mapping(story.get("story_state"))
    current_scene = _as_mapping(story.get("current_scene"))
    hidden_elements = _as_mapping(current_scene.get("hidden_elements"))
    current_act_index = story.get("current_act", 0)
    acts = story.get("acts") or []
    current_act = acts[current_act_index] if acts and 0 <= current_act_index < len(acts) else {}

    candidates = [
        ("Current goal", story_state.get("current_objective") or story_memory.get("current_goal") or story.get("protagonist_objective")),
        ("Current tension", story_state.get("current_tension") or (story_memory.get("open_tensions") or [""])[0]),
        ("Immediate stakes", story_state.get("immediate_stakes")),
        ("Latest reveal", story_state.get("latest_reveal") or story_memory.get("last_major_turning_point")),
        ("Act purpose", current_act.get("purpose")),
        ("Scene location", current_scene.get("location") or current_scene.get("setting")),
        ("Scene mood", current_scene.get("emotional_tone") or current_scene.get("mood")),
        ("Foreshadowing", hidden_elements.get("foreshadowing")),
    ]

    for label, value in candidates:
        text = _normalize_inline_text(value)
        if text:
            memory_lines.append(f"- {label}: {text}")

    for clue in story_memory.get("active_clues", []) or []:
        text = _normalize_inline_text(clue)
        if text:
            memory_lines.append(f"- Active clue: {text}")

    return memory_lines[:max_items]


def _build_benchmark_chat_native_messages(
    story: Dict[str, Any],
    protagonist: Dict[str, Any],
    user_input: str,
    action_type: str,
    exchange_count: int,
    pacing_level: int,
    target_character_id: Optional[str],
    target_character_name: Optional[str],
) -> List[Dict[str, str]]:
    responder = _pick_default_benchmark_responder(story, protagonist.get("id"), target_character_id)
    responder_id = responder.get("id") if responder else None
    responder_name = responder.get("name") if responder else "the most relevant character"
    setting_text = _format_setting_text(story.get("setting"))
    current_scene = _as_mapping(story.get("current_scene"))
    scene_location = _normalize_inline_text(current_scene.get("location") or current_scene.get("setting") or setting_text)
    scene_mood = _normalize_inline_text(current_scene.get("emotional_tone") or current_scene.get("mood"))
    story_state = _as_mapping(story.get("story_state"))
    memory_lines = _select_benchmark_memory_lines(story)
    voice_anchors = _select_benchmark_voice_anchors(story, protagonist.get("id"), responder_id)
    benchmark_guidance = _build_benchmark_prompt_guidance(exchange_count)

    instructions = [
        "Write the next reply in a fictional story chat.",
        "Stay fully in character and write vivid but efficient prose with concrete sensory detail.",
        "The reply must feel like a strong SillyTavern-style RP turn: expressive, readable, and character-led.",
        "Aim for roughly 120-220 words unless the countdown is about to end.",
        "The turn must contain one meaningful development: a reveal, a conflict shift, or a concrete next objective.",
        "Do not pad with empty reassurance, summary, or generic therapist language.",
        "Keep the focus on the immediate dramatic moment, not on abstract analysis.",
        "Format the visible reply in RP mixed style: use *...* for action, sensory narration, or scene texture; keep spoken dialogue as plain text or quoted dialogue.",
        "Do not repeatedly re-introduce the speaker by name or role unless this is their first formal entrance or the protagonist directly asks who they are.",
        "Do not force a location change unless the turn genuinely earns one.",
        "Return exactly the tagged format shown below and do not add extra markers or commentary.",
        f"Reply as {responder_name} ({responder_id or 'choose-a-valid-character-id'}).",
    ]
    if target_character_name:
        instructions.append(f"The protagonist is explicitly addressing {target_character_name}; that character should reply.")
    if pacing_level >= 3:
        instructions.append("A hard pacing window is active. Make the situation visibly change in this turn.")
    if pacing_level >= 4:
        instructions.append("The story is in endgame mode. Make the next choices point directly at resolution.")

    output_contract = "\n".join(
        [
            BENCHMARK_RESPONSE_MARKERS["character_id"],
            "exact_character_id",
            BENCHMARK_RESPONSE_MARKERS["response"],
            "one visible reply in prose",
            BENCHMARK_RESPONSE_MARKERS["choices"],
            "- first choice",
            "- second choice",
            "- third choice",
            BENCHMARK_RESPONSE_MARKERS["tags"],
            "scene_shift: yes|no",
            "act_advance: yes|no",
            "ending_ready: yes|no",
            "objective: ...",
            "tension: ...",
            "immediate_stakes: ...",
            "latest_reveal: ...",
            "relationship_shift: ...",
            "emotional_beat: ...",
            "location_status: ...",
            "next_location: ...",
        ]
    )

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": "\n".join(instructions),
        },
        {
            "role": "system",
            "content": "\n".join(
                [
                    f"Title: {story.get('title', '')}",
                    f"Theme: {_normalize_inline_text(story.get('cinematic_theme') or story.get('theme'))}",
                    f"Setting: {setting_text}",
                    f"Current location: {scene_location}",
                    f"Current mood: {scene_mood or 'tense and active'}",
                    f"Action type: {action_type}",
                    f"Benchmark exchange count: {exchange_count}",
                    f"Pacing level: {pacing_level}",
                    f"Current objective: {_normalize_inline_text(story_state.get('current_objective') or story.get('protagonist_objective'))}",
                    f"Current tension: {_normalize_inline_text(story_state.get('current_tension'))}",
                    benchmark_guidance,
                    "",
                    "CHARACTER VOICES:",
                    _build_character_voice_block(story, protagonist, responder),
                    "",
                    "RELEVANT MEMORY:",
                    "\n".join(memory_lines) if memory_lines else "- None yet.",
                    "",
                    "VOICE ANCHORS:",
                    "\n".join([f"- {anchor}" for anchor in voice_anchors]) if voice_anchors else "- Keep the established tone from chat history.",
                    "",
                    "OUTPUT CONTRACT:",
                    output_contract,
                ]
            ),
        },
    ]

    character_map = {char.get("id"): char for char in story.get("characters", []) if char.get("id")}
    recent_messages = current_scene.get("messages", []) or []
    recent_messages = recent_messages[-12:]
    for message in recent_messages:
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        char_id = message.get("character_id")
        if message.get("type") == "system":
            messages.append({"role": "system", "content": f"Scene note: {content}"})
            continue
        speaker = character_map.get(char_id, {}).get("name", char_id or "Unknown")
        role = "user" if char_id == protagonist.get("id") else "assistant"
        messages.append({"role": role, "content": f"{speaker}: {content}"})

    messages.append(
        {
            "role": "user",
            "content": f"{protagonist.get('name', 'You')}: {user_input}",
        }
    )
    return messages


def _extract_tagged_section(content: str, marker: str, next_markers: List[str]) -> str:
    start_idx = content.find(marker)
    if start_idx < 0:
        return ""
    start_idx += len(marker)
    remainder = content[start_idx:]
    end_positions = [remainder.find(next_marker) for next_marker in next_markers if remainder.find(next_marker) >= 0]
    end_idx = min(end_positions) if end_positions else len(remainder)
    return remainder[:end_idx].strip()


def _strip_benchmark_state_block(text: str) -> str:
    if not text:
        return ""

    cleaned = str(text)
    for marker in (BENCHMARK_RESPONSE_MARKERS["choices"], BENCHMARK_RESPONSE_MARKERS["tags"]):
        marker_index = cleaned.find(marker)
        if marker_index >= 0:
            cleaned = cleaned[:marker_index]

    tag_match = BENCHMARK_STATE_TAG_PATTERN.search(cleaned)
    if tag_match:
        cleaned = cleaned[:tag_match.start()]

    return cleaned.strip()


def _choice_to_id(choice_text: str, index: int) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", choice_text.lower()).strip("_")
    if not normalized:
        normalized = f"choice_{index + 1}"
    return normalized[:48]


def _parse_bool_tag(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_benchmark_choice_lines(content: str) -> List[str]:
    if not content:
        return []

    content_text = str(content)
    has_choices_marker = BENCHMARK_RESPONSE_MARKERS["choices"] in content_text
    choices_block = (
        _extract_tagged_section(
            content_text,
            BENCHMARK_RESPONSE_MARKERS["choices"],
            [BENCHMARK_RESPONSE_MARKERS["tags"]],
        )
        if has_choices_marker
        else ""
    )
    source = choices_block if has_choices_marker else content_text
    parsed_choices: List[str] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in BENCHMARK_RESPONSE_MARKERS.values():
            continue
        if BENCHMARK_STATE_TAG_PATTERN.match(line):
            break
        line = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        if not line or line.lower() in {"choices", "player choices"}:
            continue
        parsed_choices.append(line)
    return parsed_choices


def _parse_benchmark_main_generation(
    content: str,
    story: Dict[str, Any],
    protagonist: Dict[str, Any],
    target_character_id: Optional[str],
) -> Dict[str, Any]:
    markers = list(BENCHMARK_RESPONSE_MARKERS.values())
    character_map = {char.get("id"): char for char in story.get("characters", []) if char.get("id")}
    default_responder = _pick_default_benchmark_responder(story, protagonist.get("id"), target_character_id)
    fallback_character_id = (
        target_character_id
        or (default_responder.get("id") if default_responder else None)
        or next(
            (
                char.get("id")
                for char in story.get("characters", [])
                if char.get("id") not in {protagonist.get("id"), "system"}
            ),
            protagonist.get("id"),
        )
    )

    character_id = _extract_tagged_section(
        content,
        BENCHMARK_RESPONSE_MARKERS["character_id"],
        [BENCHMARK_RESPONSE_MARKERS["response"], BENCHMARK_RESPONSE_MARKERS["choices"], BENCHMARK_RESPONSE_MARKERS["tags"]],
    ).splitlines()[0:1]
    character_id = (character_id[0].strip() if character_id else "").strip()
    if character_id not in character_map:
        character_id = fallback_character_id

    response_text = _extract_tagged_section(
        content,
        BENCHMARK_RESPONSE_MARKERS["response"],
        [BENCHMARK_RESPONSE_MARKERS["choices"], BENCHMARK_RESPONSE_MARKERS["tags"]],
    )
    if not response_text:
        stripped = content
        for marker in markers:
            stripped = stripped.replace(marker, "")
        response_lines = stripped.splitlines()
        while response_lines and (
            not response_lines[0].strip()
            or response_lines[0].strip() == "exact_character_id"
            or response_lines[0].strip() in character_map
        ):
            response_lines.pop(0)
        response_text = "\n".join(response_lines).strip()
    response_text = _strip_benchmark_state_block(response_text)

    parsed_choices = _parse_benchmark_choice_lines(content)

    tags_block = _extract_tagged_section(
        content,
        BENCHMARK_RESPONSE_MARKERS["tags"],
        [],
    )
    tags: Dict[str, str] = {}
    for raw_line in tags_block.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        tags[key.strip().lower()] = value.strip()

    return {
        "character_id": character_id,
        "assistant_text": response_text,
        "suggested_choices": parsed_choices,
        "scene_shift": _parse_bool_tag(tags.get("scene_shift", "no")),
        "act_advance": _parse_bool_tag(tags.get("act_advance", "no")),
        "ending_ready": _parse_bool_tag(tags.get("ending_ready", "no")),
        "objective": tags.get("objective", ""),
        "tension": tags.get("tension", ""),
        "immediate_stakes": tags.get("immediate_stakes", ""),
        "latest_reveal": tags.get("latest_reveal", ""),
        "relationship_shift": tags.get("relationship_shift", ""),
        "emotional_beat": tags.get("emotional_beat", ""),
        "location_status": tags.get("location_status", ""),
        "next_location": tags.get("next_location", ""),
    }


def _fallback_benchmark_choices(
    generation: Dict[str, Any],
    exchange_count: int,
    conclusion_countdown: int,
    allow_end_choice: bool,
) -> List[str]:
    if allow_end_choice and (conclusion_countdown > 0 or generation.get("ending_ready")):
        return [
            "Push for the final truth right now.",
            "Lock in the consequence before anyone can back away.",
            "End the story now",
        ]
    if generation.get("scene_shift"):
        return [
            "Follow the shift before the moment closes.",
            "Stop and ask what this change really means.",
            "Use the new location to press for the missing truth.",
        ]
    if exchange_count >= 7:
        return [
            "Press for the concrete truth.",
            "Take the next risky step before the lead cools.",
            "Change the leverage before the moment settles again.",
        ]
    return [
        "Ask the character to go one layer deeper.",
        "Act on the strongest lead in front of you.",
        "Shift the pressure with a sharper question or move.",
    ]


def _normalize_benchmark_choice_texts(
    choice_texts: List[str],
    allow_end_choice: bool,
) -> List[str]:
    normalized_choices: List[str] = []
    seen: set[str] = set()
    for choice_text in choice_texts or []:
        cleaned = _normalize_inline_text(choice_text)
        if not cleaned:
            continue
        cleaned_lower = cleaned.lower()
        if not allow_end_choice and cleaned_lower == "end the story now":
            continue
        if cleaned_lower in seen:
            continue
        seen.add(cleaned_lower)
        normalized_choices.append(cleaned)
    return normalized_choices


def _resolve_benchmark_choice_texts(
    suggested_choices: List[str],
    fallback_choices: List[str],
    target_choice_count: int,
    allow_end_choice: bool,
) -> Tuple[List[str], bool]:
    resolved_choices = _normalize_benchmark_choice_texts(suggested_choices, allow_end_choice)
    seen_choice_texts = {choice.lower() for choice in resolved_choices}
    fallback_choice_set = {
        _normalize_inline_text(choice_text).lower()
        for choice_text in fallback_choices
        if _normalize_inline_text(choice_text)
    }

    for fallback_choice in fallback_choices:
        cleaned_fallback = _normalize_inline_text(fallback_choice)
        cleaned_fallback_lower = cleaned_fallback.lower()
        if not cleaned_fallback or cleaned_fallback_lower in seen_choice_texts:
            continue
        resolved_choices.append(cleaned_fallback)
        seen_choice_texts.add(cleaned_fallback_lower)
        if len(resolved_choices) >= target_choice_count:
            break

    resolved_choices = resolved_choices[:target_choice_count]
    fallback_only = bool(resolved_choices) and len(resolved_choices) == target_choice_count and all(
        choice.lower() in fallback_choice_set for choice in resolved_choices
    )
    return resolved_choices, fallback_only


def _build_benchmark_choice_repair_messages(
    story: Dict[str, Any],
    protagonist: Dict[str, Any],
    generation: Dict[str, Any],
    user_input: str,
    action_type: str,
    exchange_count: int,
    pacing_level: int,
    fallback_choices: List[str],
    target_choice_count: int,
    allow_end_choice: bool,
) -> List[Dict[str, str]]:
    current_scene = _as_mapping(story.get("current_scene"))
    story_state = _as_mapping(story.get("story_state"))
    character_map = {char.get("id"): char for char in story.get("characters", []) if char.get("id")}
    responder_id = generation.get("character_id")
    responder_name = character_map.get(responder_id, {}).get("name", responder_id or "The other character")
    setting_text = _format_setting_text(story.get("setting"))
    scene_location = _normalize_inline_text(current_scene.get("location") or current_scene.get("setting") or setting_text)
    scene_mood = _normalize_inline_text(current_scene.get("emotional_tone") or current_scene.get("mood"))
    visible_reply = _normalize_display_text(generation.get("assistant_text") or "")
    memory_lines = _select_benchmark_memory_lines(story, max_items=5)
    forbidden_choices = "\n".join(f"- {choice}" for choice in fallback_choices) or "- None."

    instructions = [
        "Repair the player choice list for a fictional story chat turn.",
        "The visible reply is already written. Do not rewrite the reply.",
        f"Return exactly {target_choice_count} branching player choices.",
        "Each option must be concrete, scene-specific, and immediately actionable in the very next beat.",
        "Make the branches meaningfully different in tactic, target, or emotional risk.",
        "Do not output generic filler, explanation, analysis, or any text outside the required tagged choice block.",
        "Do not reuse or paraphrase these generic fallback choices:",
        forbidden_choices,
        "Ground every option in the actual people, objects, deadlines, revelations, or leverage visible in this turn.",
    ]
    if allow_end_choice:
        instructions.append('Only include "End the story now" if this moment genuinely supports an immediate ending.')
    else:
        instructions.append('Do not include "End the story now".')

    choice_placeholders = ["first", "second", "third", "fourth"]
    output_contract_lines = [BENCHMARK_RESPONSE_MARKERS["choices"]]
    for index in range(target_choice_count):
        ordinal = choice_placeholders[index] if index < len(choice_placeholders) else f"choice {index + 1}"
        output_contract_lines.append(f"- {ordinal} specific choice")
    output_contract = "\n".join(output_contract_lines)

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": "\n".join(
                instructions
                + [
                    "",
                    "OUTPUT CONTRACT:",
                    output_contract,
                ]
            ),
        },
        {
            "role": "system",
            "content": "\n".join(
                [
                    f"Title: {story.get('title', '')}",
                    f"Theme: {_normalize_inline_text(story.get('cinematic_theme') or story.get('theme'))}",
                    f"Setting: {setting_text}",
                    f"Current location: {scene_location}",
                    f"Current mood: {scene_mood or 'tense and active'}",
                    f"Action type: {action_type}",
                    f"Benchmark exchange count: {exchange_count}",
                    f"Pacing level: {pacing_level}",
                    f"Current objective: {_normalize_inline_text(story_state.get('current_objective') or story.get('protagonist_objective'))}",
                    f"Current tension: {_normalize_inline_text(story_state.get('current_tension'))}",
                    f"Immediate stakes: {_normalize_inline_text(story_state.get('immediate_stakes'))}",
                    "",
                    "RELEVANT MEMORY:",
                    "\n".join(memory_lines) if memory_lines else "- None yet.",
                    "",
                    "VISIBLE REPLY THAT MUST STAY UNCHANGED:",
                    visible_reply or "(No visible reply captured.)",
                ]
            ),
        },
    ]

    recent_messages = current_scene.get("messages", []) or []
    for message in recent_messages[-8:]:
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        char_id = message.get("character_id")
        if message.get("type") == "system":
            messages.append({"role": "system", "content": f"Scene note: {content}"})
            continue
        speaker = character_map.get(char_id, {}).get("name", char_id or "Unknown")
        role = "user" if char_id == protagonist.get("id") else "assistant"
        messages.append({"role": role, "content": f"{speaker}: {content}"})

    messages.append(
        {
            "role": "user",
            "content": f"{protagonist.get('name', 'You')}: {user_input}",
        }
    )
    if visible_reply:
        messages.append(
            {
                "role": "assistant",
                "content": f"{responder_name}: {visible_reply}",
            }
        )
    messages.append(
        {
            "role": "user",
            "content": "Generate the repaired branching choices now. Return only the tagged choices block.",
        }
    )
    return messages


def _repair_benchmark_choices_if_needed(
    story: Dict[str, Any],
    protagonist: Dict[str, Any],
    generation: Dict[str, Any],
    user_input: str,
    action_type: str,
    exchange_count: int,
    pacing_level: int,
    speed_profile,
    conclusion_countdown: int,
    story_model: str,
) -> Dict[str, Any]:
    allow_end_choice = can_offer_end_story_choice(story, conclusion_countdown)
    target_choice_count = max(speed_profile.max_choices or 3, 2)
    fallback_choices = _fallback_benchmark_choices(
        generation,
        exchange_count,
        conclusion_countdown,
        allow_end_choice,
    )
    _, fallback_only = _resolve_benchmark_choice_texts(
        generation.get("suggested_choices") or [],
        fallback_choices,
        target_choice_count,
        allow_end_choice,
    )
    if not fallback_only:
        return generation

    logger.info(
        "Benchmark choice repair triggered because the turn resolved to fallback-only options.",
        extra={"story_id": story.get("id"), "exchange_count": exchange_count},
    )
    retry_messages = _build_benchmark_choice_repair_messages(
        story=story,
        protagonist=protagonist,
        generation=generation,
        user_input=user_input,
        action_type=action_type,
        exchange_count=exchange_count,
        pacing_level=pacing_level,
        fallback_choices=fallback_choices,
        target_choice_count=target_choice_count,
        allow_end_choice=allow_end_choice,
    )
    retry_response = get_llm_completion(
        messages=retry_messages,
        model=story_model,
        task="story",
        trace_context=_build_story_trace_context(
            story,
            "benchmark_choice_repair",
            "story",
            metadata={
                "action_type": action_type,
                "exchange_count": exchange_count,
                "pacing_level": pacing_level,
                "story_mode": speed_profile.story_mode,
                "repair_reason": "fallback_only_choices",
            },
        ),
    )
    if retry_response.get("error"):
        logger.warning("Benchmark choice repair failed: %s", retry_response["error"])
        return generation

    repaired_choices = _parse_benchmark_choice_lines(retry_response.get("content", ""))
    resolved_repair_choices, repair_fallback_only = _resolve_benchmark_choice_texts(
        repaired_choices,
        fallback_choices,
        target_choice_count,
        allow_end_choice,
    )
    if not resolved_repair_choices or repair_fallback_only:
        logger.info("Benchmark choice repair did not improve the fallback choices; keeping original fallback set.")
        return generation

    repaired_generation = dict(generation)
    repaired_generation["suggested_choices"] = resolved_repair_choices
    repaired_generation["choice_retry_used"] = True
    return repaired_generation


def _build_benchmark_advance_data(
    story: Dict[str, Any],
    generation: Dict[str, Any],
    exchange_count: int,
    speed_profile,
    conclusion_countdown: int = 0,
) -> Dict[str, Any]:
    response_text = generation.get("assistant_text") or "The moment tightens, and someone finally says the thing that changes the scene."
    response_text, response_render_mode = _build_visible_turn_content(
        response_text,
        preferred_mode="rp_mixed",
    )
    allow_end_choice = can_offer_end_story_choice(story, conclusion_countdown)
    target_choice_count = max(speed_profile.max_choices or 3, 2)
    fallback_choices = _fallback_benchmark_choices(
        generation,
        exchange_count,
        conclusion_countdown,
        allow_end_choice,
    )
    raw_choices, _ = _resolve_benchmark_choice_texts(
        generation.get("suggested_choices") or [],
        fallback_choices,
        target_choice_count,
        allow_end_choice,
    )
    choice_dicts = []
    for index, cleaned in enumerate(raw_choices[:target_choice_count]):
        if not cleaned:
            continue
        choice_dicts.append(
            {
                "id": _choice_to_id(cleaned, index),
                "text": cleaned,
                "dramatic_impact": "Pushes the benchmark story into a concrete next beat.",
                "visual_representation": "A direct, high-momentum decision point.",
            }
        )

    if allow_end_choice and generation.get("ending_ready") and not any(
        choice.get("text", "").strip().lower() == "end the story now"
        for choice in choice_dicts
    ):
        end_choice = {
            "id": "end_the_story_now",
            "text": "End the story now",
            "dramatic_impact": "Immediately concludes the narrative with a clear resolution.",
            "visual_representation": "A final decision held in sharp relief.",
        }
        if len(choice_dicts) >= target_choice_count:
            choice_dicts[-1] = end_choice
        else:
            choice_dicts.append(end_choice)

    emotional_beat = generation.get("emotional_beat") or "The scene sharpens with clear momentum."
    latest_reveal = generation.get("latest_reveal") or ""
    current_scene = _as_mapping(story.get("current_scene"))
    story_state_source = _as_mapping(story.get("story_state"))
    current_location = current_scene.get("location") or current_scene.get("setting") or _format_setting_text(story.get("setting"))
    next_location = generation.get("next_location") or current_location
    transition_flag = generation.get("scene_shift")
    transition_required = _parse_bool_tag(transition_flag) if isinstance(transition_flag, str) else bool(transition_flag)
    act_advance_flag = generation.get("act_advance")
    ending_ready_flag = generation.get("ending_ready")
    story_state = {
        "current_objective": generation.get("objective") or story_state_source.get("current_objective") or story.get("protagonist_objective") or "Move toward the next concrete objective.",
        "current_tension": generation.get("tension") or story_state_source.get("current_tension") or "Something important is still being held back.",
        "immediate_stakes": generation.get("immediate_stakes") or story_state_source.get("immediate_stakes") or "If the moment slips, the strongest lead may disappear.",
        "location_status": generation.get("location_status") or str(next_location),
        "relationship_shift": generation.get("relationship_shift") or story_state_source.get("relationship_shift", ""),
        "latest_reveal": latest_reveal,
        "emotional_beat": emotional_beat,
    }

    advance_data = {
        "cinematic_responses": [
            {
                "character_id": generation.get("character_id"),
                "dialogue": response_text,
                "delivery": emotional_beat,
                "action": "",
                "direction": "",
                "render_mode": response_render_mode,
            }
        ],
        "npc_reply_expected": True,
        "act_advance": _parse_bool_tag(act_advance_flag) if isinstance(act_advance_flag, str) else bool(act_advance_flag),
        "ending_ready": _parse_bool_tag(ending_ready_flag) if isinstance(ending_ready_flag, str) else bool(ending_ready_flag),
        "new_choices": choice_dicts,
        "scene_update": {"emotional_tone": emotional_beat},
        "story_state": story_state,
        "scene_elements": {
            "atmosphere": emotional_beat,
            "visual_details": [],
            "symbolic_motifs": [],
        },
        "scene_dynamics": {
            "transition_required": transition_required,
            "new_location": next_location if transition_required else "",
            "time_progression": "moments later" if transition_required else "",
            "narrative_advancement": latest_reveal or story_state["current_objective"],
            "scene_transition_caption": f"MOMENTS LATER - {str(next_location).upper()}" if transition_required else "",
        },
        "hidden_elements": {
            "easter_egg": "",
            "foreshadowing": latest_reveal,
        },
    }
    return advance_data


def _sync_benchmark_state_to_context(
    story_id: str,
    context_manager,
    story: Dict[str, Any],
    advance_data: Dict[str, Any],
    npc_content: str,
) -> None:
    state = context_manager.story_states.get(story_id)
    if not state:
        return

    story_state = _as_mapping(advance_data.get("story_state"))
    emotional_tone = _as_mapping(advance_data.get("scene_update")).get("emotional_tone", "")
    latest_reveal = _normalize_inline_text(story_state.get("latest_reveal"))
    current_tension = _normalize_inline_text(story_state.get("current_tension"))
    state.what_just_happened = _normalize_inline_text(npc_content)[:240]
    state.current_goal = _normalize_inline_text(story_state.get("current_objective") or story.get("protagonist_objective"))
    state.open_tensions = [current_tension] if current_tension else []
    state.active_clues = [latest_reveal] if latest_reveal else []
    state.last_major_turning_point = latest_reveal or _normalize_inline_text(story_state.get("emotional_beat") or emotional_tone)


def _should_schedule_benchmark_state_patch(
    story: Dict[str, Any],
    advance_data: Dict[str, Any],
    exchange_count: int,
) -> bool:
    if story.get("_benchmark_state_patch_inflight"):
        return False
    dynamics = _as_mapping(advance_data.get("scene_dynamics"))
    story_state = _as_mapping(advance_data.get("story_state"))
    if dynamics.get("transition_required"):
        return True
    if exchange_count <= 1:
        return True
    if exchange_count % 2 == 0:
        return True
    return not all(
        _normalize_inline_text(story_state.get(key))
        for key in ("current_objective", "current_tension", "immediate_stakes", "emotional_beat")
    )


async def _refresh_benchmark_state_patch(
    story_id: str,
    context_manager,
    stories_db: Dict[str, Any],
) -> None:
    story = stories_db.get(story_id)
    if not story:
        return

    try:
        protagonist = get_protagonist(story)
        if not protagonist:
            return
        character_map = {char.get("id"): char for char in story.get("characters", []) if char.get("id")}
        recent_messages = [
            message
            for message in (story.get("current_scene", {}).get("messages", []) or [])
            if message.get("type") != "system"
        ][-8:]
        transcript_lines = []
        for message in recent_messages:
            char_id = message.get("character_id")
            speaker = character_map.get(char_id, {}).get("name", char_id or "Unknown")
            transcript_lines.append(f"{speaker}: {message.get('content', '')}")

        messages = [
            {
                "role": "system",
                "content": (
                    "Summarize the current benchmark story turn into compact state JSON. "
                    "Be concrete, concise, and grounded in what just happened."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(
                    [
                        f"Title: {story.get('title', '')}",
                        f"Current act: {(story.get('acts') or [{}])[story.get('current_act', 0)].get('title', '') if story.get('acts') else ''}",
                        f"Location: {story.get('current_scene', {}).get('location') or story.get('current_scene', {}).get('setting') or _format_setting_text(story.get('setting'))}",
                        "Recent transcript:",
                        "\n".join(transcript_lines) if transcript_lines else "(none)",
                        "",
                        "Return JSON with keys:",
                        "what_just_happened, current_goal, open_tensions, active_clues, last_major_turning_point,",
                        "current_objective, current_tension, immediate_stakes, location_status, relationship_shift, latest_reveal, emotional_beat",
                    ]
                ),
            },
        ]
        response = get_llm_completion(
            messages=messages,
            model=story.get("llm_config", {}).get("reflection", settings.get_llm_model("reflection")),
            task="reflection",
            trace_context=_build_story_trace_context(
                story,
                "benchmark_state_patch",
                "reflection",
                metadata={"generation_mode": "chat_native", "story_id": story_id},
            ),
        )
        if response.get("error"):
            return

        parsed = json.loads(extract_json_from_response(response.get("content", "")))
        story_memory = story.setdefault("story_memory", {})
        story_memory.update(
            {
                "what_just_happened": _normalize_inline_text(parsed.get("what_just_happened")) or story_memory.get("what_just_happened", ""),
                "current_goal": _normalize_inline_text(parsed.get("current_goal")) or story_memory.get("current_goal", ""),
                "open_tensions": [item for item in (parsed.get("open_tensions") or []) if _normalize_inline_text(item)][:3],
                "active_clues": [item for item in (parsed.get("active_clues") or []) if _normalize_inline_text(item)][:3],
                "last_major_turning_point": _normalize_inline_text(parsed.get("last_major_turning_point")) or story_memory.get("last_major_turning_point", ""),
            }
        )
        story_state = story.setdefault("story_state", {})
        story_state.update(
            {
                "current_objective": _normalize_inline_text(parsed.get("current_objective")) or story_state.get("current_objective", ""),
                "current_tension": _normalize_inline_text(parsed.get("current_tension")) or story_state.get("current_tension", ""),
                "immediate_stakes": _normalize_inline_text(parsed.get("immediate_stakes")) or story_state.get("immediate_stakes", ""),
                "location_status": _normalize_inline_text(parsed.get("location_status")) or story_state.get("location_status", ""),
                "relationship_shift": _normalize_inline_text(parsed.get("relationship_shift")) or story_state.get("relationship_shift", ""),
                "latest_reveal": _normalize_inline_text(parsed.get("latest_reveal")) or story_state.get("latest_reveal", ""),
                "emotional_beat": _normalize_inline_text(parsed.get("emotional_beat")) or story_state.get("emotional_beat", ""),
            }
        )
        story["state_freshness"] = "live"
        story["state_updated_at"] = datetime.now().isoformat()

        state = context_manager.story_states.get(story_id)
        if state:
            state.what_just_happened = story_memory.get("what_just_happened", "")
            state.current_goal = story_memory.get("current_goal", "")
            state.open_tensions = story_memory.get("open_tensions", [])
            state.active_clues = story_memory.get("active_clues", [])
            state.last_major_turning_point = story_memory.get("last_major_turning_point", "")
    except Exception as exc:
        logger.warning(f"[Benchmark State Patch] Failed for story {story_id}: {exc}")
    finally:
        latest_story = stories_db.get(story_id)
        if latest_story is not None:
            latest_story["_benchmark_state_patch_inflight"] = False


def _limit_branching_choices(
    choices: List[Dict[str, Any]],
    max_choices: Optional[int],
) -> List[Dict[str, Any]]:
    if max_choices is None or max_choices <= 0:
        return choices
    limited_choices = list(choices[:max_choices])
    end_choice = next(
        (
            choice
            for choice in choices
            if str(choice.get("text", "")).strip().lower() == "end the story now"
        ),
        None,
    )
    if end_choice and not any(
        str(choice.get("text", "")).strip().lower() == "end the story now"
        for choice in limited_choices
    ):
        if limited_choices:
            limited_choices[-1] = end_choice
        else:
            limited_choices.append(end_choice)
    return limited_choices


async def check_plot_progression(story: Dict) -> Dict[str, Any]:
    """
    Use LLM to evaluate whether meaningful plot progression has occurred
    in the last 5 rounds of dialogue (~10 non-system messages).

    Only triggers when there are at least 10 non-system messages in the
    current scene. Returns early with has_progressed=True if there isn't
    enough history to judge.
    """
    messages = story.get("current_scene", {}).get("messages", [])
    non_system_messages = [m for m in messages if m.get("type") != "system"]

    if len(non_system_messages) < 10:
        return {"has_progressed": True, "reasoning": "Not enough history to evaluate", "suggested_development": ""}

    recent = non_system_messages[-10:]
    character_map = {c["id"]: c for c in story.get("characters", []) if "id" in c}

    conversation_lines = []
    for msg in recent:
        char_id = msg.get("character_id", "unknown")
        speaker = character_map.get(char_id, {}).get("name", char_id)
        content = msg.get("content", "")
        conversation_lines.append(f"{speaker}: {content}")

    recent_conversation = "\n".join(conversation_lines)

    check_prompt = prompt_templates.PLOT_PROGRESSION_CHECK_PROMPT.format(
        title=story.get("title", ""),
        theme=story.get("cinematic_theme", story.get("theme", "")),
        recent_conversation=recent_conversation,
    )

    check_messages = [
        {"role": "system", "content": "You are a story analyst. Evaluate plot progression concisely and respond only with JSON."},
        {"role": "user", "content": check_prompt},
    ]
    llm_config = story.get("llm_config", {}) or {}

    response = get_llm_completion(
        messages=check_messages,
        model=llm_config.get("story", settings.get_llm_model("story")),
        task="story",
        trace_context=_build_story_trace_context(
            story,
            "plot_progression_check",
            "story",
            metadata={
                "recent_conversation": recent_conversation,
                "non_system_message_count": len(non_system_messages),
            },
        ),
    )

    if response.get("error"):
        logger.warning(f"[Plot Progression Check] LLM call failed: {response['error']}")
        return {"has_progressed": True, "reasoning": "Check failed", "suggested_development": ""}

    try:
        content = extract_json_from_response(response["content"])
        result = json.loads(content)
        logger.info(
            f"[Plot Progression Check] has_progressed={result.get('has_progressed')}, "
            f"reasoning={result.get('reasoning', '')[:100]}"
        )
        return result
    except Exception as e:
        logger.warning(f"[Plot Progression Check] Failed to parse response: {e}")
        return {"has_progressed": True, "reasoning": "Parse failed", "suggested_development": ""}


def _payload_has_material_shift(advance_data: Dict[str, Any]) -> bool:
    story_state = advance_data.get("story_state", {}) or {}
    dynamics = advance_data.get("scene_dynamics", {}) or {}
    hidden = advance_data.get("hidden_elements", {}) or {}
    elements = advance_data.get("scene_elements", {}) or {}
    responses = advance_data.get("cinematic_responses", []) or []
    if dynamics.get("transition_required") or dynamics.get("new_location") or dynamics.get("scene_transition_caption"):
        return True
    if dynamics.get("narrative_advancement") or hidden.get("foreshadowing") or hidden.get("easter_egg"):
        return True
    if any(story_state.get(key) for key in ["latest_reveal", "relationship_shift", "current_tension", "immediate_stakes"]):
        return True
    if elements.get("visual_details") or elements.get("symbolic_motifs"):
        return True
    if len(responses) >= 2:
        return True
    return False


def _normalize_scene_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _has_real_scene_shift(story: Dict[str, Any], dynamics: Dict[str, Any]) -> bool:
    current_scene = _as_mapping(story.get("current_scene"))
    current_location = _normalize_scene_label(
        current_scene.get("location") or current_scene.get("setting") or _format_setting_text(story.get("setting"))
    )
    next_location = _normalize_scene_label(dynamics.get("new_location"))
    time_progression = _normalize_inline_text(dynamics.get("time_progression"))
    location_changed = bool(next_location and next_location != current_location)
    explicit_time_jump = bool(time_progression)
    return location_changed or explicit_time_jump


def _sanitize_scene_transition_payload(story: Dict[str, Any], advance_data: Dict[str, Any]) -> Dict[str, Any]:
    dynamics = _as_mapping(advance_data.get("scene_dynamics"))
    if not dynamics:
        return advance_data

    sanitized = dict(dynamics)
    if not _has_real_scene_shift(story, sanitized):
        sanitized["transition_required"] = False
        sanitized["new_location"] = ""
        sanitized["time_progression"] = ""
        sanitized["scene_transition_caption"] = ""

    advance_data["scene_dynamics"] = sanitized
    return advance_data


def _structure_shift_flags(story: Dict[str, Any], advance_data: Dict[str, Any]) -> Dict[str, bool]:
    story_state = advance_data.get("story_state", {}) or {}
    current_story_state = story.get("story_state", {}) or {}
    current_scene = story.get("current_scene", {}) or {}
    dynamics = advance_data.get("scene_dynamics", {}) or {}
    hidden = advance_data.get("hidden_elements", {}) or {}

    current_location = str(current_scene.get("location") or current_scene.get("setting") or "").strip().lower()
    next_location = str(dynamics.get("new_location") or "").strip().lower()
    objective = str(story_state.get("current_objective") or "").strip()
    existing_objective = str(current_story_state.get("current_objective") or story.get("protagonist_objective") or "").strip()
    tension_blob = " ".join([
        str(story_state.get("current_tension") or ""),
        str(story_state.get("immediate_stakes") or ""),
        str(dynamics.get("narrative_advancement") or ""),
    ]).lower()

    return {
        "new_reveal": bool(story_state.get("latest_reveal") or hidden.get("foreshadowing") or hidden.get("easter_egg")),
        "location_shift": bool(dynamics.get("transition_required") or (next_location and next_location != current_location)),
        "relationship_shift": bool(story_state.get("relationship_shift")),
        "goal_shift": bool(objective and objective != existing_objective),
        "conflict_escalation": any(
            marker in tension_blob
            for marker in ["risk", "danger", "threat", "urgent", "before", "lose", "break", "exposed", "confront", "pressure"]
        ) or bool(story_state.get("current_tension") and story_state.get("immediate_stakes")),
    }


def _enforce_structure_guard(
    story: Dict[str, Any],
    advance_data: Dict[str, Any],
    progression_count: int,
    speed_profile,
    progression_result: Optional[Dict[str, Any]] = None,
    force_advance: bool = False,
) -> Dict[str, Any]:
    flags = _structure_shift_flags(story, advance_data)
    require_scene_shift = (
        progression_count >= speed_profile.mandatory_shift_start or force_advance
    ) and not flags["location_shift"]
    pressure_level = (
        progression_count >= speed_profile.mandatory_shift_start
        or force_advance
        or not (progression_result or {}).get("has_progressed", True)
    )
    if _payload_has_material_shift(advance_data) and not require_scene_shift and (not pressure_level or any(flags.values())):
        return advance_data

    current_scene = story.get("current_scene", {}) or {}
    current_location = current_scene.get("location") or current_scene.get("setting") or "a newly revealed area"
    fallback_location = current_location if isinstance(current_location, str) else "a newly revealed area"
    characters = story.get("characters", []) or []
    supporting_character = next((char for char in characters if char.get("role") != "protagonist"), None)
    current_act_index = min(max(story.get("current_act", 0), 0), max(len(story.get("acts", [])) - 1, 0)) if story.get("acts") else 0
    current_act = (story.get("acts") or [{}])[current_act_index] if story.get("acts") else {}
    suggested_development = (progression_result or {}).get("suggested_development", "")
    reasoning = (progression_result or {}).get("reasoning", "")
    dynamics = advance_data.setdefault("scene_dynamics", {})
    story_state = advance_data.setdefault("story_state", {})

    if progression_count >= speed_profile.mandatory_shift_start and not flags["location_shift"]:
        story_state["location_status"] = story_state.get("location_status") or (
            f"The pressure inside {fallback_location} becomes impossible to ignore."
        )

    if not flags["new_reveal"]:
        story_state["latest_reveal"] = story_state.get("latest_reveal") or suggested_development or (
            f"A concrete truth surfaces in {current_act.get('title', 'this act') or 'this act'}, ending the stall."
        )

    if not flags["goal_shift"]:
        story_state["current_objective"] = story_state.get("current_objective") or (
            "Act on the newest lead before the moment closes."
        )

    if not flags["conflict_escalation"]:
        story_state["current_tension"] = story_state.get("current_tension") or reasoning or (
            "The scene can no longer stay in reflection; someone must risk a decision, confession, or discovery."
        )
        story_state["immediate_stakes"] = story_state.get("immediate_stakes") or (
            "If no one acts now, the strongest lead may vanish and the emotional pressure will harden into retreat."
        )

    if not flags["relationship_shift"] and supporting_character:
        story_state["relationship_shift"] = story_state.get("relationship_shift") or (
            f"The exchange with {supporting_character.get('name', 'the other character')} changes the emotional balance of the scene."
        )

    story_state["emotional_beat"] = story_state.get("emotional_beat") or "Taut, urgent, and newly exposed."
    dynamics["narrative_advancement"] = dynamics.get("narrative_advancement") or (
        suggested_development
        or "The emotional stalemate breaks and the scene pivots toward a concrete discovery, confrontation, or urgent next move."
    )

    if not advance_data.get("scene_description"):
        advance_data["scene_description"] = (
            f"The energy in {fallback_location} tightens as attention locks onto the next truth waiting inside the same space."
        )

    elements = advance_data.setdefault("scene_elements", {})
    elements["atmosphere"] = elements.get("atmosphere") or "Taut, urgent, and charged with consequence."

    hidden = advance_data.setdefault("hidden_elements", {})
    hidden["foreshadowing"] = hidden.get("foreshadowing") or (
        f"After {progression_count} {speed_profile.pacing_unit} units, the next move is now tied to a reveal or confrontation that cannot be postponed."
    )

    if not advance_data.get("branching_paths"):
        advance_data["branching_paths"] = [
            {
                "id": "push_into_reveal",
                "text": "Follow the strongest lead immediately.",
                "dramatic_impact": "Pushes the story into a concrete reveal or confrontation.",
                "visual_representation": "A tense move toward the source of the scene's pressure.",
            },
            {
                "id": "force_confession",
                "text": "Stop and demand the full truth first.",
                "dramatic_impact": "Turns the moment into a confession that reframes the stakes.",
                "visual_representation": "A close, pressure-filled exchange where someone finally breaks.",
            },
            {
                "id": "investigate_carefully",
                "text": "Study the environment for a hidden clue.",
                "dramatic_impact": "Creates an investigative beat that uncovers the next real lead.",
                "visual_representation": "Slow attention to details as a meaningful clue comes into focus.",
            },
        ]
    return advance_data


async def advance_story(story_id: str, user_input: str, action_type: str, context_manager, stories_db,
                      reflection: Optional[Dict[str, Any]] = None,
                      streaming_queue=None):
    """
    Helper function to advance the story with either a message or a choice,
    leveraging the context management system for richer, more personalized responses.
    
    Args:
        story_id: The ID of the story to advance
        user_input: The user's input (message content or choice text)
        action_type: The type of action ("Message" or "Choice")
        context_manager: The context management system
        stories_db: The stories database
        reflection: Optional reflection data from meta-planner to guide story generation
    
    Returns:
        The updated current scene
    """
    if story_id not in stories_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    
    story = stories_db[story_id]
    user_id = story.get("user_id")
    story_model = story.get("llm_config", {}).get("story", settings.get_llm_model("story"))
    speed_profile = get_story_speed_profile(story=story)
    
    if story["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Story is not active.")

    # Extract target character from user input if specified
    target_character_id = None
    target_character_name = None
    
    # Check if input has the format "@CharacterName: message"
    if action_type.lower() == "message" and "@" in user_input:
        parts = user_input.split(":", 1)
        if len(parts) == 2:
            character_identifier = parts[0].strip()
            if character_identifier.startswith("@"):
                target_name = character_identifier[1:].strip()  # Remove @ symbol
                
                # Try to find the character by name
                for char in story.get("characters", []):
                    if char.get("name", "").lower() == target_name.lower():
                        target_character_id = char.get("id")
                        target_character_name = char.get("name")
                        user_input = parts[1].strip()  # Use only the message part
                        logger.info(f"Detected target character: {target_character_name} (ID: {target_character_id})")
                        break
    
    # 1. Format conversation history and find characters
    history = []
    protagonist = get_protagonist(story)
    
    if not protagonist:
        logger.error(f"CRITICAL: No protagonist found for active story {story_id} during story advancement.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Story is in a corrupted state.")
    
    logger.info(f"--- Advancing Story {story_id} ---")
    logger.info(f"Action Type: {action_type}, User Input: {user_input}")
    logger.info(f"Protagonist for story {story_id} identified as: {protagonist.get('name')} (ID: {protagonist.get('id')})")

    character_map = {c["id"]: c for c in story.get("characters", []) if "id" in c}

    # Build enhanced conversation history from story state
    logger.info(f"Building enhanced message history for LLM prompt (story {story_id})...")
    
    # Track previous choices to explicitly prevent repetition
    previous_choices = []
    previous_locations = set()
    
    for msg in story.get("current_scene", {}).get("messages", []):
        char_id = msg.get("character_id")
        speaker = character_map.get(char_id, {}).get("name", "Unknown")
        content = msg.get('content', '')
        msg_type = msg.get('type', 'text')
        
        # Keep track of choices made by the protagonist
        if char_id == protagonist.get("id") and msg_type == 'choice':
            previous_choices.append(content)
        
        # Extract location mentions (simplified approach)
        if "at the " in content or "in the " in content:
            for location_phrase in re.findall(r"(at|in) the ([a-zA-Z\s]+)", content):
                previous_locations.add(location_phrase[1].strip())
        
        logger.info(f"  - History: Speaker resolved as '{speaker}' (from ID '{char_id}') said: \"{content[:50]}...\"")
        history.append(f"{speaker}: {content}")
    
    # Add metadata about previous interactions to help prevent repetition
    if previous_choices:
        history.append(f"\n[META: Previous choices made by protagonist: {', '.join(previous_choices)}. DO NOT REPEAT THESE OPTIONS.]")
    
    if previous_locations:
        history.append(f"\n[META: Previously mentioned locations: {', '.join(previous_locations)}. Consider moving to a new location.]")
    
    current_scene_messages = story.get("current_scene", {}).get("messages", []) or []
    non_system_count = len([m for m in current_scene_messages if m.get("type") != "system"])
    exchange_count = count_story_exchanges(current_scene_messages)
    progression_count = get_progression_count_for_messages(speed_profile, current_scene_messages)
    pacing_level = build_pacing_level(speed_profile, progression_count)

    if speed_profile.benchmark_speed_profile:
        history.append(f"\n[META: Current benchmark exchange count: {exchange_count}.]")
        history.append(f"\n{_build_benchmark_prompt_guidance(exchange_count)}")
    elif progression_count < speed_profile.acceleration_start:
        history.append("\n[META: IMPORTANT - Ensure steady narrative progression in this response. Introduce new elements or insights.]")
    elif progression_count < speed_profile.critical_start:
        history.append("\n[META: IMPORTANT - Accelerate narrative progression. Introduce new tensions, conflicts or revelations to move the story forward.]")
    elif progression_count < speed_profile.mandatory_shift_start:
        history.append("\n[META: CRITICAL - The scene is becoming prolonged. Introduce significant plot developments, conflicts, or prepare for a scene transition soon.]")
    else:
        excess = progression_count - speed_profile.mandatory_shift_start
        urgency = "URGENT" if excess <= 2 else "EXTREMELY URGENT" if excess <= 5 else "IMMEDIATE MANDATORY ACTION"
        history.append(
            f"\n[META: {urgency} - This scene has continued for too long ({progression_count} {speed_profile.pacing_unit}s). "
            "You MUST implement ONE of these narrative shifts in this response:"
        )
        history.append("1. Change the physical location/scene entirely")
        history.append("2. Introduce a major unexpected event or revelation that dramatically changes the situation")
        history.append("3. Bring in a new character or entity that redirects the narrative")
        history.append("4. Resolve the current tension and establish a new goal/objective")
        history.append("DO NOT JUST HINT AT THESE CHANGES - ACTUALLY IMPLEMENT ONE OF THEM IN THIS RESPONSE.]")
    
    # Add target character directive if specified
    if target_character_id and target_character_name:
        history.append(f"\n[META: IMPORTANT - The protagonist is specifically addressing {target_character_name}. Your response MUST come from this character.]")
    
    conversation_history = "\n".join(history)

    # === LLM-based plot progression check (last 5 rounds) ===
    plot_stagnation_directive = ""
    progression_result: Dict[str, Any] = {"has_progressed": True, "reasoning": "", "suggested_development": ""}
    non_system_msgs = [m for m in current_scene_messages if m.get("type") != "system"]
    if len(non_system_msgs) >= 10 and not speed_profile.skip_optional_llm:
        try:
            progression_result = await check_plot_progression(story)
            if not progression_result.get("has_progressed", True):
                logger.warning(
                    f"[Plot Progression Check] Story {story_id} - stagnation detected: "
                    f"{progression_result.get('reasoning', 'N/A')}"
                )
                suggested = progression_result.get("suggested_development", "")
                plot_stagnation_directive = (
                    "\n\n[CRITICAL PLOT STAGNATION ALERT]\n"
                    "Analysis of the last 5 rounds shows NO meaningful plot progression.\n"
                    f"Reason: {progression_result.get('reasoning', 'Repetitive or circular conversation detected')}\n"
                    + (f"Suggested development: {suggested}\n" if suggested else "")
                    + "\nYOU MUST take IMMEDIATE action to dramatically advance the plot in this response:\n"
                    "1. Introduce a significant NEW event, discovery, or crisis\n"
                    "2. Change the setting or introduce a new character\n"
                    "3. Reveal critical information that changes everything\n"
                    "4. Create a dramatic turning point\n"
                    "\nDO NOT continue the current conversational pattern. BREAK the cycle NOW."
                )
            else:
                logger.info(
                    f"[Plot Progression Check] Story {story_id} - progression confirmed: "
                    f"{progression_result.get('reasoning', 'N/A')[:80]}"
                )
        except Exception as e:
            logger.error(f"[Plot Progression Check] Error during check for story {story_id}: {e}")

    # 2. Get enhanced context from context manager if available
    context_available = False
    enhanced_context = {}
    
    if user_id and story_id in context_manager.story_states and user_id in context_manager.user_profiles:
        try:
            enhanced_context = context_manager.get_full_context(story_id, user_id)
            context_available = True
            logger.info(f"Retrieved enhanced context for story {story_id}, user {user_id}")
        except ValueError as e:
            logger.warning(f"Could not retrieve context from context manager: {e}")
        except Exception as e:
            logger.error(f"Error accessing context manager: {e}")
    
    # 3. Prepare the prompt for the LLM
    emotional_goal = story.get("emotional_goal") or story.get("emotional_undercurrent", "")
    fast_forward_this_turn = False
    if context_available:
        # Create an enhanced prompt using the context manager data
        prompt = """
You are continuing an interactive therapeutic story. Your goal is to generate the next part of the narrative based on the user's latest action.

**STORY CONTEXT:**
- **Title:** {title}
- **Theme:** {theme}
- **Emotional Goal:** {emotional_goal}
- **Setting:** {setting}

**USER PROFILE:**
{user_profile}

**NARRATIVE SUMMARY:**
{narrative_summary}

**EMOTIONAL JOURNEY:**
{emotional_journey}

**CONVERSATION HISTORY (Current Scene):**
{conversation_history}

**USER'S LATEST ACTION:**
- **Action Type:** {action_type}
- **Content:** {user_input}
{target_character}

**YOUR TASK:**
Generate the next part of the story. You must respond as the appropriate character from their perspective. Your response should:
1. **Acknowledge the User's Input:** Directly or indirectly respond to what the user just said or did.
2. **Maintain Character Voice:** Stay true to the character's established personality and role in the story.
3. **Advance the Narrative:** Move the story forward in a meaningful way.
4. **Uphold the Therapeutic Goal:** Keep the story's emotional goal in mind. The interaction should be supportive and insightful.
5. **Reference Past Events:** Occasionally reference previous interactions or decisions when relevant.
6. **Consider the User's Background:** Subtly incorporate knowledge of the user's personal situation.
7. **Match the Emotional Arc:** Align with the user's current emotional state and the therapeutic journey.
8. **Provide New Choices:** Give the user 2-3 new, meaningful choices to continue the interaction. These choices should reflect different emotional paths or reactions.
9. **Update Scene State:** Describe the current emotional tone of the scene after your response.

**IMPORTANT CHARACTER ATTRIBUTION:**
- If the user has specifically addressed a character, ONLY respond as that character.
- If no specific character was addressed, determine the most appropriate character to respond based on the conversation context.
- NEVER speak as multiple characters in a single response. Each response must be from ONE character's perspective only.
- Ensure the character_id in your response matches the character who is speaking.
- NEVER attribute dialogue to "Grandpa Joe" or any other name directly - use the proper character_id.
- Do NOT repeatedly introduce the character by name or role unless this is their first formal entrance or the protagonist explicitly asks who they are.

**OUTPUT FORMAT:**
You MUST respond with a single, valid JSON object that follows this schema. Do not add any extra text or markdown formatting around the JSON.

        {schema}
""".format(
            title=story["title"],
            theme=story.get("cinematic_theme", story.get("theme", "")),
            emotional_goal=emotional_goal,
            setting=story["setting"],
            user_profile=enhanced_context.get("user", {}).get("profile_summary", "No profile available"),
            narrative_summary=enhanced_context.get("current_state", {}).get("narrative_summary", "No summary available"),
            emotional_journey=enhanced_context.get("user_journey", {}).get("journey_summary", "No journey summary available"),
            conversation_history=conversation_history,
            action_type=action_type,
            user_input=user_input,
            target_character=f"\n- **Target Character:** {target_character_name}" if target_character_name else "",
            schema=prompt_templates.STORY_ADVANCEMENT_SCHEMA
        )

        # 检查是否需要强制推进情节
        try:
            state = context_manager.story_states.get(story_id)
            if state and getattr(state, 'force_advance', False):
                prompt += "\n\n[META: The story has not progressed significantly in the last 6 rounds. You MUST introduce a major plot development, new conflict, or dramatic change in the next response. Do NOT repeat previous content. FORCE NARRATIVE PROGRESSION.]"
                state.force_advance = False  # 重置标志
                fast_forward_this_turn = True
                logger.info(f"[Force Advance] Injected force progression meta into prompt for story {story_id}")
            # 在提示中注入结局倒计时信息
            if state and getattr(state, 'conclusion_countdown', 0) > 0:
                remaining = int(state.conclusion_countdown)
                prompt += f"\n\n[META: Conclusion countdown active. You MUST conclude the story within {remaining} turn(s). Provide at least one explicit choice that immediately ends the story (e.g., 'End the story now'), and ensure ALL choices clearly advance toward resolution.]"
        except Exception as e:
            logger.error(f"[Force Advance] Error checking or resetting force_advance flag: {e}")
    else:
        # Use the standard prompt template if enhanced context is not available
        prompt = prompt_templates.STORY_ADVANCEMENT_PROMPT.format(
            title=story["title"],
            theme=story.get("cinematic_theme", story.get("theme", "")),
            emotional_goal=emotional_goal,
            characters=json.dumps(story["characters"]),
            setting=story["setting"],
            conversation_history=conversation_history,
            action_type=action_type,
            user_input=user_input,
            target_character_directive=f"\n- **Target Character:** {target_character_name}" if target_character_name else "",
            schema=prompt_templates.STORY_ADVANCEMENT_SCHEMA
        )
        # 非上下文分支同样注入倒计时提示
        try:
            state = context_manager.story_states.get(story_id)
            if state and getattr(state, 'conclusion_countdown', 0) > 0:
                remaining = int(state.conclusion_countdown)
                prompt += f"\n\n[META: Conclusion countdown active. You MUST conclude the story within {remaining} turn(s). Provide at least one explicit choice that immediately ends the story (e.g., 'End the story now'), and ensure ALL choices clearly advance toward resolution.]"
        except Exception as e:
            logger.error(f"[Countdown META] Error injecting countdown directive: {e}")
    
    # 如果提供了反思数据，将其添加到提示中
    if reflection:
        logger.info(f"Incorporating reflection data into story advancement prompt for story {story_id}")
        logger.info(f"--- REFLECTION DATA ---\n{json.dumps(reflection, indent=2)}")
        
        # 将反思数据添加到提示中
        prompt += "\n\n**STORY REFLECTION GUIDANCE:**\n"
        
        if reflection.get("plot_status"):
            prompt += f"\nCurrent Plot: {reflection.get('plot_status')}"
            
        if reflection.get("user_choice_analysis"):
            prompt += f"\nUser Interest: {reflection.get('user_choice_analysis')}"
            
        if reflection.get("story_advancement_strategy"):
            prompt += f"\nAdvancement Strategy: {reflection.get('story_advancement_strategy')}"
        
        # 添加基于pacing_level的特定指导
        pacing_data = reflection.get("pacing_data", {})
        if pacing_data:
            pacing_level = pacing_data.get("level", 0)
            pacing_count = pacing_data.get("progression_count")
            if pacing_count is None:
                pacing_count = pacing_data.get("exchange_count") or pacing_data.get("dialogue_count", 0)
            pacing_unit = pacing_data.get("progression_unit", "dialogue")
            
            prompt += f"\n\n**PACING DIRECTIVE (Level {pacing_level}):**"
            
            if pacing_level == 0:
                prompt += "\nMAINTAIN CURRENT PACE: Normal story progression is acceptable."
            elif pacing_level == 1:
                prompt += "\nACCELERATE STORY: Begin introducing new elements or increase tension."
                prompt += f"\nNote: Current {pacing_unit} count is {pacing_count}, approaching threshold."
            elif pacing_level == 2:
                prompt += "\nCRITICAL POINT: You SHOULD prepare for a scene transition or major development."
                prompt += f"\nNote: Current {pacing_unit} count is {pacing_count}, very close to threshold."
            elif pacing_level == 3:
                prompt += "\nMANDATORY CHANGE: You MUST implement a scene transition or major plot event NOW."
                prompt += f"\nNote: Current {pacing_unit} count is {pacing_count}, exceeded threshold."
            elif pacing_level >= 4:
                prompt += "\nEMERGENCY INTERVENTION: IMMEDIATE dramatic narrative shift required."
                prompt += f"\nNote: Current {pacing_unit} count is {pacing_count}, severely exceeded threshold."
                prompt += "\nYou MUST use ONE of these methods to dramatically shift the narrative:"
                prompt += "\n1. Change physical location entirely (new scene)"
                prompt += "\n2. Introduce a shocking revelation or unexpected event"
                prompt += "\n3. Bring in a new character who changes everything"
                prompt += "\n4. Resolve current conflict and establish entirely new objective"
        
        prompt += "\n\nUse this reflection to optimize your response. Focus on advancing the story in a way that aligns with the user's interests and maintains engagement."
    
    # Inject plot stagnation directive if LLM-based check detected no progression
    if plot_stagnation_directive:
        prompt += plot_stagnation_directive
        logger.info(f"[Plot Progression Check] Injected stagnation directive into prompt for story {story_id}")

    benchmark_generation: Optional[Dict[str, Any]] = None
    if speed_profile.benchmark_speed_profile:
        messages = _build_benchmark_chat_native_messages(
            story=story,
            protagonist=protagonist,
            user_input=user_input,
            action_type=action_type,
            exchange_count=exchange_count,
            pacing_level=pacing_level,
            target_character_id=target_character_id,
            target_character_name=target_character_name,
        )
        story_trace_context = _build_story_trace_context(
            story,
            "benchmark_main_generation",
            "story",
            metadata={
                "action_type": action_type,
                "user_input": user_input,
                "target_character_id": target_character_id,
                "target_character_name": target_character_name,
                "dialogue_count": non_system_count,
                "exchange_count": exchange_count,
                "pacing_level": pacing_level,
                "story_mode": speed_profile.story_mode,
                "generation_mode": "chat_native",
                "streaming": streaming_queue is not None,
            },
        )
    else:
        messages = [{"role": "system", "content": prompt_templates.SYSTEM_PROMPT}, 
                    {"role": "user", "content": prompt}]
        story_trace_context = _build_story_trace_context(
            story,
            "story_advance",
            "story",
            metadata={
                "action_type": action_type,
                "user_input": user_input,
                "target_character_id": target_character_id,
                "target_character_name": target_character_name,
                "dialogue_count": non_system_count,
                "exchange_count": exchange_count,
                "pacing_level": pacing_level,
                "story_mode": speed_profile.story_mode,
                "has_reflection": bool(reflection),
                "streaming": streaming_queue is not None,
            },
        )

    # 4. Call LLM
    logger.info(f"Calling story model ({story_model}) for story advancement")

    if streaming_queue is not None:
        # Streaming mode: feed dialogue chars into the queue as they arrive
        loop = asyncio.get_event_loop()
        extractor = BenchmarkTaggedStreamExtractor() if speed_profile.benchmark_speed_profile else DialogueStreamExtractor()

        def _on_chunk(text: str) -> None:
            dialogue_fragment = extractor.feed(text)
            if dialogue_fragment:
                try:
                    loop.call_soon_threadsafe(
                        streaming_queue.put_nowait,
                        {"type": "delta", "text": dialogue_fragment},
                    )
                except Exception:
                    pass

        full_content = await asyncio.to_thread(
            stream_story_completion_sync,
            messages,
            story_model,
            _on_chunk,
            "story",
            story_trace_context,
        )
        if speed_profile.benchmark_speed_profile:
            trailing_fragment = extractor.finalize()
            if trailing_fragment:
                try:
                    await streaming_queue.put({"type": "delta", "text": trailing_fragment})
                except Exception:
                    pass
        response = {
            "content": full_content,
            "error": None if full_content else "Streaming produced empty response",
        }
    else:
        response = get_llm_completion(
            messages=messages,
            model=story_model,
            task="story",
            trace_context=story_trace_context,
        )

    if response["error"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response["error"])
        
    try:
        if speed_profile.benchmark_speed_profile:
            benchmark_generation = _parse_benchmark_main_generation(
                response["content"],
                story=story,
                protagonist=protagonist,
                target_character_id=target_character_id,
            )
            story_state = context_manager.story_states.get(story_id)
            conclusion_countdown = getattr(story_state, "conclusion_countdown", story.get("conclusion_countdown", 0))
            benchmark_generation = _repair_benchmark_choices_if_needed(
                story=story,
                protagonist=protagonist,
                generation=benchmark_generation,
                user_input=user_input,
                action_type=action_type,
                exchange_count=exchange_count,
                pacing_level=pacing_level,
                speed_profile=speed_profile,
                conclusion_countdown=conclusion_countdown,
                story_model=story_model,
            )
            advance_data = _build_benchmark_advance_data(
                story=story,
                generation=benchmark_generation,
                exchange_count=exchange_count,
                speed_profile=speed_profile,
                conclusion_countdown=conclusion_countdown,
            )
        else:
            advance_data = parse_json_response(
                response["content"],
                task="story",
                model=story_model,
                trace_context=_build_story_trace_context(
                    story,
                    "json_repair",
                    "story",
                    metadata={
                        "upstream_source": "story_advance",
                        "action_type": action_type,
                    },
                ),
            )
            advance_data = validate_story_advancement_payload(advance_data, story)
    except (ValueError, json.JSONDecodeError, TypeError) as e:
        logger.error(f"Failed to parse LLM response for story advancement: {response['content']}")
        # ---- Robust Fallback --------------------------------------------------
        # Never leak raw JSON / malformed payloads into the chat UI.
        logger.warning("Falling back to safe narrative mode for this turn of story advancement.")
        fallback_line = "The room goes quiet for a beat, as if everyone is weighing what this means before speaking again."
        if speed_profile.benchmark_speed_profile:
            benchmark_generation = _parse_benchmark_main_generation(
                response.get("content", ""),
                story=story,
                protagonist=protagonist,
                target_character_id=target_character_id,
            )
            story_state = context_manager.story_states.get(story_id)
            conclusion_countdown = getattr(story_state, "conclusion_countdown", story.get("conclusion_countdown", 0))
            if benchmark_generation.get("assistant_text"):
                fallback_line = benchmark_generation["assistant_text"]
            benchmark_generation = _repair_benchmark_choices_if_needed(
                story=story,
                protagonist=protagonist,
                generation=benchmark_generation,
                user_input=user_input,
                action_type=action_type,
                exchange_count=exchange_count,
                pacing_level=pacing_level,
                speed_profile=speed_profile,
                conclusion_countdown=conclusion_countdown,
                story_model=story_model,
            )
            advance_data = _build_benchmark_advance_data(
                story=story,
                generation=benchmark_generation,
                exchange_count=exchange_count,
                speed_profile=speed_profile,
                conclusion_countdown=conclusion_countdown,
            )
        else:
            if len(response.get("content", "")) < 280 and not any(ch in response.get("content", "") for ch in "{}[]"):
                fallback_line = response["content"].strip() or fallback_line
            advance_data = {
                "cinematic_responses": [
                    {
                        "character_id": protagonist["id"],
                        "dialogue": fallback_line
                    }
                ],
                "npc_reply_expected": False
            }
        # NOTE: 不再 raise 异常，以便后续逻辑继续执行。

    state_for_guard = context_manager.story_states.get(story_id) if story_id in context_manager.story_states else None
    dialogue_count_for_guard = (
        state_for_guard.dialogue_counter
        if state_for_guard is not None
        else non_system_count
    )
    progression_count_for_guard = (
        dialogue_count_for_guard // 2
        if speed_profile.pacing_unit == "exchange"
        else dialogue_count_for_guard
    )
    if progression_count_for_guard >= speed_profile.structure_guard_start or (state_for_guard and state_for_guard.force_advance):
        advance_data = _enforce_structure_guard(
            story,
            advance_data,
            progression_count_for_guard,
            speed_profile,
            progression_result=progression_result,
            force_advance=bool(state_for_guard and state_for_guard.force_advance),
        )
    advance_data = _sanitize_scene_transition_payload(story, advance_data)

    # 5. Update story state
    # Add user's message/choice to history
    user_content, user_render_mode = _build_visible_turn_content(
        user_input,
        preferred_mode="plain",
    )
    user_message = {
        "id": f"msg-{uuid.uuid4()}",
        "character_id": protagonist["id"],
        "content": user_content or str(user_input),
        "timestamp": datetime.now().isoformat(),
        "type": action_type.lower(),
        "render_mode": user_render_mode,
    }
    logger.info(f"Adding user action to story {story_id}: Type='{action_type}', CharID='{protagonist['id']}'")
    story["current_scene"]["messages"].append(user_message)

    # -------- Dialogue counting and profile-based conclusion countdown --------
    try:
        if story_id in context_manager.story_states:
            # Record the user's message in context and increment dialogue counter
            context_manager.process_message(
                story_id=story_id,
                character_id=protagonist["id"],
                content=user_input,
                message_type=action_type.lower(),
                emotion="",
                llm_model=story_model,
            )
            state = context_manager.story_states.get(story_id)
            if state and state.conclusion_countdown == 0:
                state_progression_count = (
                    state.dialogue_counter // 2
                    if speed_profile.pacing_unit == "exchange"
                    else state.dialogue_counter
                )
                if speed_profile.benchmark_speed_profile and not has_scene_transition_occurred(story):
                    state_progression_count = -1
                if state_progression_count >= speed_profile.conclusion_start:
                    state.conclusion_countdown = speed_profile.conclusion_countdown_turns
                    logger.warning(
                        "[Conclusion Countdown] Started %s-turn countdown for story %s after %s %s units",
                        speed_profile.conclusion_countdown_turns,
                        story_id,
                        state_progression_count,
                        speed_profile.pacing_unit,
                    )
    except Exception as e:
        logger.error(f"[Conclusion Countdown] Failed to update dialogue counter or start countdown: {e}")

    # If a target character was specified, ensure the response comes from that character
    if target_character_id and "cinematic_responses" in advance_data and advance_data["cinematic_responses"]:
        first_response = advance_data["cinematic_responses"][0]
        if first_response.get("character_id") != target_character_id:
            logger.warning(f"LLM responded with wrong character (got {first_response.get('character_id')}, expected {target_character_id}). Fixing attribution.")
            first_response["character_id"] = target_character_id

    # Check if there's a scene description and add it as a system message
    if "scene_description" in advance_data and advance_data["scene_description"]:
        scene_desc = advance_data["scene_description"]
        story["current_scene"]["description"] = scene_desc
        scene_message = {
            "id": f"scene-{uuid.uuid4()}",
            "character_id": "system",
            "content": scene_desc,
            "timestamp": datetime.now().isoformat(),
            "type": "system",
            "render_mode": _detect_render_mode(scene_desc, "plain"),
        }
        logger.info(f"Adding scene description to chat history: {scene_desc[:50]}...")
        story["current_scene"]["messages"].append(scene_message)
    
    # If the action type is "Choice", we need to transform it into a proper dialogue
    # by generating the protagonist's actual spoken words based on the choice
    if action_type.lower() == "choice":
        # Get the first cinematic response if it exists and is from the protagonist
        protagonist_response = None
        if "cinematic_responses" in advance_data and advance_data["cinematic_responses"]:
            first_response = advance_data["cinematic_responses"][0]
            if first_response.get("character_id") == protagonist["id"]:
                protagonist_response = first_response
                # Remove it from the list so we don't add it twice
                advance_data["cinematic_responses"] = advance_data["cinematic_responses"][1:]
        
        # If we found a protagonist response in the cinematic_responses, use it
        if protagonist_response:
            protagonist_content, protagonist_render_mode = _build_visible_turn_content(
                protagonist_response.get("dialogue", ""),
                action=protagonist_response.get("action", ""),
                direction=protagonist_response.get("direction", ""),
                preferred_mode=protagonist_response.get("render_mode", "plain"),
            )
            protagonist_dialogue = {
                "id": f"msg-{uuid.uuid4()}",
                "character_id": protagonist["id"],
                "content": protagonist_content,
                "timestamp": datetime.now().isoformat(),
                "type": "text",
                "delivery": protagonist_response.get("delivery", ""),
                "action": protagonist_response.get("action", ""),
                "direction": protagonist_response.get("direction", ""),
                "render_mode": protagonist_render_mode,
            }
            logger.info(f"Adding protagonist dialogue to story {story_id} from cinematic_responses")
            story["current_scene"]["messages"].append(protagonist_dialogue)
            if story_id in context_manager.story_states:
                try:
                    context_manager.process_message(
                        story_id=story_id,
                        character_id=protagonist["id"],
                        content=protagonist_dialogue["content"],
                        message_type="text",
                        emotion=advance_data.get("scene_update", {}).get("emotional_tone", ""),
                        llm_model=story_model,
                    )
                except Exception as e:
                    logger.error(f"Failed to add protagonist dialogue to context manager: {e}")
    
    # Add NPC's response to history
    npc_expected_flag = advance_data.get("npc_reply_expected", True)

    # Collect NPC replies (array preferred, fallback to single object)
    responses_raw = advance_data.get("cinematic_responses")
    if responses_raw is None:
        single = advance_data.get("npc_response") or advance_data.get("cinematic_response")
        responses_raw = [single] if single else []

    # 添加角色ID规范化的辅助函数，确保在处理每个响应前调用
    def ensure_valid_character_id(char_id, character_map, protagonist):
        """确保角色ID有效，如果无效则尝试修复"""
        if not char_id or char_id in character_map:
            return char_id
        
        # 创建名称到ID的映射
        character_name_to_id = {}
        for c in character_map.values():
            if "name" in c:
                # 添加规范化名称映射
                normalized_name = normalize_character_id(c.get("name", ""))
                character_name_to_id[normalized_name] = c["id"]
                # 添加原始名称映射（小写）
                character_name_to_id[c.get("name", "").lower()] = c["id"]
                # 添加无空格名称映射
                character_name_to_id[c.get("name", "").lower().replace(" ", "")] = c["id"]
        
        # 尝试匹配
        if isinstance(char_id, str):
            # 1. 直接匹配小写名称
            if char_id.lower() in character_name_to_id:
                correct_id = character_name_to_id[char_id.lower()]
                logger.warning(f"Character ID correction: '{char_id}' -> '{correct_id}' (by lowercase name)")
                return correct_id
                
            # 2. 匹配规范化名称
            normalized_id = normalize_character_id(char_id)
            if normalized_id in character_name_to_id:
                correct_id = character_name_to_id[normalized_id]
                logger.warning(f"Character ID correction: '{char_id}' -> '{correct_id}' (by normalized name)")
                return correct_id
                
            # 3. 匹配无空格名称
            no_space_id = char_id.lower().replace(" ", "")
            if no_space_id in character_name_to_id:
                correct_id = character_name_to_id[no_space_id]
                logger.warning(f"Character ID correction: '{char_id}' -> '{correct_id}' (by no-space name)")
                return correct_id
                
            # 4. 特殊情况：主角
            if char_id == "protagonist" or "protagonist" in char_id.lower():
                logger.warning(f"Character ID correction: '{char_id}' -> '{protagonist['id']}' (protagonist special case)")
                return protagonist["id"]
            
            # 5. 部分匹配：检查ID是否是某个角色名称的一部分
            for name, id in character_name_to_id.items():
                if name in char_id.lower() or char_id.lower() in name:
                    logger.warning(f"Character ID correction: '{char_id}' -> '{id}' (partial name match)")
                    return id
                
        # 默认返回第一个NPC或主角
        first_npc = next((c["id"] for c in character_map.values() 
                         if c.get("role") in ["npc", "supporting", "mentor", "antagonist"]), 
                         protagonist["id"])
        logger.warning(f"Invalid character ID '{char_id}', using '{first_npc}' instead (fallback)")
        return first_npc

    # Fallback: if expected but none provided
    if npc_expected_flag and len(responses_raw) == 0:
        fallback_npc = next((c for c in story.get("characters", []) if c.get("role") != "protagonist"), None)
        if fallback_npc:
            responses_raw = [{
                "character_id": fallback_npc["id"],
                "dialogue": "She pauses, then nods: \"Alright, let's take a closer look together.\""
            }]

    # Iterate through responses and add to scene
    for resp in responses_raw:
        if not resp:
            continue
            
        # Check if this is a scene description (first response and contains environmental details)
        is_scene_description = False
        if resp == responses_raw[0] and "action" in resp and resp.get("action"):
            action_text = resp.get("action", "").lower()
            # Check if this seems to be a scene description
            scene_keywords = ["surrounding", "environment", "room", "area", "space", "location", "scene", "setting"]
            if any(keyword in action_text for keyword in scene_keywords):
                is_scene_description = True
                # Add the scene description as a system message
                scene_desc = resp.get("action", "")
                if scene_desc:
                    scene_message = {
                        "id": f"scene-{uuid.uuid4()}",
                        "character_id": "system",
                        "content": scene_desc,
                        "timestamp": datetime.now().isoformat(),
                        "type": "system",
                        "render_mode": _detect_render_mode(scene_desc, "plain"),
                    }
                    logger.info(f"Adding scene description to chat history")
                    story["current_scene"]["messages"].append(scene_message)
        
        # If this was just a scene description, don't add it as character dialogue
        if is_scene_description:
            continue
            
        # 使用辅助函数确保角色ID有效
        npc_char_id = ensure_valid_character_id(resp.get("character_id"), character_map, protagonist)
        resp["character_id"] = npc_char_id  # 更新响应中的角色ID
        
        npc_content = resp.get("content") or resp.get("dialogue", "")
        
        # Verify character_name matches the character_id
        character_name = resp.get("character_name", "")
        expected_name = character_map.get(npc_char_id, {}).get("name", "")
        
        if character_name and expected_name and character_name != expected_name:
            logger.warning(f"Character name mismatch: ID '{npc_char_id}' should be '{expected_name}' but was '{character_name}'. Fixing attribution.")
            # Update the response with the correct character name
            resp["character_name"] = expected_name
            
        npc_content, npc_render_mode = _build_visible_turn_content(
            npc_content,
            action=resp.get("action", ""),
            direction=resp.get("direction", ""),
            preferred_mode=resp.get("render_mode", "plain"),
        )

        npc_message = {
            "id": f"msg-{uuid.uuid4()}",
            "character_id": npc_char_id,
            "content": npc_content,
            "timestamp": datetime.now().isoformat(),
            "type": "text",
            "delivery": resp.get("delivery", ""),
            "action": resp.get("action", ""),
            "direction": resp.get("direction", ""),
            "render_mode": npc_render_mode,
        }
        logger.info(f"Adding NPC response to story {story_id}: CharID='{npc_char_id}'")
        story["current_scene"]["messages"].append(npc_message)
        
        # Also process this message in the context manager
        if story_id in context_manager.story_states:
            try:
                context_manager.process_message(
                    story_id=story_id, 
                    character_id=npc_char_id,
                    content=npc_content,
                    emotion=advance_data.get("scene_update", {}).get("emotional_tone", ""),
                    llm_model=story_model,
                )
                logger.info(f"Added NPC response to context manager for story {story_id}")
            except Exception as e:
                logger.error(f"Failed to add NPC response to context manager: {e}")

    # Handle emotional tone / atmosphere
    if "scene_update" in advance_data and advance_data["scene_update"].get("emotional_tone"):
        story["current_scene"]["emotional_tone"] = advance_data["scene_update"].get("emotional_tone")
    elif "scene_dynamics" in advance_data and advance_data["scene_dynamics"].get("atmosphere"):
        story["current_scene"]["emotional_tone"] = advance_data["scene_dynamics"].get("atmosphere")

    if advance_data.get("scene_elements"):
        story["current_scene"]["scene_elements"] = advance_data["scene_elements"]

    if advance_data.get("hidden_elements"):
        story["current_scene"]["hidden_elements"] = advance_data["hidden_elements"]
        story["hidden_elements"] = advance_data["hidden_elements"]

    dynamics = _as_mapping(advance_data.get("scene_dynamics"))
    has_real_scene_transition = _has_real_scene_shift(story, dynamics)
    current_location = _normalize_scene_label(
        story["current_scene"].get("location") or story["current_scene"].get("setting") or _format_setting_text(story.get("setting"))
    )

    if dynamics:
        story["current_scene"]["scene_dynamics"] = dynamics
        next_location = _normalize_inline_text(dynamics.get("new_location"))
        if has_real_scene_transition and next_location and _normalize_scene_label(next_location) != current_location:
            story["current_scene"]["location"] = next_location

    if advance_data.get("story_state"):
        existing_story_state = story.setdefault("story_state", {})
        for key, value in (advance_data.get("story_state") or {}).items():
            if isinstance(value, str) and value.strip():
                existing_story_state[key] = value.strip()
        story["current_scene"]["story_state"] = dict(existing_story_state)

    # Handle scene transition caption if provided
    scene_transition_added = False
    story["current_scene"]["scene_transition_caption"] = ""
    
    if has_real_scene_transition and dynamics.get("scene_transition_caption"):
        story["current_scene"]["scene_transition_caption"] = dynamics.get("scene_transition_caption")
        story["current_scene"]["scene_dynamics"] = dynamics
        next_location = _normalize_inline_text(dynamics.get("new_location"))
        if next_location and _normalize_scene_label(next_location) != current_location:
            story["current_scene"]["location"] = next_location
        
        # Add the scene transition caption as a system message in the chat history
        scene_transition_message = {
            "id": f"transition-{uuid.uuid4()}",
            "character_id": "system",
            "content": f"[{story['current_scene']['scene_transition_caption']}]",
            "timestamp": datetime.now().isoformat(),
            "type": "system",
            "render_mode": "plain",
        }
        logger.info(f"Adding scene transition message to chat history: {scene_transition_message['content']}")
        story["current_scene"]["messages"].append(scene_transition_message)
        scene_transition_added = True
    
    # Check if we need to accelerate story based on dialogue count and reflection
    force_pacing_transition = False
    if reflection and "story_advancement_strategy" in reflection:
        pacing_assessment = reflection["story_advancement_strategy"].get("pacing_assessment", "")
        if "accelerate" in pacing_assessment.lower() or "transition" in pacing_assessment.lower():
            logger.info(f"Reflection suggests accelerating story pace: '{pacing_assessment}'")
            force_pacing_transition = True

    # Also force pacing transition when fast-forward was requested this turn
    if fast_forward_this_turn:
        force_pacing_transition = True

    # 若处于结局倒计时，强制将分支选项指向结局或强推进
    try:
        state = context_manager.story_states.get(story_id)
        if state and state.conclusion_countdown > 0:
            force_pacing_transition = True
            # 确保存在“立即结尾”的明确选项
            if "branching_paths" not in advance_data or not advance_data.get("branching_paths"):
                advance_data["branching_paths"] = []
            end_choice = {
                "id": f"end-now-{uuid.uuid4()}",
                "text": "End the story now",
                "dramatic_impact": "Immediately concludes the narrative with a clear resolution"
            }
            # 仅当不存在类似文本时添加
            if not any(str(c.get("text", "")).lower().strip() == "end the story now" for c in advance_data["branching_paths"]):
                advance_data["branching_paths"].append(end_choice)
    except Exception as e:
        logger.error(f"[Countdown Choices] Error enforcing end-now choice: {e}")
    
    # Check if the story is stagnating and needs intervention
    story_stagnating = is_story_stagnating(story)
    scene_transition_requested = bool(
        ("scene_dynamics" in advance_data and advance_data["scene_dynamics"].get("transition_required"))
        or ("narrative_progression" in advance_data and advance_data["narrative_progression"].get("scene_transition"))
    )
    force_transition = (story_stagnating or force_pacing_transition) and not scene_transition_requested

    act_advance_flag = advance_data.get("act_advance")
    narrative_progression = advance_data.get("narrative_progression") or {}
    if isinstance(act_advance_flag, str):
        act_advance_requested = _parse_bool_tag(act_advance_flag)
    else:
        act_advance_requested = bool(act_advance_flag)
    if not act_advance_requested:
        narrative_act_advance = narrative_progression.get("act_advance")
        if isinstance(narrative_act_advance, str):
            act_advance_requested = _parse_bool_tag(narrative_act_advance)
        else:
            act_advance_requested = bool(narrative_act_advance)

    state = context_manager.story_states.get(story_id)
    acts = story.get("acts") or []
    endgame_act_advance = bool(
        state
        and state.conclusion_countdown > 0
        and advance_data.get("ending_ready")
        and acts
        and story.get("current_act", 0) < len(acts) - 1
    )
    should_advance_act = act_advance_requested or endgame_act_advance

    if force_transition:
        if force_pacing_transition:
            logger.warning(f"Forcing narrative advancement for story {story_id} due to pacing recommendation")
        else:
            logger.warning(f"Forcing narrative advancement for story {story_id} due to detected stagnation")

        if "scene_dynamics" not in advance_data:
            advance_data["scene_dynamics"] = {}
        if force_pacing_transition:
            advance_data["scene_dynamics"]["narrative_advancement"] = "Advancing to accelerate story pace"
        else:
            advance_data["scene_dynamics"]["narrative_advancement"] = "Advancing to break repetitive pattern"

        if "branching_paths" in advance_data and advance_data["branching_paths"]:
            for i, choice in enumerate(advance_data["branching_paths"]):
                if force_pacing_transition:
                    choice["dramatic_impact"] = f"Accelerates the story toward a key development (path {i+1})"
                else:
                    choice["dramatic_impact"] = f"Leads to a significant change in the story direction (forced progression path {i+1})"

    if scene_transition_requested:
        if not story["current_scene"].get("scene_transition_caption"):
            new_location = _normalize_inline_text(advance_data.get("scene_dynamics", {}).get("new_location"))
            time_progress = _normalize_inline_text(advance_data.get("scene_dynamics", {}).get("time_progression")) or "LATER"
            caption = f"{time_progress.upper()} - {new_location.upper()}" if new_location else time_progress.upper()
            story["current_scene"]["scene_transition_caption"] = caption
            logger.info(f"Added scene transition caption: {caption}")

        if not scene_transition_added and story["current_scene"].get("scene_transition_caption"):
            scene_transition_message = {
                "id": f"transition-{uuid.uuid4()}",
                "character_id": "system",
                "content": f"[{story['current_scene']['scene_transition_caption']}]",
                "timestamp": datetime.now().isoformat(),
                "type": "system",
                "render_mode": "plain",
            }
            logger.info(f"Adding scene transition message to chat history: {scene_transition_message['content']}")
            story["current_scene"]["messages"].append(scene_transition_message)

    if advance_data.get("scene_dynamics"):
        story["current_scene"]["scene_dynamics"] = advance_data["scene_dynamics"]

    if should_advance_act and acts:
        previous_act = story.get("current_act", 0)
        story["current_act"] = min(previous_act + 1, len(acts) - 1)
        if story["current_act"] != previous_act:
            logger.info(f"Story {story_id} advanced to act index {story['current_act']}")

    final_choices: List[Dict[str, Any]] = []
    for choice_group in (
        advance_data.get("new_choices"),
        advance_data.get("branching_paths"),
    ):
        if not isinstance(choice_group, list):
            continue
        for choice in choice_group:
            choice_text = str(choice.get("text", "")).strip().lower()
            if choice_text and any(
                str(existing_choice.get("text", "")).strip().lower() == choice_text
                for existing_choice in final_choices
            ):
                continue
            final_choices.append(choice)
    current_countdown = getattr(state, "conclusion_countdown", story.get("conclusion_countdown", 0)) if state else story.get("conclusion_countdown", 0)
    if not can_offer_end_story_choice(story, current_countdown):
        final_choices = [
            choice
            for choice in final_choices
            if str(choice.get("text", "")).strip().lower() != "end the story now"
        ]
    story["current_scene"]["choices"] = _limit_branching_choices(
        final_choices,
        speed_profile.max_choices,
    )

    if speed_profile.benchmark_speed_profile:
        story["generation_mode"] = "chat_native"
        story["state_freshness"] = "derived"
        story["state_updated_at"] = datetime.now().isoformat()
        story_state = story.setdefault("story_state", {})
        story_state.update(advance_data.get("story_state", {}) or {})
        story_memory = story.setdefault("story_memory", {})
        current_tension = _normalize_inline_text(story_state.get("current_tension"))
        latest_reveal = _normalize_inline_text(story_state.get("latest_reveal"))
        latest_reply = benchmark_generation.get("assistant_text") if benchmark_generation else ""
        story_memory.update(
            {
                "what_just_happened": _normalize_inline_text(latest_reply)[:240] or story_memory.get("what_just_happened", ""),
                "current_goal": _normalize_inline_text(story_state.get("current_objective")) or story_memory.get("current_goal", ""),
                "open_tensions": [current_tension] if current_tension else story_memory.get("open_tensions", []),
                "active_clues": [latest_reveal] if latest_reveal else story_memory.get("active_clues", []),
                "last_major_turning_point": latest_reveal or _normalize_inline_text(story_state.get("emotional_beat")) or story_memory.get("last_major_turning_point", ""),
            }
        )
        story["current_scene"]["story_state"] = dict(story_state)
        if advance_data.get("scene_elements"):
            story["current_scene"]["scene_elements"] = advance_data.get("scene_elements", {})
        if advance_data.get("scene_dynamics"):
            story["current_scene"]["scene_dynamics"] = advance_data.get("scene_dynamics", {})
        _sync_benchmark_state_to_context(
            story_id=story_id,
            context_manager=context_manager,
            story=story,
            advance_data=advance_data,
            npc_content=latest_reply,
        )

        current_exchange_count = count_story_exchanges(story["current_scene"]["messages"])
        patch_scheduled = _should_schedule_benchmark_state_patch(
            story=story,
            advance_data=advance_data,
            exchange_count=current_exchange_count,
        )
        story["_benchmark_state_patch_scheduled"] = patch_scheduled
        if patch_scheduled:
            story["_benchmark_state_patch_inflight"] = True
            asyncio.create_task(
                _refresh_benchmark_state_patch(
                    story_id=story_id,
                    context_manager=context_manager,
                    stories_db=stories_db,
                )
            )
    else:
        story.setdefault("generation_mode", "legacy_json")
        story.setdefault("state_freshness", "stale")

    # -------- Enforce conclusion if countdown active --------
    try:
        state = context_manager.story_states.get(story_id)
        if state and state.conclusion_countdown > 0:
            state.conclusion_countdown -= 1
            logger.info(f"[Conclusion Countdown] Story {story_id} turns left: {state.conclusion_countdown}")
            # During countdown, add a gentle system nudge toward resolution
            story.setdefault("current_scene", {}).setdefault("messages", []).append({
                "id": f"sys-{uuid.uuid4()}",
                "character_id": "system",
                "content": "[The narrative accelerates toward a resolution.]",
                "timestamp": datetime.now().isoformat(),
                "type": "system",
            })
            if state.conclusion_countdown == 0:
                story["status"] = "completed"
                story.setdefault("current_scene", {}).setdefault("messages", []).append({
                    "id": f"end-{uuid.uuid4()}",
                    "character_id": "system",
                    "content": "[THE STORY REACHES ITS CONCLUSION]",
                    "timestamp": datetime.now().isoformat(),
                    "type": "system",
                })
                logger.warning(
                    "[Conclusion Enforced] Story %s has been marked completed due to the %s speed profile countdown",
                    story_id,
                    speed_profile.story_mode,
                )
    except Exception as e:
        logger.error(f"[Conclusion Enforcement] Error while enforcing countdown: {e}")

    stories_db[story_id] = story
    
    # 6. Update user journey in context manager if possible
    if user_id and context_available:
        try:
            # Detect likely emotion from response and choices
            emotion = advance_data.get("scene_update", {}).get("emotional_tone", "neutral")
            # Estimate intensity based on content (simplistic implementation)
            intensity = 0.7  # Default medium-high intensity
            
            journey_key = f"{user_id}:{story_id}"
            if journey_key in context_manager.user_journeys:
                # Record emotional state
                context_manager.user_journeys[journey_key].record_emotional_state(
                    emotion=emotion,
                    intensity=intensity,
                    trigger=f"NPC response: {npc_content[:30]}..."
                )
                
                # If this was a choice (decision point), record it
                if action_type == "Choice":
                    implications = "Unknown"  # In a real implementation, this would be analyzed
                    context_manager.process_user_decision(
                        user_id=user_id,
                        story_id=story_id,
                        decision_point=user_input,
                        choice=user_input,
                        implications=implications,
                        emotion=emotion,
                        intensity=intensity,
                        llm_model=story_model,
                    )
                    logger.info(f"Recorded user decision in journey for story {story_id}")
        except Exception as e:
            logger.error(f"Failed to update user journey in context manager: {e}")
    
    return story["current_scene"]

async def enhance_act_structure(story_id: str, basic_acts: List[Dict], input_data: Dict) -> List[Dict]:
    """
    Takes the basic act structure generated in the initial story creation
    and enhances it with more creative and detailed elements.
    
    Args:
        story_id: ID of the story
        basic_acts: The initial simple act structure from the story creation
        input_data: Additional story data needed for the enhancement prompt
    
    Returns:
        Enhanced act structure with more cinematic and detailed elements
    """
    # Format the basic acts for the prompt
    existing_acts_formatted = json.dumps(basic_acts, indent=2)
    
    # Convert characters list to a formatted string
    character_descriptions = []
    for char in input_data.get("characters", []):
        name = char.get("name", "Unknown")
        role = char.get("role", "Unknown")
        if "visual_description" in char:
            desc = f"{name} ({role}): {char['visual_description'][:100]}..."
        else:
            desc = f"{name} ({role})"
        character_descriptions.append(desc)
    
    characters_str = "\n- ".join(character_descriptions)
    if characters_str:
        characters_str = "- " + characters_str
    
    # Format setting
    setting_str = ""
    if isinstance(input_data.get("setting"), dict):
        setting = input_data["setting"]
        setting_str = f"{setting.get('primary_location', '')}, {setting.get('time_period', '')}"
        if setting.get("atmosphere"):
            setting_str += f" - {setting.get('atmosphere')}"
    else:
        setting_str = str(input_data.get("setting", ""))
    
    # Prepare the prompt
    prompt = prompt_templates.ACT_ENHANCEMENT_PROMPT_TEMPLATE.format(
        title=input_data.get("title", ""),
        premise=input_data.get("high_concept_premise", ""),
        emotional_need=input_data.get("emotional_goal", ""),
        setting=setting_str,
        characters=characters_str,
        keywords=input_data.get("keywords", ""),
        existing_acts=existing_acts_formatted
    )
    
    # Call the LLM - 使用专门的故事模型
    messages = [
        {"role": "system", "content": "You are a master screenwriter who excels at creating compelling dramatic structures."},
        {"role": "user", "content": f"{prompt}\n\nReturn a valid JSON array matching this schema:\n{prompt_templates.ACT_ENHANCEMENT_SCHEMA}"}
    ]
    
    story_model = input_data.get("llm_config", {}).get("story", settings.get_llm_model("story"))
    logger.info(f"Calling story model ({story_model}) for act enhancement")
    response = get_llm_completion(
        messages=messages,
        model=story_model  # 使用专门的故事模型
    )
    
    if response["error"]:
        logger.warning(f"Failed to enhance acts for story {story_id}: {response['error']}")
        return basic_acts
    
    try:
        content_to_parse = extract_json_from_response(response["content"])
        enhanced_acts = json.loads(content_to_parse)
        logger.info(f"Successfully enhanced act structure for story {story_id}")
        return enhanced_acts
    except (ValueError, json.JSONDecodeError, TypeError) as e:
        logger.error(f"Failed to parse enhanced acts: {e}")
        logger.error(f"Raw response: {response['content']}")
        return basic_acts 
