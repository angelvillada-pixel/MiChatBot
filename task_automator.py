"""
═══════════════════════════════════════════════════════════════════════════
 task_automator.py · DeepNova v7.0 · Automatización de Tareas Repetitivas
═══════════════════════════════════════════════════════════════════════════
 Detección automática de patrones repetitivos en las consultas del usuario
 y oferta de "macros" guardables y reejecutables con un solo comando.

 Características:
   • Detección de plantillas (consultas similares con parámetros que cambian)
   • Registro y nombrado de macros
   • Ejecución por nombre o por shortcut /run <nombre>
   • Persistencia ligera en archivo JSON
   • Thread-safe

 Áreas cubiertas (del documento de mejoras):
   ✓ 4.1 Automatización de tareas
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os
import re
import json
import time
import threading
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional, Tuple

MACRO_FILE = os.environ.get("MACRO_FILE", "macros.json")
SIMILARITY_THRESHOLD = 0.72   # Jaccard mínimo para considerar plantilla
MIN_REPEAT_COUNT     = 3      # nº mínimo de consultas similares para sugerir macro

_lock = threading.RLock()
_state: Dict[str, Any] = {
    "macros": {},                                 # nombre → {pattern, params, created_at, n_runs}
    "history": defaultdict(list),                 # uid → [{prompt, ts}]
}


# ──────────────────────────────────────────────────────────────────────
#  Persistencia
# ──────────────────────────────────────────────────────────────────────
def _save() -> None:
    try:
        with open(MACRO_FILE, "w", encoding="utf-8") as f:
            json.dump({"macros": _state["macros"]}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load() -> None:
    if not os.path.exists(MACRO_FILE):
        return
    try:
        with open(MACRO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _state["macros"] = data.get("macros") or {}
    except Exception:
        pass


_load()


# ──────────────────────────────────────────────────────────────────────
#  Helpers de similitud
# ──────────────────────────────────────────────────────────────────────
_WORD_RE = re.compile(r"[\wáéíóúñü]{3,}", re.IGNORECASE)


def _tokens(s: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(s or "")]


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _common_template(prompts: List[str]) -> Tuple[str, List[str]]:
    """Heurística: detecta tokens compartidos entre prompts y los marca como
    'fijos'; los que cambian son 'parámetros'."""
    if not prompts:
        return "", []
    token_sets = [set(_tokens(p)) for p in prompts]
    common = set.intersection(*token_sets) if len(token_sets) > 1 else token_sets[0]
    # toma como "plantilla" el primer prompt con los tokens variables marcados
    base = prompts[0]
    tokens = _WORD_RE.findall(base)
    params: List[str] = []
    pattern = base
    for t in tokens:
        if t.lower() not in common and len(t) >= 3:
            pattern = re.sub(rf"\b{re.escape(t)}\b", "{$param}", pattern, count=1)
            params.append(t)
    return pattern, params


# ──────────────────────────────────────────────────────────────────────
#  API pública
# ──────────────────────────────────────────────────────────────────────
def track(user_id: str, prompt: str) -> Optional[Dict[str, Any]]:
    """Registra una consulta y devuelve sugerencia de macro si detecta patrón.

    Returns:
        None si no hay sugerencia, o un dict con la propuesta de macro.
    """
    if not prompt or not user_id:
        return None

    with _lock:
        hist = _state["history"][user_id]
        hist.append({"prompt": prompt, "ts": time.time()})
        # mantener solo los últimos 50
        if len(hist) > 50:
            del hist[: len(hist) - 50]

        if len(hist) < MIN_REPEAT_COUNT:
            return None

        # busca cluster con jaccard alto contra el último prompt
        last_tokens = _tokens(prompt)
        cluster: List[str] = [prompt]
        for entry in reversed(hist[:-1]):
            sim = _jaccard(last_tokens, _tokens(entry["prompt"]))
            if sim >= SIMILARITY_THRESHOLD:
                cluster.append(entry["prompt"])
                if len(cluster) >= 6:
                    break

        if len(cluster) < MIN_REPEAT_COUNT:
            return None

        pattern, params = _common_template(cluster)
        # Evitar sugerir si ya existe macro idéntica
        for m_name, m in _state["macros"].items():
            if m.get("pattern") == pattern:
                return None

        return {
            "suggestion": True,
            "pattern": pattern,
            "params": params,
            "examples": cluster[:3],
            "message": (
                "He detectado que repites consultas similares. ¿Quieres guardarlas "
                "como una macro reutilizable? Usa `/macro save <nombre>` para "
                "registrarla y `/run <nombre> <param>` para ejecutarla."
            ),
        }


def save_macro(name: str, pattern: str, params: List[str], owner: Optional[str] = None) -> Dict[str, Any]:
    name = (name or "").strip().lower().replace(" ", "_")
    if not name or not pattern:
        return {"ok": False, "error": "nombre y patrón requeridos"}
    with _lock:
        _state["macros"][name] = {
            "name": name,
            "pattern": pattern,
            "params": params or [],
            "owner": owner,
            "created_at": time.time(),
            "n_runs": 0,
            "last_run": None,
        }
        _save()
        return {"ok": True, "name": name}


def run_macro(name: str, args: List[str]) -> Dict[str, Any]:
    """Sustituye `{$param}` por los argumentos en orden y devuelve el prompt
    final que se enviaría al LLM. (No ejecuta — el caller lo procesa.)"""
    name = (name or "").strip().lower().replace(" ", "_")
    with _lock:
        m = _state["macros"].get(name)
        if not m:
            return {"ok": False, "error": f"macro '{name}' no existe"}
        prompt = m["pattern"]
        for a in args:
            prompt = prompt.replace("{$param}", a, 1)
        m["n_runs"] += 1
        m["last_run"] = time.time()
        _save()
        return {"ok": True, "prompt": prompt, "macro": name, "n_runs": m["n_runs"]}


def list_macros(owner: Optional[str] = None) -> List[Dict[str, Any]]:
    with _lock:
        items = []
        for name, m in _state["macros"].items():
            if owner and m.get("owner") and m["owner"] != owner:
                continue
            items.append(dict(m))
        items.sort(key=lambda x: -(x.get("n_runs", 0)))
        return items


def delete_macro(name: str) -> bool:
    with _lock:
        if name in _state["macros"]:
            del _state["macros"][name]
            _save()
            return True
        return False


def stats() -> Dict[str, Any]:
    with _lock:
        users = len(_state["history"])
        total_prompts = sum(len(h) for h in _state["history"].values())
        return {
            "macros": len(_state["macros"]),
            "users_tracked": users,
            "prompts_in_history": total_prompts,
            "most_used_macro": (
                max(_state["macros"].items(), key=lambda kv: kv[1].get("n_runs", 0))[0]
                if _state["macros"] else None
            ),
        }


# ──────────────────────────────────────────────────────────────────────
#  Procesamiento de comandos /macro y /run
# ──────────────────────────────────────────────────────────────────────
_CMD_SAVE_RE = re.compile(r"^/macro\s+save\s+(\S+)\s+(.+)$", re.IGNORECASE | re.DOTALL)
_CMD_RUN_RE  = re.compile(r"^/run\s+(\S+)(?:\s+(.+))?$",       re.IGNORECASE | re.DOTALL)
_CMD_LIST_RE = re.compile(r"^/macro\s+list\s*$",                re.IGNORECASE)
_CMD_DEL_RE  = re.compile(r"^/macro\s+delete\s+(\S+)\s*$",       re.IGNORECASE)


def parse_command(text: str, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Parsea comandos /macro y /run. Devuelve dict con la acción o None."""
    if not text:
        return None
    text = text.strip()

    m = _CMD_SAVE_RE.match(text)
    if m:
        name, pattern_text = m.group(1), m.group(2).strip()
        # extraer params automáticamente: cualquier {$x}
        params = re.findall(r"\{\$(\w+)\}", pattern_text)
        # normalizar a {$param}
        normalized = re.sub(r"\{\$\w+\}", "{$param}", pattern_text)
        res = save_macro(name, normalized, params, owner=owner)
        if res.get("ok"):
            return {"action": "saved", "name": name,
                    "message": f"✅ Macro `{name}` guardada. Úsala con `/run {name} <args>`."}
        return {"action": "error", "message": res.get("error", "error")}

    m = _CMD_RUN_RE.match(text)
    if m:
        name = m.group(1)
        args_str = (m.group(2) or "").strip()
        args = [a.strip() for a in args_str.split("|")] if "|" in args_str else ([args_str] if args_str else [])
        res = run_macro(name, args)
        if res.get("ok"):
            return {"action": "run", "prompt": res["prompt"], "macro": name}
        return {"action": "error", "message": res.get("error", "error")}

    if _CMD_LIST_RE.match(text):
        items = list_macros(owner=owner)
        if not items:
            return {"action": "list", "message": "No tienes macros guardadas todavía."}
        lines = ["📚 **Tus macros:**"]
        for it in items:
            lines.append(f"- `/run {it['name']}`  ·  {it['n_runs']} usos  ·  patrón: `{it['pattern'][:80]}`")
        return {"action": "list", "message": "\n".join(lines)}

    m = _CMD_DEL_RE.match(text)
    if m:
        name = m.group(1)
        ok = delete_macro(name)
        return {"action": "deleted",
                "message": (f"🗑️ Macro `{name}` eliminada." if ok else f"❌ No existe `{name}`.")}

    return None
