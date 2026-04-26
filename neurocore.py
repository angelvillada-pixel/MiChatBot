"""
═══════════════════════════════════════════════════════════════════════════
 neurocore.py  ·  DeepNova v6.0 · Orquestador NeuroCore-X
═══════════════════════════════════════════════════════════════════════════
 Wrapper de alto nivel sobre nova_models + cualquier LLM client.
 - Routing automático cuando no se especifica modelo
 - Fallback a nova_sonnet si el modelo elegido falla
 - Compatible con el cliente Groq existente o cualquier cliente custom
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Any, Optional
import logging

from nova_models import route_model, safe_get_model

logger = logging.getLogger("neurocore")


class NeuroCore:
    """Orquestador inteligente de modelos Nova.

    Uso:
        nc = NeuroCore(llm_client)
        resp = await nc.process("explícame X", model_id="nova_opus")
    """

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    async def process(
        self,
        user_input: str,
        model_id: Optional[str] = None,
    ) -> str:
        """Procesa la entrada del usuario eligiendo modelo + fallback."""
        model = safe_get_model(model_id) if model_id else route_model(user_input)
        logger.info("[neurocore] modelo=%s intent_route=%s", model["id"], not model_id)

        try:
            return await self.llm.generate(
                prompt=user_input,
                system=model["system_prompt"],
                temperature=model["temperature"],
                max_tokens=model["max_tokens"],
            )
        except Exception as e:
            logger.warning("[neurocore] modelo %s falló (%s) → fallback nova_sonnet", model["id"], e)
            fb = safe_get_model("nova_sonnet")
            return await self.llm.generate(
                prompt=user_input,
                system=fb["system_prompt"],
                temperature=fb["temperature"],
                max_tokens=fb["max_tokens"],
            )

    # Versión sync (para integraciones Flask/Groq existentes que no usan asyncio)
    def process_sync(
        self,
        user_input: str,
        model_id: Optional[str] = None,
    ) -> str:
        model = safe_get_model(model_id) if model_id else route_model(user_input)
        logger.info("[neurocore-sync] modelo=%s", model["id"])
        try:
            return self.llm.generate_sync(
                prompt=user_input,
                system=model["system_prompt"],
                temperature=model["temperature"],
                max_tokens=model["max_tokens"],
            )
        except Exception as e:
            logger.warning("[neurocore-sync] fallback: %s", e)
            fb = safe_get_model("nova_sonnet")
            return self.llm.generate_sync(
                prompt=user_input,
                system=fb["system_prompt"],
                temperature=fb["temperature"],
                max_tokens=fb["max_tokens"],
            )
