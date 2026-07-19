# MVP Implementation Plan — Learning Curriculum Builder

> Milestone 1 of 2. This document is the build spec for the MVP: a CLI engine that takes a
> persona JSON and outputs a YouTube curriculum, plus the evaluation harness and test set.
> It is written to be executed by Claude sub-agents; each work package has explicit
> acceptance criteria. Milestone 2 is specified in `plans/02-enhancements-plan.md`.

---

## 1. What the assignment grades (keep in view at every step)

From `rc_curriculum_assignment.pdf` (RapidCanvas AI Engineer take-home):

| Priority | Criterion | Implication for this build |
|---|---|---|
| **#1** | **Evaluation** — "how you decided whether outputs are good... what your evaluation does NOT tell you" | Eval harness ships **in the MVP**, not later. EVALUATION.md is a first-class deliverable. Surface eval-vs-judgment disagreements and discarded signals. |
| #2 | **Output quality** — "Do inclusion reasons reference actual content, or just metadata?" | Curator sees chapters + subtitle text of finalists; reasons must quote/cite actual content. |
| #3 | **Code** — "readable, sensibly structured, not over-engineered" | Plain Python modules, no frameworks, no abstractions for hypothetical futures. |
| #4 | **Design decisions** — explainable choices | README documents each significant decision in a few sentences. |

Deliverables: runnable agent (one command after setup), `/test_set/` with ≥5 scenarios,
evaluation writeup, README with design decisions + "what I'd do with more time".
Submission: public GitHub repo, final commit tagged `v1-submission`.

Sketch of good output (for the reference persona): 4–6 ranked videos, ~5 hours total,
starts with React/Vite setup, then a project-build tutorial mirroring the habit-tracker
goal, skips JS intros (known) and "in 100 seconds" content (constraint), each video has a
short content-grounded reason; stronger outputs show considered-and-dropped candidates,
per-pick confidence, and why two similar videos didn't both make the cut. **Output format
is our decision** — we ship JSON + Markdown (§6).

## 2. Locked decisions (from planning Q&A with the author)

1. **Eval harness in MVP** — deterministic checks + LLM judge + report generator.
2. **Content depth**: search/triage on metadata only (cheap); the ~12–15 finalists get
   full extraction including subtitles, so curation reasons cite actual content.
3. **Data source: yt-dlp only.** No YouTube Data API key needed by graders.
4. **Tiered Claude models**: Haiku 4.5 (`claude-haiku-4-5`) for guard + triage;
   Sonnet 5 (`claude-sonnet-5`) for planning + curation + judge. Config-driven so the
   model-comparison bonus is cheap later.
5. **In MVP scope**: harmful-content guard, content-level dedup (bonus item, nearly free
   in the curation prompt), web search for recent concepts (via Anthropic's server-side
   `web_search` tool — same API key, no extra credential), cost/latency instrumentation.
6. **Full reasoning trace in output**: picks with confidence + content-grounded reasons,
   considered-but-dropped with drop reasons, dedup explanations, budget accounting.
7. **Search width**: 3–5 LLM-generated queries, ~10–15 flat results each (40–60 candidates
   after dedupe), triaged down to 12–15 finalists for deep fetch.
8. **CLI only.** No UI in either milestone (decision revised from the original mind map).

## 3. Architecture

One linear pipeline. No agent loop in the MVP (that's milestone 2); each stage is a plain
function so the flow is easy to read, test, and instrument.

```
persona.json
   │
   ▼
[0] validate ──► pydantic Persona model; defaults for optional fields
   │
   ▼
[1] guard (Haiku) ──► harmful goal? → emit refusal artifact, exit cleanly
   │
   ▼
[2] plan (Sonnet 5 + web_search tool) ──► TopicPlan:
   │      expertise assessment, ordered topics w/ time allocation,
   │      known-concepts removed, unknowns + inferred prereqs added,
   │      recent-concepts enrichment from web search, 3-5 search queries
   ▼
[3] search (yt-dlp flat, parallel, cached) ──► 40-60 CandidateVideo (light metadata)
   │
   ▼
[4] triage ──► hard filters in code (duration/live/shorts), then Haiku scores
   │            relevance + constraint fit from metadata → top 12-15 finalists
   ▼
[5] deep fetch (yt-dlp full, parallel, cached) ──► chapters, description,
   │            subtitles (compressed), engagement stats per finalist
   ▼
[6] curate (Sonnet 5, structured output) ──► Curriculum:
   │      4-6 ordered picks w/ watch instructions, content-cited reasons,
   │      confidence, dropped list w/ reasons, dedup calls, budget accounting
   │      → validated: only real candidate IDs, budget respected; 1 retry w/ feedback
   ▼
[7] render ──► outputs/<persona_id>/curriculum.json + curriculum.md + run_meta.json
```

### Repo layout

```
src/curriculum_agent/
  __init__.py
  cli.py            # argparse entrypoint: run | eval
  config.py         # models, pool sizes, token budgets, paths — every dial in one place
  schemas.py        # pydantic models for every stage boundary (the contracts)
  llm.py            # thin Anthropic client wrapper: parse() calls, retry, usage accounting
  guard.py          # stage 1
  planner.py        # stage 2 (topic plan + query generation, web_search tool)
  youtube.py        # stages 3+5: search, deep fetch, subtitle processing, disk cache
  triage.py         # stage 4
  curator.py        # stage 6 (+ output validation & retry)
  render.py         # stage 7 (markdown + json writers)
  prompts.py        # all prompt templates as module constants (reviewable in one file)
eval/
  run_eval.py       # runs pipeline over test_set/, then checks + judge, writes report
  checks.py         # deterministic checks
  judge.py          # LLM-judge rubric scoring
  results/          # per-run eval artifacts (gitignore raw, commit summary)
test_set/           # ≥7 persona JSONs + .expected.json property files
outputs/            # per-persona run artifacts (gitignored except one committed example)
plans/              # these documents
README.md
EVALUATION.md
pyproject.toml      # deps: anthropic, yt-dlp, pydantic, python-dotenv
.env.example        # ANTHROPIC_API_KEY=
```

One command after setup: `uv run curriculum run test_set/weekend_react_dev.json`
(and `uv run curriculum eval` for the harness). Wire via `[project.scripts]`.

## 4. Stage specifications

### Stage 0 — Input validation (`schemas.py`)

`Persona` pydantic model matching the assignment's reference JSON exactly:
`persona_id: str`, `goal: str`, `time_budget_minutes: int (>0)`,
`user_context: {background: str, known: list[str] = [], unknown: list[str] = [], constraints: str = ""}`.
Mandatory per the mind map: goal, background, time budget. Optional: known, unknown,
constraints — pipeline must run with all optionals absent. Reject nonsense early with a
clear CLI error (negative budget, empty goal).

### Stage 1 — Safety guard (`guard.py`, Haiku)

Single cheap call, structured output: `{safe: bool, category: str|null, reason: str}`.
Blocks goals seeking harm capability (weapons/explosives synthesis, malware for attack,
etc.); does NOT block dual-use educational topics (chemistry, security careers). On
unsafe: write `outputs/<id>/refusal.json` + a short human-readable md explaining the
refusal, exit code 0 (a refusal is a *correct output*, not a crash — the eval asserts it).

### Stage 2 — Learner profiling & topic planning (`planner.py`, Sonnet 5)

One call with the `web_search` server tool attached
(`{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}` — runs
server-side on the same API key). Prompt instructs: search only when the goal is
version/ecosystem-sensitive (e.g. "current recommended React tooling 2026"), otherwise
skip — keeps latency down on evergreen topics (cooking).

Structured output `TopicPlan`:
- `expertise_start`: the learner's starting level **in the goal domain**, derived from
  `background` + `known[]` + `unknown[]` (a 5-yr Python dev who doesn't know React is an
  *experienced engineer / domain beginner* — not a novice; this distinction drives both
  query style and video selection). Includes a one-line justification.
- `expertise_target_provisional`: what level is *plausibly reachable* within the time
  budget — explicitly a pre-search **estimate** (no video content exists yet); used only
  to calibrate queries, topic time allocation, and triage. The *grounded* verdict on the
  level actually reached is produced later by the curator (stage 6,
  `expertise_achieved`), once real video content is in hand — this matches the mind
  map, which places "level of expertise you'll achieve" inside the post-search filter
  algorithm, not the planner.
- `topics[]`: name, why-needed, est_minutes, ordered by prerequisite dependency.
  Known concepts excluded; unknowns included; missing prerequisites inferred from
  background (e.g. Python dev → needs JSX, not programming basics).
- `constraint_notes[]`: machine-usable interpretation of free-text constraints
  (e.g. "avoid 'in 100 seconds'" → exclude-title-pattern; "prefer project-based" →
  ranking preference). Downstream stages consume these instead of re-parsing prose.
- `search_queries[]` (3–5): targeted, constraint-aware
  (e.g. "react vite project tutorial build app", not "learn react").
- `edge_case`: if knowns ⊇ the goal's required concepts (mind map edge case
  "knowns >>> unknowns"), plan says so and pivots to advanced/deepening content, and the
  final report tells the user their budget likely exceeds what's needed.

> **Stages 3–5 validated by experiment before implementation**
> (`experiments/benchmark_youtube_fetch.py`, results in
> `experiments/benchmark_results.json`, live YouTube, 2026-07-18):
> - Flat search returns **all triage fields** (id, title, duration, channel, views) in
>   ~1s per query — triage needs nothing more.
> - A single full-metadata search costs **~1.06s per video, serially inside yt-dlp**
>   (~64s for a 60-candidate pool, not parallelizable within one search call). The
>   two-stage design (parallel flat queries + parallel deep-fetch of 14 finalists) does
>   the same job in **~5–8s** — ~10× faster. Two-stage confirmed.
> - Subtitle **text is not in the metadata** (URL listings only); the extra download is
>   cheap (~0.2s each) but raw transcripts run **0.9k–10.7k tokens/video**, scaling with
>   duration → the per-video compression budget is REQUIRED, not optional.
> - Chapters present on only 2/6–4/8 videos; manual subs on 1/8 (auto-captions 8/8) →
>   both fallbacks (transcript sampling, auto-captions) are load-bearing.

### Stage 3 — Search (`youtube.py`)

`ytsearchN:` with `extract_flat: True` (fast — one request per query, no per-video
fetch). 10–15 results/query, run queries in a `ThreadPoolExecutor`, dedupe by video id,
keep light fields: id, title, duration, channel, view_count, url.
**Disk cache** (`.cache/search/<sha1(query)>.json`): dev iteration and eval reruns don't
hammer YouTube; `--no-cache` flag to bypass. Tolerate per-query failure (log, continue)
— fail the run only if *all* queries return nothing.

### Stage 4 — Triage (`triage.py`)

Code-level hard filters first (free, deterministic): duration > remaining budget,
duration < 120s (shorts / "in 100 seconds"-style), live/upcoming, missing duration.
Then **one** Haiku call with the whole candidate table (id, title, duration, channel,
views) + TopicPlan: score each 0–10 for relevance/level-fit/constraint-fit with a
one-phrase reason. Keep top `FINALIST_COUNT = 14`. Store all scores — the dropped-at-triage
list feeds the final report's trace and milestone 2's follow-up Q&A.

### Stage 5 — Deep fetch (`youtube.py`)

Parallel full `extract_info` per finalist (cached per video id: `.cache/videos/<id>.json`).
Collect: description, chapters (start/end/title), tags, like/view counts, upload date,
channel subs, heatmap if present, subtitles.

**Subtitle handling** (the fiddly part — isolate in `subtitles.py`-style helpers inside
`youtube.py`):
- Prefer manual subs over auto-captions; language: constraint language if specified, else `en`.
- Fetch `json3` format; de-duplicate the rolling-repeat artifact of auto-captions
  (consecutive events repeat the previous line — keep only novel text).
- **Compression to a token budget** (~2,500 tokens/video, `config.py`): if the video has
  chapters, sample the first ~2 sentences of each chapter (aligned by timestamp) — this
  gives the curator "what is actually taught, when". No chapters → head + evenly spaced
  windows. Always record `transcript_coverage: full|sampled|none`.
- A video with no subtitles at all is still usable (chapters + description); mark it so
  the curator can weigh lower confidence.

Output per finalist: `VideoContent` bundle — the curator's raw material.

### Stage 6 — Curation (`curator.py`, Sonnet 5)

One structured-output call (`client.messages.parse`, pydantic `Curriculum`) with:
TopicPlan + persona + all 12–15 `VideoContent` bundles.

`Curriculum` schema:
```
picks[]:      video_id, order, title, url,
              watch: {mode: full|segments, segments?: [{start_s, end_s, chapter_title}], minutes}
              reason (MUST cite specific chapters/transcript moments by name/timestamp),
              covers_topics[], confidence: high|medium|low + confidence_why
dropped[]:    video_id, reason (incl. "overlaps with <pick> because <specific content>"
              for dedup calls — the bonus criterion)
budget:       total_minutes, budget_minutes, headroom_note
plan_gaps[]:  topics from TopicPlan not covered by any pick (honesty over padding)
expertise_achieved: {level, justification} — the GROUNDED verdict on what level the
              learner reaches by completing these specific picks: justified by what the
              selected videos' chapters/transcripts actually cover and what plan_gaps
              omit ("can build & persist a small React app; testing/deployment not
              covered"). If it falls short of the planner's provisional target, say so
              explicitly in the report.
summary:      2-3 sentence learner-facing overview
```

Prompt rules: **selection is expertise-conditioned** — use `expertise_start` as a hard
criterion: skip videos pitched below the learner's level (beginner intros re-teaching
`known[]` concepts) and above it (talks assuming mastery of `unknown[]` topics); prefer
videos whose stated prerequisites match what the learner already knows;
pick 4–6 (fewer only if budget forces it); order by prerequisite;
partial-watch via chapter segments is allowed and encouraged when only part of a long
video is relevant (mind map: len(videos) ≤ len(curriculum)); never exceed budget; two
videos covering the same material → keep the better one and say why in `dropped`;
reasons must reference content the bundle actually contains — no invented chapter names.

**Post-validation in code** (LLMs will occasionally violate all of these):
1. every `video_id` ∈ finalist set (kills hallucinated videos),
2. sum(minutes) ≤ budget × 1.05,
3. segments lie within video duration,
4. 1 ≤ picks ≤ 6.
On failure: one retry with the specific violation appended to the prompt; second failure
→ raise with a clear error (eval will catch it — do not silently ship a broken plan).

### Stage 7 — Render (`render.py`)

- `curriculum.json` — the validated `Curriculum` + persona + TopicPlan (full trace).
- `curriculum.md` — human-readable: summary, expertise trajectory (start level →
  grounded `expertise_achieved`, flagging any shortfall vs the planner's provisional
  target), ordered picks with
  links/durations/watch-segments/reasons/confidence, considered-but-dropped table,
  budget accounting, plan gaps.
- `run_meta.json` — per-stage wall-time, per-call model + input/output/cache tokens,
  computed cost (prices in `config.py`: Sonnet 5 $3/$15 per MTok, Haiku 4.5 $1/$5),
  cache hit counts, candidate-pool sizes. This is the cost/latency bonus, earned by
  instrumentation from day one.

### `llm.py` conventions

Zero-arg `anthropic.Anthropic()` client (reads `ANTHROPIC_API_KEY`). All calls:
`temperature` never set (Sonnet 5 rejects non-default sampling params), structured
outputs via `messages.parse(output_format=<PydanticModel>)`, one wrapper that logs
usage into a per-run accumulator, SDK's built-in retries + one schema-level retry hook.
Model names only ever referenced via `config.py`.

## 5. Evaluation harness (the #1 deliverable)

### 5.1 Test set (`test_set/`) — 7 personas + expectations

Each persona ships with `<name>.expected.json` declaring machine-checkable properties
(this is the "golden dataset" from the mind map, adapted: YouTube search is
non-deterministic, so we assert **properties**, never exact video IDs).

| Persona | Exercises | Key expectations |
|---|---|---|
| `weekend_react_dev` | the reference case (verbatim from PDF) | no "100 seconds"/short intros; project-based majority; no JS-fundamentals videos; ≤360 min |
| `french_cooking_novice` | non-tech domain, zero known concepts | topic coverage from goal; ≤ budget |
| `travel_blogger_expert_track` | vague/aspirational goal, long budget | plan decomposes goal into concrete skills |
| `explosives_blocked` | safety guard | `expect_refusal: true`, no curriculum emitted |
| `hindi_language_learner` | language constraint | picks' language/subs match constraint |
| `senior_dev_knows_it_all` | knowns ⊇ unknowns edge case | pipeline completes; report flags that goal is largely already met; advanced content only |
| `sixty_minute_crunch` | tight budget | ≤60 min total; segment-watching or few picks; honest `plan_gaps` |

(≥5 required; we ship 7. Graders will also run their own — nothing may be hardcoded to
these personas.)

### 5.2 Deterministic checks (`eval/checks.py`)

Run against `curriculum.json` + the run's candidate pool + expectations file:
- schema validity; picks ⊆ candidate pool (no hallucinated videos)
- budget: total ≤ budget × 1.05; segments within video bounds
- count 4–6 (unless budget-constrained, then ≥1 and flagged)
- **reason groundedness proxy**: each reason shares ≥1 non-trivial n-gram with that
  video's chapters/transcript/description (cheap fabrication detector)
- constraint checks from expectations (forbidden title patterns absent, refusal
  present/absent, language match)
- no duplicate videos; no two picks whose `covers_topics` are identical without a dedup
  note in `dropped`
- ordering sanity: prerequisite topics appear before dependents (from TopicPlan order)

Each check → `{name, pass, detail}`; the suite never throws on a failing check.

### 5.3 LLM judge (`eval/judge.py`, Sonnet 5)

Rubric-scored 1–5 with justification, structured output, fed the persona + TopicPlan +
curriculum + the finalists' content bundles (so it can verify claims against source):
`relevance_to_goal`, `level_fit` (picks match `expertise_start` — nothing re-teaching
knowns, nothing assuming unknowns), `ordering_logic`, `constraint_satisfaction`,
`reason_groundedness` (do reasons match what the video content actually contains?),
`selection_quality` (were the dropped candidates justifiably dropped?),
`expertise_claim_grounded` (is `expertise_achieved` supported by what the picked
videos' content covers, and consistent with `plan_gaps`? — an inflated claim scores low).
Judge model/prompt configurable — feeds milestone 2's model-comparison.

### 5.4 Report (`eval/run_eval.py`)

`uv run curriculum eval [--personas ...] [--skip-run]`: pipeline (cached) → checks →
judge → `eval/results/<timestamp>/` per-persona JSON + a summary markdown table
(persona × checks passed × judge scores × cost × latency) ready to embed in EVALUATION.md.

### 5.5 EVALUATION.md (hand-written, drafted alongside the code)

Must cover, explicitly: what we measure and why; results table from the harness; **what
the evaluation does NOT tell us** (e.g. checks can't tell a good video from a mediocre
one that satisfies all constraints; judge shares the curator's blind spots — same model
family; groundedness n-gram check is a proxy, defeatable by quoting irrelevant chapter
titles); **where eval and human judgment disagreed** during development (log these as
they happen — keep a `eval/disagreements.md` scratchpad from day one); **signals
considered and discarded** (e.g. like/view ratio — popularity ≠ pedagogical fit for a
specific learner; comment sentiment — cut from MVP for latency, see milestone 2).

## 6. Implementation considerations → resolutions

| # | Consideration | Resolution in this plan |
|---|---|---|
| 1 | Curator hallucinates video IDs/URLs | Curation restricted to provided candidate IDs; code validation + retry-with-feedback (stage 6); eval check |
| 2 | Search/LLM non-determinism breaks eval | Property-based expectations, not golden video IDs; disk caching makes reruns reproducible |
| 3 | Subtitle text blows the context window | Per-video token budget + chapter-aligned sampling; coverage flag (stage 5). 15 × 2.5k ≈ 38k input tokens — fine for Sonnet 5 |
| 4 | ~2/3 of videos lack creator chapters (mind map note) | yt-dlp's description-timestamp fallback already populates `chapters` for many; else transcript sampling covers it; missing both → curator told, lowers confidence |
| 5 | yt-dlp fragility / YouTube throttling | Retries with backoff, per-video timeout, graceful degradation (video without subs still usable), caching, parallel fetch capped at ~8 workers |
| 6 | Time budget impossible to fill exactly | Chapter-segment partial watching; honest `plan_gaps` + headroom note rather than padding |
| 7 | Harmful goals (own test case: explosives) | Stage-1 guard; refusal is a first-class, evaluated output |
| 8 | Knowns >>> unknowns edge case (mind map) | Planner detects, pivots to advanced content, report flags it; dedicated persona |
| 9 | Free-text constraints are ambiguous | Planner normalizes them into `constraint_notes` once; all downstream stages consume the structured form |
| 10 | Latency (graders run 10+ personas) | flat search first; deep fetch only finalists; parallel I/O; caching. Target: ≤ ~2 min cold, seconds warm per persona |
| 11 | Cost | Haiku for high-volume stages; one big Sonnet call for curation. Est. ~$0.10–0.25/run cold — measured, not guessed, via run_meta |
| 12 | API key cap (assignment warns) | Caching avoids repeat spend; `run_meta.json` tracks cumulative cost; small `MAX_*` dials in config |
| 13 | Over-engineering risk (explicit rubric item) | No classes where functions do; no plugin systems; prompts in one file; one linear pipeline |
| 14 | Language constraints | Planner puts language in queries + triage; deep fetch requests that subtitle language; eval checks it |
| 15 | Web search adds latency on evergreen topics | Prompt-gated: model told to search only for fast-moving ecosystems; `max_uses: 3` |

## 7. Build order (work packages for sub-agents)

Each WP is independently verifiable; WPs 2–4 can run in parallel after WP1.

- **WP1 — Skeleton & contracts**: repo layout, `config.py`, `schemas.py` (all pydantic
  models above), `llm.py`, CLI stub, `.env.example`, pyproject scripts/deps.
  ✓ `uv run curriculum run --help` works; schemas round-trip the reference persona.
- **WP2 — YouTube layer**: search, deep fetch, subtitle compression, caching (evolve the
  existing root `youtube.py` into `src/curriculum_agent/youtube.py`; delete the old one).
  ✓ live smoke test: query → ≥30 candidates; 3 known video ids → bundles with
  chapters/transcript under token budget; second call hits cache.
- **WP3 — Guard + Planner**: prompts, web_search tool wiring, structured outputs.
  ✓ explosives goal → refused; reference persona → plan excludes known JS topics,
  includes React/JSX/hooks, 3–5 sane queries, constraint_notes capture both constraints.
- **WP4 — Triage + Deep-fetch orchestration + Curator + Render**: end-to-end path.
  ✓ reference persona → curriculum.md matching the assignment's "good output" sketch;
  validation rejects a planted fake video id.
- **WP5 — Eval harness + test set**: 7 personas + expectations, checks, judge, report.
  ✓ `uv run curriculum eval` produces the summary table; explosives persona passes via
  refusal; at least one intentionally-broken fixture fails the right check.
- **WP6 — Docs & polish**: README (setup, one-command run, design decisions, what-I'd-do
  -with-more-time referencing milestone 2 plan), EVALUATION.md, commit one example
  output, tag readiness checklist.
  ✓ fresh-clone dry run following README verbatim succeeds.

## 8. Definition of done (MVP)

- [ ] `uv run curriculum run <persona.json>` works end-to-end on a fresh clone with only
      `ANTHROPIC_API_KEY` set
- [ ] Reference persona output matches the assignment's sketch (4–6 videos, ~budget,
      skips knowns + "100 seconds", content-grounded reasons, dropped-list, confidence)
- [ ] 7-persona test set + expectations committed
- [ ] `uv run curriculum eval` produces checks + judge + cost/latency report
- [ ] EVALUATION.md: measures, results, limits of the eval, disagreements, discarded signals
- [ ] README: setup, design decisions, "what I'd do with more time"
- [ ] run_meta cost/latency numbers quoted in README (bonus item)
- [ ] No hardcoding against test personas; graders' unseen personas will just work
