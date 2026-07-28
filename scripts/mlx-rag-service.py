#!/usr/bin/env python3
"""
MUTX MLX-Native RAG Service
Apple Silicon-native embeddings via mxbai-embed-large-v1 (MLX, M4 GPU).
Vector storage via pure SQLite + numpy cosine similarity.
No C extensions needed — fully portable.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Optional

import mlx.core as mx
import numpy as np
from mlx_embeddings import load as load_embed_model
from mlx_embeddings import generate as mlx_generate

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
import uvicorn

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("VECTOR_DB", "/Users/fortune/.openclaw/workspace/data/mlx-rag.db")
MODEL_ID = os.getenv("EMBED_MODEL", "mlx-community/mxbai-embed-large-v1")
PORT = int(os.getenv("PORT", "18792"))
TOP_K = int(os.getenv("TOP_K", "8"))
DIM = 1024  # mxbai-embed-large-v1 output dim
API_KEY = os.getenv("MLX_RAG_API_KEY")

logger = logging.getLogger(__name__)

# ── Model (loaded once, stays in M4 GPU memory) ───────────────────────────────
_model_lock = threading.Lock()
_embed_model = None
_tokenizer = None


def get_model():
    global _embed_model, _tokenizer
    if _embed_model is None:
        with _model_lock:
            if _embed_model is None:
                print(f"[mlx-rag] Loading {MODEL_ID} on Apple M4 Metal...", flush=True)
                _embed_model, _tokenizer = load_embed_model(MODEL_ID)
                print("[mlx-rag] Model loaded — ready on M4 GPU", flush=True)
    return _embed_model, _tokenizer


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts using MLX. Returns (N, DIM) float32 numpy array, L2-normalized."""
    model, tokenizer = get_model()
    output = mlx_generate(model, tokenizer, texts=texts)
    vecs = output.text_embeds
    # L2 normalize on MLX, then transfer to numpy
    norms = mx.sqrt(mx.sum(vecs**2, axis=1, keepdims=True) + 1e-8)
    vecs = (vecs / norms).astype(mx.float32)
    return vecs.tolist()


# ── Cosine similarity (pure numpy) ───────────────────────────────────────────
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity between (N, D) and (M, D) -> (N, M)."""
    dot = a @ b.T
    na = np.linalg.norm(a, axis=1, keepdims=True) + 1e-8
    nb = np.linalg.norm(b, axis=1, keepdims=True) + 1e-8
    return dot / (na * nb.T)


# ── DB ────────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS docs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id      TEXT UNIQUE NOT NULL,
            content     TEXT NOT NULL,
            metadata    TEXT DEFAULT '{}',
            created_at  REAL DEFAULT (unixepoch())
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS doc_vecs (
            doc_id  TEXT PRIMARY KEY,
            vector  BLOB NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_id ON docs(doc_id)")
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    print(f"[mlx-rag] DB ready at {DB_PATH} — {count} docs indexed", flush=True)
    return conn


# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="MUTX MLX RAG", version="1.0.0", default_response_class=ORJSONResponse)


def require_api_key(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    if not API_KEY:
        raise HTTPException(503, "MLX_RAG_API_KEY is not configured")

    bearer_token = None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            bearer_token = token

    provided_key = x_api_key or bearer_token
    if provided_key != API_KEY:
        raise HTTPException(401, "unauthorized")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        model, _ = get_model()
        return {"status": "ok", "model": MODEL_ID, "dim": DIM, "gpu": "M4 Metal"}
    except Exception:
        logger.exception("MLX RAG health check failed")
        return {"status": "degraded", "error": "service unavailable"}


# ── Embed ─────────────────────────────────────────────────────────────────────
@app.post("/embed")
def embed(texts: list[str], _auth: None = Depends(require_api_key)):
    if not texts or len(texts) > 100:
        raise HTTPException(400, "texts must be 1–100 items")
    try:
        vecs = embed_texts(texts)
        return {"vectors": vecs, "model": MODEL_ID, "count": len(vecs)}
    except Exception:
        logger.exception("Embedding request failed")
        raise HTTPException(500, "Embedding request failed")


# ── Index ─────────────────────────────────────────────────────────────────────
@app.post("/index")
def index_docs(docs: list[dict], _auth: None = Depends(require_api_key)):
    """
    Index documents. Each: {id, content, metadata: {source, title, tags}}
    Re-indexing same doc_id replaces content + vector.
    """
    if not docs:
        raise HTTPException(400, "docs list required")
    conn = get_db()
    t0 = time.time()
    for doc in docs:
        doc_id = str(doc["id"])
        content = doc["content"]
        meta = json.dumps(doc.get("metadata", {}))
        vecs = embed_texts([content])
        vec_blob = np.array(vecs[0], dtype=np.float32).tobytes()
        conn.execute("DELETE FROM docs WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM doc_vecs WHERE doc_id = ?", (doc_id,))
        conn.execute(
            "INSERT INTO docs (doc_id, content, metadata) VALUES (?, ?, ?)", (doc_id, content, meta)
        )
        conn.execute("INSERT INTO doc_vecs (doc_id, vector) VALUES (?, ?)", (doc_id, vec_blob))
    conn.commit()
    elapsed = time.time() - t0
    return {"indexed": len(docs), "seconds": round(elapsed, 2), "model": MODEL_ID}


class QueryReq(BaseModel):
    q: str
    top_k: Optional[int] = None
    hybrid: bool = False


# ── Query ─────────────────────────────────────────────────────────────────────
@app.post("/query")
def query_req(req: QueryReq, _auth: None = Depends(require_api_key)):
    """
    Semantic similarity search. Returns top-k docs ranked by cosine similarity.
    Set hybrid=true for MLX semantic + keyword boost.
    """
    q = req.q
    top_k = req.top_k if req.top_k is not None else TOP_K
    if not q or not q.strip():
        raise HTTPException(400, "query string required")

    conn = get_db()
    t0 = time.time()

    # Embed query
    qvecs = embed_texts([q])
    qvec = np.array(qvecs[0], dtype=np.float32).reshape(1, -1)

    # Fetch all doc vectors
    rows = conn.execute(
        "SELECT d.doc_id, d.content, d.metadata, v.vector FROM docs d JOIN doc_vecs v ON d.doc_id = v.doc_id"
    ).fetchall()
    if not rows:
        return {
            "query": q,
            "model": MODEL_ID,
            "results": [],
            "ms": round((time.time() - t0) * 1000),
        }

    doc_ids = [r["doc_id"] for r in rows]
    contents = [r["content"] for r in rows]
    metas = [json.loads(r["metadata"]) for r in rows]
    vec_blobs = [r["vector"] for r in rows]
    doc_vecs = np.array([np.frombuffer(v, dtype=np.float32) for v in vec_blobs])

    # Cosine similarity
    scores = cosine_similarity(qvec, doc_vecs)[0]

    if req.hybrid:
        keywords = set(q.lower().split())
        kw_scores = np.array(
            [sum(1 for kw in keywords if kw in c.lower()) / max(len(keywords), 1) for c in contents]
        )
        scores = 0.65 * scores + 0.35 * kw_scores

    # Top-k
    top_idx = np.argsort(scores)[::-1][:top_k]
    results = [
        {
            "doc_id": doc_ids[i],
            "content": contents[i][:600],
            "metadata": metas[i],
            "score": round(float(scores[i]), 4),
        }
        for i in top_idx
    ]
    return {
        "query": q,
        "model": MODEL_ID,
        "docs": len(rows),
        "results": results,
        "ms": round((time.time() - t0) * 1000),
    }


# ── Stats ─────────────────────────────────────────────────────────────────────
@app.get("/stats")
def stats(_auth: None = Depends(require_api_key)):
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    return {"docs": count, "dim": DIM, "model": MODEL_ID, "db": DB_PATH}


# ── Clear ─────────────────────────────────────────────────────────────────────
@app.post("/clear")
def clear(_auth: None = Depends(require_api_key)):
    conn = get_db()
    conn.execute("DELETE FROM docs")
    conn.execute("DELETE FROM doc_vecs")
    conn.commit()
    return {"status": "cleared"}


if __name__ == "__main__":
    init_db()
    print(f"[mlx-rag] Starting MLX RAG service on port {PORT}...", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
