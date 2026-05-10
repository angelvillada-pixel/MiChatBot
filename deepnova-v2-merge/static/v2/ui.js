/* ════════════════════════════════════════════════════════════════════
   DeepNova /v2 · ui.js
   Capa visual: sidebar, modales, toasts, temas, atajos, helpers DOM.
   No depende de backend (solo DOM + localStorage).
   ════════════════════════════════════════════════════════════════════ */

window.DN = window.DN || {};

DN.cfg = {
    LS_THEME:        "dn_v2_theme",
    LS_SIDEBAR:      "dn_v2_sidebar_state",
    LS_SETTINGS:     "dn_v2_settings",
    LS_SESSIONS:     "dn_v2_sessions",
    LS_CURRENT_SESS: "dn_v2_current_session",
    LS_PERSIST_UID:  "dn_v2_uid",
    DEFAULT_THEME:   "dark",
    BACKEND:         "",   // mismo origen
    API: {
        chat:       "/chat",
        execute:    "/execute",
        health:     "/health",
        themes:     "/api/themes",
        prompts:    "/api/prompts",
        suggestions:"/api/suggestions",
        shortcuts:  "/api/shortcuts",
        sessionsList:"/sessions",
        sessions:   "/sessions",
        feedback:   "/api/feedback",
        export:     "/history/export",
        clear:      "/clear"
    }
};

/* ─── Helpers DOM ─────────────────────────────────────────────────── */
DN.$  = (sel, root = document) => root.querySelector(sel);
DN.$$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

DN.el = (tag, opts = {}, ...children) => {
    const node = document.createElement(tag);
    if (opts.cls)   node.className = opts.cls;
    if (opts.id)    node.id = opts.id;
    if (opts.text)  node.textContent = opts.text;
    if (opts.html)  node.innerHTML = opts.html;
    if (opts.attrs) Object.entries(opts.attrs).forEach(([k,v]) => node.setAttribute(k, v));
    if (opts.style) Object.assign(node.style, opts.style);
    if (opts.on)    Object.entries(opts.on).forEach(([ev,fn]) => node.addEventListener(ev, fn));
    children.flat().forEach(c => {
        if (c == null) return;
        node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
};

DN.escapeHTML = (s) => String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");

DN.uid = () => "u_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

DN.formatTime = (ts) => {
    try {
        const d = (ts instanceof Date) ? ts : new Date(ts);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch { return ""; }
};

DN.copyToClipboard = async (text) => {
    try {
        await navigator.clipboard.writeText(text);
        DN.toast("Copiado al portapapeles", "success");
    } catch {
        DN.toast("No se pudo copiar", "error");
    }
};

/* ─── Toasts ──────────────────────────────────────────────────────── */
DN.toast = (msg, level = "info", ms = 3200) => {
    const wrap = DN.$("#toastWrap");
    if (!wrap) return;
    const ico = ({ success: "✅", error: "❌", warn: "⚠️", info: "💡" })[level] || "💡";
    const node = DN.el("div", { cls: `dn-toast ${level}` },
        DN.el("span", { cls: "ico", text: ico }),
        DN.el("span", { cls: "msg", text: msg })
    );
    wrap.appendChild(node);
    setTimeout(() => {
        node.classList.add("hide");
        setTimeout(() => node.remove(), 280);
    }, ms);
};

/* ─── Modales ─────────────────────────────────────────────────────── */
DN.openModal = (id) => {
    const m = DN.$(`#${id}`);
    if (m) m.classList.remove("hidden");
};
DN.closeModal = (id) => {
    const m = DN.$(`#${id}`);
    if (m) m.classList.add("hidden");
};

document.addEventListener("click", (e) => {
    if (e.target.matches("[data-close]") || e.target.closest("[data-close]")) {
        const overlay = e.target.closest(".dn-modal-overlay");
        if (overlay) overlay.classList.add("hidden");
    }
    // Click fuera del contenido cierra el modal
    if (e.target.classList.contains("dn-modal-overlay")) {
        e.target.classList.add("hidden");
    }
});

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        DN.$$(".dn-modal-overlay:not(.hidden)").forEach(m => m.classList.add("hidden"));
    }
});

/* ─── Tema ────────────────────────────────────────────────────────── */
DN.applyTheme = (key) => {
    document.documentElement.setAttribute("data-theme", key || "dark");
    localStorage.setItem(DN.cfg.LS_THEME, key || "dark");
    // sincroniza meta-theme-color
    const m = DN.$('meta[name="theme-color"]');
    const colors = { dark:"#0a0a0f", light:"#f8fafc", cyber:"#05030a", ocean:"#04111d",
                     forest:"#061a10", sunset:"#1a0a05", pink:"#1a0512", gold:"#1a1205",
                     ice:"#051620", fire:"#1a0505" };
    if (m && colors[key]) m.setAttribute("content", colors[key]);
};

DN.loadThemeGrid = async () => {
    const grid = DN.$("#themeGrid");
    if (!grid) return;
    grid.innerHTML = "";

    let themes = [];
    try {
        const r = await fetch(DN.cfg.API.themes);
        if (r.ok) {
            const j = await r.json();
            themes = j.themes || [];
        }
    } catch { /* offline → fallback */ }

    if (!themes.length) {
        themes = [
            {key:"",       name:"Dark",      icon:"🌑", primary:"#6366f1", desc:"Premium dark"},
            {key:"cyber",  name:"Cyberpunk", icon:"🌆", primary:"#ff00ff", desc:"Neon magenta"},
            {key:"ocean",  name:"Ocean",     icon:"🌊", primary:"#0ea5e9", desc:"Azul profundo"},
            {key:"forest", name:"Forest",    icon:"🌲", primary:"#22c55e", desc:"Verde natural"},
            {key:"sunset", name:"Sunset",    icon:"🌇", primary:"#f97316", desc:"Naranjas cálidos"},
            {key:"light",  name:"Light",     icon:"☀️", primary:"#6366f1", desc:"Claro minimalista"},
            {key:"pink",   name:"Pink",      icon:"🌸", primary:"#ec4899", desc:"Rosa elegante"},
            {key:"gold",   name:"Gold",      icon:"🥇", primary:"#d97706", desc:"Dorado sofisticado"},
            {key:"ice",    name:"Ice",       icon:"❄️", primary:"#67e8f9", desc:"Hielo cristalino"},
            {key:"fire",   name:"Fire",      icon:"🔥", primary:"#ef4444", desc:"Rojo intenso"},
        ];
    }

    const current = localStorage.getItem(DN.cfg.LS_THEME) || DN.cfg.DEFAULT_THEME;
    themes.forEach(t => {
        const themeKey = t.key || "dark";
        const card = DN.el("div", {
            cls: "dn-theme-card" + (current === themeKey ? " active" : ""),
            on: { click: () => {
                DN.applyTheme(themeKey);
                DN.$$(".dn-theme-card").forEach(c => c.classList.remove("active"));
                card.classList.add("active");
                DN.toast(`Tema "${t.name}" aplicado`, "success", 1800);
            } }
        },
            DN.el("div", { cls: "swatch", style: { background: `linear-gradient(135deg, ${t.primary}, ${t.primary}aa)` } }),
            DN.el("div", { cls: "name", text: `${t.icon || "🎨"} ${t.name}` }),
            DN.el("div", { cls: "desc", text: t.desc || "" })
        );
        grid.appendChild(card);
    });
};

/* ─── Sidebar ─────────────────────────────────────────────────────── */
DN.toggleSidebar = () => {
    const sb = DN.$("#sidebar");
    if (!sb) return;
    sb.classList.toggle("collapsed");
    localStorage.setItem(DN.cfg.LS_SIDEBAR, sb.classList.contains("collapsed") ? "1" : "0");
};

DN.restoreSidebar = () => {
    const sb = DN.$("#sidebar");
    if (!sb) return;
    if (localStorage.getItem(DN.cfg.LS_SIDEBAR) === "1") sb.classList.add("collapsed");
    else                                                   sb.classList.remove("collapsed");
    if (window.matchMedia("(max-width: 720px)").matches) sb.classList.add("collapsed");
};

/* ─── Resizer (split panes) ───────────────────────────────────────── */
DN.initResizer = () => {
    const resizer = DN.$("#dnResizer");
    const left    = DN.$("#paneChat");
    const right   = DN.$("#paneSandbox");
    if (!resizer || !left || !right) return;
    let startX = 0, leftW = 0;
    const onMove = (e) => {
        const dx = (e.clientX || (e.touches && e.touches[0].clientX) || 0) - startX;
        const total = resizer.parentElement.getBoundingClientRect().width;
        const pct = ((leftW + dx) * 100) / total;
        if (pct > 18 && pct < 82) {
            left.style.flex  = `1 1 ${pct}%`;
            right.style.flex = `1 1 ${100 - pct}%`;
        }
        document.body.style.cursor = "col-resize";
    };
    const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.removeEventListener("touchmove", onMove);
        document.removeEventListener("touchend", onUp);
        resizer.classList.remove("dragging");
        document.body.style.cursor = "";
        const fr = DN.$("#sandboxFrame");
        if (fr) fr.style.pointerEvents = "auto";
    };
    const onDown = (e) => {
        startX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
        leftW = left.getBoundingClientRect().width;
        resizer.classList.add("dragging");
        const fr = DN.$("#sandboxFrame");
        if (fr) fr.style.pointerEvents = "none";
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
        document.addEventListener("touchmove", onMove, { passive: true });
        document.addEventListener("touchend", onUp);
    };
    resizer.addEventListener("mousedown", onDown);
    resizer.addEventListener("touchstart", onDown, { passive: true });
};

/* ─── Atajos de teclado ──────────────────────────────────────────── */
DN.initShortcuts = () => {
    document.addEventListener("keydown", (e) => {
        const isMod = e.metaKey || e.ctrlKey;
        if (!isMod) return;
        const k = e.key.toLowerCase();

        if (k === "b")          { e.preventDefault(); DN.toggleSidebar(); }
        else if (k === "n")     { e.preventDefault(); DN.events?.emit?.("newChat"); }
        else if (k === "p")     { e.preventDefault(); DN.openModal("modalPrompts"); }
        else if (k === "k" && e.shiftKey) {
            e.preventDefault(); DN.events?.emit?.("clearChat");
        }
        else if (k === "e")     { e.preventDefault(); window.open(DN.cfg.API.export, "_blank"); }
    });
};

/* ─── Settings persistente ────────────────────────────────────────── */
DN.getSettings = () => {
    try { return JSON.parse(localStorage.getItem(DN.cfg.LS_SETTINGS) || "{}"); }
    catch { return {}; }
};
DN.saveSettings = (s) => {
    localStorage.setItem(DN.cfg.LS_SETTINGS, JSON.stringify(s));
};

DN.bindSettings = () => {
    const s = DN.getSettings();
    const map = {
        cfgUltraDefault:  "ultraDefault",
        cfgMultiDefault:  "multiDefault",
        cfgVoice:         "voiceOut",
        cfgAutoSandbox:   "autoSandbox"
    };
    Object.entries(map).forEach(([id, key]) => {
        const el = DN.$(`#${id}`);
        if (!el) return;
        el.checked = s[key] !== undefined ? !!s[key] : (key === "autoSandbox");
        el.addEventListener("change", () => {
            const cur = DN.getSettings();
            cur[key] = el.checked;
            DN.saveSettings(cur);
            DN.toast(`Ajuste guardado: ${key}`, "success", 1400);
        });
    });
};

/* ─── EventBus minimalista ────────────────────────────────────────── */
DN.events = (() => {
    const handlers = {};
    return {
        on:  (ev, fn) => (handlers[ev] = handlers[ev] || []).push(fn),
        off: (ev, fn) => { handlers[ev] = (handlers[ev] || []).filter(f => f !== fn); },
        emit:(ev, ...args) => (handlers[ev] || []).forEach(fn => {
            try { fn(...args); } catch (e) { console.error(`[DN.events ${ev}]`, e); }
        })
    };
})();

/* ─── Markdown seguro ─────────────────────────────────────────────── */
DN.renderMarkdown = (md) => {
    if (!window.marked || !window.DOMPurify) return DN.escapeHTML(md);
    try {
        if (window.hljs) {
            window.marked.setOptions({
                highlight: (code, lang) => {
                    try {
                        if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value;
                        return hljs.highlightAuto(code).value;
                    } catch { return DN.escapeHTML(code); }
                }
            });
        }
        const dirty = window.marked.parse(md, { gfm: true, breaks: true });
        return window.DOMPurify.sanitize(dirty, {
            ADD_ATTR: ["target", "class"],
            ALLOWED_URI_REGEXP: /^(?:(?:https?|data|blob):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i
        });
    } catch (e) {
        console.warn("[markdown] fallback", e);
        return DN.escapeHTML(md);
    }
};

/* ─── Voz (Web Speech API) ────────────────────────────────────────── */
DN.tts = (text) => {
    try {
        if (!("speechSynthesis" in window)) return;
        const u = new SpeechSynthesisUtterance(String(text).slice(0, 500));
        u.lang = "es-ES";
        u.rate = 1.05;
        speechSynthesis.cancel();
        speechSynthesis.speak(u);
    } catch (e) { console.warn("[tts]", e); }
};

DN.dictate = (cb) => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { DN.toast("Dictado no soportado en este navegador", "warn"); return null; }
    const r = new SR();
    r.lang = "es-ES";
    r.interimResults = false;
    r.continuous = false;
    r.onresult = (ev) => {
        const txt = Array.from(ev.results).map(x => x[0].transcript).join(" ");
        cb && cb(txt);
    };
    r.onerror = (e) => DN.toast("Error de dictado: " + e.error, "error");
    r.start();
    return r;
};

/* ─── UID anónimo persistente (para /sessions, /api/conversations) ── */
DN.getUID = () => {
    let uid = localStorage.getItem(DN.cfg.LS_PERSIST_UID);
    if (!uid) {
        uid = "anon_" + Math.random().toString(36).slice(2, 10);
        localStorage.setItem(DN.cfg.LS_PERSIST_UID, uid);
    }
    return uid;
};

console.log("[DN.ui] cargado");
