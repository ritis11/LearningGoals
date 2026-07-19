"""Stage 7: write run artifacts — curriculum.json, curriculum.md, candidates.json, run_meta.json."""

import json
from pathlib import Path

from .schemas import Curriculum, Persona, Refusal, TopicPlan


def _mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def curriculum_markdown(persona: Persona, plan: TopicPlan, cur: Curriculum) -> str:
    lines = [
        f"# Curriculum — {persona.persona_id}",
        "",
        f"**Goal:** {persona.goal}",
        f"**Time budget:** {persona.time_budget_minutes} min · **planned watch time:** "
        f"{cur.budget.total_minutes} min ({cur.budget.headroom_note})",
        "",
        f"> {cur.summary}",
        "",
        "## Expertise trajectory",
        f"- **Start:** {plan.expertise_start} — {plan.expertise_start_why}",
        f"- **Provisional target (pre-search estimate):** {plan.expertise_target_provisional}",
        f"- **Level reached by this curriculum (grounded):** {cur.expertise_achieved.level}",
        f"  - {cur.expertise_achieved.justification}",
    ]
    if plan.goal_already_met:
        lines += ["", f"⚠️ **Note:** {plan.goal_already_met_note}"]

    lines += ["", "## Watch in this order", ""]
    for p in sorted(cur.picks, key=lambda p: p.order):
        lines += [
            f"### {p.order}. [{p.title}]({p.url}) — {p.watch.minutes} min "
            f"(confidence: {p.confidence})",
        ]
        if p.watch.mode == "segments":
            lines.append("Watch only these segments:")
            for s in p.watch.segments:
                label = f" — {s.chapter_title}" if s.chapter_title else ""
                lines.append(f"- {_mmss(s.start_s)} → {_mmss(s.end_s)}{label}")
        lines += [
            f"**Why:** {p.reason}",
            f"**Covers:** {', '.join(p.covers_topics)}",
            f"**Confidence rationale:** {p.confidence_why}",
            "",
        ]

    if cur.plan_gaps:
        lines += [
            "## Not covered (honest gaps)",
            *[f"- {g}" for g in cur.plan_gaps],
            "",
        ]

    lines += ["## Considered but dropped", ""]
    lines += ["| Video | Why it lost |", "|---|---|"]
    for d in cur.dropped:
        title = f"[{d.title}]({d.url})" if d.url else d.title
        lines.append(f"| {title} | {d.reason} |")
    lines.append("")
    return "\n".join(lines)


def write_run(
    run_dir: Path,
    persona: Persona,
    plan: TopicPlan,
    curriculum: Curriculum,
    candidates_trace: dict,
    run_meta: dict,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "curriculum.json").write_text(
        json.dumps(
            {
                "persona": persona.model_dump(),
                "topic_plan": plan.model_dump(),
                "curriculum": curriculum.model_dump(),
            },
            indent=2,
        )
    )
    (run_dir / "curriculum.md").write_text(curriculum_markdown(persona, plan, curriculum))
    (run_dir / "candidates.json").write_text(json.dumps(candidates_trace, indent=2))
    (run_dir / "run_meta.json").write_text(json.dumps(run_meta, indent=2))


def write_refusal(run_dir: Path, refusal: Refusal, run_meta: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "refusal.json").write_text(refusal.model_dump_json(indent=2))
    (run_dir / "refusal.md").write_text(
        f"# Request declined — {refusal.persona_id}\n\n"
        f"This learning goal was declined ({refusal.category}): {refusal.reason}\n"
    )
    (run_dir / "run_meta.json").write_text(json.dumps(run_meta, indent=2))
