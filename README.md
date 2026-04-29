# MiChatBot

App Flask monolitica para DeepNova/MiChatBot.

## Ejecutar localmente

1. Crea un entorno virtual e instala dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copia la plantilla de entorno y completa tus claves:

```powershell
Copy-Item .env.example .env
```

`GROQ_API_KEY` es obligatoria para que `/chat` responda.

3. Inicia Flask:

```powershell
python app.py
```

4. Abre la app en:

```text
http://localhost:5000
```

No abras `index.html` directamente con `file://`; el frontend usa endpoints Flask como `/chat`, `/sessions` y `/api/*`.

## Seguridad

Las claves reales no deben guardarse en Git. Si una clave estuvo publicada en `.env`, rotala en el proveedor correspondiente antes de usar produccion.
