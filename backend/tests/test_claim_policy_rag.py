from langchain_core.documents import Document

import claim_engine


def make_doc(document_id, document_type, category, text, score=0.7):
    return (
        Document(
            page_content=text,
            metadata={
                "document_id": document_id,
                "document_type": document_type,
                "category": category,
                "source": f"/docs/{document_id}.pdf",
                "chunk_id": 1,
            },
        ),
        score,
    )


def test_claim_context_retrieves_policy_and_claim_evidence_separately(monkeypatch):
    calls = []

    def fake_retrieve(query, override_filter=None, override_plan=None, **_kwargs):
        calls.append((query, override_filter))
        if override_filter.get("document_type") == "policy":
            return [make_doc(10, "policy", "health_policy", "Hospitalization is covered after waiting period.")]
        return [make_doc(20, "medical_report", "medical_document", "Diagnosis: hospitalization for fever.")]

    monkeypatch.setattr(claim_engine, "retrieve_documents_with_scores_expanded", fake_retrieve)

    documents, results = claim_engine._retrieve_claim_context(
        "Can I claim hospitalization?",
        policy_category="health_policy",
        policy_document_id=10,
        claim_document_ids=[20],
    )

    assert len(documents) == 2
    assert len(results) == 2
    assert {doc.metadata["evidence_role"] for doc in documents} == {"policy", "claim"}
    assert calls[0][1] == {"document_id": 10, "document_type": "policy", "category": "health_policy"}
    assert calls[1][1] == {"document_id": {"$in": [20]}}


def test_claim_category_retrieves_policy_even_when_only_claim_docs_are_selected(monkeypatch):
    filters = []

    def fake_retrieve(query, override_filter=None, override_plan=None, **_kwargs):
        filters.append(override_filter)
        if override_filter.get("document_type") == "policy":
            return [make_doc(11, "policy", "health_policy", "Room rent covered.")]
        return [make_doc(21, "hospital_bill", "medical_document", "Hospital invoice total 10000.")]

    monkeypatch.setattr(claim_engine, "retrieve_documents_with_scores_expanded", fake_retrieve)

    documents, _results = claim_engine._retrieve_claim_context(
        "Review this hospital bill",
        policy_category="health_policy",
        claim_document_ids=[21],
    )

    assert {"document_type": "policy", "category": "health_policy"} in filters
    assert {doc.metadata["evidence_role"] for doc in documents} == {"policy", "claim"}


def test_rag_evaluation_blocks_approval_without_policy_evidence():
    claim_doc = make_doc(30, "medical_report", "medical_document", "Patient was admitted.")[0]
    claim_doc.metadata["evidence_role"] = "claim"
    parsed = {
        "decision": "approved",
        "rationale": "Approved based on claim report.",
        "covered_items": [],
        "exclusions": [],
    }

    evaluation = claim_engine.evaluate_rag_grounding(parsed, [claim_doc], [0.8])

    assert evaluation["grounded"] is False
    assert "No policy document evidence was retrieved for this claim." in evaluation["warnings"]


def test_rag_evaluation_verifies_claim_fields_against_policy_evidence():
    policy_doc = make_doc(
        31,
        "policy",
        "health_policy",
        "Hospitalization is covered after a 12 month waiting period with a coverage limit of 500000.",
    )[0]
    policy_doc.metadata["evidence_role"] = "policy"
    claim_doc = make_doc(32, "medical_report", "medical_document", "Diagnosis confirms hospitalization.")[0]
    claim_doc.metadata["evidence_role"] = "claim"
    parsed = {
        "decision": "approved",
        "rationale": "Hospitalization is covered.",
        "covered_items": ["Hospitalization"],
        "exclusions": [],
        "waiting_period_months": 12,
        "coverage_limit": 500000,
    }

    evaluation = claim_engine.evaluate_rag_grounding(parsed, [policy_doc, claim_doc], [0.8, 0.7])

    assert evaluation["grounded"] is True
    assert evaluation["grounding_score"] == 1.0
    assert all(evaluation["verification_checks"].values())


def test_rag_evaluation_rejects_unsupported_coverage_item():
    policy_doc = make_doc(33, "policy", "health_policy", "Hospitalization is covered.")[0]
    policy_doc.metadata["evidence_role"] = "policy"
    parsed = {
        "decision": "approved",
        "rationale": "Dental implants are covered.",
        "covered_items": ["Dental implants"],
        "exclusions": [],
    }

    evaluation = claim_engine.evaluate_rag_grounding(parsed, [policy_doc], [0.8])

    assert evaluation["grounded"] is False
    assert evaluation["verification_checks"]["coverage"] is False


def test_policy_retrieval_never_includes_claim_documents(monkeypatch):
    filters = []

    def fake_retrieve(query, override_filter=None, override_plan=None, **_kwargs):
        filters.append(override_filter)
        return [make_doc(10, "policy", "health_policy", "Knee replacement is covered when medically necessary.")]

    monkeypatch.setattr(claim_engine, "retrieve_documents_with_scores_expanded", fake_retrieve)
    documents, _results = claim_engine._retrieve_claim_context(
        "Does my policy cover knee replacement?",
        policy_category="health_policy",
        policy_document_id=10,
        claim_document_ids=[],
    )

    assert filters == [{"document_type": "policy", "document_id": 10, "category": "health_policy"}]
    assert all(doc.metadata.get("document_type") == "policy" for doc in documents)
