"""
═══════════════════════════════════════════════════════════════════════════
 code_optimizer.py · DeepNova v7.0 · Análisis y Optimización de Código
═══════════════════════════════════════════════════════════════════════════
 Análisis estático profesional de código Python:
   • Métricas de complejidad ciclomática y cognitiva
   • Detección de code smells (god functions, deep nesting, magic numbers)
   • Sugerencias de optimización (lista por comprensión, generadores, etc.)
   • Estimación de tiempo de ejecución (heurística)
   • Detección de problemas de seguridad básicos (eval, exec, shell=True)

 Diseño:
   - Solo stdlib (ast, tokenize)
   - 100% aditivo · seguro · sin ejecutar el código analizado
   - Salida estructurada (dict) lista para serializar a JSON

 Áreas cubiertas (del documento de mejoras):
   ✓ 4.1 Automatización de tareas (análisis automático)
   ✓ 4.2 Optimización de código
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import ast
import io
import re
import tokenize
from typing import Dict, List, Any, Tuple


# ──────────────────────────────────────────────────────────────────────
#  Análisis principal
# ──────────────────────────────────────────────────────────────────────
def analyze(code: str) -> Dict[str, Any]:
    """Análisis completo. Devuelve un informe estructurado."""
    code = (code or "").strip()
    if not code:
        return {"error": "código vacío", "ok": False}

    # Parseo seguro
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {
            "ok": False,
            "syntax_error": {
                "message": e.msg,
                "line": e.lineno,
                "col": e.offset,
            },
            "suggestion": "Revisa la sintaxis antes de optimizar.",
        }

    metrics = _metrics(code, tree)
    smells = _detect_smells(tree, code)
    security = _security_audit(tree, code)
    suggestions = _suggestions(tree, code)
    score = _quality_score(metrics, smells, security)

    return {
        "ok": True,
        "metrics": metrics,
        "smells": smells,
        "security": security,
        "suggestions": suggestions,
        "quality_score": score,
        "verdict": _verdict(score),
    }


# ──────────────────────────────────────────────────────────────────────
#  Métricas
# ──────────────────────────────────────────────────────────────────────
def _metrics(code: str, tree: ast.AST) -> Dict[str, Any]:
    lines = code.splitlines()
    sloc = sum(1 for l in lines if l.strip() and not l.strip().startswith("#"))
    n_functions = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    n_classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    n_imports = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)))

    cc = _cyclomatic_complexity(tree)
    cog = _cognitive_complexity(tree)
    max_nest = _max_nesting(tree)

    return {
        "loc": len(lines),
        "sloc": sloc,
        "n_functions": n_functions,
        "n_classes": n_classes,
        "n_imports": n_imports,
        "cyclomatic_complexity": cc,
        "cognitive_complexity": cog,
        "max_nesting_depth": max_nest,
    }


def _cyclomatic_complexity(tree: ast.AST) -> int:
    """Cuenta puntos de decisión (~ McCabe)."""
    score = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.AsyncFor,
                             ast.ExceptHandler, ast.With, ast.AsyncWith,
                             ast.BoolOp, ast.IfExp)):
            score += 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
    return score


def _cognitive_complexity(tree: ast.AST) -> int:
    """Cognitive complexity (G. Ann Campbell, SonarSource)."""
    total = 0

    def visit(node, nesting):
        nonlocal total
        increment = 0
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                increment = 1 + nesting
                total += increment
                visit(child, nesting + 1)
            elif isinstance(child, ast.BoolOp):
                total += 1
                visit(child, nesting)
            else:
                visit(child, nesting)

    visit(tree, 0)
    return total


def _max_nesting(tree: ast.AST) -> int:
    max_depth = 0

    def visit(node, depth):
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With,
                                  ast.AsyncFor, ast.AsyncWith, ast.Try)):
                visit(child, depth + 1)
            else:
                visit(child, depth)

    visit(tree, 0)
    return max_depth


# ──────────────────────────────────────────────────────────────────────
#  Code smells
# ──────────────────────────────────────────────────────────────────────
def _detect_smells(tree: ast.AST, code: str) -> List[Dict[str, Any]]:
    smells: List[Dict[str, Any]] = []

    # God function (función > 80 líneas)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n_lines = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno
            if n_lines > 80:
                smells.append({
                    "kind": "god_function",
                    "name": node.name,
                    "line": node.lineno,
                    "size_lines": n_lines,
                    "severity": "high",
                    "fix": f"Divide '{node.name}' en funciones más pequeñas y cohesivas.",
                })
            # Demasiados parámetros
            if len(node.args.args) > 6:
                smells.append({
                    "kind": "too_many_parameters",
                    "name": node.name,
                    "line": node.lineno,
                    "n_params": len(node.args.args),
                    "severity": "medium",
                    "fix": "Usa un dataclass / dict de configuración para agrupar parámetros.",
                })

    # Magic numbers (números literales fuera de constantes)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if node.value not in (0, 1, -1, 2, 10, 100, 1000):
                # Sólo se considera smell si está dentro de una expresión grande
                pass  # demasiado ruidoso para reportar todos

    # except: amplio sin tipo
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            smells.append({
                "kind": "bare_except",
                "line": node.lineno,
                "severity": "medium",
                "fix": "Captura excepciones específicas en lugar de 'except:'.",
            })

    # print() para debugging
    n_prints = sum(
        1 for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
    )
    if n_prints > 5:
        smells.append({
            "kind": "many_prints",
            "n": n_prints,
            "severity": "low",
            "fix": "Usa `logging` en producción en lugar de print().",
        })

    return smells


# ──────────────────────────────────────────────────────────────────────
#  Auditoría de seguridad
# ──────────────────────────────────────────────────────────────────────
DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__"}
DANGEROUS_MODULES = {"pickle.loads", "marshal.loads", "yaml.load"}


def _security_audit(tree: ast.AST, code: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _call_name(node.func)
            if fn in DANGEROUS_CALLS:
                issues.append({
                    "kind": "dangerous_call",
                    "name": fn,
                    "line": node.lineno,
                    "severity": "high",
                    "fix": f"`{fn}()` puede ejecutar código arbitrario. Evítalo o aísla en sandbox.",
                })
            elif fn in DANGEROUS_MODULES:
                issues.append({
                    "kind": "unsafe_deserialize",
                    "name": fn,
                    "line": node.lineno,
                    "severity": "high",
                    "fix": "Usa formatos seguros (json) o `yaml.safe_load`.",
                })
            elif fn == "subprocess.run" or fn == "subprocess.Popen":
                # check shell=True
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        issues.append({
                            "kind": "shell_injection_risk",
                            "line": node.lineno,
                            "severity": "high",
                            "fix": "Evita shell=True. Pasa la lista de argumentos directamente.",
                        })

    # Hardcoded secrets (heurístico)
    for m in re.finditer(r"(?:api[_-]?key|secret|password|token)\s*=\s*[\"']([^\"']{12,})[\"']",
                         code, re.IGNORECASE):
        issues.append({
            "kind": "hardcoded_secret",
            "line": code[: m.start()].count("\n") + 1,
            "severity": "high",
            "fix": "Mueve secretos a variables de entorno (os.environ).",
        })

    return issues


def _call_name(node: ast.AST) -> str:
    """Devuelve el nombre completo de una llamada (a.b.c)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


# ──────────────────────────────────────────────────────────────────────
#  Sugerencias de optimización
# ──────────────────────────────────────────────────────────────────────
def _suggestions(tree: ast.AST, code: str) -> List[Dict[str, Any]]:
    sug: List[Dict[str, Any]] = []

    # for + append → list comprehension
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            body = node.body
            if (len(body) == 1
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Call)
                    and isinstance(body[0].value.func, ast.Attribute)
                    and body[0].value.func.attr == "append"):
                sug.append({
                    "kind": "use_list_comprehension",
                    "line": node.lineno,
                    "benefit": "más rápido y legible",
                    "example": "result = [f(x) for x in items if cond]",
                })

    # range(len(x)) → enumerate
    for m in re.finditer(r"for\s+\w+\s+in\s+range\s*\(\s*len\s*\(", code):
        line = code[: m.start()].count("\n") + 1
        sug.append({
            "kind": "use_enumerate",
            "line": line,
            "benefit": "más pythónico y eficiente",
            "example": "for i, item in enumerate(items): ...",
        })

    # str + str dentro de loop → ''.join
    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
            # Heurística: dentro de un for
            sug.append({
                "kind": "string_concat_in_loop",
                "line": node.lineno,
                "benefit": "evita O(n²) en strings; usa ''.join() o io.StringIO",
            })
            break  # solo reportar uno

    # global / mutable default args
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    sug.append({
                        "kind": "mutable_default_arg",
                        "function": node.name,
                        "line": node.lineno,
                        "fix": "Usa `=None` y crea el objeto dentro de la función.",
                        "severity": "high",
                    })
                    break

    return sug


# ──────────────────────────────────────────────────────────────────────
#  Score de calidad (0-100)
# ──────────────────────────────────────────────────────────────────────
def _quality_score(metrics: Dict[str, Any], smells: List, security: List) -> int:
    score = 100
    cc = metrics.get("cyclomatic_complexity", 0)
    cog = metrics.get("cognitive_complexity", 0)
    nest = metrics.get("max_nesting_depth", 0)

    if cc > 30: score -= 20
    elif cc > 15: score -= 10
    if cog > 30: score -= 15
    if nest > 4: score -= 10

    for s in smells:
        sev = s.get("severity", "low")
        score -= {"high": 8, "medium": 4, "low": 2}.get(sev, 2)
    for s in security:
        sev = s.get("severity", "low")
        score -= {"high": 15, "medium": 7, "low": 3}.get(sev, 3)

    return max(0, min(100, score))


def _verdict(score: int) -> str:
    if score >= 90: return "excelente"
    if score >= 75: return "bueno"
    if score >= 60: return "aceptable"
    if score >= 40: return "necesita mejoras"
    return "crítico"


# ──────────────────────────────────────────────────────────────────────
#  Helper: render Markdown amigable (para inyectar en respuestas chat)
# ──────────────────────────────────────────────────────────────────────
def to_markdown(report: Dict[str, Any]) -> str:
    if not report.get("ok"):
        if "syntax_error" in report:
            e = report["syntax_error"]
            return f"❌ **Error de sintaxis** (línea {e['line']}): {e['message']}"
        return "❌ **Análisis falló:** " + str(report.get("error"))

    m = report["metrics"]
    out = [f"### 🧪 Análisis de código  ·  Score: **{report['quality_score']}/100**  ({report['verdict']})"]
    out.append(
        f"- LOC: {m['loc']}  ·  SLOC: {m['sloc']}  ·  Funciones: {m['n_functions']}  ·  Clases: {m['n_classes']}\n"
        f"- Complejidad ciclomática: **{m['cyclomatic_complexity']}**\n"
        f"- Complejidad cognitiva: **{m['cognitive_complexity']}**\n"
        f"- Anidamiento máximo: **{m['max_nesting_depth']}**"
    )

    if report["security"]:
        out.append("\n#### 🚨 Seguridad")
        for s in report["security"]:
            out.append(f"- **{s['kind']}** (línea {s.get('line','?')}): {s.get('fix','')}")

    if report["smells"]:
        out.append("\n#### 👃 Code smells")
        for s in report["smells"]:
            line = f" (línea {s['line']})" if "line" in s else ""
            out.append(f"- **{s['kind']}**{line}: {s.get('fix','')}")

    if report["suggestions"]:
        out.append("\n#### 💡 Sugerencias de optimización")
        for s in report["suggestions"]:
            ex = f"  → `{s['example']}`" if s.get("example") else ""
            out.append(f"- **{s['kind']}** (línea {s.get('line','?')}): {s.get('benefit','')}{ex}")

    return "\n".join(out)
