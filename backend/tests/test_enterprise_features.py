from main import get_accessible_categories
from claim_engine import estimate_confidence_from_retrieval_scores


def test_agent_role_has_restricted_document_categories():
    accessible = get_accessible_categories("agent")
    assert "health_policy" in accessible
    assert "vehicle_policy" in accessible
    assert "life_policy" in accessible
    assert "home_policy" in accessible
    assert "travel_policy" in accessible
    assert "terms_conditions" not in accessible


def test_admin_role_has_full_document_categories():
    accessible = get_accessible_categories("admin")
    assert accessible is None


def test_supported_policy_categories_include_real_insurance_types():
    from main import KNOWLEDGE_CATEGORIES

    required = {"health_policy", "vehicle_policy", "life_policy", "home_policy", "travel_policy", "other"}
    missing = sorted(required - set(KNOWLEDGE_CATEGORIES))
    assert not missing, f"Missing policy categories: {missing}"


def test_strong_retrieval_scores_raise_high_confidence():
    assert estimate_confidence_from_retrieval_scores([0.05, 0.08]) == "high"
