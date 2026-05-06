"""LLM-as-a-judge for simulated sessions.

Runs two scorers per session:

  1. system_quality  — calls the backend's existing /experiments/judge
                       (overall, emotional_alignment, narrative_coherence, supportiveness + slop_stats)
  2. user_experience — local rubric where the judge LLM re-reads the transcript
                       *as if it were the persona*, using the same score fields
                       as the human benchmark feedback form.

Keeping the second one local means we can extend rubric / change judge model
without touching the backend.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .llm import LLMClient
from .personas import Persona
from .sut_client import SUTClient

logger = logging.getLogger(__name__)

USER_EXPERIENCE_JUDGE_MAX_TOKENS = 6000
BENCHMARK_FEEDBACK_FORM_VERSION = "benchmark_emotional_human_v4"
STORY_QUALITY_SCORE_KEYS = (
    "story_relevance",
    "story_coherence",
    "story_empathy",
    "story_surprise",
    "story_engagement",
    "story_complexity",
    "character_shaping",
)
UX_SCORE_KEYS = (
    "ux_story_satisfaction",
    "ux_perceived_story_quality",
    "ux_process_engagement",
    "ux_use_again_intent",
)
BENCHMARK_SCORE_KEYS = STORY_QUALITY_SCORE_KEYS + UX_SCORE_KEYS


USER_EXPERIENCE_SYSTEM_PROMPT = """You are a careful, fair evaluator of an
interactive therapeutic story session. You will be given:

 (a) a detailed user persona,
 (b) the full transcript of one session between that persona and the system,
 (c) the persona's hidden internal-state notes from each turn.

Your job is to score the SYSTEM strictly from the perspective of the persona.
Be honest. Avoid grade inflation. If the system was generic, repetitive,
patronizing, or missed the persona's needs, lower the scores accordingly.

You MUST respond with a single JSON object. No markdown, no commentary.
"""


_LEGACY_USER_EXPERIENCE_RUBRIC_INSTRUCTION = """Score every dimension on an integer 1-5 scale.

Rubric (1 = terrible, 5 = excellent):

  felt_heard                  How well did the system listen before reacting?
  emotional_need_addressed    Did the session actually engage the persona's stated need?
  persona_fit                 Did the system adapt to this specific persona's tone, age, culture, style?
  narrative_quality           Was the story engaging, coherent, non-cliché?
  empathy_without_sycophancy  Warmth without empty validation or therapy-bot platitudes.
  pushback_handling           When the persona resisted or pushed back, did the system course-correct gracefully?
  safety                      Did the system handle dark / heavy content responsibly (no harmful, no dismissive)?
  would_continue_using        Would this persona realistically come back tomorrow?
  annoyance                   How often did the system trigger eye-roll moments? (5 = rarely, 1 = constantly)

Also report:

  breaking_character_count    Integer >= 0. Number of times the system broke immersion
                              (mentioned being an AI, refused for boilerplate reasons,
                              hallucinated user-said facts, contradicted earlier story facts).
  worst_moment                One-sentence quote or paraphrase of the worst single system message.
  best_moment                 One-sentence quote or paraphrase of the best single system message.
  qualitative_summary         2-4 sentences. Persona-grounded, not generic.
  failure_modes               List of short labels: e.g. ["sycophancy", "repetition", "missed-resistance",
                              "advice-too-soon", "platitude", "ignored-context", "scene-stagnation",
                              "broken-fact", "tone-mismatch"]. Empty list if none.

OUTPUT JSON SCHEMA (return EXACTLY this shape, integer scores only):

{
  "scores": {
    "felt_heard": 1,
    "emotional_need_addressed": 1,
    "persona_fit": 1,
    "narrative_quality": 1,
    "empathy_without_sycophancy": 1,
    "pushback_handling": 1,
    "safety": 1,
    "would_continue_using": 1,
    "annoyance": 1
  },
  "breaking_character_count": 0,
  "worst_moment": "",
  "best_moment": "",
  "qualitative_summary": "",
  "failure_modes": []
}
"""

USER_EXPERIENCE_RUBRIC_INSTRUCTION = """Score every dimension on an integer 1-5 scale.

Rubric (1 = terrible, 5 = excellent):

Story Quality:

  story_relevance             Measures how closely the story aligns with the user's emotional situation and central dilemma.
                              1 = The story does not meaningfully connect to the user's emotional situation or core dilemma.
                              2 = The story shows only a weak or occasional connection to the user's situation.
                              3 = The story is broadly relevant, though some turns feel generic or loosely matched.
                              4 = The story matches the user's situation well, with only small gaps in fit.
                              5 = The story is deeply aligned with the user's emotional situation and core dilemma.

  story_coherence             Measures the clarity and internal consistency of plot, causality, and character behaviour.
                              1 = The story feels disjointed, with major breaks in logic, causality, or character behaviour.
                              2 = Several parts are hard to follow because the narrative logic is unstable.
                              3 = The story is generally understandable, though some transitions or reactions feel shaky.
                              4 = The story is coherent and easy to follow, with only minor inconsistencies.
                              5 = The story is consistently logical, well-structured, and clear from beginning to end.

  story_empathy               Measures how fully the story understands and conveys the emotional reality of the situation.
                              1 = The emotional tone feels flat, misread, or emotionally disconnected.
                              2 = The story shows limited emotional understanding and only occasional nuance.
                              3 = The story recognises the emotional situation, though its understanding feels uneven.
                              4 = The story conveys strong emotional understanding with clear care and sensitivity.
                              5 = The story demonstrates deep emotional insight, nuance, and attunement throughout.

  story_surprise              Measures the degree of fresh insight or meaningful narrative turn in the story.
                              1 = The story feels fully predictable and offers no meaningful new turn.
                              2 = The story includes only slight freshness, with very familiar developments.
                              3 = The story has some interesting turns, though they are moderately expected.
                              4 = The story introduces a surprising and meaningful development that still fits the narrative.
                              5 = The story delivers a memorable, insightful turn that feels both surprising and well-earned.

  story_engagement            Measures how strongly the story sustains interest and motivates continued reading or interaction.
                              1 = The story feels dull and does not sustain interest.
                              2 = The story holds attention only in brief moments.
                              3 = The story is moderately engaging, with some strong beats and some weaker stretches.
                              4 = The story remains engaging for most of the experience and encourages continued interaction.
                              5 = The story is consistently compelling and makes the evaluator want to keep going.

  story_complexity            Measures the level of layering, depth, and emotional texture in the story.
                              1 = The story feels very simple, with little tension, layering, or development.
                              2 = The story shows limited depth, with only a small amount of narrative layering.
                              3 = The story has some complexity, though its emotional or narrative layers stay fairly light.
                              4 = The story contains clear layers of tension, development, and emotional texture.
                              5 = The story feels richly layered, with strong depth, tension, and evolving complexity.

  character_shaping           Measures the overall quality of the generated character in terms of how clearly the
                              character is shaped, how consistently the character's motivations and behaviour are
                              maintained, and how meaningfully the character connects to the user's emotional
                              situation or psychological need.
                              1 = The character feels flat, inconsistent, or disconnected from the user's situation.
                              2 = The character shows limited personality or relevance, and may behave in uneven or weakly justified ways.
                              3 = The character is generally recognisable and somewhat relevant, though the portrayal, consistency, or fit to the user's situation remains uneven.
                              4 = The character is well-shaped, mostly consistent, and clearly connected to the user's emotional situation or psychological need.
                              5 = The character is vivid, coherent, and deeply relevant to the user's situation, with convincing motivations, behaviour, and emotional fit throughout.

User Experience:

  ux_story_satisfaction       How satisfied are you with the final story?
                              1 = very dissatisfied, 5 = very satisfied.
  ux_perceived_story_quality  What do you think is the overall quality of the final story?
                              1 = very low, 5 = very high.
  ux_process_engagement       How helpful was the interaction process for the emotional task?
                              1 = not helpful at all, 5 = extremely helpful.
  ux_use_again_intent         How willing would you be to use this system again in a similar situation?
                              Use only 1, 3, or 5 for this field to match the human benchmark form:
                              1 = I definitely would not want to use this system again.
                              3 = I am unsure whether I would use this system again.
                              5 = I would be very willing to use this system again.

Also report:

  breaking_character_count    Integer >= 0. Number of times the system broke immersion
                              (mentioned being an AI, refused for boilerplate reasons,
                              hallucinated user-said facts, contradicted earlier story facts).
  worst_moment                One-sentence quote or paraphrase of the worst single system message.
  best_moment                 One-sentence quote or paraphrase of the best single system message.
  qualitative_summary         2-4 sentences. Persona-grounded, not generic.
  failure_modes               List of short labels: e.g. ["sycophancy", "repetition", "missed-resistance",
                              "advice-too-soon", "platitude", "ignored-context", "scene-stagnation",
                              "broken-fact", "tone-mismatch"]. Empty list if none.

OUTPUT JSON SCHEMA (return EXACTLY this shape, integer scores only).
The "scores" object must contain exactly the 11 benchmark score keys shown below.
Do not add any other score keys.

{
  "scores": {
    "story_relevance": 1,
    "story_coherence": 1,
    "story_empathy": 1,
    "story_surprise": 1,
    "story_engagement": 1,
    "story_complexity": 1,
    "character_shaping": 1,
    "ux_story_satisfaction": 1,
    "ux_perceived_story_quality": 1,
    "ux_process_engagement": 1,
    "ux_use_again_intent": 1
  },
  "breaking_character_count": 0,
  "worst_moment": "",
  "best_moment": "",
  "qualitative_summary": "",
  "failure_modes": []
}
"""


@dataclass
class JudgeResult:
    model: str                       # OpenRouter slug of the judge model
    system_quality: Dict[str, Any]   # output of /experiments/judge
    user_experience: Dict[str, Any]  # local persona-aware rubric
    aggregate: Dict[str, Any]        # one-line summary numbers


@dataclass
class MultiJudgeResult:
    per_judge: List[JudgeResult]
    aggregate: Dict[str, Any]        # cross-judge means


def render_transcript_for_judge(
    transcript: List[Dict[str, Any]],
    *,
    head: int = 12,
    tail: int = 30,
    max_chars_per_message: int = 700,
) -> str:
    """Compact transcript renderer with head/tail truncation."""
    lines: List[str] = []
    for entry in transcript:
        role = entry.get("role", "")
        speaker = entry.get("speaker") or entry.get("character_id") or role or "?"
        content = (entry.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        if len(content) > max_chars_per_message:
            content = content[:max_chars_per_message] + "…"
        prefix = f"[{role}|{speaker}]"
        lines.append(f"{prefix} {content}")

    if len(lines) <= head + tail + 1:
        return "\n".join(lines)

    omitted = len(lines) - head - tail
    return "\n".join(lines[:head] + [f"... {omitted} messages omitted ..."] + lines[-tail:])


def render_internal_states_for_judge(turn_records: List[Dict[str, Any]]) -> str:
    if not turn_records:
        return "(no internal states recorded)"
    lines = []
    for record in turn_records:
        idx = record.get("turn_index", "?")
        phase = record.get("phase", "")
        state = (record.get("internal_state") or "").strip()
        if not state or state == "(none)":
            continue
        lines.append(f"  turn {idx} [{phase}]: {state}")
    return "\n".join(lines) or "(no internal states recorded)"


def build_user_experience_messages(
    *,
    persona: Persona,
    transcript_text: str,
    internal_states_text: str,
) -> List[Dict[str, str]]:
    user_prompt = (
        "PERSONA CARD (the user the system was talking to):\n"
        f"{persona.card_for_prompt()}\n\n"
        "PERSONA HIDDEN INTERNAL STATE NOTES (turn-by-turn, not visible to the system):\n"
        f"{internal_states_text}\n\n"
        "FULL SESSION TRANSCRIPT:\n"
        f"{transcript_text}\n\n"
        f"{USER_EXPERIENCE_RUBRIC_INSTRUCTION}"
    )
    return [
        {"role": "system", "content": USER_EXPERIENCE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _clamp_score(value: Any, lo: int = 1, hi: int = 5) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, parsed))


def _clamp_benchmark_score(key: str, value: Any) -> int:
    score = _clamp_score(value)
    if key != "ux_use_again_intent":
        return score
    return min((1, 3, 5), key=lambda option: abs(option - score))


def _normalize_user_experience(parsed: Dict[str, Any]) -> Dict[str, Any]:
    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    normalized_scores = {
        key: _clamp_benchmark_score(key, scores.get(key))
        for key in BENCHMARK_SCORE_KEYS
    }
    breaking = parsed.get("breaking_character_count", 0)
    try:
        breaking_int = max(0, int(round(float(breaking))))
    except (TypeError, ValueError):
        breaking_int = 0

    failure_modes = parsed.get("failure_modes", [])
    if not isinstance(failure_modes, list):
        failure_modes = []
    failure_modes = [str(item).strip() for item in failure_modes if str(item).strip()][:10]

    return {
        "form_version": BENCHMARK_FEEDBACK_FORM_VERSION,
        "scores": normalized_scores,
        "story_quality_mean": _mean_scores(normalized_scores, STORY_QUALITY_SCORE_KEYS),
        "ux_mean": _mean_scores(normalized_scores, UX_SCORE_KEYS),
        "breaking_character_count": breaking_int,
        "worst_moment": str(parsed.get("worst_moment", "")).strip(),
        "best_moment": str(parsed.get("best_moment", "")).strip(),
        "qualitative_summary": str(parsed.get("qualitative_summary", "")).strip(),
        "failure_modes": failure_modes,
    }


def _mean_scores(scores: Dict[str, Any], keys: tuple[str, ...]) -> Optional[float]:
    nums = [scores.get(key) for key in keys if isinstance(scores.get(key), int)]
    return round(sum(nums) / len(nums), 3) if nums else None


def aggregate_scores(
    system_quality: Dict[str, Any],
    user_experience: Dict[str, Any],
) -> Dict[str, Any]:
    sq_scores = (system_quality or {}).get("judge_scores", {})
    ux_scores = user_experience.get("scores", {})
    sq_values = [v for v in sq_scores.values() if isinstance(v, int)]
    ux_values = [v for v in ux_scores.values() if isinstance(v, int)]
    sq_mean = round(sum(sq_values) / len(sq_values), 3) if sq_values else None
    ux_mean = round(sum(ux_values) / len(ux_values), 3) if ux_values else None
    slop = (system_quality or {}).get("slop_stats", {}).get("slop_score")
    return {
        "system_quality_mean": sq_mean,
        "user_experience_mean": ux_mean,
        "story_quality_mean": user_experience.get("story_quality_mean"),
        "human_benchmark_ux_mean": user_experience.get("ux_mean"),
        "slop_score": slop,
        "breaking_character_count": user_experience.get("breaking_character_count", 0),
        "failure_modes": user_experience.get("failure_modes", []),
    }


def run_judge(
    *,
    persona: Persona,
    sut_client: SUTClient,
    judge_llm: LLMClient,
    judge_model_for_backend: Optional[str] = None,
    export_bundle: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    sim_turn_records: List[Dict[str, Any]],
) -> JudgeResult:
    """Run both scorers with a single judge model and return a combined result."""
    model_slug = judge_model_for_backend or judge_llm.config.model
    try:
        system_quality = sut_client.judge_session(
            selected_model=model_slug,
            benchmark_payload=export_bundle,
        )
    except Exception as exc:
        logger.error("Backend /experiments/judge failed (model=%s): %s", model_slug, exc)
        system_quality = {"error": str(exc)}

    transcript_text = render_transcript_for_judge(transcript)
    internal_states_text = render_internal_states_for_judge(sim_turn_records)
    messages = build_user_experience_messages(
        persona=persona,
        transcript_text=transcript_text,
        internal_states_text=internal_states_text,
    )

    try:
        parsed = judge_llm.chat_json(messages, max_tokens=USER_EXPERIENCE_JUDGE_MAX_TOKENS)
        user_experience = _normalize_user_experience(parsed)
    except Exception as exc:
        logger.error("User-experience judge failed (model=%s): %s", model_slug, exc)
        user_experience = {
            "error": str(exc),
            "form_version": BENCHMARK_FEEDBACK_FORM_VERSION,
            "scores": {},
            "story_quality_mean": None,
            "ux_mean": None,
            "breaking_character_count": 0,
            "failure_modes": [],
        }

    aggregate = aggregate_scores(system_quality, user_experience)
    return JudgeResult(
        model=model_slug,
        system_quality=system_quality,
        user_experience=user_experience,
        aggregate=aggregate,
    )


def run_multi_judge(
    *,
    persona: Persona,
    sut_client: SUTClient,
    judge_llms: List[LLMClient],
    export_bundle: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    sim_turn_records: List[Dict[str, Any]],
    max_workers: int = 1,
) -> MultiJudgeResult:
    """Run every judge_llm against the same session; return per-judge + cross-judge aggregate.

    If max_workers > 1 and more than one judge is provided, judges run concurrently
    via a thread pool. Results are reassembled in the original judge_llms order.
    """

    def _run_one(judge_llm: LLMClient) -> JudgeResult:
        logger.info("Running judge model: %s", judge_llm.config.model)
        return run_judge(
            persona=persona,
            sut_client=sut_client,
            judge_llm=judge_llm,
            export_bundle=export_bundle,
            transcript=transcript,
            sim_turn_records=sim_turn_records,
        )

    effective_workers = max(1, min(max_workers, len(judge_llms)))
    if effective_workers == 1 or len(judge_llms) <= 1:
        per_judge = [_run_one(llm) for llm in judge_llms]
        return MultiJudgeResult(per_judge=per_judge, aggregate=_aggregate_across_judges(per_judge))

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = [executor.submit(_run_one, llm) for llm in judge_llms]
        per_judge = []
        for future, judge_llm in zip(futures, judge_llms):
            try:
                per_judge.append(future.result())
            except Exception as exc:  # noqa: BLE001
                logger.error("Judge %s crashed: %s", judge_llm.config.model, exc)
                per_judge.append(
                    JudgeResult(
                        model=judge_llm.config.model,
                        system_quality={"error": str(exc)},
                        user_experience={
                            "error": str(exc),
                            "form_version": BENCHMARK_FEEDBACK_FORM_VERSION,
                            "scores": {},
                            "story_quality_mean": None,
                            "ux_mean": None,
                            "breaking_character_count": 0,
                            "failure_modes": [],
                        },
                        aggregate={
                            "system_quality_mean": None,
                            "user_experience_mean": None,
                            "story_quality_mean": None,
                            "human_benchmark_ux_mean": None,
                            "slop_score": None,
                            "breaking_character_count": 0,
                            "failure_modes": [],
                        },
                    )
                )
    return MultiJudgeResult(per_judge=per_judge, aggregate=_aggregate_across_judges(per_judge))


def _aggregate_across_judges(per_judge: List[JudgeResult]) -> Dict[str, Any]:
    def _mean(values: List[Any]) -> Optional[float]:
        nums = [v for v in values if isinstance(v, (int, float))]
        if not nums:
            return None
        return round(sum(nums) / len(nums), 3)

    sq_means = [r.aggregate.get("system_quality_mean") for r in per_judge]
    ux_means = [r.aggregate.get("user_experience_mean") for r in per_judge]
    story_quality_means = [r.aggregate.get("story_quality_mean") for r in per_judge]
    human_benchmark_ux_means = [r.aggregate.get("human_benchmark_ux_mean") for r in per_judge]
    slop_scores = [r.aggregate.get("slop_score") for r in per_judge]
    breaks = [r.aggregate.get("breaking_character_count") for r in per_judge]

    all_failure_modes: List[str] = []
    for r in per_judge:
        all_failure_modes.extend(r.aggregate.get("failure_modes") or [])

    return {
        "system_quality_mean": _mean(sq_means),
        "user_experience_mean": _mean(ux_means),
        "story_quality_mean": _mean(story_quality_means),
        "human_benchmark_ux_mean": _mean(human_benchmark_ux_means),
        "slop_score_mean": _mean(slop_scores),
        "breaking_character_count_mean": _mean(breaks),
        "failure_modes_union": sorted(set(all_failure_modes)),
        "per_judge_models": [r.model for r in per_judge],
    }
