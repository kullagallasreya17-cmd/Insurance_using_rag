import os

LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "0"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.15"))
INSUFFICIENT_CONTEXT_ANSWER = "I couldn't find sufficiently relevant information in the uploaded insurance documents."
SELECTED_DOCUMENT_NOT_FOUND_ANSWER = "I couldn't find this information in the selected insurance document."
MULTI_DOCUMENT_NOT_FOUND_ANSWER = "I couldn't find this information across the retrieved insurance documents."


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
        evidence_role = doc.metadata.get("evidence_role", "context")

        context_parts.append(
            f"[Chunk {index} | role: {evidence_role} | type: {document_type} | category: {category} | "
            f"page: {page} | source: {source}]\n{doc.page_content}"
        )

    return "\n\n".join(context_parts)


def _has_explicit_document_context(documents) -> bool:
    if not documents:
        return False
    metadata = [getattr(doc, "metadata", {}) or {} for doc in documents]
    sources = {item.get("source") for item in metadata if item.get("source")}
    filenames = {item.get("filename") for item in metadata if item.get("filename")}
    document_ids = {item.get("document_id") for item in metadata if item.get("document_id") is not None}
    return len(sources) == 1 or len(filenames) == 1 or len(document_ids) == 1


def _is_multi_document_context(documents) -> bool:
    if not documents:
        return False
    metadata = [getattr(doc, "metadata", {}) or {} for doc in documents]
    document_keys = {
        item.get("document_id") or item.get("source") or item.get("filename")
        for item in metadata
        if item.get("document_id") is not None or item.get("source") or item.get("filename")
    }
    return len(document_keys) > 1


def _validate_verified_context(documents) -> tuple[bool, str | None]:
    if not documents:
        return False, INSUFFICIENT_CONTEXT_ANSWER

    categories = set()
    sources = set()
    for doc in documents:
        text = (getattr(doc, "page_content", "") or "").strip()
        metadata = getattr(doc, "metadata", {}) or {}
        if not text:
            return False, SELECTED_DOCUMENT_NOT_FOUND_ANSWER

        score = metadata.get("retrieval_score")
        if score is not None:
            try:
                if float(score) < RAG_SIMILARITY_THRESHOLD:
                    return False, INSUFFICIENT_CONTEXT_ANSWER
            except (TypeError, ValueError):
                return False, INSUFFICIENT_CONTEXT_ANSWER

        if metadata.get("category"):
            categories.add(metadata.get("category"))
        if metadata.get("source"):
            sources.add(metadata.get("source"))

    if len(categories) > 1 and len(sources) <= 1:
        return False, SELECTED_DOCUMENT_NOT_FOUND_ANSWER

    return True, None


def _fallback_answer(question, documents, reason=None):
    if not documents:
        return INSUFFICIENT_CONTEXT_ANSWER

    snippets = []
    seen = set()
    for doc in documents:
        text = " ".join((doc.page_content or "").split())
        if not text:
            continue
        excerpt = text[:450]
        if excerpt in seen:
            continue
        seen.add(excerpt)
        snippets.append(excerpt)
        if len(snippets) >= 3:
            break

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


def _invoke_with_retries(llm, prompt: str):
    import time

    attempts = max(1, LLM_MAX_RETRIES + 1)
    backoff = 1.0
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            response = llm.invoke(prompt)
            if hasattr(response, "content"):
                return response.content
            return str(response)
        except Exception as exc:
            last_exc = exc
            if _is_quota_error(exc):
                # If it's a quota/rate-limit issue, bail out immediately so caller can fallback.
                raise
            if attempt >= attempts:
                break
            time.sleep(backoff)
            backoff = min(backoff * 2, 10)

    # Re-raise the final exception for the caller to handle
    if last_exc:
        raise last_exc
    return None


def generate_answer(question, documents):

    is_valid_context, validation_message = _validate_verified_context(documents)
    if not is_valid_context:
        return validation_message or SELECTED_DOCUMENT_NOT_FOUND_ANSWER

    if not os.getenv("GOOGLE_API_KEY"):
        return _fallback_answer(question, documents)

    llm = _build_llm(temperature=0.2)

    context = _format_context(documents)

    not_found_answer = MULTI_DOCUMENT_NOT_FOUND_ANSWER if _is_multi_document_context(documents) else SELECTED_DOCUMENT_NOT_FOUND_ANSWER
    comparison_instruction = (
        "If multiple documents are retrieved, compare them document by document. "
        "For superlative questions such as highest coverage, identify the relevant value from each retrieved policy when present, then name the highest. "
        "If a value is missing for any policy, say which policy is missing that value."
        if _is_multi_document_context(documents)
        else "Answer only for the selected/retrieved document."
    )

    prompt = f"""
You are an insurance document question-answering assistant.

Use ONLY the VERIFIED RETRIEVED CONTEXT below.
The retrieved context has already been filtered to the document requested by the user when a specific document was requested.

Important rules:
- For single-document questions, never use information from another insurance document.
- For multi-document comparison questions, use only the retrieved documents and keep each policy's facts separate.
- Never use general insurance knowledge to fill missing policy details.
- Never invent coverage, exclusions, waiting periods, premiums, claim requirements, or policy conditions.
- If the answer is not explicitly supported by the verified context, say exactly:
  "{not_found_answer}"
- Always prefer refusing to answer over providing unsupported information.
- {comparison_instruction}

Verified retrieved context:
{context}

User question:
{question}

Answer:
"""

    try:
        return _invoke_with_retries(llm, prompt)
    except Exception as exc:
        print(f"LLM generation unavailable: {type(exc).__name__}: {exc}")
        return _fallback_answer(question, documents, reason="quota" if _is_quota_error(exc) else None)


def generate_claim_analysis(question, documents, claim_amount=None, policy_category=None, admission_date=None):
    is_valid_context, validation_message = _validate_verified_context(documents)
    if not is_valid_context:
        return """{
  "decision": "needs_review",
  "confidence": "low",
  "rationale": "%s",
  "covered_items": [],
  "exclusions": [],
  "policy_start_date": null,
  "admission_date": null,
  "waiting_period_months": null,
  "missing_information": ["Policy evidence"],
  "next_steps": ["Upload or select the relevant policy document and supporting claim documents"]
}""" % (validation_message or "Insufficient verified policy context was retrieved for this claim.")

    if not os.getenv("GOOGLE_API_KEY"):
        return """{
  "decision": "needs_review",
  "confidence": "low",
  "rationale": "LLM service is not configured, so the claim needs manual review.",
  "covered_items": [],
  "exclusions": [],
  "policy_start_date": null,
  "admission_date": null,
  "waiting_period_months": null,
  "missing_information": ["LLM service configuration"],
  "next_steps": ["Configure GOOGLE_API_KEY or review the claim manually"]
}"""

    llm = _build_llm(temperature=0.0)

    context = _format_context(documents)

    prompt = f"""
You are an enterprise insurance claim analysis engine.

Use only the retrieved policy and claim evidence context provided below. Do not invent benefits, exclusions, dates, bills, diagnoses, or claim requirements.
Return valid JSON only, with no markdown fences and no explanatory text. Use exactly these keys:
{
  "decision": "approved" | "rejected" | "needs_review",
  "confidence": "low" | "medium" | "high",
  "rationale": "short explanation grounded in the provided context",
  "covered_items": [],
  "exclusions": [],
  "policy_start_date": null,
  "admission_date": null,
  "waiting_period_months": null,
  "missing_information": [],
  "next_steps": []
}

Rules:
- Treat chunks with role=policy as the source of truth for coverage, exclusions, limits, waiting periods, and required documents.
- Treat chunks with role=claim as supporting evidence only. Claim evidence cannot create coverage that the policy evidence does not state.
- If the context clearly shows the claim is covered, return approved.
- If the context clearly shows a policy exclusion or non-coverage, return rejected.
- If the evidence is incomplete or the question is ambiguous, return needs_review.
- Prefer needs_review when you are not fully sure.
- Keep rationale short and factual.
- If no relevant policy context is available, return needs_review with a clear reason and add "Policy document evidence" to missing_information.
- If retrieved documents disagree or specific page-level details are missing, note this explicitly in the rationale and missing_information.
- Include missing claim documents in missing_information when policy requirements are not satisfied by the provided claim evidence.

Claim amount: {claim_amount}
Policy category: {policy_category}
Admission date: {admission_date}

Context:
{context}

Question:
{question}
"""

    try:
        return _invoke_with_retries(llm, prompt)
    except Exception as exc:
        print(f"LLM claim analysis unavailable: {type(exc).__name__}: {exc}")
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
  "policy_start_date": null,
  "admission_date": null,
  "waiting_period_months": null,
  "missing_information": ["LLM service response"],
  "next_steps": ["Retry analysis later or review the claim manually"]
}""" % rationale
