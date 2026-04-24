"""
═══════════════════════════════════════════════════════════════════════════
 User Profile Module — DeepNova v4 / NeuroCore-X
═══════════════════════════════════════════════════════════════════════════
 Gestión de perfil de usuario persistente:
   • Información personal (nombre, profesión, intereses)
   • Preferencias (idioma, estilo de respuesta, tema UI)
   • Stack técnico preferido
   • Contexto persistente que se inyecta en cada respuesta
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os, json, threading
from datetime import datetime
from typing import Dict, Any, Optional

PROFILE_FILE = os.environ.get("NEUROCORE_PROFILE_FILE", "neurocore_profiles.json")
_lock = threading.Lock()

DEFAULT_PROFILE: Dict[str, Any] = {
    "name":        "",
    "profession":  "",
    "interests":   [],
    "language":    "es",
    "tone":        "profesional-amigable",
    "response_style": "detallado",
    "preferred_stack": [],
    "avatar":      "🧠",
    "theme":       "dark",
    "ultra_mode_default": False,
    "created_at":  None,
    "updated_at":  None,
    "custom_context": "",  # texto libre que el usuario quiera inyectar
}


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(PROFILE_FILE):
        return {}
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_all(data: Dict[str, Any]) -> bool:
    try:
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_profile(sid: str) -> Dict[str, Any]:
    with _lock:
        data = _load_all()
        prof = data.get(sid, {})
    merged = {**DEFAULT_PROFILE, **prof}
    if not merged.get("created_at"):
        merged["created_at"] = datetime.utcnow().isoformat()
    return merged


def update_profile(sid: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        data = _load_all()
        cur = {**DEFAULT_PROFILE, **data.get(sid, {})}
        # Whitelist de keys permitidas
        allowed = set(DEFAULT_PROFILE.keys())
        for k, v in (updates or {}).items():
            if k in allowed:
                cur[k] = v
        cur["updated_at"] = datetime.utcnow().isoformat()
        if not cur.get("created_at"):
            cur["created_at"] = cur["updated_at"]
        data[sid] = cur
        _save_all(data)
    return cur


def reset_profile(sid: str) -> bool:
    with _lock:
        data = _load_all()
        if sid in data:
            del data[sid]
            return _save_all(data)
    return True


def profile_to_system_prompt(profile: Dict[str, Any]) -> str:
    """Convierte el perfil en un bloque inyectable en el system prompt."""
    if not profile:
        return ""
    parts = ["\n\n═══ PERFIL DEL USUARIO ═══"]
    if profile.get("name"):
        parts.append(f"Nombre: {profile['name']}")
    if profile.get("profession"):
        parts.append(f"Profesión: {profile['profession']}")
    if profile.get("interests"):
        ints = profile["interests"] if isinstance(profile["interests"], list) else [profile["interests"]]
        parts.append(f"Intereses: {', '.join(str(i) for i in ints[:8])}")
    if profile.get("preferred_stack"):
        st = profile["preferred_stack"] if isinstance(profile["preferred_stack"], list) else [profile["preferred_stack"]]
        parts.append(f"Stack preferido: {', '.join(str(s) for s in st[:10])}")
    if profile.get("language"):
        parts.append(f"Idioma principal: {profile['language']}")
    if profile.get("tone"):
        parts.append(f"Tono preferido: {profile['tone']}")
    if profile.get("response_style"):
        parts.append(f"Estilo de respuesta: {profile['response_style']}")
    if profile.get("custom_context"):
        parts.append(f"Contexto extra: {profile['custom_context'][:500]}")
    parts.append("Ajusta tus respuestas a este perfil cuando sea relevante.")
    return "\n".join(parts)


def list_all_profiles() -> Dict[str, Any]:
    with _lock:
        data = _load_all()
    return {"count": len(data), "sids": list(data.keys())}
