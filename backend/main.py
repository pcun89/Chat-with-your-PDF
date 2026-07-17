"""
FastAPI backend for the Chat-with-your-PDF demo.

Endpoints:
  POST   /api/documents        upload a PDF, returns {document_id, num_pages, num_chunks}
  POST   /api/chat             ask a question about a previously uploaded document
  DELETE /api/documents/{id}   drop a document from memory
  GET    /api/health           liveness check for Cloud Run
"""

import rag
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, HTTPException, UploadFile
import os
import time

from dotenv import load_dotenv

load_dotenv()  # local dev convenience; Cloud Run uses real env vars


app = FastAPI(title="Chat with your PDF", version="1.0.0")

ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB, generous for a resume/report demo


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    document_id: str
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = []


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    num_pages: int
    num_chunks: int
    elapsed_ms: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/documents", response_model=UploadResponse)
def upload_document(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "application/octet-stream") and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file.")

    pdf_bytes = file.file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(400, "PDF is too large (max 20MB for this demo).")
    if not pdf_bytes:
        raise HTTPException(400, "Uploaded file is empty.")

    start = time.time()

    pages = rag.extract_pages(pdf_bytes)
    if not any(p.strip() for p in pages):
        raise HTTPException(
            422,
            "No extractable text found. This PDF may be a scanned image without "
            "an OCR text layer, which this demo doesn't process.",
        )

    chunks = rag.chunk_pages(pages)
    if not chunks:
        raise HTTPException(422, "Couldn't split this PDF into chunks.")

    try:
        embeddings = rag.embed_texts([c.text for c in chunks])
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    doc_id = rag.STORE.add_document(file.filename, chunks, embeddings)
    elapsed_ms = int((time.time() - start) * 1000)

    return UploadResponse(
        document_id=doc_id,
        filename=file.filename,
        num_pages=len(pages),
        num_chunks=len(chunks),
        elapsed_ms=elapsed_ms,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    doc = rag.STORE.get_document(req.document_id)
    if doc is None:
        raise HTTPException(
            404, "Document not found. It may have expired - try re-uploading.")

    try:
        result = rag.answer_question(
            req.document_id,
            req.question,
            history=[t.model_dump() for t in req.history],
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    return ChatResponse(**result)


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str):
    rag.STORE.delete_document(document_id)
    return {"status": "deleted"}
