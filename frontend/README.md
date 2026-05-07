<h1 align="center">NARRA-Gym Frontend</h1>
<h4 align="center">React + TypeScript SPA — the reader-facing surface of the engine</h4>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=white" alt="React 18">
  <img src="https://img.shields.io/badge/TypeScript-4.9-3178C6.svg?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/MUI-7-007FFF.svg?logo=mui&logoColor=white" alt="MUI 7">
  <img src="https://img.shields.io/badge/three.js-0.161-000000.svg?logo=three.js&logoColor=white" alt="three.js">
  <img src="https://img.shields.io/badge/CRA-5-09D3AC.svg?logo=createreactapp&logoColor=white" alt="Create React App">
</p>

> See the [project root README](../README.md) for architecture, benchmark workflow, and the engine itself.

---

## Routes

Routing lives in [`src/App.tsx`](src/App.tsx).

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | `Home` | Landing page — choose between the live engine and benchmark mode |
| `/start` | `EmotionalNeedForm` | Step 1 — user types in what they're feeling |
| `/clarify-questions` | `ClarifyingQuestionsForm` | Step 2 — clarifying questions + keyword selection |
| `/story/preview` | `StoryPreview` | Cinematic intro before the interaction loop |
| `/story/interaction` | `StoryInteraction` | The live story — streamed dialogue, branching choices, embedded artifacts |
| `/conclusion` | `StoryConclusion` | End-of-session reflection + 11-dimension feedback form |
| `/experiment` | `ExperimentMode` | Benchmark mode — pick model, manage blind / quick-test sessions |
| `/experiment/judge` | `BenchmarkJudgePage` | Reviewer view — score completed sessions |
| `/debug/progress` | `ProgressHarness` | Internal harness for testing progress UI |

---

## Source Layout

```
frontend/src/
├── App.tsx                          # Theme + Router + StoryProvider
├── index.tsx                        # Entry point
│
├── pages/                           # one component per route
│   ├── Home.tsx
│   ├── EmotionalNeedForm.tsx
│   ├── ClarifyingQuestionsForm.tsx
│   ├── StoryPreview.tsx
│   ├── StoryInteraction.tsx         # the main session view
│   ├── StoryConclusion.tsx          # post-session feedback
│   ├── ExperimentMode.tsx           # benchmark setup
│   └── BenchmarkJudge.tsx           # human evaluation view
│
├── contexts/
│   └── StoryContext.tsx             # API client, SSE streaming, story state
│
├── components/                      # reusable UI widgets
│   ├── ShaderBackground.tsx         # three.js shader background
│   ├── Typewriter.tsx               # streamed-text typewriter effect
│   ├── StoryProgressBar.tsx
│   ├── StoryIntroAnimation.tsx
│   ├── EmotionalJourneyMap.tsx      # journey visualization
│   ├── EmotionalWeather.tsx         # ambient state indicator
│   ├── InteractiveElement.tsx       # iframe sandbox for artifact HTML
│   ├── TranscriptPane.tsx
│   ├── BenchmarkEvaluationForm.tsx  # 11-dimension rubric
│   ├── BenchmarkSessionHistoryDialog.tsx
│   ├── FeedbackWidget.tsx
│   ├── JourneyButton.tsx
│   ├── MixedRichText.tsx
│   ├── SpacetimeWarp.tsx
│   └── DebugPanel.tsx
│
├── utils/
│   └── localBenchmarkReview.ts      # localStorage helpers (versioned + legacy fallback)
│
├── types/                           # shared TypeScript types
└── data/                            # static seed data
```

---

## Environment Variables

Configured via [`.env.development`](.env.development):

| Variable | Default | Purpose |
|---|---|---|
| `REACT_APP_API_BASE_URL` | `http://localhost:11454` | Backend FastAPI URL |
| `REACT_APP_HTTP_PROXY` | — | Optional outbound proxy (mirrored from `run_app.sh`) |
| `REACT_APP_HTTPS_PROXY` | — | Optional outbound proxy |

Only `REACT_APP_*` prefixed variables are exposed to the browser bundle (CRA convention).

---

## Scripts

```bash
npm start          # dev server at http://localhost:3000 (hot reload)
npm test           # Jest watch mode
npm run build      # production bundle into build/
npm run eject      # ⚠️ one-way — only if you need full webpack/Babel/ESLint control
```

Tests use `@testing-library/react`. The shader background is mocked in `App.test.tsx` to avoid WebGL during JSDOM runs.

---

## Theme & Styling

A custom MUI theme (defined in `App.tsx`) implements the project's "Apple-inspired healing" aesthetic:

- **Palette**: sage `#7db8a2` × peach `#e8a898` × lavender accents on warm cream paper
- **Typography**: *Cormorant Garamond* (display) + *Manrope* (body), loaded from Google Fonts
- **Surfaces**: glassmorphism — `backdrop-filter: blur(20px) saturate(180%)` on `Paper`/`Card`
- **Buttons**: gradient-filled with subtle hover lift (`translateY(-0.5px)`)
- **Background**: full-screen three.js shader (`ShaderBackground`)

If you change palette or fonts, do it inside the `theme = createTheme({...})` block in `App.tsx` — do **not** add ad-hoc styles in component files.

---

## Notes

- `localStorage` keys are still prefixed `emonest:*` for backwards compatibility — see `src/utils/localBenchmarkReview.ts` (`LEGACY_STORAGE_PREFIXES`). Renaming would orphan existing user benchmark histories.
- The frontend talks to the backend over plain HTTP + Server-Sent Events for streamed dialogue; no WebSocket.
- All routes share a single `StoryProvider` so navigation between pages preserves session state.
