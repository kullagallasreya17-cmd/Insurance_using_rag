from main import get_accessible_categories
from claim_engine import estimate_confidence_from_retrieval_scores


def test_agent_role_has_restricted_document_categories():
    accessible = get_accessible_categories("agent")
    assert "health_policy" in accessible
    assert "terms_conditions" not in accessible


def test_admin_role_has_full_document_categories():
    accessible = get_accessible_categories("admin")
    assert accessible is None


def test_strong_retrieval_scores_raise_high_confidence():
    assert estimate_confidence_from_retrieval_scores([0.05, 0.08]) == "high"
