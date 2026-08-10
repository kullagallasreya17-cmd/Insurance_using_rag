from typing import List

from langchain_core.documents import Document


class HybridRetrievalResult:
    def __init__(self, documents: List[Document], scores: List[float]):
        self.documents = documents
        self.scores = scores


class HybridRetriever:
    def __init__(self, vector_retriever, bm25_retriever=None):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever

    def retrieve(self, query: str, k: int = 6, category: str | None = None) -> HybridRetrievalResult:
        vector_docs = self.vector_retriever(query, k=k, category=category)
        documents = [doc for doc in vector_docs]
        scores = [1.0 for _ in documents]

        if self.bm25_retriever is not None:
            bm25_docs = self.bm25_retriever(query, k=k, category=category)
            for doc in bm25_docs:
                if doc not in documents:
                    documents.append(doc)
                    scores.append(0.8)

        return HybridRetrievalResult(documents=documents[:k], scores=scores[:k])
