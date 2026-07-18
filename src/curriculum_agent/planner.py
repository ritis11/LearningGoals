"""Stage 2: learner profiling + topic plan + query generation (Sonnet 5).

Recency enrichment is a separate, conditional call (gated by the guard's
needs_recency_check) so the structured-output planning call never mixes with
server-side tool use. See docs/BUILD_NOTES.md for the rationale.
"""

from . import config, prompts
from .llm import LLM
from .schemas import Persona, TopicPlan


def fetch_recency_notes(llm: LLM, persona: Persona) -> str:
    user = (
        f"Learning area: {persona.goal}\n"
        f"Learner background: {persona.user_context.background}\n"
        "What should a curriculum built today reflect?"
    )
    try:
        return llm.text_with_web_search(
            stage="recency",
            model=config.MODEL_SMART,
            system=prompts.RECENCY_SYSTEM,
            user=user,
        ).strip()
    except Exception as exc:  # enrichment is optional — never fail the run for it
        print(f"[planner] recency check failed, continuing without: {exc}")
        return ""


def make_plan(llm: LLM, persona: Persona, recency_notes: str = "") -> TopicPlan:
    parts = [
        "Learner persona:",
        persona.model_dump_json(indent=2),
    ]
    if recency_notes:
        parts += ["", "Recency notes (from live web search today):", recency_notes]
    plan = llm.parse(
        stage="plan",
        model=config.MODEL_SMART,
        system=prompts.PLANNER_SYSTEM,
        user="\n".join(parts),
        output_model=TopicPlan,
        max_tokens=4096,
    )
    # keep the query list inside configured bounds regardless of model enthusiasm
    plan.search_queries = plan.search_queries[: config.MAX_QUERIES]
    return plan
