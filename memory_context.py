"""
═══════════════════════════════════════════════════════════════════════════
 memory_context.py  ·  DeepNova v6.0 · Memoria contextual estilo ChatGPT
═══════════════════════════════════════════════════════════════════════════
 Construye prompts con contexto previo coherente, sin saturar tokens.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import List, Dict, Any
import re


def build_context(user_input: str, memory: List[str], max_items: int = 5, max_chars: int = 1500) -> str:
    """Construye un bloque de contexto a partir de los últimos N mensajes."""
    if not memory:
        return user_input

    recent = memory[-max_items:]
    ctx = "\n".join(f"- {m}" for m in recent)

    # Truncar contexto si excede
    if len(ctx) > max_chars:
        ctx = ctx[-max_chars:]
        ctx = "...[contexto truncado]\n" + ctx

    return f"""Contexto previo de la conversación:
{ctx}

Nueva entrada del usuario:
{user_input}"""


def build_messages_with_context(
    system: str,
    user_input: str,
    history: List[Dict[str, str]],
    max_pairs: int = 8,
) -> List[Dict[str, str]]:
    """Construye una lista `messages` para chat completions con historial."""
    msgs: List[Dict[str, str]] = [{"role": "system", "content": system}]
    # history: [{role: 'user'|'assistant', content: '...'}, ...]
    if history:
        # tomar las últimas max_pairs*2 entradas (pares user/assistant)
        recent = history[-(max_pairs * 2):]
        msgs.extend(recent)
    msgs.append({"role": "user", "content": user_input})
    return msgs


def summarize_for_memory(text: str, max_len: int = 200) -> str:
    """Resume un mensaje largo para guardar en memoria sin perder lo esencial."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def extract_facts(message: str) -> List[str]:
    """Detecta frases que parecen 'hechos del usuario' (me llamo X, soy Y, vivo en Z)."""
    facts = []
    patterns = [
        r"me llamo ([\w\s]+)",
        r"mi nombre es ([\w\s]+)",
        r"soy (?:un[a]? )?([\w\s]+)",
        r"trabajo (?:de|como|en) ([\w\s]+)",
        r"vivo en ([\w\s,]+)",
        r"me gusta(?:n)? ([\w\s,]+)",
        r"prefiero ([\w\s,]+)",
    ]
    low = message.lower()
    for pat in patterns:
        m = re.search(pat, low)
        if m:
            facts.append(f"{pat.split('(')[0].strip()}: {m.group(1).strip()}")
    return facts
