"""
═══════════════════════════════════════════════════════════════════════════
 multi_hop_reasoner.py · DeepNova v7.0 · Razonamiento Multi-Salto + ToT
═══════════════════════════════════════════════════════════════════════════
 Implementa:
   • Descomposición jerárquica (problem → sub-problems → atomic steps)
   • Tree-of-Thoughts (ToT) con poda heurística y backtracking
   • Verificación cruzada entre pasos (consistency check)
   • Síntesis final con citas internas paso → conclusión

 Diseño:
   - Drop-in: recibe `llm_call` como callable (igual que neurocore_x)
   - 100% aditivo, no toca lógica existente
   - Fallback robusto si el LLM falla en cualquier nodo

 Áreas cubiertas (del documento de mejoras):
   ✓ 3.1 Razonamiento multi-salto avanzado
   ✓ 3.2 Integración de conocimiento de dominio (vía domain_knowledge)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import re
import json
import time
from typing import Callable, List, Dict, Any, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────
#  Config
# ──────────────────────────────────────────────────────────────────────
MAX_DEPTH        = 3
MAX_BRANCHES     = 3
MIN_CONFIDENCE   = 0.55
MAX_TOTAL_NODES  = 12   # presupuesto total de nodos para evitar explosión

# Plantilla para descomponer en sub-problemas
DECOMPOSE_PROMPT = """Eres un experto en descomposición de problemas complejos.

Tarea: {query}

Descompón la tarea en EXACTAMENTE entre 2 y 4 sub-problemas atómicos
que, resueltos secuencialmente, lleven a la solución completa.

Responde SOLO con JSON válido:
{{
  "needs_decomposition": true|false,
  "subproblems": [
    {{"id": 1, "question": "...", "depends_on": [], "type": "factual|analytical|creative|computational"}},
    ...
  ],
  "rationale": "breve explicación"
}}

Si la tarea es simple y no requiere descomposición, devuelve
{{"needs_decomposition": false, "subproblems": [], "rationale": "..."}}.
"""

# Plantilla para generar caminos alternativos (ToT)
BRANCH_PROMPT = """Estás resolviendo este sub-problema:

{subproblem}

Contexto previo:
{context}

Genera EXACTAMENTE {n_branches} enfoques distintos y prometedores para resolverlo.
Sé conciso (máx 2 frases por enfoque).

Responde SOLO con JSON:
{{
  "branches": [
    {{"id": 1, "approach": "...", "expected_confidence": 0.0-1.0}},
    ...
  ]
}}
"""

# Plantilla para evaluar/ejecutar una rama
EXECUTE_BRANCH_PROMPT = """Ejecuta este enfoque para responder al sub-problema.

Sub-problema: {subproblem}
Enfoque elegido: {approach}
Contexto: {context}

Da una respuesta sólida y concreta. Al final añade en una línea:
CONFIDENCE: 0.0-1.0
"""

# Verificación cruzada
VERIFY_PROMPT = """Verifica la coherencia entre estos pasos resueltos:

{steps_summary}

Detecta:
- Contradicciones internas
- Saltos lógicos no justificados
- Conclusiones que no se siguen de las premisas

Responde SOLO JSON:
{{"consistent": true|false, "issues": ["..."], "confidence": 0.0-1.0}}
"""

# Síntesis final
SYNTHESIS_PROMPT = """Pregunta original del usuario:
{query}

Pasos resueltos (con su confianza):
{steps_block}

Verificación de consistencia: {verification}

Sintetiza la RESPUESTA FINAL al usuario:
- Respuesta directa primero
- Luego razonamiento estructurado (si aporta)
- Cita los pasos como [paso N] cuando sea relevante
- Profesional, sin relleno
"""

# ──────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # intento de saneado simple
        try:
            cleaned = m.group(0).replace("\n", " ")
            return json.loads(cleaned)
        except Exception:
            return None


def _parse_confidence(text: str, default: float = 0.6) -> float:
    m = re.search(r"CONFIDENCE\s*:\s*([0-9]*\.?[0-9]+)", text or "", re.IGNORECASE)
    if not m:
        return default
    try:
        v = float(m.group(1))
        return max(0.0, min(1.0, v))
    except Exception:
        return default


# ──────────────────────────────────────────────────────────────────────
#  Pipeline principal
# ──────────────────────────────────────────────────────────────────────
def reason(
    query: str,
    llm_call: Callable[[List[Dict], float], str],
    *,
    fast_llm: Optional[Callable[[str], str]] = None,
    base_system: str = "",
    domain_context: str = "",
    max_depth: int = MAX_DEPTH,
    max_branches: int = MAX_BRANCHES,
) -> Dict[str, Any]:
    """Razonamiento multi-salto con ToT.

    Returns:
        {
          "answer": str,        # respuesta final al usuario
          "plan": dict,         # plan de descomposición
          "trace": list[dict],  # cada sub-problema + rama elegida
          "verification": dict, # informe de consistencia
          "elapsed_ms": int,
          "engine": "MultiHop-ToT-v1"
        }
    """
    t0 = time.time()
    nodes_used = 0

    # ── 1) Descomposición ─────────────────────────────────────────
    plan = _decompose(query, llm_call, base_system, domain_context)
    nodes_used += 1

    subs: List[Dict[str, Any]] = plan.get("subproblems", []) or []
    if not plan.get("needs_decomposition") or not subs:
        # Tarea simple → ejecutar directamente con un solo paso
        subs = [{"id": 1, "question": query, "depends_on": [], "type": "direct"}]

    # ── 2) ToT por sub-problema ───────────────────────────────────
    trace: List[Dict[str, Any]] = []
    accumulated_context = domain_context

    for sub in subs:
        if nodes_used >= MAX_TOTAL_NODES:
            break
        # 2a) Generar ramas
        branches = _branch(
            sub["question"], accumulated_context, llm_call, base_system,
            n_branches=max_branches,
        )
        nodes_used += 1

        # 2b) Ejecutar cada rama y elegir la mejor
        executed: List[Dict[str, Any]] = []
        for br in branches[:max_branches]:
            if nodes_used >= MAX_TOTAL_NODES:
                break
            res = _execute_branch(
                sub["question"], br["approach"], accumulated_context,
                llm_call, base_system,
            )
            nodes_used += 1
            executed.append({
                "branch_id": br.get("id"),
                "approach": br["approach"],
                "answer": res["answer"],
                "confidence": res["confidence"],
            })

        if not executed:
            executed = [{
                "branch_id": 0,
                "approach": "fallback-directo",
                "answer": _fallback_direct(sub["question"], llm_call, base_system),
                "confidence": 0.5,
            }]
            nodes_used += 1

        # 2c) Selección por mayor confianza, con poda si todas son bajas
        best = max(executed, key=lambda x: x["confidence"])
        if best["confidence"] < MIN_CONFIDENCE and len(executed) > 1:
            # backtracking: reintenta con prompt enriquecido
            retry = _execute_branch(
                sub["question"],
                "Reconsidera el problema desde primeros principios.",
                accumulated_context, llm_call, base_system,
            )
            nodes_used += 1
            if retry["confidence"] > best["confidence"]:
                best = {
                    "branch_id": 99, "approach": "primeros principios",
                    "answer": retry["answer"], "confidence": retry["confidence"],
                }

        trace.append({
            "id": sub["id"],
            "question": sub["question"],
            "type": sub.get("type"),
            "explored_branches": executed,
            "selected": best,
        })

        # Acumula el resultado al contexto para el siguiente paso (multi-hop real)
        accumulated_context += f"\n\n[paso {sub['id']}] {sub['question']}\n→ {best['answer'][:600]}"

    # ── 3) Verificación cruzada ──────────────────────────────────
    verification = _verify(trace, llm_call, base_system) if len(trace) > 1 else {
        "consistent": True, "issues": [], "confidence": trace[0]["selected"]["confidence"] if trace else 0.0,
    }

    # ── 4) Síntesis final ─────────────────────────────────────────
    answer = _synthesize(query, trace, verification, llm_call, base_system)

    return {
        "answer": answer,
        "plan": plan,
        "trace": trace,
        "verification": verification,
        "nodes_used": nodes_used,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "engine": "MultiHop-ToT-v1",
    }


# ──────────────────────────────────────────────────────────────────────
#  Sub-pasos
# ──────────────────────────────────────────────────────────────────────
def _decompose(query: str, llm_call, base_system: str, domain_ctx: str) -> Dict[str, Any]:
    sys = (base_system or "") + "\nResponde estrictamente con JSON válido."
    if domain_ctx:
        sys += f"\n\n[CONOCIMIENTO DE DOMINIO]\n{domain_ctx[:1500]}"
    msgs = [
        {"role": "system", "content": sys},
        {"role": "user", "content": DECOMPOSE_PROMPT.format(query=query)},
    ]
    raw = _safe_call(llm_call, msgs, 0.3)
    parsed = _extract_json(raw) or {}
    if "subproblems" not in parsed:
        return {"needs_decomposition": False, "subproblems": [], "rationale": "fallback"}
    return parsed


def _branch(subproblem: str, context: str, llm_call, base_system: str, n_branches: int = 3) -> List[Dict[str, Any]]:
    msgs = [
        {"role": "system", "content": (base_system or "") + "\nResponde solo JSON válido."},
        {"role": "user", "content": BRANCH_PROMPT.format(
            subproblem=subproblem, context=(context or "—")[:1500], n_branches=n_branches,
        )},
    ]
    raw = _safe_call(llm_call, msgs, 0.7)
    parsed = _extract_json(raw) or {}
    branches = parsed.get("branches") or []
    if not branches:
        # fallback: una única rama directa
        branches = [{"id": 1, "approach": "Resolver directamente paso a paso.", "expected_confidence": 0.6}]
    return branches


def _execute_branch(subproblem: str, approach: str, context: str, llm_call, base_system: str) -> Dict[str, Any]:
    msgs = [
        {"role": "system", "content": base_system or ""},
        {"role": "user", "content": EXECUTE_BRANCH_PROMPT.format(
            subproblem=subproblem, approach=approach, context=(context or "—")[:1800],
        )},
    ]
    raw = _safe_call(llm_call, msgs, 0.5)
    return {"answer": (raw or "").strip(), "confidence": _parse_confidence(raw)}


def _fallback_direct(query: str, llm_call, base_system: str) -> str:
    msgs = [
        {"role": "system", "content": base_system or ""},
        {"role": "user", "content": query},
    ]
    return _safe_call(llm_call, msgs, 0.4) or "[sin respuesta]"


def _verify(trace: List[Dict[str, Any]], llm_call, base_system: str) -> Dict[str, Any]:
    summary_lines = []
    for i, step in enumerate(trace, 1):
        sel = step["selected"]
        summary_lines.append(
            f"[paso {i}] {step['question']}\n→ {sel['answer'][:400]} (conf={sel['confidence']:.2f})"
        )
    summary = "\n\n".join(summary_lines)
    msgs = [
        {"role": "system", "content": (base_system or "") + "\nResponde solo JSON válido."},
        {"role": "user", "content": VERIFY_PROMPT.format(steps_summary=summary)},
    ]
    raw = _safe_call(llm_call, msgs, 0.2)
    parsed = _extract_json(raw) or {"consistent": True, "issues": [], "confidence": 0.7}
    return parsed


def _synthesize(query: str, trace: List[Dict[str, Any]], verification: Dict[str, Any], llm_call, base_system: str) -> str:
    steps_block = "\n".join(
        f"[paso {i}] {s['question']}\n→ {s['selected']['answer'][:600]} (conf={s['selected']['confidence']:.2f})"
        for i, s in enumerate(trace, 1)
    )
    msgs = [
        {"role": "system", "content": base_system or ""},
        {"role": "user", "content": SYNTHESIS_PROMPT.format(
            query=query, steps_block=steps_block, verification=json.dumps(verification, ensure_ascii=False),
        )},
    ]
    return _safe_call(llm_call, msgs, 0.5) or trace[-1]["selected"]["answer"] if trace else ""


def _safe_call(llm_call, messages: List[Dict], temperature: float) -> str:
    try:
        out = llm_call(messages, temperature)
        return out or ""
    except Exception as e:
        return f"[llm-error: {e}]"
