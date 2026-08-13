import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from rag.vectorstore import get_mongo_collection, get_mongo_vector_store


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


def _normalize_text(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_compare_query(query: str) -> bool:
    normalized = _normalize_text(query)
    return bool(re.search(r"\b(compare|versus|vs|v\.|different|difference|both|either)\b", normalized))


def _is_policy_query(query: str) -> bool:
    normalized = _normalize_text(query)
    return bool(re.search(r"\b(policy|policies|insurance)\b", normalized))


def _token_set(value: str) -> set[str]:
    return {token for token in (value or "").split() if len(token) > 2}


def _distinctive_tokens(value: str) -> list[str]:
    return [
        token
        for token in _normalize_text(value).split()
        if len(token) > 2 and token not in POLICY_STOP_WORDS
    ]


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

        # Match natural user mentions like "auto secure" from
        # "Auto Secure Policy.pdf" without requiring the file extension/path.
        for size in range(2, len(distinctive) + 1):
            for start in range(0, len(distinctive) - size + 1):
                variants.add(" ".join(distinctive[start : start + size]))

    return {variant for variant in variants if variant}


def _matches_policy_variant(query: str, variant: str) -> bool:
    if not variant:
        return False

    variant_tokens = _distinctive_tokens(variant)
    if not variant_tokens:
        return False

    if variant in query:
        return True

    query_tokens = _token_set(query)
    if len(variant_tokens) == 1:
        return variant_tokens[0] in query_tokens

    return set(variant_tokens).issubset(query_tokens)


def _find_policy_sources(query: str) -> list[str]:
    query_normalized = _normalize_text(query)
    collection = get_mongo_collection()
    sources = collection.distinct("source")
    titles = collection.distinct("title")
    matches: list[str] = []

    for source in sources:
        for variant in _policy_variants(source):
            if _matches_policy_variant(query_normalized, variant):
                matches.append(source)
                break

    for title in titles:
        for variant in _policy_variants(title):
            if _matches_policy_variant(query_normalized, variant):
                policy_sources = collection.distinct("source", {"title": title})
                matches.extend(policy_sources)
                break

    return sorted(set(matches))


def _build_query_filter(query: str, category: str | None = None) -> dict | None:
    policy_sources = _find_policy_sources(query)
    query_filter: dict[str, object] = {}

    if category:
        query_filter["category"] = category

    if policy_sources:
        if len(policy_sources) == 1:
            if _is_compare_query(query):
                # A compare query referencing one known policy should broaden the search
                # to all policies rather than restricting to a single source.
                if _is_policy_query(query):
                    query_filter["document_type"] = "policy"
                return query_filter
            query_filter["source"] = policy_sources[0]
        else:
            query_filter["source"] = {"$in": policy_sources}
        return query_filter

    if _is_compare_query(query):
        if _is_policy_query(query):
            query_filter["document_type"] = "policy"
            return query_filter
        return query_filter if query_filter else None

    if _is_policy_query(query):
        query_filter["document_type"] = "policy"
        return query_filter

    return query_filter if query_filter else None


def retrieve_documents_with_scores(query, category: str | None = None):
    vector_store = get_mongo_vector_store()
    query_filter = _build_query_filter(query, category=category)

    docs_with_scores = vector_store.similarity_search_with_score(
        query,
        k=6,
        filter=query_filter,
    )
    docs_with_scores = sorted(docs_with_scores, key=lambda item: item[1], reverse=True)[:6]

    print("\n========== Retrieved Chunks ==========")
    if not docs_with_scores:
        print("No chunks found in the vector database.")

    for index, (doc, score) in enumerate(docs_with_scores, start=1):
        preview = " ".join(doc.page_content.split())[:250]
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page_label") or doc.metadata.get("page")
        print(f"{index}. score={score:.4f} page={page} source={source}")
        print(f"   {preview}")

    return docs_with_scores


def retrieve_documents(query, category: str | None = None):
    docs_with_scores = retrieve_documents_with_scores(query, category=category)
    return [doc for doc, _score in docs_with_scores]
