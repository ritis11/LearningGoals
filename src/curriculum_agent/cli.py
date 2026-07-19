"""CLI entrypoint: `curriculum run <persona.json>` and `curriculum eval`."""

import argparse
import json
import sys
from pathlib import Path

from . import config, pipeline
from .schemas import Persona


def main() -> None:
    parser = argparse.ArgumentParser(prog="curriculum", description="Learning Curriculum Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="build a curriculum for one persona JSON")
    p_run.add_argument("persona", type=Path, help="path to persona JSON")
    p_run.add_argument("--no-cache", action="store_true", help="bypass YouTube disk cache")
    p_run.add_argument("--provider", choices=["anthropic", "gemini"],
                       default=config.DEFAULT_PROVIDER,
                       help="LLM provider (default: $CURRICULUM_PROVIDER or anthropic)")
    p_run.add_argument("--transcripts", action="store_true",
                       help="also download subtitle text for finalists (rate-limited "
                            "by YouTube; chapters/descriptions are used regardless)")
    p_run.add_argument("--output-dir", type=Path, default=None)

    p_serve = sub.add_parser("serve", help="start the web UI + API")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--host", default="127.0.0.1")

    p_eval = sub.add_parser("eval", help="run the evaluation harness over test_set/")
    p_eval.add_argument("--personas", nargs="*", default=None, help="subset of persona ids")
    p_eval.add_argument("--skip-run", action="store_true",
                        help="evaluate existing outputs/ without re-running the pipeline")
    p_eval.add_argument("--no-judge", action="store_true",
                        help="deterministic checks only (no LLM judge)")
    p_eval.add_argument("--provider", choices=["anthropic", "gemini"],
                        default=config.DEFAULT_PROVIDER,
                        help="LLM provider (default: $CURRICULUM_PROVIDER or anthropic)")
    p_eval.add_argument("--judge-provider", choices=["anthropic", "gemini"], default=None,
                        help="judge with a different provider than the curator "
                             "(mitigates shared blind spots)")
    p_eval.add_argument("--selftest", action="store_true",
                        help="meta-eval: seed faults into a real run and assert every "
                             "check catches its fault (no LLM cost)")

    p_stab = sub.add_parser("stability",
                            help="run one persona N times; measure output variance")
    p_stab.add_argument("persona", type=Path)
    p_stab.add_argument("--runs", type=int, default=3)
    p_stab.add_argument("--provider", choices=["anthropic", "gemini"],
                        default=config.DEFAULT_PROVIDER)

    args = parser.parse_args()

    if args.command == "run":
        try:
            persona = Persona.model_validate(json.loads(args.persona.read_text()))
        except Exception as exc:
            sys.exit(f"invalid persona file: {exc}")
        print(f"building curriculum for '{persona.persona_id}' "
              f"(budget {persona.time_budget_minutes} min)")
        pipeline.run(persona, use_cache=not args.no_cache, output_root=args.output_dir,
                     provider=args.provider, transcripts=args.transcripts)

    elif args.command == "serve":
        import uvicorn

        from .server import app
        print(f"Web UI: http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")

    elif args.command == "eval":
        # imported lazily: eval/ ships alongside src/ but isn't part of the package
        sys.path.insert(0, str(config.ROOT))
        if args.selftest:
            from eval.selftest import run_selftest
            sys.exit(0 if run_selftest() else 1)
        from eval.run_eval import run_eval

        run_eval(persona_ids=args.personas, skip_run=args.skip_run,
                 use_judge=not args.no_judge, provider=args.provider,
                 judge_provider=args.judge_provider)

    elif args.command == "stability":
        sys.path.insert(0, str(config.ROOT))
        from eval.stability import run_stability

        run_stability(args.persona, runs=args.runs, provider=args.provider)


if __name__ == "__main__":
    main()
