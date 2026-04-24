"""
═══════════════════════════════════════════════════════════════════════════
 Image Generation Module — DeepNova v4 / NeuroCore-X
═══════════════════════════════════════════════════════════════════════════
 Generación REAL de imágenes sin requerir API keys:
   • Primario:  Pollinations.ai (gratis, sin auth) — flux / turbo / nano-banana
   • Secundario: Hugging Face Inference (si HF_TOKEN en env)
   • Fallback:  SVG placeholder artístico generado localmente

 Todas las funciones devuelven URL o data-URI consumible desde el frontend.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os, re, base64, hashlib, random, urllib.parse, time, json
from typing import Dict, Any, Optional

try:
    import requests
except Exception:
    requests = None  # fallback puro


# ── Modelos Pollinations ───────────────────────────────────────────
POLLINATIONS_MODELS = {
    "flux":         "flux",
    "flux-realism": "flux-realism",
    "flux-anime":   "flux-anime",
    "flux-3d":      "flux-3d",
    "turbo":        "turbo",
    "nano-banana":  "flux",   # alias simpático (como pidió el sistema)
}

DEFAULT_MODEL = "flux"


def _sanitize(prompt: str) -> str:
    """Limpia y mejora un prompt para generación de imágenes."""
    p = (prompt or "").strip()
    p = re.sub(r"\s+", " ", p)
    # Traducción básica de palabras comunes ES→EN para mejorar el generador
    repl = {
        r"\bperro\b": "dog", r"\bgato\b": "cat", r"\bcasa\b": "house",
        r"\bárbol\b": "tree", r"\bmontaña\b": "mountain", r"\bplaya\b": "beach",
        r"\bciudad\b": "city", r"\bpaisaje\b": "landscape", r"\bretrato\b": "portrait",
        r"\brobot\b": "robot", r"\bastronauta\b": "astronaut", r"\bdragón\b": "dragon",
        r"\bespacio\b": "space", r"\bfuturo\b": "futuristic", r"\bmágico\b": "magical",
    }
    pl = p.lower()
    for k, v in repl.items():
        pl = re.sub(k, v, pl)
    return pl[:500]


def enhance_prompt(prompt: str, style: str = "cinematic") -> str:
    """Enriquece un prompt con modificadores de calidad."""
    base = _sanitize(prompt)
    style_packs = {
        "cinematic":    "cinematic lighting, 8k, ultra detailed, dramatic composition, film grain",
        "photo":        "photorealistic, 85mm lens, soft shadows, natural lighting, dof",
        "anime":        "anime style, vibrant colors, studio ghibli, detailed background",
        "3d":           "3d render, octane, hyperrealistic, volumetric light, pixar style",
        "art":          "digital art, trending on artstation, intricate details, concept art",
        "minimal":      "minimalist, clean composition, white background, product shot",
        "fantasy":      "epic fantasy, mystical, glowing, magical atmosphere, highly detailed",
        "cyberpunk":    "cyberpunk, neon lights, futuristic city, rain, blade runner aesthetic",
    }
    mods = style_packs.get(style, style_packs["cinematic"])
    return f"{base}, {mods}"


# ═══════════════════════════════════════════════════════════════════════
#  Pollinations.ai — Primario (sin auth, robusto, gratis)
# ═══════════════════════════════════════════════════════════════════════
def generate_via_pollinations(
    prompt: str,
    model: str = DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    nologo: bool = True,
    enhance: bool = True,
) -> Dict[str, Any]:
    """
    Genera una imagen vía Pollinations.ai.
    Devuelve dict con url, prompt_final, model, size, etc.
    No descarga la imagen (el frontend la carga directamente); esto es eficiente.
    """
    real_model = POLLINATIONS_MODELS.get(model, DEFAULT_MODEL)
    final_prompt = enhance_prompt(prompt) if enhance else _sanitize(prompt)
    if seed is None:
        seed = random.randint(1, 10_000_000)

    encoded = urllib.parse.quote(final_prompt, safe="")
    params = {
        "width":  width,
        "height": height,
        "model":  real_model,
        "seed":   seed,
        "nologo": "true" if nologo else "false",
        "enhance": "true" if enhance else "false",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://image.pollinations.ai/prompt/{encoded}?{qs}"

    return {
        "success":      True,
        "url":          url,
        "provider":     "pollinations",
        "model":        real_model,
        "prompt":       final_prompt,
        "original":     prompt,
        "width":        width,
        "height":       height,
        "seed":         seed,
        "message":      f"Imagen generada con Pollinations ({real_model})",
    }


# ═══════════════════════════════════════════════════════════════════════
#  Hugging Face — Secundario (opcional, si HF_TOKEN existe)
# ═══════════════════════════════════════════════════════════════════════
HF_MODELS = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
]

def generate_via_huggingface(prompt: str, model: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
    if not token or requests is None:
        return {"success": False, "error": "HF_TOKEN no configurado"}
    model = model or HF_MODELS[0]
    api = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "image/png"}
    final_prompt = enhance_prompt(prompt)
    try:
        r = requests.post(api, headers=headers, json={"inputs": final_prompt}, timeout=timeout)
        if r.status_code != 200:
            return {"success": False, "error": f"HF {r.status_code}: {r.text[:120]}"}
        b64 = base64.b64encode(r.content).decode("ascii")
        return {
            "success":  True,
            "url":      f"data:image/png;base64,{b64}",
            "provider": "huggingface",
            "model":    model,
            "prompt":   final_prompt,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
#  SVG Placeholder — Fallback final (nunca falla)
# ═══════════════════════════════════════════════════════════════════════
def _hash_color(seed: str, offset: int = 0) -> str:
    h = hashlib.md5((seed + str(offset)).encode()).hexdigest()
    return "#" + h[:6]


def generate_placeholder_svg(prompt: str, width: int = 1024, height: int = 1024) -> Dict[str, Any]:
    c1 = _hash_color(prompt, 0)
    c2 = _hash_color(prompt, 1)
    c3 = _hash_color(prompt, 2)
    safe = (prompt or "NeuroCore-X").replace("<", "&lt;").replace(">", "&gt;")[:80]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="50%" stop-color="{c2}"/>
      <stop offset="100%" stop-color="{c3}"/>
    </linearGradient>
    <radialGradient id="r" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.35)"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#g)"/>
  <circle cx="{width//2}" cy="{height//2}" r="{min(width,height)//3}" fill="url(#r)"/>
  <text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle"
        font-family="Segoe UI, sans-serif" font-size="{max(24, width//28)}" fill="white"
        style="text-shadow:0 2px 12px rgba(0,0,0,0.6)">{safe}</text>
  <text x="50%" y="95%" text-anchor="middle" font-family="monospace" font-size="18"
        fill="rgba(255,255,255,0.7)">NeuroCore-X · Generated</text>
</svg>"""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return {
        "success":  True,
        "url":      f"data:image/svg+xml;base64,{b64}",
        "provider": "svg-fallback",
        "model":    "local-gradient",
        "prompt":   prompt,
        "message":  "Fallback SVG — configurar Pollinations para imágenes reales",
    }


# ═══════════════════════════════════════════════════════════════════════
#  API UNIFICADA
# ═══════════════════════════════════════════════════════════════════════
def generate_image(
    prompt: str,
    model: str = DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    style: str = "cinematic",
    provider: str = "auto",
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Punto de entrada unificado.
    provider: "auto" | "pollinations" | "huggingface" | "svg"
    """
    if not prompt or len(prompt.strip()) < 3:
        return {"success": False, "error": "Prompt vacío"}

    # Auto-enhance con el style elegido
    final_prompt = enhance_prompt(prompt, style=style)

    if provider in ("auto", "pollinations"):
        try:
            res = generate_via_pollinations(
                prompt=final_prompt, model=model, width=width, height=height,
                seed=seed, enhance=False  # ya aplicamos enhance
            )
            res["style"] = style
            return res
        except Exception as e:
            if provider == "pollinations":
                return {"success": False, "error": str(e)}

    if provider in ("auto", "huggingface"):
        res = generate_via_huggingface(final_prompt)
        if res.get("success"):
            res["style"] = style
            return res
        if provider == "huggingface":
            return res

    # Fallback
    res = generate_placeholder_svg(prompt, width, height)
    res["style"] = style
    return res


def list_models() -> Dict[str, Any]:
    return {
        "models":    list(POLLINATIONS_MODELS.keys()),
        "styles":    ["cinematic", "photo", "anime", "3d", "art", "minimal", "fantasy", "cyberpunk"],
        "providers": ["auto", "pollinations", "huggingface", "svg"],
        "default_model":    DEFAULT_MODEL,
        "default_provider": "auto",
    }
