"""
═══════════════════════════════════════════════════════════════════════════
 learning_engine.py · DeepNova v7.0 · Motor de Aprendizaje Continuo
═══════════════════════════════════════════════════════════════════════════
 Implementa RLHF-lite (Reinforcement Learning from Human Feedback) en un
 entorno sin GPU: refuerzo de patrones exitosos según el feedback del
 usuario (+1 / -1), vocabulario adaptativo, detección de preferencias
 estilísticas y mejora de prompts en runtime.

 Diseño:
   • 100% aditivo · no rompe nada
   • Cero dependencias pesadas (solo stdlib + numpy si está)
   • Persistencia opcional a través del módulo `database` ya existente
   • Thread-safe

 Áreas cubiertas (del documento de mejoras):
   ✓ 1.1 Algoritmos de aprendizaje (refuerzo basado en feedback)
   ✓ 1.2 Actualizaciones de conocimiento (vocab + preferencias)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os
import re
import json
import time
import math
import hashlib
import threading
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Any, Optional

# ──────────────────────────────────────────────────────────────────────
#  Config
# ──────────────────────────────────────────────────────────────────────
LEARNING_ENABLED = os.environ.get("LEARNING_ENABLED", "1") == "1"
LEARNING_FILE    = os.environ.get("LEARNING_FILE", "learning_state.json")
MAX_PATTERNS     = 5000           # límite de patrones registrados
DECAY_HALFLIFE   = 30 * 24 * 3600 # 30 días: los patrones antiguos pierden peso

_lock = threading.RLock()


# ──────────────────────────────────────────────────────────────────────
#  Estado in-memory (con persistencia perezosa)
# ──────────────────────────────────────────────────────────────────────
class _State:
    def __init__(self) -> None:
        # patrón → {score, n_pos, n_neg, last_seen, examples}
        self.patterns: Dict[str, Dict[str, Any]] = {}
        # vocab por usuario → Counter
        self.user_vocab: Dict[str, Counter] = defaultdict(Counter)
        # preferencias por usuario (estilo, longitud, idioma…)
        self.user_prefs: Dict[str, Dict[str, Any]] = defaultdict(dict)
        # estadísticas globales
        self.stats = {
            "total_feedback": 0,
            "positive": 0,
            "negative": 0,
            "started_at": time.time(),
            "last_update": time.time(),
        }


_state = _State()


# ──────────────────────────────────────────────────────────────────────
#  Persistencia
# ──────────────────────────────────────────────────────────────────────
def _save_to_disk() -> None:
    try:
        snap = {
            "patterns": _state.patterns,
            "user_prefs": _state.user_prefs,
            "user_vocab": {u: dict(c.most_common(200)) for u, c in _state.user_vocab.items()},
            "stats": _state.stats,
        }
        with open(LEARNING_FILE, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def _load_from_disk() -> None:
    if not os.path.exists(LEARNING_FILE):
        return
    try:
        with open(LEARNING_FILE, "r", encoding="utf-8") as f:
            snap = json.load(f)
        _state.patterns = snap.get("patterns", {})
        _state.stats.update(snap.get("stats", {}))
        for u, prefs in (snap.get("user_prefs") or {}).items():
            _state.user_prefs[u].update(prefs)
        for u, vocab in (snap.get("user_vocab") or {}).items():
            _state.user_vocab[u].update(vocab)
    except Exception:
        pass


_load_from_disk()


# ──────────────────────────────────────────────────────────────────────
#  Helpers internos
# ──────────────────────────────────────────────────────────────────────
_WORD_RE = re.compile(r"[a-záéíóúñü0-9]{3,}", re.IGNORECASE)


def _tokens(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def _pattern_key(prompt: str) -> str:
    """Firma estable de un prompt (top 12 tokens ordenados)."""
    toks = sorted(set(_tokens(prompt)))[:12]
    if not toks:
        return ""
    raw = " ".join(toks)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _decay_factor(last_seen: float) -> float:
    """Factor de decaimiento exponencial (vida media = DECAY_HALFLIFE)."""
    age = max(0.0, time.time() - last_seen)
    return 0.5 ** (age / DECAY_HALFLIFE)


# ──────────────────────────────────────────────────────────────────────
#  API PÚBLICA — feedback explícito
# ──────────────────────────────────────────────────────────────────────
def record_feedback(
    user_id: str,
    prompt: str,
    response: str,
    vote: int,
    signal: str = "thumb",
    comment: str = "",
) -> Dict[str, Any]:
    """Registra feedback (+1 / -1) y refuerza/penaliza el patrón asociado.

    Args:
        user_id:  id de sesión / usuario
        prompt:   mensaje del usuario que originó la respuesta
        response: respuesta del modelo
        vote:     +1 (👍) ó -1 (👎)
        signal:   'thumb' | 'copied' | 'regenerated' | 'edited' | …
        comment:  comentario textual opcional
    Returns:
        dict con score actualizado del patrón y delta aplicado.
    """
    if not LEARNING_ENABLED:
        return {"enabled": False}

    vote = 1 if vote > 0 else (-1 if vote < 0 else 0)
    if vote == 0:
        return {"vote": 0}

    key = _pattern_key(prompt)
    if not key:
        return {"vote": vote, "skipped": "empty"}

    with _lock:
        rec = _state.patterns.get(key)
        if rec is None:
            rec = {
                "key": key,
                "score": 0.0,
                "n_pos": 0,
                "n_neg": 0,
                "last_seen": time.time(),
                "examples": [],
                "first_seen": time.time(),
                "last_signal": signal,
            }
            _state.patterns[key] = rec

        # Pesos por señal: thumbs explícito = 1.0, copiado = 0.6, regenerado = -0.4
        weight = {
            "thumb": 1.0,
            "copied": 0.6,
            "edited": 0.3,
            "regenerated": -0.4,
        }.get(signal, 0.5)

        delta = vote * weight
        rec["score"] = round(rec["score"] * _decay_factor(rec["last_seen"]) + delta, 4)
        rec["last_seen"] = time.time()
        rec["last_signal"] = signal
        if vote > 0: rec["n_pos"] += 1
        if vote < 0: rec["n_neg"] += 1

        # Guardar hasta 3 ejemplos representativos (rotación)
        ex = rec.setdefault("examples", [])
        if len(ex) < 3 and response:
            ex.append({"prompt": prompt[:200], "response": response[:300], "vote": vote})

        # Estadísticas globales
        _state.stats["total_feedback"] += 1
        if vote > 0: _state.stats["positive"] += 1
        if vote < 0: _state.stats["negative"] += 1
        _state.stats["last_update"] = time.time()

        # LRU: si se pasa del cap, descartar el patrón con menor score
        if len(_state.patterns) > MAX_PATTERNS:
            worst = min(_state.patterns.items(), key=lambda kv: kv[1]["score"])
            _state.patterns.pop(worst[0], None)

        # Detección de preferencias del usuario (heurístico ligero)
        _update_user_prefs(user_id, prompt, response, vote)

        # Persistencia perezosa (cada 10 feedbacks)
        if _state.stats["total_feedback"] % 10 == 0:
            _save_to_disk()

        return {
            "key": key,
            "score": rec["score"],
            "n_pos": rec["n_pos"],
            "n_neg": rec["n_neg"],
            "delta": delta,
        }


def _update_user_prefs(uid: str, prompt: str, response: str, vote: int) -> None:
    """Detecta preferencias estilísticas implícitas en el feedback."""
    prefs = _state.user_prefs[uid]
    n = (response or "")
    length = len(n)

    # Acumulador EMA de longitud preferida
    cur_len = prefs.get("avg_response_length", length)
    alpha = 0.2 if vote > 0 else 0.05
    prefs["avg_response_length"] = round((1 - alpha) * cur_len + alpha * length, 1)

    # Detección de gusto por código / tablas / emojis
    if vote > 0:
        if "```" in n:
            prefs["likes_code"] = prefs.get("likes_code", 0) + 1
        if "|" in n and "---" in n:
            prefs["likes_tables"] = prefs.get("likes_tables", 0) + 1
        emojis = sum(1 for c in n if ord(c) > 0x1F000)
        if emojis >= 3:
            prefs["likes_emojis"] = prefs.get("likes_emojis", 0) + 1

    # Idioma preferido (heurística)
    es_score = sum(1 for w in ["el", "la", "que", "de", "y", "en"] if f" {w} " in (n.lower()))
    en_score = sum(1 for w in ["the", "and", "is", "to", "of", "in"] if f" {w} " in (n.lower()))
    if vote > 0:
        prefs["lang_es_score"] = prefs.get("lang_es_score", 0) + es_score
        prefs["lang_en_score"] = prefs.get("lang_en_score", 0) + en_score

    # Vocabulario favorito
    for tok in _tokens(prompt)[:20]:
        _state.user_vocab[uid][tok] += (1 if vote > 0 else 0)


# ──────────────────────────────────────────────────────────────────────
#  API PÚBLICA — recuperación de patrones aprendidos
# ──────────────────────────────────────────────────────────────────────
def get_pattern_score(prompt: str) -> float:
    """Devuelve el score acumulado del patrón (puede ser negativo)."""
    key = _pattern_key(prompt)
    if not key:
        return 0.0
    with _lock:
        rec = _state.patterns.get(key)
        if not rec:
            return 0.0
        return round(rec["score"] * _decay_factor(rec["last_seen"]), 4)


def get_user_preferences(user_id: str) -> Dict[str, Any]:
    with _lock:
        prefs = dict(_state.user_prefs.get(user_id, {}))
        # Idioma preferido derivado
        es = prefs.get("lang_es_score", 0)
        en = prefs.get("lang_en_score", 0)
        if es or en:
            prefs["preferred_lang"] = "es" if es >= en else "en"
        return prefs


def adapt_system_prompt(base_system: str, user_id: str) -> str:
    """Inyecta hints adaptativos al system prompt según el aprendizaje."""
    if not LEARNING_ENABLED:
        return base_system

    prefs = get_user_preferences(user_id)
    if not prefs:
        return base_system

    hints: List[str] = []
    if prefs.get("avg_response_length", 0) > 1800:
        hints.append("- El usuario prefiere respuestas extensas y detalladas.")
    elif 0 < prefs.get("avg_response_length", 0) < 600:
        hints.append("- El usuario prefiere respuestas concisas y directas.")

    if prefs.get("likes_code", 0) >= 3:
        hints.append("- El usuario valora especialmente los ejemplos de código completos.")
    if prefs.get("likes_tables", 0) >= 2:
        hints.append("- El usuario aprecia tablas comparativas cuando aporten valor.")
    if prefs.get("likes_emojis", 0) >= 3:
        hints.append("- El usuario aprecia un toque de emojis (con moderación).")

    if not hints:
        return base_system

    return base_system + "\n\n[ADAPTACIÓN APRENDIDA DEL USUARIO]\n" + "\n".join(hints)


def top_successful_patterns(n: int = 10) -> List[Dict[str, Any]]:
    """Patrones con mejor score (los que el sistema 'sabe hacer bien')."""
    with _lock:
        items = []
        for k, rec in _state.patterns.items():
            score = rec["score"] * _decay_factor(rec["last_seen"])
            if score <= 0:
                continue
            items.append({
                "key": k,
                "score": round(score, 3),
                "n_pos": rec["n_pos"],
                "n_neg": rec["n_neg"],
                "first_seen": rec.get("first_seen"),
                "examples": rec.get("examples", []),
            })
        items.sort(key=lambda x: -x["score"])
        return items[:n]


def stats() -> Dict[str, Any]:
    with _lock:
        s = dict(_state.stats)
        s["patterns_known"] = len(_state.patterns)
        s["users_with_prefs"] = len(_state.user_prefs)
        positive_rate = 0.0
        total = s.get("positive", 0) + s.get("negative", 0)
        if total > 0:
            positive_rate = s["positive"] / total
        s["positive_rate"] = round(positive_rate, 3)
        return s


def reset_user(user_id: str) -> None:
    with _lock:
        _state.user_prefs.pop(user_id, None)
        _state.user_vocab.pop(user_id, None)


def reset_all() -> None:
    with _lock:
        _state.patterns.clear()
        _state.user_prefs.clear()
        _state.user_vocab.clear()
        _state.stats["total_feedback"] = 0
        _state.stats["positive"] = 0
        _state.stats["negative"] = 0
        _state.stats["last_update"] = time.time()
        try:
            if os.path.exists(LEARNING_FILE):
                os.remove(LEARNING_FILE)
        except Exception:
            pass
