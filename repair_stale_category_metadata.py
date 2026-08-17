#!/usr/bin/env python
import sys

sys.path.insert(0, "backend")

from rag.vectorstore import get_mongo_collection


SOURCE_CATEGORY_REPAIRS = {
    "/app/documents/policy_e752bd96e0494bb5af13dc9e05ef5ab9_Insurance_FAQ_Sample.pdf": {
        "category": "faq",
        "filename": "Insurance_FAQ_Sample.pdf",
        "document_name": "Insurance_FAQ_Sample",
    },
    "/app/documents/policy_85df692057344ca19f18ce154f836624_claim_procedure_sample.pdf": {
        "category": "claim_procedure",
        "filename": "claim_procedure_sample.pdf",
        "document_name": "claim_procedure_sample",
    },
    "/app/documents/policy_65ed7e1b46dc46f0980af794a220d49a_Life Insurance Policy.pdf": {
        "category": "life_policy",
        "filename": "Life Insurance Policy.pdf",
        "document_name": "Life Insurance Policy",
    },
    "/app/documents/policy_caeb9d4f80d6474d9069dfbbc4cfac5e_Life Insurance Policy.pdf": {
        "category": "life_policy",
        "filename": "Life Insurance Policy.pdf",
        "document_name": "Life Insurance Policy",
    },
    "/app/documents/policy_203d4e95b8344c7b9725983ca1cf05f0_Medical_Patient_document.pdf": {
        "category": "medical_document",
        "filename": "Medical_Patient_document.pdf",
        "document_name": "Medical_Patient_document",
    },
}


def main():
    collection = get_mongo_collection()
    for source, metadata in SOURCE_CATEGORY_REPAIRS.items():
        result = collection.update_many(
            {"source": source},
            {"$set": {"document_type": "policy", **metadata}},
        )
        print(
            f"source={source} category={metadata['category']} "
            f"matched={result.matched_count} modified={result.modified_count}"
        )


if __name__ == "__main__":
    main()
