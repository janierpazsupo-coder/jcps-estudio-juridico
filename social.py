"""JCPS Comunidad: noticias internas, seguidores anónimos, reacciones, eventos y anuncios.
No es una integración con Facebook/Meta, WhatsApp ni notificaciones push.
Almacena únicamente un identificador aleatorio de navegador para seguir/reaccionar.
"""
import html
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from consultas import contact_db, sql, DATABASE_URL

router = APIRouter()
_ready = False
_init_lock = threading.Lock()
_limits = defaultdict(deque)

SEED = [
 ('guia','Derecho Civil: antes de firmar un contrato','Revisa los datos de las partes, las obligaciones, los plazos y la documentación. Una consulta inicial puede ayudarte a identificar dudas.','', '', ''),
 ('guia','Derecho Laboral: ¿qué revisar ante un despido?','Conserva tus comunicaciones laborales y verifica fechas, documentos y beneficios que correspondan a tu régimen.','', '', ''),
]


def _persistent():
    # Render free discards local SQLite storage on restart. Never claim durable follows, likes, or posts there.
    return bool(DATABASE_URL) or not bool(os.getenv('RENDER'))


def _init():
    global _ready
    if _ready:
        return
    if not _persistent():
        raise HTTPException(503,'Comunidad pendiente de conectar a almacenamiento persistente.')
    with _init_lock:
        if _ready:
            return
        with contact_db() as (conn, pg):
            if pg:
                conn.execute('''CREATE TABLE IF NOT EXISTS jcps_social_posts (
                id BIGSERIAL PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT NOT NULL,
                contenido TEXT NOT NULL, creado TEXT NOT NULL, fecha_evento TEXT NOT NULL DEFAULT '',
                lugar TEXT NOT NULL DEFAULT '', enlace TEXT NOT NULL DEFAULT '')''')
            else:
                conn.execute('''CREATE TABLE IF NOT EXISTS jcps_social_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, titulo TEXT NOT NULL,
                contenido TEXT NOT NULL, creado TEXT NOT NULL, fecha_evento TEXT NOT NULL DEFAULT '',
                lugar TEXT NOT NULL DEFAULT '', enlace TEXT NOT NULL DEFAULT '')''')
            conn.execute('''CREATE TABLE IF NOT EXISTS jcps_social_followers (
                visitor TEXT PRIMARY KEY, creado TEXT NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS jcps_social_reactions (
                post_id BIGINT NOT NULL, visitor TEXT NOT NULL, kind TEXT NOT NULL,
                PRIMARY KEY(post_id, visitor))''')
            cur = conn.execute('SELECT COUNT(*) FROM jcps_social_posts')
            if (cur.fetchone() or (0,))[0] == 0:
                today = datetime.now(timezone.utc).isoformat()
                for row in SEED:
                    conn.execute(sql(pg,'''INSERT INTO jcps_social_posts
                        (tipo,titulo,contenido,creado,fecha_evento,lugar,enlace)
                        VALUES (?,?,?,?,?,?,?)'''),(row[0],row[1],row[2],today,row[3],row[4],row[5]))
        _ready=True


def _validate_visitor(value):
    s = str(value or '')
    if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',s,re.I):
        raise HTTPException(422,'Identificador de visitante no válido.')
    return s.lower()


def _rate(req,visitor):
    ip = req.client.host if req.client else 'unknown'
    now=time.monotonic()
    key=(ip,visitor)
    q=_limits[key]
    while q and now-q[0]>60: q.popleft()
    if len(q)>16:
        raise HTTPException(429,'Demasiadas solicitudes. Vuelve más tarde.')
    q.append(now)
    if len(_limits)>20000:
        _limits.clear()


def _origin(req):
    origin=req.headers.get('origin','').rstrip('/')
    allowed={'https://jcps-estudio-juridico.onrender.com'}
    allowed.update(x.strip().rstrip('/') for x in os.getenv('JCPS_PUBLIC_ORIGINS','').split(',') if x.strip())
    # Allow requests with no Origin (some browsers/forms); protect via SameSite+CSRF/admin and nonce for public.
    if origin and origin not in allowed and not origin.startswith(('http://127.0.0.1:', 'http://localhost:')):
        raise HTTPException(403,'Origen no permitido.')


def _counts(conn,pg,ids):
    if not ids:return {}
    v={i:{'like':0,'toque':0} for i in ids}
    for ident, kind, count in conn.execute('SELECT post_id,kind,COUNT(*) FROM jcps_social_reactions GROUP BY post_id,kind'):
        if ident in v and kind in v[ident]:v[ident][kind]=count
    return v


@router.get('/api/comunidad')
def comunidad():
    if not _persistent():
        return JSONResponse({'operativo':False,'detalle':'Falta conectar la base de datos persistente para la comunidad.','publicaciones':[], 'eventos':[], 'anuncios':[], 'recuerdos':[], 'seguidores':0},headers={'Cache-Control':'no-store'})
    try:
        _init()
        with contact_db() as (conn, pg):
            all_posts=list(conn.execute('SELECT id,tipo,titulo,contenido,creado,fecha_evento,lugar,enlace FROM jcps_social_posts ORDER BY id DESC LIMIT 90'))
            ids=[r[0] for r in all_posts]
            counts=_counts(conn,pg,ids)
            num=conn.execute('SELECT COUNT(*) FROM jcps_social_followers').fetchone()[0]
        records=[]
        for x in all_posts:
            if 'derecho penal' in str(x[2]).lower(): continue
            records.append(dict(zip(('id','tipo','titulo','contenido','creado','fecha_evento','lugar','enlace'),x),reacciones=counts.get(x[0],{'like':0,'toque':0})))
        now=datetime.now(timezone.utc)
        articles=[x for x in records if x['tipo']=='guia']
        events=[x for x in records if x['tipo']=='evento' and x['fecha_evento'] and x['fecha_evento']>=now.strftime('%Y-%m-%d')]
        ads=[x for x in records if x['tipo']=='anuncio']
        memories=[]
        for item in records:
            try:
                created=datetime.fromisoformat(item['creado'].replace('Z','+00:00'))
                if (now-created).days>=30 and created.month==now.month and created.day==now.day:
                    memories.append(item)
            except (ValueError,TypeError):pass
        return JSONResponse({'operativo':True,'publicaciones':articles[:12], 'eventos':events[:12],
                             'anuncios':ads[:12],'recuerdos':memories[:12],'seguidores':num,'actualizado':now.isoformat()},headers={'Cache-Control':'no-store'})
    except HTTPException: raise
    except Exception:
        return JSONResponse({'operativo':False,'detalle':'No se pudieron consultar las novedades.','publicaciones':[], 'eventos':[], 'anuncios':[], 'recuerdos':[], 'seguidores':0},status_code=503,headers={'Cache-Control':'no-store'})


@router.post('/api/comunidad/seguir')
async def seguir(req:Request):
    _origin(req);_init()
    obj=await req.json()
    if not isinstance(obj,dict):raise HTTPException(422,'Datos inválidos.')
    visitor=_validate_visitor(obj.get('visitor'))
    following=obj.get('seguir')
    if type(following) is not bool:raise HTTPException(422,'Decisión inválida.')
    _rate(req,visitor)
    with contact_db() as (conn,pg):
        if following:
            conn.execute(sql(pg,'INSERT INTO jcps_social_followers(visitor,creado) VALUES (?,?) ON CONFLICT(visitor) DO NOTHING'),(visitor,datetime.now(timezone.utc).isoformat()))
        else:
            conn.execute(sql(pg,'DELETE FROM jcps_social_followers WHERE visitor=?'),(visitor,))
        count=conn.execute('SELECT COUNT(*) FROM jcps_social_followers').fetchone()[0]
    return JSONResponse({'ok':True,'siguiendo':following,'seguidores':count},headers={'Cache-Control':'no-store'})


@router.post('/api/comunidad/reaccion')
async def reaccion(req:Request):
    _origin(req);_init()
    obj=await req.json()
    if not isinstance(obj,dict):raise HTTPException(422,'Datos inválidos.')
    visitor=_validate_visitor(obj.get('visitor'))
    try: post_id=int(obj.get('post_id'))
    except (TypeError,ValueError): raise HTTPException(422,'Publicación inválida.')
    kind=obj.get('tipo')
    if kind not in ('like','toque') or post_id < 1:
        raise HTTPException(422,'Reacción inválida.')
    _rate(req,visitor)
    with contact_db() as (conn,pg):
        x=conn.execute(sql(pg,'SELECT tipo FROM jcps_social_posts WHERE id=?'),(post_id,)).fetchone()
        if not x:raise HTTPException(404,'Publicación inexistente.')
        old=conn.execute(sql(pg,'SELECT kind FROM jcps_social_reactions WHERE post_id=? AND visitor=?'),(post_id,visitor)).fetchone()
        if old and old[0]==kind:
            conn.execute(sql(pg,'DELETE FROM jcps_social_reactions WHERE post_id=? AND visitor=?'),(post_id,visitor))
            chosen=''
        else:
            conn.execute(sql(pg,'''INSERT INTO jcps_social_reactions(post_id,visitor,kind)
                          VALUES (?,?,?) ON CONFLICT(post_id,visitor) DO UPDATE SET kind=excluded.kind'''),(post_id,visitor,kind))
            chosen=kind
        counts=_counts(conn,pg,[post_id]).get(post_id,{'like':0,'toque':0})
    return JSONResponse({'ok':True,'elegida':chosen,'conteos':counts},headers={'Cache-Control':'no-store'})


def _admin(req):
    if req.session.get('admin') is not True:
        raise HTTPException(403,'Acceso reservado.')


def _clean_link(url):
    if not url:return ''
    if len(url)>500:return ''
    try:
        o=urlsplit(url)
        if o.scheme!='https' or not o.hostname or o.username or o.password:return ''
    except ValueError:return ''
    return url


@router.get('/admin/comunidad',response_class=HTMLResponse)
def admin_comunidad(req:Request):
    _admin(req);_init()
    with contact_db() as (conn,pg):
        rows=list(conn.execute('SELECT id,tipo,titulo,creado FROM jcps_social_posts ORDER BY id DESC LIMIT 70'))
    esc=html.escape
    items=''.join(f'<li>#{i} · {esc(k)} · {esc(t)} <small>{esc(date[:10])}</small></li>' for i,k,t,date in rows)
    csrf=req.session.get('jcps_social_csrf')
    if not csrf:
        import secrets
        csrf=secrets.token_hex(24)
        req.session['jcps_social_csrf']=csrf
    return HTMLResponse('''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Administrar comunidad JCPS</title>
    <style>body{font:16px system-ui;max-width:800px;margin:3rem auto;padding:1.5rem;background:#18130f;color:#f9eedc}input,textarea,select,button{display:block;width:100%;box-sizing:border-box;padding:12px;margin:9px 0 18px;border:1px solid #ae905f;border-radius:8px}button{background:#dabc84;color:#18130f;font-weight:700}a{color:#e6c78f}li{margin:12px 0}label{font-weight:600}</style>
    <h1>Comunidad · JCPS</h1><p>Solo el administrador puede publicar novedades, eventos o promociones. No es un gestor de anuncios de Meta.</p><p><a href="/admin">Regresar al administrador</a></p>
    <form method="post" action="/admin/comunidad/nuevo">
    <input type="hidden" name="csrf" value="'''+csrf+'''"><label>Tipo<select name="tipo"><option value="guia">Publicación</option><option value="evento">Evento</option><option value="anuncio">Promoción JCPS</option></select></label>
    <label>Título<input name="titulo" maxlength="100" required></label><label>Descripción<textarea name="contenido" maxlength="850" rows="5" required></textarea></label>
    <label>Fecha del evento (opcional)<input type="date" name="fecha_evento"></label><label>Lugar (opcional)<input name="lugar" maxlength="120"></label><label>Enlace HTTPS verificado (opcional)<input type="url" name="enlace" maxlength="500"></label>
    <button type="submit">Publicar contenido</button></form><h2>Publicaciones registradas</h2><ul>'''+items+'''</ul></html>''')


@router.post('/admin/comunidad/nuevo')
async def admin_publicar(req:Request):
    _admin(req);_origin(req);_init()
    form=await req.form()
    import hmac
    if not hmac.compare_digest(str(form.get('csrf','')),str(req.session.get('jcps_social_csrf',''))):
        raise HTTPException(403,'Solicitud no autorizada.')
    kind=str(form.get('tipo',''))
    title=str(form.get('titulo','')).strip()
    body=str(form.get('contenido','')).strip()
    when=str(form.get('fecha_evento','')).strip()
    place=str(form.get('lugar','')).strip()
    link=_clean_link(str(form.get('enlace','')).strip())
    if kind not in ('guia','evento','anuncio') or not (4<=len(title)<=100) or not (10<=len(body)<=850) or len(place)>120:
        raise HTTPException(422,'Completa los datos correctamente.')
    if when:
        try: datetime.strptime(when,'%Y-%m-%d')
        except ValueError:raise HTTPException(422,'Fecha inválida.')
    if kind=='evento' and not when:raise HTTPException(422,'El evento requiere una fecha.')
    with contact_db() as (conn,pg):
        conn.execute(sql(pg,'''INSERT INTO jcps_social_posts(tipo,titulo,contenido,creado,fecha_evento,lugar,enlace)
                     VALUES (?,?,?,?,?,?,?)'''),(kind,title,body,datetime.now(timezone.utc).isoformat(),when,place,link))
    return RedirectResponse('/admin/comunidad',status_code=303)
