import re
import logging
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from langchain_core.documents import Document

from rag.vectorstore import (
    MONGO_EMBEDDING_KEY,
    MONGO_TEXT_KEY,
    get_mongo_collection,
    get_mongo_vector_store,
)


RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.15"))
RAG_FETCH_K = int(os.getenv("RAG_FETCH_K", "30"))
RAG_RERANK_ENABLED = os.getenv("RAG_RERANK_ENABLED", "1") != "0"
RAG_RERANK_STRATEGY = os.getenv("RAG_RERANK_STRATEGY", "lexical").lower()
RAG_RERANK_MODEL = os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RAG_RERANK_VECTOR_WEIGHT = float(os.getenv("RAG_RERANK_VECTOR_WEIGHT", "0.65"))
RAG_HYBRID_LEXICAL_K = int(os.getenv("RAG_HYBRID_LEXICAL_K", "30"))
_CROSS_ENCODER = None

POLICY_STOP_WORDS = {
    "backend",
    "document",
    "documents",
    "doc",
    "file",
    "insurance",
    "pdf",
    "policy",
    "private",
    "pvt",
    "uploaded",
    "wording",
    "wordings",
}

RERANK_STOP_WORDS = POLICY_STOP_WORDS | {
    "about",
    "after",
    "against",
    "also",
    "any",
    "are",
    "based",
    "can",
    "does",
    "for",
    "from",
    "give",
    "has",
    "how",
    "into",
    "its",
    "only",
    "tell",
    "the",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
}

CATEGORY_ALIASES = {
    "health_policy": ("health policy", "health_policy", "medical policy", "hospitalization policy"),
    "vehicle_policy": ("vehicle policy", "vehicle_policy", "motor policy", "motor insurance", "car insurance", "auto policy"),
    "life_policy": ("life policy", "life_policy", "term insurance", "life insurance"),
    "home_policy": ("home policy", "home_policy", "home insurance"),
    "travel_policy": ("travel policy", "travel_policy", "travel insurance"),
    "personal_accident_policy": ("personal accident", "personal_accident_policy"),
    "critical_illness_policy": ("critical illness", "critical_illness_policy"),
    "property_policy": ("property policy", "property_policy"),
    "claim_procedure": ("claim procedure", "claim_procedure"),
    "terms_conditions": ("terms conditions", "terms_conditions", "terms and conditions"),
    "faq": ("faq", "insurance faq"),
}

DOCUMENT_REFERENCE_WORDS = {
    "document",
    "file",
    "pdf",
    "policy",
    "summarize",
    "summary",
}
CLAIM_FILENAME_HINTS = re.compile(
    r"\b(patient|medical|report|bill|invoice|prescription|lab|discharge|receipt|surgery_sample)\b",
    re.IGNORECASE,
)


@dataclass
class RetrievalPlan:
    query_filter: dict | None
    detected_category: str | None = None
    detected_sources: list[str] | None = None
    explicit_document: bool = False
    allow_multiple_documents: bool = False


def _normalize_text(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_compare_query(query: str) -> bool:
    normalized = _normalize_text(query)
    return bool(
        re.search(
            r"\b(compare|versus|vs|v|different|difference|both|either|among|between|highest|lowest|maximum|minimum|best|least|most)\b",
            normalized,
        )
    )


def _is_multi_document_query(query: str) -> bool:
    normalized = _normalize_text(query)
    if _is_compare_query(query):
        return True
    return bool(
        re.search(r"\b(which|what)\s+polic(?:y|ies)\b", normalized)
        or re.search(r"\bpolicies\b.*\b(uploaded|indexed|available|all)\b", normalized)
        or re.search(r"\b(uploaded|indexed|available|all)\b.*\bpolicies\b", normalized)
    )


def _is_policy_query(query: str) -> bool:
    normalized = _normalize_text(query)
    return bool(re.search(r"\b(policy|policies|insurance)\b", normalized))


def _token_set(value: str) -> set[str]:
    return {token for token in (value or "").split() if len(token) > 2}


def _distinctive_tokens(value: str) -> list[str]:
    return [
        token
        for token in _normalize_text(value).split()
        if len(token) > 2
        and token not in POLICY_STOP_WORDS
        and not re.fullmatch(r"[0-9a-f]{8,}", token)
    ]


def _infer_category_from_query(query: str) -> str | None:
    categories = _infer_categories_from_query(query)
    return categories[0] if len(categories) == 1 else None


def _infer_categories_from_query(query: str) -> list[str]:
    normalized = _normalize_text(query)
    categories = []
    for category, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            alias_normalized = _normalize_text(alias)
            if alias_normalized and alias_normalized in normalized:
                categories.append(category)
                break
    return categories


def _is_explicit_document_query(query: str) -> bool:
    normalized = _normalize_text(query)
    tokens = set(normalized.split())
    if tokens.intersection(DOCUMENT_REFERENCE_WORDS):
        return True
    return any(_normalize_text(alias) in normalized for aliases in CATEGORY_ALIASES.values() for alias in aliases)


def _source_name_parts(value: str) -> set[str]:
    if not value:
        return set()

    value = str(value)
    path = Path(value)
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    return {
        value,
        path.name,
        path.stem,
        posix_path.name,
        posix_path.stem,
        windows_path.name,
        windows_path.stem,
    }


def _policy_variants(value: str) -> set[str]:
    if not value:
        return set()

    variants: set[str] = set()
    for part in _source_name_parts(value):
        normalized = _normalize_text(part)
        if not normalized:
            continue

        variants.add(normalized)

        distinctive = _distinctive_tokens(normalized)
        if distinctive:
            variants.add(" ".join(distinctive))
            variants.update(distinctive)

        # Match natural user mentions like "auto secure" from
        # "Auto Secure Policy.pdf" without requiring the file extension/path.
        for size in range(2, len(distinctive) + 1):
            for start in range(0, len(distinctive) - size + 1):
                variants.add(" ".join(distinctive[start : start + size]))

    return {variant for variant in variants if variant}


def _metadata_variants(metadata: dict) -> set[str]:
    variants: set[str] = set()
    for key in ("source", "filename", "document_name", "title"):
        variants.update(_policy_variants(metadata.get(key)))
    category = metadata.get("category")
    if category:
        variants.add(_normalize_text(category))
        variants.add(_normalize_text(str(category).replace("_", " ")))
    return {variant for variant in variants if variant}


def _matches_policy_variant(query: str, variant: str) -> bool:
    if not variant:
        return False

    variant_tokens = _distinctive_tokens(variant)
    if not variant_tokens:
        return False

    if variant in query:
        return True

    query_tokens = set(_normalize_text(query).split())
    if len(variant_tokens) == 1:
        return variant_tokens[0] in query_tokens

    return set(variant_tokens).issubset(query_tokens)


def _matches_named_document(query: str, value: str) -> tuple[bool, int]:
    """Match a filename/document name, preserving identifiers such as A/B/C."""
    stem = _normalize_text(Path(str(value or "")).stem)
    tokens = [token for token in stem.split() if token not in {"policy", "pdf", "document"}]
    query_tokens = set(_normalize_text(query).split())
    if not tokens or not set(tokens).issubset(query_tokens):
        return False, 0
    return True, len(tokens)


def _find_policy_sources(query: str) -> list[str]:
    query_normalized = _normalize_text(query)
    collection = get_mongo_collection()
    projection = {
        "_id": 0,
        "source": 1,
        "filename": 1,
        "document_name": 1,
        "title": 1,
        "category": 1,
        "document_type": 1,
    }
    records = list(collection.find({}, projection))
    named_matches: list[tuple[int, str]] = []
    category_matches: list[str] = []

    for record in records:
        source = record.get("source")
        if not source or record.get("document_type") != "policy":
            continue

        # Filename/document-name matches identify one document. Category
        # matches such as "health policy" are intentionally only a fallback;
        # otherwise a named Health_Policy_C query can match every health policy.
        named_scores = []
        for key in ("filename", "document_name", "title"):
            matched, specificity = _matches_named_document(query_normalized, record.get(key))
            if matched:
                named_scores.append(specificity)
        if named_scores:
            specificity = max(named_scores)
            named_matches.append((specificity, source))
            continue

        for variant in _metadata_variants(record):
            if _matches_policy_variant(query_normalized, variant):
                category_matches.append(source)
                break

    if named_matches:
        highest_specificity = max(score for score, _source in named_matches)
        return sorted({source for score, source in named_matches if score == highest_specificity})
    return sorted(set(category_matches))


def _build_retrieval_plan(query: str, category: str | None = None) -> RetrievalPlan:
    allow_multiple = _is_multi_document_query(query)
    inferred_categories = _infer_categories_from_query(query)
    inferred_category = category or (inferred_categories[0] if len(inferred_categories) == 1 else None)
    explicit_document = _is_explicit_document_query(query)
    policy_sources = _find_policy_sources(query)
    query_filter: dict[str, object] = {}

    if inferred_category:
        query_filter["category"] = inferred_category

    if _is_policy_query(query):
        query_filter["document_type"] = "policy"

    # If a category is provided, prefer sources that belong to that category
    # to avoid returning documents from other policy types (e.g. life vs health).
    if inferred_category and policy_sources:
        collection = get_mongo_collection()
        try:
            sources_in_category = set(collection.distinct("source", {"category": inferred_category}))
            filtered = [s for s in policy_sources if s in sources_in_category]
            if filtered:
                policy_sources = filtered
            else:
                # If none of the found policy_sources belong to the requested category,
                # ignore the name-based sources and rely on the category filter only.
                policy_sources = []
        except Exception:
            # If the DB lookup fails for any reason, fall back to conservative behavior
            # and rely only on the explicit category filter (already set above).
            policy_sources = []
    if policy_sources:
        if len(policy_sources) == 1 and not allow_multiple:
            query_filter["source"] = policy_sources[0]
        else:
            query_filter["source"] = {"$in": policy_sources}
        return RetrievalPlan(
            query_filter=query_filter,
            detected_category=inferred_category,
            detected_sources=policy_sources,
            explicit_document=explicit_document and not allow_multiple,
            allow_multiple_documents=allow_multiple,
        )

    if allow_multiple:
        if _is_policy_query(query):
            query_filter["document_type"] = "policy"
            return RetrievalPlan(query_filter=query_filter, detected_category=inferred_category, allow_multiple_documents=True)
        return RetrievalPlan(query_filter=query_filter if query_filter else None, detected_category=inferred_category, allow_multiple_documents=True)

    if _is_policy_query(query):
        return RetrievalPlan(
            query_filter=query_filter,
            detected_category=inferred_category,
            explicit_document=explicit_document,
        )

    return RetrievalPlan(
        query_filter=query_filter if query_filter else None,
        detected_category=inferred_category,
        explicit_document=explicit_document,
    )


def _build_query_filter(query: str, category: str | None = None) -> dict | None:
    return _build_retrieval_plan(query, category=category).query_filter


def _metadata_matches_plan(metadata: dict, plan: RetrievalPlan) -> bool:
    if plan.detected_category and metadata.get("category") != plan.detected_category:
        return False

    sources = plan.detected_sources or []
    if sources and metadata.get("source") not in sources:
        return False

    if plan.query_filter and plan.query_filter.get("document_type") == "policy":
        filename = metadata.get("filename") or metadata.get("document_name") or metadata.get("source") or ""
        if CLAIM_FILENAME_HINTS.search(str(filename)):
            logging.warning(
                "Policy retrieval rejected evidence-like document filename=%s document_id=%s",
                filename,
                metadata.get("document_id"),
            )
            return False

    return True


def _chunk_dedup_key(doc) -> tuple:
    meta = doc.metadata or {}
    return (
        meta.get("document_id") or meta.get("sha256") or meta.get("source") or meta.get("filename"),
        meta.get("page_label") or meta.get("page"),
        meta.get("chunk_id"),
        (doc.page_content or "")[:120],
    )


def _rerank_tokens(value: str) -> set[str]:
    return {
        token
        for token in _normalize_text(value).split()
        if len(token) > 2 and token not in RERANK_STOP_WORDS
    }


def _lexical_rerank_score(query: str, text: str) -> float:
    query_tokens = _rerank_tokens(query)
    if not query_tokens:
        return 0.0

    text_tokens = _rerank_tokens(text)
    if not text_tokens:
        return 0.0

    overlap = query_tokens.intersection(text_tokens)
    recall = len(overlap) / len(query_tokens)
    precision = len(overlap) / max(len(text_tokens), 1)
    score = (0.8 * recall) + (0.2 * precision)

    normalized_query = _normalize_text(query)
    normalized_text = _normalize_text(text)
    for phrase_size in (3, 2):
        query_parts = normalized_query.split()
        for start in range(0, max(len(query_parts) - phrase_size + 1, 0)):
            phrase = " ".join(query_parts[start : start + phrase_size])
            if phrase and phrase in normalized_text:
                score += 0.05

    return min(score, 1.0)


def _lexical_search_with_scores(query: str, query_filter: dict | None, k: int) -> list[tuple[Document, float]]:
    """Retrieve lexical matches directly from MongoDB for hybrid recall.

    Mongo Atlas vector search can miss exact policy terms such as "FIR",
    "discharge summary", or "cashless". This lightweight lexical pass gives
    those exact-match chunks a chance before the reranker chooses the final set.
    """
    tokens = _rerank_tokens(query)
    if not tokens:
        return []

    try:
        collection = get_mongo_collection()
        records = collection.find(query_filter or {})
    except Exception as exc:
        logging.warning("Hybrid lexical retrieval unavailable: %s", exc)
        return []

    scored: list[tuple[Document, float]] = []
    for record in records:
        text = record.get(MONGO_TEXT_KEY, "") or ""
        score = _lexical_rerank_score(query, text)
        if score <= 0:
            continue

        metadata = {
            key: value
            for key, value in record.items()
            if key not in {MONGO_TEXT_KEY, MONGO_EMBEDDING_KEY, "_id"}
        }
        metadata["lexical_score"] = score
        scored.append((Document(page_content=text, metadata=metadata), score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:k]


def _get_cross_encoder():
    global _CROSS_ENCODER
    if _CROSS_ENCODER is not None:
        return _CROSS_ENCODER

    try:
        from sentence_transformers import CrossEncoder

        _CROSS_ENCODER = CrossEncoder(RAG_RERANK_MODEL)
        return _CROSS_ENCODER
    except Exception as exc:
        logging.warning("Cross-encoder reranker unavailable: %s. Falling back to lexical rerank.", exc)
        return None


def _rerank_results(query: str, candidates: list[tuple[object, float, str]]) -> list[tuple[object, float, str]]:
    if not RAG_RERANK_ENABLED or len(candidates) <= 1:
        return candidates

    vector_weight = min(max(RAG_RERANK_VECTOR_WEIGHT, 0.0), 1.0)
    reranked: list[tuple[object, float, str]] = []

    cross_scores = None
    if RAG_RERANK_STRATEGY == "cross_encoder":
        cross_encoder = _get_cross_encoder()
        if cross_encoder is not None:
            pairs = [(query, doc.page_content or "") for doc, _score, _reason in candidates]
            try:
                cross_scores = [float(score) for score in cross_encoder.predict(pairs)]
            except Exception as exc:
                logging.warning("Cross-encoder rerank failed: %s. Falling back to lexical rerank.", exc)

    for index, (doc, vector_score, reason) in enumerate(candidates):
        lexical_score = _lexical_rerank_score(query, doc.page_content or "")
        if cross_scores is not None:
            rerank_signal = cross_scores[index]
        else:
            rerank_signal = lexical_score

        final_score = (vector_weight * float(vector_score)) + ((1.0 - vector_weight) * rerank_signal)
        doc.metadata["vector_score"] = float(vector_score)
        doc.metadata["rerank_score"] = float(final_score)
        doc.metadata["rerank_signal"] = float(rerank_signal)
        doc.metadata["rerank_strategy"] = "cross_encoder" if cross_scores is not None else "lexical"
        reranked.append((doc, float(final_score), f"{reason}:reranked"))

    return sorted(reranked, key=lambda item: item[1], reverse=True)


def _source_key(doc) -> str:
    meta = getattr(doc, "metadata", {}) or {}
    return str(
        meta.get("document_id")
        or meta.get("source")
        or meta.get("filename")
        or meta.get("document_name")
        or "unknown"
    )


def _diversify_multi_document_results(
    results: list[tuple[object, float, str]],
    k: int = 6,
    max_per_source: int = 2,
) -> list[tuple[object, float, str]]:
    """Keep high scoring chunks while forcing multi-policy coverage.

    For comparison/superlative questions, the answer needs evidence from each
    candidate policy. Pure top-k retrieval often returns several chunks from one
    policy, which makes the generator answer as if only that document exists.
    """
    if len(results) <= 1:
        return results[:k]

    by_source: dict[str, list[tuple[object, float, str]]] = {}
    for item in results:
        by_source.setdefault(_source_key(item[0]), []).append(item)

    if len(by_source) <= 1:
        return results[:k]

    diversified: list[tuple[object, float, str]] = []
    for source_results in by_source.values():
        source_results.sort(key=lambda item: item[1], reverse=True)
        diversified.append(source_results[0])

    remaining = [
        item
        for item in results
        if item not in diversified
    ]
    remaining.sort(key=lambda item: item[1], reverse=True)

    source_counts: dict[str, int] = {}
    final_results: list[tuple[object, float, str]] = []
    for item in sorted(diversified, key=lambda item: item[1], reverse=True):
        source = _source_key(item[0])
        source_counts[source] = source_counts.get(source, 0) + 1
        final_results.append(item)

    for item in remaining:
        if len(final_results) >= k:
            break
        source = _source_key(item[0])
        if source_counts.get(source, 0) >= max_per_source:
            continue
        source_counts[source] = source_counts.get(source, 0) + 1
        final_results.append(item)

    return final_results[:k]


def _log_retrieval_debug(question: str, plan: RetrievalPlan, accepted, rejected) -> None:
    logging.info(
        "RAG retrieval plan: question=%r detected_category=%s detected_sources=%s "
        "explicit_document=%s allow_multiple_documents=%s filter=%s threshold=%.4f",
        question,
        plan.detected_category,
        plan.detected_sources or [],
        plan.explicit_document,
        plan.allow_multiple_documents,
        plan.query_filter,
        RAG_SIMILARITY_THRESHOLD,
    )

    for label, results in (("accepted", accepted), ("rejected", rejected[:10])):
        for index, (doc, score, reason) in enumerate(results, start=1):
            meta = doc.metadata or {}
            logging.info(
                "RAG %s chunk %s: source=%s filename=%s category=%s document_type=%s "
                "page=%s chunk_id=%s score=%.4f vector_score=%s rerank_score=%s reason=%s",
                label,
                index,
                meta.get("source"),
                meta.get("filename"),
                meta.get("category"),
                meta.get("document_type"),
                meta.get("page_label") or meta.get("page"),
                meta.get("chunk_id"),
                float(score),
                meta.get("vector_score"),
                meta.get("rerank_score"),
                reason,
            )


def retrieve_documents_with_scores(
    query,
    category: str | None = None,
    override_filter: dict | None = None,
    override_plan: RetrievalPlan | None = None,
):
    vector_store = get_mongo_vector_store()
    plan = override_plan or _build_retrieval_plan(query, category=category)
    query_filter = override_filter if override_filter is not None else plan.query_filter
    if override_filter is not None:
        plan.query_filter = override_filter

    vector_docs_with_scores = vector_store.similarity_search_with_score(
        query,
        k=RAG_FETCH_K,
        filter=query_filter,
    )
    lexical_docs_with_scores = _lexical_search_with_scores(
        query,
        query_filter,
        RAG_HYBRID_LEXICAL_K,
    )
    raw_docs_with_scores = vector_docs_with_scores + lexical_docs_with_scores

    accepted_with_reason: list[tuple[object, float, str]] = []
    rejected_with_reason: list[tuple[object, float, str]] = []
    seen_keys = set()

    for doc, score in sorted(raw_docs_with_scores, key=lambda item: item[1], reverse=True):
        meta = doc.metadata or {}
        score = float(score)

        if not _metadata_matches_plan(meta, plan):
            rejected_with_reason.append((doc, score, "metadata_mismatch"))
            continue

        if score < RAG_SIMILARITY_THRESHOLD:
            rejected_with_reason.append((doc, score, "below_similarity_threshold"))
            continue

        dedup_key = _chunk_dedup_key(doc)
        if dedup_key in seen_keys:
            rejected_with_reason.append((doc, score, "duplicate_chunk"))
            continue

        seen_keys.add(dedup_key)
        doc.metadata["retrieval_score"] = score
        accepted_with_reason.append((doc, score, "accepted"))

    accepted_with_reason = _rerank_results(query, accepted_with_reason)
    if plan.allow_multiple_documents:
        accepted_with_reason = _diversify_multi_document_results(accepted_with_reason, k=6, max_per_source=2)
    else:
        accepted_with_reason = accepted_with_reason[:6]
    _log_retrieval_debug(query, plan, accepted_with_reason, rejected_with_reason)
    docs_with_scores = [(doc, score) for doc, score, _reason in accepted_with_reason]

    print("\n========== Retrieved Chunks ==========")
    if not docs_with_scores:
        print("No chunks found in the vector database.")

    for index, (doc, score) in enumerate(docs_with_scores, start=1):
        preview = " ".join(doc.page_content.split())[:250]
        source = doc.metadata.get("source", "unknown")
        filename = doc.metadata.get("filename", "unknown")
        category_value = doc.metadata.get("category", "unknown")
        page = doc.metadata.get("page_label") or doc.metadata.get("page")
        print(f"{index}. score={score:.4f} category={category_value} page={page} filename={filename} source={source}")
        print(f"   {preview}")

    return docs_with_scores


def retrieve_documents_with_scores_expanded(
    query,
    category: str | None = None,
    override_filter: dict | None = None,
    override_plan: RetrievalPlan | None = None,
    k: int = 6,
):
    """Retrieve with query decomposition/expansion while preserving scores.

    Claim analysis and confidence scoring need retrieval scores, but the older
    scored API only searched the raw query. This mirrors retrieve_documents()
    so scored callers also get decomposition, hybrid lexical recall, and
    reranking.
    """
    parts = _query_transform(query)
    forced_plan = override_plan or _build_retrieval_plan(query, category=category)
    forced_filter = override_filter if override_filter is not None else forced_plan.query_filter

    aggregated: list[tuple[object, float]] = []
    seen_keys = set()

    for part in parts:
        for expanded_query in _expand_query(part):
            results = retrieve_documents_with_scores(
                expanded_query,
                category=category,
                override_filter=forced_filter,
                override_plan=forced_plan,
            )
            for doc, score in results:
                dedup_key = _chunk_dedup_key(doc)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                doc.metadata["retrieval_query"] = expanded_query
                aggregated.append((doc, score))
            if len(aggregated) >= k:
                break
        if len(aggregated) >= k:
            break

    return aggregated[:k]


def retrieve_documents(query, category: str | None = None):
    # Transform and possibly split the query into focused sub-queries
    parts = _query_transform(query)

    # If the original query refers to a specific known source, prefer that filter
    forced_plan = _build_retrieval_plan(query, category=category)
    forced_filter = forced_plan.query_filter

    aggregated: list[tuple[object, float]] = []
    seen_keys = set()

    def _add_results(results):
        for d, s in results:
            dedup_key = _chunk_dedup_key(d)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            aggregated.append((d, s))

    # For each transformed part, run a small set of expanded queries and collect unique docs
    for part in parts:
        expansions = _expand_query(part)
        for q in expansions:
            results = retrieve_documents_with_scores(
                q,
                category=category,
                override_filter=forced_filter,
                override_plan=forced_plan,
            )
            _add_results(results)
            if len(aggregated) >= 6:
                break
        if len(aggregated) >= 6:
            break

    # Return up to 6 documents
    return [doc for doc, _score in aggregated[:6]]


def _query_transform(query: str) -> list[str]:
    """Apply basic query transformation/expansion.

    - If the query contains explicit document mentions (policy names), keep as-is and
        return single transformed query that will be filtered by source elsewhere.
    - If the query is a long compound question (contains ' and ' or comma), split into
        sub-questions to retrieve targeted context per sub-question.
    - Otherwise return the original query.
    """
    q = _normalize_text(query)
    # If contains multiple clauses separated by ' and ' or commas, split
    if "," in query or " and " in q:
        parts = [part.strip() for part in re.split(r",| and |;", query) if part.strip()]
        if len(parts) > 1:
            return parts

    return [query]


def _expand_query(query: str) -> list[str]:
    q = query.strip()
    expansions = [q]
    # Short queries get modest expansions to improve recall
    tokens = _distinctive_tokens(q)
    if tokens:
        expansions.append(" ".join(tokens))
        if len(tokens) <= 3:
            expansions.append(f"{q} coverage")
            expansions.append(f"{q} benefits")
            expansions.append(f"what is {q}")
    # Keep original at front, unique the list while preserving order
    seen = set()
    out = []
    for item in expansions:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
