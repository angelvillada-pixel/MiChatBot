from flask import Flask, request, jsonify
from flask_cors import CORS
import groq, os, re, time, json, requests
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# ── CLIENTES ──────────────────────────────
_groq_client = None

def get_groq():
    global _groq_client
    if _groq_client is None:
        _groq_client = groq.Groq(
            api_key=os.environ.get("GROQ_API_KEY")
        )
    return _groq_client

# ── MODELOS DISPONIBLES ───────────────────
MODELS = {
    "fast":    "llama-3.1-8b-instant",      # Rápido
    "smart":   "llama-3.3-70b-versatile",   # Inteligente
    "reason":  "deepseek-r1-distill-llama-70b", # Razonamiento
    "mix":     "mixtral-8x7b-32768",        # Creativo
}

# ── PERSONALIDAD NOVA 3.0 ─────────────────
SYSTEM_BASE = """Eres "Nova 3.0", una IA avanzada y en evolución constante.

IDENTIDAD:
- Nombre: Nova 3.0
- Versión: 3.0 — Multi-modelo, memoria persistente
- Creada para ser la IA más útil y adaptable

PERSONALIDAD:
- Inteligente, creativa, directa y profesional
- Respondes SIEMPRE en español
- Máximo 3 emojis por respuesta
- Formato visual claro: párrafos cortos y listas
- Proactiva: sugieres mejoras constantemente

CAPACIDADES REALES:
1. Razonamiento avanzado (multi-modelo)
2. Memoria de conversación persistente
3. Búsqueda web en tiempo real
4. Análisis de documentos y texto
5. Código limpio y explicado
6. Traducción avanzada
7. Diseño web premium
8. Generación de contenido

ESTILO:
- Respuestas organizadas con encabezados
- Código siempre comentado
- Tablas para comparaciones
- Nunca "paredes de texto"

OBJETIVO: Ser la experiencia de IA
más excepcional posible."""

# ── MEMORIA PERSISTENTE ───────────────────
# Simula memoria entre sesiones
# En producción real usarías una BD

sessions_memory = {}  # memoria por sesión
user_profiles   = {}  # perfil del usuario
convs           = {}  # conversaciones

def get_memory_context(sid):
    """Obtiene contexto de memoria del usuario"""
    if sid not in sessions_memory:
        return ""
    mem = sessions_memory[sid]
    if not mem:
        return ""
    ctx = "\n\nMEMORIA DEL USUARIO:\n"
    for key, val in mem.items():
        ctx += f"- {key}: {val}\n"
    return ctx

def extract_and_save_memory(sid, msg, response):
    """Extrae información importante y la guarda"""
    if sid not in sessions_memory:
        sessions_memory[sid] = {}

    msg_lower = msg.lower()

    # Detectar nombre
    if any(w in msg_lower for w in ["me llamo","mi nombre es","soy "]):
        words = msg.split()
        for i, w in enumerate(words):
            if w.lower() in ["llamo","es","soy"] and i+1 < len(words):
                sessions_memory[sid]["nombre"] = words[i+1]
                break

    # Detectar preferencias
    if "me gusta" in msg_lower or "prefiero" in msg_lower:
        sessions_memory[sid]["preferencia_reciente"] = msg[:100]

    # Detectar profesión
    if any(w in msg_lower for w in
        ["trabajo en","soy desarrollador","soy diseñador",
         "soy estudiante","mi trabajo"]):
        sessions_memory[sid]["contexto_profesional"] = msg[:150]

# ── RATE LIMITING ─────────────────────────
rate_counts = defaultdict(list)

def check_rate(ip, max_r=30, win=60):
    now = time.time()
    rate_counts[ip] = [
        t for t in rate_counts[ip] if now-t < win
    ]
    if len(rate_counts[ip]) >= max_r:
        return False
    rate_counts[ip].append(now)
    return True

# ── FILTRO DE SEGURIDAD ───────────────────
BLOCKED = [
    r"(?i)(hackear sistema|explotar|malware real)",
    r"(?i)(robar contraseña|phishing real)",
]

def is_safe(text):
    if len(text) > 5000:
        return False, "Mensaje muy largo"
    for p in BLOCKED:
        if re.search(p, text):
            return False, "Contenido no permitido"
    return True, ""

# ── BÚSQUEDA WEB ──────────────────────────
def web_search(query):
    """
    Búsqueda web usando DuckDuckGo (gratuito, sin API key)
    """
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1"
        }
        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        results = []

        # Respuesta directa
        if data.get("AbstractText"):
            results.append(f"📌 {data['AbstractText'][:300]}")

        # Resultados relacionados
        for item in data.get("RelatedTopics", [])[:3]:
            if isinstance(item, dict) and item.get("Text"):
                results.append(f"• {item['Text'][:200]}")

        if results:
            return "\n".join(results)
        else:
            return None

    except Exception as e:
        return None

def needs_web_search(msg):
    """Detecta si el mensaje necesita búsqueda web"""
    triggers = [
        "busca","buscar","qué es","quién es",
        "cuándo","dónde","noticias","actualidad",
        "hoy","precio","clima","último","reciente",
        "search","find","news","latest","2024","2025"
    ]
    msg_lower = msg.lower()
    return any(t in msg_lower for t in triggers)

# ── SELECCIÓN INTELIGENTE DE MODELO ───────
def select_model(msg):
    """Elige el mejor modelo según la tarea"""
    msg_lower = msg.lower()

    # Razonamiento complejo
    if any(w in msg_lower for w in
        ["analiza","razona","explica por qué",
         "compara","pros y contras","debería"]):
        return MODELS["reason"], "🧠 Razonamiento"

    # Código
    if any(w in msg_lower for w in
        ["código","code","programa","función",
         "script","bug","error","python","javascript"]):
        return MODELS["smart"], "💻 Código"

    # Creatividad
    if any(w in msg_lower for w in
        ["crea","imagina","escribe","historia",
         "poema","idea","diseña","inventa"]):
        return MODELS["mix"], "🎨 Creativo"

    # Default: rápido
    return MODELS["fast"], "⚡ Rápido"

# ── MULTI-IA: CONSULTA A VARIOS MODELOS ───
def multi_model_query(msg, primary_response):
    """
    Consulta a múltiples modelos y combina respuestas
    Solo para preguntas importantes
    """
    try:
        # Segundo modelo verifica/enriquece la respuesta
        verify_prompt = f"""El usuario preguntó: "{msg}"

Una IA respondió: "{primary_response[:500]}"

Enriquece o corrige esta respuesta en máximo 2 párrafos.
Si la respuesta ya es perfecta, solo di "APROBADO"."""

        r = get_groq().chat.completions.create(
            model=MODELS["reason"],
            messages=[
                {"role":"system","content":"Eres un verificador experto. Sé conciso."},
                {"role":"user","content":verify_prompt}
            ],
            max_tokens=300,
            temperature=0.3
        )
        verification = r.choices[0].message.content

        if "APROBADO" not in verification:
            return primary_response + \
                "\n\n---\n💡 **Análisis adicional:**\n" + \
                verification
        return primary_response

    except:
        return primary_response

# ── ENDPOINTS ─────────────────────────────

@app.route("/")
def home():
    return open("index.html", encoding="utf-8").read()

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "Nova 3.0",
        "models": list(MODELS.values()),
        "sessions": len(convs)
    })

@app.route("/chat", methods=["POST"])
def chat():
    ip = request.remote_addr
    if not check_rate(ip):
        return jsonify({
            "response":"⚠️ Demasiadas peticiones. Espera."
        }), 429

    data = request.json
    msg  = data.get("message","").strip()
    sid  = data.get("session_id","x")
    use_multi = data.get("multi_model", False)

    if not msg:
        return jsonify({"response":"Escribe algo 😊"}),400

    safe, reason = is_safe(msg)
    if not safe:
        return jsonify({"response":f"⚠️ {reason}"}),400

    # Inicializar sesión
    if sid not in convs:
        convs[sid] = []

    # Seleccionar modelo
    model, mode_label = select_model(msg)

    # Búsqueda web si es necesario
    web_context = ""
    web_used = False
    if needs_web_search(msg):
        results = web_search(msg)
        if results:
            web_context = f"\n\nINFO WEB ACTUAL:\n{results}"
            web_used = True

    # Memoria del usuario
    memory_ctx = get_memory_context(sid)

    # System prompt completo
    system = SYSTEM_BASE + memory_ctx + web_context

    try:
        convs[sid].append({"role":"user","content":msg})

        r = get_groq().chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content":system}
            ] + convs[sid][-20:],
            temperature=0.8,
            max_tokens=1200
        )
        response = r.choices[0].message.content

        # Multi-modelo para preguntas complejas
        if use_multi and len(msg) > 30:
            response = multi_model_query(msg, response)

        convs[sid].append({
            "role":"assistant",
            "content":response
        })

        # Guardar en memoria
        extract_and_save_memory(sid, msg, response)

        return jsonify({
            "response": response,
            "model_used": model,
            "mode": mode_label,
            "web_search": web_used,
            "memory_active": bool(sessions_memory.get(sid))
        })

    except Exception as e:
        if convs[sid]:
            convs[sid].pop()
        return jsonify({
            "response":f"Error: {str(e)}"
        }), 500

@app.route("/search", methods=["POST"])
def search():
    """Búsqueda web directa"""
    query = request.json.get("query","")
    if not query:
        return jsonify({"results":"Sin query"}), 400
    results = web_search(query)
    return jsonify({
        "results": results or "Sin resultados",
        "query": query
    })

@app.route("/memory", methods=["GET"])
def memory():
    """Ver memoria de una sesión"""
    sid = request.args.get("session_id","x")
    return jsonify({
        "memory": sessions_memory.get(sid,{}),
        "messages": len(convs.get(sid,[]))
    })

@app.route("/clear", methods=["POST"])
def clear():
    sid = request.json.get("session_id","x")
    convs[sid] = []
    # Mantener memoria aunque se limpie el chat
    return jsonify({"status":"ok"})

@app.route("/clear_memory", methods=["POST"])
def clear_memory():
    """Limpiar memoria del usuario"""
    sid = request.json.get("session_id","x")
    sessions_memory[sid] = {}
    convs[sid] = []
    return jsonify({"status":"ok","message":"Memoria borrada"})

@app.route("/analyze", methods=["POST"])
def analyze():
    """Analiza texto o documento enviado"""
    data = request.json
    text = data.get("text","")
    task = data.get("task","resume")
    sid  = data.get("session_id","x")

    tasks = {
        "resume":   "Resume este texto en puntos clave:",
        "sentiment":"Analiza el sentimiento y tono de:",
        "improve":  "Mejora y corrige este texto:",
        "translate":"Traduce al inglés:",
        "keywords": "Extrae las palabras clave principales de:",
    }

    prompt = tasks.get(task, tasks["resume"])

    try:
        r = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role":"system","content":SYSTEM_BASE},
                {"role":"user","content":f"{prompt}\n\n{text[:3000]}"}
            ],
            temperature=0.5,
            max_tokens=800
        )
        return jsonify({
            "result": r.choices[0].message.content,
            "task": task,
            "chars_analyzed": len(text)
        })
    except Exception as e:
        return jsonify({"result":f"Error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
