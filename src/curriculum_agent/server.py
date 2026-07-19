"""Web UI + JSON API over the pipeline. One FastAPI app, in-memory job registry.

Endpoints:
  GET  /                    the single-page UI (static/index.html)
  POST /api/suggest         one fast-model call -> suggested known/unknown concepts
  POST /api/curriculum      validate persona -> run pipeline in a thread -> {run_id}
  GET  /api/runs/{run_id}   poll: {status, stage, result?, error?}
"""

import json
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import config, pipeline, prompts
from .llm import make_llm
from .schemas import ConceptSuggestions, Persona, UserContext

app = FastAPI(title="Learning Curriculum Builder")

_STATIC = Path(__file__).parent / "static"
_jobs: dict[str, dict] = {}  # run_id -> {status, stage, run_dir, error, created}
_jobs_lock = threading.Lock()


# --- request models ---------------------------------------------------------------

class SuggestRequest(BaseModel):
    goal: str
    background: str
    provider: str = config.DEFAULT_PROVIDER


class CurriculumRequest(BaseModel):
    goal: str
    background: str
    time_budget_minutes: int
    known: list[str] = []
    unknown: list[str] = []
    constraints: str = ""
    provider: str = config.DEFAULT_PROVIDER
    transcripts: bool = config.FETCH_TRANSCRIPTS


# --- routes -----------------------------------------------------------------------

@app.get("/")
def index() -> HTMLResponse:
    html = (_STATIC / "index.html").read_text()
    return HTMLResponse(html.replace("{{default_provider}}", config.DEFAULT_PROVIDER))


@app.post("/api/suggest")
def suggest(req: SuggestRequest) -> dict:
    if not req.goal.strip():
        raise HTTPException(400, "goal is required for suggestions")
    llm = make_llm(req.provider)
    result: ConceptSuggestions = llm.parse(
        stage="suggest",
        model=llm.model_fast,
        system=prompts.SUGGEST_SYSTEM,
        user=f"Goal: {req.goal}\nBackground: {req.background or 'not given'}",
        output_model=ConceptSuggestions,
        max_tokens=1024,
    )
    return result.model_dump()


@app.post("/api/curriculum")
def create_curriculum(req: CurriculumRequest) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "_", req.goal.lower()).strip("_")[:40] or "curriculum"
    run_id = f"{slug}-{uuid.uuid4().hex[:6]}"
    try:
        persona = Persona(
            persona_id=run_id,
            goal=req.goal,
            time_budget_minutes=req.time_budget_minutes,
            user_context=UserContext(
                background=req.background,
                known=[k for k in req.known if k.strip()],
                unknown=[u for u in req.unknown if u.strip()],
                constraints=req.constraints,
            ),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    with _jobs_lock:
        _jobs[run_id] = {"status": "running", "stage": "starting", "run_dir": None,
                         "error": None, "created": time.time()}

    def set_stage(stage: str) -> None:
        with _jobs_lock:
            _jobs[run_id]["stage"] = stage

    def work() -> None:
        try:
            run_dir = pipeline.run(persona, provider=req.provider,
                                   transcripts=req.transcripts, on_stage=set_stage)
            with _jobs_lock:
                _jobs[run_id]["run_dir"] = str(run_dir)
                _jobs[run_id]["status"] = (
                    "refused" if (run_dir / "refusal.json").exists() else "done"
                )
        except Exception as exc:  # surfaced to the poller, not swallowed
            with _jobs_lock:
                _jobs[run_id]["status"] = "error"
                _jobs[run_id]["error"] = str(exc)[:500]

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}")
def run_status(run_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(run_id)
    if job is None:
        raise HTTPException(404, "unknown run id")
    out: dict = {"status": job["status"], "stage": job["stage"], "error": job["error"]}
    if job["status"] in ("done", "refused") and job["run_dir"]:
        run_dir = Path(job["run_dir"])
        artifact = "curriculum.json" if job["status"] == "done" else "refusal.json"
        out["result"] = json.loads((run_dir / artifact).read_text())
        meta = run_dir / "run_meta.json"
        if meta.exists():
            m = json.loads(meta.read_text())
            out["cost_usd"] = m.get("total_cost_usd")
            out["seconds"] = m.get("total_seconds")
    return out
