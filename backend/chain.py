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


def extract_input(payload: dict[str, str]) -> str:
    return payload["input"]


def get_llm():
    print("Using Amazon Bedrock (Meta Llama 3)")
    return ChatBedrock(
        model="meta.llama3-8b-instruct-v1:0",
        model_kwargs={"temperature":0.0},
        streaming=True
    )
        

def build_rag_chain():
    embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')
    db = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=embeddings)
    retriever = db.as_retriever(search_kwargs={'k': 3})

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

    extract_query = RunnableLambda(extract_input)

    return (
        {
            "context": extract_query | retriever | RunnableLambda(format_documents),
            "input": extract_query,
        }
        | prompt
        | llm
        | StrOutputParser()
    )


def get_answer(query: str) -> str:
    print(f"Thinking about: '{query}'...")
    return build_rag_chain().invoke({"input": query})

@traceable
def stream_answer(query: str):
    for chunk in build_rag_chain().stream({"input": query}):
        yield chunk


if __name__ == "__main__":
    answer = get_answer("Explain what the math_funcs.py file does.")
    print("\nAI Response:\n")
    print(answer)