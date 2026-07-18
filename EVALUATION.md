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

<!-- paste eval/results/<timestamp>/summary.md here after running: uv run curriculum eval -->
*Pending first keyed run.*

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

## 5. Where eval and human judgment disagreed

> Maintained as disagreements are found during development — see also
> `docs/BUILD_NOTES.md`.

*(to be filled during keyed runs)*

## 6. Signals considered and discarded

- **View count / like ratio as a ranking signal.** Deliberately demoted to a weak
  tiebreak: popularity ranks what's popular, not what's right for *this* learner —
  that's the assignment's own framing of the problem. Triage sees the numbers but is
  prompted to prioritize relevance and level fit.
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
