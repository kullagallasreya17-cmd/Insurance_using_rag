import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_community.vectorstores.documentdb import (
    DocumentDBSimilarityType,
)
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.operations import SearchIndexModel

from rag.embeddings import EMBEDDING_DIM, get_embeddings


# ============================================================
# ENVIRONMENT
# ============================================================

dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path)

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017"
)

MONGO_DB = os.getenv(
    "MONGO_DB",
    "insurance"
)

MONGO_COLLECTION = os.getenv(
    "MONGO_COLLECTION",
    "document_vectors"
)

MONGO_TEXT_KEY = os.getenv(
    "MONGO_TEXT_KEY",
    "textContent"
)

MONGO_EMBEDDING_KEY = os.getenv(
    "MONGO_EMBEDDING_KEY",
    "embedding"
)

MONGO_INDEX_NAME = os.getenv(
    "MONGO_INDEX_NAME",
    "vectorSearchIndex"
)

MONGO_USE_ATLAS_SEARCH = (
    os.getenv("MONGO_USE_ATLAS_SEARCH", "1") != "0"
)

MONGO_FALLBACK_TO_BRUTE_FORCE = (
    os.getenv("MONGO_FALLBACK_TO_BRUTE_FORCE", "1") != "0"
)


# ============================================================
# MONGODB CONNECTION
# ============================================================

def get_mongo_client() -> MongoClient:
    """
    Create MongoDB client.
    """
    return MongoClient(MONGO_URI)


def get_mongo_collection() -> Collection:
    """
    Return the document_vectors collection.
    """
    client = get_mongo_client()

    return client[MONGO_DB][MONGO_COLLECTION]


# ============================================================
# ATLAS VECTOR SEARCH INDEX
# ============================================================

def create_atlas_vector_search_index() -> None:
    """
    Create MongoDB Atlas Vector Search index.

    This uses the modern PyMongo SearchIndexModel API instead
    of DocumentDBVectorSearch.create_index().
    """

    collection = get_mongo_collection()

    index_definition = {
        "fields": [
            {
                "type": "vector",
                "path": MONGO_EMBEDDING_KEY,
                "numDimensions": EMBEDDING_DIM,
                "similarity": "cosine",
            },

            # Fields that may be used for filtering.
            {
                "type": "filter",
                "path": "document_id",
            },
            {
                "type": "filter",
                "path": "document_type",
            },
            {
                "type": "filter",
                "path": "category",
            },
        ]
    }

    index_model = SearchIndexModel(
        definition=index_definition,
        name=MONGO_INDEX_NAME,
        type="vectorSearch",
    )

    logging.info(
        "Creating MongoDB Atlas Vector Search index: %s",
        MONGO_INDEX_NAME,
    )

    result = collection.create_search_index(
        model=index_model
    )

    logging.info(
        "Atlas Vector Search index creation requested: %s",
        result,
    )


def atlas_index_exists() -> bool:
    """
    Check whether the configured Atlas Vector Search index exists.
    """

    collection = get_mongo_collection()

    try:
        indexes = collection.list_search_indexes()

        for index in indexes:
            if index.get("name") == MONGO_INDEX_NAME:
                logging.info(
                    "Atlas Vector Search index exists: %s",
                    MONGO_INDEX_NAME,
                )
                return True

        logging.warning(
            "Atlas Vector Search index does not exist: %s",
            MONGO_INDEX_NAME,
        )

        return False

    except Exception as exc:
        logging.warning(
            "Could not check Atlas Vector Search indexes: %s",
            exc,
        )

        return False


# ============================================================
# ATLAS VECTOR SEARCH STORE
# ============================================================

class MongoAtlasVectorStore:

    def __init__(
        self,
        collection: Collection,
        embedding: Any,
        index_name: str,
        text_key: str,
        embedding_key: str,
    ):
        self._collection = collection
        self._embedding = embedding
        self._index_name = index_name
        self._text_key = text_key
        self._embedding_key = embedding_key

    # --------------------------------------------------------
    # INDEX CHECK
    # --------------------------------------------------------

    def index_exists(self) -> bool:

        try:

            indexes = self._collection.list_search_indexes()

            for index in indexes:

                if index.get("name") == self._index_name:

                    status = index.get("status")

                    logging.info(
                        "Atlas index '%s' found. Status=%s",
                        self._index_name,
                        status,
                    )

                    return True

            return False

        except Exception as exc:

            logging.warning(
                "Unable to check Atlas Vector Search index: %s",
                exc,
            )

            return False

    # --------------------------------------------------------
    # ADD TEXTS
    # --------------------------------------------------------

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> List[Any]:

        texts = list(texts)

        if metadatas is None:

            metadatas = [
                {}
                for _ in texts
            ]

        if len(texts) != len(metadatas):

            raise ValueError(
                "texts and metadatas must have the same length"
            )

        logging.info(
            "Generating embeddings for %d chunks",
            len(texts),
        )

        embeddings = self._embedding.embed_documents(
            texts
        )

        documents = []

        for text, metadata, embedding in zip(
            texts,
            metadatas,
            embeddings,
        ):

            document = {
                self._text_key: text,
                self._embedding_key: embedding,
                **metadata,
            }

            documents.append(document)

        if not documents:
            return []

        result = self._collection.insert_many(
            documents
        )

        logging.info(
            "Inserted %d chunks into MongoDB",
            len(result.inserted_ids),
        )

        return list(result.inserted_ids)

    # --------------------------------------------------------
    # VECTOR SEARCH
    # --------------------------------------------------------

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        **kwargs: Any,
    ) -> List[tuple[Document, float]]:

        logging.info(
            "Generating embedding for query"
        )

        query_embedding = (
            self._embedding.embed_query(query)
        )

        vector_search_stage = {
            "$vectorSearch": {
                "index": self._index_name,
                "path": self._embedding_key,
                "queryVector": query_embedding,
                "numCandidates": max(k * 20, 100),
                "limit": k,
            }
        }

        # ----------------------------------------------------
        # Optional MongoDB filters
        # ----------------------------------------------------

        if filter:

            vector_search_stage[
                "$vectorSearch"
            ]["filter"] = filter

        pipeline = [
            vector_search_stage,

            {
                "$project": {
                    "_id": 0,

                    self._text_key: 1,

                    "document_id": 1,
                    "document_type": 1,
                    "category": 1,
                    "source": 1,
                    "filename": 1,
                    "document_name": 1,
                    "title": 1,
                    "page": 1,
                    "page_label": 1,
                    "chunk_id": 1,
                    "sha256": 1,

                    "score": {
                        "$meta": "vectorSearchScore"
                    },
                }
            },
        ]

        logging.info(
            "Executing MongoDB Atlas Vector Search"
        )

        cursor = self._collection.aggregate(
            pipeline
        )

        results: List[
            tuple[Document, float]
        ] = []

        for item in cursor:

            score = float(
                item.pop(
                    "score",
                    0.0
                )
            )

            if score < score_threshold:
                continue

            text = item.pop(
                self._text_key,
                ""
            )

            metadata = {
                key: value
                for key, value in item.items()
                if key not in {
                    self._embedding_key,
                    "_id",
                }
            }

            document = Document(
                page_content=text,
                metadata=metadata,
            )

            results.append(
                (
                    document,
                    score,
                )
            )

        logging.info(
            "Atlas Vector Search returned %d results",
            len(results),
        )

        return results

    # --------------------------------------------------------
    # SIMPLE SEARCH
    # --------------------------------------------------------

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        *,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Document]:

        results = (
            self.similarity_search_with_score(
                query=query,
                k=k,
                filter=filter,
                **kwargs,
            )
        )

        return [
            document
            for document, _ in results
        ]


# ============================================================
# BRUTE FORCE FALLBACK
# ============================================================

class MongoBruteForceVectorStore:

    def __init__(
        self,
        collection: Collection,
        embedding: Any,
        text_key: str,
        embedding_key: str,
        similarity: DocumentDBSimilarityType =
            DocumentDBSimilarityType.COS,
    ):

        self._collection = collection
        self._embedding = embedding
        self._text_key = text_key
        self._embedding_key = embedding_key
        self._similarity_type = similarity

    # --------------------------------------------------------
    # INDEX
    # --------------------------------------------------------

    def index_exists(self) -> bool:

        return True

    def create_index(
        self,
        dimensions: int = EMBEDDING_DIM,
        similarity: DocumentDBSimilarityType =
            DocumentDBSimilarityType.COS,
        **kwargs: Any,
    ) -> None:

        self._similarity_type = similarity

        self._collection.create_index(
            [("category", 1)]
        )

        self._collection.create_index(
            [("document_type", 1)]
        )

        self._collection.create_index(
            [("source", 1)]
        )

        self._collection.create_index(
            [("title", 1)]
        )

    # --------------------------------------------------------
    # INSERT
    # --------------------------------------------------------

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> List[Any]:

        texts = list(texts)

        if metadatas is None:

            metadatas = [
                {}
                for _ in texts
            ]

        embeddings = (
            self._embedding.embed_documents(
                texts
            )
        )

        documents = []

        for text, metadata, embedding in zip(
            texts,
            metadatas,
            embeddings,
        ):

            documents.append(
                {
                    self._text_key: text,
                    self._embedding_key: embedding,
                    **metadata,
                }
            )

        if not documents:
            return []

        result = (
            self._collection.insert_many(
                documents
            )
        )

        return list(
            result.inserted_ids
        )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        **kwargs: Any,
    ) -> List[tuple[Document, float]]:

        query_embedding = (
            self._embedding.embed_query(query)
        )

        if not filter:
            filter = {}

        query_vector = np.asarray(
            query_embedding,
            dtype=np.float32,
        )

        cursor = self._collection.find(
            filter
        )

        results = []

        for item in cursor:

            vector = item.get(
                self._embedding_key
            )

            if vector is None:
                continue

            document_vector = np.asarray(
                vector,
                dtype=np.float32,
            )

            score = self._compute_score(
                query_vector,
                document_vector,
            )

            if score < score_threshold:
                continue

            metadata = {
                key: value
                for key, value in item.items()
                if key not in {
                    self._text_key,
                    self._embedding_key,
                    "_id",
                }
            }

            document = Document(
                page_content=item.get(
                    self._text_key,
                    "",
                ),
                metadata=metadata,
            )

            results.append(
                (
                    document,
                    float(score),
                )
            )

        results.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return results[:k]

    # --------------------------------------------------------
    # SIMPLE SEARCH
    # --------------------------------------------------------

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        *,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Document]:

        return [
            document
            for document, _ in
            self.similarity_search_with_score(
                query,
                k=k,
                filter=filter,
                **kwargs,
            )
        ]

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    def _compute_score(
        self,
        query_vector: np.ndarray,
        document_vector: np.ndarray,
    ) -> float:

        if (
            self._similarity_type ==
            DocumentDBSimilarityType.COS
        ):

            query_norm = np.linalg.norm(
                query_vector
            )

            document_norm = np.linalg.norm(
                document_vector
            )

            if (
                query_norm == 0
                or document_norm == 0
            ):
                return 0.0

            return float(
                np.dot(
                    query_vector,
                    document_vector,
                )
                /
                (
                    query_norm
                    *
                    document_norm
                )
            )

        if (
            self._similarity_type ==
            DocumentDBSimilarityType.EUC
        ):

            return float(
                -np.linalg.norm(
                    query_vector
                    -
                    document_vector
                )
            )

        if (
            self._similarity_type ==
            DocumentDBSimilarityType.DOT
        ):

            return float(
                np.dot(
                    query_vector,
                    document_vector,
                )
            )

        return float(
            np.dot(
                query_vector,
                document_vector,
            )
        )


# ============================================================
# GET VECTOR STORE
# ============================================================

def get_mongo_vector_store() -> Any:

    collection = get_mongo_collection()

    # Load embedding model
    embedding_model = get_embeddings()

    # ========================================================
    # ATLAS VECTOR SEARCH
    # ========================================================

    if MONGO_USE_ATLAS_SEARCH:

        try:

            # Check whether index already exists
            if not atlas_index_exists():

                logging.info(
                    "Atlas Vector Search index not found."
                )

                create_atlas_vector_search_index()

                logging.info(
                    "Atlas Vector Search index creation "
                    "requested. It may take some time "
                    "to become READY."
                )

            else:

                logging.info(
                    "Using existing Atlas Vector Search "
                    "index: %s",
                    MONGO_INDEX_NAME,
                )

            return MongoAtlasVectorStore(
                collection=collection,
                embedding=embedding_model,
                index_name=MONGO_INDEX_NAME,
                text_key=MONGO_TEXT_KEY,
                embedding_key=MONGO_EMBEDDING_KEY,
            )

        except Exception as exc:

            logging.exception(
                "Atlas Vector Search initialization failed."
            )

            logging.warning(
                "Reason: %s",
                exc,
            )

            # =================================================
            # FALLBACK
            # =================================================

            if MONGO_FALLBACK_TO_BRUTE_FORCE:

                logging.warning(
                    "Falling back to brute-force "
                    "MongoDB vector retrieval."
                )

                fallback = (
                    MongoBruteForceVectorStore(
                        collection=collection,
                        embedding=embedding_model,
                        text_key=MONGO_TEXT_KEY,
                        embedding_key=MONGO_EMBEDDING_KEY,
                    )
                )

                fallback.create_index(
                    dimensions=EMBEDDING_DIM,
                    similarity=(
                        DocumentDBSimilarityType.COS
                    ),
                )

                return fallback

            raise

    # ========================================================
    # BRUTE FORCE ONLY
    # ========================================================

    logging.info(
        "MongoDB Atlas Vector Search disabled."
    )

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


# ============================================================
# NORMALIZE SCORE
# ============================================================

def normalize_similarity_score(
    raw_score: Any,
) -> float:

    try:

        score = float(raw_score)

    except (TypeError, ValueError):

        return float("inf")

    if 0.0 <= score <= 1.0:

        return 1.0 - score

    return score
