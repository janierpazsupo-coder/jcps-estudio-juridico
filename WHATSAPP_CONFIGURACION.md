# JCPS: aviso automático por WhatsApp Business Platform

**Estado:** código incorporado; no se envían mensajes hasta configurar un emisor Meta autorizado. No inventamos credenciales ni aprobaciones.

## Qué hace

1. El visitante completa el formulario de Derecho Civil o Derecho Laboral.
2. El servidor guarda la consulta y los adjuntos en la bandeja privada (/admin/consultas).
3. Si Meta Cloud API está autorizada y configurada, el servidor intenta enviar un aviso automáticamente al número del responsable.
4. Guarda un estado: `no_configurado`, `aceptado_por_meta`, `rechazado_por_meta`, `error_comunicacion` o `sin_confirmacion_meta`.

**Importante:** `aceptado_por_meta` no significa entregado o leído. Para verificar entrega/lectura se requieren webhooks oficiales de Meta, aún no implementados. Los adjuntos permanecen privados en JCPS y NO se envían por WhatsApp automáticamente.

## Configurar sin revelar secretos en GitHub

Usar Render → Servicio JCPS → Environment. Nunca pegar tokens en el código o páginas públicas.

- `JCPS_WA_ACCESS_TOKEN`: token de acceso autorizado para WhatsApp Cloud API.
- `JCPS_WA_PHONE_NUMBER_ID`: ID de número emisor de WhatsApp Business (no es el número de teléfono).
- `JCPS_WA_TO`: número del responsable que recibirá avisos en formato internacional, sin +.
- `JCPS_WA_TEMPLATE_NAME`: nombre EXACTO de una plantilla aprobada por Meta.
- `JCPS_WA_TEMPLATE_LANG`: idioma de la plantilla, por defecto `es`.
- `JCPS_WA_GRAPH_VERSION`: versión de Graph API admitida, por defecto `v24.0`.
- `JCPS_WA_MODE=template`: modo recomendado para notificaciones empresariales.

### Plantilla de referencia sugerida

Crear para revisión en WhatsApp Manager una plantilla utilitaria en español con **dos variables de cuerpo**:

`JCPS: se registró la consulta {{1}} del área {{2}}. Entra a la bandeja privada de JCPS para ver el mensaje.`

El nombre que tú escojas en Meta debe coincidir exactamente con `JCPS_WA_TEMPLATE_NAME`. Meta decide si aprueba la plantilla. La cuenta y el destinatario deben cumplir los requisitos de autorización y consentimiento.

La plantilla anterior solo notifica **código y especialidad**, no envía el texto completo del visitante. Para usar una plantilla detallada aprobada con cinco variables, configurar `JCPS_WA_TEMPLATE_DETAIL=1`, y la plantilla debe aceptar, en orden: código, especialidad, remitente, asunto, consulta. Revisa cuidadosamente la privacidad antes de activar esa opción.

### Texto libre (ventana de 24 horas)

`JCPS_WA_MODE=text` intenta enviar el texto completo. Meta lo permite solamente cuando exista una ventana de atención de 24 horas abierta por un mensaje del destinatario al número emisor. Fuera de esa ventana se rechazará. No es el modo recomendado para avisos continuos.

## Pruebas antes de atención real

- Usar un número emisor y destinatario autorizados.
- Probar una consulta sin información sensible.
- Revisar `/admin/consultas` y su estado de aviso; comprobar también el WhatsApp destinatario.
- Verificar limitaciones, tarifas, políticas de privacidad y comportamiento de archivos.
- La base gratuita actual tiene vencimiento programado: **7 de diciembre de 2026**. Antes de procesar expedientes reales, contratar/trasladar a almacenamiento duradero, controlar acceso, cifrado y copias de seguridad.
