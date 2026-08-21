import json
import logging
import re
from datetime import datetime
from typing import Optional

from rag.generator import generate_claim_analysis
from rag.retriever import RetrievalPlan, retrieve_documents_with_scores_expanded

def _build_claim_policy_query(
    question: str,
    policy_category: str | None = None,
) -> str:
    """Expand claim questions with the policy clauses needed for assessment."""
    category_text = (policy_category or "health insurance").replace("_", " ")
    return (
        f"{category_text} {question} coverage hospitalization medically necessary treatment "
        "waiting period exclusions coverage limit sum insured deductible co payment "
        "room rent sub limit eligibility claim documents definitions"
    )
from web_research import search_hospital_cost


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
                "filename": metadata.get("filename"),
                "document_name": metadata.get("document_name") or metadata.get("title"),
                "category": metadata.get("category", "general"),
                "document_type": metadata.get("document_type", "unknown"),
                "evidence_role": metadata.get("evidence_role", "context"),
                "document_id": metadata.get("document_id"),
                "chunk_id": metadata.get("chunk_id"),
                "retrieval_score": metadata.get("retrieval_score"),
                "rerank_score": metadata.get("rerank_score"),
                "page": metadata.get("page_label") or metadata.get("page", "unknown"),
                "excerpt": excerpt,
            }
        )

    # Deduplicate citations while preserving first-occurrence order.
    # Use the strongest available document identity so multi-policy answers do
    # not collapse citations when source/page fields are missing or generic.
    seen = set()
    unique_citations = []
    for c in citations:
        document_key = (
            c.get("document_id")
            or c.get("source")
            or c.get("filename")
            or c.get("document_name")
            or c.get("excerpt")
        )
        key = (document_key, c.get("page"), c.get("chunk_id"))
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

    # Older vector stores may return distance where lower is better, while
    # Atlas/cosine paths return similarity where higher is better. Normalize
    # obvious distance-shaped values into a comparable confidence signal.
    if all(0.0 <= score <= 0.25 for score in safe_scores):
        return "high"
    if any(score > 1.0 for score in safe_scores):
        avg_distance = sum(safe_scores) / len(safe_scores)
        if avg_distance <= 0.25:
            return "high"
        if avg_distance <= 0.75:
            return "medium"
        return "low"

    avg_score = sum(safe_scores) / len(safe_scores)

    if avg_score >= 0.45:
        return "high"
    if avg_score >= 0.25:
        return "medium"
    return "low"


CLAIM_DOCUMENT_RULES = {
    "health_policy": [
        ("policy", "Active policy document"),
        ("medical_report", "Doctor consultation or diagnosis report"),
        ("hospital_bill", "Hospital bill or invoice"),
        ("prescription", "Prescription or treatment advice"),
        ("lab_report", "Lab or investigation reports, if applicable"),
    ],
    "vehicle_policy": [
        ("policy", "Active vehicle policy document"),
        ("hospital_bill", "Repair bill or estimate"),
        ("medical_report", "Accident or damage report"),
    ],
    "life_policy": [
        ("policy", "Active life policy document"),
        ("medical_report", "Medical or death certificate evidence"),
    ],
    "default": [
        ("policy", "Relevant policy document"),
        ("medical_report", "Supporting claim report"),
        ("hospital_bill", "Claim bill or invoice"),
    ],
}


def build_claim_document_checklist(
    documents,
    policy_category: str | None = None,
    uploaded_document_types: list[str] | None = None,
):
    required = CLAIM_DOCUMENT_RULES.get(policy_category or "", CLAIM_DOCUMENT_RULES["default"])
    present_types = set(uploaded_document_types or [])
    for doc in documents or []:
        metadata = getattr(doc, "metadata", {}) or {}
        document_type = metadata.get("document_type")
        if document_type:
            present_types.add(document_type)
        if metadata.get("evidence_role") == "policy":
            present_types.add("policy")

    items = []
    for document_type, label in required:
        present = document_type in present_types
        items.append(
            {
                "document_type": document_type,
                "label": label,
                "present": present,
            }
        )

    missing = [item["label"] for item in items if not item["present"]]
    return {
        "required": items,
        "missing_documents": missing,
        "complete": not missing,
    }


def evaluate_rag_grounding(parsed: dict, documents, retrieval_scores: list[float]):
    confidence = estimate_confidence_from_retrieval_scores(retrieval_scores)
    has_sources = bool(documents)
    has_policy_source = False
    has_claim_source = False
    supported_terms = set()
    context = " ".join((getattr(doc, "page_content", "") or "").lower() for doc in documents or [])
    answer_text = " ".join(
        str(parsed.get(field, ""))
        for field in ("decision", "rationale", "evidence_summary")
    ).lower()
    for field in ("covered_items", "exclusions"):
        for item in parsed.get(field, []) or []:
            item_text = str(item).lower().strip()
            if item_text and item_text in context:
                supported_terms.add(item_text)
            if item_text and item_text in answer_text and item_text not in context:
                supported_terms.discard(item_text)

    policy_context = " ".join(
        (getattr(doc, "page_content", "") or "").lower()
        for doc in documents or []
        if (getattr(doc, "metadata", {}) or {}).get("evidence_role") == "policy"
        or (getattr(doc, "metadata", {}) or {}).get("document_type") == "policy"
    )
    claim_context = " ".join(
        (getattr(doc, "page_content", "") or "").lower()
        for doc in documents or []
        if (getattr(doc, "metadata", {}) or {}).get("evidence_role") == "claim"
    )
    verification_warnings = []
    coverage_items = _ensure_list(parsed.get("covered_items"))
    exclusion_items = _ensure_list(parsed.get("exclusions"))
    unsupported_coverage = [
        str(item) for item in coverage_items
        if str(item).strip().lower() not in policy_context
    ]
    unsupported_exclusions = [
        str(item) for item in exclusion_items
        if str(item).strip().lower() not in policy_context
    ]
    if parsed.get("decision") == "approved" and not coverage_items:
        verification_warnings.append("Coverage was not explicitly identified in policy evidence.")
    if unsupported_coverage:
        verification_warnings.append("One or more covered items were not found in policy evidence.")
    if unsupported_exclusions:
        verification_warnings.append("One or more exclusions were not found in policy evidence.")

    waiting_value = parsed.get("waiting_period_months")
    waiting_verified = waiting_value is None or str(waiting_value).lower() in policy_context
    if not waiting_verified:
        verification_warnings.append("Waiting-period value was not found in policy evidence.")

    limit_value = parsed.get("coverage_limit")
    limit_verified = limit_value is None or str(limit_value).replace(",", "").lower() in policy_context.replace(",", "")
    if not limit_verified:
        verification_warnings.append("Coverage-limit value was not found in policy evidence.")

    has_claim_documents = any(
        (getattr(doc, "metadata", {}) or {}).get("document_type") != "policy"
        for doc in documents or []
    )
    claim_evidence_verified = not has_claim_documents or bool(claim_context.strip())
    if has_claim_documents and not claim_evidence_verified:
        verification_warnings.append("Claim documents were retrieved without usable claim evidence.")

    citation_valid = all(
        (getattr(doc, "metadata", {}) or {}).get("source")
        or (getattr(doc, "metadata", {}) or {}).get("filename")
        for doc in documents or []
    )
    if not citation_valid:
        verification_warnings.append("Retrieved evidence is missing source citations.")

    for doc in documents or []:
        metadata = getattr(doc, "metadata", {}) or {}
        if metadata.get("evidence_role") == "policy" or metadata.get("document_type") == "policy":
            has_policy_source = True
        elif metadata.get("evidence_role") == "claim":
            has_claim_source = True

    warnings = []
    if not has_sources:
        warnings.append("No retrieved policy evidence was available.")
    if not has_policy_source:
        warnings.append("No policy document evidence was retrieved for this claim.")
    if confidence == "low":
        warnings.append("Retrieved evidence was low confidence.")
    if (parsed.get("decision") == "approved" and not supported_terms and has_sources):
        warnings.append("Approval was not backed by explicit covered item or exclusion evidence.")
    warnings.extend(verification_warnings)

    verification_checks = {
        "coverage": not unsupported_coverage and (parsed.get("decision") != "approved" or bool(coverage_items)),
        "exclusions": not unsupported_exclusions,
        "waiting_period": waiting_verified,
        "coverage_limit": limit_verified,
        "claim_evidence": claim_evidence_verified,
        "citations": citation_valid,
    }

    return {
        "confidence": confidence,
        "source_count": len(documents or []),
        "policy_source_count": sum(
            1
            for doc in documents or []
            if (getattr(doc, "metadata", {}) or {}).get("evidence_role") == "policy"
            or (getattr(doc, "metadata", {}) or {}).get("document_type") == "policy"
        ),
        "claim_source_count": sum(
            1
            for doc in documents or []
            if (getattr(doc, "metadata", {}) or {}).get("evidence_role") == "claim"
        ),
        "has_claim_evidence": has_claim_source,
        "supported_terms": sorted(supported_terms),
        "warnings": warnings,
        "verification_checks": verification_checks,
        "grounding_score": round(
            sum(verification_checks.values()) / len(verification_checks), 2
        ),
        "grounded": has_sources and has_policy_source and confidence != "low" and not warnings,
    }


def _ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def _retrieve_claim_context(
    question: str,
    policy_category: str | None = None,
    policy_document_id: int | None = None,
    claim_document_ids: list[int] | None = None,
):
    logging.info(
        "[CLAIM RETRIEVAL] query=%r policy_id=%s policy_category=%s claim_document_ids=%s",
        question,
        policy_document_id,
        policy_category,
        claim_document_ids or [],
    )
    if policy_document_id is None and not claim_document_ids:
        if policy_category:
            policy_filter = {"document_type": "policy", "category": policy_category}
            policy_plan = RetrievalPlan(query_filter=policy_filter)
            retrieval_results = retrieve_documents_with_scores_expanded(
                _build_policy_retrieval_query(question),
                override_filter=policy_filter,
                override_plan=policy_plan,
            )
            for doc, _score in retrieval_results:
                doc.metadata["evidence_role"] = "policy"
        else:
            retrieval_results = retrieve_documents_with_scores_expanded(question)
        return [doc for doc, _score in retrieval_results], retrieval_results

    results: list[tuple[object, float]] = []
    if policy_document_id is not None or policy_category:
        policy_filter = {"document_type": "policy"}
        if policy_document_id is not None:
            policy_filter["document_id"] = policy_document_id
        if policy_category:
            policy_filter["category"] = policy_category
        policy_plan = RetrievalPlan(query_filter=policy_filter)
        policy_results = retrieve_documents_with_scores_expanded(
            _build_claim_policy_query(question, policy_category),
            override_filter=policy_filter,
            override_plan=policy_plan,
        )
        for doc, _score in policy_results:
            doc.metadata["evidence_role"] = "policy"
        logging.info(
            "[CLAIM RETRIEVAL] policy_id=%s retrieved=%s scores=%s",
            policy_document_id,
            len(policy_results),
            [round(float(score), 4) for _doc, score in policy_results],
        )
        results.extend(policy_results)

    if claim_document_ids:
        claim_filter = {"document_id": {"$in": claim_document_ids}}
        claim_plan = RetrievalPlan(query_filter=claim_filter)
        claim_results = retrieve_documents_with_scores_expanded(
            _build_claim_evidence_query(question),
            override_filter=claim_filter,
            override_plan=claim_plan,
        )
        for doc, _score in claim_results:
            doc.metadata["evidence_role"] = "claim"
        logging.info(
            "[CLAIM EVIDENCE] document_ids=%s retrieved=%s scores=%s",
            claim_document_ids,
            len(claim_results),
            [round(float(score), 4) for _doc, score in claim_results],
        )
        results.extend(claim_results)

    seen = set()
    unique_results = []
    for doc, score in results:
        metadata = getattr(doc, "metadata", {}) or {}
        key = (
            metadata.get("document_id"),
            metadata.get("source"),
            metadata.get("page"),
            metadata.get("chunk_id"),
            (getattr(doc, "page_content", "") or "")[:80],
        )
        if key in seen:
            continue
        seen.add(key)
        unique_results.append((doc, score))

    return [doc for doc, _score in unique_results], unique_results


def _build_policy_retrieval_query(question: str) -> str:
    return (
        f"{question} policy coverage exclusions eligibility waiting period "
        "sum insured deductible co payment claim required documents"
    )


def _build_claim_evidence_query(question: str) -> str:
    return (
        f"{question} diagnosis treatment hospital bill prescription lab report "
        "discharge summary invoice admission date"
    )


def analyze_claim(
    question: str,
    claim_amount: float | None = None,
    policy_category: str | None = None,
    policy_document_id: int | None = None,
    claim_document_ids: list[int] | None = None,
    uploaded_document_types: list[str] | None = None,
    hospital_name: str | None = None,
    hospital_location: str | None = None,
    enable_web_search: bool = True,
    force_web_research: bool = False,
):
    documents, retrieval_results = _retrieve_claim_context(
        question,
        policy_category=policy_category,
        policy_document_id=policy_document_id,
        claim_document_ids=claim_document_ids,
    )
    retrieval_scores = [score for _doc, score in retrieval_results]
    # If the client provided an admission_date in the question text (or structured input),
    # the generator can include it in the analysis. For now we attempt to extract an ISO date token.
    admission_date = None
    # naive ISO date extraction
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(question))
    if m:
        admission_date = m.group(1)

    web_research = {"enabled": False, "sources": [], "summary": ""}
    if enable_web_search and hospital_name and (force_web_research or not claim_document_ids):
        web_research = search_hospital_cost(
            question,
            hospital_name,
            hospital_location,
            claim_amount=claim_amount,
        )

    raw_answer = generate_claim_analysis(
        question,
        documents,
        claim_amount,
        policy_category,
        admission_date=admission_date,
        external_context=web_research.get("summary", ""),
    )

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
    parsed["covered_items"] = _ensure_list(parsed.get("covered_items"))
    parsed["exclusions"] = _ensure_list(parsed.get("exclusions"))
    parsed["missing_information"] = _ensure_list(parsed.get("missing_information"))
    parsed["next_steps"] = _ensure_list(parsed.get("next_steps"))

    checklist = build_claim_document_checklist(
        documents,
        policy_category=policy_category,
        uploaded_document_types=uploaded_document_types,
    )
    parsed["document_checklist"] = checklist
    for missing_document in checklist["missing_documents"]:
        if missing_document not in parsed["missing_information"]:
            parsed["missing_information"].append(missing_document)

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

    # Do not treat the submitted amount as payable without policy rules.
    has_financial_rules = any(
        value is not None
        for value in (coverage_limit, parsed.get("deductible"), parsed.get("co_payment"), parsed.get("sub_limit"))
    )
    eligible = None
    if claim_amount is not None and has_financial_rules:
        eligible = float(claim_amount)
        if coverage_limit is not None:
            eligible = min(eligible, coverage_limit)
        eligible = max(0.0, eligible - deductible - co_payment - sub_limit)

    parsed["financials"] = {
        "claim_amount": claim_amt,
        "coverage_limit": coverage_limit,
        "deductible": deductible,
        "co_payment": co_payment,
        "sub_limit": sub_limit,
        "eligible_amount": round(eligible, 2) if eligible is not None else None,
    }

    # Preserve the submitted hospital name even when the LLM omits it.
    submitted_hospital_name = hospital_name

    # Hospital network verification: use local data file, otherwise UNKNOWN
    hospital_networks = _load_hospital_networks()
    hospital_name = parsed.get("hospital_name") or submitted_hospital_name or None
    if not hospital_name:
        # try to find in question text or documents
        hospital_name = None
    network_status = "UNKNOWN"
    if hospital_name:
        network_status = hospital_networks.get(hospital_name.strip().lower(), "UNKNOWN")
    parsed["hospital_network_status"] = network_status
    parsed["hospital_research"] = {
        "hospital_name": hospital_name,
        "location": hospital_location,
        "query": web_research.get("query"),
        "sources": web_research.get("sources", []),
        "summary": web_research.get("summary", ""),
        "amount_assessment": web_research.get("amount_assessment"),
        "disclaimer": web_research.get(
            "disclaimer",
            "Public web estimates are informational and must be verified with the hospital and insurer.",
        ),
    }
    if web_research.get("enabled") and not web_research.get("sources"):
        parsed.setdefault("missing_information", []).append("Verified hospital estimate or bill")

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
    rag_evaluation = evaluate_rag_grounding(parsed, documents, retrieval_scores)
    parsed["rag_evaluation"] = rag_evaluation

    if parsed.get("decision") not in {"approved", "rejected", "needs_review"}:
        parsed["decision"] = "needs_review"
    if not rag_evaluation["grounded"] and parsed.get("decision") == "approved":
        parsed["decision"] = "needs_review"
        parsed.setdefault("next_steps", []).append(
            "Manual review required because the approval is not sufficiently grounded in retrieved policy evidence."
        )

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
