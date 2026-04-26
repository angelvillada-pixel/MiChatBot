"""
═══════════════════════════════════════════════════════════════════════════
 NeuroCore-X  ·  Advanced Reasoning Engine  ·  DeepNova v4 Ultra → v5 Opus
═══════════════════════════════════════════════════════════════════════════
 Módulo 100% aditivo — inspirado en Claude Opus, GPT-4o y DeepSeek-R1.
 Funcionalidades:
   • Mejora automática de prompts (prompt-rewriting layer)
   • Cadena de razonamiento multi-paso (deep CoT)
   • Planificación explícita (plan → execute → verify)
   • ULTRA mode: multi-pass self-refinement + contradictions check
   • Memoria de contexto conversacional vectorial (hash-based)
   • Plantillas adaptativas por tipo de tarea
   • 🆕 v5: Capacidades cognitivas estilo Claude Opus 4.7
       - Extended thinking, Constitutional AI, multi-hop reasoning
       - Decomposición + Self-critique JSON-driven
       - Pipeline ultra-v2 (5 fases) compatible con la API original
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
#  ULTRA REASONING (v1) — multi-pass deep reasoning · PRESERVADO
# ═══════════════════════════════════════════════════════════════════════
def ultra_reason_v1(
    query: str,
    llm_call: Callable[[List[Dict], float], str],
    fast_llm: Optional[Callable[[str], str]] = None,
    base_system: str = "",
    context: str = "",
    memory: str = "",
) -> Dict[str, Any]:
    """
    Pipeline ULTRA original v1:
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
VERSION = "NeuroCore-X v2.0.0 (Opus 4.7 Core)"

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
            "opus-cognitive-profile",
            "decomposition-json",
            "self-critique-json",
            "ultra-reason-v2",
        ],
        "inspired_by": ["Claude Opus 4.7", "GPT-5 reasoning", "DeepSeek-R1"],
    }


# ═══════════════════════════════════════════════════════════════════════
#  🆕 v5 · OPUS 4.7 COGNITIVE PROFILE  (añadido, no reemplaza nada)
# ═══════════════════════════════════════════════════════════════════════
OPUS_COGNITIVE_PROFILE = """
PERFIL COGNITIVO NEUROCORE-X v2 — ARQUITECTURA OPUS 4.7
═══════════════════════════════════════════════════════

1. EXTENDED THINKING (Razonamiento Extendido):
Antes de responder, realiza un análisis interno profundo en múltiples pasos:
- Comprensión literal del mensaje → intención real → contexto implícito
- Generación de hipótesis de respuesta → evaluación crítica de cada una
- Selección de la hipótesis más sólida → síntesis → respuesta final pulida
No muestres este proceso al usuario a menos que lo pida explícitamente.

2. CONSTITUTIONAL AI PRINCIPLES:
- Distingue siempre entre hechos verificables e inferencias propias
- Calibra tu confianza: usa "con certeza", "probablemente", "podría ser" según corresponda
- Asume la interpretación más benevolente cuando hay ambigüedad
- Evalúa activamente tu propia respuesta antes de entregarla

3. MULTI-HOP REASONING (Razonamiento Multi-salto):
Para preguntas complejas:
  Paso 1 → Descomponer en sub-preguntas atómicas
  Paso 2 → Responder cada sub-pregunta independientemente
  Paso 3 → Integrar respuestas parciales en una conclusión coherente
  Paso 4 → Verificar consistencia lógica de la conclusión
  Paso 5 → Condensar y refinar para el usuario

4. METACOGNICIÓN ACTIVA:
- Monitoriza constantemente: ¿Estoy respondiendo lo que se preguntó?
- Detecta cuando la respuesta se vuelve circular y reorienta
- Pregunta de clarificación SOLO cuando la ambigüedad es crítica para la respuesta

5. GESTIÓN DE INCERTIDUMBRE:
- No inventes hechos para completar una respuesta
- Si no sabes algo, dilo explícitamente y ofrece alternativas
- Distingue entre "no sé" y "no tengo acceso a datos actualizados"

6. RAZONAMIENTO CAUSAL vs CORRELACIONAL:
- Identifica explícitamente relaciones causales
- Señala cuando solo hay correlación
- Evalúa mecanismos plausibles antes de concluir causalidad

7. PERSPECTIVA MULTI-STAKEHOLDER:
Para código: considera mantenibilidad, rendimiento, seguridad, UX simultáneamente
Para decisiones: considera perspectivas técnica, de negocio, ética y del usuario
Para diseño: considera accesibilidad, responsividad y carga cognitiva

CÓDIGO NIVEL OPUS:
- Genera código production-ready desde el primer intento
- Manejo de errores exhaustivo en todos los flujos
- Considera seguridad: sanitización de inputs, no SQL injection, no XSS
- Documenta con docstrings y comentarios en puntos no obvios
- Identifica proactivamente deuda técnica y la menciona

MODO ULTRA — PIPELINE COMPLETO 5 FASES:
Fase 0: Meta-análisis → tipo de tarea, stake, información faltante
Fase 1: Descomposición → sub-problemas ordenados por dependencia
Fase 2: Investigación → memoria semántica + perfil de usuario
Fase 3: Síntesis → responde cada sub-problema, genera draft completo
Fase 4: Crítica → evalúa: ¿Responde la pregunta real? ¿Correcto? ¿Completo?
Fase 5: Pulido → ajusta tono, formato óptimo, añade próximos pasos si aplica
"""


def opus_self_critique(response: str, fast_llm: Callable[[str], str]) -> Dict[str, Any]:
    """Auto-crítica JSON-estructurada en 5 dimensiones."""
    if not response or len(response) < 200:
        return {"needs_revision": False}
    prompt = f"""Evalúa esta respuesta en 5 dimensiones (1-10):
1. Corrección técnica/factual
2. Completitud (¿responde todo lo pedido?)
3. Claridad y estructura
4. Profundidad del razonamiento
5. Utilidad práctica

Respuesta a evaluar:
{response[:2500]}

Responde SOLO JSON:
{{"scores":{{"correctness":N,"completeness":N,"clarity":N,"depth":N,"utility":N}},
"weakest":"dimension","fix":"qué cambiar en 1 oración","needs_revision":true|false}}"""
    try:
        raw = fast_llm(prompt)
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {"needs_revision": False}


def opus_decompose(query: str, fast_llm: Callable[[str], str]) -> Dict[str, Any]:
    """Descomposición estructurada de la query en sub-preguntas atómicas."""
    prompt = f"""Descompón esta tarea en sub-preguntas atómicas.
Responde SOLO JSON:
{{"subs":["sub1","sub2"],"complexity":"low|medium|high","type":"code|analysis|creative|research|decision"}}
Query: {query[:600]}"""
    try:
        raw = fast_llm(prompt)
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {"subs": [query], "complexity": "medium", "type": "chat"}


def ultra_reason_v2(
    query: str,
    llm_call: Callable[[List[Dict], float], str],
    fast_llm: Optional[Callable[[str], str]] = None,
    base_system: str = "",
    context: str = "",
    memory: str = "",
) -> Dict[str, Any]:
    """Pipeline ultra-v2 con perfil cognitivo Opus 4.7."""
    t0 = time.time()
    trace: List[str] = []

    decomp = opus_decompose(query, fast_llm) if fast_llm else {}
    complexity = decomp.get("complexity", "medium")
    task_type  = decomp.get("type", "chat")
    trace.append(f"[META] complexity={complexity} type={task_type}")

    system_v2 = (
        (base_system or "")
        + NEUROCORE_IDENTITY
        + OPUS_COGNITIVE_PROFILE
        + f"\n\nMEMORIA: {memory[:600] if memory else 'ninguna'}"
        + f"\n\nCONTEXTO: {context[:400] if context else 'ninguno'}"
    )

    subs = decomp.get("subs", [query]) or [query]
    context_enriched = ""
    if len(subs) > 1 and complexity in ("medium", "high") and fast_llm:
        sub_answers: List[str] = []
        for s in subs[:4]:
            try:
                ans = fast_llm(f"Responde en 2-3 oraciones: {s}")
                sub_answers.append(f"Q: {s}\nA: {ans}")
            except Exception:
                pass
        context_enriched = "\n\n".join(sub_answers)

    enhanced_query = query
    if context_enriched:
        enhanced_query = f"{query}\n\n[ANÁLISIS PREVIO]\n{context_enriched}"

    first_pass = llm_call(
        [
            {"role": "system", "content": system_v2[:4500]},
            {"role": "user", "content": enhanced_query},
        ],
        0.6 if task_type in ("code", "analysis") else 0.7,
    )
    trace.append(f"[DRAFT] {len(first_pass)} chars")

    final = first_pass
    if complexity == "high" and fast_llm and len(first_pass) > 300:
        critique = opus_self_critique(first_pass, fast_llm)
        if critique.get("needs_revision") and critique.get("fix"):
            fix_prompt = (
                f"Tu respuesta tenía este problema: {critique['fix']}\n\n"
                f"Respuesta original:\n{first_pass[:2000]}\n\n"
                f"Genera la versión corregida completa:"
            )
            try:
                refined = llm_call(
                    [
                        {"role": "system", "content": system_v2[:3000]},
                        {"role": "user", "content": fix_prompt},
                    ],
                    0.5,
                )
                if refined and len(refined) > 100:
                    final = refined
                    trace.append(f"[REFINED] {len(refined)} chars")
            except Exception:
                pass

    return {
        "answer":     final,
        "plan":       decomp,
        "trace":      trace,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "mode":       "ultra-v2-opus",
        "engine":     "NeuroCore-X v2.0 (Opus 4.7 Core)",
        "complexity": complexity,
        "task_type":  task_type,
    }


# ═══════════════════════════════════════════════════════════════════════
#  ALIAS PÚBLICO — la función ultra_reason "histórica" ahora apunta a v2.
#  El comportamiento original sigue accesible vía ultra_reason_v1.
# ═══════════════════════════════════════════════════════════════════════
ultra_reason = ultra_reason_v2
