"""Re-run failed 11-dimension user-experience judges from saved simulation results.

This repairs judge JSON parse failures without re-running the full story simulation.

Examples:
  python -m simulation.rejudge_failed_scores --dry-run
  python -m simulation.rejudge_failed_scores --judge-model google/gemini-3.1-pro-preview --in-place
  python -m simulation.rejudge_failed_scores simulation/results/sim_runs_20260426_152705.jsonl --out-dir simulation/results/rejudged
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .judge import (
    BENCHMARK_SCORE_KEYS,
    BENCHMARK_FEEDBACK_FORM_VERSION,
    USER_EXPERIENCE_JUDGE_MAX_TOKENS,
    JudgeResult,
    _aggregate_across_judges,
    _normalize_user_experience,
    aggregate_scores,
    build_user_experience_messages,
    render_internal_states_for_judge,
    render_transcript_for_judge,
)
from .llm import LLMClient, LLMConfig
from .personas import Persona, discover_personas


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "simulation" / "results"
DEFAULT_JUDGE_MODEL = "google/gemini-3.1-pro-preview"

LOGGER = logging.getLogger("simulation.rejudge_failed_scores")


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                LOGGER.warning("Skipping invalid JSONL line %s:%s: %s", path, line_no, exc)
                continue
            if isinstance(payload, dict):
                payload["_rejudge_source_line"] = line_no
                records.append(payload)
    return records


def _write_jsonl(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            record = dict(record)
            record.pop("_rejudge_source_line", None)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _discover_paths(inputs: Sequence[str]) -> List[Path]:
    if inputs:
        paths: List[Path] = []
        for raw in inputs:
            path = Path(raw)
            if path.is_dir():
                paths.extend(sorted(path.glob("*.jsonl")))
            elif path.exists():
                paths.append(path)
            else:
                LOGGER.warning("Input path does not exist: %s", path)
        return sorted(dict.fromkeys(paths))
    return sorted(DEFAULT_RESULTS_DIR.glob("*.jsonl"))


def _has_all_benchmark_scores(user_experience: Dict[str, Any]) -> bool:
    scores = user_experience.get("scores")
    if not isinstance(scores, dict):
        return False
    return all(key in scores for key in BENCHMARK_SCORE_KEYS)


def _is_rejudge_target(judge: Dict[str, Any], judge_model: str) -> bool:
    if str(judge.get("model") or "") != judge_model:
        return False
    user_experience = judge.get("user_experience")
    if not isinstance(user_experience, dict):
        return True
    if _has_all_benchmark_scores(user_experience):
        return False
    if user_experience.get("form_version") == BENCHMARK_FEEDBACK_FORM_VERSION:
        return True
    if user_experience.get("error"):
        return True
    return False


def _as_judge_result(judge: Dict[str, Any]) -> JudgeResult:
    user_experience = judge.get("user_experience")
    if not isinstance(user_experience, dict):
        user_experience = {}
    system_quality = judge.get("system_quality")
    if not isinstance(system_quality, dict):
        system_quality = {}
    aggregate = judge.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = aggregate_scores(system_quality, user_experience)
    return JudgeResult(
        model=str(judge.get("model") or ""),
        system_quality=system_quality,
        user_experience=user_experience,
        aggregate=aggregate,
    )


def _recompute_cross_judge_aggregate(record: Dict[str, Any]) -> None:
    judges = record.get("judges")
    if not isinstance(judges, list):
        return
    per_judge = [_as_judge_result(judge) for judge in judges if isinstance(judge, dict)]
    record["aggregate_across_judges"] = _aggregate_across_judges(per_judge)


def _rejudge_one(
    *,
    record: Dict[str, Any],
    judge: Dict[str, Any],
    persona: Persona,
    llm: LLMClient,
) -> None:
    transcript = record.get("transcript_for_judge")
    if not isinstance(transcript, list):
        raise ValueError("record has no transcript_for_judge list")
    turn_records = record.get("sim_turn_records")
    if not isinstance(turn_records, list):
        turn_records = []

    transcript_text = render_transcript_for_judge(transcript)
    internal_states_text = render_internal_states_for_judge(turn_records)
    messages = build_user_experience_messages(
        persona=persona,
        transcript_text=transcript_text,
        internal_states_text=internal_states_text,
    )
    parsed = llm.chat_json(messages, max_tokens=USER_EXPERIENCE_JUDGE_MAX_TOKENS)
    user_experience = _normalize_user_experience(parsed)

    system_quality = judge.get("system_quality")
    if not isinstance(system_quality, dict):
        system_quality = {}
    judge["user_experience"] = user_experience
    judge["aggregate"] = aggregate_scores(system_quality, user_experience)


def _target_count(records: Sequence[Dict[str, Any]], judge_model: str) -> int:
    count = 0
    for record in records:
        judges = record.get("judges")
        if not isinstance(judges, list) or record.get("error"):
            continue
        count += sum(
            1 for judge in judges if isinstance(judge, dict) and _is_rejudge_target(judge, judge_model)
        )
    return count


def rejudge_paths(
    *,
    paths: Sequence[Path],
    judge_model: str,
    dry_run: bool,
    in_place: bool,
    out_dir: Optional[Path],
) -> int:
    personas = {persona.id: persona for persona in discover_personas()}
    llm: Optional[LLMClient] = None
    total_targets = 0
    total_repaired = 0
    total_failed = 0

    for path in paths:
        records = _load_jsonl(path)
        targets = _target_count(records, judge_model)
        total_targets += targets
        if targets == 0:
            continue

        print(f"{path}: {targets} failed judge(s) to rejudge")
        if dry_run:
            for record in records:
                if record.get("error"):
                    continue
                persona_id = str(record.get("persona_id") or "")
                line_no = record.get("_rejudge_source_line", "?")
                for judge in record.get("judges") or []:
                    if isinstance(judge, dict) and _is_rejudge_target(judge, judge_model):
                        print(f"  line {line_no}: persona={persona_id} judge={judge_model}")
            continue

        if llm is None:
            config = LLMConfig.from_env(role="judge", default_model=judge_model, default_temperature=0.2)
            config.model = judge_model
            llm = LLMClient(config)

        changed = False
        for record in records:
            if record.get("error"):
                continue
            persona_id = str(record.get("persona_id") or "")
            persona = personas.get(persona_id)
            if persona is None:
                LOGGER.warning("Skipping %s line %s: unknown persona_id=%s", path, record.get("_rejudge_source_line"), persona_id)
                total_failed += 1
                continue
            judges = record.get("judges")
            if not isinstance(judges, list):
                continue
            repaired_record = False
            for judge in judges:
                if not isinstance(judge, dict) or not _is_rejudge_target(judge, judge_model):
                    continue
                try:
                    _rejudge_one(record=record, judge=judge, persona=persona, llm=llm)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.error(
                        "Rejudge failed for %s line %s persona=%s judge=%s: %s",
                        path,
                        record.get("_rejudge_source_line"),
                        persona_id,
                        judge_model,
                        exc,
                    )
                    total_failed += 1
                    continue
                total_repaired += 1
                changed = True
                repaired_record = True
                print(f"  repaired line {record.get('_rejudge_source_line')}: persona={persona_id}")
            if repaired_record:
                _recompute_cross_judge_aggregate(record)

        if changed:
            if in_place:
                output_path = path
            else:
                target_dir = out_dir or path.parent
                output_path = target_dir / f"{path.stem}.rejudged{path.suffix}"
            _write_jsonl(output_path, records)
            print(f"  wrote {output_path}")

    print(
        f"Done. targets={total_targets}, repaired={total_repaired}, failed={total_failed}, dry_run={dry_run}"
    )
    return 1 if total_failed else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-run failed 11-dimension user-experience judges from saved simulation JSONL files."
    )
    parser.add_argument("inputs", nargs="*", help="JSONL file(s) or directory/directories. Default: simulation/results/*.jsonl")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help=f"Judge model to repair (default: {DEFAULT_JUDGE_MODEL}).")
    parser.add_argument("--dry-run", action="store_true", help="Only list target rows; do not call the LLM or write files.")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the original JSONL files with repaired judge results.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Write repaired copies to this directory instead of overwriting.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.in_place and args.out_dir:
        parser.error("--in-place and --out-dir are mutually exclusive")

    paths = _discover_paths(args.inputs)
    if not paths:
        print("No JSONL result files found.")
        return 2

    dry_run = args.dry_run or (not args.in_place and args.out_dir is None)
    return rejudge_paths(
        paths=paths,
        judge_model=args.judge_model,
        dry_run=dry_run,
        in_place=args.in_place,
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
