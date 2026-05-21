from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from langsmith import traceable
from git import Repo
import json
import os
import uuid
import tempfile
import shutil
import subprocess
import threading
from typing import Dict
from enum import Enum

from chain import stream_answer
from ingest import build_vector_db


# ---------------------------------------------------------------------------
# Temporary directory for git clones.
# ---------------------------------------------------------------------------
APP_TEMP_DIR = "/app/temp"
os.makedirs(APP_TEMP_DIR, exist_ok=True)

# Belt-and-suspenders: ensure git trusts any directory it encounters at runtime.
try:
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", "*"],
        check=True, capture_output=True
    )
except Exception:
    pass

app = FastAPI(title='CodeSense API')

# ---------------------------------------------------------------------------
# CORS — allow:
#   • Your canonical Vercel deployment
#   • Any Vercel preview URL  (feature-branch / PR deploys)
#   • Local development
# ---------------------------------------------------------------------------
CORS_ORIGINS = [
    "https://codesense-beta.vercel.app",
    "https://codesense-beta-git-main-srikanthbabu.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://codesense.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory job store.
# Tracks the status of every async ingestion job by job_id (UUID).
# In a multi-replica setup you'd replace this with Redis, but for a single
# EC2 container this is perfectly reliable.
# ---------------------------------------------------------------------------
class JobStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"

# { job_id: { "status": JobStatus, "detail": str } }
jobs: Dict[str, dict] = {}


class QueryRequest(BaseModel):
    query: str

class RepoRequest(BaseModel):
    github_url: str


# ---------------------------------------------------------------------------
# Background worker — runs the full clone + embed pipeline in a thread.
# ---------------------------------------------------------------------------
def _run_ingestion(job_id: str, github_url: str):
    """Called in a daemon thread. Updates jobs[job_id] as it progresses."""
    temp_dir = tempfile.mkdtemp(dir=APP_TEMP_DIR)
    try:
        jobs[job_id]["status"] = JobStatus.RUNNING
        print(f"[job:{job_id}] Cloning {github_url} -> {temp_dir}")
        Repo.clone_from(github_url, temp_dir, depth=1, single_branch=True)

        print(f"[job:{job_id}] Clone complete. Building vector DB...")
        build_vector_db(repo_path=temp_dir)

        jobs[job_id]["status"] = JobStatus.COMPLETE
        jobs[job_id]["detail"] = "Repository ingested successfully."
        print(f"[job:{job_id}] Done.")

    except Exception as e:
        import traceback
        jobs[job_id]["status"] = JobStatus.FAILED
        jobs[job_id]["detail"] = str(e)
        print(f"[job:{job_id}] FAILED: {e}")
        traceback.print_exc()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[job:{job_id}] Temp dir {temp_dir} cleaned up.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    """Liveness probe — used by EC2/ALB health checks and the frontend."""
    return {"status": "ok"}


@app.post("/api/ask")
@traceable
def ask_question(request: QueryRequest):
    print(f"API received query: {request.query}")
    return StreamingResponse(
        event_stream(request.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/ingest", status_code=202)
async def ingest_repo(request: RepoRequest):
    """
    Accepts a GitHub URL, starts ingestion in a background thread,
    and immediately returns HTTP 202 Accepted with a job_id.

    The client polls GET /api/ingest/status/{job_id} to track progress.
    This avoids Vercel's 10-second proxy timeout entirely.
    """
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": JobStatus.PENDING, "detail": ""}

    thread = threading.Thread(
        target=_run_ingestion,
        args=(job_id, request.github_url),
        daemon=True,          # dies with the process; no orphaned threads
        name=f"ingest-{job_id[:8]}"
    )
    thread.start()

    print(f"[job:{job_id}] Accepted ingest for {request.github_url}")
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/ingest/status/{job_id}")
async def ingest_status(job_id: str):
    """
    Poll this endpoint to check the status of an async ingest job.

    Returns:
        status: "pending" | "running" | "complete" | "failed"
        detail: error message (only when status == "failed")
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"job_id": job_id, "status": job["status"], "detail": job["detail"]}


def event_stream(query: str):
    for chunk in stream_answer(query):
        payload = json.dumps({"token": chunk})
        yield f"data: {payload}\n\n"
    yield "data: [DONE]\n\n"
