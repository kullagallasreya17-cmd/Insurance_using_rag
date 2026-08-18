import logging
import time

from agents.retriever_agent import RetrievalAgent
from claim_engine import build_document_citations, estimate_confidence_from_retrieval_scores
from rag.cache import cache
from rag.generator import generate_answer


RETRIEVAL_UNAVAILABLE_ANSWER = (
    "I couldn't contact the document search index right now, so I can't safely "
    "summarize the indexed policy yet. Please make sure the backend and MongoDB "
    "vector store are running, then try again."
)


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
        try:
            documents = self.retriever.retrieve(question)
        except Exception as exc:
            retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
            logging.exception("Chat retrieval failed for question %r", question)
            return {
                "answer": RETRIEVAL_UNAVAILABLE_ANSWER,
                "retrieval_ms": retrieval_ms,
                "generation_ms": 0,
                "sources": [],
                "citations": [],
                "confidence": "low",
                "error": str(exc),
            }

        retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)

        generation_started = time.perf_counter()
        answer = generate_answer(question, documents)
        generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)

        citations = build_document_citations(documents)
        confidence = "medium" if documents else "low"
        try:
            confidence = estimate_confidence_from_retrieval_scores(
                [score for _doc, score in self.retriever.retrieve_with_scores(question)]
            )
        except Exception:
            logging.exception("Chat confidence scoring failed for question %r", question)

        result = {
            "answer": answer,
            "retrieval_ms": retrieval_ms,
            "generation_ms": generation_ms,
            "sources": [
                {
                    "source": item["source"],
                    "filename": item.get("filename"),
                    "document_name": item.get("document_name"),
                    "document_id": item.get("document_id"),
                    "category": item["category"],
                    "document_type": item["document_type"],
                    "evidence_role": item.get("evidence_role"),
                    "page": item["page"],
                    "excerpt": item["excerpt"],
                }
                for item in citations
            ],
            "citations": citations,
            "confidence": confidence,
        }
        cache.set(question, result)
        return result
