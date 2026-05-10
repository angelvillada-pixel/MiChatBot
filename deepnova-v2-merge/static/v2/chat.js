/* ════════════════════════════════════════════════════════════════════
   DeepNova /v2 · chat.js
   Lógica del chat: mensajes, sesiones, fetch a /chat, persistencia.
   Conecta al backend Deep Nova SIN modificar /chat ni /sessions.
   ════════════════════════════════════════════════════════════════════ */

DN.chat = (function () {

    const { $, $$, el, escapeHTML, renderMarkdown, formatTime, uid, cfg, toast,
            getUID, copyToClipboard, getSettings } = DN;

    // ─── Estado ────────────────────────────────────────────────────
    const state = {
        sessions:      [],          // sesiones locales (espejo persistente)
        currentId:     null,        // id de la sesión actual
        attachment:    null,        // {type, base64?, content?, name}
        abortCtrl:     null,        // AbortController activo
        processing:    false,
        flags: {
            ultra: false,
            multi: false
        },
        backendSession: null        // id externo "sess_*" cuando el backend lo soporta
    };

    // ─── Almacenamiento local ──────────────────────────────────────
    const lsLoad = () => {
        try {
            state.sessions = JSON.parse(localStorage.getItem(cfg.LS_SESSIONS) || "[]");
            state.currentId = localStorage.getItem(cfg.LS_CURRENT_SESS);
        } catch {
            state.sessions = [];
            state.currentId = null;
        }
    };
    const lsSave = () => {
        localStorage.setItem(cfg.LS_SESSIONS, JSON.stringify(state.sessions));
        if (state.currentId) localStorage.setItem(cfg.LS_CURRENT_SESS, state.currentId);
    };

    // ─── Sesiones ──────────────────────────────────────────────────
    const newSession = (autoLoad = true) => {
        const d = new Date();
        const sess = {
            id: uid(),
            title: `Conversación ${d.getHours().toString().padStart(2,"0")}:${d.getMinutes().toString().padStart(2,"0")}`,
            createdAt: d.toISOString(),
            messages: [],
            renderedCode: "",
            backendId: null
        };
        state.sessions.unshift(sess);
        lsSave();

        // Crear sesión persistente en el backend (best-effort, no bloquea)
        fetch(cfg.API.sessions, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                uid: getUID(),
                title: sess.title,
                mode: "chat"
            })
        }).then(r => r.ok ? r.json() : null)
          .then(j => {
              if (j && j.id) {
                  sess.backendId = j.id;
                  state.backendSession = j.id;
                  lsSave();
              }
          })
          .catch(() => { /* offline OK */ });

        if (autoLoad) loadSession(sess.id);
        else renderList();
        return sess.id;
    };

    const loadSession = (id) => {
        state.currentId = id;
        lsSave();
        const s = state.sessions.find(x => x.id === id);
        state.backendSession = s?.backendId || null;
        renderHistory();
        renderList();
        DN.events.emit("sessionChange", s);
    };

    const renameSession = (id, title) => {
        const s = state.sessions.find(x => x.id === id);
        if (!s) return;
        s.title = title;
        lsSave();
        renderList();
        if (s.backendId) {
            fetch(`${cfg.API.sessions}/${s.backendId}`, {
                method: "PATCH",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({title})
            }).catch(() => {});
        }
    };

    const deleteSession = (id) => {
        const s = state.sessions.find(x => x.id === id);
        if (s?.backendId) {
            fetch(`${cfg.API.sessions}/${s.backendId}`, { method: "DELETE" }).catch(() => {});
        }
        state.sessions = state.sessions.filter(x => x.id !== id);
        if (state.currentId === id) {
            state.currentId = state.sessions[0]?.id || null;
            if (!state.currentId) newSession();
            else loadSession(state.currentId);
        }
        lsSave();
        renderList();
    };

    const currentSession = () => state.sessions.find(x => x.id === state.currentId) || null;

    // ─── Persistencia de mensajes ──────────────────────────────────
    const pushMessage = (role, content, meta = {}) => {
        const s = currentSession();
        if (!s) return null;
        const msg = {
            id: uid(),
            role,
            content,
            ts: Date.now(),
            ...meta
        };
        s.messages.push(msg);
        // Auto-titular con el primer prompt del usuario
        if (role === "user" && s.messages.filter(m => m.role === "user").length === 1) {
            s.title = content.substring(0, 40).trim() + (content.length > 40 ? "…" : "");
            renderList();
        }
        lsSave();
        return msg;
    };

    // ─── Render: lista lateral ─────────────────────────────────────
    const renderList = (filter = "") => {
        const list = $("#sessionList");
        if (!list) return;
        list.innerHTML = "";
        const q = filter.trim().toLowerCase();
        const items = state.sessions.filter(s =>
            !q || s.title.toLowerCase().includes(q) ||
            s.messages.some(m => (m.content || "").toLowerCase().includes(q))
        );
        if (!items.length) {
            list.appendChild(el("div", {
                style: { padding: "20px 14px", color: "var(--text-muted)", fontSize: ".82rem", textAlign: "center" },
                text: q ? "Sin resultados" : "Aún no hay conversaciones"
            }));
            return;
        }
        items.forEach(s => {
            const item = el("div", {
                cls: "dn-session-item" + (s.id === state.currentId ? " active" : ""),
                attrs: { title: s.title },
                on: { click: () => loadSession(s.id) }
            },
                el("span", { cls: "dn-session-title", text: s.title }),
                el("button", {
                    cls: "dn-session-del",
                    text: "🗑️",
                    attrs: { title: "Eliminar" },
                    on: { click: (e) => {
                        e.stopPropagation();
                        if (confirm("¿Eliminar esta conversación?")) deleteSession(s.id);
                    } }
                })
            );
            list.appendChild(item);
        });

        // session badge en input foot
        const sShort = $("#sessionShort");
        if (sShort) {
            const cur = currentSession();
            sShort.textContent = cur ? cur.title.slice(0, 22) + (cur.title.length > 22 ? "…" : "") : "sin sesión";
        }
        const cfgSession = $("#cfgSession");
        if (cfgSession) cfgSession.textContent = state.currentId || "—";
    };

    // ─── Render: historial principal ───────────────────────────────
    const renderHistory = () => {
        const h = $("#chatHistory");
        if (!h) return;
        h.innerHTML = "";
        const s = currentSession();
        if (!s || s.messages.length === 0) {
            h.appendChild(buildWelcome());
            DN.sandbox?.reset?.();
            return;
        }
        s.messages.forEach(m => h.appendChild(renderMsg(m)));
        h.scrollTop = h.scrollHeight;
        // Recuperar último código en sandbox
        if (s.renderedCode && DN.sandbox) DN.sandbox.renderHTML(s.renderedCode, false);
    };

    const buildWelcome = () => {
        const wrap = el("div", { cls: "dn-welcome" },
            el("h1", { text: "Bienvenido a DeepNova" }),
            el("p", { html: "Plataforma IA premium con <strong>NeuroCore-X</strong>, multi-modelo, sandbox y memoria persistente." }),
            el("div", { cls: "dn-suggestions", id: "welcomeSuggestions" })
        );
        // cargar sugerencias contextuales
        setTimeout(loadSuggestions, 0);
        return wrap;
    };

    const loadSuggestions = async () => {
        const wrap = $("#welcomeSuggestions");
        if (!wrap) return;
        wrap.innerHTML = "";
        let sugs = [];
        try {
            const r = await fetch(cfg.API.suggestions + "?context=empty");
            if (r.ok) {
                const j = await r.json();
                sugs = j.suggestions || [];
            }
        } catch {}
        if (!sugs.length) {
            sugs = [
                {icon:"💡", text:"Idea innovadora de startup IA 2026"},
                {icon:"💻", text:"Crea una API REST en Python con FastAPI"},
                {icon:"🎨", text:"Diseña un dashboard premium dark mode"},
                {icon:"🤖", text:"/agente Crea un sitio web profesional"},
                {icon:"🌐", text:"Busca tendencias IA"},
                {icon:"📊", text:"Genera un informe ejecutivo estructurado"}
            ];
        }
        sugs.forEach(sg => {
            const card = el("div", {
                cls: "dn-sugg-card",
                on: { click: () => {
                    const ti = $("#promptInput");
                    if (ti) {
                        ti.value = sg.text;
                        ti.dispatchEvent(new Event("input"));
                        ti.focus();
                    }
                } }
            },
                el("span", { cls: "ico", text: sg.icon || "💡" }),
                el("span", { text: sg.text })
            );
            wrap.appendChild(card);
        });
    };

    // ─── Render: mensaje individual ────────────────────────────────
    const renderMsg = (m) => {
        const isUser = m.role === "user";
        const isSys  = m.role === "system";

        const avatar = el("div", {
            cls: "dn-avatar",
            text: isUser ? "Tú" : isSys ? "•" : "DN"
        });

        const bubbleHTML = isUser
            ? `<div>${escapeHTML(m.content)}</div>`
            : renderMarkdown(m.content || "");

        const bubble = el("div", { cls: "dn-bubble", html: bubbleHTML });

        // Code copy buttons
        bubble.querySelectorAll("pre").forEach(pre => {
            const btn = el("button", {
                cls: "dn-code-copy",
                text: "Copiar",
                on: { click: () => copyToClipboard(pre.innerText) }
            });
            pre.appendChild(btn);
        });

        // Meta (timestamp + acciones)
        const actions = el("div", { cls: "dn-msg-actions" });
        if (!isUser && !isSys) {
            actions.appendChild(el("button", {
                cls: "dn-msg-action", text: "📋", attrs: { title: "Copiar respuesta" },
                on: { click: () => copyToClipboard(m.content) }
            }));
            actions.appendChild(el("button", {
                cls: "dn-msg-action", text: "🔄", attrs: { title: "Regenerar" },
                on: { click: () => DN.events.emit("regenerate", m) }
            }));
            actions.appendChild(el("button", {
                cls: "dn-msg-action", text: "👍", attrs: { title: "Útil" },
                on: { click: () => sendFeedback(+1, m) }
            }));
            actions.appendChild(el("button", {
                cls: "dn-msg-action", text: "👎", attrs: { title: "No útil" },
                on: { click: () => sendFeedback(-1, m) }
            }));
            if (m.content && m.content.length < 1500) {
                actions.appendChild(el("button", {
                    cls: "dn-msg-action", text: "🔊", attrs: { title: "Leer en voz alta" },
                    on: { click: () => DN.tts(m.content) }
                }));
            }
        }

        const meta = el("div", { cls: "dn-msg-meta" },
            el("span", { text: formatTime(m.ts) }),
            m.model_used ? el("span", { cls: "dn-mini-tag", text: m.model_used }) : null,
            actions
        );

        return el("div", {
            cls: "dn-msg " + (isUser ? "user" : isSys ? "system" : "ai"),
            attrs: { "data-msg-id": m.id }
        },
            avatar,
            el("div", { style: { maxWidth: "calc(100% - 60px)" } }, bubble, meta)
        );
    };

    // ─── Feedback al backend ───────────────────────────────────────
    const sendFeedback = async (vote, m) => {
        try {
            await fetch(cfg.API.feedback, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    sid: getUID(),
                    vote: vote,
                    signal: "thumb",
                    comment: ""
                })
            });
            toast(vote > 0 ? "Gracias por tu feedback 👍" : "Feedback registrado 👎", "success", 1800);
        } catch {
            toast("No se pudo enviar feedback", "error");
        }
    };

    // ─── Adjuntos ──────────────────────────────────────────────────
    const setAttachment = (file) => {
        if (!file) return;
        const preview = $("#attachPreview");
        const reader = new FileReader();
        const isImg = (file.type || "").startsWith("image/");

        reader.onload = (e) => {
            const result = e.target.result;
            if (isImg) {
                state.attachment = {
                    type: "image",
                    base64: result.split(",")[1] || "",
                    dataURL: result,
                    name: file.name
                };
            } else {
                state.attachment = {
                    type: "text",
                    content: result,
                    name: file.name
                };
            }
            // Refresh preview
            preview.innerHTML = "";
            if (isImg) {
                const img = el("img", { attrs: { src: result, alt: file.name } });
                preview.appendChild(img);
            } else {
                preview.appendChild(el("span", { cls: "ico", text: "📄" }));
            }
            preview.appendChild(el("span", { cls: "name", text: file.name }));
            preview.appendChild(el("span", {
                cls: "close", text: "✕",
                attrs: { title: "Quitar" },
                on: { click: clearAttachment }
            }));
            preview.classList.remove("hidden");
        };

        if (isImg) reader.readAsDataURL(file);
        else       reader.readAsText(file);
    };

    const clearAttachment = () => {
        state.attachment = null;
        const preview = $("#attachPreview");
        if (preview) {
            preview.classList.add("hidden");
            preview.innerHTML = "";
        }
        const fi = $("#fileInput");
        if (fi) fi.value = "";
    };

    // ─── Envío al backend ──────────────────────────────────────────
    const send = async (textOverride) => {
        if (state.processing && state.abortCtrl) {
            state.abortCtrl.abort();
            return;
        }
        const ti = $("#promptInput");
        const text = (textOverride ?? (ti?.value || "")).trim();
        if (!text && !state.attachment) return;

        if (!state.currentId) newSession(false);
        const s = currentSession();
        if (!s) return;

        // Construir mensaje del usuario incluyendo adjunto
        let finalMsg = text || "[Archivo adjunto enviado]";
        const attachData = state.attachment;
        if (attachData?.type === "text") {
            finalMsg = `[Archivo: ${attachData.name}]\n\`\`\`\n${attachData.content}\n\`\`\`\n\n${text}`;
        }

        pushMessage("user", finalMsg);
        if (ti) { ti.value = ""; ti.style.height = ""; }
        $("#charCount") && ($("#charCount").textContent = "0 chars");

        // Render mensaje del usuario + placeholder de IA
        const h = $("#chatHistory");
        const welcome = $("#welcomeScreen");
        if (welcome) welcome.remove();

        const userMsg = s.messages[s.messages.length - 1];
        h.appendChild(renderMsg(userMsg));

        const aiPlaceholder = el("div", { cls: "dn-msg ai" },
            el("div", { cls: "dn-avatar", text: "DN" }),
            el("div", { style: { maxWidth: "calc(100% - 60px)" } },
                el("div", { cls: "dn-bubble", html: '<div class="dn-typing"><span></span><span></span><span></span></div>' })
            )
        );
        h.appendChild(aiPlaceholder);
        h.scrollTop = h.scrollHeight;

        // UI estado "procesando"
        state.processing = true;
        state.abortCtrl = new AbortController();
        toggleSendButton(true);

        // Construir payload
        const settings = getSettings();
        const useUltra = state.flags.ultra || !!settings.ultraDefault;
        const useMulti = state.flags.multi || !!settings.multiDefault;

        const payload = {
            message: finalMsg,
            session_id: getUID(),
            session_id_external: s.backendId || "",
            ultra: useUltra,
            multi_model: useMulti
        };
        if (attachData?.type === "image") {
            payload.image = attachData.base64;  // backend puede usarlo si soporta visión
        }

        clearAttachment();

        try {
            const r = await fetch(cfg.API.chat, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
                signal: state.abortCtrl.signal
            });
            if (!r.ok) {
                const errTxt = await r.text().catch(() => `HTTP ${r.status}`);
                throw new Error(errTxt);
            }
            const data = await r.json();
            const reply = data.response || "(respuesta vacía)";
            const meta = {
                model_used: data.model_used || "DeepNova",
                modes_used: data.modes_used || [],
                web_search: !!data.web_search,
                ultra: !!data.ultra
            };

            // Reemplazar placeholder
            aiPlaceholder.remove();
            const aiMsg = pushMessage("assistant", reply, meta);
            h.appendChild(renderMsg(aiMsg));
            h.scrollTop = h.scrollHeight;

            // Sandbox auto-render
            if (settings.autoSandbox !== false && DN.sandbox) {
                DN.sandbox.parseAndRender(reply);
                s.renderedCode = DN.sandbox.getCurrent() || "";
                lsSave();
            }

            // Voz
            if (settings.voiceOut) DN.tts(reply.replace(/```[\s\S]*?```/g, "").slice(0, 400));

            // Actualizar tag de modo
            const tag = $("#modeTag");
            if (tag && meta.modes_used?.length) tag.textContent = meta.modes_used.slice(0,2).join("·");

        } catch (err) {
            aiPlaceholder.remove();
            if (err.name === "AbortError") {
                const sysMsg = pushMessage("system", "🛑 Petición detenida por el usuario.");
                h.appendChild(renderMsg(sysMsg));
                toast("Petición cancelada", "warn", 1800);
            } else {
                console.error("[chat]", err);
                const sysMsg = pushMessage("system",
                    "❌ Error al contactar el backend. Verifica que DeepNova esté corriendo. " +
                    "Detalle: " + escapeHTML(String(err.message || err)).slice(0, 200));
                h.appendChild(renderMsg(sysMsg));
                toast("Error al enviar mensaje", "error");
            }
        } finally {
            state.processing = false;
            state.abortCtrl = null;
            toggleSendButton(false);
            const tiNow = $("#promptInput");
            tiNow && tiNow.focus();
        }
    };

    const toggleSendButton = (busy) => {
        const btn = $("#btnSend");
        if (!btn) return;
        if (busy) {
            btn.classList.add("stop");
            btn.textContent = "■";
            btn.title = "Detener respuesta";
        } else {
            btn.classList.remove("stop");
            btn.textContent = "➤";
            btn.title = "Enviar";
        }
    };

    // ─── Limpieza completa ─────────────────────────────────────────
    const clearAll = () => {
        if (!confirm("¿Borrar TODAS las conversaciones locales? Esta acción no se puede deshacer.")) return;
        state.sessions = [];
        state.currentId = null;
        localStorage.removeItem(cfg.LS_SESSIONS);
        localStorage.removeItem(cfg.LS_CURRENT_SESS);
        newSession();
        toast("Historial local limpiado", "success");
    };

    const clearCurrent = () => {
        const s = currentSession();
        if (!s) return;
        if (!confirm("¿Limpiar mensajes de la conversación actual?")) return;
        s.messages = [];
        s.renderedCode = "";
        lsSave();
        renderHistory();
        DN.sandbox?.reset?.();
    };

    // ─── Inicialización ────────────────────────────────────────────
    const init = () => {
        lsLoad();
        if (!state.sessions.length || !state.currentId) {
            newSession();
        } else {
            renderHistory();
            renderList();
        }

        // Search en sidebar
        const searchInput = $("#searchSessions");
        searchInput?.addEventListener("input", (e) => renderList(e.target.value));

        // Eventos globales
        DN.events.on("newChat",   () => newSession());
        DN.events.on("clearChat", () => clearCurrent());
        DN.events.on("regenerate", (m) => {
            // Toma el último mensaje user previo a este AI y reenvíalo
            const s = currentSession();
            if (!s) return;
            const idx = s.messages.findIndex(x => x.id === m.id);
            if (idx <= 0) return;
            for (let i = idx - 1; i >= 0; i--) {
                if (s.messages[i].role === "user") {
                    send(s.messages[i].content);
                    return;
                }
            }
        });
    };

    return {
        init, send,
        newSession, loadSession, deleteSession, renameSession,
        currentSession, pushMessage,
        setAttachment, clearAttachment,
        clearAll, clearCurrent,
        toggleFlag: (k) => { state.flags[k] = !state.flags[k]; return state.flags[k]; },
        getFlag:    (k) => !!state.flags[k],
        renderList, renderHistory,
        _state: state // debug
    };
})();

console.log("[DN.chat] cargado");
