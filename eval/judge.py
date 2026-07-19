"""LLM judge: rubric-scores a curriculum against the finalists' actual content."""

import json
from pathlib import Path

from curriculum_agent import config, prompts, youtube
from curriculum_agent.llm import BaseLLM
from curriculum_agent.schemas import JudgeScores


def judge_run(llm: BaseLLM, run_dir: Path) -> JudgeScores | None:
    """Returns None for refusal runs (nothing to rubric-score)."""
    curriculum_path = run_dir / "curriculum.json"
    if not curriculum_path.exists():
        return None
    data = json.loads(curriculum_path.read_text())
    trace = json.loads((run_dir / "candidates.json").read_text())

    bundles = []
    for vid in trace.get("finalist_ids", []):
        cache_file = config.CACHE_DIR / "videos" / f"{vid}.json"
        if cache_file.exists():
            info = json.loads(cache_file.read_text())
            bundles.append(youtube.build_content_bundle(info).model_dump())

    user = "\n\n".join(
        [
            "Learner persona:\n" + json.dumps(data["persona"], indent=1),
            "Topic plan:\n" + json.dumps(data["topic_plan"], indent=1),
            "Finalist video bundles (ground truth of video content):\n"
            + json.dumps(bundles, indent=1),
            "Curriculum under evaluation:\n" + json.dumps(data["curriculum"], indent=1),
        ]
    )
    return llm.parse(
        stage="judge",
        model=llm.model_smart,
        system=prompts.JUDGE_SYSTEM,
        user=user,
        output_model=JudgeScores,
        max_tokens=8192,
        effort="medium",  # 7 dims + justifications; bound thinking so JSON fits
    )
