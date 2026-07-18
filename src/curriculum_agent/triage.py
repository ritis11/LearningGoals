"""Stage 4: hard filters in code, then one Haiku call scores the survivors."""

from . import config, prompts
from .llm import LLM
from .schemas import CandidateVideo, Persona, TopicPlan, TriageResult, TriageScore


def hard_filter(
    candidates: list[CandidateVideo], budget_minutes: int
) -> tuple[list[CandidateVideo], list[dict]]:
    """Deterministic, free filters. Returns (kept, dropped_records_for_trace)."""
    kept, dropped = [], []
    for c in candidates:
        if c.duration_s is None:
            dropped.append({"id": c.id, "title": c.title, "why": "no duration (likely live/upcoming)"})
        elif c.duration_s < config.MIN_VIDEO_SECONDS:
            dropped.append({"id": c.id, "title": c.title, "why": f"under {config.MIN_VIDEO_SECONDS}s (short-form)"})
        elif c.duration_s > budget_minutes * 60 * 2:
            # >2x budget: even partial watching rarely pays off; keep the trace honest
            dropped.append({"id": c.id, "title": c.title, "why": "more than 2x the total time budget"})
        else:
            kept.append(c)
    return kept, dropped


def _candidate_table(candidates: list[CandidateVideo]) -> str:
    lines = ["id | title | minutes | channel | views"]
    for c in candidates:
        lines.append(
            f"{c.id} | {c.title} | {round((c.duration_s or 0) / 60)} | "
            f"{c.channel or '?'} | {c.view_count or '?'}"
        )
    return "\n".join(lines)


def triage(
    llm: LLM, persona: Persona, plan: TopicPlan, candidates: list[CandidateVideo]
) -> tuple[list[str], list[TriageScore]]:
    """Returns (finalist_ids, all_scores). Scores for every candidate are kept for the trace."""
    user = "\n\n".join(
        [
            f"Goal: {persona.goal}",
            f"Learner expertise: {plan.expertise_start}",
            f"Time budget: {persona.time_budget_minutes} minutes",
            "Topic plan: " + "; ".join(t.name for t in sorted(plan.topics, key=lambda t: t.order)),
            "Constraint notes:\n" + "\n".join(f"- {n.instruction}" for n in plan.constraint_notes)
            if plan.constraint_notes
            else "Constraint notes: none",
            "Candidates:\n" + _candidate_table(candidates),
        ]
    )
    result: TriageResult = llm.parse(
        stage="triage",
        model=config.MODEL_FAST,
        system=prompts.TRIAGE_SYSTEM,
        user=user,
        output_model=TriageResult,
        max_tokens=8192,
    )
    known_ids = {c.id for c in candidates}
    scores = [s for s in result.scores if s.id in known_ids]  # drop hallucinated ids
    ranked = sorted(scores, key=lambda s: s.score, reverse=True)
    finalists = [s.id for s in ranked if not s.constraint_violation][: config.FINALIST_COUNT]
    return finalists, scores
