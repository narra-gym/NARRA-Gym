"""Run the simulation benchmark sequentially across the configured SUT models."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class SutModel:
    model: str
    provider: str


SUT_MODELS: tuple[SutModel, ...] = (
    SutModel("openai/gpt-5.4", "OpenRouter"),
    SutModel("anthropic/claude-opus-4.6", "OpenRouter"),
    SutModel("anthropic/claude-sonnet-4.6", "OpenRouter"),
    SutModel("google/gemini-3.1-pro-preview", "OpenRouter"),
    SutModel("deepseek/deepseek-v4-pro", "OpenRouter"),
    SutModel("z-ai/glm-5.1", "OpenRouter"),
    SutModel("qwen/qwen3.5-397b-a17b", "OpenRouter"),
    SutModel("z-ai/glm-5", "OpenRouter"),
    SutModel("deepseek/deepseek-v3.2", "OpenRouter"),
)


def _safe_dir_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_")


def _build_runner_command(args: argparse.Namespace, entry: SutModel, model_out_dir: Path) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "simulation.runner",
        "--sut-model",
        entry.model,
        "--sut-base-url",
        args.sut_base_url,
        "--runs",
        str(args.runs),
        "--out-dir",
        str(model_out_dir),
        "--session-concurrency",
        str(args.session_concurrency),
        "--judge-concurrency",
        str(args.judge_concurrency),
    ]

    for persona_id in args.persona:
        command.extend(["--persona", persona_id])

    if args.max_turns is not None:
        command.extend(["--max-turns", str(args.max_turns)])

    if args.sim_user_model:
        command.extend(["--sim-user-model", args.sim_user_model])

    for judge_model in args.judge_model:
        command.extend(["--judge-model", judge_model])

    if args.no_internal_state:
        command.append("--no-internal-state")

    if args.verbose_runner:
        command.append("--verbose")

    return command


def _format_command(command: List[str]) -> str:
    return subprocess.list2cmdline(command)


def _audit_output_model(model_out_dir: Path, expected_model: str, started_epoch: float) -> List[str]:
    issues: List[str] = []
    new_files = [
        path
        for path in model_out_dir.glob("sim_runs_*.jsonl")
        if path.stat().st_mtime >= started_epoch - 1
    ]
    if not new_files:
        return [f"No new sim_runs_*.jsonl file found in {model_out_dir}."]

    checked = 0
    for path in new_files:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    issues.append(f"{path}:{line_number} is not valid JSON: {exc}")
                    continue
                if record.get("error"):
                    continue
                checked += 1
                config = record.get("config") or {}
                actual_model = config.get("sut_selected_model")
                if actual_model != expected_model:
                    issues.append(
                        f"{path}:{line_number} has sut_selected_model={actual_model!r}, "
                        f"expected {expected_model!r}."
                    )

    if checked == 0:
        issues.append(f"No successful records found in new output files for {expected_model}.")
    return issues


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run python -m simulation.runner sequentially for each SUT model."
    )
    parser.add_argument("--runs", type=int, default=1, help="Runs per persona for each SUT model.")
    parser.add_argument(
        "--persona",
        action="append",
        default=[],
        help="Persona id to include. Repeatable. Default: all personas.",
    )
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--sut-base-url", default="http://127.0.0.1:11454")
    parser.add_argument("--out-dir", type=Path, default=Path("simulation/results/model_sweep"))
    parser.add_argument(
        "--session-concurrency",
        type=int,
        default=1,
        help="Sessions to run in parallel inside each model batch. Default keeps logs clean.",
    )
    parser.add_argument("--judge-concurrency", type=int, default=3)
    parser.add_argument("--sim-user-model", default=None)
    parser.add_argument(
        "--judge-model",
        action="append",
        default=[],
        help="Override judge model. Repeatable. Default: runner's multi-judge defaults.",
    )
    parser.add_argument("--no-internal-state", action="store_true")
    parser.add_argument("--verbose-runner", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--skip-output-audit",
        action="store_true",
        help="Do not verify that each new JSONL record has the expected sut_selected_model.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for index, entry in enumerate(SUT_MODELS, start=1):
        model_out_dir = args.out_dir / _safe_dir_name(entry.model)
        model_out_dir.mkdir(parents=True, exist_ok=True)
        command = _build_runner_command(args, entry, model_out_dir)

        print()
        print(f"[{index}/{len(SUT_MODELS)}] Running SUT model: {entry.model} ({entry.provider})")
        print(f"Output: {model_out_dir}")
        print(f"Command: {_format_command(command)}")

        started = time.perf_counter()
        started_epoch = time.time()
        if args.dry_run:
            exit_code = 0
        else:
            completed = subprocess.run(command)
            exit_code = completed.returncode
        elapsed = round(time.perf_counter() - started, 2)

        audit_issues: List[str] = []
        if exit_code == 0 and not args.dry_run and not args.skip_output_audit:
            audit_issues = _audit_output_model(model_out_dir, entry.model, started_epoch)
            if audit_issues:
                exit_code = 1
                for issue in audit_issues:
                    print(f"AUDIT FAILED: {issue}", file=sys.stderr)

        results.append((entry.model, entry.provider, exit_code, elapsed, model_out_dir))
        if exit_code != 0:
            print(f"FAILED: {entry.model} exited with code {exit_code}", file=sys.stderr)
            if args.stop_on_failure:
                break

    print()
    print("=== SUT model sweep summary ===")
    for model, provider, exit_code, elapsed, model_out_dir in results:
        print(
            f"{model:<36} {provider:<13} exit={exit_code:<3} "
            f"sec={elapsed:<8} out={model_out_dir}"
        )

    return 1 if any(row[2] != 0 for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
