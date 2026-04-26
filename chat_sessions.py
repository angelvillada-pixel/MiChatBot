"""
═══════════════════════════════════════════════════════════════════════════
 chat_sessions.py  ·  DeepNova v5 · Sistema de Sesiones Persistentes
═══════════════════════════════════════════════════════════════════════════
 100% aditivo. Persiste cada conversación en disco (JSON) para que el
 sidebar tipo ChatGPT pueda listarlas, renombrarlas, fijarlas y borrarlas.

 Estructura de cada sesión:
   {
     "id":            "sess_<ms>_<uid6>",
     "user_id":       "u_xxxx",
     "title":         "Texto corto",
     "mode":          "chat" | "code" | ...,
     "created_at":    ISO8601,
     "updated_at":    ISO8601,
     "messages":      [{role, content, timestamp, meta}],
     "message_count": int,
     "pinned":        bool
   }
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

SESSION_FILE = os.environ.get("DEEPNOVA_SESSIONS_FILE", "deepnova_sessions.json")


class ChatSessionManager:
    """Gestor thread-safe-suficiente de sesiones de chat persistentes."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = self._load()

    # ── persistencia ──────────────────────────────────────────────────
    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            print(f"[chat_sessions] _load warn: {e}")
        return {}

    def _save(self) -> None:
        try:
            tmp = SESSION_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SESSION_FILE)
        except Exception as e:
            print(f"[chat_sessions] _save warn: {e}")

    # ── CRUD ──────────────────────────────────────────────────────────
    def create_session(
        self,
        user_id: str,
        title: str = "Nueva conversación",
        mode: str = "chat",
    ) -> str:
        session_id = f"sess_{int(time.time() * 1000)}_{(user_id or 'anon')[:6]}"
        self._sessions[session_id] = {
            "id": session_id,
            "user_id": user_id or "anon",
            "title": title or "Nueva conversación",
            "mode": mode or "chat",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "messages": [],
            "message_count": 0,
            "pinned": False,
        }
        self._save()
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)

    def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        sessions = [
            s for s in self._sessions.values() if s.get("user_id") == user_id
        ]
        # primero los fijados, luego por updated_at desc
        sessions.sort(
            key=lambda x: (
                0 if x.get("pinned") else 1,
                # invertir updated_at para que recientes vayan primero
                -1 * _ts_iso(x.get("updated_at", "")),
            )
        )
        return [
            {k: v for k, v in s.items() if k != "messages"} for s in sessions
        ]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if session_id not in self._sessions:
            return False
        s = self._sessions[session_id]
        s["messages"].append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
                "meta": meta or {},
            }
        )
        s["message_count"] = len(s["messages"])
        s["updated_at"] = datetime.utcnow().isoformat()
        # auto-rename con el primer mensaje del usuario
        if s["message_count"] == 2 and (
            s["title"] in ("Nueva conversación", "", None)
        ):
            first_user = next(
                (m["content"] for m in s["messages"] if m["role"] == "user"),
                "",
            )
            if first_user:
                s["title"] = first_user[:60] + (
                    "…" if len(first_user) > 60 else ""
                )
        self._save()
        return True

    def get_messages(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        s = self._sessions.get(session_id, {})
        msgs = s.get("messages", [])
        if limit and limit > 0:
            return msgs[-limit:]
        return msgs

    def rename_session(self, session_id: str, title: str) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id]["title"] = (title or "").strip() or "Sin título"
            self._sessions[session_id]["updated_at"] = datetime.utcnow().isoformat()
            self._save()
            return True
        return False

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._save()
            return True
        return False

    def pin_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id]["pinned"] = not self._sessions[
                session_id
            ].get("pinned", False)
            self._save()
            return True
        return False


def _ts_iso(s: str) -> float:
    """Convierte ISO8601 a timestamp; 0 si falla. Usado para ordenar."""
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s.replace("Z", "")).timestamp()
    except Exception:
        return 0.0


# Instancia global usada por app.py
session_manager = ChatSessionManager()
