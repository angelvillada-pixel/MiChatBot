from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import groq, os, re, time, json, requests, base64
from collections import defaultdict
from datetime import datetime
import io

app = Flask(__name__)
CORS(app)

# ── CLIENTE GROQ ──────────────────────────
_client = None
def get_groq():
    global _client
    if _client is None:
        _client = groq.Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client

# ── MODELOS ACTUALIZADOS 2025 ─────────────
MODELS = {
    "fast":   "llama-3.1-8b-instant",
    "smart":  "llama-3.3-70b-versatile",
    "reason": "deepseek-r1-distill-llama-70b",
    "creative":"llama-3.1-70b-versatile",  # reemplaza mixtral
    "vision": "llama-3.2-11b-vision-preview", # para imágenes
}

# ── PERSONALIDAD NOVA 4.0 ─────────────────
SYSTEM_BASE = """Eres "Nova 4.0", la IA más avanzada y útil.

IDENTIDAD:
- Nombre: Nova 4.0
- Multi-modelo, memoria permanente, agente autónomo
- Siempre en español (o el idioma del usuario)
- Máximo 3 emojis por respuesta
- Formato visual claro y organizado
- Proactiva: siempre sugiere mejoras

CAPACIDADES:
1. Multi-modelo (4 IAs especializadas)
2. Memoria permanente entre sesiones
3. Búsqueda web en tiempo real
4. Análisis de imágenes y documentos
5. Modo debate entre modelos
6. Agente autónomo (tareas complejas)
7. Detector de idioma automático
8. Comandos rápidos (/traducir, /resumir, etc.)

COMANDOS QUE RECONOCES:
/traducir [texto] → traduce al inglés
/resumir [texto]  → resume el texto
/codigo [lang]    → genera código
/buscar [tema]    → busca en web
/debate [tema]    → inicia debate entre IAs
/tareas           → muestra lista de tareas
/analizar [texto] → analiza el texto

AGENTE AUTÓNOMO:
Cuando una tarea es compleja, la divides en
pasos y los ejecutas uno por uno mostrando
tu razonamiento en cada paso.

DETECTOR DE IDIOMA:
Detectas el idioma del usuario y respondes
en el mismo idioma automáticamente."""

# ══════════════════════════════════════════
# MEMORIA PERMANENTE (archivo JSON)
# ══════════════════════════════════════════
MEMORY_FILE = "nova_memory.json"
HISTORY_FILE = "nova_history.json"

def load_json(filename):
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}

def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

# Cargar memoria y historial al iniciar
permanent_memory = load_json(MEMORY_FILE)
conversation_history = load_json(HISTORY_FILE)

def save_memory(sid, key, value):
    if sid not in permanent_memory:
        permanent_memory[sid] = {}
    permanent_memory[sid][key] = value
    permanent_memory[sid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json(MEMORY_FILE, permanent_memory)

def get_memory(sid):
    return permanent_memory.get(sid, {})

def save_to_history(sid, msg, response, model):
    if sid not in conversation_history:
        conversation_history[sid] = []
    conversation_history[sid].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": msg,
        "nova": response,
        "model": model
    })
    # Máximo 200 mensajes por usuario
    if len(conversation_history[sid]) > 200:
        conversation_history[sid] = conversation_history[sid][-200:]
    save_json(HISTORY_FILE, conversation_history)

def extract_memory(sid, msg):
    """Extrae y guarda info importante del mensaje"""
    msg_lower = msg.lower()
    # Nombre
    for trigger in ["me llamo","mi nombre es","soy "]:
        if trigger in msg_lower:
            words = msg.split()
            for i,w in enumerate(words):
                if w.lower() in ["llamo","es","soy"] and i+1<len(words):
                    save_memory(sid,"nombre",words[i+1].strip(".,!?"))
                    break
    # Profesión
    for trigger in ["trabajo como","soy desarrollador","soy diseñador",
                    "soy estudiante","trabajo en","mi profesión"]:
        if trigger in msg_lower:
            save_memory(sid,"profesion",msg[:100])
    # Preferencias
    if "me gusta" in msg_lower or "prefiero" in msg_lower:
        save_memory(sid,"preferencia",msg[:120])

def get_memory_prompt(sid):
    mem = get_memory(sid)
    if not mem:
        return ""
    lines = ["\n\nLO QUE SÉ DEL USUARIO:"]
    for k,v in mem.items():
        if k != "last_seen":
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)

# ══════════════════════════════════════════
# SESIONES Y RATE LIMIT
# ══════════════════════════════════════════
convs = {}
rate_counts = defaultdict(list)
tasks_store = {}  # tareas por usuario

def check_rate(ip, max_r=30, win=60):
    now = time.time()
    rate_counts[ip] = [t for t in rate_counts[ip] if now-t<win]
    if len(rate_counts[ip]) >= max_r:
        return False
    rate_counts[ip].append(now)
    return True

BLOCKED = [
    r"(?i)(hackear sistema real|exploit real|malware real)",
]
def is_safe(text):
    if len(text) > 6000:
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
            params={"q":query,"format":"json",
                    "no_html":"1","skip_disambig":"1"},
            timeout=5
        )
        data = r.json()
        results = []
        if data.get("AbstractText"):
            results.append(f"📌 {data['AbstractText'][:400]}")
        for item in data.get("RelatedTopics",[])[:3]:
            if isinstance(item,dict) and item.get("Text"):
                results.append(f"• {item['Text'][:200]}")
        return "\n".join(results) if results else None
    except:
        return None

def needs_search(msg):
    triggers = ["busca","buscar","qué es","quién es","cuándo",
                "noticias","hoy","precio","clima","último",
                "reciente","2024","2025","actualidad","/buscar"]
    return any(t in msg.lower() for t in triggers)

# ══════════════════════════════════════════
# DETECTOR DE IDIOMA
# ══════════════════════════════════════════
def detect_language(text):
    """Detecta idioma simple por palabras comunes"""
    text_lower = text.lower()
    langs = {
        "español": ["hola","cómo","qué","para","con","una","gracias"],
        "english": ["hello","how","what","for","with","the","thanks","please"],
        "português": ["olá","como","para","obrigado","você","uma"],
        "français": ["bonjour","comment","pour","avec","merci","vous"],
        "deutsch": ["hallo","wie","für","mit","danke","sind"],
        "italiano": ["ciao","come","per","con","grazie","sono"],
    }
    scores = {lang:0 for lang in langs}
    for lang, words in langs.items():
        for word in words:
            if word in text_lower:
                scores[lang] += 1
    detected = max(scores, key=scores.get)
    return detected if scores[detected] > 0 else "español"

def get_lang_instruction(lang):
    instructions = {
        "english": "Respond in English.",
        "português": "Responda em português.",
        "français": "Répondez en français.",
        "deutsch": "Antworten Sie auf Deutsch.",
        "italiano": "Rispondi in italiano.",
        "español": "Responde en español.",
    }
    return instructions.get(lang, "Responde en español.")

# ══════════════════════════════════════════
# SELECCIÓN DE MODELO
# ══════════════════════════════════════════
def select_model(msg):
    msg_lower = msg.lower()
    if any(w in msg_lower for w in
        ["analiza","razona","por qué","compara",
         "debería","pros","contras","/debate"]):
        return MODELS["reason"], "DeepSeek R1"
    if any(w in msg_lower for w in
        ["código","code","programa","función",
         "script","bug","python","javascript","css"]):
        return MODELS["smart"], "LLaMA 70B"
    if any(w in msg_lower for w in
        ["crea","imagina","escribe","historia",
         "poema","idea","diseña","inventa","creativo"]):
        return MODELS["creative"], "LLaMA Creative"
    return MODELS["fast"], "LLaMA 3.1"

# ══════════════════════════════════════════
# MODO DEBATE
# ══════════════════════════════════════════
def debate_mode(topic):
    """2 modelos debaten, Nova da veredicto"""
    try:
        # Posición 1: LLaMA 70B
        r1 = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role":"system","content":
                 "Defiende una posición con argumentos sólidos. "
                 "Sé directo y convincente. Máximo 150 palabras."},
                {"role":"user","content":
                 f"Defiende la PRIMERA opción del debate: {topic}"}
            ],
            max_tokens=200, temperature=0.7
        )
        pos1 = r1.choices[0].message.content

        # Posición 2: DeepSeek R1
        r2 = get_groq().chat.completions.create(
            model=MODELS["reason"],
            messages=[
                {"role":"system","content":
                 "Contradice y presenta la posición alternativa "
                 "con argumentos sólidos. Máximo 150 palabras."},
                {"role":"user","content":
                 f"Presenta la posición CONTRARIA del debate: {topic}"}
            ],
            max_tokens=200, temperature=0.7
        )
        pos2 = r2.choices[0].message.content

        # Veredicto: Nova
        r3 = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role":"system","content":
                 "Eres árbitro imparcial. Da un veredicto "
                 "justo y equilibrado. Máximo 100 palabras."},
                {"role":"user","content":
                 f"Debate: {topic}\n\n"
                 f"Posición A: {pos1}\n\n"
                 f"Posición B: {pos2}\n\n"
                 f"Da tu veredicto final:"}
            ],
            max_tokens=150, temperature=0.5
        )
        verdict = r3.choices[0].message.content

        return f"""**🥊 MODO DEBATE: {topic}**

---
**🔵 LLaMA 70B defiende:**
{pos1}

---
**🟡 DeepSeek R1 contradice:**
{pos2}

---
**⚖️ Veredicto de Nova:**
{verdict}"""

    except Exception as e:
        return f"Error en debate: {str(e)}"

# ══════════════════════════════════════════
# AGENTE AUTÓNOMO
# ══════════════════════════════════════════
def autonomous_agent(task, sid):
    """Divide tarea compleja en pasos y ejecuta"""
    try:
        # Paso 1: Planificar
        plan_r = get_groq().chat.completions.create(
            model=MODELS["reason"],
            messages=[
                {"role":"system","content":
                 "Eres un planificador experto. "
                 "Divide la tarea en máximo 4 pasos claros y concisos. "
                 "Formato: 1. Paso uno\n2. Paso dos\netc."},
                {"role":"user","content":
                 f"Planifica cómo resolver: {task}"}
            ],
            max_tokens=300, temperature=0.3
        )
        plan = plan_r.choices[0].message.content

        # Paso 2: Ejecutar
        exec_r = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role":"system","content":SYSTEM_BASE},
                {"role":"user","content":
                 f"Ejecuta este plan paso a paso para: {task}\n\n"
                 f"Plan:\n{plan}\n\n"
                 f"Desarrolla cada paso con detalle y ejemplos."}
            ],
            max_tokens=1000, temperature=0.7
        )
        execution = exec_r.choices[0].message.content

        return f"""**🤖 AGENTE AUTÓNOMO**
*Tarea: {task}*

---
**📋 Plan de acción:**
{plan}

---
**⚙️ Ejecución:**
{execution}"""

    except Exception as e:
        return f"Error en agente: {str(e)}"

# ══════════════════════════════════════════
# ANÁLISIS DE IMÁGENES
# ══════════════════════════════════════════
def analyze_image(image_b64, prompt="Describe esta imagen en detalle"):
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["vision"],
            messages=[{
                "role":"user",
                "content":[
                    {"type":"text","text":prompt},
                    {"type":"image_url","image_url":{
                        "url":f"data:image/jpeg;base64,{image_b64}"
                    }}
                ]
            }],
            max_tokens=800
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"Error analizando imagen: {str(e)}"

# ══════════════════════════════════════════
# COMANDOS RÁPIDOS
# ══════════════════════════════════════════
def process_command(msg, sid):
    """Procesa comandos /comando"""
    msg_strip = msg.strip()

    if msg_strip.startswith("/traducir "):
        text = msg_strip[10:]
        return f"Traducción al inglés:\n\n{text}", True

    if msg_strip.startswith("/resumir "):
        text = msg_strip[9:]
        return None, False  # pasa al chat normal con contexto

    if msg_strip.startswith("/debate "):
        topic = msg_strip[8:]
        return debate_mode(topic), True

    if msg_strip.startswith("/buscar "):
        query = msg_strip[8:]
        result = web_search(query)
        return f"**🌐 Búsqueda: {query}**\n\n{result or 'Sin resultados'}", True

    if msg_strip.startswith("/agente "):
        task = msg_strip[8:]
        return autonomous_agent(task, sid), True

    if msg_strip == "/tareas":
        tasks = tasks_store.get(sid, [])
        if not tasks:
            return "📋 No tienes tareas pendientes.", True
        t_list = "\n".join(
            [f"{'✅' if t['done'] else '⬜'} {i+1}. {t['text']}"
             for i,t in enumerate(tasks)]
        )
        return f"**📋 Tus tareas:**\n\n{t_list}", True

    if msg_strip.startswith("/tarea "):
        task_text = msg_strip[7:]
        if sid not in tasks_store:
            tasks_store[sid] = []
        tasks_store[sid].append({"text":task_text,"done":False})
        return f"✅ Tarea añadida: **{task_text}**", True

    return None, False

# ══════════════════════════════════════════
# MULTI-MODELO (verificación)
# ══════════════════════════════════════════
def multi_verify(msg, primary):
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["reason"],
            messages=[
                {"role":"system","content":
                 "Verifica si la respuesta es correcta y completa. "
                 "Si es perfecta escribe solo 'APROBADO'. "
                 "Si necesita mejora, añade máximo 2 oraciones."},
                {"role":"user","content":
                 f"Pregunta: {msg}\nRespuesta: {primary[:400]}"}
            ],
            max_tokens=150, temperature=0.2
        )
        extra = r.choices[0].message.content
        if "APROBADO" not in extra:
            return primary + "\n\n💡 " + extra
        return primary
    except:
        return primary

# ══════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════

@app.route("/")
def home():
    return open("index.html", encoding="utf-8").read()

@app.route("/health")
def health():
    return jsonify({
        "status":"ok","version":"Nova 4.0",
        "models":list(MODELS.keys()),
        "sessions":len(convs),
        "memories":len(permanent_memory)
    })

@app.route("/chat", methods=["POST"])
def chat():
    ip = request.remote_addr
    if not check_rate(ip):
        return jsonify({"response":"⚠️ Demasiadas peticiones."}),429

    data       = request.json
    msg        = data.get("message","").strip()
    sid        = data.get("session_id","x")
    multi      = data.get("multi_model", False)
    agent_mode = data.get("agent_mode", False)

    if not msg:
        return jsonify({"response":"Escribe algo 😊"}),400
    safe,reason = is_safe(msg)
    if not safe:
        return jsonify({"response":f"⚠️ {reason}"}),400

    # Comandos rápidos
    cmd_result, is_cmd = process_command(msg, sid)
    if is_cmd:
        return jsonify({
            "response":cmd_result,
            "model_used":"Nova Command",
            "mode":"Comando"
        })

    # Modo agente
    if agent_mode or msg.lower().startswith("agente:"):
        task = msg.replace("agente:","").strip()
        result = autonomous_agent(task, sid)
        return jsonify({
            "response":result,
            "model_used":"Multi-Agente",
            "mode":"Agente"
        })

    # Modo debate
    if "/debate" in msg.lower():
        topic = msg.lower().replace("/debate","").strip()
        return jsonify({
            "response":debate_mode(topic),
            "model_used":"Debate Mode",
            "mode":"Debate"
        })

    # Detectar idioma
    lang = detect_language(msg)
    lang_instruction = get_lang_instruction(lang)

    # Búsqueda web
    web_ctx = ""
    web_used = False
    if needs_search(msg):
        results = web_search(msg)
        if results:
            web_ctx = f"\n\nINFO WEB:\n{results}"
            web_used = True

    # Seleccionar modelo
    model, mode_label = select_model(msg)

    # Memoria permanente
    mem_ctx = get_memory_prompt(sid)

    # System final
    system = SYSTEM_BASE + mem_ctx + web_ctx + \
             f"\n\nIDIOMA: {lang_instruction}"

    # Inicializar sesión
    if sid not in convs:
        convs[sid] = []

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

        # Multi-IA
        if multi and len(msg) > 20:
            response = multi_verify(msg, response)

        convs[sid].append({"role":"assistant","content":response})

        # Guardar memoria y historial
        extract_memory(sid, msg)
        save_to_history(sid, msg, response, model)

        return jsonify({
            "response":response,
            "model_used":model,
            "mode":mode_label,
            "web_search":web_used,
            "language":lang,
            "memory_active":bool(get_memory(sid))
        })

    except Exception as e:
        if convs[sid]:
            convs[sid].pop()
        return jsonify({"response":f"Error: {str(e)}"}),500

@app.route("/image", methods=["POST"])
def image():
    """Analiza imagen enviada"""
    data    = request.json
    img_b64 = data.get("image","")
    prompt  = data.get("prompt","Describe esta imagen en detalle en español")
    if not img_b64:
        return jsonify({"result":"Sin imagen"}),400
    result = analyze_image(img_b64, prompt)
    return jsonify({"result":result})

@app.route("/debate", methods=["POST"])
def debate():
    topic = request.json.get("topic","")
    if not topic:
        return jsonify({"result":"Sin tema"}),400
    return jsonify({"result":debate_mode(topic)})

@app.route("/agent", methods=["POST"])
def agent():
    data = request.json
    task = data.get("task","")
    sid  = data.get("session_id","x")
    if not task:
        return jsonify({"result":"Sin tarea"}),400
    return jsonify({"result":autonomous_agent(task,sid)})

@app.route("/tasks", methods=["GET","POST","PUT"])
def tasks():
    sid = request.args.get("session_id") or \
          request.json.get("session_id","x") \
          if request.json else "x"

    if request.method == "GET":
        return jsonify({"tasks":tasks_store.get(sid,[])})

    if request.method == "POST":
        text = request.json.get("text","")
        if sid not in tasks_store:
            tasks_store[sid] = []
        tasks_store[sid].append({"text":text,"done":False})
        return jsonify({"status":"ok","tasks":tasks_store[sid]})

    if request.method == "PUT":
        idx = request.json.get("index",0)
        if sid in tasks_store and idx < len(tasks_store[sid]):
            tasks_store[sid][idx]["done"] = \
                not tasks_store[sid][idx]["done"]
        return jsonify({"tasks":tasks_store.get(sid,[])})

@app.route("/memory", methods=["GET"])
def memory():
    sid = request.args.get("session_id","x")
    return jsonify({
        "memory":get_memory(sid),
        "messages":len(convs.get(sid,[]))
    })

@app.route("/history", methods=["GET"])
def history():
    sid = request.args.get("session_id","x")
    hist = conversation_history.get(sid,[])
    return jsonify({
        "history":hist[-50:],  # últimos 50
        "total":len(hist)
    })

@app.route("/history/export", methods=["GET"])
def export_history():
    """Exporta historial como JSON"""
    sid    = request.args.get("session_id","x")
    fmt    = request.args.get("format","json")
    hist   = conversation_history.get(sid,[])

    if fmt == "txt":
        lines = [f"=== HISTORIAL NOVA 4.0 ===\n"]
        for h in hist:
            lines.append(f"[{h['timestamp']}]")
            lines.append(f"Tú: {h['user']}")
            lines.append(f"Nova: {h['nova']}\n")
        content = "\n".join(lines)
        buf = io.BytesIO(content.encode("utf-8"))
        return send_file(buf,
            mimetype="text/plain",
            as_attachment=True,
            download_name="nova_historial.txt")

    # JSON por defecto
    buf = io.BytesIO(
        json.dumps(hist,ensure_ascii=False,indent=2).encode("utf-8")
    )
    return send_file(buf,
        mimetype="application/json",
        as_attachment=True,
        download_name="nova_historial.json")

@app.route("/analytics", methods=["GET"])
def analytics():
    """Dashboard de analytics"""
    sid = request.args.get("session_id","x")
    hist = conversation_history.get(sid,[])

    # Modelos usados
    model_counts = defaultdict(int)
    for h in hist:
        m = h.get("model","unknown")
        if "8b" in m:    model_counts["LLaMA 3.1"]  += 1
        elif "70b" in m: model_counts["LLaMA 70B"]  += 1
        elif "deep" in m:model_counts["DeepSeek R1"] += 1
        else:            model_counts["Otro"] += 1

    # Horas de uso
    hours = defaultdict(int)
    for h in hist:
        try:
            hour = h["timestamp"].split(" ")[1].split(":")[0]
            hours[hour] += 1
        except:
            pass

    return jsonify({
        "total_messages": len(hist),
        "models_used": dict(model_counts),
        "hours": dict(hours),
        "memory_items": len(get_memory(sid)),
        "active_tasks": len([
            t for t in tasks_store.get(sid,[])
            if not t["done"]
        ])
    })

@app.route("/search", methods=["POST"])
def search():
    query = request.json.get("query","")
    results = web_search(query)
    return jsonify({"results":results or "Sin resultados"})

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    text = data.get("text","")
    task = data.get("task","resume")
    tasks_map = {
        "resume":   "Resume en puntos clave:",
        "sentiment":"Analiza sentimiento y tono:",
        "improve":  "Mejora y corrige:",
        "keywords": "Extrae palabras clave:",
        "translate":"Traduce al inglés:",
    }
    prompt = tasks_map.get(task, tasks_map["resume"])
    try:
        r = get_groq().chat.completions.create(
            model=MODELS["smart"],
            messages=[
                {"role":"system","content":SYSTEM_BASE},
                {"role":"user","content":f"{prompt}\n\n{text[:4000]}"}
            ],
            temperature=0.5, max_tokens=800
        )
        return jsonify({"result":r.choices[0].message.content})
    except Exception as e:
        return jsonify({"result":f"Error: {str(e)}"}),500

@app.route("/clear", methods=["POST"])
def clear():
    sid = request.json.get("session_id","x")
    convs[sid] = []
    return jsonify({"status":"ok"})

@app.route("/clear_memory", methods=["POST"])
def clear_memory():
    sid = request.json.get("session_id","x")
    permanent_memory[sid] = {}
    convs[sid] = []
    save_json(MEMORY_FILE, permanent_memory)
    return jsonify({"status":"ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
