# EmoNest — Interactive Therapeutic Story Engine

EmoNest is an LLM-powered interactive storytelling platform that creates personalized, emotionally resonant narrative experiences. Users provide an emotional need, answer profiling questions, and are immersed in a cinematic, choice-driven story designed to offer therapeutic insight and engagement.

## Architecture

```
StoryGame-1/
├── backend/                 # FastAPI server (Python)
│   ├── src/
│   │   ├── main.py              # API routes & story lifecycle
│   │   ├── story_advancement.py # Per-turn LLM story engine
│   │   ├── prompt_templates.py  # All LLM prompt templates
│   │   ├── context_manager.py   # User profile, story state, journey tracking
│   │   ├── llm_client.py        # OpenAI-compatible LLM client (sync + streaming)
│   │   ├── meta_planner.py      # Reflection, interactive HTML elements, image gen
│   │   ├── config.py            # Environment-based configuration
│   │   ├── models.py            # Pydantic request/response models
│   │   ├── utils.py             # JSON extraction, character helpers, stagnation detection
│   │   ├── experiment_store.py  # SQLite experiment session persistence
│   │   └── rag_system.py        # (Experimental) RAG helpers
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # React + TypeScript SPA
│   ├── src/
│   │   ├── App.tsx              # Router
│   │   ├── contexts/            # StoryContext (API, streaming, state)
│   │   ├── pages/               # Home, StoryInteraction, StoryConclusion, …
│   │   └── components/          # UI widgets (progress, typewriter, emotions, …)
│   ├── package.json
│   └── .env.development
├── requirements.txt         # Global Python dependencies (mirrors backend/)
├── run_app.sh               # One-command launcher (macOS / Linux)
├── run_app.py               # One-command launcher (cross-platform)
└── README.md
```

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Python** | >= 3.9 | 3.10+ recommended |
| **Node.js** | >= 18 | LTS recommended |
| **npm** | >= 9 | (or **yarn** >= 1.22) |
| **conda** | optional | For virtual environment management |

You will also need **at least one** LLM API key:

- [OpenAI API key](https://platform.openai.com/api-keys) — for story generation and image generation
- [OpenRouter API key](https://openrouter.ai/keys) — alternative multi-model gateway
- [Google Gemini API key](https://aistudio.google.com/apikey) — optional, for image generation

And optionally:

- [Remove.bg API key](https://www.remove.bg/api) or [Replicate API token](https://replicate.com/account/api-tokens) — for character background removal

## Installation

### 1. Clone the repository

```bash
git clone <repo-url> StoryGame-1
cd StoryGame-1
```

### 2. Backend setup

```bash
# Create and activate a virtual environment (conda example)
conda create -n emonest python=3.10 -y
conda activate emonest

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Frontend setup

```bash
cd frontend
npm install        # or: yarn install
cd ..
```

### 4. Configure environment variables

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in your API keys. The minimum required configuration:

```env
# Choose provider: "openai" or "openrouter"
LLM_PROVIDER=openai

# Your API key (required)
LLM_API_KEY=sk-...

# Model routing (adjust to your preference)
LLM_DEFAULT_MODEL=gpt-4o-mini
LLM_STORY_MODEL=gpt-4o-mini
LLM_INTERACTIVE_ELEMENT_MODEL=gpt-4o
LLM_QUESTIONS_MODEL=gpt-4o-mini
LLM_KEYWORDS_MODEL=gpt-4o-mini
LLM_PROFILE_KEYWORDS_MODEL=gpt-4o-mini
LLM_REFLECTION_MODEL=gpt-4o

# Image generation (optional)
IMAGE_API_PROVIDER=openai          # "openai" or "gemini"
GEMINI_API_KEY=                    # required if IMAGE_API_PROVIDER=gemini

# Background removal (optional)
BG_REMOVAL_PROVIDER=removebg       # "removebg" or "replicate"
REMOVEBG_API_KEY=
REPLICATE_API_TOKEN=
```

The frontend reads `frontend/.env.development` for the API base URL (defaults to `http://localhost:11454`).

## Running the Application

### Option A: One-command launcher

```bash
# macOS / Linux
bash run_app.sh

# Cross-platform (Python)
python run_app.py
```

This starts both servers and prints the URLs when ready.

### Option B: Start servers manually

**Terminal 1 — Backend** (port 11454):

```bash
cd backend/src
python main.py
# or: uvicorn main:app --host 127.0.0.1 --port 11454
```

**Terminal 2 — Frontend** (port 3000):

```bash
cd frontend
npm start
```

### Access the app

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:11454 |
| API docs (Swagger) | http://localhost:11454/docs |

## Proxy Configuration (Optional)

If you need to route API traffic through a proxy:

```bash
# Via launcher script
bash run_app.sh --http-proxy=http://127.0.0.1:7890 --https-proxy=http://127.0.0.1:7890

# Or set in backend/.env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

## Key Features

- **5-step story generation** — foundation, world-building, characters, act structure, opening scene
- **Critic-and-refine pipeline** — LLM critic evaluates the story blueprint on novelty, engagement, and cinematic quality, then a refiner polishes it
- **Interactive storytelling** — free-text messages and branching choices drive the narrative
- **LLM plot progression check** — analyzes the last 5 dialogue rounds for stagnation and forces advancement when needed
- **Streaming responses** — real-time NPC dialogue via SSE
- **Meta-reflection** — periodic LLM analysis of pacing, user interest, and advancement strategy
- **Character image generation** — AI-generated character portraits with background removal
- **Scene background generation** — cinematic scene backgrounds
- **Experiment mode** — A/B testing with configurable LLM conditions and SQLite persistence
- **Context management** — rolling summaries, user journey tracking, emotional state monitoring

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | `openai` or `openrouter` |
| `LLM_API_KEY` | — | Primary API key (required) |
| `LLM_BASE_URL` | auto | Override API base URL |
| `LLM_DEFAULT_MODEL` | `gpt-4o-mini` | Default model for misc tasks |
| `LLM_STORY_MODEL` | `gpt-4o-mini` | Model for story generation |
| `LLM_INTERACTIVE_ELEMENT_MODEL` | `gpt-4o` | Model for interactive HTML elements |
| `LLM_QUESTIONS_MODEL` | `gpt-4o-mini` | Model for clarifying questions |
| `LLM_KEYWORDS_MODEL` | `gpt-4o-mini` | Model for keyword suggestions |
| `LLM_PROFILE_KEYWORDS_MODEL` | `gpt-4o-mini` | Model for profile keyword generation |
| `LLM_REFLECTION_MODEL` | `gpt-4o` | Model for meta-reflection |
| `LLM_TEMPERATURELESS_MODELS` | — | Comma-separated list of models that reject temperature |
| `IMAGE_API_PROVIDER` | `openai` | `openai` or `gemini` |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `BG_REMOVAL_PROVIDER` | `removebg` | `removebg` or `replicate` |
| `REMOVEBG_API_KEY` | — | Remove.bg API key |
| `REPLICATE_API_TOKEN` | — | Replicate API token |
| `HTTP_PROXY` / `HTTPS_PROXY` | — | Optional proxy URLs |
| `EXPERIMENT_DB_PATH` | `data/emobenchmark.sqlite3` | SQLite database path |
| `EXPORT_OUTPUT_DIR` | `exports` | Directory for data exports |

## Changelog

### 2025-06-30
- Add iteration summary for advancing story

### 2025-06-24
- Add user constraint for story generation
- Modify prompt templates

### 2025-06-21
- Add multiple choices for clarification questions
- Add keywords selection for profiling
- Fix background bugs

### 2025-06-20
- Add character image generation (DALL-E 3)
- Add chat background image generation
- Add start homepage

### 2025-09-30
- Redesign all UI styles (background, fonts, colors)

### 2025-10-01
- Add proceed flow for interactive elements
- Change character page and avatar style

### 2026-03-31
- Enforce novelty checks for generated interactive elements with similarity scoring, one retry, and persisted summary/tag history
- Add stronger story-structure guards so long scenes must introduce a reveal, shift, escalation, or transition instead of stalling
- Add schema validation and normalization for story advancement payloads before they reach chat or UI
- Expose richer story metadata in API responses, including recap, clues, tensions, objective, act progress, cast status, countdown, and interactive-element history
- Expand context memory with rolling recap buckets such as what just happened, current goal, open tensions, active clues, and last major turning point
- Update frontend story typing and response merging so streamed and non-streamed story metadata stay in sync
- Enrich live story UI with a stronger right-side info panel, more cinematic message styling, better scene transition presentation, and interactive-moment history
- Upgrade interactive element framing to feel more like a premium story artifact
- Fix Cast panel click error caused by the role badge interaction handling
- Make interactive elements auto-resize to fit their iframe content so they are no longer clipped by a too-small container
