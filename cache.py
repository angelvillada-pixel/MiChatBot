"""
═══════════════════════════════════════════════════════════════════════════
 cache.py  ·  DeepNova v6.0 · Cache LRU thread-safe en memoria
═══════════════════════════════════════════════════════════════════════════
 Cache de respuestas para acelerar prompts repetidos.
 - LRU con tamaño máximo configurable
 - TTL opcional por entrada
 - Thread-safe
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import time, threading, hashlib
from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    def __init__(self, max_size: int = 500, default_ttl: int = 600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._data: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        self._lock = threading.Lock()

    def _key(self, prompt: str, model_id: str = "") -> str:
        h = hashlib.sha256(f"{model_id}::{prompt}".encode()).hexdigest()
        return h[:32]

    def get(self, prompt: str, model_id: str = "") -> Optional[Any]:
        k = self._key(prompt, model_id)
        with self._lock:
            entry = self._data.get(k)
            if not entry:
                return None
            value, expires = entry
            if expires and time.time() > expires:
                self._data.pop(k, None)
                return None
            self._data.move_to_end(k)
            return value

    def set(self, prompt: str, value: Any, model_id: str = "", ttl: Optional[int] = None) -> None:
        k = self._key(prompt, model_id)
        ttl = ttl if ttl is not None else self.default_ttl
        expires = time.time() + ttl if ttl > 0 else 0
        with self._lock:
            self._data[k] = (value, expires)
            self._data.move_to_end(k)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._data), "max_size": self.max_size}


# Instancia global
response_cache = LRUCache(max_size=500, default_ttl=600)


def cached_or_compute(prompt: str, model_id: str, compute_fn, ttl: int = 600):
    """Helper: devuelve cache si existe, sino calcula y guarda."""
    hit = response_cache.get(prompt, model_id)
    if hit is not None:
        return hit, True
    result = compute_fn()
    response_cache.set(prompt, result, model_id, ttl)
    return result, False
