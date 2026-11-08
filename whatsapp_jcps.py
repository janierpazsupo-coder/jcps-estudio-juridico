"""Avisos de consultas JCPS mediante WhatsApp Business Cloud API.

No sustituye la configuración ni la aprobación del número emisor y plantilla en Meta.
Un ID 'wamid' significa aceptación por la API, NO entrega ni lectura.
Sin credenciales no se hace ninguna llamada externa.
"""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _parameters(code, area, name, subject, message):
    detailed = os.getenv("JCPS_WA_TEMPLATE_DETAIL", "0") == "1"
    if detailed:
        return [code, area, name[:90], subject[:130], message[:2300]]
    return [code, area]


def send_whatsapp_notice(code, area, name, subject, message):
    """Intento de notificación; devuelve un estado verificable sin inventar entrega."""
    token = os.getenv("JCPS_WA_ACCESS_TOKEN", "").strip()
    sender_id = os.getenv("JCPS_WA_PHONE_NUMBER_ID", "").strip()
    to = os.getenv("JCPS_WA_TO", "").strip().lstrip("+")
    version = os.getenv("JCPS_WA_GRAPH_VERSION", "v24.0").strip()
    template_name = os.getenv("JCPS_WA_TEMPLATE_NAME", "").strip()
    mode = os.getenv("JCPS_WA_MODE", "template").strip().lower()

    if not (token and sender_id and to and (template_name or mode == "text")):
        return {"estado": "no_configurado", "mensaje_id": ""}
    if (not re.fullmatch(r"\d{7,24}", sender_id)
            or not re.fullmatch(r"\d{10,15}", to)
            or not re.fullmatch(r"v\d{1,3}\.\d{1,2}", version)
            or mode not in ("template", "text")):
        return {"estado": "configuracion_invalida", "mensaje_id": ""}

    if mode == "template":
        if not re.fullmatch(r"[a-z0-9_]{1,120}", template_name):
            return {"estado": "configuracion_invalida", "mensaje_id": ""}
        params = _parameters(code, area, name, subject, message)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": os.getenv("JCPS_WA_TEMPLATE_LANG", "es").strip()},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": value} for value in params
                ]}],
            },
        }
    else:
        # Los mensajes de texto libre requieren una ventana de atención válida.
        body = (f"JCPS · Nueva consulta {code}\n"
                f"Especialidad: {area}\n"
                f"Remitente: {name}\n"
                f"Asunto: {subject}\n\n"
                f"Consulta:\n{message}")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body[:4096]},
        }

    endpoint = f"https://graph.facebook.com/{version}/{sender_id}/messages"
    req = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=9) as response:
            result = json.loads(response.read(32768).decode("utf-8"))
        msgs = result.get("messages", [])
        message_id = msgs[0].get("id", "") if msgs and isinstance(msgs[0], dict) else ""
        if not isinstance(message_id, str) or not message_id.startswith("wamid"):
            return {"estado": "sin_confirmacion_meta", "mensaje_id": ""}
        return {"estado": "aceptado_por_meta", "mensaje_id": message_id[:255]}
    except HTTPError:
        # No exponemos cuerpos de error de Meta, tokens ni datos de clientes.
        return {"estado": "rechazado_por_meta", "mensaje_id": ""}
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        return {"estado": "error_comunicacion", "mensaje_id": ""}
