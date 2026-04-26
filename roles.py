"""
═══════════════════════════════════════════════════════════════════════════
 roles.py  ·  DeepNova v6.0 · Sistema de planes y permisos
═══════════════════════════════════════════════════════════════════════════
 Free / Pro / Ultra con control de acceso a modelos y features.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Dict, Set, Optional

# ── Definición de planes ─────────────────────────────────────────────
PLANS: Dict[str, Dict] = {
    "free": {
        "name": "Free",
        "price_usd": 0,
        "models":   {"nova_haiku", "nova_sonnet"},
        "features": {"chat", "history"},
        "rpm":      10,    # requests por minuto
        "rpd":      100,   # requests por día
    },
    "pro": {
        "name": "Pro",
        "price_usd": 10,
        "models":   {"nova_haiku", "nova_sonnet", "nova_claude"},
        "features": {"chat", "history", "voice", "image", "memory"},
        "rpm":      40,
        "rpd":      2000,
    },
    "ultra": {
        "name": "Ultra",
        "price_usd": 25,
        "models":   {"nova_haiku", "nova_sonnet", "nova_claude", "nova_opus"},
        "features": {"chat", "history", "voice", "image", "memory", "agents", "plugins", "priority"},
        "rpm":      120,
        "rpd":      10000,
    },
}


def get_plan(plan_id: Optional[str]) -> Dict:
    """Devuelve el plan o 'free' si no existe."""
    return PLANS.get((plan_id or "free").lower(), PLANS["free"])


def can_use_model(plan_id: Optional[str], model_id: str) -> bool:
    """¿El plan permite usar este modelo Nova?"""
    return model_id in get_plan(plan_id)["models"]


def has_feature(plan_id: Optional[str], feature: str) -> bool:
    """¿El plan tiene esta feature habilitada?"""
    return feature in get_plan(plan_id)["features"]


def list_plans() -> list:
    """Lista pública de planes (para UI de pricing)."""
    return [
        {
            "id":       pid,
            "name":     p["name"],
            "price":    p["price_usd"],
            "models":   sorted(p["models"]),
            "features": sorted(p["features"]),
            "rpm":      p["rpm"],
            "rpd":      p["rpd"],
        }
        for pid, p in PLANS.items()
    ]
