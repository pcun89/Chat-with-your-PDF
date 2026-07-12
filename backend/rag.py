"""
Core RAG (Retrieval-Augmented Generation) logic.

Pipeline:
  1. extract_pages()   -> raw text per PDF page
  2. chunk_pages()     -> overlapping text chunks, each tagged with its source page
  3. embed_texts()     -> Gemini embedding vectors for each chunk
  4. VectorStore        -> in-memory cosine-similarity search over chunk embeddings
  5. answer_question() -> retrieve top-k chunks, build a grounded prompt, call Gemini

Everything here is intentionally framework-light so it's easy to talk through
in an interview: there's no hidden magic, just chunking -> embedding -> cosine
similarity -> prompt stuffing.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from pypdf import PdfReader
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
CHAT_MODEL = os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE_CHARS", "1000"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP_CHARS", "150"))
TOP_K = int(os.environ.get("TOP_K", "5"))

_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """Lazily build a single shared Gemini client (reads GEMINI_API_KEY from env)."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy backend/.env.example to backend/.env "
                "and add your key from https://aistudio.google.com/app/apikey"
            )
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# 1. PDF extraction
# ---------------------------------------------------------------------------

def extract_pages(pdf_bytes: bytes) -> list[str]:
    """Return a list of page texts (index 0 = page 1)."""
    reader = PdfReader(__import__("io").BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        # Collapse whitespace noise that PDF extraction tends to introduce.
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        pages.append(text.strip())
    return pages


# ---------------------------------------------------------------------------
# 2. Chunking
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id: str
    text: str
    page: int  # 1-indexed


def chunk_pages(pages: list[str], chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """
    Paragraph-aware sliding window chunking.

    Why this approach (good interview talking point): naive fixed-size
    character splitting cuts sentences in half, which hurts both embedding
    quality and the model's ability to quote cleanly. Splitting purely by
    paragraph leaves chunks wildly different sizes, which hurts retrieval
    consistency. So we accumulate whole paragraphs up to `chunk_size`, then
    slide back `overlap` characters so a fact split across a paragraph
    boundary still has a chunk that contains it whole.
    """
    chunks: list[Chunk] = []

    for page_num, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue

        paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
        buffer = ""

        def flush(buf: str):
            if buf.strip():
                chunks.append(Chunk(id=str(uuid.uuid4())[
                              :8], text=buf.strip(), page=page_num))

        for para in paragraphs:
            if len(buffer) + len(para) + 1 <= chunk_size:
                buffer = f"{buffer}\n{para}".strip()
            else:
                if buffer:
                    flush(buffer)
                    # carry overlap from the tail of the previous buffer
                    tail = buffer[-overlap:] if overlap > 0 else ""
                    buffer = f"{tail}\n{para}".strip()
                else:
                    # single paragraph longer than chunk_size: hard-split it
                    for i in range(0, len(para), chunk_size - overlap):
                        flush(para[i:i + chunk_size])
                    buffer = ""
        flush(buffer)

    return chunks


# ---------------------------------------------------------------------------
# 3. Embeddings
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> np.ndarray:
    """
    Embed a batch of strings with Gemini's embedding model.

    task_type matters: RETRIEVAL_DOCUMENT optimizes chunk vectors for being
    *found*, RETRIEVAL_QUERY optimizes a question vector for *finding things*.
    Using the right one measurably improves retrieval quality over using
    the same embedding mode for both sides.
    """
    if not texts:
        return np.zeros((0, 1))

    client = get_client()
    vectors: list[list[float]] = []

    # Batch to stay well under request size limits.
    batch_size = 90
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.models.embed_content(
            model=EMBED_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        vectors.extend([e.values for e in response.embeddings])

    return np.array(vectors, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text], task_type="RETRIEVAL_QUERY")[0]


# ---------------------------------------------------------------------------
# 4. Vector store (in-memory, cosine similarity)
# ---------------------------------------------------------------------------
#
# This is deliberately a plain numpy matrix, not a vector DB. For a single
# document per session this is faster than network round-trips to Postgres
# and has zero infra cost - a reasonable production choice, not a shortcut.
# `pgvector_store.py` next to this file is a drop-in alternative with the
# same interface, backed by Cloud SQL + the pgvector extension, for when
# you need persistence across many documents/users.

@dataclass
class Document:
    id: str
    filename: str
    chunks: list[Chunk]
    embeddings: np.ndarray  # shape (n_chunks, dim), L2-normalized


class InMemoryVectorStore:
    def __init__(self):
        self._docs: dict[str, Document] = {}

    def add_document(self, filename: str, chunks: list[Chunk], embeddings: np.ndarray) -> str:
        doc_id = str(uuid.uuid4())
        norm = embeddings / \
            np.clip(np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8, None)
        self._docs[doc_id] = Document(
            id=doc_id, filename=filename, chunks=chunks, embeddings=norm)
        return doc_id

    def get_document(self, doc_id: str) -> Optional[Document]:
        return self._docs.get(doc_id)

    def delete_document(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)

    def search(self, doc_id: str, query_vector: np.ndarray, top_k: int = TOP_K) -> list[tuple[Chunk, float]]:
        doc = self._docs.get(doc_id)
        if doc is None or len(doc.chunks) == 0:
            return []
        q = query_vector / max(np.linalg.norm(query_vector), 1e-8)
        scores = doc.embeddings @ q  # cosine similarity since both sides are normalized
        top_idx = np.argsort(-scores)[:top_k]
        return [(doc.chunks[i], float(scores[i])) for i in top_idx]


STORE = InMemoryVectorStore()


# ---------------------------------------------------------------------------
# 5. Answer generation
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are a careful research assistant answering questions about ONE uploaded PDF.

Rules:
- Answer ONLY using the excerpts provided in the context below. Do not use outside knowledge.
- If the excerpts don't contain the answer, say clearly that the document doesn't appear to cover it. Never guess or fabricate.
- When you state a fact, cite the page it came from like this: (p. 4).
- Keep answers concise and direct. Use bullet points for lists.
"""


def build_context(retrieved: list[tuple[Chunk, float]]) -> str:
    parts = []
    for chunk, score in retrieved:
        parts.append(
            f"[Page {chunk.page} | relevance {score:.2f}]\n{chunk.text}")
    return "\n\n---\n\n".join(parts)


def answer_question(doc_id: str, question: str, history: list[dict] | None = None) -> dict:
    query_vec = embed_query(question)
    retrieved = STORE.search(doc_id, query_vec, top_k=TOP_K)

    if not retrieved:
        return {
            "answer": "I couldn't find an indexed document with that ID. Try uploading the PDF again.",
            "sources": [],
        }

    context = build_context(retrieved)

    history_text = ""
    if history:
        history_text = "\n".join(
            f"{turn['role'].upper()}: {turn['content']}" for turn in history[-6:]
        )

    prompt = f"""{history_text}

CONTEXT EXCERPTS FROM THE DOCUMENT:
{context}

QUESTION: {question}

Answer using only the context above, with page citations like (p. N)."""

    client = get_client()
    response = client.models.generate_content(
        model=CHAT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            max_output_tokens=1024,
        ),
    )

    sources = [
        {
            "page": chunk.page,
            "relevance": round(score, 3),
            "snippet": (chunk.text[:240] + "...") if len(chunk.text) > 240 else chunk.text,
        }
        for chunk, score in retrieved
    ]

    return {"answer": response.text, "sources": sources}
