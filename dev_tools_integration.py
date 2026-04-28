"""
═══════════════════════════════════════════════════════════════════════════
 dev_tools_integration.py · DeepNova v7.0 · Integración con Herramientas Dev
═══════════════════════════════════════════════════════════════════════════
 Conectores ligeros con plataformas de desarrollo:
   • GitHub      (issues, PRs, repos públicos sin token)
   • Jupyter     (export/import .ipynb)
   • VSCode      (formato de respuestas con anclas linkeables)
   • Snippets    (gestión de fragmentos de código reutilizables)

 Diseño:
   - HTTP simple con requests (ya está en deps)
   - Sin OAuth obligatorio: rutas no autenticadas para datos públicos
   - Tokens opcionales por env var (GITHUB_TOKEN)

 Áreas cubiertas (del documento de mejoras):
   ✓ 5.1 Integración con herramientas de desarrollo
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os
import json
import re
import base64
from typing import Dict, List, Any, Optional

try:
    import requests
    _HAS_REQ = True
except Exception:
    _HAS_REQ = False


# ──────────────────────────────────────────────────────────────────────
#  GitHub
# ──────────────────────────────────────────────────────────────────────
GITHUB_API = "https://api.github.com"


def _gh_headers() -> Dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "DeepNova/7.0"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def github_repo_info(owner: str, repo: str) -> Dict[str, Any]:
    """Información pública del repositorio."""
    if not _HAS_REQ:
        return {"ok": False, "error": "requests no disponible"}
    try:
        r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}",
                         headers=_gh_headers(), timeout=15)
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "error": r.text[:200]}
        d = r.json()
        return {
            "ok": True,
            "name":         d.get("full_name"),
            "description":  d.get("description"),
            "stars":        d.get("stargazers_count"),
            "forks":        d.get("forks_count"),
            "language":     d.get("language"),
            "open_issues":  d.get("open_issues_count"),
            "default_branch": d.get("default_branch"),
            "url":          d.get("html_url"),
            "topics":       d.get("topics", []),
            "updated_at":   d.get("updated_at"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def github_search_repos(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    if not _HAS_REQ:
        return []
    try:
        r = requests.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": query, "sort": "stars", "per_page": max_results},
            headers=_gh_headers(), timeout=15,
        )
        if r.status_code != 200:
            return []
        return [
            {
                "name": it["full_name"],
                "stars": it["stargazers_count"],
                "description": it.get("description"),
                "url": it["html_url"],
                "language": it.get("language"),
            }
            for it in r.json().get("items", [])[:max_results]
        ]
    except Exception:
        return []


def github_repo_readme(owner: str, repo: str, max_chars: int = 4000) -> str:
    if not _HAS_REQ:
        return ""
    try:
        r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/readme",
                         headers=_gh_headers(), timeout=15)
        if r.status_code != 200:
            return ""
        d = r.json()
        content = d.get("content", "")
        if d.get("encoding") == "base64":
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            return decoded[:max_chars]
        return ""
    except Exception:
        return ""


def github_list_issues(owner: str, repo: str, state: str = "open",
                       max_results: int = 10) -> List[Dict[str, Any]]:
    if not _HAS_REQ:
        return []
    try:
        r = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": max_results},
            headers=_gh_headers(), timeout=15,
        )
        if r.status_code != 200:
            return []
        out = []
        for it in r.json():
            if "pull_request" in it:
                continue  # filtrar PRs
            out.append({
                "number": it["number"],
                "title": it["title"],
                "url": it["html_url"],
                "state": it["state"],
                "labels": [l["name"] for l in it.get("labels", [])],
                "comments": it.get("comments", 0),
            })
        return out
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────
#  Jupyter Notebook (.ipynb) export/import simple
# ──────────────────────────────────────────────────────────────────────
def chat_to_notebook(messages: List[Dict[str, str]], title: str = "DeepNova export") -> Dict[str, Any]:
    """Convierte una lista de mensajes en un notebook .ipynb mínimo válido."""
    cells = [{
        "cell_type": "markdown",
        "metadata": {},
        "source": [f"# {title}\n\nExportado desde DeepNova"],
    }]
    for m in messages or []:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if role == "user":
            cells.append({
                "cell_type": "markdown", "metadata": {},
                "source": [f"## 🧑 Usuario\n\n{content}"],
            })
        elif role == "assistant":
            # extrae bloques ```python``` como celdas de código
            blocks = _split_code_blocks(content)
            for b in blocks:
                if b["type"] == "code" and b["lang"] in ("python", "py"):
                    cells.append({
                        "cell_type": "code",
                        "metadata": {},
                        "execution_count": None,
                        "source": b["text"].splitlines(keepends=True),
                        "outputs": [],
                    })
                else:
                    src = b["text"]
                    if b["type"] == "code":
                        src = f"```{b['lang']}\n{b['text']}\n```"
                    cells.append({
                        "cell_type": "markdown", "metadata": {},
                        "source": [f"## 🤖 DeepNova\n\n{src}"],
                    })
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4, "nbformat_minor": 5,
    }
    return nb


def _split_code_blocks(text: str) -> List[Dict[str, str]]:
    """Divide texto en celdas alternando markdown / código."""
    parts: List[Dict[str, str]] = []
    pattern = re.compile(r"```(\w+)?\n([\s\S]*?)```")
    last = 0
    for m in pattern.finditer(text or ""):
        if m.start() > last:
            txt = text[last:m.start()].strip()
            if txt:
                parts.append({"type": "md", "lang": "", "text": txt})
        parts.append({"type": "code", "lang": m.group(1) or "", "text": m.group(2)})
        last = m.end()
    if last < len(text or ""):
        rem = text[last:].strip()
        if rem:
            parts.append({"type": "md", "lang": "", "text": rem})
    if not parts:
        parts.append({"type": "md", "lang": "", "text": text or ""})
    return parts


# ──────────────────────────────────────────────────────────────────────
#  Snippets (gestión local persistente)
# ──────────────────────────────────────────────────────────────────────
SNIPPETS_FILE = os.environ.get("SNIPPETS_FILE", "snippets.json")
_snippets: Dict[str, Dict[str, Any]] = {}


def _load_snippets() -> None:
    global _snippets
    if os.path.exists(SNIPPETS_FILE):
        try:
            with open(SNIPPETS_FILE, "r", encoding="utf-8") as f:
                _snippets = json.load(f) or {}
        except Exception:
            _snippets = {}


def _save_snippets() -> None:
    try:
        with open(SNIPPETS_FILE, "w", encoding="utf-8") as f:
            json.dump(_snippets, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_load_snippets()


def snippet_save(name: str, code: str, lang: str = "python", desc: str = "") -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "name vacío"}
    _snippets[name] = {
        "name": name, "code": code, "lang": lang, "desc": desc,
        "created_at": __import__("time").time(),
    }
    _save_snippets()
    return {"ok": True, "name": name}


def snippet_get(name: str) -> Optional[Dict[str, Any]]:
    return _snippets.get(name)


def snippet_list() -> List[Dict[str, Any]]:
    return [
        {"name": n, "lang": s.get("lang"), "desc": s.get("desc"), "size": len(s.get("code", ""))}
        for n, s in _snippets.items()
    ]


def snippet_delete(name: str) -> bool:
    if name in _snippets:
        del _snippets[name]
        _save_snippets()
        return True
    return False


# ──────────────────────────────────────────────────────────────────────
#  VSCode-friendly formatting
# ──────────────────────────────────────────────────────────────────────
def vscode_format_code(code: str, lang: str = "python", filename: Optional[str] = None) -> str:
    """Formato bloque de código con metadata útil para VSCode (link a línea)."""
    header = f"```{lang}"
    if filename:
        header += f" filename={filename}"
    return f"{header}\n{code}\n```"
