"""Small, best-effort public web research fallback for claim cost context."""

import os
import re

from rag.web_search import web_search


def _extract_amounts(text: str) -> list[float]:
    amounts = []
    for raw_value, unit in re.findall(
        r"(?:rs\.?|inr|₹)\s*([0-9]+(?:\.[0-9]+)?)\s*(lakh| lakhs|crore| crores|k)?",
        text,
        flags=re.IGNORECASE,
    ):
        value = float(raw_value)
        normalized_unit = (unit or "").strip().lower()
        if normalized_unit.startswith("lakh"):
            value *= 100000
        elif normalized_unit.startswith("crore"):
            value *= 10000000
        elif normalized_unit == "k":
            value *= 1000
        amounts.append(value)
    return amounts


def search_hospital_cost(
    question: str,
    hospital_name: str | None,
    location: str | None,
    claim_amount: float | None = None,
) -> dict:
    if os.getenv("CLAIM_WEB_SEARCH_ENABLED", "1") == "0" or not hospital_name:
        return {"enabled": False, "sources": [], "summary": ""}

    query = " ".join(
        part
        for part in (
            question,
            hospital_name,
            location,
            "India knee surgery cost estimate",
        )
        if part
    )
    search_result = web_search(query)
    sources = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "source": item.get("source"),
            "published_date": item.get("published_date"),
        }
        for item in search_result.get("results", [])
    ]

    summary = "\n".join(
        f"- {item['title']}: {item['snippet']} ({item['url']})"
        for item in sources
    )
    extracted_amounts = [amount for item in sources for amount in _extract_amounts(item["snippet"])]
    amount_assessment = None
    if claim_amount is not None and extracted_amounts:
        low = min(extracted_amounts)
        high = max(extracted_amounts)
        if claim_amount < low:
            status = "below_public_estimate"
            message = "The entered amount is below the public estimate range. Confirm whether the estimate covers the same procedure and room category."
        elif claim_amount > high:
            status = "above_public_estimate"
            message = "The entered amount is above the public estimate range. Request a hospital estimate and itemized bill before deciding."
        else:
            status = "within_public_estimate"
            message = "The entered amount falls within the public estimate range. This does not confirm policy eligibility or final payable amount."
        amount_assessment = {
            "status": status,
            "entered_amount": claim_amount,
            "public_estimate_min": low,
            "public_estimate_max": high,
            "message": message,
        }
    return {
        "enabled": search_result.get("ok", False),
        "query": query,
        "sources": sources,
        "summary": summary or search_result.get("error") or "No public cost estimates were found.",
        "amount_assessment": amount_assessment,
        "disclaimer": "Public web estimates are informational and must be verified with the hospital and insurer.",
    }