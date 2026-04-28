"""
═══════════════════════════════════════════════════════════════════════════
 domain_knowledge.py · DeepNova v7.0 · Conocimiento Especializado por Dominio
═══════════════════════════════════════════════════════════════════════════
 Provee contexto experto inyectable al system prompt según el dominio
 detectado de la consulta del usuario.

 Dominios incluidos:
   • software       (programación, arquitectura, devops)
   • finance        (mercados, contabilidad, análisis financiero)
   • medicine       (clínica, fármacos, diagnóstico)
   • legal          (contratos, normativa, compliance)
   • science        (física, química, biología)
   • education      (pedagogía, didáctica)
   • marketing      (growth, copy, SEO, ads)
   • data_science   (ML, estadística, análisis)

 Diseño:
   - Detección rápida y determinística (sin LLM)
   - Contexto compacto y de alta calidad (mejora reasoning sin saturar tokens)
   - 100% aditivo · cero deps externas

 Áreas cubiertas (del documento de mejoras):
   ✓ 3.2 Integración de conocimiento de dominio
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import re
from typing import Dict, List, Tuple

# ──────────────────────────────────────────────────────────────────────
#  Diccionario de palabras clave por dominio (case-insensitive)
# ──────────────────────────────────────────────────────────────────────
DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "software": [
        "código", "programa", "función", "clase", "api", "endpoint",
        "python", "javascript", "typescript", "react", "next.js", "node",
        "docker", "kubernetes", "ci/cd", "devops", "git", "github",
        "framework", "backend", "frontend", "fullstack", "rest", "graphql",
        "microservicio", "arquitectura", "patrón de diseño", "refactor",
        "test", "pytest", "unitario", "deploy", "producción",
    ],
    "finance": [
        "acción", "bolsa", "stock", "ticker", "dividendo", "ipo", "etf",
        "balance", "estado de resultados", "flujo de caja", "ebitda",
        "ratio", "p/e", "valuación", "valoración", "dcf", "wacc",
        "inversión", "portafolio", "hedge", "futuro", "opción",
        "interés", "tasa", "inflación", "fed", "bce", "bonos", "treasury",
        "criptomoneda", "bitcoin", "ethereum", "blockchain",
    ],
    "medicine": [
        "síntoma", "diagnóstico", "tratamiento", "fármaco", "medicamento",
        "dosis", "posología", "efecto adverso", "contraindicación",
        "patología", "enfermedad", "infección", "virus", "bacteria",
        "presión arterial", "glucosa", "colesterol", "hemoglobina",
        "rx", "tac", "resonancia", "ecocardio", "biopsia",
        "paciente", "clínica", "consulta médica",
    ],
    "legal": [
        "contrato", "cláusula", "ley", "artículo", "código civil",
        "código penal", "demanda", "juicio", "sentencia", "tribunal",
        "abogado", "notario", "compliance", "rgpd", "gdpr",
        "propiedad intelectual", "patente", "marca registrada",
        "derecho mercantil", "obligación", "responsabilidad civil",
    ],
    "science": [
        "experimento", "hipótesis", "teoría", "ecuación", "fórmula",
        "molécula", "átomo", "electrón", "neutrón", "protón",
        "célula", "adn", "arn", "proteína", "enzima",
        "newton", "einstein", "mecánica cuántica", "termodinámica",
        "química orgánica", "tabla periódica", "reacción química",
    ],
    "education": [
        "alumno", "estudiante", "profesor", "docente", "currículo",
        "didáctica", "pedagogía", "evaluación", "examen", "rúbrica",
        "competencia", "objetivo de aprendizaje", "lesson plan",
        "metodología activa", "abp", "flipped classroom",
    ],
    "marketing": [
        "marketing", "marca", "branding", "campaña", "anuncio", "ads",
        "facebook ads", "google ads", "seo", "sem", "ctr", "cpc",
        "conversión", "funnel", "lead", "growth hack", "copywriting",
        "posicionamiento", "buyer persona", "b2b", "b2c",
    ],
    "data_science": [
        "dataset", "modelo", "entrenar", "feature", "label",
        "regresión", "clasificación", "clustering", "knn", "svm",
        "red neuronal", "deep learning", "machine learning",
        "pandas", "numpy", "scikit", "tensorflow", "pytorch",
        "overfitting", "cross-validation", "métrica", "auc", "roc",
        "f1", "precision", "recall",
    ],
}

# ──────────────────────────────────────────────────────────────────────
#  Contexto experto por dominio (system-prompt augmentation)
# ──────────────────────────────────────────────────────────────────────
DOMAIN_CONTEXT: Dict[str, str] = {
    "software": """[DOMINIO: SOFTWARE / INGENIERÍA DE SOFTWARE]
Aplica principios SOLID, DRY, KISS, YAGNI.
Considera: edge cases, validación de inputs, manejo de errores, logging,
seguridad (OWASP top-10), tests automatizados, observabilidad y escalabilidad.
Sugiere stack moderno: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0,
Next.js 15, TypeScript estricto, Docker multi-stage, CI/CD con GitHub Actions.
Cuando entregues código: completo, ejecutable, con imports, comentarios útiles
y un ejemplo mínimo de uso. Evita anti-patrones (god-class, spaghetti, etc.).""",

    "finance": """[DOMINIO: FINANZAS]
Razona con rigor: usa ratios (P/E, P/B, ROE, deuda/EBITDA), múltiplos
comparables, DCF y análisis de sensibilidad cuando aplique.
Distingue claramente entre análisis fundamental, técnico y cuantitativo.
Recuerda: no eres asesor financiero registrado — añade un disclaimer breve
cuando se pidan recomendaciones de inversión personales.
Datos: cifras concretas y trazables, periodo claro, moneda explícita.""",

    "medicine": """[DOMINIO: MEDICINA / SALUD]
Razona como un clínico: anamnesis → diagnóstico diferencial → exámenes
complementarios → tratamiento → seguimiento. Cita guías reconocidas
(NICE, AHA, ESC, MSF) cuando sea relevante.
⚠️ DISCLAIMER OBLIGATORIO: la información es educativa y NO sustituye
consulta con un profesional sanitario habilitado. No diagnosticas ni
prescribes. Para emergencias, indica acudir a urgencias.""",

    "legal": """[DOMINIO: LEGAL / DERECHO]
Razona estructurando: hechos → norma aplicable → análisis → conclusión.
Cita la normativa con artículo y jurisdicción cuando sea posible.
⚠️ DISCLAIMER OBLIGATORIO: la información es orientativa y NO constituye
asesoramiento legal. Para casos concretos, consultar a un abogado
colegiado en la jurisdicción correspondiente.""",

    "science": """[DOMINIO: CIENCIA]
Razona con método científico: hipótesis verificable, evidencia empírica,
unidades del SI, magnitudes con incertidumbre cuando proceda.
Distingue claramente entre hecho establecido, consenso científico,
hipótesis y especulación. Usa notación matemática limpia (LaTeX si ayuda).""",

    "education": """[DOMINIO: EDUCACIÓN]
Adapta nivel cognitivo (Bloom) y estilo al destinatario (niño, adolescente,
universitario, adulto). Estructura: objetivo → activación previa → contenido
→ ejemplo → práctica guiada → evaluación. Prefiere metodologías activas.""",

    "marketing": """[DOMINIO: MARKETING]
Razona en términos de buyer persona, customer journey, funnel
(awareness → consideration → decision → loyalty) y métricas claras
(CAC, LTV, ROAS, CTR, CR). Copy directo, orientado a beneficios,
con CTAs claros. Ética: no recomiendas tácticas engañosas (dark patterns).""",

    "data_science": """[DOMINIO: CIENCIA DE DATOS / ML]
Sigue el flujo CRISP-DM: comprensión del problema → datos → preparación
→ modelado → evaluación → despliegue. Evita data leakage y overfitting.
Reporta siempre métrica relevante (no solo accuracy en clases desbalanceadas).
Stack: pandas, scikit-learn, PyTorch/TensorFlow, MLflow para tracking.""",
}


# ──────────────────────────────────────────────────────────────────────
#  Detección de dominios
# ──────────────────────────────────────────────────────────────────────
_WORD_RE = re.compile(r"[\wáéíóúñü]+", re.IGNORECASE)


def detect_domains(text: str, max_domains: int = 2) -> List[Tuple[str, int]]:
    """Devuelve lista [(dominio, score), ...] ordenada por score descendente."""
    if not text:
        return []
    low = text.lower()
    scores: Dict[str, int] = {}
    for domain, kws in DOMAIN_KEYWORDS.items():
        s = 0
        for kw in kws:
            if " " in kw:
                if kw in low:
                    s += 2  # frase completa pesa más
            else:
                # palabra suelta: match por palabra completa
                if re.search(rf"\b{re.escape(kw)}\b", low):
                    s += 1
        if s > 0:
            scores[domain] = s
    if not scores:
        return []
    return sorted(scores.items(), key=lambda kv: -kv[1])[:max_domains]


def get_domain_context(text: str, max_domains: int = 2) -> str:
    """Devuelve el bloque de contexto experto a inyectar al system prompt."""
    detected = detect_domains(text, max_domains=max_domains)
    if not detected:
        return ""
    blocks = []
    for domain, _score in detected:
        ctx = DOMAIN_CONTEXT.get(domain)
        if ctx:
            blocks.append(ctx)
    return "\n\n".join(blocks)


def explain_detection(text: str) -> Dict[str, any]:
    """Útil para debugging: muestra qué keywords matchearon."""
    low = (text or "").lower()
    out: Dict[str, any] = {}
    for domain, kws in DOMAIN_KEYWORDS.items():
        matched = [kw for kw in kws if (kw in low if " " in kw else re.search(rf"\b{re.escape(kw)}\b", low))]
        if matched:
            out[domain] = matched
    return out


def list_domains() -> List[str]:
    return sorted(DOMAIN_KEYWORDS.keys())
