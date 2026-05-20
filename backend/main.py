from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from langsmith import traceable
from git import Repo
import json
import tempfile
import shutil

from chain import stream_answer
from ingest import build_vector_db


app = FastAPI(title='CodeSense API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://codesense-beta.vercel.app"],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
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

@app.post('/api/ingest')
async def ingest_repo(request: RepoRequest):
    print(f"API received repository URL: {request.github_url}")
    # Force the temporary directory to be inside our permitted /app/temp folder
    temp_dir = tempfile.mkdtemp(dir="/app/temp")
    try:
        print(f"Cloning {request.github_url}")
        Repo.clone_from(
            request.github_url,
            temp_dir,
            depth=1,
            single_branch=True
        )
        print("Building vector database...")
        build_vector_db(repo_path=temp_dir)
        return {"message": "Repository ingested successfully."}
    except Exception as e:
        print(f"Error during ingestion: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("Temporary files cleaned up")
