# JCPS — Estudio Jurídico Paz Supo

Portal de orientación jurídica en Perú, con secciones de Derecho Civil, Derecho Laboral y Derecho Penal.

## Tecnología

FastAPI + SQLite + HTML, CSS y JavaScript. Guías administrables. Esta versión es de información general; no ofrece patrocinio ni representación legal.

## Ejecutar localmente

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Render

Runtime: Python. Build: `pip install -r requirements.txt`. Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`.

En producción, configure las variables `JCPS_HTTPS_ONLY=1`, `JCPS_ADMIN_PASSWORD` y `JCPS_SESSION_SECRET` si desea activar el panel `/admin`. Nunca almacene claves o bases privadas en el repositorio. La base SQLite local no conserva cambios permanentes en un servicio efímero gratuito.

El formulario prepara un mensaje para WhatsApp; el envío final debe confirmarse en la aplicación. Los archivos adjuntos deben compartirse por separado.
