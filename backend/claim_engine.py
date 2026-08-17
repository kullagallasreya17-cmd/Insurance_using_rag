import json
import re
from datetime import datetime
from typing import Optional

from agents.retriever_agent import RetrievalAgent
from rag.generator import generate_claim_analysis


def _parse_number(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text.replace(",", ""))
    if match:
        try:
            return float(match.group(1))
        except Exception:
            return None
    return None


def _load_hospital_networks():
    try:
        with open("backend/hospital_networks.json", "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


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

    # Deduplicate citations while preserving first-occurrence order.
    # Use (source, page) as a stable key so identical document/page pairs
    # are shown only once even if multiple chunks were retrieved.
    seen = set()
    unique_citations = []
    for c in citations:
        key = (c.get("source"), c.get("page"))
        if key not in seen:
            seen.add(key)
            unique_citations.append(c)

    return unique_citations


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

    if avg_score >= 0.45:
        return "high"
    if avg_score >= 0.25:
        return "medium"
    return "low"


def analyze_claim(question: str, claim_amount: float | None = None, policy_category: str | None = None):
    retriever = RetrievalAgent()
    documents = retriever.retrieve(question, category=policy_category)
    retrieval_results = retriever.retrieve_with_scores(question, category=policy_category)
    retrieval_scores = [score for _doc, score in retrieval_results]
    # If the client provided an admission_date in the question text (or structured input),
    # the generator can include it in the analysis. For now we attempt to extract an ISO date token.
    admission_date = None
    # naive ISO date extraction
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(question))
    if m:
        admission_date = m.group(1)

    raw_answer = generate_claim_analysis(question, documents, claim_amount, policy_category, admission_date=admission_date)

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

    # Ensure dates and waiting-period info exist as keys
    policy_start = parsed.get("policy_start_date")
    admission = parsed.get("admission_date")
    waiting_months = parsed.get("waiting_period_months")

    # Compute waiting-period days and eligibility if we have dates
    parsed["waiting_period_days"] = None
    parsed["waiting_period_eligible"] = None
    try:
        if policy_start and admission:
            dt_policy = datetime.fromisoformat(str(policy_start))
            dt_adm = datetime.fromisoformat(str(admission))
            delta = (dt_adm - dt_policy).days
            parsed["waiting_period_days"] = int(delta)
            if waiting_months is not None:
                try:
                    wm = int(waiting_months)
                    parsed["waiting_period_eligible"] = delta >= (wm * 30)
                    if not parsed["waiting_period_eligible"]:
                        parsed.setdefault("missing_information", []).append(
                            f"Admission date is within the policy waiting period ({waiting_months} months)."
                        )
                except Exception:
                    pass
    except Exception:
        pass

    # Financial breakdown: try to parse numeric values returned by LLM or provided inputs
    parsed.setdefault("coverage_limit", None)
    parsed.setdefault("deductible", None)
    parsed.setdefault("co_payment", None)
    parsed.setdefault("sub_limit", None)

    coverage_limit = _parse_number(parsed.get("coverage_limit"))
    deductible = _parse_number(parsed.get("deductible")) or 0.0
    co_payment = _parse_number(parsed.get("co_payment")) or 0.0
    sub_limit = _parse_number(parsed.get("sub_limit")) or 0.0
    claim_amt = float(claim_amount) if claim_amount is not None else _parse_number(parsed.get("claim_amount")) or 0.0

    # Compute eligible amount conservatively
    eligible = claim_amt
    if coverage_limit is not None:
        eligible = min(eligible, coverage_limit)
    eligible = max(0.0, eligible - deductible - co_payment - sub_limit)

    parsed["financials"] = {
        "claim_amount": claim_amt,
        "coverage_limit": coverage_limit,
        "deductible": deductible,
        "co_payment": co_payment,
        "sub_limit": sub_limit,
        "eligible_amount": round(eligible, 2),
    }

    # Hospital network verification: use local data file, otherwise UNKNOWN
    hospital_networks = _load_hospital_networks()
    hospital_name = parsed.get("hospital_name") or None
    if not hospital_name:
        # try to find in question text or documents
        hospital_name = None
    network_status = "UNKNOWN"
    if hospital_name:
        network_status = hospital_networks.get(hospital_name.strip().lower(), "UNKNOWN")
    parsed["hospital_network_status"] = network_status

    # Add evidence summary if missing by summarizing retrieved citations
    if not parsed.get("evidence_summary"):
        citations = build_document_citations(documents)
        if citations:
            excerpts = [c.get("excerpt") for c in citations if c.get("excerpt")]
            parsed["evidence_summary"] = " | ".join(excerpts[:3]) if excerpts else "Retrieved policy sources available."
        else:
            parsed["evidence_summary"] = "No structured evidence was returned."

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

    # Rule-based overrides / validation combining RAG evidence + policy rules + claim inputs
    # 1) Waiting period violation -> reject
    try:
        if parsed.get("waiting_period_eligible") is False:
            parsed["decision"] = "rejected"
            parsed["confidence"] = "high"
            parsed.setdefault("rationale", "")
            parsed["rationale"] += " Waiting period not satisfied."
    except Exception:
        pass

    # 2) If hospital network unknown, escalate for manual review
    if parsed.get("hospital_network_status") == "UNKNOWN":
        parsed.setdefault("missing_information", []).append("Hospital network status UNKNOWN; verify provider.")
        if parsed.get("decision") == "approved":
            parsed["decision"] = "needs_review"

    # 3) If claim exceeds coverage limit significantly, mark for review
    try:
        if coverage_limit is not None and claim_amt > (coverage_limit * 1.0):
            parsed.setdefault("missing_information", []).append("Claim exceeds coverage limit.")
            if parsed.get("decision") == "approved":
                parsed["decision"] = "needs_review"
    except Exception:
        pass
    return parsed
