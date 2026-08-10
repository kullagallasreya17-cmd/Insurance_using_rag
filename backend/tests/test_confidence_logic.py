from claim_engine import estimate_confidence_from_retrieval_scores


def test_high_confidence_for_strong_retrieval_matches():
    assert estimate_confidence_from_retrieval_scores([0.12, 0.18, 0.15]) == "high"


def test_medium_confidence_for_moderate_retrieval_matches():
    assert estimate_confidence_from_retrieval_scores([0.42, 0.38, 0.45]) == "medium"


def test_low_confidence_for_weak_or_distance_based_matches():
    assert estimate_confidence_from_retrieval_scores([1.8, 1.9, 2.1]) == "low"
