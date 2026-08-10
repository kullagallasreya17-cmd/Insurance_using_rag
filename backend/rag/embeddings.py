import hashlib
import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv


load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / ".cache" / "huggingface"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(CACHE_DIR)

EMBEDDING_DIM = 384
HF_EMBEDDING_MODEL = os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_EMBEDDINGS = None


class LocalEmbeddings:
    """Fallback implementation used only if Hugging Face is disabled."""

    def __init__(self, embedding_dim: int = EMBEDDING_DIM):
        self.embedding_dim = embedding_dim

    def _hash_to_vector(self, text: str) -> np.ndarray:
        hash_obj = hashlib.sha256(text.lower().encode())
        hash_int = int(hash_obj.hexdigest(), 16)

        np.random.seed(hash_int % (2**31))
        embedding = np.random.randn(self.embedding_dim).astype(np.float32)

        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def embed_query(self, text: str) -> list:
        return self._hash_to_vector(text).tolist()

    def embed_documents(self, texts: list) -> list:
        return [self._hash_to_vector(text).tolist() for text in texts]


def get_embeddings():
    """Use Hugging Face semantic embeddings by default for real RAG retrieval."""
    global _EMBEDDINGS
    if _EMBEDDINGS is not None:
        return _EMBEDDINGS

    if os.getenv("USE_HUGGINGFACE", "1") == "1":
        try:
            from langchain_huggingface import HuggingFaceEmbeddings

            _EMBEDDINGS = HuggingFaceEmbeddings(
                model_name=HF_EMBEDDING_MODEL,
                encode_kwargs={"normalize_embeddings": True},
                cache_folder=str(CACHE_DIR),
            )
            print(f"Using HuggingFace embeddings: {HF_EMBEDDING_MODEL}")
            return _EMBEDDINGS
        except Exception as exc:
            print(f"HuggingFace embeddings unavailable: {exc}")
            print("  Falling back to local embeddings...")

    _EMBEDDINGS = LocalEmbeddings(embedding_dim=EMBEDDING_DIM)
    print("Using local offline embeddings (fallback only)")
    return _EMBEDDINGS
