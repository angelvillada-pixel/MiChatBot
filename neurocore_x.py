"""
═══════════════════════════════════════════════════════════════════════════
 NeuroCore-X  ·  Advanced Reasoning Engine  ·  DeepNova v4 Ultra
═══════════════════════════════════════════════════════════════════════════
 Módulo 100% aditivo — inspirado en Claude Opus, GPT-4o y DeepSeek-R1.
 Funcionalidades:
   • Mejora automática de prompts (prompt-rewriting layer)
   • Cadena de razonamiento multi-paso (deep CoT)
   • Planificación explícita (plan → execute → verify)
   • ULTRA mode: multi-pass self-refinement + contradictions check
   • Memoria de contexto conversacional vectorial (hash-based)
   • Plantillas adaptativas por tipo de tarea
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import re, json, hashlib, time
from typing import List, Dict, Any, Callable, Optional, Tuple

# ── Core identity injected into every ULTRA call ──
NEUROCORE_IDENTITY = """Eres **NeuroCore-X**, el núcleo de razonamiento avanzado de DeepNova v4.
Inspirado en arquitecturas tipo Claude Opus 4.7 y GPT-5 reasoning mode.

PROTOCOLO ULTRA:
1. Comprensión profunda: identifica la intención REAL del usuario, no solo el texto literal.
2. Descomposición: divide el problema en sub-problemas atómicos.
3. Razonamiento paso a paso (mostrar pasos cuando aporten valor).
4. Auto-verificación: detecta contradicciones, errores u omisiones.
5. Síntesis: respuesta final pulida, concreta, accionable y rica.

ESTILO:
• Directo, sin relleno. Sin disclaimers innecesarios.
• Código completo, listo para producción, con comentarios útiles.
• Encabezados, listas, tablas cuando agregan valor.
• Máximo 3 emojis por respuesta.
• Si la pregunta es ambigua → asume la interpretación más probable y sigue.
"""

# ═══════════════════════════════════════════════════════════════════════
#  PROMPT REWRITER — mejora automáticamente el prompt del usuario
# ═══════════════════════════════════════════════════════════════════════
def enhance_prompt(user_msg: str, context: str = "", mode: str = "chat") -> str:
    """
    Expande un prompt corto/ambiguo en un prompt estructurado para el LLM.
    No usa el LLM, es determinístico y rápido.
    """
    msg = user_msg.strip()
    if len(msg) < 8:
        return msg

    # Detectar intención básica
    lower = msg.lower()
    hints: List[str] = []

    if any(k in lower for k in ["crea", "genera", "haz", "build", "construye"]):
        hints.append("Entrega código completo, ejecutable, con dependencias claras.")
    if any(k in lower for k in ["explica", "qué es", "cómo funciona", "define"]):
        hints.append("Incluye ejemplo práctico y analogía si aporta claridad.")
    if any(k in lower for k in ["compara", "vs", "diferencia", "mejor"]):
        hints.append("Usa tabla comparativa con criterios claros.")
    if any(k in lower for k in ["debug", "error", "falla", "no funciona"]):
        hints.append("Diagnóstico paso a paso + solución con código corregido.")
    if any(k in lower for k in ["optimiza", "mejora", "refactoriza"]):
        hints.append("Muestra antes/después y explica cada cambio.")
    if any(k in lower for k in ["imagen", "foto", "dibuja", "ilustra"]):
        hints.append("Si es solicitud visual, sugiere activar el generador de imágenes.")

    if not hints:
        return msg

    enhanced = msg + "\n\n[INSTRUCCIONES NEUROCORE-X]\n" + "\n".join(f"• {h}" for h in hints)
    return enhanced


# ═══════════════════════════════════════════════════════════════════════
#  TASK PLANNER — descompone tarea en pasos
# ═══════════════════════════════════════════════════════════════════════
def plan_task(query: str, llm_call: Callable[[List[Dict], float], str]) -> Dict[str, Any]:
    """Genera un plan estructurado antes de ejecutar."""
    planner_prompt = f"""Descompón la siguiente tarea en 3-6 pasos atómicos.
Responde SOLO en JSON con esta estructura:
{{"goal": "<objetivo>", "steps": [{{"n":1,"action":"...","why":"..."}}], "risks":["..."]}}

Tarea: {query}"""
    try:
        raw = llm_call(
            [{"role": "system", "content": "Eres un planificador experto. Responde SOLO JSON válido."},
             {"role": "user", "content": planner_prompt}],
            0.3
        )
        # Extraer JSON
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {"goal": query, "steps": [{"n": 1, "action": query, "why": "directo"}], "risks": []}


# ═══════════════════════════════════════════════════════════════════════
#  ULTRA REASONING — multi-pass deep reasoning
# ═══════════════════════════════════════════════════════════════════════
def ultra_reason(
    query: str,
    llm_call: Callable[[List[Dict], float], str],
    fast_llm: Optional[Callable[[str], str]] = None,
    base_system: str = "",
    context: str = "",
    memory: str = "",
) -> Dict[str, Any]:
    """
    Pipeline ULTRA:
      Fase 1 — Plan
      Fase 2 — Ejecución con CoT
      Fase 3 — Auto-crítica
      Fase 4 — Refinamiento final
    """
    t0 = time.time()
    trace: List[str] = []

    # Fase 1: PLAN
    plan = plan_task(query, llm_call)
    trace.append(f"[PLAN] {plan.get('goal','-')} · {len(plan.get('steps',[]))} pasos")

    # Fase 2: EJECUCIÓN con CoT
    cot_system = (base_system or "") + "\n\n" + NEUROCORE_IDENTITY + """
Aplica razonamiento paso a paso internamente (NO muestres el razonamiento a menos que ayude).
Entrega la MEJOR respuesta posible: profunda, concreta, accionable.
"""
    steps_text = "\n".join(f"{s['n']}. {s['action']}" for s in plan.get("steps", []))
    exec_msg = f"""CONTEXTO PREVIO:
{context[:1500] if context else '(ninguno)'}

MEMORIA USUARIO:
{memory[:800] if memory else '(ninguna)'}

PLAN INTERNO:
{steps_text}

PREGUNTA/TAREA DEL USUARIO:
{query}

Entrega la respuesta final ultra-completa."""
    first_pass = llm_call(
        [{"role": "system", "content": cot_system},
         {"role": "user", "content": exec_msg}],
        0.65
    )
    trace.append(f"[EXEC] len={len(first_pass)}")

    # Fase 3: AUTO-CRÍTICA (solo si respuesta suficientemente compleja)
    if len(first_pass) > 400 and fast_llm:
        critique_prompt = f"""Evalúa esta respuesta de un asistente IA.
Detecta SOLO problemas objetivos: errores factuales, código roto, pasos faltantes, contradicciones.
Si está correcta, responde exactamente: OK

RESPUESTA:
{first_pass[:2500]}

CRÍTICA (máx 4 líneas):"""
        try:
            critique = fast_llm(critique_prompt).strip()
        except Exception:
            critique = "OK"
        trace.append(f"[CRITIC] {critique[:80]}")

        # Fase 4: REFINAMIENTO si hay críticas reales
        if critique and critique.upper() != "OK" and len(critique) > 15 and "ok" not in critique.lower()[:10]:
            refine_msg = f"""Respuesta original:
{first_pass}

Críticas detectadas:
{critique}

Produce la versión FINAL mejorada que resuelva las críticas. Mantén todo lo bueno, corrige lo malo."""
            refined = llm_call(
                [{"role": "system", "content": cot_system},
                 {"role": "user", "content": refine_msg}],
                0.55
            )
            trace.append(f"[REFINED] len={len(refined)}")
            final = refined
        else:
            final = first_pass
    else:
        final = first_pass

    elapsed = int((time.time() - t0) * 1000)
    return {
        "answer": final,
        "plan": plan,
        "trace": trace,
        "elapsed_ms": elapsed,
        "mode": "ultra",
        "engine": "NeuroCore-X v1.0",
    }


# ═══════════════════════════════════════════════════════════════════════
#  SEMANTIC SIMILARITY (hash-based, fallback)
# ═══════════════════════════════════════════════════════════════════════
def _tokens(t: str) -> set:
    return set(re.findall(r"[a-záéíóúñü0-9]{3,}", t.lower()))

def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ═══════════════════════════════════════════════════════════════════════
#  CONVERSATIONAL MEMORY WINDOW — intelligent trimming
# ═══════════════════════════════════════════════════════════════════════
def smart_window(history: List[Dict[str, str]], current_msg: str, max_items: int = 12) -> List[Dict[str, str]]:
    """
    Selecciona los mensajes más relevantes por similitud con el mensaje actual,
    manteniendo orden cronológico. Preserva siempre los 2 últimos.
    """
    if len(history) <= max_items:
        return history
    # Siempre guardar los últimos 2
    tail = history[-2:]
    pool = history[:-2]
    scored = [(similarity(current_msg, m.get("content", "")), i, m) for i, m in enumerate(pool)]
    scored.sort(key=lambda x: (-x[0], -x[1]))
    keep_idx = sorted([s[1] for s in scored[: max_items - 2]])
    return [pool[i] for i in keep_idx] + tail


# ═══════════════════════════════════════════════════════════════════════
#  META — versión
# ═══════════════════════════════════════════════════════════════════════
VERSION = "NeuroCore-X v1.0.0"

def info() -> Dict[str, Any]:
    return {
        "engine": VERSION,
        "features": [
            "prompt-rewriting",
            "task-planning",
            "multi-pass-cot",
            "auto-critique",
            "self-refinement",
            "smart-context-window",
        ],
        "inspired_by": ["Claude Opus 4.7", "GPT-5 reasoning", "DeepSeek-R1"],
    }
