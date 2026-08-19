import logging
import time

from agents.retriever_agent import RetrievalAgent
from claim_engine import build_document_citations, estimate_confidence_from_retrieval_scores
from rag.cache import cache
from rag.generator import generate_answer
from rag.query_router import QueryRoute, classify_query
from rag.web_search import format_web_context, web_search


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

        route = classify_query(question)
        retrieval_started = time.perf_counter()
        documents = []
        if route in {QueryRoute.POLICY_ONLY, QueryRoute.POLICY_AND_WEB}:
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
                    "route": route.value,
                    "web_search_used": False,
                    "web_sources": [],
                    "error": str(exc),
                }

        retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
        web_result = {"ok": True, "results": [], "provider": None, "error": None}
        if route in {QueryRoute.WEB_ONLY, QueryRoute.POLICY_AND_WEB}:
            web_result = web_search(question)

        generation_started = time.perf_counter()
        answer = generate_answer(
            question,
            documents,
            external_context=(
                format_web_context(web_result.get("results", []))
                if web_result.get("results")
                else ""
            ),
            route=route.value,
        )
        generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)

        citations = build_document_citations(documents)
        confidence = "medium" if documents or web_result.get("results") else "low"
        if documents:
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
            "sources": citations,
            "citations": citations,
            "confidence": confidence,
            "route": route.value,
            "web_search_used": route in {QueryRoute.WEB_ONLY, QueryRoute.POLICY_AND_WEB},
            "web_search_ok": web_result.get("ok", False),
            "web_search_error": web_result.get("error"),
            "web_provider": web_result.get("provider"),
            "web_sources": web_result.get("results", []),
        }
        cache.set(question, result)
        return result
