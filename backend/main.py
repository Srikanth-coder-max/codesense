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
# Persistent directory for cached git clones.
# ---------------------------------------------------------------------------
REPOS_DIR = "/app/repos"
os.makedirs(REPOS_DIR, exist_ok=True)

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
    github_url: str  # Added to identify which repo's DB to query

class RepoRequest(BaseModel):
    github_url: str


def get_collection_name(github_url: str) -> str:
    """Converts a GitHub URL into a safe collection/folder name."""
    # e.g. https://github.com/tiangolo/fastapi -> tiangolo_fastapi
    clean_url = github_url.replace("https://", "").replace("http://", "").rstrip("/")
    parts = clean_url.split("/")
    if len(parts) >= 3:
        return f"{parts[-2]}_{parts[-1]}"
    return parts[-1]


# ---------------------------------------------------------------------------
# Background worker — runs the full clone + embed pipeline in a thread.
# ---------------------------------------------------------------------------
def _run_ingestion(job_id: str, github_url: str):
    """Called in a daemon thread. Updates jobs[job_id] as it progresses."""
    try:
        jobs[job_id]["status"] = JobStatus.RUNNING
        collection_name = get_collection_name(github_url)
        repo_path = os.path.join(REPOS_DIR, collection_name)
        
        # 1. Repository Caching Logic (Pull or Clone)
        if os.path.exists(repo_path) and os.path.isdir(os.path.join(repo_path, ".git")):
            print(f"[job:{job_id}] Cache hit! Repo exists at {repo_path}. Pulling latest...")
            repo = Repo(repo_path)
            # Make sure we're on the default branch and pull
            try:
                repo.remotes.origin.pull()
                print(f"[job:{job_id}] Git pull successful.")
            except Exception as e:
                print(f"[job:{job_id}] Git pull warning (might be offline or detached): {e}")
        else:
            print(f"[job:{job_id}] Cloning {github_url} -> {repo_path}")
            Repo.clone_from(github_url, repo_path, depth=1, single_branch=True)

        # 2. Vector DB Logic (which now checks for existing index)
        print(f"[job:{job_id}] Code ready. Building vector DB...")
        build_vector_db(repo_path=repo_path, collection_name=collection_name)

        jobs[job_id]["status"] = JobStatus.COMPLETE
        jobs[job_id]["detail"] = "Repository ingested successfully."
        print(f"[job:{job_id}] Done.")

    except Exception as e:
        import traceback
        jobs[job_id]["status"] = JobStatus.FAILED
        jobs[job_id]["detail"] = str(e)
        print(f"[job:{job_id}] FAILED: {e}")
        traceback.print_exc()


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
    print(f"API received query: {request.query} for {request.github_url}")
    collection_name = get_collection_name(request.github_url)
    return StreamingResponse(
        event_stream(request.query, collection_name),
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


def event_stream(query: str, collection_name: str):
    for chunk in stream_answer(query, collection_name):
        payload = json.dumps({"token": chunk})
        yield f"data: {payload}\n\n"
    yield "data: [DONE]\n\n"
