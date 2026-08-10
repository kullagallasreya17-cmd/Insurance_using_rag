COLLECTIONS = {
    "health_policy": "health_policy",
    "vehicle_policy": "vehicle_policy",
    "life_policy": "life_policy",
    "claim_procedure": "claim_procedure",
    "medical_document": "medical_document",
}


def resolve_collection(category: str) -> str:
    return COLLECTIONS.get(category, "documents")
