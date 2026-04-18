from flask import Flask, request, jsonify
from flask_cors import CORS
import groq, os

app = Flask(__name__)
CORS(app)

client = groq.Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL  = "llama-3.1-8b-instant"
SYSTEM = """Eres un asistente personal inteligente.
Respondes SIEMPRE en español, eres amigable y recuerdas la conversación."""
convs  = {}

@app.route("/")
def home():
    return open("index.html", encoding="utf-8").read()

@app.route("/health")
def health():
    return jsonify({"status":"ok"})

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        msg  = data.get("message","")
        sid  = data.get("session_id","x")
        if not msg:
            return jsonify({"response":"Escribe algo 😊"}), 400
        if sid not in convs:
            convs[sid] = []
        convs[sid].append({"role":"user","content":msg})
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role":"system","content":SYSTEM}]+convs[sid][-20:],
            temperature=0.8,
            max_tokens=500
        )
        ans = r.choices[0].message.content
        convs[sid].append({"role":"assistant","content":ans})
        return jsonify({"response":ans})
    except Exception as e:
        return jsonify({"response":f"Error: {str(e)}"}),500

@app.route("/clear", methods=["POST"])
def clear():
    convs[request.json.get("session_id","x")] = []
    return jsonify({"status":"ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
