#!/usr/bin/env python
"""Test vectorstore functionality."""
import sys
import io
sys.path.insert(0, 'd:/projects/Insurance_using_RAG/backend')

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from rag.vectorstore import get_mongo_vector_store

try:
    print("Initializing vectorstore...")
    vs = get_mongo_vector_store()
    print(f'[OK] Vectorstore type: {type(vs).__name__}')
    
    print("\nSearching for 'vehicle policy coverage'...")
    result = vs.similarity_search_with_score(
        'vehicle policy coverage', 
        k=3, 
        filter={'category': 'vehicle_policy'}
    )
    print(f'[OK] Found {len(result)} results')
    
    for i, (doc, score) in enumerate(result, 1):
        source = doc.metadata.get('source', '?')
        excerpt = doc.page_content[:100].replace('\n', ' ')
        print(f'\n{i}. Score: {score:.4f}')
        print(f'   Source: {source}')
        print(f'   Text: {excerpt}...')
    
    print("\n" + "="*50)
    print("[OK] Vectorstore is working correctly!")
    
except Exception as e:
    import traceback
    print(f'\n[ERROR] {type(e).__name__}: {e}')
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
