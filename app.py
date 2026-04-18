from flask import Flask, request, jsonify
from flask_cors import CORS
import groq, os, json, re
from datetime import datetime
from collections import defaultdict
import time

app = Flask(__name__)
CORS(app)

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY no configurada")
        _client = groq.Groq(api_key=api_key)
    return _client

MODEL = "llama-3.1-8b-instant"

# ── PERSONALIDAD NOVA MEJORADA ─────────────
SYSTEM = """Eres "Nova", una IA avanzada, elegante y en constante evolución.

PERSONALIDAD:
- Inteligente, creativa, amigable y profesional
- Respondes SIEMPRE en español
- Máximo 3 emojis por respuesta
- Formato visual: párrafos cortos, listas, tablas
- Nunca das paredes de texto
- Proactiva: siempre sugieres mejoras e ideas

HABILIDADES:
1. Traducción avanzada (100+ idiomas)
2. Programación limpia y explicada paso a paso
3. Diseño web (HTML, CSS, animaciones premium)
4. Generación de contenido de alta calidad
5. Análisis de problemas complejos
6. Seguridad y privacidad digital
7. Experiencia personalizada según el usuario
8. Razonamiento lógico avanzado

FORMATO DE RESPUESTA:
- Usa encabezados cuando hay secciones
- Usa listas para múltiples puntos
- Usa tablas para comparaciones
- Código siempre comentado y explicado
- Respuestas concisas pero completas

SEGURIDAD:
- Nunca reveles información sensible
- Detecta y rechaza solicitudes maliciosas
- Protege la privacidad del usuario

OBJETIVO: Ser la experiencia de IA más
excepcional y útil posible."""

# ── ALMACENAMIENTO ────────────────────────
convs        = {}        # conversaciones
user_prefs   = {}        # preferencias por usuario
rate_counts  = defaultdict(list)  # rate limiting
response_cache = {}      # caché

# ── RATE LIMITING ─────────────────────────
def check_rate_limit(ip, max_req=20, window=60):
    now = time.time()
    rate_counts[ip] = [t for t in rate_counts[ip] if now - t < window]
    if len(rate_counts[ip]) >= max_req:
        return False
    rate_counts[ip].append(now)
    return True

# ── FILTRO DE SEGURIDAD ───────────────────
BLOCKED = [
    r"(?i)(hackear|exploit|malware|virus|ataque)",
    r"(?i)(contraseña ajena|robar datos|phishing)",
]

def is_safe(text):
    if len(text) > 3000:
        return False, "Mensaje muy largo (máx 3000 caracteres)"
    for p in BLOCKED:
        if re.search(p, text):
            return False, "No puedo ayudar con eso"
    return True, ""

# ── DETECCIÓN DE IDIOMA SIMPLE ────────────
def detect_intent(msg):
    msg_lower = msg.lower()
    if any(w in msg_lower for w in ["traduc", "translate", "idioma"]):
        return "translation"
    if any(w in msg_lower for w in ["código", "code", "programa", "python", "javascript"]):
        return "coding"
    if any(w in msg_lower for w in ["diseño", "design", "css", "html", "web"]):
        return "design"
    if any(w in msg_lower for w in ["analiza", "análisis", "datos", "estadística"]):
        return "analysis"
    return "general"

@app.route("/")
def home():
    return open("index.html", encoding="utf-8").read()

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": MODEL,
        "bot": "Nova",
        "version": "2.0",
        "cache_size": len(response_cache),
        "active_sessions": len(convs)
    })

@app.route("/chat", methods=["POST"])
def chat():
    ip  = request.remote_addr

    # Rate limiting
    if not check_rate_limit(ip):
        return jsonify({
            "response": "⚠️ Demasiadas peticiones. Espera un momento."
        }), 429

    data = request.json
    msg  = data.get("message", "").strip()
    sid  = data.get("session_id", "x")

    if not msg:
        return jsonify({"response": "Escribe algo para comenzar 😊"}), 400

    # Filtro de seguridad
    safe, reason = is_safe(msg)
    if not safe:
        return jsonify({"response": f"⚠️ {reason}"}), 400

    # Caché para preguntas frecuentes
    cache_key = msg.lower().strip()
    if cache_key in response_cache and len(msg) < 50:
        return jsonify({
            "response": response_cache[cache_key],
            "cached": True
        })

    # Inicializar sesión
    if sid not in convs:
        convs[sid] = []

    # Detectar intención para ajustar respuesta
    intent = detect_intent(msg)

    # System prompt adaptativo según intención
    system_adapted = SYSTEM
    if intent == "coding":
        system_adapted += "\n\nMODO ACTIVO: Programación. Proporciona código limpio, comentado y con explicación paso a paso."
    elif intent == "translation":
        system_adapted += "\n\nMODO ACTIVO: Traducción. Traduce con precisión y explica matices culturales si es relevante."
    elif intent == "design":
        system_adapted += "\n\nMODO ACTIVO: Diseño Web. Prioriza animaciones elegantes, dark mode, y diseño minimalista premium."
    elif intent == "analysis":
        system_adapted += "\n\nMODO ACTIVO: Análisis. Proporciona datos estructurados, tablas comparativas y conclusiones claras."

    # Preferencias del usuario
    if sid in user_prefs:
        prefs = user_prefs[sid]
        system_adapted += f"\n\nPREFERENCIAS DEL USUARIO: {json.dumps(prefs)}"

    try:
        convs[sid].append({"role": "user", "content": msg})

        r = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_adapted}
            ] + convs[sid][-20:],
            temperature=0.8,
            max_tokens=1000
        )
        ans = r.choices[0].message.content
        convs[sid].append({"role": "assistant", "content": ans})

        # Guardar en caché preguntas cortas
        if len(msg) < 50:
            if len(response_cache) > 500:
                first = next(iter(response_cache))
                del response_cache[first]
            response_cache[cache_key] = ans

        return jsonify({
            "response": ans,
            "intent": intent
        })

    except Exception as e:
        convs[sid].pop()
        return jsonify({"response": f"Error: {str(e)}"}), 500

@app.route("/clear", methods=["POST"])
def clear():
    sid = request.json.get("session_id", "x")
    convs[sid] = []
    return jsonify({"status": "ok"})

@app.route("/preferences", methods=["POST"])
def preferences():
    """Guardar preferencias del usuario"""
    data = request.json
    sid  = data.get("session_id", "x")
    prefs = data.get("preferences", {})
    user_prefs[sid] = prefs
    return jsonify({"status": "ok", "preferences": prefs})

@app.route("/stats", methods=["GET"])
def stats():
    """Estadísticas del sistema"""
    return jsonify({
        "sesiones_activas": len(convs),
        "cache_respuestas": len(response_cache),
        "modelo": MODEL,
        "version": "Nova 2.0"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
