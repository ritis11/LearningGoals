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

No YouTube API key is needed — video data comes via yt-dlp. First runs are network-heavy
(~1–2 min/persona); reruns hit the disk cache in `.cache/` and cost seconds.

## How it works

```
persona.json → validate → guard (Haiku: harmful-goal check + recency gate)
  → plan (Sonnet: expertise profiling, topic plan, constraint normalization, queries;
          conditional live web search for fast-moving topics)
  → search (yt-dlp flat, 3-5 queries in parallel, ~40-60 candidates)
  → triage (hard filters in code, then Haiku scores metadata → ~14 finalists)
  → deep fetch (parallel: chapters, stats, subtitles compressed to a token budget)
  → curate (Sonnet: 4-6 picks, segment-level watch instructions, content-cited
            reasons, dedup, dropped-with-reasons, grounded expertise verdict;
            code-level validation + one retry)
  → render (md + json + full trace + cost/latency meta)
```

Design decisions and the experiments behind them are journaled in
`docs/BUILD_NOTES.md`; the milestone plans are in `plans/`.

### Key design decisions (short version)

- **Two-stage fetch, measured not assumed**: a single full-metadata search costs
  ~1.06s/video *serially* (~64s for a 60-candidate pool); flat search + parallel deep
  fetch of finalists does it in ~5–8s. Benchmarked before building
  (`experiments/benchmark_youtube_fetch.py`).
- **Content-grounded reasons**: finalists' chapters + compressed transcripts go to the
  curator, and an eval check + judge dimension punish reasons that don't reference
  actual content — the rubric explicitly penalizes metadata-only reasoning.
- **Two-phase expertise assessment**: the planner only *estimates* what's reachable
  (pre-search); the grounded "level you'll reach" verdict comes from the curator, which
  has the picked videos' content in hand, and shortfalls are reported honestly.
- **Tiered models**: Haiku 4.5 for guard/triage (cheap, high-volume), Sonnet 5 for
  plan/curate/judge (reasoning-heavy). All dials in `config.py`.
- **Refusals are outputs, not errors**: a harmful goal (e.g. the explosives test
  persona) produces an evaluated `refusal.json`, exit code 0.
- **Eval ships with the engine**: 7 personas with property-based expectations (search
  is non-deterministic, so we assert properties, never exact video IDs), deterministic
  checks + an LLM judge. See `EVALUATION.md`.

## What I'd do with more time

The full prioritized plan is `plans/02-enhancements-plan.md`. First three, and why:

1. **Comparison harness** (depth × model × prompt): turns "content grounding matters"
   into a measured quality-vs-cost delta — the strongest possible evaluation story.
2. **Agentic curator**: a bounded tool-use loop that can pull full transcripts, run one
   gap-filling search, and do explicit pairwise comparisons of overlapping videos.
3. **Follow-up Q&A** (`curriculum ask`): the agent defends its choices from the
   persisted trace — "why didn't you include video X?" gets a grounded answer.

## Repo map

```
src/curriculum_agent/   the agent (pipeline.py orchestrates; prompts.py has every prompt)
eval/                   checks.py (deterministic), judge.py (LLM), run_eval.py (report)
test_set/               7 personas + .expected.json property files
experiments/            pre-implementation benchmarks + smoke tests (kept as evidence)
plans/                  MVP + enhancements plans
docs/BUILD_NOTES.md     the build journal: decisions, experiments, dead ends
```
