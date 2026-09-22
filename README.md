# 📄 Chat with your PDF

**Ask questions about any PDF and get answers grounded in cited excerpts from the document — not the model's general knowledge.**

**A retrieval-augmented generation (RAG) pipeline built from scratch: no LangChain, no managed vector database. Every step — chunking, embedding, retrieval, generation — is plain, readable code, so nothing is a black box.**

## Why this exists

Most "chat with your docs" demos wrap an API call and call it a day. This one is built to be *explained*, not just run — every design decision below has a reason behind it, because the interesting part of RAG isn't calling an LLM, it's everything that happens before the LLM is called.

## Stack

| Layer        | Choice                                                                 |
|--------------|-------------------------------------------------------------------------|
| Frontend     | React + Vite → GitHub Pages                                            |
| Backend      | FastAPI → Google Cloud Run                                             |
| Embeddings   | Gemini `gemini-embedding-001`                                          |
| Chat model   | Gemini `gemini-2.5-flash`                                              |
| Vector store | In-memory cosine search (numpy) by default; drop-in Postgres + pgvector implementation included for persistence at scale |

## Features

- 📎 Drag-and-drop PDF upload, parsed and indexed in seconds
- 💬 Multi-turn chat that stays grounded in the source document
- 🔍 Every answer shows its receipts — hoverable citation chips reveal the exact page and excerpt the model retrieved
- 🚫 Explicit "not in this document" responses instead of hallucinated guesses
- ⚡ Zero-infra by default (in-memory vector store); Cloud SQL + pgvector path included for production scale

## Run it locally

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your GEMINI_API_KEY — free at aistudio.google.com/app/apikey
uvicorn main:app --reload --port 8000
```
**Frontend**
```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_URL=http://localhost:8000
npm run dev
```

Open the printed `localhost:5173` URL, drop in a PDF, start asking questions.

## Deploying

**Backend → Cloud Run**
```bash
cd backend
gcloud run deploy chat-with-pdf-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=YOUR_KEY,ALLOWED_ORIGINS=https://YOUR_GH_USERNAME.github.io
```

**Frontend → GitHub Pages**
- Push to `main` with `.github/workflows/deploy-frontend.yml` in place
- Set a repo secret `VITE_API_URL` to your Cloud Run URL
- Enable Pages in repo settings (source: GitHub Actions)
- Or deploy manually: `cd frontend && npm run build && npm run deploy`

## How it works

**1. Chunking.** Paragraph-aware sliding window: paragraphs accumulate up to `CHUNK_SIZE_CHARS` (default 1000 chars), then a chunk is flushed and the next one carries over the previous chunk's tail (`CHUNK_OVERLAP_CHARS`, default 150). Fixed-size character splitting slices sentences in half mid-thought; pure paragraph splitting gives wildly inconsistent chunk sizes. This is the middle ground — and the overlap means a fact straddling a paragraph break still has one chunk that contains it whole.

**2. Embedding asymmetry.** Chunks are embedded with `task_type="RETRIEVAL_DOCUMENT"`, questions with `RETRIEVAL_QUERY` — two different embedding modes optimized for being-found vs. finding, respectively. Using the same mode for both measurably hurts recall.

**3. Grounding, not guessing.** The system prompt instructs the model to answer *only* from retrieved excerpts and say plainly when the document doesn't cover something. Every claim carries a `(p. N)` citation, and the UI surfaces the actual retrieved snippets as hoverable chips — retrieval quality is auditable, not just trusted.

**4. Retrieval.** Cosine similarity over normalized embedding vectors, top-5 by default. With one document per session, a numpy matrix scan beats a network round-trip to a vector DB and costs nothing to run. `pgvector_store.py` shows the swap-in path (Cloud SQL + HNSW index) for many documents/users and persistence across restarts.

**5. Cost/latency.** Uploads batch embedding calls (up to 90 chunks per request) instead of one call per chunk. Generation uses `gemini-2.5-flash` rather than a heavier model, because answer quality here is bottlenecked by retrieval relevance, not model size.

**Failure modes handled explicitly:** scanned PDFs with no text layer, oversized uploads, and a clear message when a document has expired from memory rather than a generic 404.

## What's intentionally left out

- **Auth / multi-tenancy** — out of scope for a demo; would add a user table and scope vector search by `(user_id, document_id)`
- **Streaming responses** — answers return in one shot via `generate_content`; swapping to `generate_content_stream` + SSE is the clear next step for long answers
- **OCR for scanned PDFs** — would need a Vision/OCR pass before chunking