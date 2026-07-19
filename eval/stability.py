"""Stability probe: run one persona N times and measure how much the output moves.

Warm caches keep search/deep-fetch fixed, so variance isolates the LLM stages.
Measures pairwise pick-set Jaccard overlap, watch-minutes spread, and check pass-rates.
Costs N pipeline runs (~$0.03 each on gemini flash). Run via:
  uv run curriculum stability test_set/weekend_react_dev.json --runs 3
"""

import itertools
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from curriculum_agent import config, pipeline
from curriculum_agent.schemas import Persona

from eval.checks import run_checks


def run_stability(persona_path: Path, runs: int = 3,
                  provider: str = config.DEFAULT_PROVIDER) -> Path:
    persona = Persona.model_validate(json.loads(persona_path.read_text()))
    pick_sets, minutes, passes, results = [], [], [], []

    for i in range(runs):
        variant = persona.model_copy(update={"persona_id": f"{persona.persona_id}__stab{i}"})
        print(f"\n=== stability run {i + 1}/{runs} ===")
        run_dir = pipeline.run(variant, provider=provider)
        cur = json.loads((run_dir / "curriculum.json").read_text())["curriculum"]
        checks = run_checks(run_dir, {}, variant.model_dump())
        pick_sets.append({p["video_id"] for p in cur["picks"]})
        minutes.append(cur["budget"]["total_minutes"])
        passes.append(sum(c["pass"] for c in checks) / len(checks))
        results.append({"picks": sorted(pick_sets[-1]), "minutes": minutes[-1],
                        "checks_pass_rate": round(passes[-1], 2)})

    jaccards = [
        len(a & b) / len(a | b) if a | b else 1.0
        for a, b in itertools.combinations(pick_sets, 2)
    ]
    report = {
        "persona": persona.persona_id,
        "provider": provider,
        "runs": results,
        "mean_pick_jaccard": round(statistics.mean(jaccards), 2) if jaccards else None,
        "minutes_mean": round(statistics.mean(minutes), 1),
        "minutes_stdev": round(statistics.stdev(minutes), 1) if len(minutes) > 1 else 0.0,
        "min_check_pass_rate": round(min(passes), 2),
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = config.EVAL_RESULTS_DIR / f"stability-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\npick overlap (mean Jaccard): {report['mean_pick_jaccard']}"
          f" | minutes: {report['minutes_mean']}±{report['minutes_stdev']}"
          f" | worst check pass-rate: {report['min_check_pass_rate']}")
    print(f"report → {out}")
    return out
