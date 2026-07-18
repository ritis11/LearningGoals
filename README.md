# Learning Curriculum Builder

An AI agent that takes a learning goal, a time budget, and a learner's context (what
they know, what they don't, their constraints) and produces a YouTube curriculum the
learner can follow to reach the goal within the budget — with content-grounded reasons
for every pick, a considered-but-dropped trace, and an honest assessment of the level
they'll actually reach.

Built for the RapidCanvas AI Engineer take-home (`rc_curriculum_assignment.pdf`).

## Setup & run (one command after setup)

```bash
# 1. install deps (needs uv: https://docs.astral.sh/uv/)
uv sync

# 2. API key (provided with the assignment)
cp .env.example .env   # then paste the key into .env

# 3. build a curriculum
uv run curriculum run test_set/weekend_react_dev.json
```

Artifacts land in `outputs/<persona_id>/`:
- `curriculum.md` — the human-readable plan (picks in order, watch segments, reasons,
  confidence, dropped candidates, expertise trajectory, honest gaps)
- `curriculum.json` — the same, machine-readable, with the full topic plan
- `candidates.json` — the complete search/triage trace (what was considered and why it lost)
- `run_meta.json` — per-stage latency, per-call token usage, computed cost

Run the evaluation harness (the most important deliverable — see `EVALUATION.md`):

```bash
uv run curriculum eval              # full: pipeline + checks + LLM judge over test_set/
uv run curriculum eval --no-judge   # deterministic checks only (no LLM cost)
```

No YouTube API key is needed — video data comes via yt-dlp. First runs are network-heavy;
reruns hit the disk cache in `.cache/` and cost seconds.

**Measured cost & latency** (reference persona, cold caches): ~1–2.5 min per curriculum;
**$0.03 on Gemini flash vs $0.32 on Claude (Haiku 4.5 + Sonnet 5)** for outputs that pass
the same checks. Per-stage numbers land in every run's `run_meta.json`.

The engine runs on either provider — `--provider anthropic|gemini` (or set
`CURRICULUM_PROVIDER` in `.env`); the default is Anthropic with the assignment key.

## How it works

```
persona.json → validate → guard (fast model: harmful-goal check + recency gate)
  → plan (smart model: expertise profiling, topic plan, constraint normalization,
          queries; conditional live web search for fast-moving topics)
  → search (yt-dlp flat, 3-5 queries in parallel, ~40-60 candidates)
  → triage (hard filters in code, then fast model scores metadata → ~14 finalists)
  → deep fetch (parallel: chapters, stats, subtitles compressed to a token budget)
  → curate (smart model: ordered picks, segment-level watch instructions,
            content-cited reasons, dedup, dropped-with-reasons, grounded expertise
            verdict; code-level validation + one retry)
  → render (md + json + full trace + cost/latency meta)
```

Fast/smart model per provider: Haiku 4.5 / Sonnet 5 on Anthropic, flash on Gemini —
see `config.py`.

## Design decisions

Each entry is a problem actually hit during the build and the architectural choice made
for it. The blow-by-blow (experiments, dead ends, incidents) is in `docs/BUILD_NOTES.md`.

**A linear pipeline, not an agent loop.** Curation could be a free-form agent with
tools; the MVP is instead eight deterministic stages with typed contracts between them.
Reason: a fixed pipeline is readable, debuggable, and — crucially — evaluable stage by
stage. The agentic version is a planned evolution (see below), attempted only now that
an eval exists to prove whether the added freedom actually buys quality.

**Two-stage video fetching, decided by measurement.** One search call *can* return full
metadata for every result, but it does per-video work serially (~64s for a 60-candidate
pool). Cheap flat search for breadth, full extraction only for the ~14 triaged
finalists, runs in ~5–8s. This was benchmarked before implementation
(`experiments/benchmark_youtube_fetch.py`), not assumed.

**Deep content only where it pays.** The rubric's core question is whether inclusion
reasons reference actual content. Transcripts are token-heavy (raw: up to ~10k tokens
per video), so triage sees only metadata, while finalists get chapters plus transcripts
compressed to a per-video budget. Eval enforces the payoff: a groundedness check and a
judge dimension punish reasons that don't reference real content.

**Everything external degrades; only search is fatal.** Mid-build, YouTube IP-blocked
caption downloads for a full day. The architecture treats transcripts, web-search
recency enrichment, and even individual video fetches as optional layers: their failure
lowers pick confidence (and says so in the output) instead of crashing the run. A
refused harmful goal is likewise a *correct output* with its own artifact, not an error.

**Model output is never trusted structurally.** LLMs occasionally hallucinate video
IDs, overrun time budgets, and emit truncated JSON. Every curation passes a code-level
validation gate (picks must exist in the real candidate pool, arithmetic is recomputed,
segment bounds checked) with one retry that quotes the violations, then fails loudly.

**Reasoning spend is a first-class budget.** Reasoning models spend "thinking" tokens
from the same budget as the answer — live runs had curricula silently truncated by the
model's own deliberation. Generation-heavy calls now run with bounded reasoning effort,
and the parse layer self-heals once before failing. Cost, latency, and tokens are
instrumented per stage from day one, which is how this (and a 10× slow enrichment step)
was caught.

**Provider-agnostic LLM layer.** One small interface, two backends: Anthropic (tiered —
cheap model for guard/triage, strong model for plan/curate/judge) and Gemini flash (raw
REST, no extra SDK). Motivations: the assignment key has a usage cap, a second provider
turns "model comparison" into a measured cross-provider result ($0.32 vs $0.03 per
curriculum, same checks passing), and the abstraction keeps every pipeline stage
provider-blind.

**Cache all immutable facts.** Search results, video metadata, and transcripts are
cached on disk. Consequences: eval reruns are reproducible and near-free, graders can
re-run the test set in seconds, and the system stops re-triggering the rate limits that
caused the caption block in the first place.

**Property-based evaluation, no golden outputs.** YouTube search is non-deterministic
over a live corpus, so expected-video-ID tests would rot in weeks. The test set asserts
properties instead — budget respected, constraints honored, no hallucinated picks,
refusal when required. What the eval *cannot* see is documented as carefully as what it
can (`EVALUATION.md` §4–5).

**Two-phase expertise assessment.** "What level will I reach?" can't be honestly
answered before knowing what the videos contain. The planner only *estimates* a target
to calibrate queries; the grounded verdict comes from the curator, which holds the
picked videos' actual content — and shortfalls against the estimate are reported, not
papered over.

## What I'd do with more time

The full prioritized plan is `plans/02-enhancements-plan.md`. First three, and why in
this order:

1. **Comparison harness** (content depth × model × prompt matrix over the test set).
   First because it multiplies the value of everything after it: it turns claims like
   "content grounding matters" into measured quality-vs-cost deltas, and every later
   feature gets accepted or rejected by this harness instead of by intuition.
2. **Agentic curator** — a bounded tool-use loop that can pull a finalist's *full*
   transcript, run one gap-filling search, and do explicit pairwise comparisons of
   overlapping videos. Second because it attacks the MVP's real quality ceiling (the
   curator can only rank what triage handed it), and because #1 must exist first to
   prove the extra cost buys anything.
3. **Follow-up Q&A** (`curriculum ask`) — the agent defends its choices from the
   persisted run trace, so "why didn't you include video X?" gets an answer grounded
   in recorded drop reasons rather than a retcon. Third because the trace it needs is
   already persisted by the MVP; it's high user value at low marginal cost.

Beyond those: community-sourced discovery (Reddit — popularity ranks what's popular,
communities rank what people actually learned from), SponsorBlock-aware time budgets,
and a 10K-users/day cost projection built from accumulated `run_meta` data.

## Repo map

```
src/curriculum_agent/   the agent (pipeline.py orchestrates; prompts.py has every prompt)
eval/                   checks.py (deterministic), judge.py (LLM), run_eval.py (report)
test_set/               7 personas + .expected.json property files
experiments/            pre-implementation benchmarks + smoke tests (kept as evidence)
plans/                  MVP + enhancements plans
docs/BUILD_NOTES.md     the build journal: decisions, experiments, dead ends
```
