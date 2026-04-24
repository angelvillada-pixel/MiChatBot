"""
═══════════════════════════════════════════════════════════════════════
 embeddings.py — M2: Embeddings locales con fallback robusto
═══════════════════════════════════════════════════════════════════════

Intenta cargar sentence-transformers (MiniLM-L6-v2, ~22 MB).
Si no está disponible → usa un fallback hashing + TF característico
que genera vectores de 128 dims deterministas y comparables.

Exporta:
  embed(text)              → np.ndarray (float32)
  embed_to_blob(text)      → bytes       (para guardar en DB)
  blob_to_vec(blob)        → np.ndarray
  cosine(a, b)             → float
  semantic_search(query, corpus, top_k) → List[(score, item)]
"""
import os
import struct
import hashlib
import math
from typing import List, Tuple, Any, Optional

import numpy as np

# ──────────────────────────────────────────────────────────────────────
# Carga lazy del modelo principal
# ──────────────────────────────────────────────────────────────────────
_MODEL = None
_MODEL_LOADED = False
_MODEL_FAILED = False
EMBED_DIM_REAL     = 384   # MiniLM-L6-v2
EMBED_DIM_FALLBACK = 128

FORCE_FALLBACK = os.environ.get("EMBEDDINGS_FALLBACK", "0") == "1"

def _try_load_model():
    """Intenta cargar sentence-transformers de forma lazy."""
    global _MODEL, _MODEL_LOADED, _MODEL_FAILED
    if _MODEL_LOADED or _MODEL_FAILED or FORCE_FALLBACK:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        _MODEL_LOADED = True
        print("[embeddings] MiniLM-L6-v2 cargado OK")
    except Exception as e:
        _MODEL_FAILED = True
        print(f"[embeddings] Fallback hashing activo: {e}")
    return _MODEL

# ──────────────────────────────────────────────────────────────────────
# Fallback hashing deterministic embedding
# ──────────────────────────────────────────────────────────────────────
def _fallback_embed(text: str) -> np.ndarray:
    """
    Embedding por hashing + TF:
    - Tokeniza a palabras
    - Cada palabra → bucket[hash(word) mod 128]
    - Normaliza L2
    """
    text = (text or "").lower()
    words = [w for w in text.split() if len(w) > 1]
    vec = np.zeros(EMBED_DIM_FALLBACK, dtype=np.float32)
    if not words:
        return vec
    for w in words:
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
        idx = h % EMBED_DIM_FALLBACK
        vec[idx] += 1.0
        # Pequeña difusión a buckets vecinos para reducir colisiones
        vec[(idx + 1) % EMBED_DIM_FALLBACK] += 0.25
    # Normalización L2
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.astype(np.float32)

# ──────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────
def embed(text: str) -> np.ndarray:
    """Devuelve un vector np.float32. Usa MiniLM si está disponible, si no fallback."""
    text = (text or "")[:2000]
    if not text.strip():
        dim = EMBED_DIM_REAL if (_MODEL_LOADED and not FORCE_FALLBACK) else EMBED_DIM_FALLBACK
        return np.zeros(dim, dtype=np.float32)

    model = _try_load_model()
    if model is not None:
        try:
            v = model.encode(text, normalize_embeddings=True)
            return np.asarray(v, dtype=np.float32)
        except Exception:
            pass
    return _fallback_embed(text)

def embed_to_blob(text: str) -> bytes:
    """Serializa el embedding a bytes para guardar en la DB."""
    v = embed(text)
    # Formato: [dim:int32][float32 * dim]
    return struct.pack("<i", len(v)) + v.tobytes()

def blob_to_vec(blob: bytes) -> Optional[np.ndarray]:
    """Deserializa bytes a np.ndarray. Robusto a blobs corruptos."""
    if not blob or len(blob) < 4:
        return None
    try:
        dim = struct.unpack("<i", blob[:4])[0]
        data = blob[4:4 + dim * 4]
        if len(data) != dim * 4:
            return None
        return np.frombuffer(data, dtype=np.float32)
    except Exception:
        return None

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Similaridad coseno tolerante a vectores de distinta dimensión."""
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return 0.0
    if len(a) != len(b):
        # Dimensiones distintas (ej. uno MiniLM, otro fallback) → 0
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

def semantic_search(
    query: str,
    corpus: List[Tuple[Any, bytes]],
    top_k: int = 5,
    min_score: float = 0.25,
) -> List[Tuple[float, Any]]:
    """
    corpus: lista de (item, blob) donde blob es la serialización del embedding.
    Devuelve lista de (score, item) ordenada desc, filtrada por min_score.
    """
    qv = embed(query)
    scored: List[Tuple[float, Any]] = []
    for item, blob in corpus:
        v = blob_to_vec(blob)
        if v is None:
            continue
        s = cosine(qv, v)
        if s >= min_score:
            scored.append((s, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]

def is_real_model() -> bool:
    """Útil para /health — indica si MiniLM está activo."""
    _try_load_model()
    return bool(_MODEL_LOADED and not FORCE_FALLBACK)
