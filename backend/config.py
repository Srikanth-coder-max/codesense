import os 
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DB_DIR = os.path.join(BASE_DIR, 'backend', 'chromadb')
REPO_PATH = os.path.join(BASE_DIR, 'backend', 'sample_repo')

