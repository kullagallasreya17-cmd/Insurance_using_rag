#!/usr/bin/env python
import sys

sys.path.insert(0, "backend")

from database import get_db
from rag.vectorstore import MONGO_TEXT_KEY, get_mongo_collection


VEHICLE_FILENAME = "Sample_Vehicle_Insurance_Policy.pdf"
HEALTH_FILENAME = "insurance_policy.pdf"
VEHICLE_SOURCE = "/app/documents/policy_2291f5b8712945af8efcacedcba932bc_Sample_Vehicle_Insurance_Policy.pdf"
HEALTH_SOURCE = "/app/documents/policy_9953ea8312bd432ca344a8a1ac3df654_insurance_policy.pdf"


def main():
    db = next(get_db())
    collection = get_mongo_collection()

    vehicle_doc = db.documents.find_one({"filename": VEHICLE_FILENAME}, {"_id": 0, "id": 1})
    health_doc = db.documents.find_one({"filename": HEALTH_FILENAME}, {"_id": 0, "id": 1})

    vehicle_id = vehicle_doc.get("id") if vehicle_doc else None
    health_id = health_doc.get("id") if health_doc else None

    vehicle_filter = {
        "source": VEHICLE_SOURCE,
    }
    vehicle_update = {
        "$set": {
            "category": "vehicle_policy",
            "document_type": "policy",
            "filename": VEHICLE_FILENAME,
            "document_name": "Sample_Vehicle_Insurance_Policy",
        }
    }
    if vehicle_id is not None:
        vehicle_update["$set"]["document_id"] = vehicle_id

    health_filter = {
        "source": HEALTH_SOURCE,
    }
    health_update = {
        "$set": {
            "category": "health_policy",
            "document_type": "policy",
            "filename": HEALTH_FILENAME,
            "document_name": "insurance_policy",
        }
    }
    if health_id is not None:
        health_update["$set"]["document_id"] = health_id

    vehicle_result = collection.update_many(vehicle_filter, vehicle_update)
    health_result = collection.update_many(health_filter, health_update)

    if health_id is not None:
        db.documents.update_one(
            {"id": health_id},
            {"$set": {"category": "health_policy", "document_type": "policy"}},
        )

    print(
        "vehicle_chunks_matched=",
        vehicle_result.matched_count,
        "vehicle_chunks_modified=",
        vehicle_result.modified_count,
    )
    print(
        "health_chunks_matched=",
        health_result.matched_count,
        "health_chunks_modified=",
        health_result.modified_count,
    )
    if health_id is not None:
        print(f"document_id={health_id} recategorized_to=health_policy")


if __name__ == "__main__":
    main()
