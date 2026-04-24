"""
═══════════════════════════════════════════════════════════════════════
 favicon.py — M7: Generador de identidad visual (SVG → PNG multi-size)
═══════════════════════════════════════════════════════════════════════

Expone rutas Flask para servir:
  /favicon.svg
  /favicon.ico (PNG 32x32 dentro de ICO si cairosvg disponible; si no, SVG)
  /icon-16.png, /icon-32.png, /icon-180.png (Apple), /icon-192.png, /icon-512.png
  /site.webmanifest

Cascada robusta:
  1) cairosvg  → PNG alta calidad
  2) Pillow    → PNG generado desde primitivas (sin SVG real)
  3) Fallback  → sirve directamente el SVG como PNG (content-type svg)

Cache-control: immutable, max-age=31536000.
"""
import io
import os
from flask import Response, jsonify

# ──────────────────────────────────────────────────────────────────────
# Fuente SVG — degradado violeta/índigo con "N" (DeepNova)
# ──────────────────────────────────────────────────────────────────────
FAVICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"  stop-color="#6366f1"/>
      <stop offset="50%" stop-color="#8b5cf6"/>
      <stop offset="100%" stop-color="#06b6d4"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="40%" r="60%">
      <stop offset="0%"  stop-color="#ffffff" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="512" height="512" rx="112" ry="112" fill="url(#g)"/>
  <rect width="512" height="512" rx="112" ry="112" fill="url(#glow)"/>
  <path d="M140 360 V152 h52 l128 168 V152 h52 v208 h-52 L192 192 v168 z"
        fill="#ffffff" fill-opacity="0.97"/>
  <circle cx="388" cy="156" r="18" fill="#ffffff" fill-opacity="0.95"/>
</svg>"""

_SIZES = [16, 32, 180, 192, 512]
_CACHE = {}    # size -> bytes PNG

_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
}

# ──────────────────────────────────────────────────────────────────────
# Renderers (cascada)
# ──────────────────────────────────────────────────────────────────────
def _render_cairosvg(size: int) -> bytes:
    import cairosvg
    return cairosvg.svg2png(
        bytestring=FAVICON_SVG.encode("utf-8"),
        output_width=size, output_height=size,
    )

def _render_pillow(size: int) -> bytes:
    """Renderiza un fallback de calidad aceptable usando primitivas Pillow."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Degradado aproximado manual
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(99  * (1 - t) + 6   * t)
        g = int(102 * (1 - t) + 182 * t)
        b = int(241 * (1 - t) + 212 * t)
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Esquinas redondeadas (máscara)
    from PIL import ImageDraw as D2
    mask = Image.new("L", (size, size), 0)
    d2 = D2.Draw(mask)
    radius = int(size * 0.22)
    d2.rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)

    # "N" estilizada
    d3 = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.58))
    except Exception:
        font = ImageFont.load_default()
    text = "N"
    try:
        bbox = d3.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = int(size * 0.4), int(size * 0.5)
    d3.text(((size - tw) // 2, (size - th) // 2 - int(size * 0.05)),
            text, fill=(255, 255, 255, 245), font=font)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

def _render_svg_bytes() -> bytes:
    return FAVICON_SVG.encode("utf-8")

def render_png(size: int) -> bytes:
    """Devuelve bytes PNG del tamaño pedido. Usa cascada cairosvg → pillow."""
    if size in _CACHE:
        return _CACHE[size]
    for renderer in (_render_cairosvg, _render_pillow):
        try:
            data = renderer(size)
            _CACHE[size] = data
            return data
        except Exception as e:
            print(f"[favicon] renderer {renderer.__name__} falló para {size}: {e}")
            continue
    # Fallback último recurso: devolver SVG como bytes (browsers modernos lo aceptan)
    return _render_svg_bytes()

# ──────────────────────────────────────────────────────────────────────
# Registro de rutas Flask
# ──────────────────────────────────────────────────────────────────────
def register(app):
    """Registra todas las rutas de favicon/manifest en la Flask `app`."""

    @app.route("/favicon.svg")
    def _svg():
        return Response(FAVICON_SVG, mimetype="image/svg+xml", headers=_CACHE_HEADERS)

    @app.route("/favicon.ico")
    def _ico():
        data = render_png(32)
        # Si cairosvg/pillow fallaron totalmente devolvemos svg
        if data.startswith(b"<?xml") or data.startswith(b"<svg"):
            return Response(data, mimetype="image/svg+xml", headers=_CACHE_HEADERS)
        return Response(data, mimetype="image/png", headers=_CACHE_HEADERS)

    for s in _SIZES:
        # Capturamos s en el closure
        def _make(size):
            def _png():
                data = render_png(size)
                mt = "image/svg+xml" if data.startswith(b"<") else "image/png"
                return Response(data, mimetype=mt, headers=_CACHE_HEADERS)
            _png.__name__ = f"_icon_{size}"
            return _png
        app.add_url_rule(f"/icon-{s}.png", endpoint=f"icon_{s}", view_func=_make(s))

    @app.route("/site.webmanifest")
    def _manifest():
        data = {
            "name":       "DeepNova",
            "short_name": "DeepNova",
            "description": "God-Tier Agent — DeepNova v2 Híbrido",
            "icons": [
                {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                {"src": "/favicon.svg",  "sizes": "any",      "type": "image/svg+xml"},
            ],
            "theme_color":       "#6366f1",
            "background_color":  "#06080f",
            "display":           "standalone",
            "start_url":         "/",
        }
        return jsonify(data), 200, _CACHE_HEADERS

    @app.route("/apple-touch-icon.png")
    def _apple():
        data = render_png(180)
        mt = "image/svg+xml" if data.startswith(b"<") else "image/png"
        return Response(data, mimetype=mt, headers=_CACHE_HEADERS)

    return app
