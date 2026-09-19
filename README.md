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