COLLECTIONS = {
    "health_policy": "health_policy",
    "vehicle_policy": "vehicle_policy",
    "life_policy": "life_policy",
    "home_policy": "home_policy",
    "travel_policy": "travel_policy",
    "personal_accident_policy": "personal_accident_policy",
    "critical_illness_policy": "critical_illness_policy",
    "property_policy": "property_policy",
    "claim_procedure": "claim_procedure",
    "medical_document": "medical_document",
    "other": "other",
}


def resolve_collection(category: str) -> str:
    return COLLECTIONS.get(category, "documents")
