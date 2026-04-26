"""
═══════════════════════════════════════════════════════════════════════════
 limiter.py  ·  DeepNova v6.0 · Rate Limiter avanzado
═══════════════════════════════════════════════════════════════════════════
 Rate limit por IP/usuario con ventanas configurables.
 Compatible con el sistema de planes (roles.py).
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import time, threading
from collections import defaultdict, deque
from typing import Optional


class RateLimiter:
    def __init__(self):
        self._buckets: dict = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, max_requests: int = 20, window_sec: int = 60) -> bool:
        """¿Se permite esta petición? Actualiza el bucket."""
        now = time.time()
        with self._lock:
            q = self._buckets[key]
            # Purgar antiguos
            cutoff = now - window_sec
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= max_requests:
                return False
            q.append(now)
            return True

    def remaining(self, key: str, max_requests: int = 20, window_sec: int = 60) -> int:
        now = time.time()
        with self._lock:
            q = self._buckets[key]
            cutoff = now - window_sec
            while q and q[0] < cutoff:
                q.popleft()
            return max(0, max_requests - len(q))

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


# Instancia global
limiter = RateLimiter()


def allow_request(ip: str, plan: dict | None = None) -> bool:
    """Helper integrado con planes (roles.py).
    Si pasas el dict del plan, usa sus límites rpm; si no, usa default 20/60s.
    """
    if plan:
        return limiter.allow(ip, max_requests=plan.get("rpm", 20), window_sec=60)
    return limiter.allow(ip, max_requests=20, window_sec=60)
