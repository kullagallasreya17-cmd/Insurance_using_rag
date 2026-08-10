from rag.retrieval_strategy import HybridRetriever
from rag.retriever import retrieve_documents, retrieve_documents_with_scores


class RetrievalAgent:
    """
    Retrieval Agent

    Responsibilities:
    - Receive the user query
    - Search the Vector Database
    - Return the relevant documents
    """

    def __init__(self):
        self.hybrid_retriever = HybridRetriever(
            vector_retriever=lambda query, k=6, category=None: retrieve_documents(query, category=category)[:k],
            bm25_retriever=lambda query, k=6, category=None: retrieve_documents(query, category=category)[:k],
        )

    def _infer_category_from_query(self, query: str) -> str | None:
        normalized = (query or "").lower()
        if "insurance_faq" in normalized or "faq" in normalized:
            return "faq"
        if "claim procedure" in normalized or "claim_procedure" in normalized:
            return "claim_procedure"
        if "health policy" in normalized or "health_policy" in normalized:
            return "health_policy"
        if "vehicle policy" in normalized or "vehicle_policy" in normalized:
            return "vehicle_policy"
        if "life policy" in normalized or "life_policy" in normalized:
            return "life_policy"
        return None

    def retrieve(self, query: str, category: str | None = None):
        effective_category = category or self._infer_category_from_query(query)

        print("\n========== Retrieval Agent ==========")
        print(f"Searching for: {query}")
        if effective_category:
            print(f"Category filter: {effective_category}")

        documents = self.hybrid_retriever.retrieve(query, k=6, category=effective_category).documents

        print(f"{len(documents)} documents retrieved.\n")

        return documents

    def retrieve_with_scores(self, query: str, category: str | None = None):
        effective_category = category or self._infer_category_from_query(query)
        result = retrieve_documents_with_scores(query, category=effective_category)
        print(f"{len(result)} documents retrieved with scores.\n")
        return result