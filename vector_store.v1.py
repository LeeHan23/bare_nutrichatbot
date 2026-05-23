import os
from typing import List
from dotenv import load_dotenv
from langchain_community.vectorstores import PGVector
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from embeddings import get_embedding_function

load_dotenv()

PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
)


def get_connection_string() -> str:
    url = PGVECTOR_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


class MergedRetriever(BaseRetriever):
    """Combines results from multiple retrievers, deduplicating by page_content."""

    retrievers: List[BaseRetriever]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        seen = set()
        results = []
        for retriever in self.retrievers:
            for doc in retriever.invoke(query):
                if doc.page_content not in seen:
                    seen.add(doc.page_content)
                    results.append(doc)
        return results


def get_retriever(client_id: str) -> BaseRetriever:
    """
    Returns a hybrid retriever combining the shared base knowledge collection
    and the client-specific collection from pgvector.
    """
    connection_string = get_connection_string()
    embedding_function = get_embedding_function()

    base_db = PGVector(
        connection_string=connection_string,
        embedding_function=embedding_function,
        collection_name="base_knowledge",
        use_jsonb=True,
    )
    base_retriever = base_db.as_retriever(search_kwargs={"k": 5})

    client_db = PGVector(
        connection_string=connection_string,
        embedding_function=embedding_function,
        collection_name=f"client_{client_id}_knowledge",
        use_jsonb=True,
    )
    client_retriever = client_db.as_retriever(search_kwargs={"k": 5})

    print(f"[VectorStore] Using hybrid retriever for client_id: {client_id}")
    return MergedRetriever(retrievers=[base_retriever, client_retriever])
