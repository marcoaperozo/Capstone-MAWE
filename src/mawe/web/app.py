"""Minimal FastAPI front end.

Week 8.  Optional: the engine and the CLI work without it.  Its purpose is to
make a run inspectable - the specification, every version of the code and
every review are already in the database, and this exposes them.

    pip install fastapi uvicorn
    uvicorn mawe.web.app:app --reload

Runs execute synchronously. That is deliberate at this scale: a run against
the mock provider finishes in milliseconds, and a job queue would be
infrastructure the project does not need to answer its research question.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..db import Run, make_engine, session_scope
from ..engine import Engine
from ..llm import get_provider
from ..llm.base import ProviderError

app = FastAPI(
    title="MAWE",
    description="Multi-Agent AI Workflow Engine - prompt in, reviewed code out.",
    version="1.0.0",
)

_settings = Settings()
_db = make_engine(_settings.database_url)


class RunRequest(BaseModel):
    prompt: str = Field(..., min_length=3,
                        examples=["Build a terminal snake game"])
    language: str = Field("python", pattern="^(python|javascript)$")
    max_iterations: Optional[int] = Field(None, ge=1, le=20)
    provider: Optional[str] = Field(None, pattern="^(mock|anthropic|openai)$")


class RunSummary(BaseModel):
    id: int
    prompt: str
    status: str
    termination_reason: Optional[str]
    iterations: int
    total_tokens: int


class RunResponse(RunSummary):
    files: List[Dict[str, str]] = []
    acceptance_criteria: List[str] = []
    issues: List[str] = []
    warnings: List[str] = []


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "version": app.version,
            "provider": _settings.provider}


@app.post("/api/runs", response_model=RunResponse)
def create_run(request: RunRequest) -> RunResponse:
    settings = Settings()
    if request.max_iterations:
        settings.max_iterations = request.max_iterations
    try:
        provider = get_provider(request.provider)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    engine = Engine(provider=provider, settings=settings,
                    database_url=settings.database_url)
    result = engine.run(request.prompt, language=request.language)

    return RunResponse(
        id=result.run_id or 0,
        prompt=request.prompt,
        status=result.status,
        termination_reason=result.termination_reason,
        iterations=result.iterations,
        total_tokens=result.total_tokens,
        files=[{"path": f["path"], "content": f["content"]}
               for f in result.files],
        acceptance_criteria=result.acceptance_criteria,
        issues=result.issues,
        warnings=result.warnings,
    )


@app.get("/api/runs", response_model=List[RunSummary])
def list_runs(limit: int = 25) -> List[RunSummary]:
    with session_scope(_db) as session:
        rows = (session.query(Run)
                .order_by(Run.id.desc())
                .limit(max(1, min(limit, 200)))
                .all())
        return [
            RunSummary(
                id=r.id,
                prompt=(r.project.prompt if r.project else ""),
                status=r.status,
                termination_reason=r.termination_reason,
                iterations=r.iteration_count,
                total_tokens=r.total_tokens,
            )
            for r in rows
        ]


@app.get("/api/runs/{run_id}")
def get_run(run_id: int) -> Dict[str, Any]:
    with session_scope(_db) as session:
        run = session.get(Run, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"no run {run_id}")
        return {
            "id": run.id,
            "prompt": run.project.prompt if run.project else "",
            "status": run.status,
            "termination_reason": run.termination_reason,
            "iterations": run.iteration_count,
            "total_tokens": run.total_tokens,
            "specification": [
                {"version": s.version, "content": s.content,
                 "acceptance_criteria": s.acceptance_criteria}
                for s in run.specifications
            ],
            "code_artifacts": [
                {"iteration": a.iteration, "path": a.file_path,
                 "hash": a.content_hash[:12], "content": a.content}
                for a in run.code_artifacts
            ],
            "reviews": [
                {"iteration": r.iteration, "verdict": r.verdict,
                 "severity": r.severity, "tests_passed": r.tests_passed,
                 "tests_failed": r.tests_failed, "feedback": r.feedback}
                for r in run.reviews
            ],
            "memory": [
                {"from": m.from_iteration, "to": m.to_iteration,
                 "tokens_before": m.tokens_before,
                 "tokens_after": m.tokens_after}
                for m in run.memory_summaries
            ],
        }


INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MAWE</title>
<style>
  :root { --navy:#003466; --line:#d6dee6; --bg:#fbfcfd; --mono:ui-monospace,
          SFMono-Regular, Menlo, Consolas, monospace; }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.55 system-ui, -apple-system, Segoe UI, sans-serif;
         color:#14202c; background:var(--bg); }
  header { background:var(--navy); color:#fff; padding:18px 24px; }
  header h1 { margin:0; font-size:19px; letter-spacing:.2px; }
  header p { margin:4px 0 0; opacity:.8; font-size:13px; }
  main { max-width:960px; margin:0 auto; padding:24px 16px 60px; }
  form { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
  input[type=text] { flex:1 1 320px; padding:10px 12px; border:1px solid var(--line);
                     border-radius:6px; font-size:15px; }
  select, button { padding:10px 14px; border:1px solid var(--line);
                   border-radius:6px; background:#fff; font-size:15px; }
  button { background:var(--navy); color:#fff; border-color:var(--navy);
           cursor:pointer; }
  button[disabled] { opacity:.55; cursor:progress; }
  .hint { color:#5c6b7a; font-size:13px; margin:0 0 20px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:8px;
          padding:16px 18px; margin-bottom:14px; }
  .row { display:flex; gap:22px; flex-wrap:wrap; font-size:14px; }
  .row b { font-weight:600; }
  .pill { display:inline-block; padding:2px 9px; border-radius:11px;
          font-size:12px; font-weight:600; }
  .ok { background:#e3f3e8; color:#1e6f3c; }
  .warn { background:#fdf0dd; color:#a86200; }
  pre { background:#1e1e1e; color:#e6e6e6; padding:14px; border-radius:6px;
        overflow:auto; font:12.5px/1.5 var(--mono); }
  h2 { font-size:15px; margin:22px 0 10px; }
  ol { margin:0; padding-left:20px; font-size:14px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; padding:7px 9px; border-bottom:1px solid var(--line); }
  th { font-size:12px; text-transform:uppercase; letter-spacing:.4px; color:#5c6b7a; }
</style>
</head>
<body>
<header>
  <h1>MAWE &mdash; Multi-Agent AI Workflow Engine</h1>
  <p>Product Manager &rarr; Developer &rarr; Code Reviewer, looping until the
     acceptance checks pass.</p>
</header>
<main>
  <form id="f">
    <input type="text" id="prompt" placeholder="Build a terminal snake game"
           value="Build a terminal snake game" required>
    <select id="language">
      <option value="python">Python</option>
      <option value="javascript">JavaScript</option>
    </select>
    <button type="submit" id="go">Run</button>
  </form>
  <p class="hint">Uses the provider configured in <code>.env</code>
     (<code>mock</code> by default &mdash; no API key, no cost).</p>
  <div id="out"></div>
  <h2>Recent runs</h2>
  <div class="card"><table id="runs">
    <thead><tr><th>#</th><th>Prompt</th><th>Status</th><th>Exit</th>
    <th>Iters</th><th>Tokens</th></tr></thead><tbody></tbody>
  </table></div>
</main>
<script>
const esc = s => String(s).replace(/[&<>]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function refresh() {
  const rows = await (await fetch('/api/runs?limit=10')).json();
  document.querySelector('#runs tbody').innerHTML = rows.map(r =>
    `<tr><td>${r.id}</td><td>${esc(r.prompt).slice(0,52)}</td>
     <td>${esc(r.status)}</td><td>${esc(r.termination_reason || '')}</td>
     <td>${r.iterations}</td><td>${r.total_tokens.toLocaleString()}</td></tr>`
  ).join('') || '<tr><td colspan="6">No runs yet.</td></tr>';
}

document.getElementById('f').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = document.getElementById('go');
  const out = document.getElementById('out');
  btn.disabled = true; btn.textContent = 'Running…';
  out.innerHTML = '';
  try {
    const res = await fetch('/api/runs', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        prompt: document.getElementById('prompt').value,
        language: document.getElementById('language').value})});
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || 'request failed');
    const cls = d.status === 'approved' ? 'ok' : 'warn';
    out.innerHTML = `<div class="card">
      <div class="row">
        <span><b>Run</b> #${d.id}</span>
        <span><b>Status</b> <span class="pill ${cls}">${esc(d.status)}</span></span>
        <span><b>Exit</b> ${esc(d.termination_reason)}</span>
        <span><b>Iterations</b> ${d.iterations}</span>
        <span><b>Tokens</b> ${d.total_tokens.toLocaleString()}</span>
      </div>
      ${d.acceptance_criteria.length ? `<h2>Acceptance criteria</h2><ol>${
        d.acceptance_criteria.map(c => `<li>${esc(c)}</li>`).join('')}</ol>` : ''}
      ${d.warnings.length ? `<h2>Warnings</h2><ol>${
        d.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ol>` : ''}
      ${d.files.map(f => `<h2>${esc(f.path)}</h2><pre>${esc(f.content)}</pre>`).join('')}
    </div>`;
  } catch (err) {
    out.innerHTML = `<div class="card"><b>Error:</b> ${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = 'Run';
    refresh();
  }
});
refresh();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX
