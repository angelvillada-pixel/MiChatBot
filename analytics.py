"""
═══════════════════════════════════════════════════════════════════════════
 analytics.py  ·  DeepNova v6.0 · Métricas de uso y dashboard backend
═══════════════════════════════════════════════════════════════════════════
 Tracking en memoria de:
   - uso por modelo
   - latencia
   - errores
   - usuarios activos (set)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import time, threading
from collections import Counter, defaultdict
from typing import Dict, Any

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "model_usage":   Counter(),       # modelo → nº usos
    "intent_usage":  Counter(),       # intent → nº usos
    "errors":        Counter(),       # tipo_error → nº
    "latency_ms":    defaultdict(list),  # modelo → [ms, ms, ...]
    "active_users":  set(),
    "requests_total": 0,
    "started_at":    time.time(),
}


def log_request(model_id: str, user_id: str | None = None, intent: str | None = None) -> None:
    with _lock:
        _state["model_usage"][model_id] += 1
        _state["requests_total"] += 1
        if intent:
            _state["intent_usage"][intent] += 1
        if user_id:
            _state["active_users"].add(user_id)


def log_latency(model_id: str, ms: float) -> None:
    with _lock:
        arr = _state["latency_ms"][model_id]
        arr.append(ms)
        # mantener solo últimos 1000
        if len(arr) > 1000:
            del arr[: len(arr) - 1000]


def log_error(error_type: str) -> None:
    with _lock:
        _state["errors"][error_type] += 1


def stats() -> Dict[str, Any]:
    """Snapshot agregado para dashboard."""
    with _lock:
        latency_avg = {
            m: round(sum(v) / len(v), 1) if v else 0
            for m, v in _state["latency_ms"].items()
        }
        uptime_sec = int(time.time() - _state["started_at"])
        return {
            "requests_total":    _state["requests_total"],
            "model_usage":       dict(_state["model_usage"]),
            "intent_usage":      dict(_state["intent_usage"]),
            "errors":            dict(_state["errors"]),
            "latency_avg_ms":    latency_avg,
            "active_users":      len(_state["active_users"]),
            "uptime_sec":        uptime_sec,
        }


def reset() -> None:
    with _lock:
        _state["model_usage"].clear()
        _state["intent_usage"].clear()
        _state["errors"].clear()
        _state["latency_ms"].clear()
        _state["active_users"].clear()
        _state["requests_total"] = 0
        _state["started_at"] = time.time()
