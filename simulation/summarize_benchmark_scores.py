"""Summarize simulation judge scores aligned to the human benchmark rubric.

Examples:
  python -m simulation.summarize_benchmark_scores
  python -m simulation.summarize_benchmark_scores --latest
  python -m simulation.summarize_benchmark_scores --overall
  python -m simulation.summarize_benchmark_scores --markdown benchmark_scores_model_compare.md
  python -m simulation.summarize_benchmark_scores simulation/results/sim_runs_20260426_150403.jsonl
  python -m simulation.summarize_benchmark_scores --by persona --by model --csv summary.csv --details-csv details.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "simulation" / "results"

STORY_SCORE_KEYS = (
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
SCORE_KEYS = STORY_SCORE_KEYS + UX_SCORE_KEYS


@dataclass(frozen=True)
class ScoreRow:
    source_file: str
    run_id: str
    persona_id: str
    story_id: str
    tested_model: str
    judge_model: str
    scores: Dict[str, int]
    story_quality_mean: Optional[float]
    ux_mean: Optional[float]
    all_score_mean: Optional[float]


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json_records(path: Path) -> Iterable[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(f"[warn] Skipping invalid JSONL line {path}:{line_no}: {exc}")
                    continue
                if isinstance(record, dict):
                    yield record
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[warn] Skipping invalid JSON file {path}: {exc}")
        return

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
    elif isinstance(payload, dict):
        if isinstance(payload.get("runs"), list):
            for item in payload["runs"]:
                if isinstance(item, dict):
                    yield item
        else:
            yield payload


def _discover_paths(inputs: Sequence[str], latest: bool) -> List[Path]:
    if inputs:
        paths: List[Path] = []
        for raw in inputs:
            path = Path(raw)
            if path.is_dir():
                paths.extend(sorted(path.glob("*.jsonl")))
                paths.extend(sorted(path.glob("*.json")))
            elif path.exists():
                paths.append(path)
            else:
                print(f"[warn] Input path does not exist: {path}")
        return sorted(dict.fromkeys(paths))

    paths = sorted(DEFAULT_RESULTS_DIR.glob("*.jsonl")) + sorted(DEFAULT_RESULTS_DIR.glob("*.json"))
    paths = sorted(dict.fromkeys(paths), key=lambda item: item.stat().st_mtime if item.exists() else 0)
    if latest and paths:
        return [paths[-1]]
    return paths


def _coerce_score(value: Any) -> Optional[int]:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if parsed < 1 or parsed > 5:
        return None
    return parsed


def _mean(values: Sequence[int]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


def _extract_scores(raw_scores: Dict[str, Any]) -> Optional[Dict[str, int]]:
    scores: Dict[str, int] = {}
    for key in SCORE_KEYS:
        score = _coerce_score(raw_scores.get(key))
        if score is None:
            return None
        scores[key] = score
    return scores


def _judge_entries(record: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    judges = record.get("judges")
    if isinstance(judges, list):
        for index, judge in enumerate(judges):
            judge_dict = _as_dict(judge)
            yield str(judge_dict.get("model") or f"judge-{index + 1}"), judge_dict
        return

    legacy_judge = _as_dict(record.get("judge"))
    if legacy_judge:
        config = _as_dict(record.get("config"))
        yield str(config.get("judge_model") or "judge"), legacy_judge


def collect_rows(paths: Sequence[Path]) -> Tuple[List[ScoreRow], Dict[str, int]]:
    rows: List[ScoreRow] = []
    counters = {
        "files": len(paths),
        "records": 0,
        "error_records": 0,
        "judge_entries": 0,
        "scored_entries": 0,
        "skipped_missing_scores": 0,
    }

    for path in paths:
        for record in _load_json_records(path):
            counters["records"] += 1
            if record.get("error"):
                counters["error_records"] += 1
                continue

            config = _as_dict(record.get("config"))
            tested_model = (
                str(config.get("sut_selected_model") or "").strip()
                or str(config.get("sut_model") or "").strip()
                or str(record.get("selected_model") or "").strip()
                or str(config.get("sim_user_model") or "").strip()
                or "unknown_model"
            )

            for judge_model, judge in _judge_entries(record):
                counters["judge_entries"] += 1
                user_experience = _as_dict(judge.get("user_experience"))
                scores = _extract_scores(_as_dict(user_experience.get("scores")))
                if scores is None:
                    counters["skipped_missing_scores"] += 1
                    continue

                counters["scored_entries"] += 1
                story_values = [scores[key] for key in STORY_SCORE_KEYS]
                ux_values = [scores[key] for key in UX_SCORE_KEYS]
                all_values = [scores[key] for key in SCORE_KEYS]
                rows.append(
                    ScoreRow(
                        source_file=str(path),
                        run_id=str(record.get("run_id") or ""),
                        persona_id=str(record.get("persona_id") or ""),
                        story_id=str(record.get("story_id") or ""),
                        tested_model=tested_model,
                        judge_model=judge_model,
                        scores=scores,
                        story_quality_mean=_mean(story_values),
                        ux_mean=_mean(ux_values),
                        all_score_mean=_mean(all_values),
                    )
                )
    return rows, counters


def collect_diagnostics(paths: Sequence[Path]) -> Tuple[Dict[str, Dict[str, Dict[str, int]]], Dict[str, int]]:
    model_files: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    skip_reasons: Dict[str, int] = defaultdict(int)

    for path in paths:
        for record in _load_json_records(path):
            if not isinstance(record, dict):
                model_files["unknown_model"][path.name]["invalid_record"] += 1
                skip_reasons["invalid_record"] += 1
                continue

            config = _as_dict(record.get("config"))
            tested_model = (
                str(config.get("sut_selected_model") or "").strip()
                or str(config.get("sut_model") or "").strip()
                or str(record.get("selected_model") or "").strip()
                or str(config.get("sim_user_model") or "").strip()
                or "unknown_model"
            )

            if record.get("error"):
                model_files[tested_model][path.name]["record_error"] += 1
                reason = str(record.get("error") or "")
                if "timed out" in reason:
                    skip_reasons["record_error: timed out"] += 1
                elif "LLM API" in reason:
                    skip_reasons["record_error: LLM API failure"] += 1
                else:
                    skip_reasons["record_error: other"] += 1
                continue

            has_judge = False
            for judge_model, judge in _judge_entries(record):
                has_judge = True
                user_experience = _as_dict(judge.get("user_experience"))
                scores = _as_dict(user_experience.get("scores"))
                parsed_scores = _extract_scores(scores)
                if parsed_scores is not None:
                    model_files[tested_model][path.name]["scored"] += 1
                    continue

                if user_experience.get("error"):
                    model_files[tested_model][path.name]["judge_error"] += 1
                    error_text = str(user_experience.get("error") or "")
                    if "Could not parse JSON" in error_text:
                        skip_reasons[f"judge_error: parse failed ({judge_model})"] += 1
                    elif "not a valid model ID" in error_text:
                        skip_reasons[f"judge_error: invalid judge model ({judge_model})"] += 1
                    else:
                        skip_reasons[f"judge_error: other ({judge_model})"] += 1
                    continue

                legacy_keys = {"felt_heard", "emotional_need_addressed", "persona_fit", "narrative_quality"}
                if legacy_keys.intersection(scores):
                    model_files[tested_model][path.name]["legacy_rubric"] += 1
                    skip_reasons["missing_scores: legacy rubric/no 11 dimensions"] += 1
                else:
                    model_files[tested_model][path.name]["missing_scores"] += 1
                    skip_reasons["missing_scores: incomplete 11 dimensions"] += 1

            if not has_judge:
                model_files[tested_model][path.name]["no_judges"] += 1
                skip_reasons["no_judges"] += 1

    return model_files, skip_reasons


def _stats(values: Sequence[int]) -> Dict[str, Any]:
    nums = list(values)
    if not nums:
        return {"n": 0, "mean": "", "median": "", "stdev": "", "min": "", "max": ""}
    stdev = statistics.stdev(nums) if len(nums) > 1 else 0.0
    return {
        "n": len(nums),
        "mean": round(statistics.mean(nums), 3),
        "median": round(statistics.median(nums), 3),
        "stdev": round(stdev, 3),
        "min": min(nums),
        "max": max(nums),
    }


def summarize_by_dimension(rows: Sequence[ScoreRow], group_by: Sequence[str] = ()) -> List[Dict[str, Any]]:
    buckets: Dict[Tuple[str, ...], List[ScoreRow]] = defaultdict(list)
    for row in rows:
        group_key = tuple(_group_value(row, key) for key in group_by)
        buckets[group_key].append(row)

    summary: List[Dict[str, Any]] = []
    for group_key, group_rows in sorted(buckets.items()):
        group_fields = dict(zip(group_by, group_key))
        for dimension in SCORE_KEYS:
            stats = _stats([row.scores[dimension] for row in group_rows])
            summary.append({**group_fields, "dimension": dimension, **stats})
        summary.append({**group_fields, "dimension": "story_quality_mean", **_float_stats([row.story_quality_mean for row in group_rows])})
        summary.append({**group_fields, "dimension": "ux_mean", **_float_stats([row.ux_mean for row in group_rows])})
        summary.append({**group_fields, "dimension": "all_score_mean", **_float_stats([row.all_score_mean for row in group_rows])})
    return summary


def _float_stats(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    nums = [value for value in values if isinstance(value, (int, float))]
    if not nums:
        return {"n": 0, "mean": "", "median": "", "stdev": "", "min": "", "max": ""}
    stdev = statistics.stdev(nums) if len(nums) > 1 else 0.0
    return {
        "n": len(nums),
        "mean": round(statistics.mean(nums), 3),
        "median": round(statistics.median(nums), 3),
        "stdev": round(stdev, 3),
        "min": round(min(nums), 3),
        "max": round(max(nums), 3),
    }


def _group_value(row: ScoreRow, key: str) -> str:
    if key == "persona":
        return row.persona_id
    if key == "model":
        return row.tested_model
    if key == "judge_model":
        return row.judge_model
    if key == "file":
        return Path(row.source_file).name
    raise ValueError(f"Unsupported group key: {key}")


def write_summary_csv(path: Path, summary: Sequence[Dict[str, Any]], group_by: Sequence[str]) -> None:
    fieldnames = [*group_by, "dimension", "n", "mean", "median", "stdev", "min", "max"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary)


def write_details_csv(path: Path, rows: Sequence[ScoreRow]) -> None:
    fieldnames = [
        "source_file",
        "run_id",
        "persona_id",
        "story_id",
        "tested_model",
        "judge_model",
        *SCORE_KEYS,
        "story_quality_mean",
        "ux_mean",
        "all_score_mean",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source_file": row.source_file,
                    "run_id": row.run_id,
                    "persona_id": row.persona_id,
                    "story_id": row.story_id,
                    "tested_model": row.tested_model,
                    "judge_model": row.judge_model,
                    **row.scores,
                    "story_quality_mean": row.story_quality_mean,
                    "ux_mean": row.ux_mean,
                    "all_score_mean": row.all_score_mean,
                }
            )


def _format_markdown_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _markdown_table(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_format_markdown_value(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def model_mean_comparison(rows: Sequence[ScoreRow]) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[ScoreRow]] = defaultdict(list)
    for row in rows:
        buckets[row.tested_model].append(row)

    comparison: List[Dict[str, Any]] = []
    for tested_model, model_rows in sorted(buckets.items()):
        item: Dict[str, Any] = {"model": tested_model, "n": len(model_rows)}
        for key in SCORE_KEYS:
            item[key] = _stats([row.scores[key] for row in model_rows])["mean"]
        item["story_quality_mean"] = _float_stats([row.story_quality_mean for row in model_rows])["mean"]
        item["ux_mean"] = _float_stats([row.ux_mean for row in model_rows])["mean"]
        item["all_score_mean"] = _float_stats([row.all_score_mean for row in model_rows])["mean"]
        comparison.append(item)
    return comparison


def transposed_model_mean_comparison(rows: Sequence[ScoreRow]) -> Tuple[List[str], List[Dict[str, Any]]]:
    comparison = model_mean_comparison(rows)
    models = [str(item["model"]) for item in comparison]
    columns = ["dimension", *models]
    dimensions = [*SCORE_KEYS, "story_quality_mean", "ux_mean", "all_score_mean"]
    table_rows: List[Dict[str, Any]] = []
    for dimension in dimensions:
        row: Dict[str, Any] = {"dimension": dimension}
        for item in comparison:
            row[str(item["model"])] = item.get(dimension, "")
        table_rows.append(row)
    n_row: Dict[str, Any] = {"dimension": "n"}
    for item in comparison:
        n_row[str(item["model"])] = item.get("n", "")
    return columns, [n_row, *table_rows]


def write_markdown_report(path: Path, rows: Sequence[ScoreRow], counters: Dict[str, int], source_paths: Sequence[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns, table_rows = transposed_model_mean_comparison(rows)
    source_names = ", ".join(source_path.name for source_path in source_paths)
    model_files, skip_reasons = collect_diagnostics(source_paths)
    file_rows: List[Dict[str, Any]] = []
    for model in sorted(model_files):
        for source_file in sorted(model_files[model]):
            counters_for_file = model_files[model][source_file]
            file_rows.append(
                {
                    "model": model,
                    "source_file": source_file,
                    "scored": counters_for_file.get("scored", 0),
                    "legacy_rubric": counters_for_file.get("legacy_rubric", 0),
                    "judge_error": counters_for_file.get("judge_error", 0),
                    "record_error": counters_for_file.get("record_error", 0),
                    "missing_scores": counters_for_file.get("missing_scores", 0),
                    "no_judges": counters_for_file.get("no_judges", 0),
                }
            )
    skip_rows = [
        {"reason": reason, "count": count}
        for reason, count in sorted(skip_reasons.items(), key=lambda item: (-item[1], item[0]))
    ]
    lines = [
        "# Benchmark Model Mean Comparison",
        "",
        f"- Source files: {len(source_paths)}",
        f"- Source file names: {source_names}",
        f"- Records: {counters['records']}",
        f"- Error records: {counters['error_records']}",
        f"- Judge entries: {counters['judge_entries']}",
        f"- Scored judge entries: {counters['scored_entries']}",
        f"- Skipped missing 11-score entries: {counters['skipped_missing_scores']}",
        "",
        "Only overall means are shown. Each model column pools all scored judge entries for that tested model.",
        "",
        _markdown_table(table_rows, columns),
        "",
        "## Source Files By Model",
        "",
        _markdown_table(
            file_rows,
            ["model", "source_file", "scored", "legacy_rubric", "judge_error", "record_error", "missing_scores", "no_judges"],
        ),
        "",
        "## Skipped / Missing Reasons",
        "",
        _markdown_table(skip_rows, ["reason", "count"]),
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(summary: Sequence[Dict[str, Any]], group_by: Sequence[str], limit: Optional[int]) -> None:
    rows = list(summary)
    if limit is not None:
        rows = rows[:limit]

    columns = [*group_by, "dimension", "n", "mean", "median", "stdev", "min", "max"]
    widths = {
        column: max([len(column), *(len(str(row.get(column, ""))) for row in rows)])
        for column in columns
    }
    header = "  ".join(column.ljust(widths[column]) for column in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        print("  ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", help="Result files or directories. Defaults to simulation/results.")
    parser.add_argument("--latest", action="store_true", help="Only summarize the newest default result file.")
    parser.add_argument(
        "--by",
        action="append",
        choices=("persona", "model", "judge_model", "file"),
        default=[],
        help="Group summary by persona, tested model, judge_model, or file. Repeatable. File grouping is included by default unless --overall is set.",
    )
    parser.add_argument("--overall", action="store_true", help="Pool all input files into one overall summary.")
    parser.add_argument("--csv", type=Path, help="Write the summary table to CSV.")
    parser.add_argument("--details-csv", type=Path, help="Write one row per run/judge score set to CSV.")
    parser.add_argument("--markdown", type=Path, help="Write one Markdown report, grouped by tested model, to this file.")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows printed to the console.")
    args = parser.parse_args(argv)

    paths = _discover_paths(args.inputs, args.latest)
    if not paths:
        print("No result files found.")
        return 1

    rows, counters = collect_rows(paths)
    print(
        "Loaded {records} records from {files} file(s); scored {scored_entries} judge entries; "
        "skipped {skipped_missing_scores} judge entries without the 11 benchmark scores; "
        "{error_records} records were errors.".format(**counters)
    )
    if not rows:
        print("No scored entries found. Run simulation with the updated benchmark judge first.")
        return 1

    group_by = list(args.by)
    if not args.overall and "file" not in group_by:
        group_by.insert(0, "file")

    summary = summarize_by_dimension(rows, group_by)
    print_summary(summary, group_by, args.limit)

    if args.csv:
        write_summary_csv(args.csv, summary, group_by)
        print(f"Wrote summary CSV: {args.csv}")
    if args.details_csv:
        write_details_csv(args.details_csv, rows)
        print(f"Wrote details CSV: {args.details_csv}")
    if args.markdown:
        write_markdown_report(args.markdown, rows, counters, paths)
        print(f"Wrote Markdown report: {args.markdown}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
