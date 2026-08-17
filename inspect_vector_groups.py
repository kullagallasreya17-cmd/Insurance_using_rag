#!/usr/bin/env python
import sys

sys.path.insert(0, "backend")

from rag.vectorstore import MONGO_TEXT_KEY, get_mongo_collection


def main():
    collection = get_mongo_collection()
    pipeline = [
        {
            "$group": {
                "_id": {"source": "$source", "category": "$category"},
                "count": {"$sum": 1},
                "sample": {"$first": f"${MONGO_TEXT_KEY}"},
                "filename": {"$first": "$filename"},
                "document_id": {"$first": "$document_id"},
                "sha256": {"$first": "$sha256"},
            }
        },
        {"$sort": {"count": -1}},
    ]
    for row in collection.aggregate(pipeline):
        sample = (row.get("sample") or "").replace("\n", " ")[:140]
        group = row["_id"]
        print(
            f"category={group.get('category')} count={row['count']} "
            f"filename={row.get('filename')} document_id={row.get('document_id')} "
            f"sha256={row.get('sha256')} source={group.get('source')}"
        )
        print(f"  text={sample}")


if __name__ == "__main__":
    main()
