import json
import re

from agents.retriever_agent import RetrievalAgent
from rag.generator import generate_claim_analysis


def build_document_citations(documents):
    """Return structured citations for retrieved policy documents."""
    citations = []
    for doc in documents:
        metadata = getattr(doc, "metadata", {}) or {}
        excerpt = " ".join((getattr(doc, "page_content", "") or "").split())[:180]
        citations.append(
            {
                "source": metadata.get("source", "unknown"),
                "category": metadata.get("category", "general"),
                "document_type": metadata.get("document_type", "unknown"),
                "page": metadata.get("page_label") or metadata.get("page", "unknown"),
                "excerpt": excerpt,
            }
        )
    return citations


def parse_structured_claim_response(raw_answer):
    """Parse claim-analysis JSON from raw model output, including fenced content."""
    if raw_answer is None:
        return {}

    if isinstance(raw_answer, dict):
        return raw_answer

    candidate = str(raw_answer).strip()
    if not candidate:
        return {}

    for text in [candidate]:
        for pattern in (
            r"```\s*(?:json)?\s*(\{.*?\})\s*```",
            r"```\s*(\{.*?\})\s*```",
            r"(?:^|\s)\{.*\}(?:\s|$)",
        ):
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                candidate = match.group(1) if match.lastindex else match.group(0)
                break
        if candidate.startswith("json"):
            candidate = candidate[4:].lstrip()

        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    # Some models return JSON inside prose, or with a trailing sentence.
    json_matches = re.findall(r"\{.*\}", candidate, re.DOTALL)
    for snippet in json_matches:
        try:
            return json.loads(snippet)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    raise ValueError("The model response could not be parsed as structured JSON.")


def estimate_confidence_from_retrieval_scores(scores):
    """Translate retrieval distance/similarity scores into a meaningful confidence label."""
    if not scores:
        return "low"

    safe_scores = [float(score) for score in scores if isinstance(score, (int, float))]
    if not safe_scores:
        return "low"

    avg_score = sum(safe_scores) / len(safe_scores)

    if avg_score <= 0.2:
        return "high"
    if avg_score <= 0.7:
        return "medium"
    return "low"


def analyze_claim(question: str, claim_amount: float | None = None, policy_category: str | None = None):
    retriever = RetrievalAgent()
    documents = retriever.retrieve(question, category=policy_category)
    retrieval_results = retriever.retrieve_with_scores(question, category=policy_category)
    retrieval_scores = [score for _doc, score in retrieval_results]
    raw_answer = generate_claim_analysis(question, documents, claim_amount, policy_category)

    try:
        parsed = parse_structured_claim_response(raw_answer)
    except (ValueError, TypeError, AttributeError):
        parsed = {
            "decision": "needs_review",
            "confidence": "medium",
            "rationale": raw_answer or "The model response could not be parsed as structured JSON.",
            "covered_items": [],
            "exclusions": [],
            "missing_information": ["The model response could not be parsed as structured JSON."],
            "next_steps": ["Review the retrieved policy context manually."],
        }

    parsed.setdefault("decision", "needs_review")
    parsed.setdefault("rationale", "")
    parsed.setdefault("covered_items", [])
    parsed.setdefault("exclusions", [])
    parsed.setdefault("missing_information", [])
    parsed.setdefault("next_steps", [])

    confidence = estimate_confidence_from_retrieval_scores(retrieval_scores)
    parsed["confidence"] = confidence

    if parsed.get("decision") not in {"approved", "rejected", "needs_review"}:
        parsed["decision"] = "needs_review"

    parsed["sources"] = build_document_citations(documents)
    parsed["citations"] = parsed["sources"]
    parsed["explanation_trail"] = parsed.get("next_steps") or []
    parsed["escalation_required"] = parsed.get("decision") == "needs_review" or confidence == "low"
    if parsed.get("decision") == "needs_review" and not any(
        "escalate" in str(step).lower() or "human" in str(step).lower() for step in parsed.get("next_steps", [])
    ):
        parsed["next_steps"] = list(parsed.get("next_steps", [])) + [
            "Escalate this claim to a human underwriter or claims specialist for manual review."
        ]
    return parsed
