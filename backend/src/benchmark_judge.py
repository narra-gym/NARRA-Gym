from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from utils import parse_json_response


OUTPUT_ROLES = {"assistant", "system"}
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9']+|[\u4e00-\u9fff]")
ENGLISH_TERM_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9']{2,}")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?:\r?\n)+|(?<=[.!?。！？；;])\s*")

GPTISM_PATTERNS: Dict[str, List[str]] = {
    "soft-gentle": [r"\bgently\b", r"\bsoftly\b", r"轻轻地?", r"温柔地?"],
    "in-this-moment": [r"\bin this moment\b", r"在这一刻", r"此刻"],
    "hold-space": [r"\bhold(?:ing)? space\b", r"留出空间", r"承接你的感受"],
    "take-a-breath": [r"\btake a breath\b", r"\bexhale\b", r"深呼吸", r"慢慢呼吸"],
    "you-are-not-alone": [r"\byou are not alone\b", r"你并不孤单", r"你不是一个人"],
    "flicker-glimmer": [r"\bflicker\b", r"\bglimmer\b", r"微光", r"一丝亮光"],
    "tender-quiet": [r"\btender\b", r"\bquiet(?:ly)?\b", r"静静地?", r"柔软"],
    "step-forward": [r"\bstep forward\b", r"向前走一步", r"再往前一步"],
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_role(record: Dict[str, Any]) -> str:
    raw_role = _clean_text(record.get("role")).lower()
    if raw_role in {"user", "assistant", "system"}:
        return raw_role

    character_id = _clean_text(record.get("character_id")).lower()
    speaker = _clean_text(record.get("speaker")).lower()
    if character_id == "system" or speaker == "system":
        return "system"
    if character_id in {"protagonist", "user"} or speaker in {"user", "protagonist", "you"}:
        return "user"
    return "assistant"


def _normalize_dialogue_record(record: Any, index: int) -> Optional[Dict[str, Any]]:
    raw = _as_dict(record)
    content = _clean_text(raw.get("content"))
    if not content:
        return None

    role = _normalize_role(raw)
    speaker = _clean_text(raw.get("speaker"))
    if not speaker:
        if role == "system":
            speaker = "System"
        elif role == "user":
            speaker = "User"
        else:
            speaker = _clean_text(raw.get("character_id")) or f"Speaker {index + 1}"

    return {
        "id": _clean_text(raw.get("id")) or f"judge-dialogue-{index}",
        "speaker": speaker,
        "role": role,
        "character_id": raw.get("character_id"),
        "content": content,
        "timestamp": raw.get("timestamp"),
        "message_type": _clean_text(raw.get("message_type")) or _clean_text(raw.get("type")) or "text",
        "turn_index": raw.get("turn_index"),
        "source": _clean_text(raw.get("source")) or "uploaded_dialogue",
    }


def build_dialogue_records_from_snapshot(snapshot: Dict[str, Any], source: str = "story_snapshot") -> List[Dict[str, Any]]:
    characters = _as_list(snapshot.get("characters"))
    character_map = {
        _clean_text(char.get("id")): _clean_text(char.get("name")) or _clean_text(char.get("id"))
        for char in characters
        if _clean_text(char.get("id"))
    }
    protagonist_id = next(
        (
            _clean_text(char.get("id"))
            for char in characters
            if _clean_text(char.get("role")).lower() == "protagonist" and _clean_text(char.get("id"))
        ),
        None,
    )

    records: List[Dict[str, Any]] = []
    for index, message in enumerate(_as_list(_as_dict(snapshot.get("current_scene")).get("messages"))):
        raw_message = _as_dict(message)
        character_id = _clean_text(raw_message.get("character_id")) or "system"
        if character_id == "system":
            role = "system"
            speaker = "System"
        elif protagonist_id and character_id == protagonist_id:
            role = "user"
            speaker = character_map.get(character_id, "User")
        else:
            role = "assistant"
            speaker = character_map.get(character_id, character_id or f"Speaker {index + 1}")

        content = _clean_text(raw_message.get("content"))
        if not content:
            continue

        records.append(
            {
                "id": _clean_text(raw_message.get("id")) or f"{source}-message-{index}",
                "speaker": speaker,
                "role": role,
                "character_id": character_id,
                "content": content,
                "timestamp": raw_message.get("timestamp"),
                "message_type": _clean_text(raw_message.get("type")) or "text",
                "source": source,
            }
        )
    return records


def build_dialogue_records_from_turn_logs(turn_logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for turn in turn_logs:
        raw_turn = _as_dict(turn)
        turn_id = _clean_text(raw_turn.get("id")) or f"turn-{raw_turn.get('turn_index', len(records))}"
        created_at = raw_turn.get("created_at")
        action_type = _clean_text(raw_turn.get("action_type")).lower() or "message"

        user_input = _clean_text(raw_turn.get("user_input"))
        if user_input:
            records.append(
                {
                    "id": f"{turn_id}-user",
                    "speaker": "User",
                    "role": "user",
                    "character_id": None,
                    "content": user_input,
                    "timestamp": created_at,
                    "message_type": action_type,
                    "turn_index": raw_turn.get("turn_index"),
                    "source": "turn_log",
                }
            )

        metadata = _as_dict(raw_turn.get("metadata"))
        response_messages = _as_list(metadata.get("response_messages"))
        if response_messages:
            for message_index, raw_message in enumerate(response_messages):
                message = _as_dict(raw_message)
                character_id = _clean_text(message.get("character_id")) or _clean_text(message.get("characterId")) or "system"
                content = _clean_text(message.get("content"))
                if not content:
                    continue

                role = "system" if character_id == "system" else "assistant"
                speaker = "System" if role == "system" else character_id
                records.append(
                    {
                        "id": _clean_text(message.get("id")) or f"{turn_id}-response-{message_index}",
                        "speaker": speaker,
                        "role": role,
                        "character_id": character_id,
                        "content": content,
                        "timestamp": message.get("timestamp") or created_at,
                        "message_type": _clean_text(message.get("type")) or "text",
                        "turn_index": raw_turn.get("turn_index"),
                        "source": "turn_log_message",
                    }
                )
            continue

        response_text = _clean_text(raw_turn.get("response_text"))
        if not response_text:
            continue

        response_character_id = raw_turn.get("response_character_id")
        speaker = _clean_text(response_character_id) or "Story"
        role = "system" if speaker.lower() == "system" else "assistant"
        records.append(
            {
                "id": f"{turn_id}-response",
                "speaker": "System" if role == "system" else speaker,
                "role": role,
                "character_id": response_character_id,
                "content": response_text,
                "timestamp": created_at,
                "message_type": "text",
                "turn_index": raw_turn.get("turn_index"),
                "source": "turn_log",
            }
        )
    return records


def normalize_benchmark_judge_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _as_dict(raw_payload)
    export_bundle = _as_dict(payload.get("export_bundle"))
    merged: Dict[str, Any] = dict(export_bundle)
    merged.update({key: value for key, value in payload.items() if key != "export_bundle"})

    session = _as_dict(merged.get("session")) or None
    turn_logs = [_as_dict(item) for item in _as_list(merged.get("turn_logs"))]
    feedback_logs = [_as_dict(item) for item in _as_list(merged.get("feedback_logs"))]
    llm_call_logs = [_as_dict(item) for item in _as_list(merged.get("llm_call_logs"))]
    story_snapshot = _as_dict(merged.get("story_snapshot")) or None
    participant_evaluation = _as_dict(merged.get("participant_evaluation")) or None
    final_view_story = (
        _as_dict(merged.get("final_view_story"))
        or _as_dict(merged.get("story"))
        or _as_dict(payload.get("story"))
        or None
    )

    dialogue_source = _clean_text(merged.get("dialogue_source")) or "uploaded_dialogue"
    normalized_dialogue = [
        normalized
        for index, item in enumerate(_as_list(merged.get("dialogue")))
        if (normalized := _normalize_dialogue_record(item, index))
    ]

    if normalized_dialogue:
        resolved_source = dialogue_source
    elif turn_logs:
        normalized_dialogue = build_dialogue_records_from_turn_logs(turn_logs)
        resolved_source = "turn_logs"
    elif story_snapshot:
        normalized_dialogue = build_dialogue_records_from_snapshot(story_snapshot, source="story_snapshot")
        resolved_source = "story_snapshot"
    elif final_view_story:
        normalized_dialogue = build_dialogue_records_from_snapshot(final_view_story, source="final_view_story")
        resolved_source = "final_view_story"
    else:
        raise ValueError("Uploaded benchmark JSON did not contain usable dialogue, turn logs, or story snapshots.")

    if not normalized_dialogue:
        raise ValueError("Uploaded benchmark JSON could not be converted into a non-empty dialogue transcript.")

    return {
        "session": session,
        "dialogue_source": resolved_source,
        "dialogue": normalized_dialogue,
        "turn_logs": turn_logs,
        "feedback_logs": feedback_logs,
        "llm_call_logs": llm_call_logs,
        "participant_evaluation": participant_evaluation,
        "story_snapshot": story_snapshot,
        "final_view_story": final_view_story,
        "schema_version": _clean_text(merged.get("schema_version")) or None,
        "export_type": _clean_text(merged.get("export_type")) or None,
    }


def _output_dialogue(dialogue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [item for item in dialogue if item.get("role") in OUTPUT_ROLES and _clean_text(item.get("content"))]


def _tokenize_text(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _split_sentences(text: str) -> List[str]:
    return [segment.strip() for segment in SENTENCE_SPLIT_PATTERN.split(text) if segment and segment.strip()]


def _normalize_sentence_prefix(sentence: str, length: int = 12) -> str:
    condensed = re.sub(r"[^\w\u4e00-\u9fff]+", "", sentence.lower())
    return condensed[:length]


def _excess_ngram_ratio(tokens: List[str], size: int) -> float:
    if len(tokens) < size:
        return 0.0
    ngrams = [tuple(tokens[index:index + size]) for index in range(len(tokens) - size + 1)]
    counts = Counter(ngrams)
    excess = sum(count - 1 for count in counts.values() if count > 1)
    return excess / max(len(ngrams), 1)


def _sentence_prefix_ratio(sentences: List[str]) -> float:
    prefixes = [_normalize_sentence_prefix(sentence) for sentence in sentences]
    prefixes = [prefix for prefix in prefixes if len(prefix) >= 4]
    if not prefixes:
        return 0.0
    counts = Counter(prefixes)
    excess = sum(count - 1 for count in counts.values() if count > 1)
    return excess / max(len(prefixes), 1)


def _extract_top_terms(text: str, sentences: List[str]) -> tuple[float, List[Dict[str, Any]]]:
    english_terms = [term.lower() for term in ENGLISH_TERM_PATTERN.findall(text)]
    if english_terms:
        counts = Counter(english_terms)
        top_items = counts.most_common(5)
        ratio = sum(count for _, count in counts.most_common(8)) / max(len(english_terms), 1)
        return ratio, [{"term": term, "count": count} for term, count in top_items if count > 1]

    prefixes = [_normalize_sentence_prefix(sentence, length=10) for sentence in sentences]
    prefixes = [prefix for prefix in prefixes if len(prefix) >= 4]
    if not prefixes:
        return 0.0, []

    counts = Counter(prefixes)
    top_items = counts.most_common(5)
    ratio = sum(count for _, count in counts.most_common(8)) / max(len(prefixes), 1)
    return ratio, [{"term": term, "count": count} for term, count in top_items if count > 1]


def _count_gptisms(text: str) -> Dict[str, int]:
    lowered = text.lower()
    hits: Dict[str, int] = {}
    for label, patterns in GPTISM_PATTERNS.items():
        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, lowered, flags=re.IGNORECASE))
        if count > 0:
            hits[label] = count
    return hits


def compute_slop_stats(dialogue: List[Dict[str, Any]]) -> Dict[str, Any]:
    output_messages = _output_dialogue(dialogue)
    output_text = "\n".join(_clean_text(item.get("content")) for item in output_messages)
    sentences = _split_sentences(output_text)
    tokens = _tokenize_text(output_text)

    repeated_bigram_ratio = _excess_ngram_ratio(tokens, 2)
    repeated_trigram_ratio = _excess_ngram_ratio(tokens, 3)
    repeated_sentence_prefix_ratio = _sentence_prefix_ratio(sentences)
    high_frequency_term_ratio, top_repeated_terms = _extract_top_terms(output_text, sentences)

    gptism_hits = _count_gptisms(output_text)
    total_output_tokens = len(tokens)
    gptism_hit_rate = sum(gptism_hits.values()) / max(total_output_tokens, 1)

    slop_score = 100 * min(
        1.0,
        (
            0.34 * min(repeated_bigram_ratio * 4.5, 1.0)
            + 0.24 * min(repeated_trigram_ratio * 7.0, 1.0)
            + 0.18 * min(high_frequency_term_ratio * 1.8, 1.0)
            + 0.14 * min(repeated_sentence_prefix_ratio * 4.0, 1.0)
            + 0.10 * min(gptism_hit_rate * 40.0, 1.0)
        ),
    )

    if slop_score < 25:
        interpretation = "Low slop. The output looks fairly varied and not overly repetitive."
    elif slop_score < 50:
        interpretation = "Moderate slop. Some repeated phrasing or stock patterns are visible."
    elif slop_score < 75:
        interpretation = "High slop. Repetition and stock phrasing are showing up frequently."
    else:
        interpretation = "Very high slop. The output is strongly repetitive or heavily pattern-driven."

    return {
        "slop_score": round(slop_score, 2),
        "interpretation": interpretation,
        "total_output_messages": len(output_messages),
        "total_output_tokens": total_output_tokens,
        "gptism_hit_rate": round(gptism_hit_rate, 4),
        "repeated_bigram_ratio": round(repeated_bigram_ratio, 4),
        "repeated_trigram_ratio": round(repeated_trigram_ratio, 4),
        "high_frequency_term_ratio": round(high_frequency_term_ratio, 4),
        "repeated_sentence_prefix_ratio": round(repeated_sentence_prefix_ratio, 4),
        "top_repeated_terms": top_repeated_terms,
        "gptism_hits": gptism_hits,
    }


def build_judge_input_summary(normalized_payload: Dict[str, Any], selected_model: Optional[str] = None) -> Dict[str, Any]:
    session = _as_dict(normalized_payload.get("session"))
    final_view_story = _as_dict(normalized_payload.get("final_view_story"))
    output_messages = _output_dialogue(_as_list(normalized_payload.get("dialogue")))
    output_text = "\n".join(_clean_text(item.get("content")) for item in output_messages)

    return {
        "session_id": session.get("session_id") or session.get("id"),
        "story_id": session.get("story_id") or final_view_story.get("story_id") or final_view_story.get("id"),
        "participant_id": session.get("participant_id") or final_view_story.get("user_id"),
        "selected_model": selected_model or session.get("selected_model"),
        "dialogue_count": len(_as_list(normalized_payload.get("dialogue"))),
        "output_message_count": len(output_messages),
        "turn_log_count": len(_as_list(normalized_payload.get("turn_logs"))),
        "llm_call_count": len(_as_list(normalized_payload.get("llm_call_logs"))),
        "feedback_count": len(_as_list(normalized_payload.get("feedback_logs"))),
        "content_source": _clean_text(normalized_payload.get("dialogue_source")) or "uploaded_dialogue",
        "story_title": _clean_text(final_view_story.get("title")) or None,
        "total_output_tokens": len(_tokenize_text(output_text)),
    }


def _truncate_dialogue_lines(lines: List[str], max_chars: int = 18000, head: int = 18, tail: int = 24) -> str:
    if not lines:
        return ""

    trimmed_lines = [line[:600] for line in lines]
    full_text = "\n".join(trimmed_lines)
    if len(full_text) <= max_chars:
        return full_text

    if len(trimmed_lines) <= head + tail:
        return full_text[:max_chars]

    omitted_count = len(trimmed_lines) - head - tail
    compact = trimmed_lines[:head] + [f"... {omitted_count} dialogue lines omitted for brevity ..."] + trimmed_lines[-tail:]
    compact_text = "\n".join(compact)
    return compact_text[:max_chars]


def build_benchmark_judge_messages(normalized_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    summary = build_judge_input_summary(normalized_payload)
    dialogue_lines: List[str] = []
    for record in _as_list(normalized_payload.get("dialogue")):
        normalized_record = _as_dict(record)
        prefix_parts: List[str] = []
        if normalized_record.get("turn_index") is not None:
            prefix_parts.append(f"Turn {normalized_record.get('turn_index')}")
        prefix_parts.append(f"{_clean_text(normalized_record.get('speaker'))} ({_clean_text(normalized_record.get('role'))})")
        dialogue_lines.append(f"{' | '.join(prefix_parts)}: {_clean_text(normalized_record.get('content'))}")

    transcript = _truncate_dialogue_lines(dialogue_lines)
    story_title = summary.get("story_title") or "Unknown Story"

    system_prompt = (
        "You are a strict but fair LLM-as-a-judge for benchmarked interactive narrative sessions. "
        "Use the transcript and session metadata to score the model output. "
        "Focus on the generated assistant/system messages, while using user messages only as context. "
        "Return JSON only."
    )
    user_prompt = (
        "Evaluate this uploaded benchmark transcript.\n\n"
        f"Story title: {story_title}\n"
        f"Session id: {summary.get('session_id') or 'unknown'}\n"
        f"Participant id: {summary.get('participant_id') or 'unknown'}\n"
        f"Dialogue count: {summary.get('dialogue_count')}\n"
        f"Output message count: {summary.get('output_message_count')}\n"
        f"Dialogue source: {summary.get('content_source')}\n\n"
        "Score these placeholder rubric dimensions from 1 to 5 as integers:\n"
        "- overall_rating\n"
        "- emotional_alignment\n"
        "- narrative_coherence\n"
        "- supportiveness\n\n"
        "Return JSON with exactly this shape:\n"
        "{\n"
        '  "overall_rating": 1,\n'
        '  "emotional_alignment": 1,\n'
        '  "narrative_coherence": 1,\n'
        '  "supportiveness": 1,\n'
        '  "summary": "short overall assessment",\n'
        '  "strengths": ["strength 1", "strength 2"],\n'
        '  "issues": ["issue 1", "issue 2"]\n'
        "}\n\n"
        "Keep the summary concise. Provide 2-4 strengths and 2-4 issues. "
        "Do not include markdown or any text outside the JSON object.\n\n"
        f"Transcript:\n{transcript}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _clamp_score(value: Any, default: int = 3) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(5, parsed))


def _normalize_string_list(value: Any, fallback: List[str]) -> List[str]:
    if not isinstance(value, list):
        return fallback
    normalized: List[str] = []
    for item in value:
        cleaned = _clean_text(item)
        if cleaned:
            normalized.append(cleaned)
        if len(normalized) >= 4:
            break
    return normalized or fallback


def parse_benchmark_judge_result(content: str, model: Optional[str] = None) -> Dict[str, Any]:
    parsed = parse_json_response(content, task="default", model=model)
    if not isinstance(parsed, dict):
        raise ValueError("Judge model did not return a JSON object.")

    scores = _as_dict(parsed.get("scores"))
    summary = _clean_text(parsed.get("summary")) or _clean_text(parsed.get("judge_summary")) or "Placeholder benchmark judgement completed."
    strengths = _normalize_string_list(parsed.get("strengths"), ["The session remained coherent enough to evaluate."])
    issues = _normalize_string_list(parsed.get("issues") or parsed.get("weaknesses"), ["The placeholder rubric still needs refinement."])

    return {
        "judge_scores": {
            "overall_rating": _clamp_score(parsed.get("overall_rating") or scores.get("overall_rating")),
            "emotional_alignment": _clamp_score(parsed.get("emotional_alignment") or scores.get("emotional_alignment")),
            "narrative_coherence": _clamp_score(parsed.get("narrative_coherence") or scores.get("narrative_coherence")),
            "supportiveness": _clamp_score(parsed.get("supportiveness") or scores.get("supportiveness")),
        },
        "judge_summary": {
            "summary": summary,
            "strengths": strengths,
            "issues": issues,
        },
    }
