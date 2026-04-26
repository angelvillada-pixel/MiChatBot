"""
═══════════════════════════════════════════════════════════════════════════
 plugins.py  ·  DeepNova v6.0 · Sistema de Plugins Externos
═══════════════════════════════════════════════════════════════════════════
 ✔ Registro dinámico de plugins (fn callables)
 ✔ Plugins built-in: weather, crypto, time
 ✔ Endpoints Flask listos para usar (Blueprint)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Callable, Dict, Any
import logging, time

logger = logging.getLogger("plugins")

PLUGINS: Dict[str, Callable[..., Any]] = {}


def register_plugin(name: str, fn: Callable[..., Any]) -> None:
    PLUGINS[name] = fn
    logger.info("[plugins] ✓ registrado: %s", name)


def run_plugin(name: str, *args, **kwargs) -> Any:
    if name not in PLUGINS:
        raise KeyError(f"Plugin '{name}' no registrado")
    return PLUGINS[name](*args, **kwargs)


def list_plugins() -> list:
    return sorted(PLUGINS.keys())


# ───────────────── PLUGINS BUILT-IN ─────────────────
def _weather(city: str) -> dict:
    import requests
    r = requests.get(f"https://wttr.in/{city}?format=j1", timeout=10)
    r.raise_for_status()
    data = r.json()
    cur = (data.get("current_condition") or [{}])[0]
    return {
        "city":    city,
        "temp_c":  cur.get("temp_C"),
        "feels_c": cur.get("FeelsLikeC"),
        "desc":    (cur.get("weatherDesc") or [{}])[0].get("value"),
        "humidity": cur.get("humidity"),
    }


def _crypto(coin: str = "bitcoin", vs: str = "usd") -> dict:
    import requests
    r = requests.get(
        f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies={vs}",
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _time_utc() -> dict:
    return {"utc_epoch": int(time.time()), "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# Auto-registro
register_plugin("weather", _weather)
register_plugin("crypto",  _crypto)
register_plugin("time",    _time_utc)


# ───────────────── BLUEPRINT FLASK ─────────────────
def make_blueprint():
    """Devuelve un Blueprint Flask con endpoints /plugins/*"""
    from flask import Blueprint, jsonify, request
    bp = Blueprint("plugins", __name__, url_prefix="/plugins")

    @bp.route("/list", methods=["GET"])
    def _list():
        return jsonify({"plugins": list_plugins()})

    @bp.route("/run/<name>", methods=["GET", "POST"])
    def _run(name):
        try:
            params = request.get_json(silent=True) or request.args.to_dict()
            result = run_plugin(name, **params) if params else run_plugin(name)
            return jsonify({"ok": True, "plugin": name, "result": result})
        except KeyError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500

    return bp
