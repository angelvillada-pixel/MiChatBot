"""
═══════════════════════════════════════════════════════════════════════════
 feedback_loop.py · DeepNova v7.0 · Sistema de Retroalimentación Inteligente
═══════════════════════════════════════════════════════════════════════════
 Une feedback explícito (👍/👎) e implícito (copiado, regenerado, editado,
 tiempo de lectura) y lo conecta con el motor de aprendizaje continuo.

 Endpoints sugeridos (registrados en improvements_patch):
   POST /api/feedback/learn   → registra feedback y aprende
   GET  /api/feedback/stats   → estadísticas del aprendizaje
   POST /api/feedback/regenerate → marca regeneración (señal -)

 Áreas cubiertas (del documento de mejoras):
   ✓ 2.2 Retroalimentación y ajuste
   ✓ 1.1 Aprendizaje automático (puente con learning_engine)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import time
from typing import Dict, Any, Optional, List

try:
    from learning_engine import (
        record_feedback, get_user_preferences,
        adapt_system_prompt, top_successful_patterns, stats as learning_stats,
    )
    _LEARNING_OK = True
except Exception:
    _LEARNING_OK = False


# ──────────────────────────────────────────────────────────────────────
#  Buffer de últimas interacciones (para enlazar feedback con prompt original)
# ──────────────────────────────────────────────────────────────────────
_recent: Dict[str, Dict[str, Any]] = {}   # uid → {prompt, response, ts}
MAX_AGE = 3600  # 1 hora


def remember_interaction(user_id: str, prompt: str, response: str,
                         message_id: Optional[str] = None) -> None:
    """Registra la última interacción del usuario para asociarla luego con feedback."""
    _recent[user_id or "anon"] = {
        "prompt": prompt or "",
        "response": response or "",
        "ts": time.time(),
        "message_id": message_id,
    }
    # Limpieza perezosa
    cutoff = time.time() - MAX_AGE
    stale = [uid for uid, d in _recent.items() if d["ts"] < cutoff]
    for uid in stale:
        _recent.pop(uid, None)


def submit_feedback(
    user_id: str,
    vote: int,
    signal: str = "thumb",
    comment: str = "",
    prompt: Optional[str] = None,
    response: Optional[str] = None,
) -> Dict[str, Any]:
    """Procesa feedback y lo enrola en el learning engine.

    Si no se pasa prompt/response, se intenta recuperar de la última interacción.
    """
    user_id = user_id or "anon"

    if not prompt or not response:
        last = _recent.get(user_id) or {}
        prompt = prompt or last.get("prompt", "")
        response = response or last.get("response", "")

    if not _LEARNING_OK:
        return {"ok": False, "reason": "learning_engine_unavailable"}

    res = record_feedback(
        user_id=user_id,
        prompt=prompt or "",
        response=response or "",
        vote=vote,
        signal=signal,
        comment=comment or "",
    )
    return {"ok": True, "result": res}


def feedback_stats() -> Dict[str, Any]:
    if not _LEARNING_OK:
        return {"available": False}
    s = learning_stats()
    s["available"] = True
    s["top_patterns"] = top_successful_patterns(5)
    return s


def get_adaptive_system(base_system: str, user_id: str) -> str:
    """Devuelve el system prompt enriquecido con preferencias aprendidas."""
    if not _LEARNING_OK:
        return base_system
    return adapt_system_prompt(base_system, user_id or "anon")


def user_preferences(user_id: str) -> Dict[str, Any]:
    if not _LEARNING_OK:
        return {}
    return get_user_preferences(user_id or "anon")


# ──────────────────────────────────────────────────────────────────────
#  Señales implícitas
# ──────────────────────────────────────────────────────────────────────
def signal_copied(user_id: str) -> Dict[str, Any]:
    """El usuario copió la respuesta → señal positiva implícita."""
    return submit_feedback(user_id, vote=1, signal="copied")


def signal_regenerated(user_id: str) -> Dict[str, Any]:
    """El usuario pidió regenerar → señal negativa implícita."""
    return submit_feedback(user_id, vote=-1, signal="regenerated")


def signal_edited(user_id: str, edited_response: str) -> Dict[str, Any]:
    """El usuario editó la respuesta antes de usarla → ligeramente negativa."""
    return submit_feedback(user_id, vote=-1, signal="edited",
                           comment=(edited_response or "")[:300])
