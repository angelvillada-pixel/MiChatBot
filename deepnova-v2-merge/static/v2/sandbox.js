/* ════════════════════════════════════════════════════════════════════
   DeepNova /v2 · sandbox.js
   Sandbox de previsualización: parsea bloques ```html|css|js|python```
   de la respuesta, los renderiza en iframe y/o ejecuta Python via /execute.
   Inspirado en Facil-con-IA, adaptado al backend Deep Nova.
   ════════════════════════════════════════════════════════════════════ */

DN.sandbox = (function () {

    const { $, $$, el, toast, cfg } = DN;

    const state = {
        currentHTML: "",
        lastRaw:     "",
        lastBlocks:  { html: "", css: "", js: "", python: "", others: [] },
        activeTab:   "preview"
    };

    // ─── Parseo de bloques de código ───────────────────────────────
    const parseBlocks = (text) => {
        const re = /```(\w+)?\s*\n?([\s\S]*?)```/g;
        const out = { html: "", css: "", js: "", python: "", others: [] };
        let m;
        while ((m = re.exec(text)) !== null) {
            const lang = (m[1] || "").toLowerCase().trim();
            const code = m[2].replace(/^\s*\n/, "").replace(/\s+$/, "");
            if (lang === "html" || lang === "xml")               out.html    += code + "\n";
            else if (lang === "css")                              out.css     += code + "\n";
            else if (lang === "javascript" || lang === "js")      out.js      += code + "\n";
            else if (lang === "python" || lang === "py")          out.python  += code + "\n";
            else if (lang === "json" || lang === "yaml")          out.others.push({lang, code});
            else if (!lang) {
                // heurística
                if (/<html|<body|<div|<!doctype/i.test(code))            out.html += code + "\n";
                else if (/^\s*[.#@\w-]+\s*\{[^}]*\}/m.test(code))         out.css  += code + "\n";
                else if (/(\bdef |\bimport |\bprint\()/.test(code))       out.python += code + "\n";
                else                                                       out.others.push({lang: "txt", code});
            } else {
                out.others.push({lang, code});
            }
        }
        return out;
    };

    // ─── Render visual: HTML+CSS+JS combinados en iframe ───────────
    const renderHTML = (html, save = true) => {
        const frame = $("#sandboxFrame");
        const empty = $("#sandboxEmpty");
        if (!frame) return;
        empty?.classList.add("hidden");
        frame.classList.remove("hidden");
        try {
            frame.removeAttribute("srcdoc");
            frame.srcdoc = html;
        } catch (e) {
            console.warn("[sandbox] srcdoc fallback", e);
            const blob = new Blob([html], {type: "text/html"});
            frame.src = URL.createObjectURL(blob);
        }
        state.currentHTML = html;
        if (save) {
            const s = DN.chat?.currentSession?.();
            if (s) { s.renderedCode = html; }
        }
    };

    const buildHTML = (b) => `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DeepNova Sandbox</title>
<style>
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  ${b.css || ""}
</style>
</head>
<body>
${b.html || ""}
<script>
try {
  ${b.js || ""}
} catch (e) {
  document.body.insertAdjacentHTML("beforeend",
    '<pre style="color:#dc2626;background:#fef2f2;padding:10px;border-radius:6px;">⚠ JS error: ' + (e.message || e) + '</pre>');
}
<\/script>
</body>
</html>`;

    // ─── Ejecutar Python via /execute (backend Deep Nova) ──────────
    const runPython = async (code) => {
        const out = $("#sandboxPython");
        if (!out) return;
        out.classList.remove("hidden");
        $("#sandboxFrame")?.classList.add("hidden");
        $("#sandboxCode")?.classList.add("hidden");
        $("#sandboxEmpty")?.classList.add("hidden");
        out.textContent = "⏳ Ejecutando Python...\n";
        switchTab("python");
        try {
            const r = await fetch(cfg.API.execute, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    code: code,
                    session_id: DN.getUID()
                })
            });
            const j = await r.json();
            const txt = (j.output || "") +
                        (j.error ? "\n❌ " + j.error : "") +
                        (j.success === false ? "\n[failed]" : "");
            out.textContent = txt.trim() || "(sin salida)";
        } catch (e) {
            out.textContent = "❌ Error: " + (e.message || e);
        }
    };

    // ─── Parse + render principal (llamado tras cada respuesta) ────
    const parseAndRender = (raw) => {
        state.lastRaw = raw || "";
        const b = parseBlocks(raw || "");
        state.lastBlocks = b;

        const code = $("#sandboxCode");
        if (code) {
            code.textContent = (b.html ? "/* HTML */\n" + b.html + "\n" : "")
                             + (b.css  ? "/* CSS */\n"  + b.css  + "\n" : "")
                             + (b.js   ? "/* JS */\n"   + b.js   + "\n" : "")
                             + (b.python ? "# Python\n" + b.python + "\n" : "")
                             + (b.others.length ? "/* Otros */\n" + b.others.map(o => `[${o.lang}]\n${o.code}`).join("\n\n") : "");
        }

        if (b.html.trim() || b.css.trim() || b.js.trim()) {
            renderHTML(buildHTML(b));
            switchTab("preview");
        } else if (b.python.trim()) {
            // No ejecutar automáticamente; mostrar código y permitir click ▶️
            const py = $("#sandboxPython");
            if (py) {
                py.textContent = "# Código Python detectado\n# Pulsa ▶️ en el chat para ejecutarlo\n\n" + b.python;
                py.classList.remove("hidden");
                $("#sandboxFrame")?.classList.add("hidden");
                $("#sandboxEmpty")?.classList.add("hidden");
                switchTab("python");
            }
        } else {
            // Sin código: dejar el sandbox como estaba o vaciar
            if (!state.currentHTML) {
                $("#sandboxFrame")?.classList.add("hidden");
                $("#sandboxCode")?.classList.add("hidden");
                $("#sandboxPython")?.classList.add("hidden");
                $("#sandboxEmpty")?.classList.remove("hidden");
            }
        }
    };

    // ─── Tabs ──────────────────────────────────────────────────────
    const switchTab = (key) => {
        state.activeTab = key;
        $$(".dn-sandbox-tabs .dn-tab").forEach(t => {
            t.classList.toggle("active", t.dataset.tab === key);
        });
        $("#sandboxFrame")?.classList.toggle("hidden", key !== "preview");
        $("#sandboxCode")?.classList.toggle("hidden",   key !== "code");
        $("#sandboxPython")?.classList.toggle("hidden", key !== "python");
        if (key === "preview" && !state.currentHTML) {
            $("#sandboxEmpty")?.classList.remove("hidden");
        } else {
            $("#sandboxEmpty")?.classList.add("hidden");
        }
    };

    // ─── Reset ────────────────────────────────────────────────────
    const reset = () => {
        state.currentHTML = "";
        const fr = $("#sandboxFrame");
        if (fr) { fr.removeAttribute("srcdoc"); fr.srcdoc = ""; fr.classList.add("hidden"); }
        $("#sandboxCode")  && ($("#sandboxCode").textContent = "");
        $("#sandboxPython")&& ($("#sandboxPython").textContent = "");
        $("#sandboxCode")?.classList.add("hidden");
        $("#sandboxPython")?.classList.add("hidden");
        $("#sandboxEmpty")?.classList.remove("hidden");
        switchTab("preview");
    };

    // ─── Descargas ─────────────────────────────────────────────────
    const downloadHTML = () => {
        if (!state.currentHTML) {
            toast("El sandbox está vacío", "warn"); return;
        }
        const blob = new Blob([state.currentHTML], {type: "text/html"});
        const a = el("a", { attrs: { href: URL.createObjectURL(blob), download: "deepnova_sandbox.html" } });
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast("HTML descargado", "success", 1600);
    };

    const downloadZIP = async () => {
        if (!window.JSZip) {
            toast("JSZip no cargado todavía", "warn"); return;
        }
        const raw = state.lastRaw;
        if (!raw) { toast("Sin respuesta IA reciente", "warn"); return; }
        const zip = new JSZip();
        const re = /```(\w+)?\s*\n?([\s\S]*?)```/g;
        let m, count = 0;
        while ((m = re.exec(raw)) !== null) {
            const lang = (m[1] || "").toLowerCase();
            const code = m[2].trim();
            let fname;
            switch (lang) {
                case "html": case "xml": fname = "index.html"; break;
                case "css":              fname = "style.css"; break;
                case "javascript":
                case "js":               fname = "script.js"; break;
                case "python":
                case "py":               fname = "main.py"; break;
                case "json":             fname = "data.json"; break;
                case "yaml": case "yml": fname = "config.yaml"; break;
                case "md":               fname = "README.md"; break;
                default:                 fname = `block_${++count}.${lang || "txt"}`;
            }
            zip.file(fname, code);
        }
        if (Object.keys(zip.files).length === 0) {
            toast("No hay bloques de código para empaquetar", "warn"); return;
        }
        const blob = await zip.generateAsync({ type: "blob" });
        const a = el("a", { attrs: { href: URL.createObjectURL(blob), download: "DeepNova_Project.zip" } });
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast("Proyecto ZIP descargado", "success", 1600);
    };

    const openInNewTab = () => {
        if (!state.currentHTML) { toast("Sandbox vacío", "warn"); return; }
        const w = window.open();
        if (!w) { toast("Popup bloqueado", "error"); return; }
        w.document.open();
        w.document.write(state.currentHTML);
        w.document.close();
    };

    // ─── Inicialización ───────────────────────────────────────────
    const init = () => {
        $$(".dn-sandbox-tabs .dn-tab").forEach(t => {
            t.addEventListener("click", () => switchTab(t.dataset.tab));
        });
        $("#btnDownloadHTML")?.addEventListener("click", downloadHTML);
        $("#btnDownloadZIP")?.addEventListener("click", downloadZIP);
        $("#btnOpenTab")?.addEventListener("click", openInNewTab);

        $("#btnSandboxBack")?.addEventListener("click", () => {
            DN.$("#dnApp")?.classList.remove("show-sandbox");
        });

        // Botón ▶️ del input: ejecuta el último python detectado
        $("#btnExecute")?.addEventListener("click", () => {
            const py = state.lastBlocks?.python;
            if (!py?.trim()) { toast("No hay Python en la última respuesta", "warn"); return; }
            runPython(py);
        });
    };

    return {
        init, parseAndRender, renderHTML,
        runPython, reset,
        downloadHTML, downloadZIP, openInNewTab,
        getCurrent: () => state.currentHTML,
        switchTab,
        _state: state
    };
})();

console.log("[DN.sandbox] cargado");
