"""
═══════════════════════════════════════════════════════════════════════════
 app_patch.py  ·  DeepNova v6.0 · Parche aditivo para app.py
═══════════════════════════════════════════════════════════════════════════
 ⚠️  IMPORTANTE: este archivo NO se ejecuta solo. Importarlo desde app.py.
 - Añade /api/nova-models, /api/nova-route, /api/stats, /api/plans, /plugins/*
 - 100% aditivo: NO modifica ni borra nada del app.py original
 - Tolerante a fallos: si falla la importación de un módulo, lo omite
═══════════════════════════════════════════════════════════════════════════

INSTRUCCIONES DE USO  (añadir 2 líneas al final de tu app.py, antes del
__main__):

    # ═════════════════════════ DeepNova v6.0 ═════════════════════════
    try:
        from app_patch import register_v6
        register_v6(app)
    except Exception as _e:
        print(f"[v6] no disponible: {_e}")
"""
from __future__ import annotations
import logging, time

logger = logging.getLogger("deepnova.v6")


def register_v6(app) -> None:
    """Registra todos los endpoints v6 en la app Flask existente."""
    from flask import jsonify, request

    # ─────────── nova_models (modelos + routing) ───────────
    try:
        from nova_models import (
            get_model_list, safe_get_model, route_model,
            detect_intent, validate_model_id, NOVA_MODELS,
        )

        @app.route("/api/nova-models", methods=["GET"])
        def _v6_nova_models():
            return jsonify({"models": get_model_list(), "count": len(NOVA_MODELS)})

        @app.route("/api/nova-route", methods=["POST"])
        def _v6_nova_route():
            data = request.get_json(silent=True) or {}
            prompt = (data.get("prompt") or data.get("message") or "").strip()
            if not prompt:
                return jsonify({"error": "prompt requerido"}), 400
            m = route_model(prompt)
            return jsonify({
                "intent":   detect_intent(prompt),
                "model_id": m["id"],
                "name":     m["name"],
                "emoji":    m["emoji"],
            })

        @app.route("/api/nova-validate", methods=["POST"])
        def _v6_nova_validate():
            data = request.get_json(silent=True) or {}
            mid = data.get("model_id")
            return jsonify({"valid": validate_model_id(mid), "model_id": mid})

        logger.info("[v6] ✓ /api/nova-models /api/nova-route /api/nova-validate")
    except Exception as e:
        logger.warning("[v6] nova_models no disponible: %s", e)

    # ─────────── analytics ───────────
    try:
        import analytics

        @app.route("/api/stats", methods=["GET"])
        def _v6_stats():
            return jsonify(analytics.stats())

        logger.info("[v6] ✓ /api/stats")
    except Exception as e:
        logger.warning("[v6] analytics no disponible: %s", e)

    # ─────────── roles / plans ───────────
    try:
        from roles import list_plans, get_plan, can_use_model, has_feature

        @app.route("/api/plans", methods=["GET"])
        def _v6_plans():
            return jsonify({"plans": list_plans()})

        @app.route("/api/plan/check", methods=["POST"])
        def _v6_plan_check():
            data = request.get_json(silent=True) or {}
            plan = data.get("plan", "free")
            model = data.get("model_id")
            feat = data.get("feature")
            res = {"plan": plan, "ok_model": None, "ok_feature": None}
            if model:
                res["ok_model"] = can_use_model(plan, model)
            if feat:
                res["ok_feature"] = has_feature(plan, feat)
            return jsonify(res)

        logger.info("[v6] ✓ /api/plans /api/plan/check")
    except Exception as e:
        logger.warning("[v6] roles no disponible: %s", e)

    # ─────────── cost control ───────────
    try:
        from cost_control import get_summary, total_cost

        @app.route("/api/cost", methods=["GET"])
        def _v6_cost():
            return jsonify({"by_model": get_summary(), "total_usd": total_cost()})

        logger.info("[v6] ✓ /api/cost")
    except Exception as e:
        logger.warning("[v6] cost_control no disponible: %s", e)

    # ─────────── cache stats ───────────
    try:
        from cache import response_cache

        @app.route("/api/cache/stats", methods=["GET"])
        def _v6_cache_stats():
            return jsonify(response_cache.stats())

        @app.route("/api/cache/clear", methods=["POST"])
        def _v6_cache_clear():
            response_cache.clear()
            return jsonify({"ok": True})

        logger.info("[v6] ✓ /api/cache/*")
    except Exception as e:
        logger.warning("[v6] cache no disponible: %s", e)

    # ─────────── plugins (Blueprint) ───────────
    try:
        from plugins import make_blueprint
        app.register_blueprint(make_blueprint())
        logger.info("[v6] ✓ /plugins/* (blueprint)")
    except Exception as e:
        logger.warning("[v6] plugins no disponible: %s", e)

    # ─────────── PWA: manifest + service worker ───────────
    try:
        from flask import send_from_directory
        import os

        @app.route("/manifest.json")
        def _v6_manifest():
            return send_from_directory(os.getcwd(), "manifest.json", mimetype="application/json")

        @app.route("/service-worker.js")
        def _v6_sw():
            return send_from_directory(os.getcwd(), "service-worker.js", mimetype="application/javascript")

        logger.info("[v6] ✓ /manifest.json /service-worker.js")
    except Exception as e:
        logger.warning("[v6] PWA no disponible: %s", e)

    logger.info("🚀 DeepNova v6.0 patch registrado")
