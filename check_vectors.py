#!/usr/bin/env python
"""Check MongoDB vector collection statistics."""
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, 'd:/projects/Insurance_using_RAG/backend')

from rag.vectorstore import get_mongo_collection

try:
    collection = get_mongo_collection()
    total = collection.count_documents({})
    print(f"\nTotal vectors in MongoDB: {total}")
    print("\nVectors by category:")
    
    categories = [c for c in collection.distinct('category') if c is not None]
    for cat in sorted(categories):
        count = collection.count_documents({'category': cat})
        print(f"  {cat}: {count}")
    
    # Check for None categories
    none_count = collection.count_documents({'category': None})
    if none_count > 0:
        print(f"  [None]: {none_count}")
    
    print("\nSample documents (first 3):")
    for i, doc in enumerate(collection.find().limit(3), 1):
        source = doc.get('source', '?')
        category = doc.get('category', '?')
        text_preview = doc.get('textContent', '')[:80]
        print(f"\n{i}. Source: {source}")
        print(f"   Category: {category}")
        print(f"   Text: {text_preview}...")

except Exception as e:
    import traceback
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)
