"""
═══════════════════════════════════════════════════════════════════════════
 multi_llm.py · DeepNova v8.0 · Multi-Provider LLM con OpenRouter
═══════════════════════════════════════════════════════════════════════════
 Cadena de fallback: Groq → OpenRouter → OpenAI → OSS → degradado
 OpenRouter da acceso a: Claude, GPT-4o, DeepSeek, Gemini, etc.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os, logging, time
from typing import Optional, Dict, Any

logger = logging.getLogger("multi_llm")

try:
    import httpx
    _HAS_HTTPX = True
except Exception:
    import requests as _req_fallback
    _HAS_HTTPX = False

# ═══════════════════════════════════════════════════════════════════════
#  MODELOS RECOMENDADOS POR PROVEEDOR
# ═══════════════════════════════════════════════════════════════════════
OPENROUTER_MODELS = {
    "best":     "anthropic/claude-sonnet-4",
    "fast":     "google/gemini-2.5-flash",
    "code":     "anthropic/claude-sonnet-4",
    "reason":   "deepseek/deepseek-r1",
    "cheap":    "google/gemini-2.5-flash",
}


class MultiLLM:
    """Cliente LLM resiliente con cadena de fallback real.

    Orden:
      1) Groq (primario — gratis, rápido)
      2) OpenRouter (si OPENROUTER_API_KEY — acceso a Claude/GPT-4/DeepSeek)
      3) OpenAI directo (si OPENAI_API_KEY)
      4) Open-source endpoint (si OSS_LLM_URL)
      5) Respuesta degradada controlada
    """

    def __init__(self, groq_client=None):
        self.groq = groq_client
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.oss_url = os.environ.get("OSS_LLM_URL")

    # ───────────────────────── GROQ ─────────────────────────
    def _call_groq(self, system: str, prompt: str, temperature: float,
                   max_tokens: int, model: str = "llama-3.3-70b-versatile") -> str:
        if self.groq is None:
            raise RuntimeError("Groq client no configurado")
        resp = self.groq.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    # ───────────────────────── OPENROUTER ─────────────────────────
    def _call_openrouter(self, system: str, prompt: str, temperature: float,
                         max_tokens: int, model_key: str = "fast") -> str:
        if not self.openrouter_key:
            raise RuntimeError("OpenRouter no configurado")
        model = OPENROUTER_MODELS.get(model_key, OPENROUTER_MODELS["fast"])

        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://deepnova.app",
            "X-Title": "DeepNova Agent",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if _HAS_HTTPX:
            with httpx.Client(timeout=90) as cli:
                r = cli.post("https://openrouter.ai/api/v1/chat/completions",
                             headers=headers, json=payload)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        else:
            r = _req_fallback.post("https://openrouter.ai/api/v1/chat/completions",
                                    headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    # ───────────────────────── OPENAI ─────────────────────────
    def _call_openai(self, system: str, prompt: str, temperature: float,
                     max_tokens: int) -> str:
        if not self.openai_key:
            raise RuntimeError("OpenAI no disponible")

        headers = {"Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if _HAS_HTTPX:
            with httpx.Client(timeout=60) as cli:
                r = cli.post("https://api.openai.com/v1/chat/completions",
                             headers=headers, json=payload)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        else:
            r = _req_fallback.post("https://api.openai.com/v1/chat/completions",
                                    headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    # ───────────────────────── OSS ─────────────────────────
    def _call_oss(self, system: str, prompt: str, temperature: float,
                  max_tokens: int) -> str:
        if not self.oss_url:
            raise RuntimeError("OSS endpoint no configurado")

        payload = {
            "model": os.environ.get("OSS_LLM_MODEL", "llama3"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if _HAS_HTTPX:
            with httpx.Client(timeout=60) as cli:
                r = cli.post(self.oss_url, json=payload)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        else:
            r = _req_fallback.post(self.oss_url, json=payload, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    # ───────────────────────── INTERFAZ PÚBLICA ─────────────────────────
    def generate_sync(self, prompt: str, system: str = "",
                      temperature: float = 0.7, max_tokens: int = 2000,
                      prefer: str = "auto") -> str:
        """
        prefer: 'auto' | 'groq' | 'openrouter' | 'best'
          - auto: Groq primero, fallback a OpenRouter
          - best: OpenRouter primero (mejor calidad), fallback a Groq
          - groq: solo Groq
          - openrouter: solo OpenRouter
        """
        chain = []

        if prefer in ("auto", "groq"):
            chain.append(("groq", lambda: self._call_groq(
                system, prompt, temperature, max_tokens)))
        if prefer in ("auto", "best", "openrouter"):
            chain.append(("openrouter", lambda: self._call_openrouter(
                system, prompt, temperature, max_tokens,
                "code" if prefer == "best" else "fast")))
        if prefer == "best":
            chain.append(("groq", lambda: self._call_groq(
                system, prompt, temperature, max_tokens)))

        chain.append(("openai", lambda: self._call_openai(
            system, prompt, temperature, max_tokens)))
        chain.append(("oss", lambda: self._call_oss(
            system, prompt, temperature, max_tokens)))

        last_err: Optional[Exception] = None
        for name, fn in chain:
            t0 = time.perf_counter()
            try:
                out = fn()
                ms = (time.perf_counter() - t0) * 1000
                logger.info("[multi_llm] ✓ %s ok (%.0fms)", name, ms)
                return out
            except Exception as e:
                last_err = e
                logger.warning("[multi_llm] %s falló: %s", name, e)

        logger.error("[multi_llm] todos fallaron: %s", last_err)
        return (f"⚠️ Todos los proveedores de IA fallaron. "
                f"Verifica tus API keys en .env. "
                f"(detalle: {type(last_err).__name__}: {last_err})")

    def has_openrouter(self) -> bool:
        return bool(self.openrouter_key)

    def has_openai(self) -> bool:
        return bool(self.openai_key)

    def available_providers(self) -> list:
        providers = ["groq"]
        if self.openrouter_key:
            providers.append("openrouter")
        if self.openai_key:
            providers.append("openai")
        if self.oss_url:
            providers.append("oss")
        return providers
