"""End-to-end runner: drive simulated personas through the EmoNest backend
and score the resulting sessions.

Usage examples:

  # Run every persona once against a local backend, output to simulation/results/
  python -m simulation.runner

  # Pick specific personas, repeat each 3 times
  python -m simulation.runner --persona anxious_grad_student --persona burnt_out_engineer --runs 3

  # Use a different judge model (defaults to LLM_DEFAULT_MODEL from backend/.env)
  python -m simulation.runner --judge-model openai/gpt-5.4 --sim-user-model openai/gpt-5.4-mini
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .judge import JudgeResult, MultiJudgeResult, run_multi_judge
from .llm import LLMClient, LLMConfig
from .personas import Persona, discover_personas, filter_personas
from .simulated_user import SimulatedUser, TurnRecord
from .sut_client import SUTClient

LOGGER = logging.getLogger("simulation.runner")


DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"

DEFAULT_JUDGE_MODELS: List[str] = [
    "openai/gpt-5.4-mini",
    "google/gemini-3.1-pro-preview",
    "anthropic/claude-sonnet-4.6",
]

DEFAULT_SIM_USER_MODELS_BY_PERSONA: Dict[str, str] = {
    "anxious_grad_student": "openai/gpt-5.4-mini",
    "grieving_father": "openai/gpt-5.4-mini",
    "burnt_out_engineer": "openai/gpt-5.4-mini",
    "lonely_retiree": "google/gemini-3.1-pro-preview",
    "overwhelmed_new_mom": "google/gemini-3.1-pro-preview",
    "chronic_illness_patient": "google/gemini-3.1-pro-preview",
    "perfectionist_artist": "anthropic/claude-sonnet-4.6",
    "socially_anxious_intern": "anthropic/claude-sonnet-4.6",
}


# ── Story creation helpers ────────────────────────────────────────────────


def _coerce_question_dict(q: Any) -> Dict[str, Any]:
    if isinstance(q, dict):
        return q
    if isinstance(q, str):
        return {"question": q, "options": [], "allowsCustom": True, "questionType": "single"}
    return {}


def _normalize_keyword_list(content: Any, fallback: List[str]) -> List[str]:
    if isinstance(content, list):
        items = [str(x).strip() for x in content if str(x).strip()]
    elif isinstance(content, str):
        items = [chunk.strip() for chunk in content.split(",") if chunk.strip()]
    else:
        items = []
    if not items:
        items = fallback[:3]
    return items[:4]


def _extract_recent_messages(story: Dict[str, Any]) -> List[Dict[str, Any]]:
    scene = story.get("current_scene") or {}
    raw_messages = scene.get("messages") or []
    characters = story.get("characters") or []
    char_lookup = {
        str(ch.get("id")): ch.get("name") or ch.get("id") for ch in characters if ch.get("id")
    }
    protagonist_id = next(
        (
            str(ch.get("id"))
            for ch in characters
            if str(ch.get("role", "")).lower() == "protagonist"
        ),
        None,
    )
    rendered: List[Dict[str, Any]] = []
    for msg in raw_messages:
        if not isinstance(msg, dict):
            continue
        character_id = str(msg.get("character_id") or "system")
        if character_id == "system":
            role = "system"
            speaker = "System"
        elif protagonist_id and character_id == protagonist_id:
            role = "user"
            speaker = char_lookup.get(character_id, "User")
        else:
            role = "assistant"
            speaker = char_lookup.get(character_id, character_id)
        rendered.append(
            {
                "role": role,
                "speaker": speaker,
                "character_id": character_id,
                "content": msg.get("content", ""),
                "type": msg.get("type", "text"),
            }
        )
    return rendered


def _extract_choices(story: Dict[str, Any]) -> List[Dict[str, Any]]:
    scene = story.get("current_scene") or {}
    return [
        {"id": c.get("id"), "text": c.get("text")}
        for c in (scene.get("choices") or [])
        if isinstance(c, dict) and c.get("id")
    ]


def _ending_available(story: Dict[str, Any]) -> bool:
    if story.get("status") == "completed":
        return True
    countdown = story.get("conclusion_countdown") or 0
    try:
        return int(countdown) <= 1
    except (TypeError, ValueError):
        return False


# ── Single session driver ────────────────────────────────────────────────


def run_one_session(
    *,
    persona: Persona,
    sut_client: SUTClient,
    sim_user_llm: LLMClient,
    judge_llms: List[LLMClient],
    sut_model: Optional[str],
    run_id: str,
    log_internal: bool = True,
    judge_max_workers: int = 1,
) -> Dict[str, Any]:
    """Drive one full simulated session: emotional need → story → multi-judge."""
    started_at = datetime.now(timezone.utc).isoformat()
    LOGGER.info("[%s] Starting persona=%s", run_id, persona.id)

    sim_user = SimulatedUser(persona=persona, llm=sim_user_llm, log_internal=log_internal)

    participant_id = f"sim-{persona.id}-{uuid.uuid4().hex[:8]}"
    session = sut_client.start_session(
        participant_id=participant_id,
        selected_model=sut_model,
        session_metadata={
            "simulated": True,
            "persona_id": persona.id,
            "sim_user_model": sim_user_llm.config.model,
            "judge_models": [llm.config.model for llm in judge_llms],
            "run_id": run_id,
        },
    )
    session_id = session["session_id"]
    participant_id = session["participant_id"]
    LOGGER.info("[%s] session_id=%s participant_id=%s", run_id, session_id, participant_id)

    # ── 1) Emotional need ────────────────────────────────────────────────
    need_action = sim_user.next_action(phase="emotional_need", sut_state={})
    emotional_need = str(need_action.get("content") or persona.emotional_need).strip() \
        or persona.emotional_need or "I'm not sure what to say."

    initiate_resp = sut_client.initiate_story(
        emotional_need=emotional_need,
        session_id=session_id,
        participant_id=participant_id,
        user_id=participant_id,
    )
    story_id = initiate_resp["story_id"]
    questions_data = initiate_resp.get("questions_data") or [
        _coerce_question_dict(q) for q in initiate_resp.get("questions", [])
    ]
    suggested_keywords = initiate_resp.get("keywords") or []
    profile_keywords = initiate_resp.get("profile_keywords") or {}

    # ── 2) Clarifying questions ──────────────────────────────────────────
    answers: Dict[str, str] = {}
    for raw_q in questions_data:
        q_dict = _coerce_question_dict(raw_q)
        question_text = str(q_dict.get("question") or "").strip()
        if not question_text:
            continue
        action = sim_user.next_action(
            phase="clarifying_questions",
            sut_state={"question": q_dict},
        )
        answer = str(action.get("content") or "").strip() or "i don't know"
        answers[question_text] = answer

    # ── 3) Keyword selection ─────────────────────────────────────────────
    keyword_action = sim_user.next_action(
        phase="keyword_selection",
        sut_state={"keywords": suggested_keywords, "profile_keywords": profile_keywords},
    )
    selected_keywords = _normalize_keyword_list(keyword_action.get("content"), suggested_keywords)

    # ── 4) Generate the story (steps 1..5) ───────────────────────────────
    LOGGER.info("[%s] Generating story (5 steps)…", run_id)
    sut_client.create_step1(
        story_id=story_id,
        emotional_need=emotional_need,
        answers=answers,
        selected_keywords=selected_keywords,
        profile_keywords=profile_keywords,
        session_id=session_id,
        participant_id=participant_id,
        user_id=participant_id,
    )
    for step in (2, 3, 4, 5):
        sut_client.create_step(step, story_id)

    story = sut_client.get_story(story_id)

    # ── 5) Interactive play loop ─────────────────────────────────────────
    LOGGER.info("[%s] Entering interactive_play (max %d turns)", run_id, persona.max_user_turns)
    turn = 0
    consecutive_errors = 0
    while turn < persona.max_user_turns:
        turn += 1
        recent_messages = _extract_recent_messages(story)
        choices = _extract_choices(story)
        ending_available = _ending_available(story)

        action = sim_user.next_action(
            phase="interactive_play",
            sut_state={
                "recent_messages": recent_messages,
                "choices": choices,
                "ending_available": ending_available,
            },
        )

        kind = action.get("action")
        try:
            if kind == "end_story":
                LOGGER.info("[%s] Persona requested end_story at turn %d", run_id, turn)
                break
            if kind == "select_choice" and action.get("choice_id"):
                story = sut_client.select_choice(
                    story_id=story_id,
                    choice_id=str(action["choice_id"]),
                    session_id=session_id,
                    participant_id=participant_id,
                )
            else:
                content = str(action.get("content") or "").strip() or "..."
                story = sut_client.send_message(
                    story_id=story_id,
                    content=content,
                    session_id=session_id,
                    participant_id=participant_id,
                )
            consecutive_errors = 0
        except Exception as exc:
            consecutive_errors += 1
            LOGGER.error("[%s] SUT call failed at turn %d: %s", run_id, turn, exc)
            sim_user.transcript[-1].notes.append(f"sut_error: {exc}")
            if consecutive_errors >= 2:
                LOGGER.warning("[%s] Aborting run due to repeated SUT errors", run_id)
                break

        if isinstance(story, dict) and story.get("status") == "completed":
            LOGGER.info("[%s] Story marked completed by SUT", run_id)
            break

    # ── 6) End story ─────────────────────────────────────────────────────
    try:
        sut_client.end_story(story_id)
    except Exception as exc:
        LOGGER.warning("[%s] end_story failed (continuing to judge): %s", run_id, exc)

    # ── 7) Pull export bundle and judge ──────────────────────────────────
    try:
        export_bundle = sut_client.export_session(session_id)
    except Exception as exc:
        LOGGER.error("[%s] export_session failed: %s", run_id, exc)
        export_bundle = {}

    transcript_for_judge = _build_transcript_for_judge(export_bundle)
    sim_records = [asdict(r) for r in sim_user.transcript]

    multi_judge = run_multi_judge(
        persona=persona,
        sut_client=sut_client,
        judge_llms=judge_llms,
        export_bundle=export_bundle,
        transcript=transcript_for_judge,
        sim_turn_records=sim_records,
        max_workers=judge_max_workers,
    )

    finished_at = datetime.now(timezone.utc).isoformat()
    LOGGER.info(
        "[%s] DONE. sys_q_mean=%s ux_mean=%s slop_mean=%s (across %d judges)",
        run_id,
        multi_judge.aggregate.get("system_quality_mean"),
        multi_judge.aggregate.get("user_experience_mean"),
        multi_judge.aggregate.get("slop_score_mean"),
        len(multi_judge.per_judge),
    )

    return {
        "run_id": run_id,
        "persona_id": persona.id,
        "persona_display_name": persona.display_name,
        "session_id": session_id,
        "participant_id": participant_id,
        "story_id": story_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "config": {
            "sim_user_model": sim_user_llm.config.model,
            "sim_user_provider": sim_user_llm.config.provider,
            "judge_models": [llm.config.model for llm in judge_llms],
            "sut_base_url": sut_client.base_url,
            "sut_selected_model": sut_model,
            "max_user_turns": persona.max_user_turns,
        },
        "emotional_need_submitted": emotional_need,
        "clarifying_answers": answers,
        "selected_keywords": selected_keywords,
        "sim_turn_records": sim_records,
        "transcript_for_judge": transcript_for_judge,
        "judges": [
            {
                "model": r.model,
                "system_quality": r.system_quality,
                "user_experience": r.user_experience,
                "aggregate": r.aggregate,
            }
            for r in multi_judge.per_judge
        ],
        "aggregate_across_judges": multi_judge.aggregate,
    }


def _build_transcript_for_judge(export_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a flattened, role-tagged transcript from the export bundle."""
    if not isinstance(export_bundle, dict):
        return []

    final_view_story = export_bundle.get("final_view_story") or export_bundle.get("story") or {}
    characters = final_view_story.get("characters") or []
    char_lookup = {
        str(ch.get("id")): ch.get("name") or ch.get("id") for ch in characters if ch.get("id")
    }
    protagonist_id = next(
        (
            str(ch.get("id"))
            for ch in characters
            if str(ch.get("role", "")).lower() == "protagonist"
        ),
        None,
    )

    messages = (final_view_story.get("current_scene") or {}).get("messages") or []
    rendered: List[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        character_id = str(msg.get("character_id") or "system")
        if character_id == "system":
            role, speaker = "system", "System"
        elif protagonist_id and character_id == protagonist_id:
            role, speaker = "user", char_lookup.get(character_id, "User")
        else:
            role, speaker = "assistant", char_lookup.get(character_id, character_id)
        rendered.append(
            {
                "role": role,
                "speaker": speaker,
                "character_id": character_id,
                "content": msg.get("content", ""),
            }
        )

    if rendered:
        return rendered

    # fallback: derive from turn_logs
    turn_logs = export_bundle.get("turn_logs") or []
    for turn in turn_logs:
        if not isinstance(turn, dict):
            continue
        user_input = str(turn.get("user_input") or "").strip()
        if user_input:
            rendered.append({"role": "user", "speaker": "User", "content": user_input})
        response_text = str(turn.get("response_text") or "").strip()
        if response_text:
            rendered.append({"role": "assistant", "speaker": "Story", "content": response_text})
    return rendered


# ── CLI ──────────────────────────────────────────────────────────────────


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_results_path(out_dir: Path, batch_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"sim_runs_{batch_id}.jsonl"


def _write_jsonl(path: Path, record: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _preflight_sut(base_url: str) -> bool:
    try:
        with SUTClient(base_url=base_url, timeout=10.0) as client:
            client.list_models()
        return True
    except Exception as exc:
        LOGGER.error(
            "SUT health check failed for %s: %s. "
            "Make sure the backend is listening on this exact address, or pass --sut-base-url.",
            base_url,
            exc,
        )
        return False


def _default_sim_user_model_for_persona(persona: Persona) -> Optional[str]:
    return DEFAULT_SIM_USER_MODELS_BY_PERSONA.get(persona.id)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run LLM-simulated user sessions against EmoNest.")
    parser.add_argument(
        "--sut-base-url",
        default=os.environ.get("SUT_BASE_URL", "http://127.0.0.1:11454"),
        help="Base URL of the EmoNest backend (default: http://127.0.0.1:11454).",
    )
    parser.add_argument(
        "--persona",
        action="append",
        dest="personas",
        help="Persona id to include. Repeatable. Default: all personas in simulation/personas/.",
    )
    parser.add_argument("--runs", type=int, default=1, help="Runs per persona (default 1).")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Override each persona's max_user_turns (optional).",
    )
    parser.add_argument(
        "--sim-user-model",
        default=os.environ.get("SIM_USER_MODEL"),
        help="Model for the simulated user. Defaults to LLM_DEFAULT_MODEL from env.",
    )
    parser.add_argument(
        "--judge-model",
        action="append",
        dest="judge_models",
        help=(
            "OpenRouter judge model slug. Repeatable. "
            f"Default (each session judged by ALL of these): {', '.join(DEFAULT_JUDGE_MODELS)}"
        ),
    )
    parser.add_argument(
        "--sut-model",
        default=None,
        help="Optional 'selected_model' to send when starting the experiment session.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"Directory for JSONL output (default: {DEFAULT_RESULTS_DIR}).",
    )
    parser.add_argument(
        "--no-internal-state",
        action="store_true",
        help="Don't capture the persona's hidden internal_state in records.",
    )
    parser.add_argument(
        "--session-concurrency",
        type=int,
        default=5,
        help="Number of sessions to drive in parallel (default 5). Set to 1 for strict sequential.",
    )
    parser.add_argument(
        "--judge-concurrency",
        type=int,
        default=3,
        help="Number of judges to run in parallel within a single session (default 3).",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    all_personas = discover_personas()
    if not all_personas:
        LOGGER.error("No personas found in simulation/personas/.")
        return 2

    try:
        selected = filter_personas(all_personas, args.personas)
    except ValueError as exc:
        LOGGER.error(str(exc))
        return 2

    if args.max_turns is not None:
        for persona in selected:
            persona.raw.setdefault("end_condition", {})["max_user_turns"] = int(args.max_turns)

    sim_user_model_override = args.sim_user_model

    judge_model_slugs = args.judge_models or DEFAULT_JUDGE_MODELS
    judge_llms: List[LLMClient] = []
    for slug in judge_model_slugs:
        judge_config = LLMConfig.from_env(
            role="judge",
            default_model=slug,
            default_temperature=0.2,
        )
        # Force the slug through even if JUDGE_MODEL env is set, so each slot
        # in the list gets the model the user actually asked for.
        judge_config.model = slug
        judge_llms.append(LLMClient(judge_config))

    if sim_user_model_override:
        LOGGER.info("Simulated user model override: %s", sim_user_model_override)
    else:
        LOGGER.info(
            "Default simulated user models by persona: %s",
            {
                p.id: _default_sim_user_model_for_persona(p) or os.environ.get("LLM_DEFAULT_MODEL")
                for p in selected
            },
        )
    LOGGER.info(
        "Judge models (each session judged by all): %s",
        [llm.config.model for llm in judge_llms],
    )
    LOGGER.info("Personas: %s", [p.id for p in selected])
    LOGGER.info(
        "Concurrency: session=%d, judge=%d",
        max(1, args.session_concurrency),
        max(1, args.judge_concurrency),
    )

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _build_results_path(args.out_dir, batch_id)
    LOGGER.info("Writing results to %s", out_path)
    if not _preflight_sut(args.sut_base_url):
        return 2

    summary_rows: List[Dict[str, Any]] = []
    from threading import Lock
    from concurrent.futures import ThreadPoolExecutor

    output_lock = Lock()
    judge_max_workers = max(1, args.judge_concurrency)
    session_max_workers = max(1, args.session_concurrency)

    sessions_to_run = [
        (persona, run_idx)
        for persona in selected
        for run_idx in range(1, args.runs + 1)
    ]

    def _drive(persona: Persona, run_idx: int) -> Optional[Dict[str, Any]]:
        run_id = f"{persona.id}__{run_idx:02d}__{uuid.uuid4().hex[:6]}"
        start = time.perf_counter()
        try:
            sim_user_config = LLMConfig.from_env(
                role="sim_user",
                default_model=(
                    sim_user_model_override
                    or _default_sim_user_model_for_persona(persona)
                ),
                default_temperature=0.95,
            )
            sim_user_llm = LLMClient(sim_user_config)
            with SUTClient(base_url=args.sut_base_url) as sut_client:
                record = run_one_session(
                    persona=persona,
                    sut_client=sut_client,
                    sim_user_llm=sim_user_llm,
                    judge_llms=judge_llms,
                    sut_model=args.sut_model,
                    run_id=run_id,
                    log_internal=not args.no_internal_state,
                    judge_max_workers=judge_max_workers,
                )
            record["wall_time_seconds"] = round(time.perf_counter() - start, 2)
            with output_lock:
                _write_jsonl(out_path, record)
            aggregate = record["aggregate_across_judges"]
            return {
                "run_id": run_id,
                "persona": persona.id,
                "system_quality_mean": aggregate.get("system_quality_mean"),
                "user_experience_mean": aggregate.get("user_experience_mean"),
                "story_quality_mean": aggregate.get("story_quality_mean"),
                "human_benchmark_ux_mean": aggregate.get("human_benchmark_ux_mean"),
                "slop_score": aggregate.get("slop_score_mean"),
                "breaking_character_count": aggregate.get("breaking_character_count_mean"),
                "wall_time_seconds": record["wall_time_seconds"],
            }
        except Exception as exc:
            LOGGER.error("[%s] FAILED: %s\n%s", run_id, exc, traceback.format_exc())
            with output_lock:
                _write_jsonl(
                    out_path,
                    {
                        "run_id": run_id,
                        "persona_id": persona.id,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "wall_time_seconds": round(time.perf_counter() - start, 2),
                    },
                )
            return None

    if session_max_workers == 1:
        for persona, run_idx in sessions_to_run:
            row = _drive(persona, run_idx)
            if row is not None:
                summary_rows.append(row)
    else:
        with ThreadPoolExecutor(max_workers=session_max_workers) as executor:
            futures = [executor.submit(_drive, p, idx) for p, idx in sessions_to_run]
            for future in futures:
                row = future.result()
                if row is not None:
                    with output_lock:
                        summary_rows.append(row)

    _print_summary(summary_rows)
    return 0


def _print_summary(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("\nNo successful runs.")
        return
    print("\n=== Simulation summary ===")
    header = f"{'run_id':<48}  {'persona':<26}  {'sys_q':>6}  {'all_ux':>6}  {'story':>6}  {'ux':>6}  {'slop':>6}  {'breaks':>6}  {'sec':>6}"
    print(header)
    print("-" * len(header))
    for row in rows:
        breaks = row.get("breaking_character_count")
        breaks_str = f"{breaks:.1f}" if isinstance(breaks, (int, float)) else "-"
        print(
            f"{row['run_id']:<48}  "
            f"{row['persona']:<26}  "
            f"{row.get('system_quality_mean') if row.get('system_quality_mean') is not None else '-':>6}  "
            f"{row.get('user_experience_mean') if row.get('user_experience_mean') is not None else '-':>6}  "
            f"{row.get('story_quality_mean') if row.get('story_quality_mean') is not None else '-':>6}  "
            f"{row.get('human_benchmark_ux_mean') if row.get('human_benchmark_ux_mean') is not None else '-':>6}  "
            f"{row.get('slop_score') if row.get('slop_score') is not None else '-':>6}  "
            f"{breaks_str:>6}  "
            f"{row.get('wall_time_seconds', 0):>6}"
        )


if __name__ == "__main__":
    sys.exit(main())
