"""Orchestrates the eight stages. One function, linear flow, per-stage timing."""

import time
from pathlib import Path

from . import config, curator, guard, planner, render, triage, youtube
from .llm import LLM
from .schemas import Persona, Refusal


def run(persona: Persona, use_cache: bool = True, output_root: Path | None = None) -> Path:
    """Runs the full pipeline; returns the run directory with all artifacts."""
    run_dir = (output_root or config.OUTPUT_DIR) / persona.persona_id
    llm = LLM()
    stage_seconds: dict[str, float] = {}
    t_run = time.perf_counter()

    def timed(name: str, fn, *args, **kwargs):
        t0 = time.perf_counter()
        out = fn(*args, **kwargs)
        stage_seconds[name] = round(time.perf_counter() - t0, 2)
        print(f"  [{name}] {stage_seconds[name]}s")
        return out

    def meta() -> dict:
        return {
            "stage_seconds": stage_seconds,
            "total_seconds": round(time.perf_counter() - t_run, 2),
            "llm_calls": llm.calls,
            "total_cost_usd": llm.total_cost_usd,
        }

    # 1 — guard
    verdict = timed("guard", guard.check_goal, llm, persona)
    if not verdict.safe:
        refusal = Refusal(persona_id=persona.persona_id, category=verdict.category, reason=verdict.reason)
        render.write_refusal(run_dir, refusal, meta())
        print(f"  goal declined ({verdict.category}); refusal written to {run_dir}")
        return run_dir

    # 2 — recency (conditional) + plan
    recency = timed("recency", planner.fetch_recency_notes, llm, persona) if verdict.needs_recency_check else ""
    plan = timed("plan", planner.make_plan, llm, persona, recency)
    print(f"  queries: {plan.search_queries}")

    # 3 — flat search
    candidates = timed("search", youtube.search_many, plan.search_queries, config.RESULTS_PER_QUERY, use_cache)
    if not candidates:
        raise RuntimeError("no search results from any query — cannot build a curriculum")
    print(f"  candidates: {len(candidates)}")

    # 4 — triage
    kept, hard_dropped = triage.hard_filter(candidates, persona.time_budget_minutes)
    finalist_ids, scores = timed("triage", triage.triage, llm, persona, plan, kept)
    print(f"  finalists: {len(finalist_ids)}")

    # 5 — deep fetch + bundles
    language = next(
        (n.instruction for n in plan.constraint_notes if n.kind == "language"), ""
    )
    lang_code = _language_code(language) or "en"
    infos = timed("deep_fetch", youtube.fetch_many, finalist_ids, use_cache, lang_code)
    bundles = [youtube.build_content_bundle(i, lang_code) for i in infos.values()]
    if not bundles:
        raise RuntimeError("deep fetch failed for every finalist")

    # 6 — curate (+ validation/retry inside)
    curriculum = timed("curate", curator.curate, llm, persona, plan, bundles)

    # 7 — render (with full trace for eval + milestone-2 follow-up Q&A)
    trace = {
        "hard_filtered": hard_dropped,
        "triage_scores": [s.model_dump() for s in scores],
        "finalist_ids": finalist_ids,
        "candidates": [c.model_dump() for c in candidates],
        "recency_notes": recency,
    }
    render.write_run(run_dir, persona, plan, curriculum, trace, meta())
    print(f"  done → {run_dir}  (cost ${llm.total_cost_usd})")
    return run_dir


def _language_code(instruction: str) -> str:
    """Best-effort ISO code from a language constraint note ('content in Hindi' -> 'hi')."""
    table = {
        "hindi": "hi", "spanish": "es", "french": "fr", "german": "de",
        "portuguese": "pt", "japanese": "ja", "korean": "ko", "chinese": "zh",
        "english": "en",
    }
    low = instruction.lower()
    return next((code for name, code in table.items() if name in low), "")
