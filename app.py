from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import groq, os, re, time, json, requests, base64
from collections import defaultdict
from datetime import datetime
import io

app = Flask(__name__)
CORS(app)

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
Tu objetivo es ser la experiencia de IA más excepcional posible.

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

def needs_search(msg):
    triggers = ["busca", "buscar", "qué es", "quién es", "cuándo",
                "noticias", "hoy", "precio", "clima", "último",
                "reciente", "2024", "2025", "actualidad", "/buscar",
                "investiga", "research", "encuentra"]
    return any(t in msg.lower() for t in triggers)

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

    if not modes:
        modes.append("chat")

    return modes

def build_unified_system(modes, web_ctx="", mem_ctx="", lang="español"):
    system = SYSTEM_BASE + mem_ctx
    mode_instructions = []

    if "code" in modes:
        mode_instructions.append(
            "MODO CÓDIGO ACTIVO: Genera código limpio, "
            "comentado, funcional y listo para producción. "
            "Explica cada sección. Incluye manejo de errores.")
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

    if s.startswith("/traducir "):
        return None, False, ["translate"]

    if s.startswith("/resumir "):
        return None, False, ["analyze", "content"]

    if s.startswith("/codigo "):
        return None, False, ["code"]

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
        "status": "ok",
        "version": "DeepNova 1.0",
        "models": list(MODELS.keys()),
        "sessions": len(convs),
        "memories": len(permanent_memory)
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
            "response": cmd,
            "modes_used": cmd_modes,
            "model_used": "DeepNova Command"
        })

    # Detectar modos activos
    modes = detect_modes(msg)
    if cmd_modes:
        modes = list(set(modes + cmd_modes))

    # Búsqueda web
    web_ctx  = ""
    web_used = False
    if "search" in modes or needs_search(msg):
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
            "response": result,
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
            "response": result,
            "modes_used": modes,
            "model_used": "Debate Mode"
        })

    # Detectar idioma
    lang = detect_lang(msg)

    # Memoria
    mem_ctx = get_memory_prompt(sid)

    # System unificado
    system = build_unified_system(modes, web_ctx, mem_ctx, lang)

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

        # Truncar mensajes muy largos
        def truncate_msg(m, max_chars=500):
            if len(m["content"]) > max_chars:
                return {
                    "role": m["role"],
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
