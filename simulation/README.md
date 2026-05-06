# EmoNest Simulation Framework

LLM-driven simulated users + LLM-as-a-judge for benchmarking the EmoNest
interactive story engine.

## What it does

For each run, the framework:

1. Loads a **persona** YAML (e.g. an anxious PhD student, a grieving father).
2. Spins up a **simulated user agent** (LLM #1) that stays in character and
   produces every required input: emotional need, clarifying-question answers,
   keyword selections, free-text messages, and branching choices.
3. Drives the real EmoNest backend end-to-end via its HTTP API as a black box.
4. After the session ends, runs **two scorers**:
   - the existing backend `/experiments/judge` for system-quality scores
     (overall, emotional alignment, narrative coherence, supportiveness, slop_stats),
   - a **persona-aware user-experience judge** (LLM #2, *different model
     recommended*) that uses the same 11 score fields as the human benchmark
     feedback form: `story_relevance`, `story_coherence`, `story_empathy`,
     `story_surprise`, `story_engagement`, `story_complexity`,
     `character_shaping`, `ux_story_satisfaction`,
     `ux_perceived_story_quality`, `ux_process_engagement`,
     `ux_use_again_intent`, plus `breaking_character_count`,
     `worst_moment`, `best_moment`, and `failure_modes`.
5. Appends one JSON line per run to `simulation/results/sim_runs_*.jsonl`.

## Layout

```
simulation/
├── personas/                 # one YAML per persona (15 included)
├── llm.py                    # OpenAI-compatible client + .env loader
├── personas.py               # persona loader
├── sut_client.py             # HTTP wrapper around the EmoNest backend
├── simulated_user.py         # the persona-faithful user agent
├── judge.py                  # backend judge passthrough + extended UX rubric
├── runner.py                 # orchestrator + CLI
└── results/                  # JSONL output, one file per CLI invocation
```

## Prerequisites

```bash
pip install pyyaml httpx openai
```

PyYAML, httpx, and openai are likely already installed via
`requirements.txt`. If not, install them.

## Configuration

`simulation/llm.py` automatically loads `backend/.env`, so the same keys you
already configured for the backend will work. You can override per role with:

| env var                   | purpose                                       |
| ------------------------- | --------------------------------------------- |
| `SIM_USER_PROVIDER`       | `openrouter` / `openai` / etc.                |
| `SIM_USER_API_KEY`        | API key for the simulated-user model          |
| `SIM_USER_BASE_URL`       | Override base URL                             |
| `SIM_USER_MODEL`          | Model id, e.g. `openai/gpt-5.4-mini`          |
| `SIM_USER_TEMPERATURE`    | float, default 0.95                           |
| `JUDGE_PROVIDER`          | (same)                                        |
| `JUDGE_API_KEY`           | (same)                                        |
| `JUDGE_BASE_URL`          | (same)                                        |
| `JUDGE_MODEL`             | model id; recommended **different family**    |
| `JUDGE_TEMPERATURE`       | float, default 0.2                            |
| `SUT_BASE_URL`            | EmoNest backend URL (default 127.0.0.1:11454) |

Strongly recommended: pick a different model family for the judge than for the
simulated user, otherwise scores skew high (self-preference bias).

## Quick start

1. Start the EmoNest backend (so the API is reachable):
   ```bash
   bash run_app.sh        # or python run_app.py
   ```

2. Run a single persona once (smoke test):
   ```bash
   python -m simulation.runner --persona burnt_out_engineer --runs 1 --verbose
   ```

3. Run the whole persona library 3 times each:
   ```bash
   python -m simulation.runner --runs 3
   ```

4. Compare two SUT model conditions (assuming you have configured them as
   benchmark conditions in the backend):
   ```bash
   python -m simulation.runner --sut-model openai/gpt-5.4 --runs 5 \
     --out-dir simulation/results/condA
   python -m simulation.runner --sut-model openai/gpt-5.4-mini --runs 5 \
     --out-dir simulation/results/condB
   ```

## Output format (one line per run)

Each JSON line in `sim_runs_*.jsonl` includes:

```json
{
  "run_id": "burnt_out_engineer__01__a1b2c3",
  "persona_id": "burnt_out_engineer",
  "session_id": "...",
  "story_id": "...",
  "config": {"sim_user_model": "...", "judge_model": "...", ...},
  "emotional_need_submitted": "...",
  "clarifying_answers": {...},
  "selected_keywords": [...],
  "sim_turn_records": [
    {"turn_index": 1, "phase": "emotional_need", "user_action": {...},
     "internal_state": "feeling skeptical but tired", ...}
  ],
  "transcript_for_judge": [{"role": "...", "speaker": "...", "content": "..."}],
  "judge": {
    "system_quality": { ...output of /experiments/judge... },
    "user_experience": {
      "form_version": "benchmark_emotional_human_v4",
      "scores": {
        "story_relevance": 4,
        "story_coherence": 3,
        "story_empathy": 4,
        "story_surprise": 3,
        "story_engagement": 4,
        "story_complexity": 3,
        "character_shaping": 4,
        "ux_story_satisfaction": 4,
        "ux_perceived_story_quality": 4,
        "ux_process_engagement": 3,
        "ux_use_again_intent": 3
      },
      "story_quality_mean": 3.57,
      "ux_mean": 3.5,
      "breaking_character_count": 0,
      "worst_moment": "...",
      "best_moment": "...",
      "qualitative_summary": "...",
      "failure_modes": ["sycophancy", "advice-too-soon"]
    },
    "aggregate": {
      "system_quality_mean": 3.5,
      "user_experience_mean": 3.78,
      "story_quality_mean": 3.57,
      "human_benchmark_ux_mean": 3.5,
      "slop_score": 22.4,
      "breaking_character_count": 0
    }
  },
  "wall_time_seconds": 142.7
}
```

## Adding a persona

Drop a new YAML into `simulation/personas/`. Recommended keys:

```yaml
id: short_unique_id
display_name: "Human-readable label"
language: en
demographics: {age: ..., gender: ..., occupation: ..., cultural_background: ...}
emotional_need: |
  Multi-line description of why they showed up.
big_five: {openness: ..., ...}
conversation_style:
  verbosity: short | medium | long
  formality: ...
  emoji_use: never | rare | occasional | frequent
  punctuation: ...
  notes: "Voice details that help the LLM impersonate them."
goals: [...]
resistance_patterns: [...]
end_condition:
  type: turns_or_satisfaction
  max_user_turns: 12
  satisfaction_signal: "..."
clarifying_question_style: |
  Guidance on how this persona answers profiling questions.
```

The whole YAML is fed to the simulated-user LLM as the persona card, so any
extra structure you add (e.g. `triggers`, `linguistic_quirks`) will be honored.

## Notes & known caveats

- **Cost**: a single full run is roughly 30–40 LLM calls (≈ 5 for story
  generation + ~12 turns × ~2 model calls + 2 judge calls). Multiply by
  `personas × runs`.
- **Self-preference bias**: always pair `--sim-user-model` and `--judge-model`
  from different model families when you can.
- **Reproducibility**: fix `SIM_USER_TEMPERATURE` and `JUDGE_TEMPERATURE` to
  small values for tighter variance, but you'll lose persona realism.
- The runner is synchronous on purpose (one session at a time). For parallel
  sweeps, run multiple processes with different `--out-dir` values.
