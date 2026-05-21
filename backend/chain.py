import os
from dotenv import load_dotenv
from config import CHROMA_DB_DIR
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_aws import ChatBedrock
from langsmith import traceable

load_dotenv()


def format_documents(documents):
    formatted = []
    for doc in documents:
        source = (
            doc.metadata.get('source')
            or doc.metadata.get('file_path')
            or 'Unknown source'
        )
        formatted.append(f"Source File: {source}\nCode:\n{doc.page_content}")
    return "\n\n".join(formatted)


def get_llm():
    print("Using Amazon Bedrock (Meta Llama 3)")
    return ChatBedrock(
        model="meta.llama3-8b-instruct-v1:0",
        model_kwargs={"temperature":0.0},
        streaming=True
    )

@traceable
def stream_answer(query: str):
    print(f"Thinking about: '{query}'...")
    
    embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')
    db = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=embeddings)
    retriever = db.as_retriever(search_kwargs={'k': 3})
    
    # 1. Manually retrieve documents first
    docs = retriever.invoke(query)
    print(f"DEBUG: Retrieved {len(docs)} documents")
    
    # 2. Handle empty context
    if len(docs) == 0:
        yield "No relevant code found in the repository. Try a different question."
        return
        
    # 3. Build generator chain
    llm = get_llm()
    system_prompt = (
        "You are an expert AI software engineer. Use the following pieces of "
        "retrieved context to answer the user's question about the codebase.\n\n"
        "Context:\n{context}\n\n"
        "If you don't know the answer, say that you don't know."
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}")
    ])
    
    chain = prompt | llm | StrOutputParser()
    
    # 4. Stream output
    context_str = format_documents(docs)
    for chunk in chain.stream({"context": context_str, "input": query}):
        yield chunk

def get_answer(query: str) -> str:
    """Non-streaming version for testing"""
    chunks = list(stream_answer(query))
    return "".join(chunks)

if __name__ == "__main__":
    answer = get_answer("Explain what the math_funcs.py file does.")
    print("\nAI Response:\n")
    print(answer)