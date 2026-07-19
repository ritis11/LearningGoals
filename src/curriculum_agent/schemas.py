"""Pydantic contracts for every stage boundary.

Models used as LLM structured outputs (GuardResult, TopicPlan, TriageResult,
Curriculum, JudgeScores) keep to structured-output-friendly shapes: no dicts with
arbitrary keys, no recursion, no numeric range constraints.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# --- stage 0: input -----------------------------------------------------------

class UserContext(BaseModel):
    background: str
    known: list[str] = []
    unknown: list[str] = []
    constraints: str = ""


class Persona(BaseModel):
    persona_id: str
    goal: str
    time_budget_minutes: int
    user_context: UserContext

    @field_validator("time_budget_minutes")
    @classmethod
    def _positive_budget(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("time_budget_minutes must be > 0")
        return v

    @field_validator("goal")
    @classmethod
    def _nonempty_goal(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("goal must be non-empty")
        return v


# --- stage 1: guard (LLM output) -----------------------------------------------

class GuardResult(BaseModel):
    safe: bool
    category: Optional[str] = Field(
        None, description="If unsafe: short category, e.g. 'weapons', 'malware'"
    )
    reason: str = Field(description="One sentence explaining the verdict")
    needs_recency_check: bool = Field(
        description="True if the goal concerns a fast-moving field (frameworks, tools, "
        "AI) where recent developments should inform the curriculum; False for "
        "evergreen topics (cooking, language basics, math)"
    )


# --- stage 2: topic plan (LLM output) --------------------------------------------

class Topic(BaseModel):
    name: str
    why: str = Field(description="Why this learner needs it for this goal")
    est_minutes: int
    order: int = Field(description="Prerequisite-respecting position, 1-based")


class ConstraintNote(BaseModel):
    source_text: str = Field(description="The learner's words this comes from")
    kind: Literal["exclude_title_pattern", "prefer_format", "language", "other"]
    instruction: str = Field(
        description="Machine-usable directive for search/triage/curation, e.g. "
        "\"exclude videos whose title matches 'in 100 seconds'\""
    )


class TopicPlan(BaseModel):
    expertise_start: str = Field(
        description="Learner's starting level IN THE GOAL DOMAIN, derived from "
        "background + known + unknown (e.g. 'experienced engineer, React beginner')"
    )
    expertise_start_why: str
    expertise_target_provisional: str = Field(
        description="PRE-SEARCH ESTIMATE of the level plausibly reachable within the "
        "time budget. Used only to calibrate queries and time allocation; the grounded "
        "verdict comes from the curator after video content is known."
    )
    goal_already_met: bool = Field(
        description="True if the learner's known concepts already cover the goal "
        "(knowns >> unknowns edge case); plan should then pivot to advanced/deepening "
        "content and say so"
    )
    goal_already_met_note: str = ""
    topics: list[Topic]
    constraint_notes: list[ConstraintNote] = []
    search_queries: list[str] = Field(
        description="3-5 targeted YouTube search queries, constraint-aware"
    )


# --- stages 3-5: youtube layer ---------------------------------------------------

class CandidateVideo(BaseModel):
    """Light record from flat search — all that triage needs."""
    id: str
    title: str
    url: str
    duration_s: Optional[int] = None
    channel: Optional[str] = None
    view_count: Optional[int] = None
    source_query: str = ""


class Chapter(BaseModel):
    title: str
    start_s: int
    end_s: int


class VideoContent(BaseModel):
    """Deep-fetched bundle for one finalist — the curator's raw material."""
    id: str
    title: str
    url: str
    duration_s: int
    channel: str = ""
    channel_followers: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    like_ratio: Optional[float] = None  # likes/views; quality floor + tiebreak signal
    upload_date: str = ""            # YYYYMMDD
    description_excerpt: str = ""
    chapters: list[Chapter] = []
    transcript_excerpt: str = ""     # compressed to TRANSCRIPT_TOKEN_BUDGET
    transcript_coverage: Literal["full", "sampled", "none"] = "none"
    transcript_source: Literal["manual", "auto", "none"] = "none"
    transcript_language: str = ""


# --- stage 4: triage (LLM output) --------------------------------------------------

class TriageScore(BaseModel):
    id: str
    score: int = Field(description="0-10: relevance to plan + level fit + constraint fit")
    reason: str = Field(description="One short phrase")
    constraint_violation: bool = False


class TriageResult(BaseModel):
    scores: list[TriageScore]


# --- stage 6: curriculum (LLM output) -----------------------------------------------

class WatchSegment(BaseModel):
    start_s: int
    end_s: int
    chapter_title: str = ""


class Watch(BaseModel):
    mode: Literal["full", "segments"]
    segments: list[WatchSegment] = []
    minutes: int = Field(description="Actual minutes of watching this pick demands")


class Pick(BaseModel):
    video_id: str
    order: int
    title: str
    url: str
    watch: Watch
    reason: str = Field(
        description="MUST cite specific chapters/transcript moments from this video's "
        "bundle by name or timestamp — never invented content"
    )
    covers_topics: list[str]
    confidence: Literal["high", "medium", "low"]
    confidence_why: str


class DroppedVideo(BaseModel):
    video_id: str
    title: str
    url: str = ""  # set programmatically from video_id after validation — never trusted from the LLM
    reason: str = Field(
        description="Why it lost. For dedup: 'overlaps with <picked title> because "
        "<specific shared content>'"
    )


class BudgetReport(BaseModel):
    total_minutes: int
    budget_minutes: int
    headroom_note: str


class ExpertiseAchieved(BaseModel):
    level: str
    justification: str = Field(
        description="GROUNDED in what the picked videos' content actually covers and "
        "what plan_gaps omit; flag shortfall vs the provisional target if any"
    )


class Curriculum(BaseModel):
    picks: list[Pick]
    dropped: list[DroppedVideo]
    budget: BudgetReport
    plan_gaps: list[str] = Field(
        description="TopicPlan topics no pick covers — honesty over padding"
    )
    expertise_achieved: ExpertiseAchieved
    summary: str = Field(description="2-3 sentence learner-facing overview")


# --- refusal artifact ----------------------------------------------------------------

class Refusal(BaseModel):
    persona_id: str
    refused: Literal[True] = True
    category: Optional[str] = None
    reason: str


# --- eval: judge (LLM output) ----------------------------------------------------------

class JudgeDimension(BaseModel):
    score: int = Field(description="1 (poor) to 5 (excellent)")
    justification: str


class JudgeScores(BaseModel):
    relevance_to_goal: JudgeDimension
    level_fit: JudgeDimension
    ordering_logic: JudgeDimension
    constraint_satisfaction: JudgeDimension
    reason_groundedness: JudgeDimension
    selection_quality: JudgeDimension
    expertise_claim_grounded: JudgeDimension
    overall_comment: str


# --- web UI: concept suggestions (LLM output) -------------------------------------

class ConceptSuggestions(BaseModel):
    known: list[str] = Field(description="Concepts the learner likely already has")
    unknown: list[str] = Field(description="Goal-required concepts they likely lack")
