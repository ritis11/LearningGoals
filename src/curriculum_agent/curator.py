"""Stage 6: curation (Sonnet 5) + code-level validation with one retry."""

import json

from . import config, prompts
from .llm import LLM
from .schemas import Curriculum, Persona, TopicPlan, VideoContent


def _bundles_block(bundles: list[VideoContent]) -> str:
    return json.dumps([b.model_dump() for b in bundles], indent=1)


def _user_message(persona: Persona, plan: TopicPlan, bundles: list[VideoContent]) -> str:
    return "\n\n".join(
        [
            "Learner persona:\n" + persona.model_dump_json(indent=2),
            "Topic plan:\n" + plan.model_dump_json(indent=2),
            f"Time budget: {persona.time_budget_minutes} minutes (HARD LIMIT)",
            "Finalist video bundles:\n" + _bundles_block(bundles),
        ]
    )


def validate(curriculum: Curriculum, bundles: list[VideoContent], budget_minutes: int) -> list[str]:
    """Deterministic checks the LLM occasionally violates. Returns violation strings."""
    problems = []
    by_id = {b.id: b for b in bundles}

    for p in curriculum.picks:
        if p.video_id not in by_id:
            problems.append(f"pick {p.video_id} is not one of the provided finalist ids")
            continue
        video = by_id[p.video_id]
        for seg in p.watch.segments:
            if seg.end_s > video.duration_s + 5 or seg.start_s < 0 or seg.start_s >= seg.end_s:
                problems.append(
                    f"pick {p.video_id}: segment {seg.start_s}-{seg.end_s}s outside video "
                    f"duration {video.duration_s}s"
                )

    total = sum(p.watch.minutes for p in curriculum.picks)
    if total > budget_minutes * config.BUDGET_TOLERANCE:
        problems.append(f"total watch minutes {total} exceeds budget {budget_minutes}")
    if not curriculum.picks:
        problems.append("no picks")
    if len(curriculum.picks) > config.MAX_PICKS:
        problems.append(f"{len(curriculum.picks)} picks exceeds max {config.MAX_PICKS}")
    if len({p.video_id for p in curriculum.picks}) != len(curriculum.picks):
        problems.append("duplicate video in picks")
    return problems


def curate(
    llm: LLM, persona: Persona, plan: TopicPlan, bundles: list[VideoContent]
) -> Curriculum:
    user = _user_message(persona, plan, bundles)
    curriculum: Curriculum = llm.parse(
        stage="curate",
        model=config.MODEL_SMART,
        system=prompts.CURATOR_SYSTEM,
        user=user,
        output_model=Curriculum,
        max_tokens=8192,
    )
    problems = validate(curriculum, bundles, persona.time_budget_minutes)
    if problems:
        retry_user = user + (
            "\n\nYour previous curriculum was REJECTED by validation for these "
            "violations — produce a corrected curriculum:\n"
            + "\n".join(f"- {p}" for p in problems)
        )
        curriculum = llm.parse(
            stage="curate_retry",
            model=config.MODEL_SMART,
            system=prompts.CURATOR_SYSTEM,
            user=retry_user,
            output_model=Curriculum,
            max_tokens=8192,
        )
        problems = validate(curriculum, bundles, persona.time_budget_minutes)
        if problems:
            raise RuntimeError(f"curation failed validation twice: {problems}")
    # normalize budget report to measured numbers (don't trust model arithmetic)
    curriculum.budget.total_minutes = sum(p.watch.minutes for p in curriculum.picks)
    curriculum.budget.budget_minutes = persona.time_budget_minutes
    return curriculum
