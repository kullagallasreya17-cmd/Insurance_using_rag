from langchain_core.documents import Document

from rag import generator, retriever


class FakeCollection:
    def __init__(self, records):
        self.records = records

    def find(self, query=None, projection=None):
        query = query or {}
        return [record for record in self.records if self._matches(record, query)]

    def distinct(self, field, query=None):
        values = []
        for record in self.find(query or {}):
            if field in record and record[field] not in values:
                values.append(record[field])
        return values

    def _matches(self, record, query):
        for key, expected in query.items():
            actual = record.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True


class FakeVectorStore:
    def __init__(self, docs_with_scores):
        self.docs_with_scores = docs_with_scores

    def similarity_search_with_score(self, query, k=4, filter=None):
        filter = filter or {}
        results = []
        for doc, score in self.docs_with_scores:
            if FakeCollection([])._matches(doc.metadata, filter):
                results.append((doc, score))
        return results[:k]


def make_doc(source, filename, category, text, score, chunk_id=1):
    return (
        Document(
            page_content=text,
            metadata={
                "source": source,
                "filename": filename,
                "document_name": filename.removesuffix(".pdf"),
                "document_type": "policy",
                "category": category,
                "chunk_id": chunk_id,
            },
        ),
        score,
    )


def install_fake_rag(monkeypatch, docs_with_scores):
    records = [doc.metadata for doc, _score in docs_with_scores]
    monkeypatch.setattr(retriever, "get_mongo_collection", lambda: FakeCollection(records))
    monkeypatch.setattr(retriever, "get_mongo_vector_store", lambda: FakeVectorStore(docs_with_scores))
    monkeypatch.setattr(retriever, "RAG_SIMILARITY_THRESHOLD", 0.15)
    monkeypatch.setattr(generator, "RAG_SIMILARITY_THRESHOLD", 0.15)


def test_vehicle_policy_document_retrieves_only_vehicle_chunks(monkeypatch):
    health = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Health hospitalization waiting period.", 0.95)
    vehicle = make_doc("/docs/Vehicle_Policy.pdf", "Vehicle_Policy.pdf", "vehicle_policy", "Vehicle collision fire theft cover.", 0.35)
    install_fake_rag(monkeypatch, [health, vehicle])

    docs = retriever.retrieve_documents("Summarize the vehicle_policy document")

    assert docs
    assert {doc.metadata["filename"] for doc in docs} == {"Vehicle_Policy.pdf"}
    assert {doc.metadata["category"] for doc in docs} == {"vehicle_policy"}


def test_vehicle_policy_summary_keeps_multiple_vehicle_chunks(monkeypatch):
    health = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Health hospitalization waiting period.", 0.95)
    vehicle_cover = make_doc(
        "/docs/Vehicle_Policy.pdf",
        "Vehicle_Policy.pdf",
        "vehicle_policy",
        "Vehicle collision fire theft cover.",
        0.45,
        chunk_id=1,
    )
    vehicle_claims = make_doc(
        "/docs/Vehicle_Policy.pdf",
        "Vehicle_Policy.pdf",
        "vehicle_policy",
        "Vehicle claim process and required documents.",
        0.4,
        chunk_id=2,
    )
    install_fake_rag(monkeypatch, [health, vehicle_cover, vehicle_claims])

    docs = retriever.retrieve_documents("Summarize the vehicle_policy document")

    assert [doc.metadata["chunk_id"] for doc in docs] == [1, 2]
    assert {doc.metadata["filename"] for doc in docs} == {"Vehicle_Policy.pdf"}


def test_vehicle_policy_cover_uses_vehicle_category(monkeypatch):
    health = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Hospitalization cover.", 0.99)
    vehicle = make_doc("/docs/Vehicle_Policy.pdf", "Vehicle_Policy.pdf", "vehicle_policy", "Covers accidental damage, collision, fire, and theft.", 0.4)
    install_fake_rag(monkeypatch, [health, vehicle])

    docs = retriever.retrieve_documents("What does the vehicle policy cover?")

    assert [doc.metadata["filename"] for doc in docs] == ["Vehicle_Policy.pdf"]


def test_vehicle_policy_exclusions_do_not_include_health_policy(monkeypatch):
    health = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Pre-existing disease waiting period exclusion.", 0.92)
    vehicle = make_doc("/docs/Vehicle_Policy.pdf", "Vehicle_Policy.pdf", "vehicle_policy", "Exclusions include wear and tear and driving without license.", 0.37)
    install_fake_rag(monkeypatch, [health, vehicle])

    docs = retriever.retrieve_documents("What are the exclusions in the vehicle policy?")

    assert docs
    assert all(doc.metadata["category"] == "vehicle_policy" for doc in docs)


def test_vehicle_policy_missing_waiting_period_does_not_use_health_policy(monkeypatch):
    health = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Pre-existing diseases have a 36-month waiting period.", 0.98)
    weak_vehicle = make_doc("/docs/Vehicle_Policy.pdf", "Vehicle_Policy.pdf", "vehicle_policy", "Vehicle policy covers collision.", 0.05)
    install_fake_rag(monkeypatch, [health, weak_vehicle])

    docs = retriever.retrieve_documents("What is the waiting period for pre-existing diseases in the vehicle policy?")
    answer = generator.generate_answer("What is the waiting period for pre-existing diseases in the vehicle policy?", docs)

    assert docs == []
    assert answer == generator.INSUFFICIENT_CONTEXT_ANSWER


def test_health_policy_document_retrieves_only_health_chunks(monkeypatch):
    vehicle = make_doc("/docs/Vehicle_Policy.pdf", "Vehicle_Policy.pdf", "vehicle_policy", "Vehicle collision cover.", 0.9)
    health = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Health hospitalization cover.", 0.3)
    install_fake_rag(monkeypatch, [vehicle, health])

    docs = retriever.retrieve_documents("Summarize the health policy document")

    assert [doc.metadata["filename"] for doc in docs] == ["Health_Policy.pdf"]


def test_compare_vehicle_and_health_allows_both_documents(monkeypatch):
    vehicle = make_doc("/docs/Vehicle_Policy.pdf", "Vehicle_Policy.pdf", "vehicle_policy", "Vehicle collision cover.", 0.4)
    health = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Health hospitalization cover.", 0.35)
    install_fake_rag(monkeypatch, [vehicle, health])

    docs = retriever.retrieve_documents("Compare the vehicle policy and health policy")

    assert {doc.metadata["filename"] for doc in docs} == {"Vehicle_Policy.pdf", "Health_Policy.pdf"}
