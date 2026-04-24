from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import groq, os, re, time, json, requests, base64
from collections import defaultdict, Counter
from datetime import datetime
from urllib.parse import urlparse
import io
import subprocess
import tempfile

# ══════════════════════════════════════════
# 🆕 DEEPNOVA v2 HÍBRIDO — Módulos avanzados
# (integración aditiva: no modifica la lógica original)
# ══════════════════════════════════════════
try:
    import reasoning  as _reasoning
    import database   as _db
    import embeddings as _emb
    import favicon    as _favicon
    _DN2_OK = True
except Exception as _e:
    print(f"[deepnova-v2] módulos avanzados no disponibles: {_e}")
    _reasoning = _db = _emb = _favicon = None
    _DN2_OK = False

app = Flask(__name__)
CORS(app)

# Registrar favicons M7 (servicio de /favicon.svg, /icon-*.png, /site.webmanifest)
if _favicon is not None:
    try:
        _favicon.register(app)
    except Exception as _e:
        print(f"[deepnova-v2] favicon register error: {_e}")

# Inicializar DB M2 (lazy, seguro de llamar varias veces)
if _db is not None:
    try:
        _db.init_db()
    except Exception as _e:
        print(f"[deepnova-v2] db init error: {_e}")

# ── CLIENTE ───────────────────────────────
_client = None
def get_groq():
    global _client
    if _client is None:
        _client = groq.Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client

# ── MODELOS ACTIVOS 2025 ──────────────────
MODELS = {
    "fast":    "llama-3.1-8b-instant",
    "smart":   "llama-3.3-70b-versatile",
    "reason":  "qwen/qwen3-32b",
    "creative":"groq/compound",
    "vision":  "meta-llama/llama-4-scout-17b-16e-instruct",
}

# ══════════════════════════════════════════
# PERSONALIDAD DEEPNOVA
# ══════════════════════════════════════════
SYSTEM_BASE = """Eres DeepNova, el Agente Autónomo más potente del mundo.

IDENTIDAD:
- Nombre: DeepNova
- Clase: God-Tier Super Agent
- Inspirado en DeepAgent de Abacus.AI (2026)
- No solo conversas: piensas, planeas y ejecutas

CAPACIDADES CORE:
1. Agente autónomo generalista — completas metas complejas paso a paso
2. Vibe Coding — el usuario describe y tú generas código listo para producción
3. Multi-agente (Swarm) — orquestas agentes especializados en paralelo
4. Investigación profunda y razonamiento avanzado en tiempo real
5. Automatización de workflows y tareas programadas
6. RAG empresarial — conocimiento personalizado del usuario
7. Integración con herramientas externas (Gmail, GitHub, Slack, etc.)
8. Testing/QA automático de software
9. Memoria a largo plazo y mejora continua

MODO DE TRABAJO UNIFICADO:
Cuando recibes una tarea, automáticamente:
- PLANIFICAS los pasos necesarios
- SELECCIONAS las herramientas correctas
- EJECUTAS cada paso mostrando tu razonamiento
- VERIFICAS el resultado
- SUGIERES mejoras proactivamente

MODOS ESPECIALIZADOS (todos activos simultáneamente):
💬 Chat       → conversación inteligente y contextual
💻 Código     → código limpio, comentado, producción-ready
🌐 Web        → diseños premium con animaciones elegantes
📝 Contenido  → textos optimizados y creativos
🔍 Análisis   → datos, patrones, insights accionables
🧠 Razonamiento → lógica profunda, pros/contras, decisiones
🥊 Debate     → múltiples perspectivas con veredicto
🤖 Agente     → ejecución autónoma multi-paso
🌍 Traducción → 100+ idiomas con contexto cultural
🎨 Diseño     → UI/UX premium, dark mode, animaciones

ESTILO:
- Respuestas organizadas: párrafos cortos, encabezados, listas
- Máximo 3 emojis por respuesta
- Código siempre funcional y explicado
- Proactivo: siempre sugiere mejoras
- Diseño web: prioriza animaciones elegantes y dark mode premium

PERSONALIDAD:
Útil, creativa, profesional, obsesionada con la excelencia.
Tu objetivo ser la experiencia de IA más excepcional posible.

REGLAS DE EJECUCIÓN OBLIGATORIAS:

1. AUTONOMÍA REAL
   - Nunca digas solo "voy a hacer un plan", ejecuta directamente
   - Código siempre completo y funcional, nunca cortado
   - Entrega proyectos reales listos para usar

2. MULTI-AGENTE SWARM (actívalo en tareas complejas)
   Coordina estos agentes especializados:
   - Investigador  → datos actuales 2025-2026, mercado, tendencias
   - Programador   → código completo con manejo de errores
   - Diseñador     → UI/UX premium, animaciones, dark mode
   - Tester        → casos de prueba y validación
   - Deployer      → instrucciones de deploy a producción

3. CÓDIGO DE PRODUCCIÓN
   Stack moderno preferido:
   - Frontend: Next.js 15, Tailwind CSS, TypeScript
   - Backend:  FastAPI, Python, SQLAlchemy, Pydantic
   - BD:       Supabase, PostgreSQL, Redis
   - Deploy:   Docker, Railway, Vercel
   Incluye siempre: autenticación, manejo de errores,
   variables de entorno e instrucciones de instalación

4. INVESTIGACIÓN ACTUALIZADA
   - Usa datos concretos de 2025-2026
   - Nunca des información genérica antigua
   - Simula research profundo con números y hechos específicos

5. PROACTIVIDAD OBLIGATORIA
   Al final de cada tarea importante agrega:
   ## Mejoras y Próximos Pasos
   Con 3-5 ideas concretas y específicas al proyecto

6. ESTILO PREMIUM
   - Encabezados ## y ### para organizar
   - Tablas comparativas cuando sea útil
   - Sin paredes de texto, sin relleno
   - Ve al grano, entrega valor real inmediato
   - No expliques lo obvio"""

# ══════════════════════════════════════════
# MEMORIA PERMANENTE
# ══════════════════════════════════════════
MEMORY_FILE  = "deepnova_memory.json"
HISTORY_FILE = "deepnova_history.json"

def load_json(f):
    try:
        if os.path.exists(f):
            with open(f, "r", encoding="utf-8") as fp:
                return json.load(fp)
    except:
        pass
    return {}

def save_json(f, data):
    try:
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except:
        pass

permanent_memory     = load_json(MEMORY_FILE)
conversation_history = load_json(HISTORY_FILE)

def save_memory(sid, key, value):
    if sid not in permanent_memory:
        permanent_memory[sid] = {}
    permanent_memory[sid][key] = value
    permanent_memory[sid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json(MEMORY_FILE, permanent_memory)

def get_memory(sid):
    return permanent_memory.get(sid, {})

def get_memory_prompt(sid):
    mem = get_memory(sid)
    if not mem:
        return ""
    lines = ["\n\nMEMORIA DEL USUARIO:"]
    for k, v in mem.items():
        if k != "last_seen":
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)

def extract_memory(sid, msg):
    msg_lower = msg.lower()
    for t in ["me llamo", "mi nombre es"]:
        if t in msg_lower:
            words = msg.split()
            for i, w in enumerate(words):
                if w.lower() in ["llamo", "es"] and i+1 < len(words):
                    save_memory(sid, "nombre", words[i+1].strip(".,!?"))
    for t in ["trabajo como", "soy desarrollador", "soy diseñador",
               "soy estudiante", "mi profesión"]:
        if t in msg_lower:
            save_memory(sid, "profesion", msg[:120])
    if any(t in msg_lower for t in ["me gusta", "prefiero", "me interesa"]):
        save_memory(sid, "interes", msg[:120])

def save_history(sid, msg, response, model, modes):
    if sid not in conversation_history:
        conversation_history[sid] = []
    conversation_history[sid].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": msg,
        "nova": response,
        "model": model,
        "modes_used": modes
    })
    if len(conversation_history[sid]) > 500:
        conversation_history[sid] = conversation_history[sid][-500:]
    save_json(HISTORY_FILE, conversation_history)

# ══════════════════════════════════════════
# MEMORIA VECTORIAL SIMPLE
# ══════════════════════════════════════════
KNOWLEDGE_FILE = "deepnova_knowledge.json"

def load_knowledge():
    return load_json(KNOWLEDGE_FILE) or {"entries": []}

def save_knowledge(data):
    save_json(KNOWLEDGE_FILE, data)

knowledge_base = load_knowledge()

def extract_keywords(text, max_kw=10):
    """Extrae palabras clave de un texto"""
    stopwords = {
        "el","la","los","las","un","una","de","del","en","con",
        "por","para","que","es","son","al","se","no","lo","su",
        "más","como","pero","este","esta","hay","fue","ser",
        "tiene","hacer","puede","muy","ya","también","todo",
        "the","is","are","was","were","have","has","do","does",
        "a","an","and","or","but","in","on","at","to","for","of"
    }
    words = re.findall(r'\b[a-záéíóúñü]{3,}\b', text.lower())
    word_freq = Counter(w for w in words if w not in stopwords)
    return [w for w, _ in word_freq.most_common(max_kw)]

def add_to_knowledge(sid, category, content, source="user"):
    """Añade información a la base de conocimiento"""
    if not content or len(content) < 10:
        return
    entry = {
        "sid":       sid,
        "category":  category,
        "content":   content[:500],
        "source":    source,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "keywords":  extract_keywords(content)
    }
    knowledge_base["entries"].append(entry)
    if len(knowledge_base["entries"]) > 1000:
        knowledge_base["entries"] = knowledge_base["entries"][-1000:]
    save_knowledge(knowledge_base)

def search_knowledge(query, sid=None, max_results=5):
    """Busca en la base de conocimiento por similitud de keywords"""
    query_kw = set(extract_keywords(query))
    if not query_kw:
        return []
    results = []
    for entry in knowledge_base.get("entries", []):
        if sid and entry.get("sid") != sid and entry.get("sid") != "global":
            continue
        entry_kw = set(entry.get("keywords", []))
        if not entry_kw:
            continue
        common = query_kw.intersection(entry_kw)
        if common:
            score = len(common) / max(len(query_kw), len(entry_kw))
            results.append({
                "content":  entry["content"],
                "category": entry.get("category", "general"),
                "score":    round(score, 3),
                "source":   entry.get("source", "unknown"),
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]

def get_knowledge_context(query, sid):
    """Genera contexto desde la base de conocimiento"""
    results = search_knowledge(query, sid)
    if not results:
        return ""
    lines = ["\n\nCONOCIMIENTO RELEVANTE:"]
    for r in results:
        lines.append(f"- [{r['category']}] {r['content'][:200]}")
    return "\n".join(lines)

def auto_learn(sid, msg, response):
    """Aprende automáticamente de conversaciones"""
    msg_lower = msg.lower()
    if any(t in msg_lower for t in
        ["mi empresa","mi proyecto","mi sitio","mi app",
         "trabajo en","estoy creando","estoy desarrollando"]):
        add_to_knowledge(sid, "proyecto", msg, "user")
    if any(t in msg_lower for t in
        ["prefiero","me gusta usar","siempre uso",
         "mi stack","mi framework","mi lenguaje"]):
        add_to_knowledge(sid, "preferencia", msg, "user")
    if any(t in msg_lower for t in
        ["la api es","el endpoint","la base de datos",
         "el servidor","el dominio"]):
        add_to_knowledge(sid, "técnico", msg, "user")
    if len(response) > 200 and any(t in msg_lower for t in
        ["explica","cómo funciona","qué es","tutorial","guía"]):
        add_to_knowledge(
            "global", "conocimiento",
            f"Q: {msg[:100]} | A: {response[:300]}",
            "deepnova"
        )

# ══════════════════════════════════════════
# RATE LIMIT Y SEGURIDAD
# ══════════════════════════════════════════
rate_counts = defaultdict(list)
convs       = {}
tasks_store = {}

def check_rate(ip, max_r=40, win=60):
    now = time.time()
    rate_counts[ip] = [t for t in rate_counts[ip] if now-t < win]
    if len(rate_counts[ip]) >= max_r:
        return False
    rate_counts[ip].append(now)
    return True

BLOCKED = [r"(?i)(hackear sistema real|exploit real|malware real)"]

def is_safe(text):
    if len(text) > 8000:
        return False, "Mensaje muy largo"
    for p in BLOCKED:
        if re.search(p, text):
            return False, "Contenido no permitido"
    return True, ""

# ══════════════════════════════════════════
# SANDBOX DE EJECUCIÓN DE CÓDIGO PYTHON
# ══════════════════════════════════════════

BLOCKED_CODE_PATTERNS = [
    r"__import__\s*\(",
    r"importlib",
    r"subprocess",
    r"socket\.",
    r"shutil\.",
    r"os\.remove|os\.rmdir|os\.unlink",
    r"open\s*\(",
]

def is_code_safe(code):
    """Verifica que el código sea seguro para ejecutar"""
    for pattern in BLOCKED_CODE_PATTERNS:
        if re.search(pattern, code):
            return False, f"Patrón bloqueado: {pattern}"
    return True, ""

def execute_python(code, timeout=10):
    """
    Ejecuta código Python usando el intérprete actual.
    Más seguro y funciona en cualquier servidor.
    """
    safe, reason = is_code_safe(code)
    if not safe:
        return {
            "output":  "",
            "error":   f"⚠️ Código bloqueado: {reason}",
            "success": False
        }

    import sys
    import io
    import traceback
    import signal
    import math, random, datetime, json, re
    import collections, itertools, functools
    import statistics, decimal, fractions, string

    # Capturar stdout
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

    output  = ""
    error   = ""
    success = False

    try:
        # Namespace limpio y seguro
        safe_globals = {
            "__builtins__": {
                # Funciones built-in básicas
                "print":      print,
                "range":      range,
                "len":        len,
                "int":        int,
                "float":      float,
                "str":        str,
                "list":       list,
                "dict":       dict,
                "set":        set,
                "tuple":      tuple,
                "bool":       bool,
                "type":       type,
                "isinstance": isinstance,
                "issubclass": issubclass,
                "enumerate":  enumerate,
                "zip":        zip,
                "map":        map,
                "filter":     filter,
                "sorted":     sorted,
                "reversed":   reversed,
                "sum":        sum,
                "min":        min,
                "max":        max,
                "abs":        abs,
                "round":      round,
                "pow":        pow,
                "divmod":     divmod,
                "hex":        hex,
                "oct":        oct,
                "bin":        bin,
                "ord":        ord,
                "chr":        chr,
                "repr":       repr,
                "format":     format,
                "any":        any,
                "all":        all,
                "next":       next,
                "iter":       iter,
                "input":      lambda x="": "",
                "hash":       hash,
                "id":         id,
                "dir":        dir,
                "vars":       vars,
                "help":       lambda x=None: "Help no disponible",
                # Excepciones comunes
                "Exception":           Exception,
                "ValueError":          ValueError,
                "TypeError":           TypeError,
                "KeyError":            KeyError,
                "IndexError":          IndexError,
                "AttributeError":      AttributeError,
                "NameError":           NameError,
                "ZeroDivisionError":   ZeroDivisionError,
                "StopIteration":       StopIteration,
                "RuntimeError":        RuntimeError,
                "NotImplementedError": NotImplementedError,
                "OverflowError":       OverflowError,
                "MemoryError":         MemoryError,
                "RecursionError":      RecursionError,
                # Constantes
                "True":       True,
                "False":      False,
                "None":       None,
                # Permitir import de módulos seguros
                "__import__": __import__,
            },
            # Módulos pre-importados disponibles
            "math":        math,
            "random":      random,
            "datetime":    datetime,
            "json":        json,
            "re":          re,
            "collections": collections,
            "itertools":   itertools,
            "functools":   functools,
            "statistics":  statistics,
            "decimal":     decimal,
            "fractions":   fractions,
            "string":      string,
        }

        exec(compile(code, "<deepnova>", "exec"), safe_globals)

        output  = sys.stdout.getvalue()
        success = True

    except Exception as e:
        output  = sys.stdout.getvalue()
        error   = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        success = False

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    if len(output) > 3000:
        output = output[:3000] + "\n... (truncado)"

    return {
        "output":  output.strip(),
        "error":   error.strip(),
        "success": success
    }

def extract_python_code(text):
    """Extrae el primer bloque de código Python de un texto"""
    pattern = r"```(?:python|py)?\n?([\s\S]*?)```"
    matches = re.findall(pattern, text)
    return matches[0].strip() if matches else None

def deepnova_execute(task, sid):
    """
    Ciclo completo: Generar → Ejecutar → Verificar → Autocorregir
    """
    results = []

    try:
        # PASO 1: Generar código
        results.append("**🔧 Generando código Python...**")

        gen_r = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role": "system", "content":
                 "Eres un programador Python experto. "
                 "Genera SOLO código Python funcional y ejecutable. "
                 "Usa print() para mostrar TODOS los resultados. "
                 "NO uses: os, sys, subprocess, requests, open(). "
                 "El código debe ser autocontenido y completo."},
                {"role": "user", "content":
                 f"Escribe código Python para: {task}\n"
                 f"Asegúrate de imprimir los resultados con print()"}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        generated = gen_r.choices[0].message.content
        code = extract_python_code(generated) or generated.strip()

        results.append(f"**📝 Código generado:**\n```python\n{code}\n```")

        # PASO 2: Ejecutar
        results.append("**⚡ Ejecutando en sandbox seguro...**")
        execution = execute_python(code)

        if execution["success"] and execution["output"]:
            results.append(
                f"**✅ Resultado real:**\n```\n{execution['output']}\n```"
            )

            # PASO 3: Analizar resultado
            analysis_r = get_groq().chat.completions.create(
                model=MODELS["fast"],
                messages=[
                    {"role": "system", "content":
                     "Analiza brevemente el resultado en español. "
                     "Explica qué hace el código y qué significa el output. "
                     "Máximo 3 oraciones."},
                    {"role": "user", "content":
                     f"Tarea: {task}\n"
                     f"Código:\n{code}\n"
                     f"Output:\n{execution['output']}"}
                ],
                max_tokens=200,
                temperature=0.5
            )
            results.append(
                f"**💡 Análisis:**\n{analysis_r.choices[0].message.content}"
            )

        else:
            # PASO 4: Autocorrección
            error_info = execution["error"] or execution["output"] or "Sin output"
            results.append(
                f"**⚠️ Error detectado:**\n```\n{error_info}\n```"
            )
            results.append("**🔄 Autocorrigiendo código...**")

            fix_r = get_groq().chat.completions.create(
                model=MODELS["smart"],
                messages=[
                    {"role": "system", "content":
                     "Eres un debugger Python experto. "
                     "Corrige el código. Retorna SOLO el código "
                     "corregido en bloque ```python```."},
                    {"role": "user", "content":
                     f"Tarea: {task}\n"
                     f"Código con error:\n```python\n{code}\n```\n"
                     f"Error: {error_info}\n"
                     f"Corrige el código:"}
                ],
                max_tokens=800,
                temperature=0.2
            )
            fixed_text = fix_r.choices[0].message.content
            fixed_code = extract_python_code(fixed_text) or fixed_text.strip()

            results.append(
                f"**🔧 Código corregido:**\n```python\n{fixed_code}\n```"
            )

            # Re-ejecutar código corregido
            fixed_exec = execute_python(fixed_code)

            if fixed_exec["success"] and fixed_exec["output"]:
                results.append(
                    f"**✅ Resultado tras corrección:**\n```\n{fixed_exec['output']}\n```"
                )
            else:
                results.append(
                    f"**❌ No se pudo ejecutar:**\n```\n{fixed_exec['error'] or 'Sin output'}\n```"
                )

    except Exception as e:
        results.append(f"**❌ Error inesperado:** {str(e)}")

    return "\n\n".join(results)

# ══════════════════════════════════════════
# BÚSQUEDA WEB
# ══════════════════════════════════════════
def web_search(query):
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json",
                    "no_html": "1", "skip_disambig": "1"},
            timeout=5
        )
        data = r.json()
        results = []
        if data.get("AbstractText"):
            results.append(f"📌 {data['AbstractText'][:500]}")
        for item in data.get("RelatedTopics", [])[:4]:
            if isinstance(item, dict) and item.get("Text"):
                results.append(f"• {item['Text'][:250]}")
        return "\n".join(results) if results else None
    except:
        return None

# ══════════════════════════════════════════
# WEB SCRAPING REAL
# ══════════════════════════════════════════
def is_url_safe(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        blocked = ["localhost", "127.0.0.1", "0.0.0.0", "10.", "192.168."]
        for b in blocked:
            if b in parsed.netloc:
                return False
        return True
    except:
        return False

def scrape_url(url, max_chars=4000):
    try:
        if not is_url_safe(url):
            return None, "URL no permitida"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DeepNova/1.0)"
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        html = r.text
        html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html)
        html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html)
        html = re.sub(r'<nav[^>]*>[\s\S]*?</nav>', '', html)
        html = re.sub(r'<footer[^>]*>[\s\S]*?</footer>', '', html)
        html = re.sub(r'<header[^>]*>[\s\S]*?</header>', '', html)
        html = re.sub(r'<h[1-6][^>]*>', '\n## ', html)
        html = re.sub(r'</h[1-6]>', '\n', html)
        html = re.sub(r'<li[^>]*>', '\n• ', html)
        html = re.sub(r'<p[^>]*>', '\n', html)
        html = re.sub(r'<br\s*/?>', '\n', html)
        html = re.sub(r'<[^>]+>', '', html)
        html = re.sub(r'&nbsp;', ' ', html)
        html = re.sub(r'&amp;', '&', html)
        html = re.sub(r'&lt;', '<', html)
        html = re.sub(r'&gt;', '>', html)
        html = re.sub(r'&#\d+;', '', html)
        html = re.sub(r'\n\s*\n', '\n\n', html)
        html = html.strip()
        if len(html) < 50:
            return None, "Página sin contenido legible"
        if len(html) > max_chars:
            html = html[:max_chars] + "\n\n... (contenido truncado)"
        return html, None
    except requests.exceptions.Timeout:
        return None, "Timeout al acceder a la URL"
    except requests.exceptions.HTTPError as e:
        return None, f"Error HTTP: {e.response.status_code}"
    except Exception as e:
        return None, f"Error: {str(e)}"

def extract_url(text):
    pattern = r'https?://[^\s<>"\')\]]+'
    match = re.search(pattern, text)
    return match.group(0) if match else None

def needs_search(msg):
    triggers = ["busca", "buscar", "qué es", "quién es", "cuándo",
                "noticias", "hoy", "precio", "clima", "último",
                "reciente", "2024", "2025", "actualidad", "/buscar",
                "investiga", "research", "encuentra"]
    return any(t in msg.lower() for t in triggers)

def needs_scraping(msg):
    """Detecta si el mensaje contiene una URL para leer"""
    return bool(extract_url(msg)) and any(
        w in msg.lower() for w in
        ["lee", "leer", "abre", "visita", "analiza esta",
         "qué dice", "resumen de", "/leer", "contenido de"]
    )

# ══════════════════════════════════════════
# DETECTOR DE IDIOMA
# ══════════════════════════════════════════
def detect_lang(text):
    langs = {
        "español":   ["hola", "cómo", "qué", "para", "con", "gracias", "una"],
        "english":   ["hello", "how", "what", "for", "with", "thanks", "the"],
        "português": ["olá", "como", "para", "obrigado", "você", "uma"],
        "français":  ["bonjour", "comment", "pour", "avec", "merci"],
        "deutsch":   ["hallo", "wie", "für", "mit", "danke"],
        "italiano":  ["ciao", "come", "per", "con", "grazie"],
    }
    t = text.lower()
    scores = {l: sum(1 for w in ws if w in t) for l, ws in langs.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "español"

LANG_PROMPTS = {
    "english":   "Respond in English.",
    "português": "Responda em português.",
    "français":  "Répondez en français.",
    "deutsch":   "Antworten Sie auf Deutsch.",
    "italiano":  "Rispondi in italiano.",
    "español":   "Responde en español.",
}

# ══════════════════════════════════════════
# DETECTOR DE MODOS ACTIVOS
# ══════════════════════════════════════════
def detect_modes(msg):
    msg_lower = msg.lower()
    modes = []

    if any(w in msg_lower for w in
        ["código", "code", "programa", "función", "script",
         "bug", "python", "javascript", "css", "html", "api",
         "backend", "frontend", "deploy", "git"]):
        modes.append("code")

    if any(w in msg_lower for w in
        ["diseña", "diseño", "web", "interfaz", "ui", "ux",
         "animación", "css", "página", "layout", "responsive"]):
        modes.append("design")

    if any(w in msg_lower for w in
        ["traduc", "translate", "idioma", "inglés", "español",
         "francés", "alemán", "portugués"]):
        modes.append("translate")

    if any(w in msg_lower for w in
        ["escribe", "artículo", "blog", "contenido", "post",
         "texto", "redacta", "copia", "marketing", "seo"]):
        modes.append("content")

    if any(w in msg_lower for w in
        ["analiza", "análisis", "datos", "estadística",
         "patrón", "tendencia", "insight", "reporte"]):
        modes.append("analyze")

    if any(w in msg_lower for w in
        ["razona", "por qué", "compara", "pros", "contras",
         "debería", "mejor", "peor", "evalúa", "decide"]):
        modes.append("reason")

    if "/debate" in msg_lower or "debate" in msg_lower:
        modes.append("debate")

    if any(w in msg_lower for w in
        ["/agente", "agente:", "autónomo", "paso a paso",
         "crea una app", "crea un sitio", "construye",
         "implementa", "desarrolla", "automatiza"]):
        modes.append("agent")

    if any(w in msg_lower for w in
        ["busca", "investiga", "research", "noticias", "precio"]):
        modes.append("search")

    # Detectar si quiere ejecutar código
    if any(w in msg_lower for w in
        ["ejecuta", "ejecutar", "corre", "correr", "/ejecutar",
         "/run", "calcula con python", "resultado de",
         "qué da este código", "output de"]):
        if "code" not in modes:
            modes.append("code")
        modes.append("execute")

    if not modes:
        modes.append("chat")

    return modes

def build_unified_system(modes, web_ctx="", mem_ctx="", lang="español", knowledge_ctx=""):
    system = SYSTEM_BASE + mem_ctx + knowledge_ctx
    mode_instructions = []

    if "code" in modes:
        mode_instructions.append(
            "MODO CÓDIGO ACTIVO: Genera código limpio, "
            "comentado, funcional y listo para producción. "
            "Explica cada sección. Incluye manejo de errores.")
    if "execute" in modes:
        mode_instructions.append(
            "MODO EJECUCIÓN ACTIVO: Puedes ejecutar código Python real. "
            "Genera código con print() para ver resultados reales.")
    if "design" in modes:
        mode_instructions.append(
            "MODO DISEÑO ACTIVO: Prioriza diseños premium con "
            "animaciones CSS elegantes, dark mode perfecto, "
            "glassmorphism, micro-animaciones y efectos hover suaves.")
    if "translate" in modes:
        mode_instructions.append(
            "MODO TRADUCCIÓN ACTIVO: Traduce con precisión "
            "considerando contexto cultural y matices del idioma.")
    if "content" in modes:
        mode_instructions.append(
            "MODO CONTENIDO ACTIVO: Genera contenido de alta "
            "calidad, optimizado para SEO, atractivo y original.")
    if "analyze" in modes:
        mode_instructions.append(
            "MODO ANÁLISIS ACTIVO: Proporciona análisis profundo "
            "con datos estructurados, tablas comparativas e insights accionables.")
    if "reason" in modes:
        mode_instructions.append(
            "MODO RAZONAMIENTO ACTIVO: Aplica pensamiento crítico "
            "profundo. Evalúa pros/contras, identifica riesgos y "
            "da recomendaciones concretas.")
    if "agent" in modes:
        mode_instructions.append(
            "MODO AGENTE ACTIVO: Divide la tarea en pasos claros. "
            "Ejecuta cada uno mostrando tu razonamiento. "
            "Al final verifica y sugiere mejoras.")
    if "search" in modes and web_ctx:
        mode_instructions.append(
            f"MODO BÚSQUEDA ACTIVO: Usa esta info web actual:\n{web_ctx}")
    if "debate" in modes:
        mode_instructions.append(
            "MODO DEBATE ACTIVO: Presenta múltiples perspectivas "
            "con argumentos sólidos para cada posición y da un "
            "veredicto final equilibrado.")

    if mode_instructions:
        system += "\n\nMODOS ACTIVOS EN ESTA RESPUESTA:\n"
        system += "\n".join(f"→ {m}" for m in mode_instructions)

    system += f"\n\nIDIOMA: {LANG_PROMPTS.get(lang, 'Responde en español.')}"
    return system

# ══════════════════════════════════════════
# AGENTE AUTÓNOMO
# ══════════════════════════════════════════
def autonomous_agent(task, sid):
    try:
        plan_r = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role": "system", "content":
                 "Eres un planificador experto. "
                 "Divide la tarea en máximo 5 pasos concretos. "
                 "Formato:\n1. [Paso]\n2. [Paso]\netc."},
                {"role": "user", "content": f"Planifica: {task}"}
            ],
            max_tokens=400, temperature=0.3
        )
        plan = plan_r.choices[0].message.content

        exec_r = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role": "system", "content": SYSTEM_BASE},
                {"role": "user", "content":
                 f"Ejecuta este plan para: {task}\n\n"
                 f"Plan:\n{plan}\n\n"
                 f"Desarrolla cada paso con código o instrucciones detalladas."}
            ],
            max_tokens=1500, temperature=0.7
        )
        execution = exec_r.choices[0].message.content

        verify_r = get_groq().chat.completions.create(
            model=MODELS["fast"],
            messages=[
                {"role": "system", "content":
                 "Revisor experto. En 2-3 líneas: ¿qué mejorarías?"},
                {"role": "user", "content":
                 f"Tarea: {task}\nSolución: {execution[:600]}"}
            ],
            max_tokens=150, temperature=0.3
        )
        improvements = verify_r.choices[0].message.content

        return (f"**🤖 DeepNova Agente Autónomo**\n*Tarea: {task}*\n\n"
                f"---\n**📋 Plan:**\n{plan}\n\n"
                f"---\n**⚙️ Ejecución:**\n{execution}\n\n"
                f"---\n**💡 Mejoras:**\n{improvements}")
    except Exception as e:
        return f"Error en agente: {str(e)}"

# ══════════════════════════════════════════
# MODO DEBATE
# ══════════════════════════════════════════
def debate_mode(topic):
    try:
        r1 = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role": "system", "content":
                 "Defiende la PRIMERA posición. Máximo 120 palabras."},
                {"role": "user", "content": f"Defiende: {topic}"}
            ],
            max_tokens=180, temperature=0.7
        )
        pos1 = r1.choices[0].message.content

        r2 = get_groq().chat.completions.create(
            model=MODELS["fast"],
            messages=[
                {"role": "system", "content":
                 "Defiende la posición CONTRARIA. Máximo 120 palabras."},
                {"role": "user", "content": f"Contra-argumenta: {topic}"}
            ],
            max_tokens=180, temperature=0.7
        )
        pos2 = r2.choices[0].message.content

        r3 = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role": "system", "content":
                 "Árbitro imparcial. Veredicto en 80 palabras."},
                {"role": "user", "content":
                 f"Debate: {topic}\nA: {pos1}\nB: {pos2}\nVeredicto:"}
            ],
            max_tokens=120, temperature=0.4
        )
        verdict = r3.choices[0].message.content

        return (f"**🥊 DEBATE: {topic}**\n\n"
                f"---\n**🔵 Posición A:**\n{pos1}\n\n"
                f"---\n**🔴 Posición B:**\n{pos2}\n\n"
                f"---\n**⚖️ Veredicto:**\n{verdict}")
    except Exception as e:
        return f"Error en debate: {str(e)}"

# ══════════════════════════════════════════
# MULTI-MODELO
# ══════════════════════════════════════════
def multi_verify(msg, primary):
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["fast"],
            messages=[
                {"role": "system", "content":
                 "Verifica la respuesta. Si es perfecta di 'APROBADO'. "
                 "Si mejora, añade máximo 2 oraciones."},
                {"role": "user", "content":
                 f"Pregunta: {msg[:200]}\nRespuesta: {primary[:400]}"}
            ],
            max_tokens=120, temperature=0.2
        )
        extra = r.choices[0].message.content
        if "APROBADO" not in extra:
            return primary + "\n\n💡 **Verificación:** " + extra
        return primary
    except:
        return primary

# ══════════════════════════════════════════
# ANÁLISIS DE IMÁGENES
# ══════════════════════════════════════════
def analyze_image(img_b64, prompt):
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["vision"],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt[:500]},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}"
                    }}
                ]
            }],
            max_tokens=800
        )
        return r.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "decommissioned" in err or "not supported" in err:
            return "Análisis de imágenes no disponible actualmente."
        if "413" in err or "too large" in err:
            return "Imagen muy grande. Usa una imagen de menos de 1MB."
        return f"Error analizando imagen: {err}"

# ══════════════════════════════════════════
# COMANDOS RÁPIDOS
# ══════════════════════════════════════════
def process_command(msg, sid):
    s = msg.strip()

    if s.startswith("/debate "):
        return debate_mode(s[8:]), True, ["debate"]

    if s.startswith("/agente ") or s.startswith("/agent "):
        task = s.split(" ", 1)[1]
        return autonomous_agent(task, sid), True, ["agent"]

    if s.startswith("/buscar "):
        q = s[8:]
        r = web_search(q)
        return f"**🌐 Búsqueda: {q}**\n\n{r or 'Sin resultados'}", True, ["search"]

    if s.startswith("/leer "):
        url = extract_url(s[6:])
        if not url:
            return "⚠️ URL no válida. Usa: /leer https://ejemplo.com", True, ["search"]
        content, error = scrape_url(url)
        if error:
            return f"⚠️ {error}", True, ["search"]
        try:
            r = get_groq().chat.completions.create(
                model=MODELS["smart"],
                messages=[
                    {"role": "system", "content":
                     "Analiza el contenido de esta página web. "
                     "Resume los puntos clave en español. "
                     "Formato claro con encabezados y listas."},
                    {"role": "user", "content":
                     f"URL: {url}\n\nContenido:\n{content[:3000]}"}
                ],
                max_tokens=800,
                temperature=0.5
            )
            analysis = r.choices[0].message.content
            return (f"**🌐 Análisis de:** {url}\n\n"
                    f"---\n{analysis}"), True, ["search", "analyze"]
        except Exception as e:
            return (f"**🌐 Contenido de:** {url}\n\n"
                    f"---\n{content[:2000]}"), True, ["search"]

    if s.startswith("/ejecutar ") or s.startswith("/run "):
        task = s.split(" ", 1)[1]
        return deepnova_execute(task, sid), True, ["code", "execute"]

    if s.startswith("/traducir "):
        return None, False, ["translate"]

    if s.startswith("/resumir "):
        return None, False, ["analyze", "content"]

    if s.startswith("/codigo "):
        return None, False, ["code"]

    if s == "/conocimiento" or s == "/knowledge":
        entries = knowledge_base.get("entries", [])
        if not entries:
            return "🧠 Base de conocimiento vacía.", True, ["chat"]
        cats = {}
        for e in entries[-30:]:
            cat = e.get("category", "general")
            if cat not in cats:
                cats[cat] = []
            cats[cat].append(e["content"][:80])
        result = "**🧠 Base de Conocimiento DeepNova**\n\n"
        for cat, items in cats.items():
            result += f"**{cat.upper()}:**\n"
            for item in items[-3:]:
                result += f"• {item}...\n"
            result += "\n"
        result += f"**Total:** {len(entries)} entradas"
        return result, True, ["chat"]

    if s.startswith("/aprender "):
        content = s[10:]
        if len(content) < 5:
            return "⚠️ Escribe algo para aprender.", True, ["chat"]
        add_to_knowledge(sid, "manual", content, "user")
        return f"✅ Aprendido: **{content[:80]}**", True, ["chat"]

    if s == "/olvidar":
        knowledge_base["entries"] = [
            e for e in knowledge_base.get("entries", [])
            if e.get("sid") != sid
        ]
        save_knowledge(knowledge_base)
        return "🗑️ Conocimiento personal borrado.", True, ["chat"]

    if s == "/tareas":
        tasks = tasks_store.get(sid, [])
        if not tasks:
            return "📋 Sin tareas pendientes.", True, ["chat"]
        t_list = "\n".join(
            [f"{'✅' if t['done'] else '⬜'} {i+1}. {t['text']}"
             for i, t in enumerate(tasks)]
        )
        return f"**📋 Tareas:**\n\n{t_list}", True, ["chat"]

    if s.startswith("/tarea "):
        text = s[7:]
        if sid not in tasks_store:
            tasks_store[sid] = []
        tasks_store[sid].append({"text": text, "done": False})
        return f"✅ Tarea añadida: **{text}**", True, ["chat"]

    return None, False, []

# ══════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════

@app.route("/")
def home():
    return open("index.html", encoding="utf-8").read()

@app.route("/health")
def health():
    return jsonify({
        "status":    "ok",
        "version":   "DeepNova 2.0",
        "models":    list(MODELS.keys()),
        "sessions":  len(convs),
        "memories":  len(permanent_memory),
        "sandbox":   "Python executor active"
    })

@app.route("/chat", methods=["POST"])
def chat():
    ip = request.remote_addr
    if not check_rate(ip):
        return jsonify({"response": "⚠️ Demasiadas peticiones."}), 429

    data  = request.json
    msg   = data.get("message", "").strip()
    sid   = data.get("session_id", "x")
    multi = data.get("multi_model", False)

    if not msg:
        return jsonify({"response": "Escribe algo 😊"}), 400

    safe, reason = is_safe(msg)
    if not safe:
        return jsonify({"response": f"⚠️ {reason}"}), 400

    # Comandos rápidos
    cmd, is_cmd, cmd_modes = process_command(msg, sid)
    if is_cmd:
        return jsonify({
            "response":   cmd,
            "modes_used": cmd_modes,
            "model_used": "DeepNova Command"
        })

    # Detectar modos activos
    modes = detect_modes(msg)
    if cmd_modes:
        modes = list(set(modes + cmd_modes))

    # Inicializar web_ctx ANTES de usarlo
    web_ctx  = ""
    web_used = False

    # Web scraping automático si hay URL
    if needs_scraping(msg):
        url = extract_url(msg)
        if url:
            content, error = scrape_url(url)
            if content:
                web_ctx  = f"CONTENIDO DE {url}:\n{content[:2000]}"
                web_used = True
                if "search" not in modes:
                    modes.append("search")
                if "analyze" not in modes:
                    modes.append("analyze")

    # Ejecución automática de código
    execute_keywords = [
        "ejecuta este código", "corre este código",
        "calcula con python", "ejecuta en python",
        "qué da este código"
    ]
    if any(k in msg.lower() for k in execute_keywords) or \
       "execute" in modes:
        result = deepnova_execute(msg, sid)
        save_history(sid, msg, result, "Python-Executor", modes)
        return jsonify({
            "response":   result,
            "modes_used": ["code", "execute"] + modes,
            "model_used": "Python-Executor"
        })

    # Búsqueda web (solo si no se hizo scraping)
    if not web_ctx and ("search" in modes or needs_search(msg)):
        result = web_search(msg)
        if result:
            web_ctx  = result
            web_used = True
            if "search" not in modes:
                modes.append("search")

    # Modo agente para tareas complejas
    agent_keywords = ["/agente", "agente:", "crea una app completa",
                      "crea un sitio web completo", "desarrolla desde cero",
                      "automatiza", "implementa un sistema"]
    if any(k in msg.lower() for k in agent_keywords):
        result = autonomous_agent(msg, sid)
        save_history(sid, msg, result, "Multi-Agent", modes)
        return jsonify({
            "response":   result,
            "modes_used": ["agent"] + modes,
            "model_used": "Multi-Agent",
            "web_search": web_used
        })

    # Modo debate
    if "debate" in modes and "/debate" in msg.lower():
        topic = msg.lower().replace("/debate", "").strip()
        result = debate_mode(topic)
        save_history(sid, msg, result, "Debate", modes)
        return jsonify({
            "response":   result,
            "modes_used": modes,
            "model_used": "Debate Mode"
        })

    # Detectar idioma
    lang = detect_lang(msg)

    # Memoria
    mem_ctx = get_memory_prompt(sid)

    # Conocimiento relevante
    knowledge_ctx = get_knowledge_context(msg, sid)

    # System unificado
    system = build_unified_system(modes, web_ctx, mem_ctx, lang, knowledge_ctx)

    # Seleccionar modelo
    if len(modes) > 2 or "reason" in modes or "agent" in modes:
        model = MODELS["smart"]
    elif "code" in modes or "design" in modes:
        model = MODELS["smart"]
    else:
        model = MODELS["fast"]

    # Inicializar sesión
    if sid not in convs:
        convs[sid] = []

    try:
        convs[sid].append({"role": "user", "content": msg})

        # Limitar historial según modelo para evitar error 413
        max_hist = 6 if model == MODELS["fast"] else 14

        def truncate_msg(m, max_chars=500):
            if len(m["content"]) > max_chars:
                return {
                    "role":    m["role"],
                    "content": m["content"][:max_chars] + "..."
                }
            return m

        historial_seguro = [
            truncate_msg(m) for m in convs[sid][-max_hist:]
        ]

        r = get_groq().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system[:2000]}
            ] + historial_seguro,
            temperature=0.8,
            max_tokens=1000
        )
        response = r.choices[0].message.content

        # Multi-IA verificación
        if multi and len(msg) > 20:
            response = multi_verify(msg, response)

        convs[sid].append({"role": "assistant", "content": response})

        # Guardar
        extract_memory(sid, msg)
        save_history(sid, msg, response, model, modes)
        auto_learn(sid, msg, response)

        return jsonify({
            "response":      response,
            "model_used":    model,
            "modes_used":    modes,
            "web_search":    web_used,
            "language":      lang,
            "memory_active": bool(get_memory(sid))
        })

    except Exception as e:
        if convs[sid]:
            convs[sid].pop()
        return jsonify({"response": f"Error: {str(e)}"}), 500

@app.route("/execute", methods=["POST"])
def execute_endpoint():
    """Endpoint para ejecutar código Python directamente desde el panel"""
    data = request.json
    code = data.get("code", "").strip()
    sid  = data.get("session_id", "x")

    if not code:
        return jsonify({"result": "Sin código", "success": False}), 400

    safe, reason = is_code_safe(code)
    if not safe:
        return jsonify({
            "output":  "",
            "error":   f"⚠️ Código bloqueado: {reason}",
            "success": False
        }), 400

    result = execute_python(code)
    return jsonify(result)

@app.route("/image", methods=["POST"])
def image():
    data    = request.json
    img_b64 = data.get("image", "")
    prompt  = data.get("prompt", "Describe esta imagen en detalle en español")
    if not img_b64:
        return jsonify({"result": "Sin imagen"}), 400
    return jsonify({"result": analyze_image(img_b64, prompt)})

@app.route("/tasks", methods=["GET", "POST", "PUT"])
def tasks():
    if request.method == "GET":
        sid = request.args.get("session_id", "x")
        return jsonify({"tasks": tasks_store.get(sid, [])})

    data = request.json
    sid  = data.get("session_id", "x")

    if request.method == "POST":
        text = data.get("text", "")
        if sid not in tasks_store:
            tasks_store[sid] = []
        tasks_store[sid].append({"text": text, "done": False})
        return jsonify({"status": "ok", "tasks": tasks_store[sid]})

    if request.method == "PUT":
        idx = data.get("index", 0)
        if sid in tasks_store and idx < len(tasks_store[sid]):
            tasks_store[sid][idx]["done"] = not tasks_store[sid][idx]["done"]
        return jsonify({"tasks": tasks_store.get(sid, [])})

@app.route("/memory", methods=["GET"])
def memory():
    sid = request.args.get("session_id", "x")
    return jsonify({
        "memory":   get_memory(sid),
        "messages": len(convs.get(sid, []))
    })

@app.route("/history/export", methods=["GET"])
def export_history():
    sid  = request.args.get("session_id", "x")
    fmt  = request.args.get("format", "json")
    hist = conversation_history.get(sid, [])

    if fmt == "txt":
        lines = ["=== HISTORIAL DEEPNOVA ===\n"]
        for h in hist:
            lines.append(f"[{h['timestamp']}]")
            lines.append(f"Tú: {h['user']}")
            lines.append(f"DeepNova: {h['nova']}")
            lines.append(f"Modos: {', '.join(h.get('modes_used', []))}\n")
        buf = io.BytesIO("\n".join(lines).encode("utf-8"))
        return send_file(buf, mimetype="text/plain",
                         as_attachment=True,
                         download_name="deepnova_historial.txt")

    buf = io.BytesIO(
        json.dumps(hist, ensure_ascii=False, indent=2).encode("utf-8")
    )
    return send_file(buf, mimetype="application/json",
                     as_attachment=True,
                     download_name="deepnova_historial.json")

@app.route("/analytics", methods=["GET"])
def analytics():
    sid  = request.args.get("session_id", "x")
    hist = conversation_history.get(sid, [])
    model_counts = defaultdict(int)
    mode_counts  = defaultdict(int)
    for h in hist:
        m = h.get("model", "")
        if "70b" in m:
            model_counts["LLaMA 70B"] += 1
        else:
            model_counts["LLaMA 3.1"] += 1
        for mode in h.get("modes_used", []):
            mode_counts[mode] += 1
    return jsonify({
        "total":        len(hist),
        "models":       dict(model_counts),
        "modes":        dict(mode_counts),
        "memory_items": len(get_memory(sid)),
        "active_tasks": len([t for t in tasks_store.get(sid, [])
                             if not t["done"]])
    })

@app.route("/search", methods=["POST"])
def search():
    q = request.json.get("query", "")
    return jsonify({"results": web_search(q) or "Sin resultados"})

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    text = data.get("text", "")
    task = data.get("task", "resume")
    tasks_map = {
        "resume":    "Resume en puntos clave:",
        "sentiment": "Analiza sentimiento y tono:",
        "improve":   "Mejora y corrige:",
        "keywords":  "Extrae palabras clave:",
        "translate": "Traduce al inglés:",
    }
    prompt = tasks_map.get(task, tasks_map["resume"])
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role": "system", "content": SYSTEM_BASE},
                {"role": "user", "content": f"{prompt}\n\n{text[:4000]}"}
            ],
            temperature=0.5,
            max_tokens=800
        )
        return jsonify({"result": r.choices[0].message.content})
    except Exception as e:
        return jsonify({"result": f"Error: {str(e)}"}), 500

@app.route("/knowledge", methods=["GET"])
def knowledge_endpoint():
    sid      = request.args.get("session_id", "x")
    entries  = knowledge_base.get("entries", [])
    user_e   = [e for e in entries if e.get("sid") == sid]
    global_e = [e for e in entries if e.get("sid") == "global"]
    return jsonify({
        "user_entries":   len(user_e),
        "global_entries": len(global_e),
        "total":          len(entries),
        "recent":         entries[-10:]
    })

@app.route("/knowledge/search", methods=["POST"])
def knowledge_search():
    data    = request.json
    query   = data.get("query", "")
    sid     = data.get("session_id", "x")
    results = search_knowledge(query, sid)
    return jsonify({
        "results": results,
        "query":   query,
        "total":   len(results)
    })

@app.route("/clear", methods=["POST"])
def clear():
    sid = request.json.get("session_id", "x")
    convs[sid] = []
    return jsonify({"status": "ok"})

@app.route("/clear_memory", methods=["POST"])
def clear_memory():
    sid = request.json.get("session_id", "x")
    permanent_memory[sid] = {}
    convs[sid] = []
    save_json(MEMORY_FILE, permanent_memory)
    return jsonify({"status": "ok"})

@app.route("/scrape", methods=["POST"])
def scrape():
    data = request.json
    url  = data.get("url", "").strip()

    if not url:
        return jsonify({"result": "Sin URL", "success": False}), 400

    if not is_url_safe(url):
        return jsonify({"result": "URL no permitida", "success": False}), 400

    content, error = scrape_url(url)

    if error:
        return jsonify({"result": error, "success": False})

    return jsonify({
        "result":  content,
        "success": True,
        "url":     url,
        "chars":   len(content)
    })

# ══════════════════════════════════════════
# 🚀 DEEPAGENT FEATURES — Módulos avanzados
# ══════════════════════════════════════════

WORKFLOWS_FILE = "deepnova_workflows.json"
INTEGRATIONS_FILE = "deepnova_integrations.json"
REPORTS_FILE = "deepnova_reports.json"
APPS_FILE = "deepnova_apps.json"

workflows_store   = load_json(WORKFLOWS_FILE)   or {}
integrations_store = load_json(INTEGRATIONS_FILE) or {}
reports_store     = load_json(REPORTS_FILE)     or {}
apps_store        = load_json(APPS_FILE)        or {}

# ──────────────────────────────────────────
# 📊 GENERADOR DE INFORMES ESTRUCTURADOS
# ──────────────────────────────────────────
def generate_structured_report(topic, sid, depth="standard"):
    """
    Genera un informe profesional estructurado.
    depth: 'quick' | 'standard' | 'deep'
    """
    depth_cfg = {
        "quick":    {"tokens": 1200, "sections": 4},
        "standard": {"tokens": 2200, "sections": 6},
        "deep":     {"tokens": 3500, "sections": 8},
    }.get(depth, {"tokens": 2200, "sections": 6})

    # Paso 1: investigación web si es necesario
    web_ctx = ""
    try:
        search_results = web_search(topic)
        if search_results:
            web_ctx = "\n\nDATOS WEB RECIENTES:\n" + "\n".join(
                f"- {r.get('title','')}: {r.get('snippet','')}" for r in search_results[:5]
            )
    except Exception:
        pass

    prompt_system = (
        "Eres un analista experto. Genera un INFORME PROFESIONAL ESTRUCTURADO en Markdown. "
        f"Debe tener {depth_cfg['sections']} secciones claras con encabezados ##, "
        "incluir datos concretos, tablas comparativas cuando aporten valor, "
        "y terminar con 'Conclusiones' y 'Próximos pasos'. "
        "Estilo ejecutivo, profundo, accionable."
    )
    user_msg = (
        f"Tema: {topic}\n"
        f"Profundidad: {depth}\n"
        "Estructura obligatoria:\n"
        "1. Resumen ejecutivo\n"
        "2. Contexto y antecedentes\n"
        "3. Análisis principal (con datos)\n"
        "4. Tabla comparativa o métricas clave\n"
        "5. Riesgos y oportunidades\n"
        "6. Recomendaciones\n"
        "7. Conclusiones\n"
        "8. Próximos pasos accionables"
        + web_ctx
    )
    r = get_groq().chat.completions.create(
        model=MODELS["smart"],
        messages=[
            {"role": "system", "content": prompt_system},
            {"role": "user",   "content": user_msg}
        ],
        max_tokens=depth_cfg["tokens"],
        temperature=0.6
    )
    content = r.choices[0].message.content
    report_id = f"rep_{int(time.time())}_{sid[:6]}"
    if sid not in reports_store:
        reports_store[sid] = []
    reports_store[sid].append({
        "id": report_id,
        "topic": topic,
        "depth": depth,
        "content": content,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "words": len(content.split())
    })
    save_json(REPORTS_FILE, reports_store)
    return {"id": report_id, "content": content, "words": len(content.split())}

# ──────────────────────────────────────────
# 🏗️ CONSTRUCTOR DE APPS SIN CÓDIGO
# ──────────────────────────────────────────
def build_no_code_app(description, sid, app_type="webapp"):
    """
    Genera una aplicación web completa (HTML+CSS+JS) a partir de una descripción.
    app_type: 'webapp' | 'landing' | 'dashboard' | 'tool'
    """
    type_hints = {
        "webapp":    "aplicación web interactiva con lógica",
        "landing":   "landing page moderna con secciones hero, features, CTA",
        "dashboard": "dashboard con tarjetas de métricas, gráficas CSS y tablas",
        "tool":      "herramienta utilitaria enfocada a resolver una tarea concreta",
    }.get(app_type, "aplicación web")

    system = (
        "Eres un desarrollador senior full-stack y diseñador UI/UX premium. "
        "Genera una aplicación web COMPLETA en UN SOLO archivo HTML autocontenido. "
        "Requisitos OBLIGATORIOS:\n"
        "- HTML5 semántico + CSS moderno (variables, grid, flex) + JS vanilla funcional\n"
        "- Diseño DARK MODE premium con gradientes y animaciones sutiles\n"
        "- 100% responsive (móvil + desktop)\n"
        "- Sin dependencias externas (sin CDN obligatorio)\n"
        "- Código LIMPIO, comentado y listo para producción\n"
        "- Debe FUNCIONAR al abrirlo en un navegador\n"
        "Devuelve SOLO el código HTML entre ```html ... ``` sin texto adicional."
    )
    user = f"Tipo: {type_hints}\nDescripción del usuario: {description}\nGenera el HTML completo."
    r = get_groq().chat.completions.create(
        model=MODELS["smart"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ],
        max_tokens=4000,
        temperature=0.65
    )
    raw = r.choices[0].message.content
    # Extraer HTML
    m = re.search(r"```(?:html)?\n?([\s\S]*?)```", raw)
    html_code = m.group(1).strip() if m else raw.strip()
    if not html_code.lower().startswith("<!doctype") and "<html" not in html_code.lower():
        html_code = f"<!DOCTYPE html>\n<html lang='es'>\n<head><meta charset='UTF-8'></head>\n<body>\n{html_code}\n</body></html>"

    app_id = f"app_{int(time.time())}_{sid[:6]}"
    if sid not in apps_store:
        apps_store[sid] = []
    apps_store[sid].append({
        "id":   app_id,
        "type": app_type,
        "description": description,
        "html": html_code,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "size_kb": round(len(html_code)/1024, 2)
    })
    save_json(APPS_FILE, apps_store)
    return {"id": app_id, "html": html_code, "size_kb": round(len(html_code)/1024, 2)}

# ──────────────────────────────────────────
# ⚙️ MOTOR DE WORKFLOWS / AUTOMATIZACIÓN
# ──────────────────────────────────────────
WORKFLOW_STEP_TYPES = {
    "search":    "Búsqueda web",
    "analyze":   "Análisis de texto",
    "summarize": "Resumir contenido",
    "translate": "Traducir texto",
    "code":      "Generar código",
    "execute":   "Ejecutar Python",
    "report":    "Generar informe",
    "email_draft": "Redactar email",
}

def run_workflow_step(step, context):
    """Ejecuta un paso individual de workflow y devuelve el resultado."""
    stype = step.get("type", "analyze")
    inp   = step.get("input", "")
    # Sustituir variables {{prev}} con el resultado del paso anterior
    inp = inp.replace("{{prev}}", str(context.get("prev", ""))[:2000])
    try:
        if stype == "search":
            results = web_search(inp)
            return "\n".join(f"- {r.get('title','')}: {r.get('snippet','')}" for r in (results or [])[:5])
        if stype == "execute":
            ex = execute_python(inp)
            return ex.get("output") or ex.get("error", "")
        if stype == "report":
            rep = generate_structured_report(inp, context.get("sid", "wf"), depth="quick")
            return rep["content"][:3000]
        # Para el resto usamos LLM con prompts distintos
        system_map = {
            "analyze":   "Analiza el siguiente contenido y extrae insights clave en viñetas.",
            "summarize": "Resume el siguiente contenido en 5 puntos clave.",
            "translate": "Traduce al inglés el siguiente texto de forma natural.",
            "code":      "Genera código funcional listo para producción con comentarios.",
            "email_draft": "Redacta un email profesional claro, asunto incluido.",
        }
        sys_p = system_map.get(stype, "Procesa la siguiente entrada.")
        r = get_groq().chat.completions.create(
            model=MODELS["fast"],
            messages=[
                {"role": "system", "content": sys_p},
                {"role": "user",   "content": inp}
            ],
            max_tokens=800,
            temperature=0.5
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"[Error en paso {stype}: {e}]"

def execute_workflow(wf_id, sid):
    wf = workflows_store.get(sid, {}).get(wf_id)
    if not wf:
        return {"success": False, "error": "Workflow no encontrado"}
    steps = wf.get("steps", [])
    context = {"sid": sid, "prev": ""}
    logs = []
    for i, step in enumerate(steps, 1):
        logs.append(f"**Paso {i}: {WORKFLOW_STEP_TYPES.get(step['type'], step['type'])}**")
        out = run_workflow_step(step, context)
        context["prev"] = out
        logs.append(out[:1500] + ("..." if len(out) > 1500 else ""))
        logs.append("---")
    wf["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    wf["runs"] = wf.get("runs", 0) + 1
    save_json(WORKFLOWS_FILE, workflows_store)
    return {"success": True, "logs": "\n\n".join(logs), "steps_run": len(steps)}

# ──────────────────────────────────────────
# 🔌 INTEGRACIONES EXTERNAS (mock seguro)
# ──────────────────────────────────────────
AVAILABLE_INTEGRATIONS = {
    "gmail":       {"name": "Gmail",            "icon": "📧", "category": "Google Workspace"},
    "gdrive":      {"name": "Google Drive",     "icon": "📁", "category": "Google Workspace"},
    "gcalendar":   {"name": "Google Calendar",  "icon": "📅", "category": "Google Workspace"},
    "gsheets":     {"name": "Google Sheets",    "icon": "📊", "category": "Google Workspace"},
    "salesforce":  {"name": "Salesforce",       "icon": "☁️", "category": "CRM"},
    "hubspot":     {"name": "HubSpot",          "icon": "🧲", "category": "CRM"},
    "slack":       {"name": "Slack",            "icon": "💬", "category": "Comunicación"},
    "notion":      {"name": "Notion",           "icon": "📓", "category": "Productividad"},
    "github":      {"name": "GitHub",           "icon": "🐙", "category": "Desarrollo"},
    "jira":        {"name": "Jira",             "icon": "🎯", "category": "Gestión"},
    "trello":      {"name": "Trello",           "icon": "📋", "category": "Gestión"},
    "zapier":      {"name": "Zapier",           "icon": "⚡", "category": "Automatización"},
}

def connect_integration(sid, key, credentials=None):
    if key not in AVAILABLE_INTEGRATIONS:
        return {"success": False, "error": "Integración desconocida"}
    if sid not in integrations_store:
        integrations_store[sid] = {}
    integrations_store[sid][key] = {
        "connected":  True,
        "connected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "meta":       AVAILABLE_INTEGRATIONS[key],
        # credentials NO se guardan en texto plano en un sistema real
        "credentials_set": bool(credentials)
    }
    save_json(INTEGRATIONS_FILE, integrations_store)
    return {"success": True, "integration": key}

def disconnect_integration(sid, key):
    if sid in integrations_store and key in integrations_store[sid]:
        del integrations_store[sid][key]
        save_json(INTEGRATIONS_FILE, integrations_store)
        return {"success": True}
    return {"success": False, "error": "No conectada"}

# ──────────────────────────────────────────
# 📄 ANÁLISIS DE DOCUMENTOS
# ──────────────────────────────────────────
def extract_text_from_upload(filename, b64_data):
    """Extrae texto de PDF, TXT, MD o DOCX (subido en base64)."""
    try:
        raw = base64.b64decode(b64_data)
    except Exception as e:
        return None, f"Base64 inválido: {e}"
    ext = (filename.rsplit(".", 1)[-1] or "").lower()
    try:
        if ext in ("txt", "md", "csv", "json", "log"):
            return raw.decode("utf-8", errors="ignore"), None
        if ext == "pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                try:
                    from PyPDF2 import PdfReader
                except ImportError:
                    return None, "Instala pypdf o PyPDF2 para analizar PDF"
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((p.extract_text() or "") for p in reader.pages), None
        if ext == "docx":
            try:
                from docx import Document
            except ImportError:
                return None, "Instala python-docx para analizar DOCX"
            doc = Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs), None
        # Fallback: intentar como texto
        return raw.decode("utf-8", errors="ignore"), None
    except Exception as e:
        return None, f"Error procesando documento: {e}"

def analyze_document(text, question=None):
    """Analiza un documento: resumen + insights + Q&A opcional."""
    text = (text or "")[:15000]  # Límite de seguridad
    if not text.strip():
        return "El documento está vacío o no se pudo leer."
    if question:
        system = (
            "Eres un experto analista. Responde la pregunta del usuario "
            "BASÁNDOTE EXCLUSIVAMENTE en el documento aportado. "
            "Si la respuesta no está, dilo claramente."
        )
        user = f"DOCUMENTO:\n{text}\n\nPREGUNTA: {question}"
    else:
        system = (
            "Eres un analista experto. Analiza el documento y devuelve en Markdown:\n"
            "## Resumen ejecutivo (3 frases)\n"
            "## Puntos clave (5 viñetas)\n"
            "## Entidades y cifras importantes\n"
            "## Tono / Propósito del documento\n"
            "## Próximos pasos recomendados"
        )
        user = f"DOCUMENTO:\n{text}"
    r = get_groq().chat.completions.create(
        model=MODELS["smart"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ],
        max_tokens=1500,
        temperature=0.4
    )
    return r.choices[0].message.content

# ══════════════════════════════════════════
# 🆕 NUEVOS ENDPOINTS DEEPAGENT
# ══════════════════════════════════════════

@app.route("/report/generate", methods=["POST"])
def report_generate():
    data  = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    depth = data.get("depth", "standard")
    sid   = data.get("sid", "anon")
    if not topic:
        return jsonify({"error": "Falta 'topic'"}), 400
    if not check_rate(request.remote_addr or "x", 10, 60):
        return jsonify({"error": "Rate limit"}), 429
    try:
        result = generate_structured_report(topic, sid, depth)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/report/list", methods=["GET"])
def report_list():
    sid = request.args.get("sid", "anon")
    return jsonify({"reports": reports_store.get(sid, [])[-20:]})

@app.route("/app/build", methods=["POST"])
def app_build():
    data = request.get_json() or {}
    desc = (data.get("description") or "").strip()
    app_type = data.get("type", "webapp")
    sid  = data.get("sid", "anon")
    if not desc:
        return jsonify({"error": "Falta 'description'"}), 400
    if not check_rate(request.remote_addr or "x", 10, 60):
        return jsonify({"error": "Rate limit"}), 429
    try:
        result = build_no_code_app(desc, sid, app_type)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/app/list", methods=["GET"])
def app_list():
    sid = request.args.get("sid", "anon")
    lst = [{k: v for k, v in a.items() if k != "html"} for a in apps_store.get(sid, [])[-20:]]
    return jsonify({"apps": lst})

@app.route("/app/<app_id>", methods=["GET"])
def app_get(app_id):
    sid = request.args.get("sid", "anon")
    for a in apps_store.get(sid, []):
        if a["id"] == app_id:
            return jsonify({"success": True, "app": a})
    return jsonify({"success": False, "error": "No encontrada"}), 404

@app.route("/workflow", methods=["GET", "POST", "DELETE"])
def workflow_endpoint():
    if request.method == "GET":
        sid = request.args.get("sid", "anon")
        return jsonify({
            "workflows": list((workflows_store.get(sid, {}) or {}).values()),
            "step_types": WORKFLOW_STEP_TYPES
        })
    if request.method == "POST":
        data = request.get_json() or {}
        sid  = data.get("sid", "anon")
        name = (data.get("name") or "").strip() or f"Workflow {len(workflows_store.get(sid,{}))+1}"
        steps = data.get("steps", [])
        if not steps or not isinstance(steps, list):
            return jsonify({"error": "Faltan steps"}), 400
        wf_id = f"wf_{int(time.time())}_{sid[:6]}"
        if sid not in workflows_store:
            workflows_store[sid] = {}
        workflows_store[sid][wf_id] = {
            "id": wf_id,
            "name": name,
            "steps": steps,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "runs": 0,
            "last_run": None
        }
        save_json(WORKFLOWS_FILE, workflows_store)
        return jsonify({"success": True, "id": wf_id})
    if request.method == "DELETE":
        data = request.get_json() or {}
        sid  = data.get("sid", "anon")
        wf_id = data.get("id")
        if sid in workflows_store and wf_id in workflows_store[sid]:
            del workflows_store[sid][wf_id]
            save_json(WORKFLOWS_FILE, workflows_store)
            return jsonify({"success": True})
        return jsonify({"success": False}), 404

@app.route("/workflow/run", methods=["POST"])
def workflow_run():
    data = request.get_json() or {}
    sid  = data.get("sid", "anon")
    wf_id = data.get("id")
    if not wf_id:
        return jsonify({"error": "Falta id"}), 400
    if not check_rate(request.remote_addr or "x", 5, 60):
        return jsonify({"error": "Rate limit"}), 429
    try:
        result = execute_workflow(wf_id, sid)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/integrations", methods=["GET"])
def integrations_list():
    sid = request.args.get("sid", "anon")
    connected = integrations_store.get(sid, {}) or {}
    catalog = []
    for key, meta in AVAILABLE_INTEGRATIONS.items():
        catalog.append({
            "key":       key,
            "name":      meta["name"],
            "icon":      meta["icon"],
            "category":  meta["category"],
            "connected": key in connected,
            "connected_at": connected.get(key, {}).get("connected_at")
        })
    return jsonify({"integrations": catalog})

@app.route("/integrations/connect", methods=["POST"])
def integrations_connect():
    data = request.get_json() or {}
    sid  = data.get("sid", "anon")
    key  = data.get("key")
    creds = data.get("credentials")
    return jsonify(connect_integration(sid, key, creds))

@app.route("/integrations/disconnect", methods=["POST"])
def integrations_disconnect():
    data = request.get_json() or {}
    return jsonify(disconnect_integration(data.get("sid", "anon"), data.get("key")))

@app.route("/document/analyze", methods=["POST"])
def document_analyze():
    data = request.get_json() or {}
    filename = data.get("filename", "doc.txt")
    b64      = data.get("data", "")
    text     = data.get("text", "")  # alternativa: texto directo
    question = data.get("question")
    sid      = data.get("sid", "anon")
    if not check_rate(request.remote_addr or "x", 10, 60):
        return jsonify({"error": "Rate limit"}), 429
    if not text and b64:
        text, err = extract_text_from_upload(filename, b64)
        if err:
            return jsonify({"success": False, "error": err}), 400
    if not text:
        return jsonify({"success": False, "error": "Sin contenido para analizar"}), 400
    try:
        result = analyze_document(text, question)
        # Guardar en knowledge base
        add_to_knowledge(sid, "documento", f"{filename}: {text[:400]}", "upload")
        return jsonify({
            "success":   True,
            "filename":  filename,
            "chars":     len(text),
            "analysis":  result
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════
# 🆕 M1 · RAZONAMIENTO AVANZADO (CoT + Self-Consistency + ReAct)
# ══════════════════════════════════════════

# Prompts y modelos por modo M3 (12 modos aislados)
MODE_CONFIG = {
    "chat":      {"model": MODELS["fast"],    "color": "#6366f1", "temp": 0.8,
                   "prompt": "Eres DeepNova en modo Chat: conversación inteligente, amable y directa."},
    "code":      {"model": MODELS["smart"],   "color": "#06b6d4", "temp": 0.3,
                   "prompt": "Eres DeepNova en modo Código: genera código limpio, comentado, producción-ready."},
    "execute":   {"model": MODELS["smart"],   "color": "#10b981", "temp": 0.2,
                   "prompt": "Eres DeepNova en modo Ejecución: generas Python con print() y verificas."},
    "design":    {"model": MODELS["smart"],   "color": "#8b5cf6", "temp": 0.7,
                   "prompt": "Eres DeepNova en modo Diseño: UI/UX premium, animaciones, dark mode."},
    "translate": {"model": MODELS["fast"],    "color": "#4ade80", "temp": 0.4,
                   "prompt": "Eres DeepNova en modo Traducción: precisión léxica y contexto cultural."},
    "content":   {"model": MODELS["smart"],   "color": "#fb923c", "temp": 0.75,
                   "prompt": "Eres DeepNova en modo Contenido: textos SEO-ready, atractivos y originales."},
    "analyze":   {"model": MODELS["smart"],   "color": "#22c55e", "temp": 0.5,
                   "prompt": "Eres DeepNova en modo Análisis: datos, patrones, insights accionables."},
    "reason":    {"model": MODELS["reason"],  "color": "#fbbf24", "temp": 0.5,
                   "prompt": "Eres DeepNova en modo Razonamiento: lógica profunda, pros/contras, decisiones."},
    "research":  {"model": MODELS["smart"],   "color": "#06b6d4", "temp": 0.5,
                   "prompt": "Eres DeepNova en modo Research: investigación profunda con datos 2025-2026."},
    "agent":     {"model": MODELS["smart"],   "color": "#fb923c", "temp": 0.6,
                   "prompt": "Eres DeepNova en modo Agente: planificas, ejecutas paso a paso y verificas."},
    "debate":    {"model": MODELS["smart"],   "color": "#f87171", "temp": 0.7,
                   "prompt": "Eres DeepNova en modo Debate: múltiples perspectivas y veredicto."},
    "creative":  {"model": MODELS["creative"], "color": "#ec4899", "temp": 0.9,
                   "prompt": "Eres DeepNova en modo Creativo: ideas originales, narrativa, storytelling."},
}

def _llm_call(messages, temperature, model=None):
    """Wrapper unificado para el pipeline M1."""
    try:
        r = get_groq().chat.completions.create(
            model=model or MODELS["smart"],
            messages=messages,
            temperature=temperature,
            max_tokens=1200,
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"[Error LLM: {e}]"

def _fast_llm(prompt):
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["fast"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=200,
        )
        return r.choices[0].message.content
    except Exception:
        return ""

@app.route("/api/reason", methods=["POST"])
def api_reason():
    """Endpoint avanzado M1: CoT + self-consistency + meta-check."""
    if _reasoning is None:
        return jsonify({"error": "Módulo reasoning no disponible"}), 501
    data  = request.get_json() or {}
    query = (data.get("query") or "").strip()
    mode  = data.get("mode", "reason")
    use_sc = bool(data.get("self_consistency", False))
    if not query:
        return jsonify({"error": "Falta 'query'"}), 400
    cfg = MODE_CONFIG.get(mode, MODE_CONFIG["chat"])
    try:
        result = _reasoning.reason_pipeline(
            query=query, mode=mode,
            llm_call=lambda m, t: _llm_call(m, t, cfg["model"]),
            fast_llm=_fast_llm,
            base_system=SYSTEM_BASE + "\n\n" + cfg["prompt"],
            use_self_consistency=use_sc,
        )
        # No exponer thinking al cliente por defecto
        public = {k: v for k, v in result.items() if k != "thinking"}
        return jsonify({"success": True, **public, "mode_config": cfg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/modes", methods=["GET"])
def api_modes():
    """Catálogo de modos M3 con colores y modelos."""
    return jsonify({"modes": [
        {"key": k, "model": v["model"], "color": v["color"],
         "temp": v["temp"], "prompt": v["prompt"][:120]}
        for k, v in MODE_CONFIG.items()
    ]})

# ══════════════════════════════════════════
# 🆕 M2 · CONVERSACIONES PERSISTENTES + BÚSQUEDA SEMÁNTICA
# ══════════════════════════════════════════

@app.route("/api/conversations", methods=["GET", "POST"])
def api_conversations():
    if _db is None:
        return jsonify({"error": "DB no disponible"}), 501
    if request.method == "GET":
        sid = request.args.get("sid", "anon")
        return jsonify({"conversations": _db.list_conversations(sid)})
    data = request.get_json() or {}
    sid = data.get("sid", "anon")
    title = data.get("title", "Nueva conversación")
    mode = data.get("mode", "chat")
    cid = _db.create_conversation(sid, title, mode)
    return jsonify({"success": bool(cid), "id": cid})

@app.route("/api/conversations/<int:cid>", methods=["GET", "PATCH", "DELETE"])
def api_conversation_detail(cid):
    if _db is None:
        return jsonify({"error": "DB no disponible"}), 501
    if request.method == "GET":
        conv = _db.get_conversation(cid)
        if not conv:
            return jsonify({"error": "No encontrada"}), 404
        msgs = _db.list_messages(cid)
        # Limpiamos blobs de embedding del payload público
        for m in msgs:
            m.pop("embedding_blob", None)
        return jsonify({"conversation": conv, "messages": msgs})
    if request.method == "PATCH":
        data = request.get_json() or {}
        fields = {k: data[k] for k in ("title", "mode", "summary") if k in data}
        ok = _db.update_conversation(cid, **fields)
        return jsonify({"success": ok})
    if request.method == "DELETE":
        return jsonify({"success": _db.delete_conversation(cid)})

@app.route("/api/conversations/<int:cid>/messages", methods=["POST"])
def api_add_message(cid):
    if _db is None:
        return jsonify({"error": "DB no disponible"}), 501
    data = request.get_json() or {}
    role = data.get("role", "user")
    content = data.get("content", "")
    model = data.get("model", "")
    modes = data.get("modes", [])
    blob = None
    if _emb is not None:
        try:
            blob = _emb.embed_to_blob(content)
        except Exception:
            blob = None
    mid = _db.add_message(cid, role, content, model, modes, blob)
    # Summarize cada 50 mensajes
    try:
        n = _db.count_messages(cid)
        if n % 50 == 0 and n > 0:
            _auto_summarize_conversation(cid)
    except Exception:
        pass
    return jsonify({"success": bool(mid), "id": mid})

def _auto_summarize_conversation(cid):
    """Genera un resumen cada 50 mensajes para mantener el contexto compacto."""
    if _db is None:
        return
    msgs = _db.list_messages(cid, limit=50)
    if not msgs:
        return
    text = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in msgs)[-6000:]
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["fast"],
            messages=[
                {"role": "system", "content": "Resume la conversación en 5 bullets clave."},
                {"role": "user",   "content": text},
            ],
            temperature=0.3, max_tokens=300,
        )
        summary = r.choices[0].message.content
        _db.update_conversation(cid, summary=summary)
    except Exception as e:
        print(f"[auto-summary] {e}")

@app.route("/api/memory/search", methods=["POST"])
def api_memory_search():
    """Búsqueda semántica cross-conversation por sid."""
    if _db is None or _emb is None:
        return jsonify({"error": "DB/embeddings no disponibles"}), 501
    data  = request.get_json() or {}
    sid   = data.get("sid", "anon")
    query = (data.get("query") or "").strip()
    top_k = int(data.get("top_k", 5))
    if not query:
        return jsonify({"error": "Falta 'query'"}), 400
    try:
        corpus_raw = _db.all_messages_with_embedding(sid, limit=500)
        corpus = [
            ({"id": r["id"], "conv_id": r["conversation_id"],
              "role": r["role"], "content": r["content"],
              "title": r["title"], "created_at": str(r["created_at"])},
             r["embedding_blob"])
            for r in corpus_raw
        ]
        results = _emb.semantic_search(query, corpus, top_k=top_k)
        out = [{"score": round(s, 3), **item} for s, item in results]
        return jsonify({"results": out, "total": len(out),
                        "engine": "MiniLM-L6-v2" if _emb.is_real_model() else "fallback-hash"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════
# 🆕 M5 · FEEDBACK (base para autoaprendizaje)
# ══════════════════════════════════════════

@app.route("/api/feedback", methods=["POST", "GET"])
def api_feedback():
    if _db is None:
        return jsonify({"error": "DB no disponible"}), 501
    if request.method == "GET":
        return jsonify(_db.feedback_stats(limit=50))
    data = request.get_json() or {}
    sid = data.get("sid", "anon")
    vote = int(data.get("vote", 0))         # +1 / -1
    comment = data.get("comment", "")
    message_id = data.get("message_id")
    signal = data.get("signal", "thumb")    # thumb | copied | regenerated
    fid = _db.add_feedback(sid, message_id, vote, comment, signal)
    return jsonify({"success": bool(fid), "id": fid})

# ══════════════════════════════════════════
# 🆕 HEALTH EXTENDIDO (estado de módulos v2)
# ══════════════════════════════════════════

@app.route("/api/health")
def api_health():
    info = {
        "version":   "DeepNova 2.0 Híbrido",
        "v2_modules": _DN2_OK,
        "models":    list(MODELS.keys()),
        "reasoning": _reasoning is not None,
        "database":  _db is not None,
        "embeddings": _emb is not None,
        "embeddings_engine": (_emb.is_real_model() if _emb else None),
        "favicon":   _favicon is not None,
    }
    if _db is not None:
        try:
            info["db"] = _db.db_info()
        except Exception:
            pass
    return jsonify(info)

# ══════════════════════════════════════════
# 🚀 ARRANQUE
# ══════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
