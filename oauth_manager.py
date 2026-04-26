"""
═══════════════════════════════════════════════════════════════════════════
 oauth_manager.py  ·  DeepNova v5 · OAuth 2.0 real (Google · GitHub · Slack)
═══════════════════════════════════════════════════════════════════════════
 Authorization Code Flow + refresh tokens automáticos.
 Tokens cifrados con Fernet (AES-128 CBC + HMAC) si está cryptography;
 fallback seguro a base64 (solo desarrollo) si no está instalada.

 Variables de entorno requeridas (no se hardcodean credenciales):
   GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI
   GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET / GITHUB_REDIRECT_URI
   SLACK_CLIENT_ID  / SLACK_CLIENT_SECRET  / SLACK_REDIRECT_URI
   OAUTH_SECRET (clave maestra para cifrar; si no se define se genera una en memoria)
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os
import json
import time
import hashlib
import base64
import secrets
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

# Cifrado opcional (Fernet) — si falla, fallback base64 (NO seguro en prod)
try:
    from cryptography.fernet import Fernet  # type: ignore
    _FERNET_OK = True
except Exception:
    _FERNET_OK = False

TOKENS_FILE = os.environ.get("DEEPNOVA_OAUTH_FILE", "deepnova_oauth_tokens.json")
SECRET_KEY = os.environ.get("OAUTH_SECRET") or secrets.token_hex(32)

# ── Configuración por proveedor ───────────────────────────────────────
OAUTH_CONFIGS: Dict[str, Dict[str, Any]] = {
    "google": {
        "auth_uri":  "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id":     os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "scopes": [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/drive.metadata.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
        ],
        "redirect_uri": os.environ.get(
            "GOOGLE_REDIRECT_URI",
            "http://localhost:5000/oauth/callback/google",
        ),
        "extra_auth_params": {"access_type": "offline", "prompt": "consent"},
    },
    "github": {
        "auth_uri":  "https://github.com/login/oauth/authorize",
        "token_uri": "https://github.com/login/oauth/access_token",
        "client_id":     os.environ.get("GITHUB_CLIENT_ID", ""),
        "client_secret": os.environ.get("GITHUB_CLIENT_SECRET", ""),
        "scopes": ["repo", "user:email"],
        "redirect_uri": os.environ.get(
            "GITHUB_REDIRECT_URI",
            "http://localhost:5000/oauth/callback/github",
        ),
        "extra_auth_params": {},
    },
    "slack": {
        "auth_uri":  "https://slack.com/oauth/v2/authorize",
        "token_uri": "https://slack.com/api/oauth.v2.access",
        "client_id":     os.environ.get("SLACK_CLIENT_ID", ""),
        "client_secret": os.environ.get("SLACK_CLIENT_SECRET", ""),
        "scopes": ["channels:read", "chat:write", "users:read"],
        "redirect_uri": os.environ.get(
            "SLACK_REDIRECT_URI",
            "http://localhost:5000/oauth/callback/slack",
        ),
        "extra_auth_params": {},
    },
}


class OAuthManager:
    """Gestor de tokens OAuth 2.0 con persistencia cifrada."""

    def __init__(self) -> None:
        self._tokens: Dict[str, Dict[str, Any]] = self._load()
        self._states: Dict[str, Dict[str, Any]] = {}  # state -> {sid, provider, ts}

    # ── cifrado ───────────────────────────────────────────────────────
    def _key(self) -> bytes:
        return base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())

    def _encrypt(self, data: str) -> str:
        if not data:
            return ""
        if not _FERNET_OK:
            return "b64:" + base64.b64encode(data.encode()).decode()
        try:
            return "fn:" + Fernet(self._key()).encrypt(data.encode()).decode()
        except Exception:
            return "b64:" + base64.b64encode(data.encode()).decode()

    def _decrypt(self, data: str) -> str:
        if not data:
            return ""
        try:
            if data.startswith("fn:") and _FERNET_OK:
                return Fernet(self._key()).decrypt(data[3:].encode()).decode()
            if data.startswith("b64:"):
                return base64.b64decode(data[4:].encode()).decode()
            # legacy (sin prefijo)
            if _FERNET_OK:
                try:
                    return Fernet(self._key()).decrypt(data.encode()).decode()
                except Exception:
                    pass
            return base64.b64decode(data.encode()).decode()
        except Exception:
            return ""

    # ── persistencia ──────────────────────────────────────────────────
    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            if os.path.exists(TOKENS_FILE):
                with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            print(f"[oauth] _load warn: {e}")
        return {}

    def _save(self) -> None:
        try:
            tmp = TOKENS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._tokens, f, indent=2)
            os.replace(tmp, TOKENS_FILE)
        except Exception as e:
            print(f"[oauth] _save warn: {e}")

    # ── flujo OAuth ───────────────────────────────────────────────────
    def generate_auth_url(self, provider: str, sid: str) -> Optional[str]:
        cfg = OAUTH_CONFIGS.get(provider)
        if not cfg or not cfg.get("client_id"):
            return None
        state = secrets.token_urlsafe(32)
        self._states[state] = {
            "sid": sid or "anon",
            "provider": provider,
            "ts": time.time(),
        }
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(cfg["scopes"]),
            "state": state,
        }
        params.update(cfg.get("extra_auth_params", {}) or {})
        return cfg["auth_uri"] + "?" + urlencode(params)

    def exchange_code(
        self, provider: str, code: str, state: str
    ) -> Dict[str, Any]:
        import requests  # local import para no forzar al boot

        state_data = self._states.pop(state, {})
        if not state_data:
            return {"success": False, "error": "Invalid state"}
        if time.time() - state_data.get("ts", 0) > 600:
            return {"success": False, "error": "State expired"}
        if state_data.get("provider") != provider:
            return {"success": False, "error": "State/provider mismatch"}

        cfg = OAUTH_CONFIGS.get(provider, {})
        if not cfg:
            return {"success": False, "error": "Unknown provider"}

        try:
            r = requests.post(
                cfg["token_uri"],
                data={
                    "code": code,
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "redirect_uri": cfg["redirect_uri"],
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
                timeout=12,
            )
            tokens = r.json() if r.headers.get("content-type", "").startswith(
                "application/json"
            ) else _parse_form(r.text)
        except Exception as e:
            return {"success": False, "error": f"network:{e}"}

        # Slack devuelve authed_user con token anidado
        access_token = tokens.get("access_token") or (
            tokens.get("authed_user", {}) or {}
        ).get("access_token")
        if not access_token:
            return {
                "success": False,
                "error": tokens.get("error", "token_error"),
                "raw": tokens,
            }

        sid = state_data["sid"]
        if sid not in self._tokens:
            self._tokens[sid] = {}
        self._tokens[sid][provider] = {
            "access_token":  self._encrypt(access_token),
            "refresh_token": self._encrypt(tokens.get("refresh_token", "")),
            "expires_at":    time.time() + int(tokens.get("expires_in", 3600) or 3600),
            "scope":         tokens.get("scope", ""),
            "token_type":    tokens.get("token_type", "Bearer"),
            "connected_at":  time.time(),
        }
        self._save()
        return {"success": True, "provider": provider}

    def get_access_token(self, sid: str, provider: str) -> Optional[str]:
        import requests

        token_data = self._tokens.get(sid, {}).get(provider)
        if not token_data:
            return None
        # vigente
        if time.time() < token_data.get("expires_at", 0) - 60:
            return self._decrypt(token_data["access_token"])
        # refrescar si es posible
        rt = self._decrypt(token_data.get("refresh_token", ""))
        if rt:
            cfg = OAUTH_CONFIGS.get(provider, {})
            try:
                r = requests.post(
                    cfg["token_uri"],
                    data={
                        "refresh_token": rt,
                        "client_id": cfg["client_id"],
                        "client_secret": cfg["client_secret"],
                        "grant_type": "refresh_token",
                    },
                    headers={"Accept": "application/json"},
                    timeout=12,
                )
                new_tokens = r.json()
                if "access_token" in new_tokens:
                    token_data["access_token"] = self._encrypt(
                        new_tokens["access_token"]
                    )
                    token_data["expires_at"] = time.time() + int(
                        new_tokens.get("expires_in", 3600) or 3600
                    )
                    if new_tokens.get("refresh_token"):
                        token_data["refresh_token"] = self._encrypt(
                            new_tokens["refresh_token"]
                        )
                    self._save()
                    return new_tokens["access_token"]
            except Exception as e:
                print(f"[oauth] refresh warn: {e}")
        return None

    def is_connected(self, sid: str, provider: str) -> bool:
        return bool(self._tokens.get(sid, {}).get(provider))

    def disconnect(self, sid: str, provider: str) -> bool:
        if sid in self._tokens and provider in self._tokens[sid]:
            del self._tokens[sid][provider]
            self._save()
            return True
        return False

    def list_connected(self, sid: str) -> List[str]:
        return list(self._tokens.get(sid, {}).keys())


def _parse_form(text: str) -> Dict[str, str]:
    """Parser fallback para respuestas application/x-www-form-urlencoded."""
    out: Dict[str, str] = {}
    for kv in (text or "").split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
    return out


# Instancia global usada por app.py
oauth_mgr = OAuthManager()
