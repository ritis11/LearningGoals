# Build Notes — the story behind the Learning Curriculum Builder

> Running journal of decisions, experiments, and dead ends, kept *while building*.
> This is source material for the final README ("design decisions") and EVALUATION.md
> ("signals considered and discarded", "where eval and judgment disagreed").
> Append entries as they happen; don't retrofit.

---

## 2026-07-18 — Design phase

### Started from a mind map, not code
Sketched the whole system in Excalidraw (`systemdiag.excalidraw`) before writing
anything: inputs (mandatory: goal/background/time-budget; optional: known/unknown/
constraints), an LLM planning step, YouTube search features inventory, a filter
algorithm, and a set of eval ideas (green boxes) + future enhancements (red boxes).
The mind map became the contract for what's MVP vs. milestone 2
(`plans/01-mvp-plan.md`, `plans/02-enhancements-plan.md`).

### Decisions locked before implementation (and why)
- **Eval ships in the MVP.** The assignment grades Evaluation as the #1 deliverable;
  building it after the engine would make it an afterthought.
- **Content depth**: metadata-only triage, but finalists get chapters + subtitles so
  inclusion reasons can cite actual content — the rubric explicitly penalizes
  metadata-only reasoning.
- **yt-dlp over YouTube Data API**: graders shouldn't need to provision a Google API
  key; yt-dlp also exposes chapters/heatmap/subtitle listings the official API doesn't.
- **Tiered models**: Haiku 4.5 for high-volume/cheap steps (guard, triage), Sonnet 5
  for reasoning-heavy steps (plan, curate, judge). Config-driven → model comparison
  bonus becomes a config sweep.
- **Web search for recent concepts** via Anthropic's server-side `web_search` tool —
  runs on the same API key, so no extra credential for graders.
- **No web UI** — reversed the mind map's UI plans; effort goes to reasoning + eval.

### Expertise assessment: caught a design flaw during plan review
First draft asked the *planner* to declare "expertise you'll reach" before any search —
an ungroundable claim (no video content exists at that point). Fixed as a two-phase
assessment: planner emits a *provisional* target (calibrates queries + time allocation);
the *curator*, which holds the picked videos' chapters/transcripts, emits the grounded
`expertise_achieved` with justification, and the report flags shortfalls vs. the
provisional target. Matches the mind map, which put this determination inside the
post-search filter algorithm. Added an `expertise_claim_grounded` judge dimension so an
inflated claim costs eval points.

### Experiment 1: is the two-stage fetch pipeline actually needed?
Question: flat search + deep-fetch-finalists-only vs. one full-metadata search that
returns everything (chapters included). Wrote `experiments/benchmark_youtube_fetch.py`
(results: `experiments/benchmark_results.json`) before implementing. Findings:
- Flat search: ~1s per query and carries **every field triage needs** (id, title,
  duration, channel, views).
- Full-metadata search: ~1.06s **per video, serial inside yt-dlp** → ~64s for a
  60-candidate pool; not parallelizable within one search call.
- Two-stage (parallel flat queries + parallel deep fetch of 14 finalists): **~5–8s**
  total. ~10× faster. Two-stage confirmed by measurement, not assumption.
- Subtitles are **not in metadata** (URL listings only). The text download is cheap
  (~0.2s) — the real cost is tokens: raw transcripts ran 0.9k–10.7k tokens/video,
  scaling with duration → per-video compression budget is required, not optional.
- Only 2/6–4/8 videos had creator chapters; 1/8 had manual subs (auto-captions 8/8) →
  transcript-sampling and auto-caption fallbacks are load-bearing, exactly as the mind
  map's "YouTube only officially exposes chapters if..." note predicted.
- Caveat for EVALUATION.md: single query, popular tech topic; niche topics may have
  sparser captions. The latency asymmetry is structural, so the architecture holds.

## 2026-07-18 — MVP implementation begins

- Environment note: no ANTHROPIC_API_KEY available during the build session; YouTube
  layer tested live (keyless), LLM stages built against the SDK's structured-output
  (`messages.parse`) contract with the end-to-end run gated on the key.
- Planner/web-search decomposition decision: instead of attaching the `web_search`
  server tool to the structured-output planning call (server tools can pause turns,
  `parse()` doesn't resume them), recency enrichment is a separate, *conditional* plain
  call — the guard call (already happening, Haiku) additionally returns
  `needs_recency_check`; only fast-moving topics pay the search latency. Simpler calls,
  fewer failure modes, same signal.

### MVP built (same day)
- Structure: linear 8-stage pipeline (`pipeline.py`), all prompts in one reviewable
  file (`prompts.py`), every dial in `config.py`, pydantic contracts at each boundary
  (`schemas.py`). Deliberately no classes/frameworks — the assignment reads the code.
- The YouTube layer was built by a sub-agent against the schema contracts and
  live-smoke-tested independently (35 candidates in 1.5s cold; bundles within token
  budget; cache: warm rerun 1.3s; a transcript 429 degraded gracefully to
  coverage="none" — exactly the tolerated-partial-failure path).
- Curator output is never trusted raw: code validates pick IDs against the real
  candidate pool, budget arithmetic, and segment bounds, then retries once with the
  specific violations quoted. Budget numbers in the report are recomputed in code
  (don't trust model arithmetic).
- Offline integration smoke (`experiments/smoke_pipeline_offline.py`, no API key):
  all 7 personas validate; search→filter→fetch→bundle on live YouTube; curator
  validation catches planted fake-ID and budget-blowout curricula; render + all eval
  checks pass on a synthetic run; refusal path artifacts check out.
- Pruned video cache: raw yt-dlp info dicts are megabytes; pruning to the 16 needed
  keys keeps the whole cache at ~52KB for 3 searches + 4 videos.
- anthropic SDK pinned >=0.116 (0.120 not published yet); `messages.parse` confirmed
  present.
- **Not yet done (needs the assignment API key in `.env`)**: first live end-to-end run,
  the real eval numbers for EVALUATION.md §3, and prompt tuning based on those outputs.

### First live run: two failures, three fixes (same day)
The first keyed end-to-end run (`weekend_react_dev`) surfaced exactly the class of
issues the eval harness exists for:

1. **YouTube `timedtext` IP block.** All 14 finalist transcript downloads returned 429.
   Diagnosis ruled out our burst as the sole cause: a *never-before-requested* video's
   fresh URL also 429'd, on multiple yt-dlp player clients, and `youtube-transcript-api`
   (different negotiation path) reported `IpBlocked` — an IP-level caption block,
   sticky for ~an hour, likely triggered by the day's accumulated experiments.
   **Response** (since no client-side trick dodges an IP block): (a) pace transcript
   downloads (1.5s spacing) with 429 backoff so we stop *triggering* blocks; (b) a
   circuit breaker — 3 consecutive exhausted-retry failures stop transcript attempts
   for the run (bundles still carry chapters + descriptions; curator confidence
   downgrades per prompt); (c) transcripts cached permanently on success, so recovery
   is a one-time cost per video; (d) stale signed URLs (expire ~6h) refresh metadata
   once on 403/404. The pipeline now *completes* through a full caption outage —
   graceful degradation over hard dependency. Logged in EVALUATION.md as a known limit:
   metadata-cached runs during a block produce chapter/description-grounded reasons
   rather than transcript-grounded ones.
2. **Curator crash: `parsed_output=None`.** Sonnet 5's adaptive thinking spends from
   the same `max_tokens` budget as the output JSON; at 8192 the curriculum JSON got
   truncated (`stop_reason=max_tokens`) and the SDK returns None rather than raising.
   Fixes: curate calls now get 16000 tokens; `llm.parse` self-heals once at the
   non-streaming ceiling and otherwise raises with the stop_reason instead of letting
   None propagate to a confusing AttributeError.
3. **Recency step took 223s** — an enrichment step costing 60% of total wall time.
   Fix: `output_config={"effort": "low"}` on the web-search call (it's a bullet-point
   research task, not quality-critical reasoning). Kept the guard-gated conditionality.

Meta-lesson for the README: stage-level timing in `run_meta` made the recency problem
visible instantly, and validation-before-render turned a would-be-silent truncation
into a stack trace. Instrumentation paid for itself on run one.

### Provider abstraction: Gemini added alongside Anthropic
Motivations: (a) the assignment's Claude key has a usage cap — dev/eval iteration
shouldn't burn it; (b) a second provider makes the "model comparison" bonus a real
cross-provider comparison, not just Haiku-vs-Sonnet; (c) it forces the LLM interface
to be honest (one `parse()` + one `text_with_web_search()` contract, two backends).

Implementation kept deliberately thin (`src/curriculum_agent/llm.py`): `AnthropicLLM`
(messages.parse + server-side web_search) and `GeminiLLM` (raw REST `generateContent`
via requests — no new SDK dependency; structured outputs via `responseJsonSchema` with
a schema-in-prompt fallback for 400s; `google_search` grounding for the recency step;
`effort` mapped to `thinkingConfig.thinkingBudget`: low→0, medium→2048, high→dynamic).
Stage modules now take the models from the LLM instance (`llm.model_fast/model_smart`)
instead of importing config constants — stages are provider-blind. Selected per run:
`--provider anthropic|gemini` (default from `CURRICULUM_PROVIDER` env). Cost accounting
covers both (flash at $0.30/$2.50 per MTok; grounding at ~$0.035/query).

Also this round, from the second live failure: truncation on Anthropic manifests two
ways (parsed_output=None *or* a raised ValidationError on cut-off JSON) — the parse
self-heal ladder now catches both, retrying once at the 16k ceiling with effort stepped
down; curate and judge calls run at effort=medium after default-effort thinking ate
>14k tokens twice.

### First green end-to-end runs — one per provider
- **Anthropic** (weekend_react_dev): completed in ~160s, $0.32. The recency fix worked
  (223s → 21s with effort=low). Curate at effort=medium: 78s, valid on first attempt.
- **Config bug found by the provider switch**: `config.py` read `CURRICULUM_PROVIDER`
  at import time, but `.env` loading lived in `llm.py`, which imports *after* config —
  so the env default silently stayed "anthropic". Moved `load_dotenv()` into config.
  Lesson: env reads belong next to env loading.
- **Gemini flash** (same persona): completed in ~133s, **$0.03 — ~10× cheaper**.
  Structured outputs via `responseJsonSchema` worked first try. The `google_search`
  grounding call hit free-tier quota (RESOURCE_EXHAUSTED) and the pipeline degraded
  gracefully (recency is optional by design). Added 429/503 retry honoring Google's
  `retryDelay` for the eval sweep.
- **Output quality note (both providers)**: the curriculum picked 3 videos / 160 min
  of a 360-min budget, justifying the headroom as "time to code along" — sensible for
  a project-based learner, but the assignment's sketch says 4–6 videos ≈ 5h. Logged as
  an eval-vs-judgment disagreement candidate; may warrant a prompt nudge ("prefer
  filling 60–90% of budget unless the goal implies hands-on time").
- YouTube caption IP block STILL active hours later: all 14 finalists had
  coverage="none"; reasons grounded via chapters instead — the degradation path works,
  but transcript-grounded curation remains unverified live. Transcripts will self-heal
  into the cache once the block lifts.

### First eval sweep: 5/7 validated, quota wall on the rest
Gemini free tier turned out to cap at **20 requests/day** — enough for 4 personas +
judging before 429s took over (retry-with-retryDelay couldn't save a *daily* cap).
Results where it ran: all deterministic checks pass (42/42 across 5 personas incl. a
checks-only pass over the existing weekend_react_dev artifacts), judge 4.86–5.0.
Edge cases verified by inspection, not just scores: refusal artifact for the explosives
persona; `goal_already_met=True` + advanced-content pivot for the senior dev; genuinely
Hindi-language picks for the language-constraint persona. Two findings promoted to
EVALUATION.md §5: the 3-picks-vs-sketch budget philosophy, and judge scores being
conditional on bundle completeness (whole sweep ran chapters-only — caption block).
Remaining: sixty_minute_crunch + travel_blogger full runs, weekend_react_dev judge —
blocked on quota reset / paid tier / provider switch (user's call: testing is pinned
to the Gemini key).

## 2026-07-19 — Web UI, chapters-first pivot, engagement floor

### The pipeline grew a face: FastAPI + one static page
Persona JSON was the right *engine* contract but a bad human interface. Added
`curriculum serve`: a small FastAPI service (`server.py`) + a single hand-written
`static/index.html` (vanilla JS, no build step, no CDN). The persona became a real API:
`POST /api/curriculum` → `{run_id}`, `GET /api/runs/{id}` polled every 3s. The
pipeline gained a 5-line `on_stage` callback so the browser shows live progress
("triaging candidates…"). The mind map's "auto-populate unknown concepts" UI idea
shipped as `POST /api/suggest` — one fast-model call, button-triggered only (quota).
Deliberately rejected: React/node toolchain (nothing here needs it), websockets
(polling is fine at this latency), a DB (in-memory jobs + disk artifacts).
Verified live through the API: suggest returned sensible transferable-knowns +
concrete unknowns; a full reference-persona run finished in 52s / $0.10 on warm
caches with stage progression streaming.

### Chapters-first: accepting what operations kept telling us
Every live day hit the same wall: YouTube's caption endpoint rate-limits per-IP so
hard that transcript-first fetching stalls runs and produces nothing — while chapters,
descriptions, and stats arrive reliably in the same metadata fetch, and every eval
check + judge score passed on chapter-grounded curation. Decision: flip the default —
`FETCH_TRANSCRIPTS = False`; transcript text is opt-in (`--transcripts` / API field),
still paced/breakered/cached/refresh-on-expiry when on, and cached transcripts are
always used for free. Curator confidence rules updated: a specific chapter list now
supports high confidence on its own. (Also re-reviewed the root `test_youtube.py`
single-full-search approach: it doesn't fix subtitles — the text is a separate
rate-limited download regardless — and the pre-build benchmark had it ~10× slower per
candidate pool. Verdict unchanged; nothing adopted.)

### Engagement: discarded as a ranker, adopted as a floor
"Use likes/views for quality" was originally discarded (popularity ≠ fit). The
resolution that survived scrutiny: it's a *negative* signal worth automating, not a
positive one. `like_ratio` (likes÷views) is now computed into every bundle; prompts
tell triage/curator it's a floor + tiebreak, never the ranking; and the eval gained a
deterministic `engagement_floor` check (<1k views or <0.5% like-ratio flags a pick)
plus median-views / mean-like-ratio columns in the summary table. Thresholds set low
on purpose so niche/non-English picks that fit a constrained learner are never
punished for not being viral. First measured numbers (reference persona artifacts):
12/12 checks, median 128,591 views, mean like-ratio 2.3% — zero LLM cost to evaluate.

### Eval hardening round: testing the tests, and unseen-persona readiness
Re-read the assignment's eval bar ("we're evaluating how you think about evaluation";
graders run *their own* personas) and closed the gaps in priority order:
1. **Self-test** (`eval --selftest`): seven seeded faults, each must be caught by its
   check — the eval now proves its own alarms ring. All 7 caught on first run.
2. **Persona-agnostic constraints**: forbidden-pattern checking used to live only in
   our hand-written `.expected.json` files — invisible on graders' unseen personas.
   Now the eval reads the planner's `constraint_notes` out of each run artifact and
   verifies them directly. The check chain became: learner free text → normalized by
   the planner → enforced by the curator → *verified by the eval* — one contract.
3. **Coverage consistency**: measured topic coverage (fuzzy word-overlap matching) and
   a contradiction check on the curator's `plan_gaps` honesty; coverage % is now a
   report column (first measurement: 100% on the reference persona, 14/14 checks).
4. **Flagged probes** for when quota allows: `--judge-provider` (cross-family judging
   kills the judge-shares-curator-blind-spots caveat), `curriculum stability` (variance
   measured, not confessed), and a human-labels agreement table (verdicts recorded
   before seeing judge scores). All mechanisms landed; numbers pending the final sweep.
The shape of this round is the story the assignment wants: the eval got *deeper*, not
fancier — zero new dashboards, three zero-token checks, and every prior limitation in
§4 now has either a mitigation or a measurement.

### Conclusion: final sweep, one last real catch, and the cut list
Final full sweep (all 7 personas, gemini flash): 6/7 clean with judge 4.86–5.0 and
100% measured coverage everywhere; self-test 7/7. The one failure was the point of the
whole exercise: `coverage_gaps_consistent` caught the curator declaring
"Short-Form Video Setup" a gap while a pick claimed to cover it — a contradiction the
4.86-scoring LLM judge waved through. Deterministic checks under LLM judging, vindicated
on the last day (EVALUATION.md §5.3).

Cut for time, moved to README's more-time section: the human-label calibration pass
(prototype removed — §5's manual spot-reads are the surviving version of the idea), and
four product-layer items (cloud DB for saved programs, progress tracking, per-module
quizzes, personal-vs-general feedback). Cross-provider judging shipped as a flag but
the final sweep judged same-family (only a Gemini key had quota) — recorded in §2 as
a limitation that stands rather than one mitigated.

Final deliverable state: README (setup, 10 design decisions, prioritized more-time
list), EVALUATION.md (checks + meta-eval + results + limits + disagreements +
discarded signals + experiments appendix), this journal as the raw trail.

<!-- append new entries below as the build progresses -->
