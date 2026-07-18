"""Eval runner: pipeline over test_set/ -> deterministic checks -> LLM judge -> report."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from curriculum_agent import config, pipeline
from curriculum_agent.llm import make_llm
from curriculum_agent.schemas import Persona

from eval.checks import run_checks
from eval.judge import judge_run

JUDGE_DIMS = [
    "relevance_to_goal", "level_fit", "ordering_logic", "constraint_satisfaction",
    "reason_groundedness", "selection_quality", "expertise_claim_grounded",
]


def _load_test_set(persona_ids: list[str] | None) -> list[tuple[Persona, dict]]:
    items = []
    for f in sorted(config.TEST_SET_DIR.glob("*.json")):
        if f.name.endswith(".expected.json"):
            continue
        persona = Persona.model_validate(json.loads(f.read_text()))
        if persona_ids and persona.persona_id not in persona_ids:
            continue
        expected_file = f.with_name(f.stem + ".expected.json")
        expected = json.loads(expected_file.read_text()) if expected_file.exists() else {}
        items.append((persona, expected))
    return items


def run_eval(persona_ids: list[str] | None = None, skip_run: bool = False,
             use_judge: bool = True, provider: str = config.DEFAULT_PROVIDER) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = config.EVAL_RESULTS_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    judge_llm = make_llm(provider) if use_judge else None

    rows = []
    for persona, expected in _load_test_set(persona_ids):
        pid = persona.persona_id
        print(f"\n=== {pid} ===")
        run_dir = config.OUTPUT_DIR / pid
        result: dict = {"persona": pid}

        if not skip_run:
            t0 = time.perf_counter()
            try:
                pipeline.run(persona, provider=provider)
                result["run_seconds"] = round(time.perf_counter() - t0, 1)
            except Exception as exc:
                result["run_error"] = str(exc)
                print(f"  PIPELINE ERROR: {exc}")

        if "run_error" not in result:
            meta_file = run_dir / "run_meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text())
                result["cost_usd"] = meta.get("total_cost_usd")
                result["run_seconds"] = result.get("run_seconds") or meta.get("total_seconds")
            checks = run_checks(run_dir, expected, persona.model_dump())
            result["checks"] = checks
            result["checks_passed"] = sum(c["pass"] for c in checks)
            result["checks_total"] = len(checks)
            for c in checks:
                mark = "PASS" if c["pass"] else "FAIL"
                print(f"  [{mark}] {c['name']}" + (f" — {c['detail']}" if c["detail"] and not c["pass"] else ""))
            if use_judge:
                scores = judge_run(judge_llm, run_dir)
                if scores is not None:
                    result["judge"] = scores.model_dump()
                    avg = sum(getattr(scores, d).score for d in JUDGE_DIMS) / len(JUDGE_DIMS)
                    result["judge_avg"] = round(avg, 2)
                    print(f"  judge avg: {result['judge_avg']}/5")

        (out_dir / f"{pid}.json").write_text(json.dumps(result, indent=2))
        rows.append(result)

    report = _summary_md(rows, stamp)
    (out_dir / "summary.md").write_text(report)
    print(f"\n{report}\nreport → {out_dir}")
    return out_dir


def _summary_md(rows: list[dict], stamp: str) -> str:
    lines = [
        f"# Eval run {stamp}",
        "",
        "| persona | checks | judge avg | cost $ | latency s | notes |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "run_error" in r:
            lines.append(f"| {r['persona']} | — | — | — | — | PIPELINE ERROR: {r['run_error'][:80]} |")
            continue
        failed = [c["name"] for c in r.get("checks", []) if not c["pass"]]
        lines.append(
            f"| {r['persona']} | {r.get('checks_passed')}/{r.get('checks_total')} "
            f"| {r.get('judge_avg', '—')} | {r.get('cost_usd', '—')} "
            f"| {r.get('run_seconds', '—')} | {('FAILED: ' + ', '.join(failed)) if failed else 'all checks pass'} |"
        )
    return "\n".join(lines)
