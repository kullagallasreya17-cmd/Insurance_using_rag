#!/usr/bin/env python3
"""
Setup script to pre-download the HuggingFace embedding model locally.
Run this ONCE with internet access to cache the model for offline use.

This solves the WinError 10013 socket permission error by pre-downloading
the sentence-transformers/all-MiniLM-L6-v2 model locally.

Usage:
    python setup_embeddings.py
"""

import os
from pathlib import Path

# Set up cache directory BEFORE importing the embeddings module
CACHE_DIR = Path(__file__).parent / ".cache" / "huggingface"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(CACHE_DIR)

print(f"📦 HuggingFace Cache Directory: {CACHE_DIR}")
print(f"📥 Starting model download (this may take 1-2 minutes)...\n")

try:
    from sentence_transformers import SentenceTransformer
    
    print("⏳ Downloading sentence-transformers/all-MiniLM-L6-v2...")
    model = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2",
        cache_folder=str(CACHE_DIR)
    )
    
    print("\n✅ Model downloaded and cached successfully!")
    print(f"   Location: {CACHE_DIR}")
    print(f"\n💾 The model is now cached locally (~120MB).")
    print(f"   Future runs will use this cached copy without needing internet.\n")
    
    # Verify the model works
    print("🧪 Testing model...")
    test_embedding = model.encode("Test sentence")
    print(f"✅ Model test successful! Embedding dimension: {len(test_embedding)}\n")
    
    print("🎉 Setup complete! You can now:")
    print("   1. Stop this script (Ctrl+C)")
    print("   2. Start your backend: python -m uvicorn main:app --reload")
    print("   3. Document uploads will now work without socket errors!\n")
    
except ImportError:
    print("❌ Error: sentence-transformers not installed")
    print("   Run: pip install sentence-transformers langchain-huggingface")
except Exception as e:
    print(f"❌ Error downloading model: {str(e)}")
    print(f"\n💡 If you see a socket/firewall error:")
    print(f"   1. Temporarily disable Windows Firewall")
    print(f"   2. Run this script again")
    print(f"   3. Re-enable Windows Firewall when done")
    print(f"   4. The model will be cached for future offline use")
