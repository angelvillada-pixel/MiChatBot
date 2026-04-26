"""
═══════════════════════════════════════════════════════════════════════════
 agents.py  ·  DeepNova v6.0 · Sistema de Agentes Autónomos
═══════════════════════════════════════════════════════════════════════════
 - Agent: agente básico que descompone y ejecuta paso a paso
 - EmpireAgent: agente avanzado que planifica con IA → ejecuta → optimiza
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Any, List, Optional
import logging

logger = logging.getLogger("agents")


class Agent:
    """Agente autónomo básico (estilo AutoGPT-lite).

    Recibe un objetivo, lo divide en pasos predefinidos y ejecuta cada uno
    a través del orquestador NeuroCore.
    """

    def __init__(self, core: Any):
        self.core = core

    def run_sync(self, goal: str, model_id: Optional[str] = None) -> str:
        steps = [
            f"Analiza el objetivo y detecta intención: {goal}",
            f"Divide el objetivo en sub-tareas atómicas: {goal}",
            f"Ejecuta cada sub-tarea y produce resultados parciales para: {goal}",
            f"Optimiza y unifica el resultado final del objetivo: {goal}",
        ]
        results: List[str] = []
        for i, step in enumerate(steps, 1):
            logger.info("[agent] paso %d/%d", i, len(steps))
            try:
                r = self.core.process_sync(step, model_id=model_id)
            except Exception as e:
                logger.warning("[agent] paso %d falló: %s", i, e)
                r = f"(paso {i} omitido: {e})"
            results.append(f"### Paso {i}\n{r}")
        return "\n\n".join(results)

    async def run(self, goal: str, model_id: Optional[str] = None) -> str:
        steps = [
            f"Analiza el objetivo: {goal}",
            "Divide en subtareas",
            "Ejecuta cada paso",
            "Optimiza resultado final",
        ]
        results: List[str] = []
        for step in steps:
            try:
                r = await self.core.process(step, model_id=model_id)
            except Exception as e:
                r = f"(error: {e})"
            results.append(r)
        return "\n".join(results)


class EmpireAgent:
    """Agente avanzado: planifica con IA, ejecuta y optimiza dinámicamente."""

    def __init__(self, core: Any):
        self.core = core

    async def execute_goal(self, goal: str, model_id: Optional[str] = None) -> str:
        # 1) Planificar con IA
        plan = await self.core.process(
            f"Divide este objetivo en pasos numerados (uno por línea, sin texto extra): {goal}",
            model_id=model_id,
        )
        steps = [s.strip(" -•0123456789.") for s in str(plan).split("\n") if s.strip()]
        if not steps:
            steps = [goal]

        # 2) Ejecutar cada paso
        results: List[str] = []
        for i, step in enumerate(steps[:8], 1):  # cap de seguridad
            try:
                res = await self.core.process(step, model_id=model_id)
                results.append(f"[{i}] {step}\n→ {res}")
            except Exception as e:
                results.append(f"[{i}] {step}\n→ (error: {e})")

        # 3) Optimizar/unificar
        try:
            joined = "\n\n".join(results)
            final = await self.core.process(
                f"Unifica y optimiza estos resultados parciales en una respuesta final coherente:\n\n{joined}",
                model_id=model_id,
            )
            return final
        except Exception:
            return "\n\n".join(results)
