import logging
import numpy as np
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_community.vectorstores.documentdb import (
    DocumentDBSimilarityType,
    DocumentDBVectorSearch,
)
from pymongo import MongoClient
from pymongo.collection import Collection

from rag.embeddings import EMBEDDING_DIM, get_embeddings


dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "insurance")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "document_vectors")
MONGO_TEXT_KEY = os.getenv("MONGO_TEXT_KEY", "textContent")
MONGO_EMBEDDING_KEY = os.getenv("MONGO_EMBEDDING_KEY", "vectorContent")
MONGO_INDEX_NAME = os.getenv("MONGO_INDEX_NAME", "vectorSearchIndex")
MONGO_USE_ATLAS_SEARCH = os.getenv("MONGO_USE_ATLAS_SEARCH", "1") != "0"
MONGO_FALLBACK_TO_BRUTE_FORCE = os.getenv("MONGO_FALLBACK_TO_BRUTE_FORCE", "1") != "0"


def get_mongo_client() -> MongoClient:
    return MongoClient(MONGO_URI)


def get_mongo_collection() -> Collection:
    return get_mongo_client()[MONGO_DB][MONGO_COLLECTION]


class MongoAtlasVectorStore(DocumentDBVectorSearch):
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
        ef_search: int = 40,
        score_threshold: float = 0.0,
    ) -> List[tuple[Document, float]]:
        embeddings = self._embedding.embed_query(query)
        if not filter:
            filter = {}

        # Map enum similarity to Atlas expected string values
        similarity_value = None
        try:
            from langchain_community.vectorstores.documentdb import DocumentDBSimilarityType

            if self._similarity_type == DocumentDBSimilarityType.COS:
                similarity_value = "cosine"
            elif self._similarity_type == DocumentDBSimilarityType.EUC:
                similarity_value = "euclidean"
            elif self._similarity_type == DocumentDBSimilarityType.DOT:
                similarity_value = "dotProduct"
        except Exception:
            similarity_value = None

        pipeline = [
            {"$match": filter},
            {
                "$search": {
                    "vectorSearch": {
                        "vector": embeddings,
                        "path": self._embedding_key,
                        "similarity": similarity_value or self._similarity_type,
                        "k": k,
                        "efSearch": ef_search,
                    }
                }
            },
            {
                "$project": {
                    "similarityScore": {"$meta": "searchScore"},
                    "document": "$$ROOT",
                }
            },
        ]

        cursor = self._collection.aggregate(pipeline)
        results: List[tuple[Document, float]] = []
        for res in cursor:
            score = res.get("similarityScore", 0.0) or 0.0
            document_object = res.get("document", {})
            text = document_object.pop(self._text_key, "")
            document_object.pop(self._embedding_key, None)
            document_object.pop("_id", None)
            if score < score_threshold:
                continue
            results.append((Document(page_content=text, metadata=document_object), float(score)))

        return results


class MongoBruteForceVectorStore:
    def __init__(
        self,
        collection: Collection,
        embedding: Any,
        text_key: str,
        embedding_key: str,
        similarity: DocumentDBSimilarityType = DocumentDBSimilarityType.COS,
    ):
        self._collection = collection
        self._embedding = embedding
        self._text_key = text_key
        self._embedding_key = embedding_key
        self._similarity_type = similarity

    def index_exists(self) -> bool:
        # Brute force fallback does not require a MongoDB vector index.
        return True

    def create_index(
        self,
        dimensions: int = EMBEDDING_DIM,
        similarity: DocumentDBSimilarityType = DocumentDBSimilarityType.COS,
        **kwargs: Any,
    ) -> None:
        self._similarity_type = similarity
        # Create standard metadata indexes to support filtering.
        self._collection.create_index([("category", 1)])
        self._collection.create_index([("document_type", 1)])
        self._collection.create_index([("source", 1)])
        self._collection.create_index([("title", 1)])

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> List[Any]:
        if metadatas is None:
            metadatas = [{} for _ in texts]

        embeddings = self._embedding.embed_documents(list(texts))
        to_insert = [
            {self._text_key: text, self._embedding_key: embedding, **metadata}
            for text, metadata, embedding in zip(texts, metadatas, embeddings)
        ]
        result = self._collection.insert_many(to_insert)
        return list(result.inserted_ids)

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        **kwargs: Any,
    ) -> List[tuple[Document, float]]:
        embeddings = self._embedding.embed_query(query)
        if not filter:
            filter = {}

        query_vector = np.asarray(embeddings, dtype=np.float32)
        cursor = self._collection.find(filter)

        results: List[tuple[Document, float]] = []
        for item in cursor:
            vector = item.get(self._embedding_key)
            if vector is None:
                continue

            score = self._compute_score(query_vector, np.asarray(vector, dtype=np.float32))
            if score < score_threshold:
                continue

            metadata = {
                key: value
                for key, value in item.items()
                if key not in {self._text_key, self._embedding_key, "_id"}
            }
            results.append((Document(page_content=item.get(self._text_key, ""), metadata=metadata), float(score)))

        results.sort(key=lambda item: item[1], reverse=True)
        return results[:k]

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        *,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Document]:
        return [doc for doc, _ in self.similarity_search_with_score(query, k=k, filter=filter, **kwargs)]

    def _compute_score(self, query_vector: np.ndarray, document_vector: np.ndarray) -> float:
        if self._similarity_type == DocumentDBSimilarityType.COS:
            query_norm = np.linalg.norm(query_vector)
            document_norm = np.linalg.norm(document_vector)
            if query_norm == 0 or document_norm == 0:
                return 0.0
            return float(np.dot(query_vector, document_vector) / (query_norm * document_norm))

        if self._similarity_type == DocumentDBSimilarityType.EUC:
            return float(-np.linalg.norm(query_vector - document_vector))

        if self._similarity_type == DocumentDBSimilarityType.DOT:
            return float(np.dot(query_vector, document_vector))

        return float(np.dot(query_vector, document_vector))


def get_mongo_vector_store() -> Any:
    collection = get_mongo_collection()
    embedding_model = get_embeddings()

    if MONGO_USE_ATLAS_SEARCH:
        vector_store = MongoAtlasVectorStore(
            collection=collection,
            embedding=embedding_model,
            index_name=MONGO_INDEX_NAME,
            text_key=MONGO_TEXT_KEY,
            embedding_key=MONGO_EMBEDDING_KEY,
        )

        if not vector_store.index_exists():
            try:
                vector_store.create_index(
                    dimensions=EMBEDDING_DIM,
                    similarity=DocumentDBSimilarityType.COS,
                )
            except Exception as exc:
                logging.warning(
                    "Atlas Search index creation failed: %s. "
                    "Falling back to brute-force Mongo retrieval if enabled.",
                    exc,
                )
                if MONGO_FALLBACK_TO_BRUTE_FORCE:
                    fallback = MongoBruteForceVectorStore(
                        collection=collection,
                        embedding=embedding_model,
                        text_key=MONGO_TEXT_KEY,
                        embedding_key=MONGO_EMBEDDING_KEY,
                    )
                    fallback.create_index(
                        dimensions=EMBEDDING_DIM,
                        similarity=DocumentDBSimilarityType.COS,
                    )
                    return fallback
                raise

        # Quick runtime check to ensure Atlas search is operational; fall back if any error occurs.
        try:
            _ = vector_store.similarity_search_with_score("test connectivity check", k=1)
            return vector_store
        except Exception as exc:
            logging.warning("Atlas vector search runtime check failed: %s. Falling back to brute-force.", exc)
            if MONGO_FALLBACK_TO_BRUTE_FORCE:
                fallback = MongoBruteForceVectorStore(
                    collection=collection,
                    embedding=embedding_model,
                    text_key=MONGO_TEXT_KEY,
                    embedding_key=MONGO_EMBEDDING_KEY,
                )
                fallback.create_index(
                    dimensions=EMBEDDING_DIM,
                    similarity=DocumentDBSimilarityType.COS,
                )
                return fallback
            raise

    fallback = MongoBruteForceVectorStore(
        collection=collection,
        embedding=embedding_model,
        text_key=MONGO_TEXT_KEY,
        embedding_key=MONGO_EMBEDDING_KEY,
    )
    fallback.create_index(
        dimensions=EMBEDDING_DIM,
        similarity=DocumentDBSimilarityType.COS,
    )
    return fallback


def normalize_similarity_score(raw_score: Any) -> float:
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return float("inf")

    if 0.0 <= score <= 1.0:
        return 1.0 - score

    return score
