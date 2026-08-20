"""Deterministic, explainable routing for policy and current-information queries."""

import re
from enum import Enum


class QueryRoute(str, Enum):
    POLICY_ONLY = "POLICY_ONLY"
    WEB_ONLY = "WEB_ONLY"
    POLICY_AND_WEB = "POLICY_AND_WEB"


class ClaimIntent(str, Enum):
    POLICY_QUERY = "POLICY_QUERY"
    CLAIM_ANALYSIS_QUERY = "CLAIM_ANALYSIS_QUERY"
    MEDICAL_DOCUMENT_QUERY = "MEDICAL_DOCUMENT_QUERY"
    WEB_QUERY = "WEB_QUERY"
    HOSPITAL_COST_QUERY = "HOSPITAL_COST_QUERY"
    MIXED_CLAIM_QUERY = "MIXED_CLAIM_QUERY"


POLICY_TERMS = re.compile(
    r"\b(policy|policies|coverage|covered|exclusion|waiting period|sum insured|deductible|premium|"
    r"claim requirement|policy document|uploaded policy|insurer|insurance terms)\b",
    re.IGNORECASE,
)
WEB_TERMS = re.compile(
    r"\b(current|latest|today|now|near|nearby|hospital|cost|price|approximate|estimate|"
    r"treatment option|available|india|bangalore|bengaluru|chennai|mumbai|delhi|hyderabad|city|location)\b",
    re.IGNORECASE,
)
CLAIM_TERMS = re.compile(
    r"\b(claim|bill|payable|reimburse|reimbursement|eligible amount|hospital bill|medical report|"
    r"discharge summary|prescription|admission|diagnosis|underwent|rejected claim|missing document)\b",
    re.IGNORECASE,
)
MEDICAL_DOCUMENT_TERMS = re.compile(
    r"\b(medical report|diagnosis|treatment recommended|prescription|discharge summary|"
    r"bill match|medical document)\b",
    re.IGNORECASE,
)
COST_TERMS = re.compile(
    r"\b(cost|price|estimate|cheaper|compare|treatment cost|hospital cost|how much)\b",
    re.IGNORECASE,
)


def classify_claim_intent(query: str, has_claim_documents: bool = False) -> ClaimIntent:
    """Classify claim-workspace requests before selecting a data source."""
    text = (query or "").strip()
    has_policy = bool(POLICY_TERMS.search(text))
    has_claim_amount = bool(re.search(r"(?:rs\.?|inr|₹|\$)?\s*\d[\d,]*(?:\.\d+)?\s*(?:lakh|lakhs|crore|crores|k)?", text, re.IGNORECASE))
    has_claim = bool(CLAIM_TERMS.search(text)) or has_claim_documents or (has_policy and has_claim_amount)
    has_cost = bool(COST_TERMS.search(text) or WEB_TERMS.search(text))

    if has_claim and has_policy and has_cost:
        return ClaimIntent.MIXED_CLAIM_QUERY
    if has_claim and has_policy:
        return ClaimIntent.CLAIM_ANALYSIS_QUERY
    if has_claim and MEDICAL_DOCUMENT_TERMS.search(text):
        return ClaimIntent.MEDICAL_DOCUMENT_QUERY
    if has_cost:
        return ClaimIntent.HOSPITAL_COST_QUERY if COST_TERMS.search(text) else ClaimIntent.WEB_QUERY
    return ClaimIntent.POLICY_QUERY


def resolve_claim_intent(mode: str, query: str, has_claim_documents: bool = False) -> ClaimIntent:
    """Honor explicit UI modes; classify only requests explicitly marked auto."""
    normalized_mode = (mode or "auto").strip().lower()
    if normalized_mode == "auto":
        return classify_claim_intent(query, has_claim_documents=has_claim_documents)
    return {
        "policy": ClaimIntent.POLICY_QUERY,
        "web": ClaimIntent.HOSPITAL_COST_QUERY,
        "claim": ClaimIntent.CLAIM_ANALYSIS_QUERY,
    }[normalized_mode]


def classify_query(query: str) -> QueryRoute:
    text = (query or "").strip()
    policy_match = bool(POLICY_TERMS.search(text))
    web_match = bool(WEB_TERMS.search(text))

    if policy_match and web_match:
        return QueryRoute.POLICY_AND_WEB
    if web_match:
        return QueryRoute.WEB_ONLY
    return QueryRoute.POLICY_ONLY