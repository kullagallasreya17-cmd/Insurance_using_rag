import time

from agents.retriever_agent import RetrievalAgent
from claim_engine import build_document_citations, estimate_confidence_from_retrieval_scores
from rag.cache import cache
from rag.generator import generate_answer


class InsuranceAgent:
    """
    Insurance AI Agent

    Workflow

    User
      ↓
    Retrieval Agent
      ↓
    Generator
      ↓
    Final Response
    """

    def __init__(self):
        self.retriever = RetrievalAgent()

    def ask(self, question: str):
        return self.ask_with_metrics(question)["answer"]

    def ask_with_metrics(self, question: str):
        cached_result = cache.get(question)
        if cached_result is not None:
            return cached_result

        print("\n==============================")
        print("Insurance AI Agent Started")
        print("==============================\n")

        retrieval_started = time.perf_counter()
        documents = self.retriever.retrieve(question)
        retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)

        generation_started = time.perf_counter()
        answer = generate_answer(question, documents)
        generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)

        citations = build_document_citations(documents)
        result = {
            "answer": answer,
            "retrieval_ms": retrieval_ms,
            "generation_ms": generation_ms,
            "sources": [
                {
                    "source": item["source"],
                    "category": item["category"],
                    "document_type": item["document_type"],
                    "page": item["page"],
                    "excerpt": item["excerpt"],
                }
                for item in citations
            ],
            "citations": citations,
            "confidence": estimate_confidence_from_retrieval_scores(
                [score for _doc, score in self.retriever.retrieve_with_scores(question)]
            ),
        }
        cache.set(question, result)
        return result