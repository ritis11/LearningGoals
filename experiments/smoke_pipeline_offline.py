"""Offline integration smoke: everything except LLM calls.

Exercises: persona schemas (all test_set files), search+deep-fetch+bundles (live
YouTube, no API key), triage hard filters, curator validation, render, eval checks.
Run: uv run python experiments/smoke_pipeline_offline.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curriculum_agent import config, curator, render, triage, youtube
from curriculum_agent.schemas import (
    BudgetReport, Curriculum, DroppedVideo, ExpertiseAchieved, Persona, Pick, Topic,
    TopicPlan, Watch,
)
from eval.checks import run_checks

# 1 — every test persona validates
personas = {}
for f in sorted(config.TEST_SET_DIR.glob("*.json")):
    if f.name.endswith(".expected.json"):
        continue
    personas[f.stem] = Persona.model_validate(json.loads(f.read_text()))
print(f"[1] {len(personas)} personas validate OK")
assert len(personas) == 7

persona = personas["weekend_react_dev"]

# 2 — search + hard filter
candidates = youtube.search_many(
    ["react vite project tutorial", "react hooks crash course"], n=10
)
kept, dropped = triage.hard_filter(candidates, persona.time_budget_minutes)
print(f"[2] search {len(candidates)} candidates → hard filter kept {len(kept)}, "
      f"dropped {len(dropped)} ({[d['why'] for d in dropped][:3]})")
assert len(kept) >= 10

# 3 — deep fetch + bundles for 4
ids = [c.id for c in kept if c.duration_s and 480 < c.duration_s < 2700][:4]
infos = youtube.fetch_many(ids)
bundles = [youtube.build_content_bundle(i) for i in infos.values()]
print(f"[3] {len(bundles)} bundles; transcripts: "
      f"{[b.transcript_coverage for b in bundles]}")
assert len(bundles) >= 3

# 4 — synthetic curriculum from real bundles → curator validation
def synth_curriculum(picks_from, bad_id=False, blow_budget=False) -> Curriculum:
    picks = []
    for i, b in enumerate(picks_from, 1):
        picks.append(Pick(
            video_id="doesnotexist" if bad_id and i == 1 else b.id,
            order=i, title=b.title, url=b.url,
            watch=Watch(mode="full", minutes=9999 if blow_budget else round(b.duration_s / 60)),
            reason=f"Covers {b.chapters[0].title if b.chapters else b.title} directly.",
            covers_topics=["React basics"], confidence="medium",
            confidence_why="offline smoke",
        ))
    return Curriculum(
        picks=picks,
        dropped=[DroppedVideo(video_id="x", title="other video", reason="overlaps with pick 1")],
        budget=BudgetReport(total_minutes=0, budget_minutes=0, headroom_note="n/a"),
        plan_gaps=[], summary="Offline smoke curriculum.",
        expertise_achieved=ExpertiseAchieved(level="beginner+", justification="smoke"),
    )

ok = curator.validate(synth_curriculum(bundles[:2]), bundles, persona.time_budget_minutes)
bad1 = curator.validate(synth_curriculum(bundles[:2], bad_id=True), bundles, persona.time_budget_minutes)
bad2 = curator.validate(synth_curriculum(bundles[:2], blow_budget=True), bundles, persona.time_budget_minutes)
print(f"[4] validate: clean={ok} | fake-id violations={len(bad1)} | budget violations={len(bad2)}")
assert not ok and bad1 and bad2

# 5 — render + eval checks on the synthetic run
plan = TopicPlan(
    expertise_start="experienced engineer, React beginner",
    expertise_start_why="5y Python, knows JS fundamentals, zero React",
    expertise_target_provisional="can build a small persisted app",
    goal_already_met=False, goal_already_met_note="",
    topics=[Topic(name="React + Vite setup", why="prereq", est_minutes=45, order=1)],
    constraint_notes=[], search_queries=["react vite project tutorial"],
)
run_dir = Path("outputs/_smoke")
trace = {
    "hard_filtered": dropped,
    "triage_scores": [],
    "finalist_ids": [b.id for b in bundles],
    "candidates": [c.model_dump() for c in candidates],
    "recency_notes": "",
}
render.write_run(run_dir, persona, plan, synth_curriculum(bundles[:2]), trace,
                 {"stage_seconds": {}, "total_seconds": 0, "llm_calls": [], "total_cost_usd": 0})
md = (run_dir / "curriculum.md").read_text()
assert "Expertise trajectory" in md and "Considered but dropped" in md
checks = run_checks(run_dir, {"expect_refusal": False,
                              "forbidden_title_patterns": ["in 100 seconds"],
                              "required_topic_terms": ["react"]},
                    persona.model_dump())
for c in checks:
    print(f"    [{'PASS' if c['pass'] else 'FAIL'}] {c['name']} {c['detail'] or ''}")
assert all(c["pass"] for c in checks), "synthetic run should pass all checks"

# 6 — refusal path artifacts + checks
from curriculum_agent.schemas import Refusal
refusal_dir = Path("outputs/_smoke_refusal")
render.write_refusal(refusal_dir, Refusal(persona_id="explosives_blocked",
                                          category="weapons", reason="harm capability"),
                     {"stage_seconds": {}, "total_seconds": 0, "llm_calls": [], "total_cost_usd": 0})
rc = run_checks(refusal_dir, {"expect_refusal": True}, personas["explosives_blocked"].model_dump())
assert all(c["pass"] for c in rc), rc
print(f"[6] refusal path checks pass ({len(rc)} checks)")

print("\nOFFLINE SMOKE OK")
