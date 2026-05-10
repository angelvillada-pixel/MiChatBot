/* ════════════════════════════════════════════════════════════════════
   DeepNova /v2 · app.js
   Orquestador principal: bind de header, modales, prompts, settings,
   y arranque coordinado de DN.ui + DN.chat + DN.sandbox.
   ════════════════════════════════════════════════════════════════════ */

(function () {

    const ready = (cb) => {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", cb);
        } else cb();
    };

    ready(() => {
        const { $, $$, el, toast, cfg } = DN;

        // ─── Tema inicial ──────────────────────────────────────────
        const savedTheme = localStorage.getItem(cfg.LS_THEME) || cfg.DEFAULT_THEME;
        DN.applyTheme(savedTheme);

        // ─── Restaurar sidebar ─────────────────────────────────────
        DN.restoreSidebar();

        // ─── Resizer + atajos + settings ───────────────────────────
        DN.initResizer();
        DN.initShortcuts();
        DN.bindSettings();

        // ─── Inicializar módulos chat y sandbox ────────────────────
        DN.sandbox.init();
        DN.chat.init();

        // ─── Header buttons ────────────────────────────────────────
        $("#btnSidebar")?.addEventListener("click", DN.toggleSidebar);

        $("#btnNewChat")?.addEventListener("click", () => {
            DN.chat.newSession();
            toast("Nueva conversación creada", "success", 1400);
        });

        $("#btnUltra")?.addEventListener("click", (e) => {
            const on = DN.chat.toggleFlag("ultra");
            e.currentTarget.classList.toggle("active", on);
            toast(on ? "Modo ULTRA activado 🌟" : "Modo ULTRA desactivado", on ? "success" : "info", 1500);
        });

        $("#btnMulti")?.addEventListener("click", (e) => {
            const on = DN.chat.toggleFlag("multi");
            e.currentTarget.classList.toggle("active", on);
            toast(on ? "Multi-IA activado 🧠" : "Multi-IA desactivado", on ? "success" : "info", 1500);
        });

        $("#btnPrompts")?.addEventListener("click", () => {
            DN.openModal("modalPrompts");
            loadPromptLibrary();
        });

        $("#btnTheme")?.addEventListener("click", () => {
            DN.openModal("modalTheme");
            DN.loadThemeGrid();
        });

        $("#btnSettings")?.addEventListener("click", () => {
            DN.openModal("modalSettings");
            refreshHealthInfo();
        });

        // ─── Input area ────────────────────────────────────────────
        const promptInput = $("#promptInput");
        const charCount   = $("#charCount");

        promptInput?.addEventListener("input", () => {
            const v = promptInput.value;
            promptInput.style.height = "auto";
            promptInput.style.height = Math.min(promptInput.scrollHeight, 200) + "px";
            if (charCount) charCount.textContent = `${v.length} chars`;
        });

        promptInput?.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                DN.chat.send();
            }
        });

        $("#btnSend")?.addEventListener("click", () => DN.chat.send());

        $("#btnAttach")?.addEventListener("click", () => $("#fileInput")?.click());
        $("#fileInput")?.addEventListener("change", (e) => {
            const f = e.target.files?.[0];
            if (f) DN.chat.setAttachment(f);
        });
        $("#attachClose")?.addEventListener("click", () => DN.chat.clearAttachment());

        // ─── Dictado por voz ───────────────────────────────────────
        let activeRec = null;
        $("#btnMic")?.addEventListener("click", (e) => {
            if (activeRec) {
                try { activeRec.stop(); } catch {}
                activeRec = null;
                e.currentTarget.classList.remove("active");
                return;
            }
            e.currentTarget.classList.add("active");
            activeRec = DN.dictate((txt) => {
                if (promptInput) {
                    promptInput.value = (promptInput.value + " " + txt).trim();
                    promptInput.dispatchEvent(new Event("input"));
                }
                e.currentTarget.classList.remove("active");
                activeRec = null;
            });
            if (!activeRec) e.currentTarget.classList.remove("active");
        });

        // ─── Settings modal acciones ───────────────────────────────
        $("#btnExportHistory")?.addEventListener("click", () => {
            window.open(cfg.API.export, "_blank");
        });

        $("#btnHealth")?.addEventListener("click", refreshHealthInfo);

        $("#btnClearAll")?.addEventListener("click", () => DN.chat.clearAll());

        // ─── Drag & drop archivos al chat ──────────────────────────
        const dropTarget = $("#paneChat");
        ["dragenter", "dragover"].forEach(ev => {
            dropTarget?.addEventListener(ev, (e) => {
                e.preventDefault(); e.stopPropagation();
                dropTarget.style.outline = "3px dashed var(--accent-color)";
                dropTarget.style.outlineOffset = "-10px";
            });
        });
        ["dragleave", "drop"].forEach(ev => {
            dropTarget?.addEventListener(ev, (e) => {
                e.preventDefault(); e.stopPropagation();
                dropTarget.style.outline = "";
            });
        });
        dropTarget?.addEventListener("drop", (e) => {
            const f = e.dataTransfer?.files?.[0];
            if (f) DN.chat.setAttachment(f);
        });

        // ─── Auto-mostrar sandbox en móvil cuando hay código ───────
        DN.events.on("sessionChange", () => {
            DN.$("#dnApp")?.classList.remove("show-sandbox");
        });

        // ─── Health periódico (status dot) ─────────────────────────
        const checkHealth = async () => {
            const dot = $("#statusDot");
            try {
                const r = await fetch(cfg.API.health, { method: "GET" });
                if (r.ok) {
                    dot?.classList.remove("offline");
                    const j = await r.json().catch(() => ({}));
                    if (j.version) {
                        const v = $("#versionLabel");
                        if (v) v.textContent = "DeepNova " + j.version;
                        const cv = $("#cfgVersion");
                        if (cv) cv.textContent = j.version + " · build " + (j.build || "—");
                    }
                } else {
                    dot?.classList.add("offline");
                }
            } catch {
                dot?.classList.add("offline");
            }
        };
        checkHealth();
        setInterval(checkHealth, 60_000);

        // ─── Prompt library loader ─────────────────────────────────
        async function loadPromptLibrary() {
            const cats = $("#promptCats");
            const list = $("#promptList");
            if (!cats || !list) return;
            cats.innerHTML = "";
            list.innerHTML = '<div class="dn-skeleton"></div><div class="dn-skeleton"></div><div class="dn-skeleton"></div>';

            try {
                const r = await fetch(cfg.API.prompts);
                const j = await r.json();
                const library = j.library || {};
                const keys = Object.keys(library);
                if (!keys.length) {
                    list.innerHTML = '<div style="color:var(--text-muted)">Sin prompts disponibles.</div>';
                    return;
                }
                let activeCat = keys[0];
                const renderCat = (k) => {
                    activeCat = k;
                    cats.querySelectorAll("button").forEach(b => b.classList.toggle("active", b.dataset.k === k));
                    list.innerHTML = "";
                    (library[k] || []).forEach(p => {
                        const item = el("div", {
                            cls: "dn-prompt-item",
                            on: { click: () => {
                                const ti = $("#promptInput");
                                if (ti) {
                                    ti.value = p.prompt + " ";
                                    ti.dispatchEvent(new Event("input"));
                                    ti.focus();
                                }
                                DN.closeModal("modalPrompts");
                                toast(`Prompt "${p.title}" cargado`, "success", 1400);
                            } }
                        },
                            el("div", { cls: "title", html: `${p.icon || "💡"} ${DN.escapeHTML(p.title)}` }),
                            el("div", { cls: "preview", text: p.prompt })
                        );
                        list.appendChild(item);
                    });
                };
                keys.forEach(k => {
                    cats.appendChild(el("button", {
                        text: k.charAt(0).toUpperCase() + k.slice(1),
                        attrs: { "data-k": k },
                        cls: k === activeCat ? "active" : "",
                        on: { click: () => renderCat(k) }
                    }));
                });
                renderCat(activeCat);
            } catch (e) {
                console.warn("[prompts]", e);
                list.innerHTML = `<div style="color:var(--danger)">Error: ${DN.escapeHTML(e.message || e)}</div>`;
            }
        }

        // ─── Health info refresh ───────────────────────────────────
        async function refreshHealthInfo() {
            try {
                const r = await fetch(cfg.API.health);
                if (!r.ok) throw new Error("HTTP " + r.status);
                const j = await r.json();
                const cv = $("#cfgVersion");
                if (cv) cv.textContent = `${j.version || "?"} · build ${j.build || "—"}`;
                const cb = $("#cfgBackend");
                if (cb) cb.textContent = `/v2 → DeepNova core (${(j.models || []).length} modelos · NeuroCore-X: ${j.neurocore_x ? "ON" : "OFF"})`;
                toast("Backend OK ✓", "success", 1400);
            } catch (e) {
                toast("Backend no responde", "error");
            }
        }

        // ─── Welcome toast ─────────────────────────────────────────
        setTimeout(() => {
            toast("DeepNova /v2 listo · UI premium · pulsa ⌘+B para historial", "success", 3500);
        }, 500);

        console.log("%c[DeepNova /v2] App lista 🚀",
            "background:linear-gradient(90deg,#6366f1,#ec4899);color:#fff;padding:6px 14px;border-radius:8px;font-weight:bold;");
    });

})();
