from langchain_core.documents import Document

import claim_engine
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
    monkeypatch.setattr(retriever, "RAG_RERANK_ENABLED", True)
    monkeypatch.setattr(retriever, "RAG_RERANK_STRATEGY", "lexical")
    monkeypatch.setattr(retriever, "RAG_RERANK_VECTOR_WEIGHT", 0.65)
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


def test_named_policy_query_does_not_match_every_policy_in_category(monkeypatch):
    policy_a = make_doc("/docs/Health_Policy_A.pdf", "Health_Policy_A.pdf", "health_policy", "Hospitalization cover.", 0.9)
    policy_c = make_doc("/docs/Health_Policy_C.pdf", "Health_Policy_C.pdf", "health_policy", "Knee replacement cover.", 0.8)
    install_fake_rag(monkeypatch, [policy_a, policy_c])

    docs = retriever.retrieve_documents("Summarize the Health_Policy_C document")

    assert {doc.metadata["filename"] for doc in docs} == {"Health_Policy_C.pdf"}
    assert {doc.metadata["document_type"] for doc in docs} == {"policy"}


def test_policy_retrieval_rejects_evidence_like_stale_policy_metadata(monkeypatch):
    stale_report = make_doc(
        "/docs/jayadeva_knee_surgery_sample_patient_report.pdf",
        "jayadeva_knee_surgery_sample_patient_report.pdf",
        "health_policy",
        "Patient diagnosis and surgery report.",
        0.95,
    )
    policy = make_doc("/docs/Health_Policy.pdf", "Health_Policy.pdf", "health_policy", "Hospitalization coverage.", 0.8)
    install_fake_rag(monkeypatch, [stale_report, policy])

    docs = retriever.retrieve_documents("Does my health policy cover hospitalization?")

    assert {doc.metadata["filename"] for doc in docs} == {"Health_Policy.pdf"}


def test_reranker_promotes_more_query_specific_chunk(monkeypatch):
    broad_cover = make_doc(
        "/docs/Vehicle_Policy.pdf",
        "Vehicle_Policy.pdf",
        "vehicle_policy",
        "Vehicle policy coverage includes collision fire theft and accidental damage.",
        0.9,
        chunk_id=1,
    )
    claim_documents = make_doc(
        "/docs/Vehicle_Policy.pdf",
        "Vehicle_Policy.pdf",
        "vehicle_policy",
        "Vehicle claim required documents include RC driving licence policy copy repair estimate and FIR.",
        0.4,
        chunk_id=2,
    )
    install_fake_rag(monkeypatch, [broad_cover, claim_documents])
    monkeypatch.setattr(retriever, "RAG_RERANK_VECTOR_WEIGHT", 0.0)

    docs = retriever.retrieve_documents("What documents are required for a vehicle claim?")

    assert docs[0].metadata["chunk_id"] == 2
    assert docs[0].metadata["rerank_strategy"] == "lexical"
    assert docs[0].metadata["rerank_score"] > docs[0].metadata["vector_score"]


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


def test_highest_coverage_question_keeps_policy_citations_separate(monkeypatch):
    health_high = make_doc(
        "/docs/Health_Policy.pdf",
        "Health_Policy.pdf",
        "health_policy",
        "Health policy coverage limit is 500000 for hospitalization.",
        0.92,
        chunk_id=1,
    )
    health_extra = make_doc(
        "/docs/Health_Policy.pdf",
        "Health_Policy.pdf",
        "health_policy",
        "Health policy room rent and ambulance coverage details.",
        0.88,
        chunk_id=2,
    )
    vehicle = make_doc(
        "/docs/Vehicle_Policy.pdf",
        "Vehicle_Policy.pdf",
        "vehicle_policy",
        "Vehicle policy coverage limit is 300000 for accident repair.",
        0.35,
        chunk_id=1,
    )
    install_fake_rag(monkeypatch, [health_high, health_extra, vehicle])

    docs = retriever.retrieve_documents("Which policy has the highest coverage?")
    citations = claim_engine.build_document_citations(docs)

    assert {doc.metadata["filename"] for doc in docs} == {"Health_Policy.pdf", "Vehicle_Policy.pdf"}
    assert {citation["filename"] for citation in citations} == {"Health_Policy.pdf", "Vehicle_Policy.pdf"}
