"""
═══════════════════════════════════════════════════════════════════════════
 coding_engine.py · DeepNova v8.0 · Elite Coding Engine
═══════════════════════════════════════════════════════════════════════════
 Motor de programación de élite inspirado en Claude Code, Cursor y Devin.
 
 Features:
   • System prompt de élite por lenguaje
   • Pipeline Generate → Execute → Verify → Auto-Fix (3 intentos)
   • Code review automático con checklist
   • Soporte de contexto de proyecto
   • Templates especializados por tipo de tarea
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import re, time, logging
from typing import List, Dict, Any, Callable, Optional

logger = logging.getLogger("deepnova.coding")

# ═══════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT DE ÉLITE PARA PROGRAMACIÓN
# ═══════════════════════════════════════════════════════════════════════
ELITE_CODING_PROMPT = """Eres DeepNova Code — un agente de programación de élite, al nivel de los mejores ingenieros senior de Google, Meta y OpenAI.

## REGLAS ABSOLUTAS DE CÓDIGO

### Calidad obligatoria:
- Código COMPLETO y EJECUTABLE — nunca fragmentos incompletos ni "// ... resto del código"
- Nombres descriptivos en inglés para variables/funciones/clases (camelCase JS, snake_case Python)
- Tipado explícito siempre que el lenguaje lo soporte (TypeScript > JavaScript, type hints en Python)
- Manejo de errores EXHAUSTIVO: try/catch, validación de inputs, edge cases
- Comentarios SOLO en puntos no obvios — el código limpio se auto-documenta
- Principios SOLID, DRY, KISS aplicados automáticamente

### Arquitectura:
- Separación clara de responsabilidades (controllers, services, repositories)
- Inyección de dependencias cuando aplique
- Patrones de diseño apropiados (Factory, Strategy, Observer, etc.)
- Configuración via variables de entorno, nunca hardcoded

### Seguridad (siempre):
- Sanitización de inputs del usuario
- Queries parametrizadas (nunca concatenar SQL)
- Validación de tipos y rangos
- Sin secrets en código, usar env vars
- CORS, CSP, rate limiting cuando aplique

### Formato de entrega:
1. **Resumen técnico** (2-3 líneas: qué hace, stack, decisiones clave)
2. **Código completo** con bloques ```lang bien delimitados
3. **Instrucciones de ejecución** (instalar deps, configurar, correr)
4. **Tests** cuando la tarea lo amerite
5. **Mejoras sugeridas** (2-3 ideas concretas para evolucionar)

### Stack preferido (usa estos por defecto salvo que el usuario pida otro):
- **Frontend**: React 19 + TypeScript + Tailwind CSS 4
- **Backend**: FastAPI (Python) o Express/Hono (Node.js)
- **BD**: PostgreSQL + Prisma/SQLAlchemy
- **Deploy**: Docker + docker-compose
- **Tests**: pytest (Python), Vitest (JS/TS)

### Temperatura mental:
- Código: preciso, determinístico, sin creatividad innecesaria
- Arquitectura: creativo pero pragmático
- Debugging: metódico, sistemático, hipótesis → verificación
"""

# ═══════════════════════════════════════════════════════════════════════
#  TEMPLATES POR TIPO DE TAREA
# ═══════════════════════════════════════════════════════════════════════
TASK_TEMPLATES = {
    "create": {
        "system_extra": (
            "MODO CREACIÓN: Genera el proyecto/componente COMPLETO desde cero. "
            "Incluye: estructura de archivos, dependencias, código, configuración y README. "
            "Todo debe funcionar al copiar y pegar."
        ),
        "temp": 0.4,
        "max_tokens": 4096,
    },
    "debug": {
        "system_extra": (
            "MODO DEBUG: Sigue este protocolo exacto:\n"
            "1. REPRODUCE: Identifica exactamente qué falla y cuándo\n"
            "2. DIAGNÓSTICO: Analiza la causa raíz (no el síntoma)\n"
            "3. HIPÓTESIS: Lista las posibles causas ordenadas por probabilidad\n"
            "4. FIX: Código corregido completo con explicación del cambio\n"
            "5. PREVENCIÓN: Cómo evitar este bug en el futuro"
        ),
        "temp": 0.2,
        "max_tokens": 3000,
    },
    "refactor": {
        "system_extra": (
            "MODO REFACTOR: Muestra ANTES → DESPUÉS con diff claro. "
            "Aplica: SOLID, DRY, Clean Code, patrones apropiados. "
            "Explica CADA cambio y por qué mejora el código. "
            "No cambies funcionalidad — solo estructura y calidad."
        ),
        "temp": 0.3,
        "max_tokens": 3500,
    },
    "test": {
        "system_extra": (
            "MODO TESTING: Genera tests exhaustivos:\n"
            "- Happy path (flujo normal)\n"
            "- Edge cases (límites, vacíos, nulos)\n"
            "- Error cases (inputs inválidos, errores de red)\n"
            "- Mocks para dependencias externas\n"
            "Framework: pytest (Python), Vitest/Jest (JS/TS)"
        ),
        "temp": 0.2,
        "max_tokens": 3500,
    },
    "explain": {
        "system_extra": (
            "MODO EXPLICACIÓN: Explica el código línea por línea como un senior "
            "explicándole a un junior talentoso. Usa analogías cuando ayuden. "
            "Incluye: qué hace cada parte, POR QUÉ se hizo así, y qué alternativas existen."
        ),
        "temp": 0.5,
        "max_tokens": 2500,
    },
    "optimize": {
        "system_extra": (
            "MODO OPTIMIZACIÓN: Analiza rendimiento y propone mejoras:\n"
            "- Complejidad algorítmica (Big O actual vs optimizada)\n"
            "- Uso de memoria\n"
            "- Queries a BD (N+1, índices faltantes)\n"
            "- Caching donde aplique\n"
            "Muestra benchmarks estimados antes/después."
        ),
        "temp": 0.3,
        "max_tokens": 3000,
    },
    "review": {
        "system_extra": (
            "MODO CODE REVIEW: Revisa como un senior en un PR de producción:\n"
            "✅ Correctitud: ¿Hace lo que debe? ¿Edge cases cubiertos?\n"
            "✅ Seguridad: ¿SQL injection? ¿XSS? ¿Secrets expuestos?\n"
            "✅ Performance: ¿Complejidad aceptable? ¿Queries optimizadas?\n"
            "✅ Mantenibilidad: ¿Nombres claros? ¿Funciones cortas? ¿DRY?\n"
            "✅ Tests: ¿Suficientes? ¿Cubren edge cases?\n"
            "Formato: tabla con severidad (🔴🟡🟢), hallazgo y fix sugerido."
        ),
        "temp": 0.3,
        "max_tokens": 3000,
    },
    "general": {
        "system_extra": "",
        "temp": 0.4,
        "max_tokens": 4096,
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  DETECTOR DE TIPO DE TAREA
# ═══════════════════════════════════════════════════════════════════════
def detect_coding_task(msg: str) -> str:
    """Detecta el tipo de tarea de coding."""
    low = msg.lower()

    if any(k in low for k in ["debug", "error", "falla", "no funciona", "bug",
                                "traceback", "exception", "rompe", "crash"]):
        return "debug"

    if any(k in low for k in ["refactor", "refactoriza", "limpia", "mejora el código",
                                "clean code", "reorganiza"]):
        return "refactor"

    if any(k in low for k in ["test", "prueba", "testing", "unitario", "pytest",
                                "jest", "vitest", "spec"]):
        return "test"

    if any(k in low for k in ["explica", "cómo funciona", "qué hace", "explain",
                                "entiend", "line by line"]):
        return "explain"

    if any(k in low for k in ["optimiz", "rendimiento", "performance", "lento",
                                "rápido", "benchmark", "complejidad"]):
        return "optimize"

    if any(k in low for k in ["review", "revisa", "analiza este código", "code review",
                                "audita", "evalúa este"]):
        return "review"

    if any(k in low for k in ["crea", "genera", "haz", "build", "construye", "implementa",
                                "desarrolla", "programa", "escribe", "hacer"]):
        return "create"

    return "general"


# ═══════════════════════════════════════════════════════════════════════
#  DETECCIÓN DE LENGUAJE
# ═══════════════════════════════════════════════════════════════════════
LANG_HINTS = {
    "python":     ["python", "py", "django", "flask", "fastapi", "pandas", "numpy", "pip", "pytest"],
    "javascript": ["javascript", "js", "node", "express", "react", "vue", "angular", "npm", "yarn"],
    "typescript": ["typescript", "ts", "tsx", "nextjs", "next.js", "nest", "deno", "bun"],
    "html_css":   ["html", "css", "tailwind", "bootstrap", "sass", "scss", "landing", "página web"],
    "sql":        ["sql", "query", "select", "insert", "postgres", "mysql", "sqlite", "prisma"],
    "rust":       ["rust", "cargo", "tokio", "actix", "wasm"],
    "go":         ["golang", " go ", "gin", "fiber", "goroutine"],
    "java":       ["java", "spring", "maven", "gradle", "jvm", "kotlin"],
    "csharp":     ["c#", "csharp", "dotnet", ".net", "asp.net", "blazor"],
    "php":        ["php", "laravel", "symfony", "composer"],
    "bash":       ["bash", "shell", "terminal", "script sh", "linux", "chmod"],
}

def detect_language(msg: str) -> str:
    low = msg.lower()
    scores = {}
    for lang, keywords in LANG_HINTS.items():
        scores[lang] = sum(1 for k in keywords if k in low)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "python"


# ═══════════════════════════════════════════════════════════════════════
#  PIPELINE PRINCIPAL: CODING CON AUTO-FIX
# ═══════════════════════════════════════════════════════════════════════
def elite_code_response(
    msg: str,
    llm_call: Callable,
    fast_llm: Optional[Callable] = None,
    base_system: str = "",
    memory: str = "",
    project_context: str = "",
    max_fix_attempts: int = 2,
) -> Dict[str, Any]:
    """
    Pipeline de élite: detecta tarea → genera con prompt especializado →
    auto-verifica → auto-corrige si hay problemas.
    """
    t0 = time.time()
    trace = []

    # 1) Detectar tipo de tarea y lenguaje
    task_type = detect_coding_task(msg)
    lang = detect_language(msg)
    template = TASK_TEMPLATES.get(task_type, TASK_TEMPLATES["general"])
    trace.append(f"[DETECT] task={task_type} lang={lang}")

    # 2) Construir system prompt de élite
    system = ELITE_CODING_PROMPT
    if base_system:
        system = base_system + "\n\n" + ELITE_CODING_PROMPT
    if template["system_extra"]:
        system += "\n\n" + template["system_extra"]
    if project_context:
        system += f"\n\nCONTEXTO DEL PROYECTO DEL USUARIO:\n{project_context[:3000]}"
    if memory:
        system += f"\n\n{memory[:800]}"

    # 3) Generar respuesta principal
    response = llm_call(
        [
            {"role": "system", "content": system[:8000]},
            {"role": "user", "content": msg},
        ],
        template["temp"],
    )
    trace.append(f"[GEN] {len(response)} chars")

    # 4) Auto-verificación para código (solo si hay código en la respuesta)
    has_code = "```" in response and len(response) > 300
    if has_code and fast_llm and task_type in ("create", "debug", "refactor", "general"):
        try:
            check = fast_llm(
                f"Revisa este código. Si tiene errores OBVIOS (syntax, imports faltantes, "
                f"variables no definidas, lógica rota), responde SOLO el error en 1 línea. "
                f"Si está correcto, responde exactamente: OK\n\n"
                f"Código:\n{response[:3000]}"
            )
            trace.append(f"[CHECK] {check[:60]}")

            if check and check.strip().upper() != "OK" and len(check) > 10:
                # Auto-fix
                for attempt in range(max_fix_attempts):
                    fix_response = llm_call(
                        [
                            {"role": "system", "content": system[:6000]},
                            {"role": "user", "content": (
                                f"Tu respuesta anterior tenía este problema:\n{check}\n\n"
                                f"Respuesta original:\n{response[:3000]}\n\n"
                                f"Genera la versión CORREGIDA completa. Pregunta original: {msg[:500]}"
                            )},
                        ],
                        0.2,
                    )
                    if fix_response and len(fix_response) > 100:
                        response = fix_response
                        trace.append(f"[FIX-{attempt+1}] {len(fix_response)} chars")
                        break
        except Exception as e:
            trace.append(f"[CHECK-ERR] {e}")

    elapsed = int((time.time() - t0) * 1000)

    return {
        "response": response,
        "task_type": task_type,
        "language": lang,
        "template": task_type,
        "trace": trace,
        "elapsed_ms": elapsed,
        "engine": "DeepNova Code Elite v1.0",
    }


# ═══════════════════════════════════════════════════════════════════════
#  CODE REVIEW STANDALONE
# ═══════════════════════════════════════════════════════════════════════
def code_review(
    code: str,
    llm_call: Callable,
    language: str = "auto",
) -> Dict[str, Any]:
    """Code review profesional de un bloque de código."""
    if language == "auto":
        language = detect_language(code)

    system = (
        "Eres un senior engineer haciendo code review en un PR de producción.\n"
        "Analiza el código y genera un reporte con:\n\n"
        "## Resumen (1-2 líneas)\n"
        "## Hallazgos\n"
        "| Severidad | Línea | Hallazgo | Fix sugerido |\n"
        "| 🔴 Crítico / 🟡 Medio / 🟢 Menor |\n\n"
        "## Puntuación (1-10)\n"
        "- Correctitud: X/10\n"
        "- Seguridad: X/10\n"
        "- Mantenibilidad: X/10\n"
        "- Performance: X/10\n\n"
        "## Código mejorado\n"
        "Si hay fixes críticos, muestra el código corregido.\n\n"
        "Sé directo, específico y accionable."
    )

    result = llm_call(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Lenguaje: {language}\n\nCódigo a revisar:\n```{language}\n{code}\n```"},
        ],
        0.3,
    )

    return {
        "review": result,
        "language": language,
        "lines": code.count("\n") + 1,
        "engine": "DeepNova Code Review v1.0",
    }


# ═══════════════════════════════════════════════════════════════════════
#  GENERADOR DE TESTS
# ═══════════════════════════════════════════════════════════════════════
def generate_tests(
    code: str,
    llm_call: Callable,
    language: str = "auto",
    framework: str = "auto",
) -> Dict[str, Any]:
    """Genera tests exhaustivos para un bloque de código."""
    if language == "auto":
        language = detect_language(code)
    if framework == "auto":
        framework = {"python": "pytest", "javascript": "vitest", "typescript": "vitest"}.get(language, "pytest")

    system = (
        f"Genera tests EXHAUSTIVOS usando {framework} para el siguiente código.\n"
        "Incluye:\n"
        "- Tests de happy path (flujo normal)\n"
        "- Tests de edge cases (vacíos, nulos, límites)\n"
        "- Tests de error (inputs inválidos, excepciones)\n"
        "- Mocks para dependencias externas\n"
        "- Descripción clara de cada test\n"
        "Código de tests COMPLETO y ejecutable."
    )

    result = llm_call(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Genera tests para:\n```{language}\n{code}\n```"},
        ],
        0.2,
    )

    return {"tests": result, "language": language, "framework": framework}


# ═══════════════════════════════════════════════════════════════════════
#  CONTEXTO DE PROYECTO
# ═══════════════════════════════════════════════════════════════════════
_project_contexts: Dict[str, str] = {}

def set_project_context(sid: str, context: str) -> None:
    _project_contexts[sid] = context[:10000]

def get_project_context(sid: str) -> str:
    return _project_contexts.get(sid, "")

def clear_project_context(sid: str) -> None:
    _project_contexts.pop(sid, None)
