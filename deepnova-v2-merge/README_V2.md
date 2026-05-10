# DeepNova /v2 · Frontend Premium

Frontend moderno fusionado con la estructura modular de **Facil-con-IA-Agent**, conectado al backend full-stack de **Deep Nova** (`MiChatBot`).

> Coexiste con el `index.html` original. La ruta `/` no se modifica. La nueva URL es `http://<host>/v2`.

---

## ✨ Características

### Visuales
- **10 temas premium** sincronizados con `/api/themes`: dark, light, cyber, ocean, forest, sunset, pink, gold, ice, fire
- **Glassmorphism** y efectos de profundidad
- **Animaciones suaves** con `cubic-bezier` y `prefers-reduced-motion` respetado
- **Responsive completo**: PC ≥1024px (split chat+sandbox), tablet/móvil (sidebar deslizable, sandbox plegable)
- **Markdown seguro** (DOMPurify) con `highlight.js` para código
- **Avatares**, burbujas, timestamps, acciones por mensaje (copiar, regenerar, feedback, voz)

### Funcionales
- 💬 Chat completo conectado a `/chat` con persistencia local + backend (`/sessions`)
- 🌟 Toggle **Modo ULTRA** (NeuroCore-X)
- 🧠 Toggle **Multi-IA**
- 📚 **Biblioteca de prompts** desde `/api/prompts`
- 🐍 **Sandbox HTML/CSS/JS** + ejecución Python via `/execute`
- 📦 **Descarga ZIP** del proyecto generado por la IA (JSZip)
- 💾 **Descarga HTML** y abrir en pestaña nueva
- 🎤 **Dictado** y 🔊 **lectura por voz** (Web Speech API)
- 📎 **Adjuntos**: imágenes y documentos de texto
- 🔍 **Búsqueda** en historial de sesiones
- 👍 **Feedback** integrado con `/api/feedback`
- ⌨️ **Atajos**: ⌘+B, ⌘+N, ⌘+P, ⌘+E, ⌘+⇧+K, Esc

### Arquitecturales
- **Modular**: 4 archivos JS (ui, chat, sandbox, app) más 1 CSS
- **100% aditivo**: si falla, el backend sigue funcionando sin cambios
- **Cero dependencias nuevas** en `requirements.txt`
- **Rollback trivial**: borrar 8 archivos + 4 líneas en app.py

---

## 🗂️ Estructura

```
static/v2/
├── index.html      Estructura visual
├── style.css       1,000+ líneas de CSS premium
├── ui.js           Capa visual (toasts, modales, temas, atajos)
├── chat.js         Lógica de chat y sesiones
├── sandbox.js      Renderer HTML/CSS/JS + Python
└── app.js          Orquestador principal
```

```
v2_frontend.py     Blueprint Flask (sirve /v2 y /v2/static/*)
app_v2_patch.py    Función register_v2(app) — patrón register_v6/v7
```

---

## 🔌 Endpoints backend usados

Todos ya existentes en Deep Nova — **ninguno se modifica**:

| Endpoint | Uso |
|---|---|
| `POST /chat` | Mensaje principal |
| `POST /execute` | Ejecutar Python en sandbox |
| `GET /health` | Status dot |
| `GET /api/themes` | Lista de temas |
| `GET /api/prompts` | Biblioteca de prompts |
| `GET /api/suggestions?context=empty` | Sugerencias welcome |
| `POST /api/feedback` | Thumbs up/down |
| `GET /history/export` | Exportar historial JSON |
| `POST /sessions` · `GET /sessions/<id>` · `PATCH` · `DELETE` | Persistencia de sesiones |

---

## 🚀 Activar

Una sola línea en `app.py`:

```python
from app_v2_patch import register_v2
register_v2(app, logger=logger)
```

Luego abrir `http://localhost:5000/v2`.

Ver `INTEGRATION_GUIDE.md` para los pasos detallados.

---

## 📜 Licencia

Misma licencia que el proyecto Deep Nova original.
