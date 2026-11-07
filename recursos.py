"""Novedades provenientes de canales RSS de Gob.pe (sin almacenar datos personales)."""
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from time import monotonic
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()
# URLs oficiales, no provenientes de la entrada del usuario.
SOURCES = (
    ('mtpe', 'Ministerio de Trabajo', 'Laboral'),
    ('sunarp', 'SUNARP', 'Civil'),
    ('pj', 'Poder Judicial', 'Civil y penal'),
)
_cache = {'until': 0.0, 'items': [], 'ok_sources': [], 'consulted': None}
_lock = asyncio.Lock()


def _read_feed(code, source, area):
    query = urlencode({'contenido': 'noticias', 'institucion': code, 'sheet': '1', 'sort_by': 'recent'})
    url = 'https://www.gob.pe/busquedas.rss?' + query
    try:
        req = Request(url, headers={'User-Agent': 'JCPS-Portal/1.0 (+https://jcps-estudio-juridico.onrender.com/)', 'Accept': 'application/rss+xml, application/xml, text/xml;q=0.9'})
        with urlopen(req, timeout=6) as response:
            payload = response.read(550_001)
        if len(payload) > 550_000:
            return []
        root = ET.fromstring(payload)
        output = []
        for item in root.findall('.//item')[:4]:
            title = ' '.join((item.findtext('title') or '').split())
            link = (item.findtext('link') or '').strip()
            host = urlparse(link)
            if not title or not link.startswith('https://') or host.hostname not in ('gob.pe', 'www.gob.pe'):
                continue
            date_raw = item.findtext('pubDate') or ''
            try:
                posted = parsedate_to_datetime(date_raw).astimezone(timezone.utc).isoformat()
            except Exception:
                posted = None
            output.append({'area': area, 'fuente': source, 'titulo': title[:175], 'url': link, 'publicado': posted})
        return output
    except Exception:
        # Si la fuente oficial no responde, la web no inventa noticias.
        return []


@router.get('/api/recursos/actualizaciones')
async def recursos_actualizaciones():
    now = monotonic()
    if now >= _cache['until']:
        async with _lock:
            if monotonic() >= _cache['until']:
                results = await asyncio.gather(*(asyncio.to_thread(_read_feed, *source) for source in SOURCES))
                _cache['items'] = [item for items in results for item in items][:10]
                _cache['ok_sources'] = [SOURCES[i][1] for i, items in enumerate(results) if items]
                _cache['consulted'] = datetime.now(timezone.utc).isoformat()
                _cache['until'] = monotonic() + 900  # Actualizar la caché cada 15 minutos.
    return JSONResponse({
        'publicaciones': _cache['items'],
        'fuentes_disponibles': _cache['ok_sources'],
        'ultima_consulta': _cache['consulted'],
        'actualizacion_automatica': True,
        'nota': 'Estas publicaciones pertenecen a sus fuentes oficiales. Si la fuente no responde, consulta el portal de la entidad.'
    }, headers={'Cache-Control': 'no-store'})
