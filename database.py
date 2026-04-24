"""
═══════════════════════════════════════════════════════════════════════
 database.py — M2: Persistencia dual SQLite/PostgreSQL (DeepNova v2)
═══════════════════════════════════════════════════════════════════════

Autodetecta DATABASE_URL:
  • Si apunta a postgres:// o postgresql:// → usa Postgres
  • Si no → SQLite local en deepnova.db

Esquema:
  conversations (id, sid, title, mode, created_at, updated_at, summary)
  messages      (id, conversation_id, role, content, model, modes, created_at,
                 embedding_blob)
  memory        (id, sid, key, value, updated_at)
  feedback      (id, message_id, sid, vote, comment, created_at)  ← M5

Usa SQLAlchemy Core (no ORM) para mantener el footprint pequeño y
compatible con el app.py original que no lo usaba.
"""
import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    Integer, String, Text, DateTime, LargeBinary, ForeignKey, Index,
    select, insert, update, delete, and_, func,
)
from sqlalchemy.exc import SQLAlchemyError

# ──────────────────────────────────────────────────────────────────────
# Engine + detección dual
# ──────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///deepnova.db")

# Railway/Heroku a veces devuelven 'postgres://' — SQLAlchemy necesita 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = DATABASE_URL.startswith("postgresql://")

_engine_kwargs = {"pool_pre_ping": True}
if not IS_POSTGRES:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine   = create_engine(DATABASE_URL, **_engine_kwargs)
metadata = MetaData()

# ──────────────────────────────────────────────────────────────────────
# Esquema
# ──────────────────────────────────────────────────────────────────────
conversations = Table(
    "conversations", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("sid",        String(128), nullable=False, index=True),
    Column("title",      String(256), default="Nueva conversación"),
    Column("mode",       String(32),  default="chat"),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    Column("summary",    Text, default=""),
    Index("idx_conv_sid_updated", "sid", "updated_at"),
)

messages = Table(
    "messages", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("conversation_id", Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True),
    Column("role",            String(16)),   # user | assistant | system
    Column("content",         Text),
    Column("model",           String(64), default=""),
    Column("modes",           String(256), default=""),
    Column("created_at",      DateTime, default=datetime.utcnow),
    Column("embedding_blob",  LargeBinary, nullable=True),
)

memory = Table(
    "memory", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("sid",        String(128), index=True),
    Column("key",        String(128)),
    Column("value",      Text),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    Index("idx_mem_sid_key", "sid", "key", unique=True),
)

feedback = Table(
    "feedback", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("message_id", Integer, nullable=True),
    Column("sid",        String(128), index=True),
    Column("vote",       Integer),        # +1 / -1
    Column("comment",    Text, default=""),
    Column("signal",     String(32), default="thumb"),  # thumb | copied | regenerated
    Column("created_at", DateTime, default=datetime.utcnow),
)

# ──────────────────────────────────────────────────────────────────────
# Init
# ──────────────────────────────────────────────────────────────────────
_initialized = False

def init_db() -> bool:
    """Crea las tablas si no existen. Seguro de llamar varias veces."""
    global _initialized
    if _initialized:
        return True
    try:
        metadata.create_all(engine)
        _initialized = True
        return True
    except SQLAlchemyError as e:
        print(f"[database] init_db error: {e}")
        return False

# ──────────────────────────────────────────────────────────────────────
# Conversaciones
# ──────────────────────────────────────────────────────────────────────
def create_conversation(sid: str, title: str = "Nueva conversación", mode: str = "chat") -> Optional[int]:
    init_db()
    try:
        with engine.begin() as c:
            res = c.execute(insert(conversations).values(sid=sid, title=title, mode=mode))
            return int(res.inserted_primary_key[0])
    except Exception as e:
        print(f"[database] create_conversation error: {e}")
        return None

def list_conversations(sid: str, limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    try:
        with engine.connect() as c:
            q = (select(conversations)
                 .where(conversations.c.sid == sid)
                 .order_by(conversations.c.updated_at.desc())
                 .limit(limit))
            rows = c.execute(q).mappings().all()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[database] list_conversations error: {e}")
        return []

def get_conversation(cid: int) -> Optional[Dict[str, Any]]:
    init_db()
    try:
        with engine.connect() as c:
            r = c.execute(select(conversations).where(conversations.c.id == cid)).mappings().first()
            return dict(r) if r else None
    except Exception:
        return None

def update_conversation(cid: int, **fields) -> bool:
    init_db()
    try:
        with engine.begin() as c:
            c.execute(update(conversations).where(conversations.c.id == cid).values(**fields))
            return True
    except Exception:
        return False

def delete_conversation(cid: int) -> bool:
    init_db()
    try:
        with engine.begin() as c:
            c.execute(delete(messages).where(messages.c.conversation_id == cid))
            c.execute(delete(conversations).where(conversations.c.id == cid))
            return True
    except Exception:
        return False

# ──────────────────────────────────────────────────────────────────────
# Mensajes
# ──────────────────────────────────────────────────────────────────────
def add_message(
    conversation_id: int,
    role: str,
    content: str,
    model: str = "",
    modes: List[str] = None,
    embedding: Optional[bytes] = None,
) -> Optional[int]:
    init_db()
    try:
        with engine.begin() as c:
            res = c.execute(insert(messages).values(
                conversation_id=conversation_id,
                role=role,
                content=content,
                model=model,
                modes=",".join(modes or []),
                embedding_blob=embedding,
            ))
            # Touch updated_at en la conversación
            c.execute(update(conversations)
                      .where(conversations.c.id == conversation_id)
                      .values(updated_at=datetime.utcnow()))
            return int(res.inserted_primary_key[0])
    except Exception as e:
        print(f"[database] add_message error: {e}")
        return None

def list_messages(conversation_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    init_db()
    try:
        with engine.connect() as c:
            q = (select(messages)
                 .where(messages.c.conversation_id == conversation_id)
                 .order_by(messages.c.created_at.asc())
                 .limit(limit))
            rows = c.execute(q).mappings().all()
            return [dict(r) for r in rows]
    except Exception:
        return []

def count_messages(conversation_id: int) -> int:
    init_db()
    try:
        with engine.connect() as c:
            n = c.execute(
                select(func.count()).select_from(messages)
                .where(messages.c.conversation_id == conversation_id)
            ).scalar()
            return int(n or 0)
    except Exception:
        return 0

def all_messages_with_embedding(sid: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Para búsqueda semántica cross-conversation."""
    init_db()
    try:
        with engine.connect() as c:
            q = (select(
                    messages.c.id,
                    messages.c.conversation_id,
                    messages.c.role,
                    messages.c.content,
                    messages.c.embedding_blob,
                    messages.c.created_at,
                    conversations.c.title,
                    conversations.c.sid,
                 )
                 .select_from(messages.join(conversations, messages.c.conversation_id == conversations.c.id))
                 .where(and_(conversations.c.sid == sid, messages.c.embedding_blob.isnot(None)))
                 .order_by(messages.c.created_at.desc())
                 .limit(limit))
            return [dict(r) for r in c.execute(q).mappings().all()]
    except Exception:
        return []

# ──────────────────────────────────────────────────────────────────────
# Memory (key/value por sid)
# ──────────────────────────────────────────────────────────────────────
def set_memory(sid: str, key: str, value: str) -> bool:
    init_db()
    try:
        with engine.begin() as c:
            existing = c.execute(
                select(memory.c.id).where(and_(memory.c.sid == sid, memory.c.key == key))
            ).scalar()
            if existing:
                c.execute(update(memory).where(memory.c.id == existing).values(value=value))
            else:
                c.execute(insert(memory).values(sid=sid, key=key, value=value))
            return True
    except Exception as e:
        print(f"[database] set_memory: {e}")
        return False

def get_memory_all(sid: str) -> Dict[str, str]:
    init_db()
    try:
        with engine.connect() as c:
            rows = c.execute(select(memory.c.key, memory.c.value).where(memory.c.sid == sid)).all()
            return {k: v for k, v in rows}
    except Exception:
        return {}

def clear_memory(sid: str) -> bool:
    init_db()
    try:
        with engine.begin() as c:
            c.execute(delete(memory).where(memory.c.sid == sid))
            return True
    except Exception:
        return False

# ──────────────────────────────────────────────────────────────────────
# Feedback (M5)
# ──────────────────────────────────────────────────────────────────────
def add_feedback(sid: str, message_id: Optional[int], vote: int,
                 comment: str = "", signal: str = "thumb") -> Optional[int]:
    init_db()
    try:
        with engine.begin() as c:
            res = c.execute(insert(feedback).values(
                sid=sid, message_id=message_id, vote=int(vote),
                comment=comment, signal=signal,
            ))
            return int(res.inserted_primary_key[0])
    except Exception as e:
        print(f"[database] add_feedback: {e}")
        return None

def feedback_stats(limit: int = 200) -> Dict[str, Any]:
    init_db()
    try:
        with engine.connect() as c:
            pos = c.execute(select(func.count()).select_from(feedback).where(feedback.c.vote > 0)).scalar() or 0
            neg = c.execute(select(func.count()).select_from(feedback).where(feedback.c.vote < 0)).scalar() or 0
            recent = c.execute(select(feedback).order_by(feedback.c.created_at.desc()).limit(limit)).mappings().all()
            return {
                "positive": int(pos),
                "negative": int(neg),
                "ratio":    round(pos / max(pos + neg, 1), 3),
                "recent":   [dict(r) for r in recent],
            }
    except Exception:
        return {"positive": 0, "negative": 0, "ratio": 0.0, "recent": []}

# ──────────────────────────────────────────────────────────────────────
# Info / health
# ──────────────────────────────────────────────────────────────────────
def db_info() -> Dict[str, Any]:
    init_db()
    info = {"backend": "postgresql" if IS_POSTGRES else "sqlite", "url": DATABASE_URL.split("@")[-1]}
    try:
        with engine.connect() as c:
            info["conversations"] = int(c.execute(select(func.count()).select_from(conversations)).scalar() or 0)
            info["messages"]      = int(c.execute(select(func.count()).select_from(messages)).scalar() or 0)
            info["memory_items"]  = int(c.execute(select(func.count()).select_from(memory)).scalar() or 0)
            info["feedback"]      = int(c.execute(select(func.count()).select_from(feedback)).scalar() or 0)
    except Exception as e:
        info["error"] = str(e)
    return info
