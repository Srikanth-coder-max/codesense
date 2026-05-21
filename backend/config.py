import os 
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Persist Chroma DB inside the application folder so the non-root user can access it.
CHROMA_DB_DIR = os.path.join(BASE_DIR, 'chromadb')
# Default sample repo path (unused in production)
REPO_PATH = os.path.join(BASE_DIR, 'sample_repo')

