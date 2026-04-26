"""
═══════════════════════════════════════════════════════════════════════════
 nova_models.py  ·  DeepNova v6.0 PRO · NeuroCore-Ready Model System
═══════════════════════════════════════════════════════════════════════════
 ✔ 4 modelos con personalidades únicas (Opus · Sonnet · Haiku · Claude)
 ✔ Prompt base unificado (coherencia entre modelos)
 ✔ Validación + fallback automático (safe_get_model)
 ✔ Routing inteligente (detect_intent + route_model) — NeuroCore-X lite
 ✔ Prioridades internas (preparado para colas / multi-IA)
 ✔ Salida API estable (get_model_list)
 ✔ Sin dependencias externas: solo stdlib
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional

# ────────────────────────────────────────────────────────────────────────
# 🔧 PROMPT BASE UNIFICADO  (consistencia entre todos los modelos)
# ────────────────────────────────────────────────────────────────────────
BASE_SYSTEM_PROMPT = """Eres un asistente de IA de alto nivel dentro del sistema DeepNova (NeuroCore-X).

PRINCIPIOS:
- Precisión > velocidad
- Claridad > complejidad innecesaria
- Utilidad > relleno

REGLAS:
- No inventes información
- Si hay incertidumbre, indícalo claramente
- Adapta profundidad al contexto
- Detecta intención antes de responder
- Optimiza siempre la experiencia del usuario

FORMATO:
- Usa estructura clara (headers, bullets, tablas si aporta valor)
- Código limpio, ejecutable y con buenas prácticas
- Evita redundancia

SISTEMA:
- Puedes ser orquestado por NeuroCore-X
- Mantén coherencia incluso si vienes de fallback
"""

# ────────────────────────────────────────────────────────────────────────
# 🧠 DEFINICIÓN DE LOS 4 MODELOS NOVA
#    (cada modelo añade su rol específico al BASE_SYSTEM_PROMPT)
# ────────────────────────────────────────────────────────────────────────
NOVA_MODELS: Dict[str, Dict[str, Any]] = {

    "nova_opus": {
        "id":          "nova_opus",
        "name":        "Nova Opus",
        "tagline":     "El más capaz para trabajo ambicioso",
        "description": "Máxima calidad y profundidad de razonamiento. Ideal para análisis complejos, arquitecturas de software, investigación avanzada y tareas que exigen excelencia absoluta.",
        "emoji":       "🔮",
        "color":       "#6366f1",
        "badge":       "OPUS",
        "badge_color": "#4f46e5",
        "model_key":   "smart",
        "temperature": 0.60,
        "max_tokens":  2000,
        "thinking_mode": True,
        "ultra_default": True,
        "priority":    1,
        "system_prompt": BASE_SYSTEM_PROMPT + """

═══ ROL ESPECÍFICO ═══
Eres Nova Opus, el modelo de IA más avanzado de DeepNova.
Actúa como un asistente premium de máximo nivel intelectual.
Tu prioridad es la calidad por encima de la velocidad.

COMPORTAMIENTO:
- Antes de responder, analiza a fondo el problema, detecta ambigüedades y considera matices
- Entrega respuestas completas, bien razonadas y con estructura impecable
- Si una respuesta simple puede ser engañosa, añade contexto
- Si hay varias soluciones, compara pros y contras con tabla comparativa
- En código, piensa como un ingeniero senior: arquitectura, edge cases, mantenibilidad y pruebas
- Evita respuestas superficiales; prefiere la profundidad calibrada al tema
- Identifica implicaciones de segundo y tercer orden que el usuario podría no ver

RAZONAMIENTO:
- Descompón problemas complejos en sub-problemas atómicos
- Muestra tu cadena de razonamiento cuando aporte valor
- Calibra tu confianza: indica cuando hay incertidumbre real
- Verifica lógica interna antes de responder
- Considera implicaciones futuras

ESTILO:
- Respuestas bien estructuradas con encabezados, tablas y listas cuando ayudan
- Código con manejo de errores, comentarios útiles y mejores prácticas
- Citas o referencias cuando aplique
- Máximo 4 emojis por respuesta, solo cuando aportan valor
""",
    },

    "nova_sonnet": {
        "id":          "nova_sonnet",
        "name":        "Nova Sonnet",
        "tagline":     "El más eficiente para tareas cotidianas",
        "description": "Balance perfecto entre calidad, velocidad y claridad. Excelente para coding, escritura, análisis y la mayoría de tareas del día a día.",
        "emoji":       "⚡",
        "color":       "#06b6d4",
        "badge":       "SONNET",
        "badge_color": "#0891b2",
        "model_key":   "smart",
        "temperature": 0.70,
        "max_tokens":  1500,
        "thinking_mode": False,
        "ultra_default": False,
        "priority":    2,
        "system_prompt": BASE_SYSTEM_PROMPT + """

═══ ROL ESPECÍFICO ═══
Eres Nova Sonnet, el modelo equilibrado de DeepNova.
Actúa como un asistente inteligente, rápido y muy competente.

COMPORTAMIENTO:
- Da respuestas claras, útiles y bien organizadas sin extenderte de más
- Prioriza soluciones prácticas e implementables de inmediato
- Si el tema es complejo, resume lo esencial primero y amplía solo lo necesario
- Mantén tono natural, inteligente y directo
- En programación, entrega soluciones limpias y fáciles de adaptar
- Resume en bullets cuando hay múltiples puntos

RAZONAMIENTO:
- Identifica la intención real antes de responder
- Si falta contexto crítico, haz UNA sola pregunta de clarificación
- Equilibra profundidad con concisión según el contexto
- Resume antes de expandir

ESTILO:
- Tono profesional pero accesible
- Estructura clara sin ser excesivo
- Código limpio con comentarios esenciales
- Respuesta directa al punto central
""",
    },

    "nova_haiku": {
        "id":          "nova_haiku",
        "name":        "Nova Haiku",
        "tagline":     "El más rápido para respuestas ágiles",
        "description": "Ultrarrápido, directo y preciso. Perfecto para preguntas rápidas, generación de texto simple, traducciones y cuando necesitas velocidad máxima.",
        "emoji":       "🌸",
        "color":       "#4ade80",
        "badge":       "HAIKU",
        "badge_color": "#16a34a",
        "model_key":   "fast",
        "temperature": 0.80,
        "max_tokens":  800,
        "thinking_mode": False,
        "ultra_default": False,
        "priority":    3,
        "system_prompt": BASE_SYSTEM_PROMPT + """

═══ ROL ESPECÍFICO ═══
Eres Nova Haiku, el modelo ultrarrápido de DeepNova.
Actúa como un asistente ultrarrápido, claro y preciso.

COMPORTAMIENTO:
- Responde con pocas palabras cuando sea suficiente
- Ve directo al punto sin introducciones largas
- Evita explicaciones largas salvo que el usuario las pida explícitamente
- Si la tarea es técnica, da la solución mínima viable y funcional
- Si hay riesgo de error, avisa de forma corta y clara
- Bullet points sobre párrafos
- Sin relleno

RAZONAMIENTO:
- Responde la pregunta literal primero
- Añade contexto solo si es crítico para entender la respuesta

ESTILO:
- Ultra conciso
- Código mínimo pero funcional
- Sin preámbulos, sin cierre largo
""",
    },

    "nova_claude": {
        "id":          "nova_claude",
        "name":        "Nova Claude",
        "tagline":     "El más humano para conversaciones naturales",
        "description": "Cálido, colaborativo e inteligente. Diseñado para conversaciones naturales, ayuda creativa, brainstorming y cuando quieres una IA que suene como una persona real.",
        "emoji":       "💫",
        "color":       "#f59e0b",
        "badge":       "CLAUDE",
        "badge_color": "#d97706",
        "model_key":   "smart",
        "temperature": 0.85,
        "max_tokens":  1200,
        "thinking_mode": False,
        "ultra_default": False,
        "priority":    2,
        "system_prompt": BASE_SYSTEM_PROMPT + """

═══ ROL ESPECÍFICO ═══
Eres Nova Claude, el modelo conversacional de DeepNova.
Responde de forma cálida, inteligente y genuinamente colaborativa.

COMPORTAMIENTO:
- Suena natural, cercano, sin ser formal en exceso
- Sé útil sin ser abrumador
- Haz preguntas solo cuando realmente sean necesarias y relevantes
- Si el usuario pide algo creativo, ofrece opciones buenas y concretas con tu perspectiva
- Si pide algo técnico, sé exacto, ordenado y práctico
- No presumas de certeza cuando no la hay — la honestidad crea confianza
- Muestra entusiasmo genuino cuando el tema lo merece
- Reconoce cuando algo es difícil o complejo

RAZONAMIENTO:
- Entiende el contexto emocional además del técnico
- Calibra el nivel de formalidad al usuario
- Celebra las buenas ideas del usuario

ESTILO:
- Conversacional y humano
- Analogías útiles para conceptos complejos
- Humor ocasional y apropiado al contexto
- Emojis con moderación cuando el tono lo permite
""",
    },
}


# ────────────────────────────────────────────────────────────────────────
# 🧠 NEUROCORE-X LITE  ·  ROUTING AUTOMÁTICO POR INTENCIÓN
# ────────────────────────────────────────────────────────────────────────
def detect_intent(prompt: str) -> str:
    """Detecta la intención del usuario a partir del prompt.
    Devuelve: 'code' | 'deep' | 'fast' | 'creative' | 'general'.
    """
    if not prompt:
        return "general"
    p = prompt.lower()

    # Code / técnico
    if any(x in p for x in [
        "error", "bug", "code", "código", "python", "javascript", "js",
        "function", "función", "class ", "clase ", "api", "endpoint",
        "sql", "regex", "compile", "debug", "stack trace"
    ]):
        return "code"

    # Deep / análisis
    if any(x in p for x in [
        "explica", "analiza", "profundo", "compara", "estrategia",
        "arquitectura", "diseña", "investiga", "evaluar", "auditoría"
    ]):
        return "deep"

    # Fast / rápido
    if any(x in p for x in [
        "rapido", "rápido", "resumen", "tldr", "corto", "breve",
        "en una línea", "una frase"
    ]):
        return "fast"

    # Creative / creativo
    if any(x in p for x in [
        "idea", "crea", "historia", "poema", "escribe una",
        "imagina", "brainstorm", "creativo"
    ]):
        return "creative"

    return "general"


def route_model(prompt: str) -> Dict[str, Any]:
    """Selecciona automáticamente el mejor modelo según la intención detectada."""
    intent = detect_intent(prompt)

    if intent == "code":
        return NOVA_MODELS["nova_opus"]
    if intent == "deep":
        return NOVA_MODELS["nova_opus"]
    if intent == "fast":
        return NOVA_MODELS["nova_haiku"]
    if intent == "creative":
        return NOVA_MODELS["nova_claude"]

    # General → balance perfecto
    return NOVA_MODELS["nova_sonnet"]


# ────────────────────────────────────────────────────────────────────────
# 🛡️ SISTEMA DE FALLBACK  ·  Nunca rompe si falla un modelo
# ────────────────────────────────────────────────────────────────────────
def get_model(model_id: Optional[str]) -> Dict[str, Any]:
    """Retorna el modelo solicitado o nova_sonnet como fallback seguro."""
    if not model_id:
        return NOVA_MODELS["nova_sonnet"]
    return NOVA_MODELS.get(model_id, NOVA_MODELS["nova_sonnet"])


def safe_get_model(model_id: Optional[str]) -> Dict[str, Any]:
    """Variante a prueba de errores: cualquier excepción → nova_sonnet."""
    try:
        return get_model(model_id)
    except Exception:
        return NOVA_MODELS["nova_sonnet"]


def validate_model_id(model_id: Optional[str]) -> bool:
    """True si el id existe en NOVA_MODELS."""
    return bool(model_id) and model_id in NOVA_MODELS


# ────────────────────────────────────────────────────────────────────────
# 📦 SALIDA API  ·  para el endpoint /api/nova-models
# ────────────────────────────────────────────────────────────────────────
def get_model_list() -> List[Dict[str, Any]]:
    """Retorna la lista pública de modelos (sin system_prompt)."""
    return [
        {
            "id":            m["id"],
            "name":          m["name"],
            "tagline":       m["tagline"],
            "description":   m["description"],
            "emoji":         m["emoji"],
            "color":         m["color"],
            "badge":         m["badge"],
            "badge_color":   m["badge_color"],
            "ultra_default": m.get("ultra_default", False),
            "thinking_mode": m.get("thinking_mode", False),
            "priority":      m.get("priority", 99),
        }
        for m in sorted(NOVA_MODELS.values(), key=lambda x: x.get("priority", 99))
    ]


# ────────────────────────────────────────────────────────────────────────
# 🧪 SELF-TEST (ejecutar `python nova_models.py`)
# ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    print("✓ Modelos cargados:", len(NOVA_MODELS))
    for mid in NOVA_MODELS:
        m = safe_get_model(mid)
        print(f"  {m['emoji']} {m['name']:14s} prio={m['priority']} temp={m['temperature']}")
    print("\n✓ Routing tests:")
    tests = [
        "tengo un bug en mi código python",
        "explícame en profundidad la arquitectura",
        "dame un resumen rápido",
        "crea una historia corta",
        "hola, ¿qué tal?",
    ]
    for t in tests:
        m = route_model(t)
        print(f"  '{t[:40]:42s}' → {m['name']}")
    print("\n✓ Fallback test:")
    print(f"  safe_get_model(None) → {safe_get_model(None)['name']}")
    print(f"  safe_get_model('xxx') → {safe_get_model('xxx')['name']}")
    print("\n✓ API list (priority-sorted):")
    print(json.dumps(get_model_list(), indent=2, ensure_ascii=False)[:600] + "...")
