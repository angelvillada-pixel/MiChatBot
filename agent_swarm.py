"""
═══════════════════════════════════════════════════════════════════════════
 agent_swarm.py · DeepNova v7.0 · Orquestador Multi-Agente Real
═══════════════════════════════════════════════════════════════════════════
 Sistema de "swarm" coordinado: cada agente es un especialista que recibe
 una sub-tarea relevante a su rol, y un Coordinator integra los resultados.

 Roles incluidos:
   • Researcher   → recolección de datos / contexto
   • Architect    → diseño y arquitectura
   • Coder        → implementación / código
   • Tester       → validación, casos de prueba, edge cases
   • Reviewer     → crítica constructiva, calidad
   • Documenter   → documentación clara y útil
   • Optimizer    → rendimiento, costo, mantenibilidad

 Ejecución paralela vía ThreadPoolExecutor cuando es seguro hacerlo.

 Áreas cubiertas (del documento de mejoras):
   ✓ 5.2 Trabajo en equipo (multi-agente)
   ✓ 4.1 Automatización de tareas complejas
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import time
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Dict, Any, Optional


# ──────────────────────────────────────────────────────────────────────
#  Definición de roles (system prompts especializados)
# ──────────────────────────────────────────────────────────────────────
AGENT_ROLES: Dict[str, Dict[str, str]] = {
    "researcher": {
        "name": "🔍 Investigador",
        "system": (
            "Eres un investigador senior. Tu rol es identificar la información "
            "clave necesaria para resolver la tarea. Lista hechos, datos, "
            "supuestos a verificar y preguntas abiertas. Sé conciso y específico. "
            "No inventes datos."
        ),
    },
    "architect": {
        "name": "🏛️ Arquitecto",
        "system": (
            "Eres un arquitecto de software senior. Diseña la solución a alto "
            "nivel: componentes, flujos de datos, decisiones técnicas con "
            "justificación, y trade-offs. Usa diagramas en texto si ayuda."
        ),
    },
    "coder": {
        "name": "💻 Programador",
        "system": (
            "Eres un programador senior. Implementa la solución con código "
            "completo, ejecutable y limpio. Incluye imports, manejo de errores, "
            "logging básico y un ejemplo mínimo de uso."
        ),
    },
    "tester": {
        "name": "🧪 Tester",
        "system": (
            "Eres un QA engineer. Diseña casos de prueba (happy path, edge cases, "
            "errores esperables, casos límite). Si aplica, incluye tests "
            "ejecutables (pytest)."
        ),
    },
    "reviewer": {
        "name": "🧐 Revisor",
        "system": (
            "Eres un reviewer crítico y justo. Identifica problemas: bugs, "
            "vulnerabilidades, anti-patrones, código difícil de mantener. "
            "Sugiere mejoras concretas con ejemplos. No seas pedante."
        ),
    },
    "documenter": {
        "name": "📚 Documentador",
        "system": (
            "Eres un technical writer. Redacta documentación clara y útil: "
            "qué hace, cómo se usa, ejemplos prácticos, troubleshooting. "
            "Markdown bien estructurado, sin relleno."
        ),
    },
    "optimizer": {
        "name": "⚡ Optimizador",
        "system": (
            "Eres un experto en optimización. Revisa rendimiento "
            "(tiempo/memoria), costos (cloud/API), mantenibilidad. "
            "Sugiere mejoras medibles con justificación."
        ),
    },
}


# ──────────────────────────────────────────────────────────────────────
#  Selección automática de roles según la tarea
# ──────────────────────────────────────────────────────────────────────
def choose_roles(task: str) -> List[str]:
    """Devuelve la lista de roles relevantes para la tarea (orden ejecutivo)."""
    low = (task or "").lower()
    chosen: List[str] = []

    # heurísticas
    if any(k in low for k in ["investiga", "busca", "datos", "tendencia", "mercado",
                              "competidores", "research"]):
        chosen.append("researcher")
    if any(k in low for k in ["diseña", "arquitectura", "estructura", "planifica",
                              "design", "architecture"]):
        chosen.append("architect")
    if any(k in low for k in ["código", "implementa", "programa", "function",
                              "api", "endpoint", "script", "build"]):
        chosen.append("coder")
    if any(k in low for k in ["prueba", "test", "edge case", "qa", "valida"]):
        chosen.append("tester")
    if any(k in low for k in ["review", "revisa", "critica", "audita"]):
        chosen.append("reviewer")
    if any(k in low for k in ["documenta", "readme", "docstring", "manual"]):
        chosen.append("documenter")
    if any(k in low for k in ["optimiza", "performance", "rendimiento", "costo",
                              "lento"]):
        chosen.append("optimizer")

    # Fallback inteligente: si nada matchea, usar pipeline core
    if not chosen:
        chosen = ["researcher", "architect", "coder", "reviewer"]

    # eliminar duplicados manteniendo orden
    seen = set()
    return [r for r in chosen if not (r in seen or seen.add(r))]


# ──────────────────────────────────────────────────────────────────────
#  Ejecución del swarm
# ──────────────────────────────────────────────────────────────────────
def run_swarm(
    task: str,
    llm_call: Callable[[List[Dict], float], str],
    *,
    roles: Optional[List[str]] = None,
    base_system: str = "",
    parallel: bool = True,
    max_workers: int = 4,
    context: str = "",
) -> Dict[str, Any]:
    """Ejecuta múltiples agentes especializados y unifica el resultado.

    Pipeline:
      1) Investigación / análisis (paralelo posible)
      2) Diseño / planificación
      3) Implementación / contenido
      4) Revisión y validación
      5) Síntesis del Coordinator

    Returns:
        {
          "answer": str,           # respuesta unificada al usuario
          "trace": list[dict],     # outputs por agente
          "elapsed_ms": int,
          "engine": "AgentSwarm-v1",
          "roles_used": [...]
        }
    """
    t0 = time.time()
    if not roles:
        roles = choose_roles(task)

    role_specs = [{"key": r, **AGENT_ROLES[r]} for r in roles if r in AGENT_ROLES]

    # ── 1) Fase paralela: roles "informativos" (researcher, architect, optimizer, reviewer)
    parallel_roles = {"researcher", "architect", "optimizer", "tester", "reviewer", "documenter"}
    sequential_roles = {"coder"}  # el coder se beneficia de tener el resto antes

    parallel_specs = [s for s in role_specs if s["key"] in parallel_roles]
    sequential_specs = [s for s in role_specs if s["key"] in sequential_roles]

    trace: List[Dict[str, Any]] = []

    def _exec_agent(spec: Dict[str, str], extra_ctx: str = "") -> Dict[str, Any]:
        sys = (base_system or "") + "\n\n" + spec["system"]
        user = task
        if context:
            user = f"[CONTEXTO]\n{context[:1500]}\n\n[TAREA]\n{task}"
        if extra_ctx:
            user = f"{user}\n\n[APORTACIONES PREVIAS DEL EQUIPO]\n{extra_ctx[:2000]}"
        msgs = [
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ]
        ts = time.time()
        try:
            out = llm_call(msgs, 0.5) or "[sin respuesta]"
        except Exception as e:
            out = f"[error en {spec['key']}: {e}]"
        return {
            "role": spec["key"],
            "name": spec["name"],
            "output": out,
            "elapsed_ms": int((time.time() - ts) * 1000),
        }

    if parallel and parallel_specs:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_exec_agent, s): s for s in parallel_specs}
            for fut in as_completed(futures):
                trace.append(fut.result())
    else:
        for s in parallel_specs:
            trace.append(_exec_agent(s))

    # ── 2) Coder con todo el contexto previo
    if sequential_specs:
        prev_ctx = "\n\n".join(
            f"### {t['name']}\n{t['output'][:1200]}" for t in trace
        )
        for s in sequential_specs:
            trace.append(_exec_agent(s, extra_ctx=prev_ctx))

    # Reordena el trace según el orden lógico de roles
    trace.sort(key=lambda t: roles.index(t["role"]) if t["role"] in roles else 99)

    # ── 3) Coordinator: síntesis final
    answer = _coordinator_synthesis(task, trace, llm_call, base_system)

    return {
        "answer": answer,
        "trace": trace,
        "roles_used": [t["role"] for t in trace],
        "elapsed_ms": int((time.time() - t0) * 1000),
        "engine": "AgentSwarm-v1",
    }


# ──────────────────────────────────────────────────────────────────────
#  Coordinator
# ──────────────────────────────────────────────────────────────────────
COORDINATOR_PROMPT = """Eres el Coordinator del swarm de agentes DeepNova.

Tarea original:
{task}

Aportaciones de los agentes especializados:

{contributions}

Sintetiza una RESPUESTA FINAL para el usuario:
- Empieza con la solución concreta (sin meta-comentarios sobre el equipo)
- Integra las mejores aportaciones de cada agente
- Resuelve contradicciones entre agentes con criterio
- Estructura con encabezados y código si aporta valor
- Sin relleno, sin disclaimers innecesarios
- Profesional, completa, accionable
"""


def _coordinator_synthesis(task: str, trace: List[Dict[str, Any]],
                            llm_call, base_system: str) -> str:
    contributions = "\n\n".join(
        f"### {t['name']}\n{t['output']}" for t in trace
    )
    msgs = [
        {"role": "system", "content": base_system or ""},
        {"role": "user", "content": COORDINATOR_PROMPT.format(
            task=task, contributions=contributions[:8000],
        )},
    ]
    try:
        return llm_call(msgs, 0.4) or trace[-1]["output"]
    except Exception:
        # fallback: concatenar las contribuciones
        return contributions


# ──────────────────────────────────────────────────────────────────────
#  Render Markdown del trace (debug / transparencia opcional)
# ──────────────────────────────────────────────────────────────────────
def trace_to_markdown(trace: List[Dict[str, Any]]) -> str:
    lines = ["## 🐝 Trace del swarm\n"]
    for t in trace:
        lines.append(f"### {t['name']}  · `{t['role']}`  ·  {t['elapsed_ms']} ms\n")
        lines.append(t["output"][:1500])
        lines.append("\n---\n")
    return "\n".join(lines)
