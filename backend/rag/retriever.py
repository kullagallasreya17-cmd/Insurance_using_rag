from rag.vectorstore import get_mongo_vector_store


def retrieve_documents_with_scores(query, category: str | None = None):
    vector_store = get_mongo_vector_store()
    query_filter = {"category": category} if category else None

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
