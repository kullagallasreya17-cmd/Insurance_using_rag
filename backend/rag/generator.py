import os


LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "0"))


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    quota_markers = (
        "quota",
        "rate limit",
        "ratelimit",
        "resource exhausted",
        "429",
    )
    return any(marker in message for marker in quota_markers)


def _format_context(documents):
    context_parts = []

    for index, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "uploaded document")
        page = doc.metadata.get("page_label") or doc.metadata.get("page", "unknown")
        category = doc.metadata.get("category", "general")
        document_type = doc.metadata.get("document_type", "document")

        context_parts.append(
            f"[Chunk {index} | type: {document_type} | category: {category} | "
            f"page: {page} | source: {source}]\n{doc.page_content}"
        )

    return "\n\n".join(context_parts)


def _fallback_answer(question, documents, reason=None):
    if not documents:
        return (
            "I couldn't find any indexed insurance document chunks to answer from. "
            "Please upload and index a policy first."
        )

    snippets = []
    for doc in documents[:3]:
        text = " ".join((doc.page_content or "").split())
        if text:
            snippets.append(text[:450])

    if not snippets:
        return (
            "I found retrieved document records, but they did not contain readable text for this question."
        )

    if reason == "quota":
        availability_message = (
            "I found relevant insurance document context, but the LLM quota or rate limit has been exceeded. "
        )
    else:
        availability_message = (
            "I found relevant insurance document context, but the LLM service is currently unavailable or slow. "
        )

    return (
        availability_message
        + f"Based on the retrieved context for '{question}', the most relevant details are: "
        + " ".join(snippets)
    )


def _build_llm(temperature: float):
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm_kwargs = {
        "model": os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash"),
        "google_api_key": os.getenv("GOOGLE_API_KEY"),
        "temperature": temperature,
        "timeout": LLM_TIMEOUT_SECONDS,
        "max_retries": LLM_MAX_RETRIES,
    }

    try:
        return ChatGoogleGenerativeAI(**llm_kwargs)
    except TypeError:
        llm_kwargs.pop("max_retries", None)
        return ChatGoogleGenerativeAI(**llm_kwargs)


def generate_answer(question, documents):

    if not documents:
        return _fallback_answer(question, documents)

    if not os.getenv("GOOGLE_API_KEY"):
        return _fallback_answer(question, documents)

    llm = _build_llm(temperature=0.2)

    context = _format_context(documents)

    prompt = f"""
You are an AI Insurance Assistant.

Answer the user's question using only the retrieved insurance document context below.

Important rules:
- If the context contains the answer, give a direct, helpful answer.
- Mention key policy details such as policy name, coverage, premiums, benefits, claim documents, exclusions, or lapse rules when relevant.
- If the context is related but does not contain a specific detail, say which related details are available.
- Say "I couldn't find the answer in the insurance documents." only when the retrieved context is empty or clearly unrelated to the question.

Retrieved context:
{context}

User question:
{question}

Answer:
"""

    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as exc:
        print(f"LLM generation unavailable: {exc}")
        return _fallback_answer(question, documents, reason="quota" if _is_quota_error(exc) else None)


def generate_claim_analysis(question, documents, claim_amount=None, policy_category=None):
    if not os.getenv("GOOGLE_API_KEY"):
        return """{
  "decision": "needs_review",
  "confidence": "low",
  "rationale": "LLM service is not configured, so the claim needs manual review.",
  "covered_items": [],
  "exclusions": [],
  "missing_information": ["LLM service configuration"],
  "next_steps": ["Configure GOOGLE_API_KEY or review the claim manually"]
}"""

    llm = _build_llm(temperature=0.0)

    context = _format_context(documents)

    prompt = f"""
You are an enterprise insurance claim analysis engine.

Use only the retrieved policy and medical context provided below. Do not invent benefits or exclusions.
Return valid JSON only, with no markdown fences and no explanatory text. Use exactly these keys:
{{
  "decision": "approved" | "rejected" | "needs_review",
  "confidence": "low" | "medium" | "high",
  "rationale": "short explanation grounded in the provided context",
  "covered_items": [],
  "exclusions": [],
  "missing_information": [],
  "next_steps": []
}}

Rules:
- If the context clearly shows the claim is covered, return approved.
- If the context clearly shows a policy exclusion or non-coverage, return rejected.
- If the evidence is incomplete or the question is ambiguous, return needs_review.
- Prefer needs_review when you are not fully sure.
- Keep rationale short and factual.
- If no relevant policy context is available, return needs_review with a clear reason.
- If retrieved documents disagree or specific page-level details are missing, note this explicitly in the rationale and missing_information.

Claim amount: {claim_amount}
Policy category: {policy_category}

Context:
{context}

Question:
{question}
"""

    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as exc:
        print(f"LLM claim analysis unavailable: {exc}")
        rationale = (
            "The LLM quota or rate limit has been exceeded, so the claim needs manual review."
            if _is_quota_error(exc)
            else "LLM service is unavailable or timed out, so the claim needs manual review."
        )
        return """{
  "decision": "needs_review",
  "confidence": "low",
  "rationale": "%s",
  "covered_items": [],
  "exclusions": [],
  "missing_information": ["LLM service response"],
  "next_steps": ["Retry analysis later or review the claim manually"]
}""" % rationale
