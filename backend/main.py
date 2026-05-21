from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from langsmith import traceable
from git import Repo
import json
import os
import tempfile
import shutil
import subprocess

from chain import stream_answer
from ingest import build_vector_db

# ---------------------------------------------------------------------------
# Temporary directory for git clones.
# Matches the directory created & chown'd in the Dockerfile.
# The ENV TMPDIR=/app/temp set in the Dockerfile also covers third-party libs.
# ---------------------------------------------------------------------------
APP_TEMP_DIR = "/app/temp"
os.makedirs(APP_TEMP_DIR, exist_ok=True)  # no-op if already exists

# Belt-and-suspenders: ensure git trusts any directory it encounters at runtime.
# (The Dockerfile already sets this for the build user; this covers the runtime user.)
try:
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", "*"],
        check=True, capture_output=True
    )
except Exception:
    pass  # non-fatal; git may still work fine

app = FastAPI(title='CodeSense API')

# ---------------------------------------------------------------------------
# CORS — allow:
#   • Your canonical Vercel deployment
#   • Any Vercel preview URL  (feature-branch / PR deploys)
#   • Local development
# ---------------------------------------------------------------------------
CORS_ORIGINS = [
    "https://codesense-beta.vercel.app",  # canonical production URL
    "https://codesense-beta-git-main-srikanthbabu.vercel.app",  # common git-branch URL
    "http://localhost:3000",              # local CRA dev server
    "http://localhost:5173",              # local Vite dev server (if ever used)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://codesense.*\.vercel\.app",  # catches ALL preview URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

class RepoRequest(BaseModel):
    github_url: str

def event_stream(query: str):
    for chunk in stream_answer(query):
        payload = json.dumps({"token": chunk})
        yield f"data: {payload}\n\n"
    yield "data: [DONE]\n\n"

@app.post('/api/ask')
@traceable
def ask_question(request: QueryRequest):
    print(f"API received query: {request.query}")
    return StreamingResponse(
        event_stream(request.query),
        media_type='text/event-stream',
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

@app.get("/health")
def health_check():
    """Simple liveness probe — useful for EC2 health checks and debugging."""
    return {"status": "ok"}


@app.post('/api/ingest')
async def ingest_repo(request: RepoRequest):
    print(f"API received repository URL: {request.github_url}")
    # Explicitly use APP_TEMP_DIR so git clone never touches the root-owned /tmp.
    temp_dir = tempfile.mkdtemp(dir=APP_TEMP_DIR)
    try:
        print(f"Cloning {request.github_url} -> {temp_dir}")
        Repo.clone_from(
            request.github_url,
            temp_dir,
            depth=1,
            single_branch=True,
        )
        print("Cloning complete. Building vector database...")
        build_vector_db(repo_path=temp_dir)
        return {"message": "Repository ingested successfully."}
    except Exception as e:
        import traceback
        print(f"Error during ingestion: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        # Always clean up, even on error, to avoid filling the disk.
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"Temporary directory {temp_dir} cleaned up.")
