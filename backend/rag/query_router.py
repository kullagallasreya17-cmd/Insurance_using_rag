"""Deterministic, explainable routing for policy and current-information queries."""

import re
from enum import Enum


class QueryRoute(str, Enum):
    POLICY_ONLY = "POLICY_ONLY"
    WEB_ONLY = "WEB_ONLY"
    POLICY_AND_WEB = "POLICY_AND_WEB"


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


def classify_query(query: str) -> QueryRoute:
    text = (query or "").strip()
    policy_match = bool(POLICY_TERMS.search(text))
    web_match = bool(WEB_TERMS.search(text))

    if policy_match and web_match:
        return QueryRoute.POLICY_AND_WEB
    if web_match:
        return QueryRoute.WEB_ONLY
    return QueryRoute.POLICY_ONLY