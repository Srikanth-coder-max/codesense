from config import REPO_PATH, CHROMA_DB_DIR
from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import LanguageParser
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
import os
import glob

# Mapping of file extensions to Language enum (only supported ones)
LANGUAGE_MAP = {
    '.py': Language.PYTHON,
    '.js': Language.JS,
    '.jsx': Language.JS,
    '.ts': Language.TS,
    '.tsx': Language.TS,
    '.java': Language.JAVA,
    '.cpp': Language.CPP,
    '.c': Language.C,
    '.cs': Language.CSHARP,
    '.go': Language.GO,
    '.rs': Language.RUST,
    '.rb': Language.RUBY,
    '.php': Language.PHP,
    '.kt': Language.KOTLIN,
    '.scala': Language.SCALA,
}

# Text files to load as plain text
TEXT_EXTENSIONS = ['.md', '.txt', '.json', '.yaml', '.yml', '.xml', '.html', '.css', '.sql', '.sh', '.bash', '.dockerfile']

def build_vector_db(repo_path: str = None):
    print("Starting ingestion pipeline...")
    path = repo_path or REPO_PATH
    
    all_docs = []
    
    # Load files for each supported language
    for ext, language in LANGUAGE_MAP.items():
        try:
            print(f"Loading {ext} files...")
            loader = GenericLoader.from_filesystem(
                path=path,
                glob="**/*",
                suffixes=[ext],
                parser=LanguageParser(language=language, parser_threshold=50)
            )
            docs = loader.load()
            all_docs.extend(docs)
            print(f"  Loaded {len(docs)} chunks from {ext} files.")
        except Exception as e:
            print(f"  Warning: Could not load {ext} files: {e}")
    
    # Load text files using simple text loader
    for ext in TEXT_EXTENSIONS:
        try:
            print(f"Loading {ext} files...")
            pattern = os.path.join(path, "**/*" + ext)
            files = glob.glob(pattern, recursive=True)
            
            if files:
                for file_path in files:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if content.strip():  # Only add if file has content
                                relative_path = os.path.relpath(file_path, path)
                                doc = Document(
                                    page_content=content,
                                    metadata={'source': relative_path}
                                )
                                all_docs.append(doc)
                    except Exception as e:
                        print(f"    Could not read {file_path}: {e}")
                
                print(f"  Loaded {len([d for d in all_docs if d.metadata.get('source', '').endswith(ext)])} {ext} files.")
        except Exception as e:
            print(f"  Warning: Could not process {ext} files: {e}")
    
    total_chunks = len(all_docs)
    print(f"Loaded {total_chunks} total chunks.")
    
    if total_chunks == 0:
        print("Warning: No documents found to ingest.")
        return

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vector_store = Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        persist_directory=CHROMA_DB_DIR
    )
    print("Ingestion Complete. Chroma DB saved.")

if __name__ == "__main__":
    build_vector_db()