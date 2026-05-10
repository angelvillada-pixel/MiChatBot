# ══════════════════════════════════════════════════════════════════════
# DeepNova · app_v2_patch.py
# Snippet 100% aditivo para enganchar el frontend /v2 al app.py existente.
# ──────────────────────────────────────────────────────────────────────
# COPIA y PEGA este bloque al FINAL de tu app.py (justo antes del
# `if __name__ == "__main__":`), o mantén este archivo y haz:
#
#     from app_v2_patch import register_v2
#     register_v2(app)
#
# Patrón idéntico al de register_v6 / register_v7 ya presentes.
# ══════════════════════════════════════════════════════════════════════

def register_v2(app, logger=None):
    """Registra el frontend premium /v2 en la app Flask de DeepNova.

    Es 100 % tolerante a fallos: si el módulo v2_frontend o la carpeta
    static/v2/ no existen, simplemente lo loguea y sigue.
    """
    try:
        from v2_frontend import register_v2_frontend
        register_v2_frontend(app)
        if logger:
            logger.info("✓ DeepNova /v2 frontend premium registrado (UI fusionada Facil-con-IA)")
        else:
            print("[v2-frontend] ✓ /v2 registrado")
        return True
    except Exception as e:
        msg = f"[v2-frontend] no disponible: {e}"
        if logger:
            logger.warning(msg)
        else:
            print(msg)
        return False


# ──────────────────────────────────────────────────────────────────────
# BLOQUE A AÑADIR EN app.py (al final, antes del bloque __main__):
# ──────────────────────────────────────────────────────────────────────
"""
# ══════════════════════════════════════════
# 🆕 DEEPNOVA v2-FRONTEND — UI premium /v2
# 100% aditivo · NO toca '/' ni 'index.html' originales
# ══════════════════════════════════════════
try:
    from app_v2_patch import register_v2
    register_v2(app, logger=logger)
except Exception as _e_v2:
    logger.warning("[v2] patch no disponible: %s", _e_v2)
"""
