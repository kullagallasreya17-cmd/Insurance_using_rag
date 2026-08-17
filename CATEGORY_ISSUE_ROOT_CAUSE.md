## CATEGORY INDEXING ISSUE - ROOT CAUSE ANALYSIS

### THE PROBLEM

**Symptoms:**
- vehicle_policy vectors: 0 (should have many)
- health_policy vectors: 22 ✓
- travel_policy vectors: 2 ✓
- **other vectors: 494 (93% - CRITICAL!)**

### THE ROOT CAUSE FOUND

**Documents collection shows correct categories:**
```
Document: Sample_Vehicle_Insurance_Policy.pdf
  Stored category: vehicle_policy ✓
  Status: indexed ✓
  BUT: 0 vectors found for this document ❌
```

**Vector collection shows wrong categories:**
```
Vectors for vehicle_policy document are stored as: other
  Text content: "Any accidental loss or damage suffered whilst the Insured..."
  This is clearly vehicle insurance content
  BUT stored with category: "other"
```

### WHY THIS HAPPENED

The documents were indexed **BEFORE** the category parameter support was added to the system. When initial documents were bulk-indexed, they were created with a default category value of **"other"**.

### VERIFICATION

From diagnostic output:
- Documents table (source of truth): 5 documents with correct categories
- Vectors table (indexed content): 494 vectors with "other" category
- This mismatch proves vectors were indexed without category metadata

### THE FIX - TWO STEPS REQUIRED

#### STEP 1: Clean Old Incorrect Vectors
Delete all vectors indexed with incorrect categories to avoid retrieval confusion:

```bash
# Clear all vectors indexed with "other" category
docker compose exec -T backend python -c "
from rag.vectorstore import get_mongo_collection
collection = get_mongo_collection()
result = collection.delete_many({'category': 'other'})
print(f'Deleted {result.deleted_count} incorrectly categorized vectors')
"
```

#### STEP 2: Re-Index Documents with Correct Category
Re-upload or re-trigger indexing for documents with correct category parameter:

```bash
# For each document that needs re-indexing:
curl -X POST "http://localhost:8000/upload/claim?category=health_policy" \
  -H "Authorization: Bearer <your_token>" \
  -F "file=@path/to/file.pdf"
```

OR use the backend directly:

```bash
docker compose exec -T backend python -c "
from database import get_database
from main import enqueue_indexing_job

db = get_database()
docs = db.documents.find({'category': {'$in': ['vehicle_policy', 'travel_policy']}})

for doc in docs:
    print(f'Re-enqueueing: {doc[\"filename\"]} -> {doc[\"category\"]}')
    enqueue_indexing_job({
        'document_id': doc['id'],
        'document_type': doc['document_type'],
        'category': doc['category'],
        'content_type': doc['content_type'],
        'uploaded_by': doc['uploaded_by'],
        'filename': doc['filename'],
    })
"
```

### VERIFICATION COMMAND

After re-indexing, verify the fix:

```bash
python diagnose_category_issue.py
```

Expected result:
```
Vectors by category:
  vehicle_policy:   N vectors
  health_policy:   22 vectors
  travel_policy:    K vectors
  other:            0 vectors  ← Should be ZERO
```

### WHY THIS HAPPENED ORIGINALLY

The codebase appears to have had these old indexed documents from before the category feature was properly implemented. When the system was set up, documents may have been indexed with:
- Default category = "other"
- No category parameter in the indexing job
- Or a bug that defaulted to "other"

The code itself is correct - category is properly passed through:
- upload_document() → enqueue_indexing_job() → process_indexing_job() → index_document()
- index_document() properly sets: `page.metadata["category"] = category`
- MongoBruteForceVectorStore properly stores: `{text_key: text, embedding_key: embedding, **metadata}`

The fix is simply to re-index these documents with the correct category parameter.

### TESTING AFTER FIX

1. Upload a test vehicle policy with category="vehicle_policy"
2. Verify it appears in MongoDB with correct category
3. Run: `python test_vectorstore.py` should return results for vehicle_policy query
4. Run: `python diagnose_category_issue.py` should show 0 vectors in "other"
