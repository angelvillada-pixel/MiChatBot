"""
═══════════════════════════════════════════════════════════════════════════
 cost_control.py  ·  DeepNova v6.0 · Estimación y control de costos
═══════════════════════════════════════════════════════════════════════════
 Tabla de costos por modelo (por 1K tokens) + helpers para presupuesto.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Dict
import threading

# Coste aproximado (USD / 1K tokens) — ajusta a tu proveedor real
MODEL_COST: Dict[str, float] = {
    "nova_opus":   0.020,
    "nova_sonnet": 0.010,
    "nova_haiku":  0.005,
    "nova_claude": 0.012,
}

_lock = threading.Lock()
_spend: Dict[str, float] = {k: 0.0 for k in MODEL_COST}
_tokens: Dict[str, int] = {k: 0 for k in MODEL_COST}


def estimate_cost(model_id: str, tokens: int) -> float:
    """Estima costo en USD para `tokens` con el modelo dado."""
    rate = MODEL_COST.get(model_id, 0.010)
    return round(rate * (tokens / 1000.0), 6)


def track_usage(model_id: str, tokens: int) -> float:
    """Registra el consumo y devuelve el coste de esta llamada."""
    cost = estimate_cost(model_id, tokens)
    with _lock:
        _spend[model_id] = _spend.get(model_id, 0.0) + cost
        _tokens[model_id] = _tokens.get(model_id, 0) + tokens
    return cost


def get_summary() -> Dict[str, Dict[str, float]]:
    """Resumen total de gasto y tokens por modelo."""
    with _lock:
        return {
            mid: {
                "tokens": _tokens.get(mid, 0),
                "cost_usd": round(_spend.get(mid, 0.0), 4),
                "rate_per_1k": MODEL_COST[mid],
            }
            for mid in MODEL_COST
        }


def total_cost() -> float:
    with _lock:
        return round(sum(_spend.values()), 4)


def reset() -> None:
    with _lock:
        for k in _spend: _spend[k] = 0.0
        for k in _tokens: _tokens[k] = 0
