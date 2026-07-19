"""Stage 1: harmful-goal guard (+ recency-check gate), one cheap Haiku call."""

from . import prompts
from .llm import BaseLLM
from .schemas import GuardResult, Persona


def check_goal(llm: BaseLLM, persona: Persona) -> GuardResult:
    user = (
        f"Learning goal: {persona.goal}\n"
        f"Learner background: {persona.user_context.background}"
    )
    return llm.parse(
        stage="guard",
        model=llm.model_fast,
        system=prompts.GUARD_SYSTEM,
        user=user,
        output_model=GuardResult,
        max_tokens=512,
    )
