"""
═══════════════════════════════════════════════════════════════════════
 reasoning.py — M1: Motor de Razonamiento Avanzado (DeepNova v2 Híbrido)
═══════════════════════════════════════════════════════════════════════

Responsabilidades:
  • CoT (Chain-of-Thought) con <thinking> aislado que nunca llega al usuario
  • Self-Consistency: genera N trayectorias y vota por mayoría semántica
  • ReAct loop: Thought → Action → Observation (máx. 6 iteraciones)
  • Meta-prompting: detección de ambigüedad con modelo fast antes de ejecutar
  • Temperatura adaptativa por modo (chat 0.8, code 0.3, reason 0.5, etc.)

Diseño: no reemplaza la lógica del app.py original — se INVOCA desde los
endpoints cuando `deep=true` o desde modos M3 que lo activen explícitamente.

Variables de entorno:
  ENABLE_SELF_CONSISTENCY=1   → activa votación N=3 en reason/research
  REASONING_MAX_ITERATIONS=6  → techo del ReAct loop
"""
import os
import re
import time
from collections import Counter
from typing import Callable, List, Dict, Any, Optional

# ──────────────────────────────────────────────────────────────────────
# Configuración global
# ──────────────────────────────────────────────────────────────────────
ENABLE_SELF_CONSISTENCY = os.environ.get("ENABLE_SELF_CONSISTENCY", "0") == "1"
MAX_ITERATIONS          = int(os.environ.get("REASONING_MAX_ITERATIONS", "6"))
MAX_SC_SAMPLES          = 3

# Temperatura óptima por modo (ajustada empíricamente)
TEMPERATURE_BY_MODE: Dict[str, float] = {
    "chat":      0.8,
    "code":      0.3,
    "execute":   0.2,
    "design":    0.7,
    "translate": 0.4,
    "content":   0.75,
    "analyze":   0.5,
    "reason":    0.5,
    "research":  0.5,
    "agent":     0.6,
    "debate":    0.7,
    "search":    0.5,
}

# ──────────────────────────────────────────────────────────────────────
# CoT: Chain-of-Thought con <thinking> aislado
# ──────────────────────────────────────────────────────────────────────
COT_INSTRUCTION = (
    "\n\nANTES de responder, piensa paso a paso DENTRO de <thinking>...</thinking>. "
    "Esa sección NO la verá el usuario: úsala para descomponer el problema, "
    "considerar alternativas y verificar tu lógica. "
    "Después, FUERA de las etiquetas, entrega la respuesta final limpia y directa."
)

_THINKING_RE = re.compile(r"<thinking>[\s\S]*?</thinking>", re.IGNORECASE)

def strip_thinking(text: str) -> str:
    """Elimina el bloque <thinking> para que el usuario solo vea la respuesta final."""
    if not text:
        return text
    cleaned = _THINKING_RE.sub("", text).strip()
    # Si por alguna razón el modelo no cerró la etiqueta, cortamos por apertura
    if "<thinking>" in cleaned.lower():
        cleaned = re.split(r"(?i)<thinking>", cleaned)[0].strip()
    return cleaned

def extract_thinking(text: str) -> Optional[str]:
    """Devuelve el contenido del <thinking> (útil para logs / debug)."""
    m = _THINKING_RE.search(text or "")
    if not m:
        return None
    return m.group(0).replace("<thinking>", "").replace("</thinking>", "").strip()

def build_cot_system(base_system: str, mode: str = "chat") -> str:
    """Añade la instrucción CoT al system prompt existente, sin destruirlo."""
    return base_system + COT_INSTRUCTION

# ──────────────────────────────────────────────────────────────────────
# Self-Consistency: muestra N trayectorias y vota por la moda
# ──────────────────────────────────────────────────────────────────────
def _signature(text: str) -> str:
    """Firma simplificada de una respuesta para votación por mayoría."""
    if not text:
        return ""
    words = re.findall(r"\b[a-záéíóúñü]{4,}\b", text.lower())[:25]
    return " ".join(sorted(set(words)))

def self_consistency(
    generator: Callable[[float], str],
    n: int = MAX_SC_SAMPLES,
    base_temp: float = 0.7,
) -> Dict[str, Any]:
    """
    Ejecuta `generator(temperature)` N veces y devuelve la respuesta más votada.
    `generator` es un callable que recibe temperatura y devuelve el texto del LLM.
    """
    if not ENABLE_SELF_CONSISTENCY or n <= 1:
        return {"answer": generator(base_temp), "votes": 1, "samples": 1}

    samples: List[str] = []
    for i in range(n):
        try:
            temp = base_temp + (i - n // 2) * 0.1  # varía temperatura
            samples.append(generator(max(0.1, min(1.2, temp))))
        except Exception:
            continue

    if not samples:
        return {"answer": "", "votes": 0, "samples": 0}

    sigs = [_signature(s) for s in samples]
    counts = Counter(sigs)
    winning_sig, votes = counts.most_common(1)[0]
    winner = next((s for s, sig in zip(samples, sigs) if sig == winning_sig), samples[0])

    return {
        "answer":  winner,
        "votes":   votes,
        "samples": len(samples),
        "agreement": round(votes / len(samples), 2),
    }

# ──────────────────────────────────────────────────────────────────────
# ReAct loop: Thought → Action → Observation
# ──────────────────────────────────────────────────────────────────────
REACT_SYSTEM = """Eres un agente ReAct. Sigues este ciclo estricto:

Thought: razonas sobre el estado actual
Action: una de [search("query"), scrape("url"), execute("python_code"), finish("respuesta")]
Observation: (la inyecta el sistema tras ejecutar la Action)

Formato EXACTO por turno:
Thought: ...
Action: nombre_accion("argumento")

Cuando tengas la respuesta, usa:
Action: finish("respuesta final completa al usuario")

Reglas:
- Máximo 6 iteraciones
- No inventes Observations: espera siempre a que el sistema te las entregue
- Sé conciso en Thought (1-2 líneas)
"""

_ACTION_RE = re.compile(
    r'Action:\s*(search|scrape|execute|finish)\s*\(\s*"((?:[^"\\]|\\.)*)"\s*\)',
    re.IGNORECASE,
)

def parse_action(text: str):
    """Extrae (nombre_accion, argumento) de la salida del LLM."""
    m = _ACTION_RE.search(text)
    if not m:
        return None, None
    return m.group(1).lower(), m.group(2)

def react_loop(
    task: str,
    llm_call: Callable[[List[Dict[str, str]], float], str],
    action_handlers: Dict[str, Callable[[str], str]],
    max_iterations: int = MAX_ITERATIONS,
) -> Dict[str, Any]:
    """
    Ejecuta un bucle ReAct.

    llm_call(messages, temperature) -> texto
    action_handlers: { "search": fn, "scrape": fn, "execute": fn }
      — "finish" se maneja internamente.

    Devuelve dict con answer, trace (lista de pasos), iterations, finished.
    """
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": REACT_SYSTEM},
        {"role": "user",   "content": f"Tarea: {task}\n\nEmpieza con Thought:"},
    ]
    trace: List[Dict[str, Any]] = []

    for i in range(max_iterations):
        raw = llm_call(messages, 0.4)
        action, arg = parse_action(raw)

        step = {"iter": i + 1, "llm_output": raw[:800], "action": action, "arg": arg}

        if action == "finish":
            step["observation"] = "[finish]"
            trace.append(step)
            return {
                "answer":     arg,
                "trace":      trace,
                "iterations": i + 1,
                "finished":   True,
            }

        if action in action_handlers and arg:
            try:
                obs = action_handlers[action](arg)
            except Exception as e:
                obs = f"[Error en {action}: {e}]"
        else:
            obs = "[Acción no reconocida — usa finish(\"respuesta\") para terminar]"

        step["observation"] = obs[:1500]
        trace.append(step)

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"Observation: {obs[:2000]}"})

    # Si se agota el loop, pedimos una respuesta directa
    messages.append({"role": "user", "content": "Se agotaron las iteraciones. Da tu mejor respuesta ahora con Action: finish(\"...\")"})
    final_raw = llm_call(messages, 0.5)
    _, final_arg = parse_action(final_raw)
    return {
        "answer":     final_arg or final_raw,
        "trace":      trace,
        "iterations": max_iterations,
        "finished":   False,
    }

# ──────────────────────────────────────────────────────────────────────
# Meta-prompting: detecta ambigüedad antes de ejecutar
# ──────────────────────────────────────────────────────────────────────
META_CHECK_PROMPT = (
    "Eres un clasificador breve. La pregunta del usuario es:\n"
    "«{query}»\n\n"
    "¿Es AMBIGUA o le falta contexto crítico para responder bien? "
    "Responde SOLO con una línea JSON: "
    '{{"ambiguous": true|false, "question": "pregunta_de_clarificación_o_vacía"}}'
)

def meta_check_ambiguity(
    query: str,
    fast_llm: Callable[[str], str],
) -> Dict[str, Any]:
    """
    Llama a un modelo rápido para decidir si la query necesita clarificación.
    `fast_llm(prompt) -> texto`.
    Devuelve {ambiguous: bool, question: str}. Falla en silencio → no ambigua.
    """
    try:
        raw = fast_llm(META_CHECK_PROMPT.format(query=query[:500]))
        m = re.search(r'\{[\s\S]*?\}', raw)
        if not m:
            return {"ambiguous": False, "question": ""}
        import json
        data = json.loads(m.group(0))
        return {
            "ambiguous": bool(data.get("ambiguous", False)),
            "question":  str(data.get("question", "")).strip(),
        }
    except Exception:
        return {"ambiguous": False, "question": ""}

# ──────────────────────────────────────────────────────────────────────
# Helper público: wrap completo
# ──────────────────────────────────────────────────────────────────────
def get_temperature(mode: str) -> float:
    """Temperatura adaptativa por modo con fallback sensato."""
    return TEMPERATURE_BY_MODE.get(mode, 0.7)

def reason_pipeline(
    query: str,
    mode: str,
    llm_call: Callable[[List[Dict[str, str]], float], str],
    fast_llm: Callable[[str], str],
    base_system: str,
    use_self_consistency: bool = False,
) -> Dict[str, Any]:
    """
    Pipeline completo M1:
      1. meta-check ambigüedad
      2. CoT con <thinking> aislado
      3. Self-consistency si activa
      4. Limpieza del output final
    """
    start = time.time()

    # 1. Meta-check
    meta = meta_check_ambiguity(query, fast_llm) if mode in ("reason", "research", "agent") else {"ambiguous": False, "question": ""}
    if meta["ambiguous"] and meta["question"]:
        return {
            "answer":        f"🤔 Para darte una respuesta precisa, necesito aclarar algo:\n\n**{meta['question']}**",
            "clarification": True,
            "meta":          meta,
            "elapsed":       round(time.time() - start, 2),
        }

    # 2+3. CoT + Self-Consistency
    system = build_cot_system(base_system, mode)
    base_temp = get_temperature(mode)

    def gen(temp: float) -> str:
        return llm_call(
            [{"role": "system", "content": system}, {"role": "user", "content": query}],
            temp,
        )

    if use_self_consistency and ENABLE_SELF_CONSISTENCY and mode in ("reason", "research"):
        sc = self_consistency(gen, n=MAX_SC_SAMPLES, base_temp=base_temp)
        raw_answer = sc["answer"]
        extra = {"self_consistency": sc}
    else:
        raw_answer = gen(base_temp)
        extra = {"self_consistency": None}

    # 4. Limpiar <thinking>
    final = strip_thinking(raw_answer)
    thinking = extract_thinking(raw_answer)

    return {
        "answer":        final,
        "thinking":      thinking,  # solo para logs internos / admin
        "clarification": False,
        "mode":          mode,
        "temperature":   base_temp,
        "elapsed":       round(time.time() - start, 2),
        **extra,
    }
