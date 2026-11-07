# JCPS – Recepción de consultas

## Función nueva

El visitante completa un formulario, puede adjuntar hasta tres archivos (3 MB cada uno, 6 MB en conjunto) y usa **Enviar consulta**. El servidor valida la solicitud, la registra y devuelve un número de referencia. No abre WhatsApp ni presenta como enviado un mensaje que no salió.

Una persona con acceso de administrador entra en `/admin`, y desde allí abre `/admin/consultas` para revisar mensajes y descargar archivos. Los archivos no están disponibles públicamente.

## Almacenamiento y seguridad

En Render gratuito el almacenamiento local es efímero. Sin `JCPS_CONTACT_DATABASE_URL`, las consultas pueden perderse cuando se reinicia o despliega el servicio. **No usar con expedientes personales ni confiar en él para captar clientes de forma estable** hasta configurar una base externa permanente.

Para usar la base gratuita `jcps-consultas` ya creada en Render, debe conectarse `JCPS_CONTACT_DATABASE_URL` a la cadena de conexión interna desde Render. El `render.yaml` proporciona una configuración opcional mediante Blueprint, que exige revisar y aprobar su plan. La base gratuita de Render expira 30 días después de su creación (2026-12-07 en este caso) y carece de copias de seguridad gestionadas.

El formulario limita tamaño, extensión y firmas básicas de archivos; aplica un control básico de frecuencia y registra consentimiento. No sustituye medidas profesionales de privacidad y ciberseguridad.

## WhatsApp a dos personas

La recepción y bandeja funcionan sin WhatsApp. **El envío automático a dos números de WhatsApp no está conectado**; exige la plataforma oficial de WhatsApp Business, credenciales autorizadas, autorización de destinatarios y, en su caso, una plantilla aprobada. La API de Meta no puede reemplazarse por enlaces `wa.me`.

## Notificaciones opcionales por correo

Puede configurarse envío de avisos con variables `JCPS_SMTP_HOST`, `JCPS_SMTP_PORT`, `JCPS_SMTP_FROM`, `JCPS_SMTP_USER`, `JCPS_SMTP_PASSWORD`, `JCPS_NOTIFY_EMAILS`. En el plan gratuito de Render las conexiones salientes SMTP tradicionales suelen estar bloqueadas; se recomienda un proveedor HTTPS cuando sea necesario. **Esta función no está activada**.

## Variables de entorno

- `JCPS_ADMIN_PASSWORD`: clave privada necesaria para el panel.
- `JCPS_SESSION_SECRET`: clave privada de sesiones.
- `JCPS_HTTPS_ONLY=1`: cookies solo HTTPS.
- `JCPS_CONTACT_DATABASE_URL`: base de datos externa PostgreSQL; si falta, SQLite temporal.
- `JCPS_RATE_SALT`: sal para identificar envíos repetidos sin guardar direcciones IP en claro.

Nunca colocar claves en GitHub, HTML o archivos públicos.
