"""
═══════════════════════════════════════════════════════════════════════════
 improvements_patch.py · DeepNova v7.0 · Mejoras IA (PATCH ADITIVO)
═══════════════════════════════════════════════════════════════════════════
 Registra los nuevos endpoints y capacidades en la app Flask existente.

 INSTRUCCIONES DE USO (UNA sola línea en app.py, antes del __main__):

     try:
         from improvements_patch import register_v7
         register_v7(
             app,
             llm_call=_llm_call,
             fast_llm=_fast_llm,
             base_system=SYSTEM_BASE_EXTENDED,
             memory_getter=get_memory_prompt,
         )
     except Exception as _e_v7:
         logger.warning("[v7] mejoras IA no disponibles: %s", _e_v7)

 100% aditivo · cero dependencias nuevas obligatorias.

 Áreas cubiertas (TODAS las del documento de mejoras del usuario):
   ✓ 1. Aprendizaje continuo (learning_engine + feedback_loop)
   ✓ 2. Interacción con el usuario (feedback adaptativo)
   ✓ 3. Razonamiento (multi_hop_reasoner + domain_knowledge)
   ✓ 4. Automatización y optimización (code_optimizer + task_automator)
   ✓ 5. Colaboración e integración (agent_swarm + dev_tools_integration)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("deepnova.v7")


def register_v7(
    app,
    *,
    llm_call: Optional[Callable] = None,
    fast_llm: Optional[Callable] = None,
    base_system: str = "",
    memory_getter: Optional[Callable] = None,
) -> None:
    """Registra todos los endpoints de mejoras v7 en la Flask app."""
    from flask import jsonify, request, send_file
    import io
    import json

    # ════════════════════════════════════════════════════════════════
    #  1) APRENDIZAJE CONTINUO  +  FEEDBACK
    # ════════════════════════════════════════════════════════════════
    try:
        import learning_engine as _le
        import feedback_loop as _fl

        @app.route("/api/feedback/learn", methods=["POST"])
        def _v7_feedback_learn():
            d = request.get_json(silent=True) or {}
            uid = (d.get("user_id") or d.get("sid") or "anon").strip()
            try:
                vote = int(d.get("vote", 0))
            except Exception:
                vote = 0
            res = _fl.submit_feedback(
                user_id=uid,
                vote=vote,
                signal=d.get("signal", "thumb"),
                comment=d.get("comment", ""),
                prompt=d.get("prompt"),
                response=d.get("response"),
            )
            return jsonify(res)

        @app.route("/api/feedback/stats", methods=["GET"])
        def _v7_feedback_stats():
            return jsonify(_fl.feedback_stats())

        @app.route("/api/feedback/copied", methods=["POST"])
        def _v7_signal_copied():
            d = request.get_json(silent=True) or {}
            return jsonify(_fl.signal_copied((d.get("user_id") or "anon").strip()))

        @app.route("/api/feedback/regenerated", methods=["POST"])
        def _v7_signal_regen():
            d = request.get_json(silent=True) or {}
            return jsonify(_fl.signal_regenerated((d.get("user_id") or "anon").strip()))

        @app.route("/api/learning/preferences", methods=["GET"])
        def _v7_user_prefs():
            uid = (request.args.get("user_id") or "anon").strip()
            return jsonify({"user_id": uid, "preferences": _le.get_user_preferences(uid)})

        @app.route("/api/learning/top-patterns", methods=["GET"])
        def _v7_top_patterns():
            try:
                n = int(request.args.get("n", 10))
            except Exception:
                n = 10
            return jsonify({"patterns": _le.top_successful_patterns(n)})

        @app.route("/api/learning/stats", methods=["GET"])
        def _v7_learning_stats():
            return jsonify(_le.stats())

        logger.info("[v7] ✓ /api/feedback/* /api/learning/*")
    except Exception as e:
        logger.warning("[v7] learning/feedback no disponible: %s", e)

    # ════════════════════════════════════════════════════════════════
    #  2) RAZONAMIENTO MULTI-SALTO + DOMINIO
    # ════════════════════════════════════════════════════════════════
    try:
        import multi_hop_reasoner as _mhr
        import domain_knowledge as _dk

        @app.route("/api/reason/multihop", methods=["POST"])
        def _v7_reason_multihop():
            if llm_call is None:
                return jsonify({"error": "llm_call no inyectado"}), 500
            d = request.get_json(silent=True) or {}
            query = (d.get("query") or d.get("message") or "").strip()
            if not query:
                return jsonify({"error": "query requerido"}), 400

            uid = (d.get("user_id") or d.get("sid") or "anon").strip()
            domain_ctx = _dk.get_domain_context(query, max_domains=2)

            mem = memory_getter(uid) if memory_getter else ""
            sys = (base_system or "") + ("\n\n" + mem if mem else "")

            result = _mhr.reason(
                query=query,
                llm_call=llm_call,
                fast_llm=fast_llm,
                base_system=sys,
                domain_context=domain_ctx,
                max_depth=int(d.get("max_depth", 3)),
                max_branches=int(d.get("max_branches", 3)),
            )
            return jsonify(result)

        @app.route("/api/domain/detect", methods=["POST"])
        def _v7_domain_detect():
            d = request.get_json(silent=True) or {}
            text = (d.get("text") or "").strip()
            return jsonify({
                "detected": _dk.detect_domains(text, max_domains=3),
                "explain": _dk.explain_detection(text),
                "context_preview": _dk.get_domain_context(text)[:1000],
            })

        @app.route("/api/domain/list", methods=["GET"])
        def _v7_domain_list():
            return jsonify({"domains": _dk.list_domains()})

        logger.info("[v7] ✓ /api/reason/multihop /api/domain/*")
    except Exception as e:
        logger.warning("[v7] razonamiento avanzado no disponible: %s", e)

    # ════════════════════════════════════════════════════════════════
    #  3) OPTIMIZADOR DE CÓDIGO
    # ════════════════════════════════════════════════════════════════
    try:
        import code_optimizer as _co

        @app.route("/api/code/analyze", methods=["POST"])
        def _v7_code_analyze():
            d = request.get_json(silent=True) or {}
            code = d.get("code") or ""
            if not code:
                return jsonify({"error": "code requerido"}), 400
            report = _co.analyze(code)
            if d.get("markdown"):
                report["markdown"] = _co.to_markdown(report)
            return jsonify(report)

        logger.info("[v7] ✓ /api/code/analyze")
    except Exception as e:
        logger.warning("[v7] code_optimizer no disponible: %s", e)

    # ════════════════════════════════════════════════════════════════
    #  4) AUTOMATIZACIÓN DE TAREAS (MACROS)
    # ════════════════════════════════════════════════════════════════
    try:
        import task_automator as _ta

        @app.route("/api/macros", methods=["GET"])
        def _v7_macros_list():
            owner = request.args.get("owner")
            return jsonify({"macros": _ta.list_macros(owner=owner)})

        @app.route("/api/macros", methods=["POST"])
        def _v7_macros_create():
            d = request.get_json(silent=True) or {}
            return jsonify(_ta.save_macro(
                name=d.get("name", ""),
                pattern=d.get("pattern", ""),
                params=d.get("params", []) or [],
                owner=d.get("owner"),
            ))

        @app.route("/api/macros/run", methods=["POST"])
        def _v7_macros_run():
            d = request.get_json(silent=True) or {}
            return jsonify(_ta.run_macro(d.get("name", ""), d.get("args", []) or []))

        @app.route("/api/macros/<name>", methods=["DELETE"])
        def _v7_macros_delete(name):
            return jsonify({"ok": _ta.delete_macro(name)})

        @app.route("/api/macros/track", methods=["POST"])
        def _v7_macros_track():
            d = request.get_json(silent=True) or {}
            sug = _ta.track(
                user_id=(d.get("user_id") or "anon").strip(),
                prompt=(d.get("prompt") or "").strip(),
            )
            return jsonify({"suggestion": sug})

        @app.route("/api/macros/stats", methods=["GET"])
        def _v7_macros_stats():
            return jsonify(_ta.stats())

        logger.info("[v7] ✓ /api/macros/*")
    except Exception as e:
        logger.warning("[v7] task_automator no disponible: %s", e)

    # ════════════════════════════════════════════════════════════════
    #  5) AGENT SWARM (multi-agente coordinado)
    # ════════════════════════════════════════════════════════════════
    try:
        import agent_swarm as _swarm

        @app.route("/api/swarm/run", methods=["POST"])
        def _v7_swarm_run():
            if llm_call is None:
                return jsonify({"error": "llm_call no inyectado"}), 500
            d = request.get_json(silent=True) or {}
            task = (d.get("task") or d.get("query") or "").strip()
            if not task:
                return jsonify({"error": "task requerido"}), 400
            roles = d.get("roles")  # optional list
            result = _swarm.run_swarm(
                task=task,
                llm_call=llm_call,
                roles=roles,
                base_system=base_system,
                parallel=bool(d.get("parallel", True)),
                context=d.get("context", ""),
            )
            if d.get("include_trace"):
                result["trace_md"] = _swarm.trace_to_markdown(result["trace"])
            return jsonify(result)

        @app.route("/api/swarm/roles", methods=["GET"])
        def _v7_swarm_roles():
            return jsonify({
                "roles": [
                    {"key": k, "name": v["name"], "system": v["system"]}
                    for k, v in _swarm.AGENT_ROLES.items()
                ]
            })

        @app.route("/api/swarm/choose", methods=["POST"])
        def _v7_swarm_choose():
            d = request.get_json(silent=True) or {}
            return jsonify({"roles": _swarm.choose_roles(d.get("task", ""))})

        logger.info("[v7] ✓ /api/swarm/*")
    except Exception as e:
        logger.warning("[v7] agent_swarm no disponible: %s", e)

    # ════════════════════════════════════════════════════════════════
    #  6) DEV TOOLS (GitHub, Notebook, Snippets)
    # ════════════════════════════════════════════════════════════════
    try:
        import dev_tools_integration as _dev

        @app.route("/api/github/repo", methods=["GET"])
        def _v7_gh_repo():
            owner = request.args.get("owner", "").strip()
            repo = request.args.get("repo", "").strip()
            if not owner or not repo:
                return jsonify({"error": "owner y repo requeridos"}), 400
            return jsonify(_dev.github_repo_info(owner, repo))

        @app.route("/api/github/search", methods=["GET"])
        def _v7_gh_search():
            q = request.args.get("q", "").strip()
            try:
                n = int(request.args.get("max", 5))
            except Exception:
                n = 5
            return jsonify({"results": _dev.github_search_repos(q, max_results=n)})

        @app.route("/api/github/readme", methods=["GET"])
        def _v7_gh_readme():
            owner = request.args.get("owner", "").strip()
            repo = request.args.get("repo", "").strip()
            return jsonify({"readme": _dev.github_repo_readme(owner, repo)})

        @app.route("/api/github/issues", methods=["GET"])
        def _v7_gh_issues():
            owner = request.args.get("owner", "").strip()
            repo = request.args.get("repo", "").strip()
            state = request.args.get("state", "open")
            try:
                n = int(request.args.get("max", 10))
            except Exception:
                n = 10
            return jsonify({"issues": _dev.github_list_issues(owner, repo, state, n)})

        @app.route("/api/notebook/export", methods=["POST"])
        def _v7_notebook_export():
            d = request.get_json(silent=True) or {}
            messages = d.get("messages") or []
            title = d.get("title") or "DeepNova export"
            nb = _dev.chat_to_notebook(messages, title=title)
            buf = io.BytesIO(json.dumps(nb, ensure_ascii=False, indent=1).encode("utf-8"))
            buf.seek(0)
            return send_file(buf, mimetype="application/x-ipynb+json",
                             as_attachment=True, download_name="deepnova_export.ipynb")

        @app.route("/api/snippets", methods=["GET"])
        def _v7_snip_list():
            return jsonify({"snippets": _dev.snippet_list()})

        @app.route("/api/snippets", methods=["POST"])
        def _v7_snip_save():
            d = request.get_json(silent=True) or {}
            return jsonify(_dev.snippet_save(
                name=d.get("name", ""),
                code=d.get("code", ""),
                lang=d.get("lang", "python"),
                desc=d.get("desc", ""),
            ))

        @app.route("/api/snippets/<name>", methods=["GET"])
        def _v7_snip_get(name):
            s = _dev.snippet_get(name)
            return jsonify(s or {"error": "not found"}), (200 if s else 404)

        @app.route("/api/snippets/<name>", methods=["DELETE"])
        def _v7_snip_del(name):
            return jsonify({"ok": _dev.snippet_delete(name)})

        logger.info("[v7] ✓ /api/github/* /api/notebook/* /api/snippets/*")
    except Exception as e:
        logger.warning("[v7] dev_tools no disponible: %s", e)

    # ════════════════════════════════════════════════════════════════
    #  7) Endpoint maestro: detección automática + routing inteligente
    # ════════════════════════════════════════════════════════════════
    try:
        import domain_knowledge as _dk
        import task_automator as _ta
        import learning_engine as _le

        @app.route("/api/smart/route", methods=["POST"])
        def _v7_smart_route():
            """Recibe un mensaje y devuelve la mejor ruta de resolución:
            'simple', 'multihop', 'swarm', 'macro', 'code_analysis'."""
            d = request.get_json(silent=True) or {}
            msg = (d.get("message") or d.get("query") or "").strip()
            uid = (d.get("user_id") or "anon").strip()
            if not msg:
                return jsonify({"error": "message requerido"}), 400

            # 1) ¿comando macro?
            cmd = _ta.parse_command(msg, owner=uid)
            if cmd:
                return jsonify({"route": "macro", "command": cmd})

            # 2) ¿pide análisis de código?
            low = msg.lower()
            looks_like_code = "```" in msg or any(k in low for k in
                ["analiza este código", "revisa el código", "optimiza esta función",
                 "detecta bugs en", "audita este script"])
            if looks_like_code:
                return jsonify({"route": "code_analysis"})

            # 3) ¿requiere swarm?
            if any(k in low for k in
                ["proyecto completo", "crea una aplicación", "construye un sistema",
                 "diseña e implementa", "investiga, diseña y", "swarm", "equipo"]):
                return jsonify({
                    "route": "swarm",
                    "domains": _dk.detect_domains(msg, max_domains=2),
                })

            # 4) ¿tarea compleja → multihop?
            words = len(msg.split())
            if words > 35 or any(k in low for k in
                ["paso a paso", "compara", "razona", "analiza profundamente",
                 "explica por qué", "qué pasaría si"]):
                return jsonify({
                    "route": "multihop",
                    "domains": _dk.detect_domains(msg, max_domains=2),
                    "score": _le.get_pattern_score(msg),
                })

            # 5) Por defecto: simple (chat normal)
            return jsonify({
                "route": "simple",
                "domains": _dk.detect_domains(msg, max_domains=1),
                "score": _le.get_pattern_score(msg),
            })

        logger.info("[v7] ✓ /api/smart/route")
    except Exception as e:
        logger.warning("[v7] smart routing no disponible: %s", e)

    # ════════════════════════════════════════════════════════════════
    #  8) Health combinado para verificar el patch v7
    # ════════════════════════════════════════════════════════════════
    @app.route("/api/v7/health", methods=["GET"])
    def _v7_health():
        modules = {}
        for mod in ["learning_engine", "feedback_loop", "multi_hop_reasoner",
                    "domain_knowledge", "code_optimizer", "task_automator",
                    "agent_swarm", "dev_tools_integration"]:
            try:
                __import__(mod)
                modules[mod] = "ok"
            except Exception as ex:
                modules[mod] = f"error: {ex}"
        return jsonify({
            "version": "7.0-mejoras-ia",
            "modules": modules,
            "all_ok": all(v == "ok" for v in modules.values()),
        })

    logger.info("🧠 DeepNova v7.0 (mejoras IA) registradas correctamente.")
