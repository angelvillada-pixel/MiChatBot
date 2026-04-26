"""
═══════════════════════════════════════════════════════════════════════════
 multi_llm.py  ·  DeepNova v6.0 · Multi-Provider LLM con Fallback Real
═══════════════════════════════════════════════════════════════════════════
 ✔ Provider primario: Groq (ya configurado en el proyecto)
 ✔ Provider fallback: OpenAI-compatible (opcional, solo si OPENAI_API_KEY)
 ✔ Provider open-source fallback: cualquier endpoint HTTP compatible
 ✔ Si todos fallan → respuesta degradada controlada (no 500)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os, logging, time
from typing import Optional

logger = logging.getLogger("multi_llm")

try:
    import httpx
    _HAS_HTTPX = True
except Exception:
    _HAS_HTTPX = False


class MultiLLM:
    """Cliente LLM resiliente con cadena de fallback real.

    Orden:
      1) Groq (primario)
      2) OpenAI (si OPENAI_API_KEY)
      3) Open-source endpoint (si OSS_LLM_URL)
      4) Respuesta degradada
    """

    def __init__(self, groq_client=None):
        self.groq = groq_client
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.oss_url = os.environ.get("OSS_LLM_URL")  # ej. http://localhost:11434/v1/chat/completions

    # ───────────────────────── PRIMARIO ─────────────────────────
    def _call_groq(self, system: str, prompt: str, temperature: float, max_tokens: int, model: str = "llama-3.3-70b-versatile") -> str:
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

    # ───────────────────────── FALLBACK 1 (OpenAI) ─────────────────────────
    def _call_openai(self, system: str, prompt: str, temperature: float, max_tokens: int) -> str:
        if not (self.openai_key and _HAS_HTTPX):
            raise RuntimeError("OpenAI no disponible")
        with httpx.Client(timeout=60) as cli:
            r = cli.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.openai_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    # ───────────────────────── FALLBACK 2 (Open Source) ─────────────────────────
    def _call_oss(self, system: str, prompt: str, temperature: float, max_tokens: int) -> str:
        if not (self.oss_url and _HAS_HTTPX):
            raise RuntimeError("OSS endpoint no configurado")
        with httpx.Client(timeout=60) as cli:
            r = cli.post(
                self.oss_url,
                json={
                    "model": os.environ.get("OSS_LLM_MODEL", "llama3"),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    # ───────────────────────── INTERFAZ PÚBLICA ─────────────────────────
    def generate_sync(self, prompt: str, system: str = "", temperature: float = 0.7, max_tokens: int = 1000) -> str:
        chain = [
            ("groq",   lambda: self._call_groq(system, prompt, temperature, max_tokens)),
            ("openai", lambda: self._call_openai(system, prompt, temperature, max_tokens)),
            ("oss",    lambda: self._call_oss(system, prompt, temperature, max_tokens)),
        ]
        last_err: Optional[Exception] = None
        for name, fn in chain:
            t0 = time.perf_counter()
            try:
                out = fn()
                logger.info("[multi_llm] ✓ %s ok (%.0fms)", name, (time.perf_counter() - t0) * 1000)
                return out
            except Exception as e:
                last_err = e
                logger.warning("[multi_llm] %s falló: %s", name, e)

        # Respuesta degradada
        logger.error("[multi_llm] todos los providers fallaron: %s", last_err)
        return ("⚠️ El servicio de IA está temporalmente saturado. "
                "Intenta de nuevo en unos segundos. "
                f"(detalle: {type(last_err).__name__})")

    async def generate(self, prompt: str, system: str = "", temperature: float = 0.7, max_tokens: int = 1000) -> str:
        # versión async simple (envuelve sync) — si quieres async puro, sustituye por httpx.AsyncClient
        return self.generate_sync(prompt, system, temperature, max_tokens)
