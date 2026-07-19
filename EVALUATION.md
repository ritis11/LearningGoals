# Evaluation

> How I decide whether the outputs are good, what I measure, results against my test
> set, and — importantly — what my evaluation does *not* tell me. Designed alongside
> the code, not after it; §7 is the short history of every experiment and pivot that
> shaped it. Reproduce everything with `uv run curriculum eval` (and
> `--selftest` for the meta-eval).

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
| plan constraints honored (patterns from the run's own `constraint_notes`) | **persona-agnostic**: works on unseen personas with no expectations file — the planner normalizes free-text constraints into the artifact, and the eval verifies against that |
| coverage vs gap claims consistent (+ measured coverage %) | catches the curator declaring a "gap" it actually covered; coverage % reported per curriculum |
| dropped-list non-empty; expertise claim non-empty | the reasoning trace is real, not decorative |

### Meta-evaluation: the checks are themselves tested
`curriculum eval --selftest` seeds seven deliberate faults into a copy of a real run —
hallucinated pick, blown budget, duplicate, fabricated reason, constraint violation,
gap contradiction, sub-floor engagement — and asserts each targeted check **fails**.
This proves the alarms ring and guards against check-rot as the schema evolves. Zero
LLM cost; runs in CI-time seconds.

### Variance & bias probes (opt-in, small LLM cost)
- `curriculum stability <persona> --runs N`: same persona N times on warm caches (only
  the LLM varies) → mean pick-set Jaccard, watch-minutes spread, worst check pass-rate.
  Puts a *number* on the §4 "one-run variance" limit.
- `curriculum eval --judge-provider <other>`: judge with a different model family than
  the curator, mitigating the §4 shared-blind-spots limit. (Mechanism in place; the
  final sweep judged same-family — only a Gemini key had quota — so that limit stands
  as documented rather than mitigated.)
- A systematic human-labeling pass (verdicts recorded before seeing judge scores, with
  an agreement table) was prototyped but cut for time — see README "what I'd do with
  more time". §5 above is the manual version of the same idea.

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

Final full sweep (2026-07-19, provider: gemini flash, chapters-first content;
`eval/results/20260719-075900`). The fault-injection self-test also passed the same
day: **7/7 seeded faults caught**.

| persona | checks | judge avg | coverage | median views | mean like% | cost $ | latency s | notes |
|---|---|---|---|---|---|---|---|---|
| explosives_blocked | 2/2 | n/a (refusal) | — | — | — | 0.0007 | 1.8 | refused correctly |
| french_cooking_novice | 13/13 | 5.0 | 100% | 539,248 | 2.0% | 0.033 | 55 | all checks pass |
| hindi_language_learner | 13/13 | 5.0 | 100% | 1,538,858 | 2.6% | 0.032 | 46 | Hindi-language picks verified |
| senior_dev_knows_it_all | 13/13 | 5.0 | 100% | 28,491 | 3.9% | 0.135 | 60 | `goal_already_met` flagged; pivoted to advanced |
| sixty_minute_crunch | 13/13 | 5.0 | 100% | 265,048 | 3.0% | 0.096 | 44 | tight 60-min budget respected |
| travel_blogger_expert_track | 12/13 | 4.86 | 100% | 122,418 | 3.5% | 0.103 | 53 | **FAILED coverage_gaps_consistent — see §5** |
| weekend_react_dev | 14/14 | 5.0 | 100% | 38,245 | 4.1% | 0.102 | 58 | reference persona; matches the assignment's output sketch |

Cost/latency: **~$0.03–0.14 and 45–60s per curriculum** on gemini flash with warm
YouTube caches (~1–2.5 min cold). The same reference persona on Anthropic
(Haiku 4.5 + Sonnet 5) cost $0.32 — a ~5–10× spread for outputs that pass the same
checks. An earlier sweep (2026-07-18, `eval/results/20260718-131127`) was cut short at
4/7 personas by the Gemini free tier's daily request cap — itself a finding that drove
the retry/backoff and caching hardening.

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
3. **The judge gave 4.86 to a curriculum the deterministic suite failed.** In the
   final sweep, `travel_blogger_expert_track` scored near-perfect with the judge while
   `coverage_gaps_consistent` caught a real contradiction: a pick claimed to cover
   "Short-Form Video (TikTok/Shorts) Setup" while the curator *also* declared it a
   plan gap. The judge — which reads the same artifact — missed the inconsistency; a
   5-line deterministic check caught it. This is the clearest argument in this
   document for layering cheap exact checks under LLM judging rather than trusting
   either alone.

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

## 7. Appendix: experiments & pivots (the short version)

The full day-by-day journal is `docs/BUILD_NOTES.md`; these are the moments that
changed the design. Every one is reproducible from files in `experiments/`.

1. **Fetch strategy was benchmarked before it was built.** Question: one
   full-metadata search vs flat-search + deep-fetch-finalists. Measured
   (`experiments/benchmark_youtube_fetch.py`): full search does per-video work
   serially (~64s for a 60-candidate pool); the two-stage design does the same job in
   ~5–8s. Also learned: transcripts are a *separate* rate-limited download, and raw
   transcripts run 0.9k–10.7k tokens/video → per-video compression budgets.
2. **The expertise claim moved to where the evidence is.** First design asked the
   planner to declare "the level you'll reach" before any search — ungroundable.
   Pivot: planner emits a labeled *estimate*; the curator, holding the picked videos'
   actual content, issues the grounded verdict; shortfalls are reported.
3. **YouTube's caption endpoint forced the chapters-first pivot.** Live runs hit
   IP-level caption blocks (429s across all clients and libraries, all day).
   Transcript-first fetching stalled runs; chapter/description grounding passed every
   check and judge dimension anyway. Pivot: transcripts became opt-in
   (`--transcripts`); reliability machinery (pacing, breaker, permanent cache,
   signed-URL refresh) retained for when they're on.
4. **Reasoning spend silently truncated outputs — twice.** Thinking tokens share the
   output budget; curricula were cut mid-JSON at 8k and again at 16k tokens. Fixes:
   bounded reasoning effort on generation-heavy calls, a self-healing parse ladder,
   and per-stage token/cost instrumentation (which also exposed a 223s → 21s win in
   the web-search enrichment step).
5. **Engagement was discarded as a ranker, then adopted as a floor.** Popularity ≠
   fit (the assignment's own framing), but near-zero views / sub-0.5% like-ratio is a
   real negative signal. It now appears exactly twice: prompt guidance
   (floor + tiebreak, never ranking) and the deterministic `engagement_floor` check.
6. **A second provider was added mid-build** (Gemini flash via raw REST) when quota
   caps threatened iteration — and turned "model comparison" into a measured result:
   ~$0.03 vs ~$0.32 per curriculum passing identical checks. The free tier's 20
   requests/day cap then killed an eval sweep, which drove retry/backoff hardening.
7. **The eval learned to test itself.** Final round: seeded-fault self-test (7/7
   caught), persona-agnostic constraint checks (works on graders' unseen personas),
   and coverage-vs-gaps consistency — which promptly caught a real curator
   contradiction the 4.86-scoring LLM judge had waved through (§5.3).
