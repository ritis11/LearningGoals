# Enhancements Plan (Milestone 2) — Learning Curriculum Builder

> Builds strictly on top of the MVP (`plans/01-mvp-plan.md`). Everything here assumes the
> MVP pipeline, schemas, eval harness, and test set exist and pass. Milestone 2 deepens
> agent reasoning, adds the follow-up Q&A and comparison bonuses, widens discovery, and
> hardens the evaluation story. **No web UI** (decision: CLI-only); the mind map's UI/UX
> ideas are realized as an interactive CLI wizard (E6).
>
> Ordering below is priority order — it doubles as the README's "what I'd do with more
> time" narrative, where the assignment asks us to explain why each extension comes first.

---

## Priority rationale (one paragraph per tier)

**Tier A (E1–E3)** directly moves the two heaviest rubric items: E1 deepens the
evaluation deliverable (model/prompt/depth comparison — an explicit bonus), E2 makes the
agent's reasoning genuinely agentic across video choices (output quality), E3 is the
follow-up Q&A bonus which also proves the reasoning trace is real. **Tier B (E4–E6)**
widens input quality: more discovery sources and better learner input produce better
curricula. **Tier C (E7–E9)** is completeness: learning reinforcement, richer signals,
and the 10K-users/day cost story.

---

## Tier A — reasoning depth & evaluation depth

### E1 — Comparison harness: depth modes × models × prompts (bonus: "model or prompt comparison")

**What.** Make the MVP's config dials into an eval matrix.
- `--depth metadata | chapters | transcript` flag on the pipeline: `metadata` curates
  from titles/descriptions/stats only; `chapters` adds chapter lists; `transcript` is the
  MVP default (full bundles). This is the mind map's "metadata-and-chapters-only vs also
  considering content" choice, made runtime-selectable.
- `eval/compare.py`: runs the test set across a configured matrix
  ({depth} × {curator: haiku, sonnet} × {prompt: v1, v2}), reuses the MVP judge, emits a
  delta table (judge scores, check pass-rates, cost, latency per cell).

**Why first.** Evaluation is the #1 graded deliverable; this turns EVALUATION.md from
"here are my scores" into "here is what content-grounding is *worth* — quality delta vs
cost delta" — exactly the kind of evaluation thinking the assignment rewards.

**Build notes.** Depth mode lives in `config.py` + a parameter to stage 5/6 (bundle
builder filters what it includes). Prompt variants live in `prompts.py` as
`CURATOR_PROMPT_V1/V2` (v2 candidate: adversarial "argue against each pick before
confirming"). Matrix runs use the MVP caches, so marginal cost is LLM-only.
✓ Done when: `uv run curriculum compare` produces the delta table and EVALUATION.md
gains a comparison section with 2–3 concrete findings.

### E2 — Agentic curator (mind map: "agent reasoning across video choices")

**What.** Replace the single-shot curation call with a bounded tool-use loop
(Anthropic tool runner, Sonnet 5) where the curator can:
- `get_video_content(video_id, part)` — pull *full* (uncompressed) transcript sections
  or all chapters for a candidate it's seriously considering,
- `search_more(query, n)` — one extra targeted search if it detects a coverage gap
  (`plan_gaps` would be non-empty), returning triaged light candidates,
- `compare_candidates(id_a, id_b)` — structured side-by-side of two overlapping videos
  (drives explicit dedup decisions),
- `finalize(curriculum)` — strict-schema terminal tool; the loop ends only through it.

Hard bounds in code: ≤ 8 tool calls, ≤ 1 extra search, token ceiling per run; on breach,
force-finalize with what it has. MVP post-validation (real IDs, budget) unchanged.

**Why.** The MVP curator can only rank what triage handed it and can't inspect deeper
when two videos look similar. The loop makes "why didn't both make the cut" decisions
observable (tool trace saved to the run artifact) and closes coverage gaps — better
output quality, and the trace feeds E3.

✓ Done when: on the reference persona the trace shows ≥1 comparison or content pull;
judge `selection_quality` does not regress vs MVP on the full test set; cost increase
measured and reported (E1 harness).

### E3 — Follow-up Q&A (bonus: "the agent retains and defends its choices")

**What.** `uv run curriculum ask <persona_id>`: interactive chat over a completed run.
Context = persona + TopicPlan + full candidate pool with triage scores + finalist bundles
+ curriculum + drop reasons + (from E2) the tool trace. Multi-turn loop with Sonnet 5.
Behavior contract: "why didn't you include video X?" → if X was a candidate, cite its
recorded drop reason and the content evidence; if X was never surfaced by search, say so
honestly (and optionally fetch its metadata live via yt-dlp to give a substantive
answer); never retcon — answers must be grounded in the persisted trace.

**Build notes.** MVP already persists everything needed in `curriculum.json` +
`run_meta.json`; add `candidates.json` (triage table) to the run artifact if not already
saved. Session transcript appended to the run directory.
✓ Done when: scripted Q&A fixture (3 questions incl. one about a never-seen video)
produces grounded, non-fabricated answers — add an eval check that answers quote trace
fields.

---

## Tier B — better inputs

### E4 — Extra discovery sources (bonus: "use a source beyond YouTube; explain why it helps")

**What.** Two additions to stage 3:
1. **Reddit mining**: query Reddit's public JSON search (`reddit.com/search.json`, no
   key) or the `web_search` tool with `allowed_domains: ["reddit.com"]` for
   "<topic> best video/course reddit"; extract YouTube links + upvote counts from
   threads; merge into the candidate pool tagged `source: reddit(<subreddit>, <score>)`.
2. **General web sweep** (already have the tool): "best <topic> tutorial <year>" →
   surface recommended course/creator names → feed as *additional search queries*, not
   direct candidates.

**Why it helps (for the README):** search ranks by popularity; communities rank by
having actually learned from the material. Community provenance is a quality signal
orthogonal to view count — exactly the "signals scattered across... communities" the
assignment's problem statement names.

✓ Done when: reference persona's pool contains ≥1 community-sourced candidate;
provenance shown in the dropped/picked trace; EVALUATION.md notes whether community
candidates won picks more often than search-ranked ones.

### E5 — Richer video signals: SponsorBlock, heatmap, comments

**What.**
- **SponsorBlock** (free public API, no key): fetch sponsor/intro/outro/filler segments
  per finalist; subtract from effective watch minutes (budget math uses *content*
  minutes); optionally emit skip-ranges in watch instructions.
- **Heatmap** (already in yt-dlp when present): pass most-replayed peaks to the curator
  as "key moments" — corroborates which sections matter.
- **Top comments** (yt-dlp `getcomments`, top-N by likes, finalists only): a
  quality/freshness signal ("outdated as of v19" comments are gold). Feed 5 comments ×
  finalist into the curation bundle; graceful skip on failure/latency budget.

**Why.** All three are content-adjacent signals the mind map already cataloged; they
sharpen both selection and the honesty of time accounting.
✓ Done when: budget accounting reports content-minutes vs raw-minutes; at least one
eval persona shows a comment- or heatmap-influenced reason; added latency measured.

### E6 — Interactive persona wizard (mind map's UI ideas, as CLI)

**What.** `uv run curriculum new`: prompts for goal/background/budget; then (mind map:
"auto-populate unknown concepts for users to edit", "on-the-fly suggestions scoped to
background") one Haiku call proposes known/unknown concept lists scoped to goal +
background, user edits inline (comma-separated accept/remove), constraints free-text;
writes a valid persona JSON and offers to run it.

**Why.** The persona JSON is the product's real UX surface in a CLI world; garbage-in
protection improves every downstream stage, and it demos well.
✓ Done when: wizard produces a schema-valid persona from a 60-second interaction and
suggested unknowns for "build a habit tracker in React" include hooks/JSX-tier items,
not "programming basics".

---

## Tier C — completeness & scale story

### E7 — Learning reinforcement & feedback loop (mind map red boxes)

- **Per-video quiz**: 3–5 questions generated from each pick's transcript (answers +
  timestamp pointers), appended to `curriculum.md` — the mind map's "questionnaire to
  test the learning levels after each video".
- **Feedback intake**: `uv run curriculum feedback <persona_id> "<free text>"` → stored;
  a lightweight prompt-note file (`prompt_tuning.md`) that the curator prompt includes —
  the mind map's "accept user's feedback to improve the curriculum maker prompt".
  Kept deliberately simple: notes-in-prompt, not fine-tuning.
✓ Quiz questions answerable *only* from the video content (spot-check via judge);
feedback demonstrably alters a rerun (fixture test).

### E8 — "Beyond the curriculum" section (mind map red box under filter)

Optional planner extension (one extra structured field, rendered as a final md section):
rough time-to-expertise estimate for level X (mind map), parallel topics worth learning
alongside, leaders/voices to follow, recent innovations (via `web_search`). Clearly
labeled as guidance, excluded from budget math and from eval checks (it's advisory).
✓ Present for reference persona; adds ≤1 web search + ~500 output tokens.

### E9 — Cost/latency analysis at scale (bonus: "project 10K users/day")

**What.** EVALUATION.md (or COSTS.md) section built from accumulated `run_meta.json`
data: measured per-curriculum cost & latency distribution → projection at 10K/day →
where to optimize, with estimated savings for each lever:
prompt caching for the static system prompts (cache reads ~0.1×), Haiku-ization of the
planner for evergreen topics, Batch API (50% off) for any non-interactive eval/refresh
workloads, shared candidate-pool cache across users with similar goals, cutting finalist
count from 14 → 10.
✓ Done when: numbers come from ≥20 real runs, each optimization lever has a projected
$/day delta, and one lever (prompt caching on the curator system prompt) is actually
implemented and its measured saving reported.

---

## Explicitly deferred / dropped (state in README)

- **Web UI** (mind map: search bar, dropdowns) — dropped by decision; wizard (E6) covers
  the input-assist ideas. Revisit only if the take-home feedback asks for it.
- **Audio→transcript (Whisper) for subtitle-less videos** — cost/latency outweighs
  benefit while auto-captions cover ~everything; noted as a future fallback.
- **Periodic eval job / cron** (mind map green box) — meaningless for a take-home
  submission; mention as the production-ization step in the scale story (E9).
- **Fine-tuning on feedback** — E7's notes-in-prompt is the right size for this project.

## Sequencing & effort sketch

| Order | Item | Est. effort | Depends on |
|---|---|---|---|
| 1 | E1 comparison harness | S–M | MVP eval |
| 2 | E2 agentic curator | M–L | MVP curator, E1 (to measure it) |
| 3 | E3 follow-up Q&A | S–M | run artifacts (MVP), E2 trace (optional) |
| 4 | E4 discovery sources | M | MVP search/triage |
| 5 | E5 richer signals | M | MVP deep fetch |
| 6 | E6 persona wizard | S | schemas |
| 7 | E7 quiz + feedback | S–M | MVP render/curator |
| 8 | E8 beyond-curriculum | S | planner |
| 9 | E9 scale analysis | S | accumulated run_meta from all of the above |

Regression gate for every item: the MVP test set + eval must still pass, and E1's
comparison table is rerun so quality/cost effects of each enhancement are *measured*,
not asserted — that habit is itself part of the evaluation story the assignment grades.
