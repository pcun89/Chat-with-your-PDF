"""
Optional production vector store: Postgres + pgvector on Cloud SQL.

This is NOT wired in by default (rag.py uses InMemoryVectorStore so the demo
runs with zero infra). Swap it in when you need documents to survive a
Cloud Run cold start/restart, or to support many users/documents at once.

Setup:
    1. Cloud SQL for Postgres instance, with the pgvector extension enabled:
         CREATE EXTENSION IF NOT EXISTS vector;
    2. pip install "psycopg[binary]"
    3. Run the schema below once.
    4. In rag.py, replace `STORE = InMemoryVectorStore()` with
       `STORE = PgVectorStore(os.environ["DATABASE_URL"])`

Schema:
    CREATE TABLE documents (
        id UUID PRIMARY KEY,
        filename TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE chunks (
        id UUID PRIMARY KEY,
        document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
        page INT NOT NULL,
        text TEXT NOT NULL,
        embedding VECTOR(3072)  -- match your embedding model's output dim
    );

    CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);

Why this is the production-shaped answer: an HNSW index gives sub-linear
approximate nearest-neighbor search instead of the O(n) numpy scan the
in-memory store does, which matters once you have many documents loaded
at once rather than one document per session.
"""

from __future__ import annotations

import uuid
from typing import Optional

import numpy as np

from rag import Chunk, Document


class PgVectorStore:
    def __init__(self, database_url: str):
        import psycopg  # imported lazily so this file doesn't break installs
        self._psycopg = psycopg
        self._database_url = database_url

    def _connect(self):
        return self._psycopg.connect(self._database_url)

    def add_document(self, filename: str, chunks: list[Chunk], embeddings: np.ndarray) -> str:
        doc_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO documents (id, filename) VALUES (%s, %s)",
                    (doc_id, filename),
                )
                for chunk, vec in zip(chunks, embeddings):
                    cur.execute(
                        "INSERT INTO chunks (id, document_id, page, text, embedding) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (chunk.id, doc_id, chunk.page, chunk.text, vec.tolist()),
                    )
            conn.commit()
        return doc_id

    def search(self, doc_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[Chunk, float]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, page, text, 1 - (embedding <=> %s::vector) AS cosine_sim
                    FROM chunks
                    WHERE document_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (query_vector.tolist(), doc_id, query_vector.tolist(), top_k),
                )
                rows = cur.fetchall()
        return [(Chunk(id=r[0], text=r[2], page=r[1]), float(r[3])) for r in rows]

    def get_document(self, doc_id: str) -> Optional[Document]:
        # Only used by the in-memory store's existence check in main.py;
        # for pgvector, `search` returning [] already signals "not found".
        return None

    def delete_document(self, doc_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            conn.commit()
