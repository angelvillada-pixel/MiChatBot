# ══════════════════════════════════════════════════════════════════════
# 🆕 DEEPNOVA v2-FRONTEND · Ruta /v2 con UI premium fusionada
# ──────────────────────────────────────────────────────────────────────
# 100 % aditivo · NO toca rutas existentes · NO modifica /chat ni /
# Sirve un frontend modular (HTML/CSS/JS separado) que consume los
# mismos endpoints del backend Deep Nova ya en producción.
#
# Uso (en app.py, una sola línea al final del bootstrapping):
#
#     try:
#         from v2_frontend import register_v2_frontend
#         register_v2_frontend(app)
#         logger.info("✓ DeepNova /v2 frontend registrado")
#     except Exception as _e_v2f:
#         logger.warning("[v2-frontend] no disponible: %s", _e_v2f)
#
# Patrón: idéntico al de register_v6 / register_v7 ya existentes.
# ══════════════════════════════════════════════════════════════════════

import os
import mimetypes
from flask import Blueprint, send_from_directory, abort, make_response

# Carpeta donde viven los assets del nuevo frontend
_HERE = os.path.dirname(os.path.abspath(__file__))
_V2_DIR = os.path.join(_HERE, "static", "v2")

v2_bp = Blueprint("deepnova_v2_frontend", __name__)


def _safe_join(base: str, filename: str) -> str:
    """Evita path traversal."""
    full = os.path.normpath(os.path.join(base, filename))
    if not full.startswith(os.path.normpath(base)):
        abort(403)
    return full


# ────────────────────────────────────────────────────────────────────
# Página principal del frontend v2
# ────────────────────────────────────────────────────────────────────
@v2_bp.route("/v2")
@v2_bp.route("/v2/")
def v2_home():
    """Sirve el index.html del nuevo frontend premium."""
    index_path = os.path.join(_V2_DIR, "index.html")
    if not os.path.exists(index_path):
        return (
            "<h1>DeepNova /v2</h1>"
            "<p>El frontend v2 no está instalado. "
            "Asegúrate de copiar la carpeta <code>static/v2/</code>.</p>"
        ), 404
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    resp.headers["X-Frontend"] = "DeepNova-v2-premium"
    return resp


# ────────────────────────────────────────────────────────────────────
# Assets estáticos de /v2 (CSS, JS, imágenes propias)
# ────────────────────────────────────────────────────────────────────
@v2_bp.route("/v2/static/<path:filename>")
def v2_static(filename):
    """Sirve los archivos estáticos del frontend v2 (css, js, etc.)."""
    full_path = _safe_join(_V2_DIR, filename)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        abort(404)

    # Cache largo para assets, salvo el HTML
    mime, _ = mimetypes.guess_type(full_path)
    resp = send_from_directory(_V2_DIR, filename)
    if mime:
        resp.headers["Content-Type"] = mime
    if filename.endswith(".html"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    else:
        resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# ────────────────────────────────────────────────────────────────────
# Información sobre /v2 (debug / health)
# ────────────────────────────────────────────────────────────────────
@v2_bp.route("/v2/info")
def v2_info():
    from flask import jsonify
    files = []
    if os.path.isdir(_V2_DIR):
        for f in sorted(os.listdir(_V2_DIR)):
            full = os.path.join(_V2_DIR, f)
            if os.path.isfile(full):
                files.append({"name": f, "size": os.path.getsize(full)})
    return jsonify({
        "frontend": "DeepNova v2 Premium",
        "path": "/v2",
        "static_dir": _V2_DIR,
        "files": files,
        "available": os.path.exists(os.path.join(_V2_DIR, "index.html")),
    })


# ────────────────────────────────────────────────────────────────────
# Registro público (idéntico patrón a register_v6 / register_v7)
# ────────────────────────────────────────────────────────────────────
def register_v2_frontend(app):
    """Registra el blueprint /v2 en la app Flask de DeepNova.

    Esta función es 100 % idempotente: si ya está registrado, no falla.
    """
    if "deepnova_v2_frontend" in app.blueprints:
        return  # ya registrado
    app.register_blueprint(v2_bp)
    return app
