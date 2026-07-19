"""Meta-eval: prove the deterministic checks actually catch what they claim to catch.

Takes the newest real run in outputs/, applies one deliberate fault per mutation, and
asserts the targeted check FAILS (and passed on the unmutated baseline). Zero LLM cost.
Run via: uv run curriculum eval --selftest
"""

import copy
import json
import shutil
import tempfile
from pathlib import Path

from curriculum_agent import config

from eval.checks import run_checks

_FAKE_ID = "zzselftest0"


def _newest_run() -> Path:
    runs = sorted(
        (p.parent for p in config.OUTPUT_DIR.glob("*/curriculum.json")),
        key=lambda p: (p / "curriculum.json").stat().st_mtime,
    )
    if not runs:
        raise SystemExit("selftest needs at least one completed run in outputs/")
    return runs[-1]


# Each mutation: (name, target_check, fn(data, trace) -> None), mutating in place.

def _hallucinated(data, trace):
    data["curriculum"]["picks"][0]["video_id"] = _FAKE_ID + "x"


def _budget_blown(data, trace):
    data["curriculum"]["picks"][0]["watch"]["minutes"] += \
        data["persona"]["time_budget_minutes"] * 2


def _duplicate(data, trace):
    dup = copy.deepcopy(data["curriculum"]["picks"][0])
    dup["order"] = len(data["curriculum"]["picks"]) + 1
    data["curriculum"]["picks"].append(dup)


def _fabricated_reason(data, trace):
    data["curriculum"]["picks"][0]["reason"] = \
        "flibbertigibbet quixotic zamboni harpsichord perambulate"


def _constraint_violation(data, trace):
    data["topic_plan"]["constraint_notes"].append({
        "source_text": "selftest", "kind": "exclude_title_pattern",
        "instruction": "exclude videos whose title contains 'in 100 seconds'",
    })
    data["curriculum"]["picks"][0]["title"] = "Learn It All in 100 Seconds"


def _gap_contradiction(data, trace):
    covered = data["curriculum"]["picks"][0]["covers_topics"][0]
    data["curriculum"]["plan_gaps"] = [covered]


def _weak_engagement(data, trace):
    # fake finalist with 50 views / 0 likes; in the candidate pool so only the
    # engagement check (not hallucination) fires
    data["curriculum"]["picks"][0]["video_id"] = _FAKE_ID
    trace["candidates"].append({"id": _FAKE_ID, "title": "obscure video",
                                "url": "https://youtube.com/watch?v=" + _FAKE_ID})


_MUTATIONS = [
    ("hallucinated_pick", "no_hallucinated_videos", _hallucinated),
    ("budget_blown", "within_budget", _budget_blown),
    ("duplicate_pick", "no_duplicate_picks", _duplicate),
    ("fabricated_reason", "reasons_reference_content", _fabricated_reason),
    ("constraint_violation", "plan_constraints_honored", _constraint_violation),
    ("gap_contradiction", "coverage_gaps_consistent", _gap_contradiction),
    ("weak_engagement", "engagement_floor", _weak_engagement),
]


def run_selftest() -> bool:
    src = _newest_run()
    persona = json.loads((src / "curriculum.json").read_text())["persona"]
    print(f"selftest against: {src.name}")

    # baseline: every targeted check must pass on the real artifact
    baseline = {c["name"]: c["pass"] for c in run_checks(src, {}, persona)}
    for _, target, _fn in _MUTATIONS:
        if not baseline.get(target, False):
            print(f"  [SKIP-RISK] baseline already fails '{target}' — fix the run first")
            return False

    fake_cache = config.CACHE_DIR / "videos" / f"{_FAKE_ID}.json"
    fake_cache.parent.mkdir(parents=True, exist_ok=True)
    fake_cache.write_text(json.dumps({"id": _FAKE_ID, "title": "obscure video",
                                      "view_count": 50, "like_count": 0}))
    ok = True
    try:
        for name, target, mutate in _MUTATIONS:
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / src.name
                shutil.copytree(src, run_dir)
                data = json.loads((run_dir / "curriculum.json").read_text())
                trace = json.loads((run_dir / "candidates.json").read_text())
                mutate(data, trace)
                (run_dir / "curriculum.json").write_text(json.dumps(data))
                (run_dir / "candidates.json").write_text(json.dumps(trace))
                failed = {c["name"] for c in run_checks(run_dir, {}, persona)
                          if not c["pass"]}
                caught = target in failed
                ok &= caught
                print(f"  [{'CAUGHT' if caught else 'MISSED'}] {name} -> {target}")
    finally:
        fake_cache.unlink(missing_ok=True)

    print("SELFTEST", "PASS — every seeded fault was caught" if ok else "FAIL")
    return ok
