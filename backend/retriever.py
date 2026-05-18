from config import CHROMA_DB_DIR
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

def retrieval(query: str):
    print(f"Searching codebase for: '{query}'\n")
    embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')
    db = Chroma(
        persist_directory=CHROMA_DB_DIR,
        embedding_function=embeddings
    )
    retriever = db.as_retriever(search_kwargs={"k":1})
    docs = retriever.invoke(query)
    if docs:
        for i, doc in enumerate(docs, 1):
            print(f"Result {i} | Source: {doc.metadata.get('source', 'Unknown')}")
            print("-" * 40)
            print(doc.page_content.strip())
    else:
        print("No result found.")
    print(docs)

if __name__ == "__main__":
    retrieval("Where is the addition math handled!")
