"""Recepción privada de consultas JCPS.
No envía WhatsApp sin autorización de WhatsApp Business ni afirma que lo haga.
La bandeja es accesible solo mediante sesión administrativa.
"""
import os
import re
import io
import hmac
import time
import uuid
import html
import hashlib
import secrets
import sqlite3
import smtplib
import mimetypes
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import quote

from fastapi import APIRouter, Request, HTTPException
from starlette.datastructures import UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image, UnidentifiedImageError

router = APIRouter()
ROOT = Path(__file__).resolve().parent
CONTACT_SQLITE = Path(os.environ.get('JCPS_CONTACT_DB_PATH', str(ROOT / 'data' / 'jcps-consultas.sqlite3')))
CONTACT_SQLITE.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get('JCPS_CONTACT_DATABASE_URL', '').strip()
MAX_UPLOAD = 3 * 1024 * 1024
MAX_TOTAL = 6 * 1024 * 1024
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.odt'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
ZIP_EXT = {'.docx', '.xlsx', '.pptx', '.odt'}
OLE_EXT = {'.doc', '.xls', '.ppt'}
ALLOWED = {'civil': 'Derecho Civil', 'laboral': 'Derecho Laboral', 'penal': 'Derecho Penal'}
APPROVED_ORIGINS = set(x.strip().rstrip('/') for x in os.getenv('JCPS_PUBLIC_ORIGINS', 'https://jcps-estudio-juridico.onrender.com').split(',') if x.strip())

@contextmanager
def contact_db():
    if DATABASE_URL:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError('Conector PostgreSQL no instalado') from exc
        conn = psycopg.connect(DATABASE_URL, connect_timeout=8)
        postgres = True
    else:
        conn = sqlite3.connect(CONTACT_SQLITE, timeout=20)
        conn.execute('PRAGMA busy_timeout=20000')
        postgres = False
    try:
        yield conn, postgres
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

_initialized = False

def init_contact_db():
    global _initialized
    if _initialized:
        return
    with contact_db() as (conn, pg):
        if pg:
            conn.execute('''CREATE TABLE IF NOT EXISTS jcps_consultas (
                id BIGSERIAL PRIMARY KEY, codigo TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
                nombre TEXT NOT NULL, area TEXT NOT NULL, asunto TEXT NOT NULL,
                mensaje TEXT NOT NULL, files_count INTEGER NOT NULL DEFAULT 0,
                recibido BOOLEAN NOT NULL DEFAULT TRUE)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS jcps_adjuntos (
                id BIGSERIAL PRIMARY KEY, consulta_id BIGINT NOT NULL REFERENCES jcps_consultas(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL, tipo TEXT NOT NULL, contenido BYTEA NOT NULL)''')
        else:
            conn.execute('''CREATE TABLE IF NOT EXISTS jcps_consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
                nombre TEXT NOT NULL, area TEXT NOT NULL, asunto TEXT NOT NULL,
                mensaje TEXT NOT NULL, files_count INTEGER NOT NULL DEFAULT 0,
                recibido INTEGER NOT NULL DEFAULT 1)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS jcps_adjuntos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, consulta_id INTEGER NOT NULL REFERENCES jcps_consultas(id),
                nombre TEXT NOT NULL, tipo TEXT NOT NULL, contenido BLOB NOT NULL)''')
    _initialized = True

def sql(pg, s):
    return s.replace('?', '%s') if pg else s

def _validate_attachment(name, payload):
    suffix = Path(name.lower()).suffix
    if suffix not in EXTENSIONS:
        raise HTTPException(status_code=422, detail='Formato de archivo no permitido.')
    if not payload or len(payload) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail='Cada archivo debe medir hasta 3 MB.')
    if suffix in IMAGE_EXT:
        try:
            with Image.open(io.BytesIO(payload)) as im:
                im.verify()
            with Image.open(io.BytesIO(payload)) as im:
                if im.width*im.height > 16_000_000 or im.width>6000 or im.height>6000:
                    raise ValueError('Imagen demasiado grande')
                fmt=im.format
                expected={'.jpg':'JPEG','.jpeg':'JPEG','.png':'PNG','.webp':'WEBP'}[suffix]
                if fmt!=expected: raise ValueError('Formato incorrecto')
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            raise HTTPException(status_code=422, detail='La imagen adjunta no es válida.')
    elif suffix=='.pdf' and not payload.startswith(b'%PDF-'):
        raise HTTPException(422,'PDF no válido.')
    elif suffix in ZIP_EXT and not payload.startswith(b'PK\x03\x04'):
        raise HTTPException(422,'Documento de Office no válido.')
    elif suffix in OLE_EXT and not payload.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        raise HTTPException(422,'Documento de Office antiguo no válido.')
    elif suffix=='.txt':
        try:
            payload.decode('utf-8')
            if b'\x00' in payload: raise ValueError()
        except (UnicodeDecodeError, ValueError):
            raise HTTPException(422,'Adjunta un texto TXT válido en UTF-8.')
    return suffix

def _safe_file_name(name):
    s=str(name or 'archivo').replace('\\','/').split('/')[-1].strip()
    s=re.sub(r'[^\w.()\- ]','_',s,flags=re.UNICODE)
    return (s[:120] or 'archivo')

def _authorized(req):
    return bool(os.getenv('JCPS_ADMIN_PASSWORD')) and req.session.get('admin') is True

def _notify_admins(code):
    """Aviso opcional de datos mínimos. No se presume que SMTP esté configurado."""
    host=os.getenv('JCPS_SMTP_HOST','').strip()
    sender=os.getenv('JCPS_SMTP_FROM','').strip()
    recipients=[x.strip() for x in os.getenv('JCPS_NOTIFY_EMAILS','').split(',') if x.strip()]
    if not host or not sender or not recipients:
        return False
    msg=EmailMessage()
    msg['Subject']=f'JCPS · Nueva consulta {code}'
    msg['From']=sender
    msg['To']=', '.join(recipients)
    msg.set_content(f'Nueva consulta recibida en JCPS.\nReferencia: {code}\nConsultar bandeja privada: https://jcps-estudio-juridico.onrender.com/admin/consultas\n\nPor seguridad no se incluyen datos personales en esta notificación.')
    port=int(os.getenv('JCPS_SMTP_PORT','587'))
    user=os.getenv('JCPS_SMTP_USER','')
    password=os.getenv('JCPS_SMTP_PASSWORD','')
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=6) as s:
            if user and password: s.login(user,password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host,port,timeout=6) as s:
            s.starttls()
            if user and password: s.login(user,password)
            s.send_message(msg)
    return True

@router.post('/api/consultas')
async def recibir_consulta(req:Request):
    # No confirmar una consulta si ningún administrador puede acceder a la bandeja.
    if not os.getenv('JCPS_ADMIN_PASSWORD', '').strip():
        raise HTTPException(503, 'La recepción está pendiente de configurar la bandeja privada. No se ha enviado la consulta.')
    origin=req.headers.get('origin','').rstrip('/')
    if origin and origin not in APPROVED_ORIGINS:
        raise HTTPException(403,'Origen no autorizado.')
    cl=req.headers.get('content-length','')
    if cl.isdigit() and int(cl)>MAX_TOTAL+100_000:
        raise HTTPException(413,'La solicitud supera el límite de 6 MB de adjuntos.')
    content_type=req.headers.get('content-type','')
    if not content_type.startswith('multipart/form-data'):
        raise HTTPException(415,'Formulario incorrecto.')
    try:
        form=await req.form(max_files=3,max_fields=12,max_part_size=MAX_UPLOAD+500)
    except Exception:
        raise HTTPException(422,'No se pudo procesar el formulario.')
    # Campo trampa para bots; no se almacena la información.
    if str(form.get('website','')).strip():
        return JSONResponse({'ok':True,'codigo':'JCPS-RECIBIDA'})
    nombre=str(form.get('remitente','')).strip()
    area=str(form.get('especialidad','')).strip()
    asunto=str(form.get('asunto','')).strip()
    mensaje=str(form.get('consulta','')).strip()
    acepto=str(form.get('consentimiento',''))
    if not (2<=len(nombre)<=90) or not(4<=len(asunto)<=130) or not(15<=len(mensaje)<=2500) or area not in ALLOWED or acepto!='si':
        raise HTTPException(422,'Completa todos los campos y acepta la información de privacidad.')
    if any(ord(c)<32 and c not in '\n\r\t' for c in nombre+asunto+mensaje):
        raise HTTPException(422,'Se encontraron caracteres no válidos.')
    files=[]
    total=0
    for item in form.getlist('archivos'):
        if not isinstance(item, UploadFile) or not item.filename:
            continue
        if len(files)>=3:
            raise HTTPException(413,'Puedes adjuntar hasta 3 archivos.')
        payload=await item.read(MAX_UPLOAD+1)
        total+=len(payload)
        if total>MAX_TOTAL:
            raise HTTPException(413,'Los adjuntos no deben superar 6 MB en total.')
        filename=_safe_file_name(item.filename)
        suffix=_validate_attachment(filename,payload)
        mime=mimetypes.types_map.get(suffix,'application/octet-stream')
        files.append((filename,mime,payload))
    if os.getenv('RENDER') and not DATABASE_URL:
        raise HTTPException(503, 'La recepción de consultas está temporalmente deshabilitada hasta asegurar su almacenamiento. No se guardó ni envió información.')
    if files and not DATABASE_URL:
        raise HTTPException(503, 'Los documentos requieren almacenamiento permanente. La consulta no se registró; inténtalo sin adjuntos por ahora.')
    init_contact_db()
    codigo='JCPS-'+datetime.now(timezone.utc).strftime('%Y%m%d')+'-'+secrets.token_hex(3).upper()
    now=datetime.now(timezone.utc).isoformat()
    try:
        with contact_db() as (conn,pg):
            # Rate limit on hashed client identifier; do not store plain IP addresses.
            # Rate limit is also supported by the honeypot field above.
            if not hasattr(recibir_consulta,'recent'): recibir_consulta.recent={}
            client=req.client.host if req.client else 'unknown'
            key=hashlib.sha256((os.getenv('JCPS_RATE_SALT','jcps')+client).encode()).hexdigest()
            recent=recibir_consulta.recent
            ts=time.monotonic()
            recent[key]=[i for i in recent.get(key,[]) if ts-i<3600]
            if len(recent[key])>=8:
                raise HTTPException(429,'Límite temporal de consultas. Vuelve a intentarlo más tarde.')
            recent[key].append(ts)
            cur=conn.execute(sql(pg,'INSERT INTO jcps_consultas(codigo,created_at,nombre,area,asunto,mensaje,files_count) VALUES(?,?,?,?,?,?,?) RETURNING id'),
                             (codigo,now,nombre,area,asunto,mensaje,len(files)))
            inserted=cur.fetchone()[0]
            for filename,mime,payload in files:
                conn.execute(sql(pg,'INSERT INTO jcps_adjuntos(consulta_id,nombre,tipo,contenido) VALUES(?,?,?,?)'),(inserted,filename,mime,payload))
    except HTTPException:
        raise
    except Exception:
        # No devolver éxito si no se pudo almacenar el envío.
        raise HTTPException(503,'No se pudo guardar la consulta. No fue enviada; intenta nuevamente.')
    notification=False
    try:
        notification=_notify_admins(codigo)
    except Exception:
        # Los avisos son independientes; la bandeja sí contiene el mensaje.
        notification=False
    return JSONResponse({'ok':True,'codigo':codigo,'estado':'recibida_en_bandeja','aviso_email':notification,
                        'detalle':'Consulta recibida en la bandeja privada JCPS. La recepción no implica envío por WhatsApp.'},
                        headers={'Cache-Control':'no-store'})

def _admin_headers(resp):
    resp.headers['Cache-Control']='no-store, private'
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['X-Frame-Options']='DENY'
    return resp

@router.get('/admin/consultas',response_class=HTMLResponse)
def bandeja(req:Request):
    if not _authorized(req):
        return _admin_headers(HTMLResponse('<!doctype html><html lang="es"><meta charset="utf-8"><title>Acceso restringido</title><body><p>Debes iniciar sesión en el panel.</p><a href="/admin">Iniciar sesión</a></body></html>',status_code=401))
    try:
        init_contact_db()
        with contact_db() as (conn,pg):
            rows=conn.execute('SELECT id,codigo,created_at,nombre,area,asunto,mensaje,files_count FROM jcps_consultas ORDER BY id DESC LIMIT 150').fetchall()
            items=[tuple(r) for r in rows]
    except Exception:
        return _admin_headers(HTMLResponse('La bandeja no está disponible.',status_code=503))
    h=lambda v:html.escape(str(v),quote=True)
    content=''.join(
       f'<article><div class="head"><strong>{h(x[1])}</strong><span>{h(x[2][:16])}</span></div>'
       f'<p><b>Remitente:</b> {h(x[3])} · <b>Área:</b> {h(ALLOWED.get(x[4],x[4]))}</p>'
       f'<p><b>Asunto:</b> {h(x[5])}</p><p class="mensaje">{h(x[6])}</p>'
       f'<p>{h(x[7])} archivo(s) adjunto(s). '+(f'<a href="/admin/consultas/{x[0]}/archivos">Ver adjuntos</a>' if x[7] else '')+'</p></article>'
       for x in items
    ) or '<p>No hay consultas recibidas todavía.</p>'
    page='''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bandeja privada JCPS</title><style>body{margin:0;background:#111618;color:#f4efe5;font:16px system-ui;line-height:1.65}main{max-width:950px;margin:auto;padding:30px 20px}a{color:#e1c08b}article{background:#242725;border:1px solid #78654d;border-radius:16px;margin:20px 0;padding:20px}.head{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.head span{color:#d8c7a3}.mensaje{white-space:pre-wrap;overflow-wrap:anywhere}h1{font-family:Georgia,serif}p{max-width:100%;overflow-wrap:anywhere}</style></head><body><main><a href="/admin">← Administración</a><h1>Bandeja de consultas JCPS</h1><p>Acceso privado. Aquí aparecen las consultas efectivamente guardadas en el servidor. No significa que ya se hayan enviado por WhatsApp.</p>'''+content+'</main></body></html>'
    return _admin_headers(HTMLResponse(page))

@router.get('/admin/consultas/{consulta_id}/archivos',response_class=HTMLResponse)
def listar_adjuntos(req:Request,consulta_id:int):
    if not _authorized(req):raise HTTPException(403,'Acceso no autorizado.')
    init_contact_db()
    with contact_db() as (conn,pg):
        query='SELECT id,nombre,LENGTH(contenido) FROM jcps_adjuntos WHERE consulta_id=? ORDER BY id'
        rows=conn.execute(sql(pg,query),(consulta_id,)).fetchall()
    h=lambda v:html.escape(str(v),quote=True)
    links=''.join(f'<li><a href="/admin/consultas/archivo/{int(x[0])}">{h(x[1])}</a> · {int(x[2])//1024} KB</li>' for x in rows)
    return _admin_headers(HTMLResponse('<!doctype html><html lang="es"><meta charset="utf-8"><title>Adjuntos JCPS</title><body style="font-family:system-ui;background:#171a1b;color:white;padding:25px"><a style="color:#e1c08b" href="/admin/consultas">Volver</a><h1>Archivos de la consulta</h1><ul>'+links+'</ul></body></html>'))

@router.get('/admin/consultas/archivo/{attachment_id}')
def descargar_adjunto(req:Request,attachment_id:int):
    if not _authorized(req):raise HTTPException(403,'Acceso no autorizado.')
    init_contact_db()
    with contact_db() as (conn,pg):
        row=conn.execute(sql(pg,'SELECT nombre,tipo,contenido FROM jcps_adjuntos WHERE id=?'),(attachment_id,)).fetchone()
    if not row:raise HTTPException(404,'Archivo no encontrado')
    filename=_safe_file_name(row[0])
    disp=f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
    return Response(content=bytes(row[2]),media_type='application/octet-stream',headers={'Content-Disposition':disp,'X-Content-Type-Options':'nosniff','Cache-Control':'no-store, private'})

@router.get('/privacidad', response_class=HTMLResponse)
def privacidad():
    doc='''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Privacidad · JCPS</title></head><body style="font:16px system-ui;max-width:730px;margin:40px auto;padding:18px;line-height:1.65"><a href="/">← JCPS</a><h1>Información de privacidad</h1><p>Los datos enviados por el formulario (nombre, asunto, especialidad, mensaje y documentos que voluntariamente adjuntes) se utilizan únicamente para recibir y gestionar consultas relacionadas con JCPS. Solo el personal autorizado puede acceder a la bandeja privada.</p><p>Evita enviar DNI, contraseñas, historias clínicas, datos bancarios o expedientes completos por este formulario. No se garantiza asesoría jurídica individual, defensa o patrocinio.</p><p>La recepción y el almacenamiento de la consulta no significan que se haya enviado a WhatsApp ni que la consulta haya sido aceptada como encargo profesional. Los archivos no se publican en la web.</p><p>El alojamiento gratuito puede no conservar datos después de reinicios o cambios del servicio hasta que se configure almacenamiento permanente. Solicita información sobre tratamiento o eliminación de datos mediante los canales de contacto del estudio.</p></body></html>'''
    return HTMLResponse(doc,headers={'Cache-Control':'no-store'})

@router.get('/api/estado-consultas')
def estado_consultas():
    if os.getenv('RENDER') and not DATABASE_URL:
        return JSONResponse({'operativo':False,'detalle':'Falta almacenamiento permanente para las consultas.'},status_code=503,headers={'Cache-Control':'no-store'})
    try:
        init_contact_db()
        with contact_db() as (conn, pg):
            conn.execute('SELECT 1').fetchone()
        return JSONResponse({'operativo':bool(os.getenv('JCPS_ADMIN_PASSWORD')), 'almacenamiento': 'postgres' if DATABASE_URL else 'local_temporal',
             'bandeja_configurada':bool(os.getenv('JCPS_ADMIN_PASSWORD')),
             'adjuntos_habilitados':bool(DATABASE_URL),
             'avisos_email_configurados':bool(os.getenv('JCPS_SMTP_HOST') and os.getenv('JCPS_NOTIFY_EMAILS'))},
             headers={'Cache-Control':'no-store'})
    except Exception:
        return JSONResponse({'operativo':False, 'detalle':'Almacenamiento de consultas no disponible.'},status_code=503,headers={'Cache-Control':'no-store'})