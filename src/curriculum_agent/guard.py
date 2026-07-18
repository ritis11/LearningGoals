"""Stage 1: harmful-goal guard (+ recency-check gate), one cheap Haiku call."""

from . import config, prompts
from .llm import LLM
from .schemas import GuardResult, Persona


def check_goal(llm: LLM, persona: Persona) -> GuardResult:
    user = (
        f"Learning goal: {persona.goal}\n"
        f"Learner background: {persona.user_context.background}"
    )
    return llm.parse(
        stage="guard",
        model=config.MODEL_FAST,
        system=prompts.GUARD_SYSTEM,
        user=user,
        output_model=GuardResult,
        max_tokens=512,
    )
