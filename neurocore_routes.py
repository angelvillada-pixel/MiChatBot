"""
═══════════════════════════════════════════════════════════════════════════
 NeuroCore-X Routes — Flask Blueprint aditivo
═══════════════════════════════════════════════════════════════════════════
 Añade endpoints sin tocar nada del app.py original:
   • POST /api/ultra           → ULTRA reasoning
   • POST /api/enhance         → Mejora de prompt
   • POST /api/plan            → Planificación de tarea
   • POST /api/image/generate  → Generación de imagen
   • GET  /api/image/models    → Modelos disponibles
   • GET  /api/profile         → Perfil del usuario
   • POST /api/profile         → Actualizar perfil
   • DELETE /api/profile       → Reset perfil
   • GET  /api/neurocore/info  → Metadatos del motor
   • POST /api/neurocore/chat  → Chat con streaming simulado
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from flask import Blueprint, request, jsonify, Response, stream_with_context
import json, time, uuid, os

# Módulos NeuroCore-X (importación suave)
try:
    import neurocore_x as _nx
except Exception as e:
    _nx = None
    print(f"[neurocore-routes] neurocore_x no disponible: {e}")

try:
    import image_gen as _img
except Exception as e:
    _img = None
    print(f"[neurocore-routes] image_gen no disponible: {e}")

try:
    import user_profile as _prof
except Exception as e:
    _prof = None
    print(f"[neurocore-routes] user_profile no disponible: {e}")


neurocore_bp = Blueprint("neurocore", __name__, url_prefix="/api")


def register(app, llm_call=None, fast_llm=None, base_system: str = "", memory_getter=None):
    """
    Registra el blueprint en la app Flask.
    Requiere que `app.py` pase los wrappers de LLM ya creados.
    """
    # Guardar referencias en config para acceso desde endpoints
    app.config["NX_LLM_CALL"]      = llm_call
    app.config["NX_FAST_LLM"]      = fast_llm
    app.config["NX_BASE_SYSTEM"]   = base_system
    app.config["NX_MEMORY_GETTER"] = memory_getter  # callable(sid) -> str

    app.register_blueprint(neurocore_bp)
    return True


# ═══════════════════════════════════════════════════════════════════════
#  ULTRA reasoning
# ═══════════════════════════════════════════════════════════════════════
@neurocore_bp.route("/ultra", methods=["POST"])
def api_ultra():
    from flask import current_app
    if _nx is None:
        return jsonify({"success": False, "error": "NeuroCore-X no disponible"}), 501
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or data.get("message") or "").strip()
    sid   = data.get("session_id") or data.get("sid") or "anon"
    if not query:
        return jsonify({"success": False, "error": "Falta query"}), 400

    llm_call   = current_app.config.get("NX_LLM_CALL")
    fast_llm   = current_app.config.get("NX_FAST_LLM")
    base_sys   = current_app.config.get("NX_BASE_SYSTEM", "")
    memory_get = current_app.config.get("NX_MEMORY_GETTER")

    if llm_call is None:
        return jsonify({"success": False, "error": "LLM no inicializado"}), 500

    # Inyectar perfil
    profile_block = ""
    if _prof is not None:
        try:
            prof = _prof.get_profile(sid)
            profile_block = _prof.profile_to_system_prompt(prof)
        except Exception:
            pass

    memory_ctx = ""
    if callable(memory_get):
        try:
            memory_ctx = memory_get(sid) or ""
        except Exception:
            pass

    try:
        result = _nx.ultra_reason(
            query=query,
            llm_call=llm_call,
            fast_llm=fast_llm,
            base_system=base_sys + profile_block,
            context=data.get("context", ""),
            memory=memory_ctx,
        )
        # No exponer el plan completo a menos que se pida
        include_trace = bool(data.get("trace", False))
        public = {
            "success":    True,
            "answer":     result["answer"],
            "elapsed_ms": result["elapsed_ms"],
            "engine":     result["engine"],
            "mode":       "ultra",
        }
        if include_trace:
            public["plan"]  = result.get("plan")
            public["trace"] = result.get("trace")
        return jsonify(public)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
#  ENHANCE prompt
# ═══════════════════════════════════════════════════════════════════════
@neurocore_bp.route("/enhance", methods=["POST"])
def api_enhance():
    if _nx is None:
        return jsonify({"success": False, "error": "NeuroCore-X no disponible"}), 501
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    mode = data.get("mode", "chat")
    if not msg:
        return jsonify({"success": False, "error": "Falta message"}), 400
    enhanced = _nx.enhance_prompt(msg, mode=mode)
    return jsonify({
        "success":  True,
        "original": msg,
        "enhanced": enhanced,
        "changed":  enhanced != msg,
    })


# ═══════════════════════════════════════════════════════════════════════
#  PLAN task
# ═══════════════════════════════════════════════════════════════════════
@neurocore_bp.route("/plan", methods=["POST"])
def api_plan():
    from flask import current_app
    if _nx is None:
        return jsonify({"success": False, "error": "NeuroCore-X no disponible"}), 501
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"success": False, "error": "Falta query"}), 400
    llm_call = current_app.config.get("NX_LLM_CALL")
    if llm_call is None:
        return jsonify({"success": False, "error": "LLM no inicializado"}), 500
    plan = _nx.plan_task(query, llm_call)
    return jsonify({"success": True, "plan": plan})


# ═══════════════════════════════════════════════════════════════════════
#  IMAGE generation
# ═══════════════════════════════════════════════════════════════════════
@neurocore_bp.route("/image/generate", methods=["POST"])
def api_image_generate():
    if _img is None:
        return jsonify({"success": False, "error": "image_gen no disponible"}), 501
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or data.get("query") or "").strip()
    if not prompt:
        return jsonify({"success": False, "error": "Falta prompt"}), 400
    model     = data.get("model",    "flux")
    style     = data.get("style",    "cinematic")
    provider  = data.get("provider", "auto")
    width     = int(data.get("width",  1024))
    height    = int(data.get("height", 1024))
    seed      = data.get("seed")
    try:
        result = _img.generate_image(
            prompt=prompt, model=model, width=width, height=height,
            style=style, provider=provider, seed=seed
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@neurocore_bp.route("/image/models", methods=["GET"])
def api_image_models():
    if _img is None:
        return jsonify({"success": False, "error": "image_gen no disponible"}), 501
    return jsonify({"success": True, **_img.list_models()})


# ═══════════════════════════════════════════════════════════════════════
#  USER PROFILE
# ═══════════════════════════════════════════════════════════════════════
@neurocore_bp.route("/profile", methods=["GET", "POST", "DELETE"])
def api_profile():
    if _prof is None:
        return jsonify({"success": False, "error": "user_profile no disponible"}), 501
    sid = (request.args.get("sid") or request.args.get("session_id") or "").strip()
    if request.method != "GET":
        data = request.get_json(silent=True) or {}
        sid = (data.get("sid") or data.get("session_id") or sid).strip()
    if not sid:
        sid = "anon"

    if request.method == "GET":
        return jsonify({"success": True, "profile": _prof.get_profile(sid)})
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        updates = data.get("profile") or {k: v for k, v in data.items() if k not in ("sid", "session_id")}
        new_prof = _prof.update_profile(sid, updates)
        return jsonify({"success": True, "profile": new_prof})
    if request.method == "DELETE":
        _prof.reset_profile(sid)
        return jsonify({"success": True, "message": "Perfil reseteado"})


# ═══════════════════════════════════════════════════════════════════════
#  STREAMING chat simulado (SSE)
# ═══════════════════════════════════════════════════════════════════════
@neurocore_bp.route("/neurocore/chat", methods=["POST"])
def api_neurocore_chat():
    from flask import current_app
    data = request.get_json(silent=True) or {}
    query = (data.get("message") or data.get("query") or "").strip()
    sid   = data.get("session_id") or data.get("sid") or "anon"
    ultra = bool(data.get("ultra", False))
    stream = bool(data.get("stream", False))
    if not query:
        return jsonify({"success": False, "error": "Falta message"}), 400

    llm_call = current_app.config.get("NX_LLM_CALL")
    fast_llm = current_app.config.get("NX_FAST_LLM")
    base_sys = current_app.config.get("NX_BASE_SYSTEM", "")
    memory_get = current_app.config.get("NX_MEMORY_GETTER")

    if llm_call is None:
        return jsonify({"success": False, "error": "LLM no inicializado"}), 500

    # Perfil
    profile_block = ""
    if _prof is not None:
        try:
            prof = _prof.get_profile(sid)
            profile_block = _prof.profile_to_system_prompt(prof)
        except Exception:
            pass
    mem = memory_get(sid) if callable(memory_get) else ""

    if ultra and _nx is not None:
        result = _nx.ultra_reason(
            query=query, llm_call=llm_call, fast_llm=fast_llm,
            base_system=base_sys + profile_block,
            context="", memory=mem,
        )
        answer = result["answer"]
        meta = {"engine": result["engine"], "elapsed_ms": result["elapsed_ms"], "mode": "ultra"}
    else:
        enhanced = _nx.enhance_prompt(query) if _nx else query
        system = base_sys + profile_block + "\n\n" + (_nx.NEUROCORE_IDENTITY if _nx else "")
        answer = llm_call(
            [{"role": "system", "content": system[:4000]},
             {"role": "user", "content": enhanced}],
            0.7
        )
        meta = {"engine": "NeuroCore-X standard", "mode": "standard"}

    if not stream:
        return jsonify({"success": True, "answer": answer, **meta})

    # SSE stream — chunking por palabras (simulado, UX ChatGPT-like)
    def gen():
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"
        words = answer.split(" ")
        buf = []
        for i, w in enumerate(words):
            buf.append(w)
            if len(buf) >= 3 or i == len(words) - 1:
                chunk = " ".join(buf) + (" " if i < len(words) - 1 else "")
                yield f"event: token\ndata: {json.dumps({'t': chunk})}\n\n"
                buf = []
                time.sleep(0.015)
        yield f"event: done\ndata: {json.dumps({'ok': True})}\n\n"

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ═══════════════════════════════════════════════════════════════════════
#  INFO / STATUS
# ═══════════════════════════════════════════════════════════════════════
@neurocore_bp.route("/neurocore/info", methods=["GET"])
def api_neurocore_info():
    info = {
        "name":    "NeuroCore-X",
        "version": "1.0.0",
        "parent":  "DeepNova v4 Ultra",
        "ts":      time.time(),
        "modules": {
            "neurocore_x": _nx is not None,
            "image_gen":   _img is not None,
            "user_profile": _prof is not None,
        },
    }
    if _nx is not None:
        info["engine_info"] = _nx.info()
    if _img is not None:
        info["image_providers"] = _img.list_models()
    return jsonify(info)
