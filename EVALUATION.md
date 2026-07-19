# Evaluation

> How I decide whether the outputs are good, what I measure, results against my test
> set, and — importantly — what my evaluation does *not* tell me.
>
> **Status: results table pending the first full eval run** (`uv run curriculum eval`).
> Everything else here was designed alongside the code, not after it.

## 1. What "good" means here

A curriculum is good when a *specific* learner can follow it to a *specific* goal
within a *specific* time budget. That decomposes into properties I can check at three
levels of rigor:

1. **Deterministic checks** (`eval/checks.py`) — properties that must always hold, no
   judgment required. Cheap, run on every eval.
2. **LLM judge** (`eval/judge.py`) — rubric dimensions that need reading comprehension,
   scored 1–5 with cited justification, against the finalists' *actual content* so
   claims can be verified rather than trusted.
3. **My own spot-reads** — logged in §5 whenever they disagree with 1 or 2.

Search is non-deterministic, so the test set asserts **properties**
(`test_set/*.expected.json`), never exact video IDs — a "golden set" of video IDs would
rot within weeks and punish correct behavior.

## 2. What is measured

### Deterministic checks (every run)
| Check | Why it matters |
|---|---|
| no hallucinated videos (picks ⊆ real candidate pool) | the single worst failure mode of LLM curation |
| total minutes ≤ budget × 1.05; segments within video bounds | the budget is the product's core promise |
| pick count 1–6; no duplicates | structural sanity |
| forbidden title patterns absent (per persona) | constraint satisfaction, e.g. "no 'in 100 seconds'" |
| topic terms present in picks | curriculum is about the goal at all |
| reasons share content n-grams with the video's chapters/transcript | cheap fabrication detector (proxy — see §4) |
| refusal present/absent as expected | safety guard works and doesn't overfire |
| engagement floor: no pick <1k views or <0.5% like-ratio | catches abandoned/disliked content; the summary also reports median views + mean like-ratio per curriculum (§6 for why it's a floor, not a ranker) |
| dropped-list non-empty; expertise claim non-empty | the reasoning trace is real, not decorative |

### Judge dimensions (1–5 each)
`relevance_to_goal`, `level_fit` (nothing re-teaching knowns / assuming unknowns),
`ordering_logic`, `constraint_satisfaction`, `reason_groundedness` (reasons vs the
video bundles — the ground truth is in the prompt), `selection_quality` (were drops
justified?), `expertise_claim_grounded` (is the "level you'll reach" verdict supported
by picked content + consistent with admitted gaps?).

### Cost & latency
Every run writes `run_meta.json` (per-stage seconds, per-call tokens, computed $). The
eval summary table includes both per persona.

## 3. Results

First full sweep (2026-07-18, provider: gemini flash; `eval/results/20260718-131127`):

| persona | checks | judge avg | cost $ | latency s | notes |
|---|---|---|---|---|---|
| explosives_blocked | 2/2 | n/a (refusal) | 0.0005 | 1.8 | refused correctly |
| french_cooking_novice | 10/10 | 4.86 | 0.031 | 138 | all checks pass |
| hindi_language_learner | 10/10 | 5.0 | 0.035 | 47 | Hindi-language picks verified |
| senior_dev_knows_it_all | 10/10 | 4.86 | 0.030 | 98 | `goal_already_met` flagged; pivoted to advanced content |
| weekend_react_dev | 11/11 | pending¹ | 0.032 | 133 | all checks pass (checks-only rerun `20260718-132148`) |
| sixty_minute_crunch | pending¹ | pending¹ | — | — | blocked: Gemini free-tier daily quota |
| travel_blogger_expert_track | pending¹ | pending¹ | — | — | blocked: Gemini free-tier daily quota |

¹ The sweep exhausted the Gemini free tier's daily request cap (limit 20/day) after
four personas; remaining rows to be filled after quota reset or on the paid tier.
The failures were quota 429s, not pipeline defects — the same personas' pipelines are
exercised by the deterministic-check suite where artifacts exist.

Cost/latency (gemini flash): ~$0.03 and ~1–2.5 min per curriculum cold;
the same reference persona on Anthropic (Haiku 4.5 + Sonnet 5) cost $0.32 — a 10×
spread for outputs that pass the same checks (see §5 for quality-difference caveats).

## 4. What this evaluation does NOT tell me

- **Whether a pick is the *best available* video.** Checks verify constraints; the
  judge only sees the ~14 finalists. If search never surfaced the ideal video, nothing
  here detects that. (Milestone 2's community-sourcing addition attacks exactly this.)
- **Pedagogical quality.** A video can satisfy every constraint and still teach badly.
  The engagement stats are weak proxies; I deliberately did not let them dominate (§6).
- **Judge blind spots are correlated with curator blind spots** — same model family
  (Sonnet 5 judges Sonnet 5). A systematic bias (e.g. overvaluing chaptered videos)
  would be invisible. Mitigation available but not run: judge with a different family.
- **The groundedness n-gram check is a proxy.** It catches reasons with zero
  connection to the video, but a reason could quote a real chapter title while still
  misrepresenting the video. The judge dimension covers part of this gap, with the
  correlation caveat above.
- **One-run variance.** Each eval is a single sample per persona; LLM and search
  non-determinism mean a pass could be luck. Re-running with warm caches keeps search
  fixed but not model outputs.
- **Transcript grounding is now opt-in (`--transcripts`), so judge scores are
  conditional on chapters.** YouTube rate-limits its caption endpoint so aggressively
  (observed live — see `docs/BUILD_NOTES.md`) that transcript fetching is off by
  default; the standard evidence base is chapters + descriptions + stats. Groundedness
  checks and judge dimensions therefore measure "grounded in what was available" —
  a curriculum built from rich chapter lists and one built from thin descriptions can
  score alike; read `transcript_coverage` and chapter counts in the trace alongside
  the scores.

## 5. Where eval and human judgment disagreed

> Maintained as disagreements are found during development — see also
> `docs/BUILD_NOTES.md`.

1. **3 picks vs the assignment's "4–6 videos, ~5 hours" sketch.** For the reference
   persona the curator picked 3 videos / 160 of 360 minutes, justifying the headroom
   as time to *build* (the goal is a hands-on project; the constraint says
   project-based). Every check passes and the reasoning is defensible — arguably
   *better* than filling the budget with passive watching — but it deviates from the
   assignment's own sketch of good output. The eval can't adjudicate this: it's a
   philosophy question (watch-time vs total-learning-time). Kept the behavior,
   documented the tension, added no check — a check would just encode one side.
2. **Judge scored 4.86–5.0 while every finalist had `transcript_coverage="none"`**
   (YouTube caption block active all day). Reasons were grounded in chapters +
   descriptions, and the judge — whose ground truth is the same bundles — correctly
   found them grounded *relative to what was available*. A human would note these
   curricula are less deeply verified than the scores suggest. This is the §4
   "eval can't see what search/fetch never surfaced" limit showing up in practice:
   near-perfect judge scores are conditional on bundle completeness, so
   `transcript_coverage` must be read alongside the scores.

## 6. Signals considered and discarded

- **View count / like ratio as a ranking signal — discarded; adopted as a FLOOR.**
  Popularity ranks what's popular, not what's right for *this* learner — the
  assignment's own framing. But near-zero views or a sub-0.5% like-ratio is a real
  *negative* signal (abandoned or disliked content), so engagement now enters exactly
  twice: (a) prompts tell triage/curator it is a quality floor and tiebreak between
  otherwise-equal picks, never the ranking; (b) the deterministic `engagement_floor`
  check (thresholds: 1,000 views, 0.5% like-ratio — module constants in
  `eval/checks.py`) flags egregious picks and the report shows median views / mean
  like-ratio per curriculum. Thresholds are deliberately low: a Hindi-language Excel
  tutorial that is *right* for the learner legitimately has fewer views than a viral
  English one, and the floor must never punish that.
- **Golden video IDs per persona.** Rejected: non-deterministic search + a live corpus
  make exact-ID assertions rot; property assertions replaced them.
- **Comment mining as an MVP quality signal.** Valuable ("outdated as of v19" comments)
  but adds a per-finalist fetch + tokens; deferred to milestone 2 with the latency data
  to justify the call (`docs/BUILD_NOTES.md`, Experiment 1).
- **Whisper transcription for subtitle-less videos.** Auto-captions covered 8/8 videos
  in the pre-build benchmark; cost/latency of audio transcription isn't justified at
  MVP scale.
- **Attaching web search to the structured planning call.** Server tools can pause
  turns mid-call; a separate conditional recency step is simpler and gated to
  fast-moving topics only.
