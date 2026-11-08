"""JCPS – portal web dinámico con FastAPI + SQLite.
Las consultas del público nunca se guardan aquí; la web prepara un mensaje para WhatsApp.
"""
import os
import re
import json
import hmac
import html
import time
import sqlite3
import io
import secrets
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs
from contextlib import contextmanager
from fastapi import FastAPI, Request, HTTPException
from PIL import Image, UnidentifiedImageError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("JCPS_DB_PATH", str(DATA / "jcps.sqlite3")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ADMIN_PASSWORD = os.getenv("JCPS_ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("JCPS_SESSION_SECRET") or secrets.token_urlsafe(48)

app = FastAPI(title="JCPS – Estudio Jurídico Paz Supo", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="strict", https_only=os.getenv("JCPS_HTTPS_ONLY", "0") == "1", max_age=21600)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

seed_guides = [
    ("despidos-y-reposicion", "laboral", "Despidos y reposición", "Conceptos sobre el cese del vínculo laboral y vías de información.", ["Tipos generales de cese y causas", "Plazos y documentos que pueden ser relevantes", "Consulta de fuentes oficiales MTPE y SUNAFIL"]),
    ("contratos-laborales", "laboral", "Contratos laborales", "Modalidades de contratación, jornada y naturaleza del vínculo laboral.", ["Modalidades de contratación", "Elementos de la relación laboral", "Aspectos sobre jornada y remuneración"]),
    ("beneficios-sociales", "laboral", "Beneficios sociales", "Información general sobre CTS, gratificaciones, vacaciones y liquidación.", ["Compensación por Tiempo de Servicios", "Gratificaciones y vacaciones", "Conceptos de liquidación"]),
    ("contratos-civiles", "civil", "Contratos y obligaciones", "Nociones sobre acuerdos civiles, obligaciones y cumplimiento contractual.", ["Elementos de un contrato", "Obligaciones de las partes", "Incumplimiento y documentación"]),
    ("propiedad-y-posesion", "civil", "Propiedad y posesión", "Conceptos de bienes, derechos patrimoniales y publicidad registral.", ["Diferencias entre propiedad y posesión", "Documentos e inscripción registral", "Consulta de SUNARP"]),
    ("familia-y-sucesiones", "civil", "Familia y sucesiones", "Información inicial sobre alimentos, herencias y obligaciones familiares.", ["Alimentos y responsabilidades familiares", "Sucesión intestada", "Documentación básica y vías de trámite"]),
    ("denuncia-penal", "penal", "Denuncias penales", "Información inicial sobre los canales de denuncia y actuaciones institucionales.", ["Canales de denuncia en entidades competentes", "Nociones sobre investigación preliminar", "Importancia de la asistencia de un abogado habilitado"]),
    ("garantias-procesales", "penal", "Garantías del proceso penal", "Conceptos de debido proceso, defensa y presunción de inocencia.", ["Derecho de defensa", "Presunción de inocencia", "Garantías procesales"]),
    ("flagrancia-y-diligencias", "penal", "Flagrancia y diligencias", "Conceptos generales de flagrancia y diligencias urgentes.", ["Flagrancia: noción legal", "Diligencias preliminares", "Actuaciones y profesionales competentes"]),
]
seed_faqs = []  # No se publican preguntas no solicitadas.

# Catálogo temático ampliable desde el panel administrativo.
expanded_topics = [
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Contrato de trabajo a plazo indeterminado",
    "Información general sobre contrato de trabajo a plazo indeterminado en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de contrato de trabajo a plazo indeterminado",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Contratos sujetos a modalidad",
    "Información general sobre contratos sujetos a modalidad en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de contratos sujetos a modalidad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Locación de servicios y desnaturalización",
    "Información general sobre locación de servicios y desnaturalización en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de locación de servicios y desnaturalización",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Contratos CAS y régimen público",
    "Información general sobre contratos cas y régimen público en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de contratos cas y régimen público",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Trabajo a tiempo parcial",
    "Información general sobre trabajo a tiempo parcial en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de trabajo a tiempo parcial",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Periodo de prueba",
    "Información general sobre periodo de prueba en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de periodo de prueba",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Teletrabajo y trabajo remoto",
    "Información general sobre teletrabajo y trabajo remoto en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de teletrabajo y trabajo remoto",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Trabajo del hogar",
    "Información general sobre trabajo del hogar en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de trabajo del hogar",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Prácticas preprofesionales y profesionales",
    "Información general sobre prácticas preprofesionales y profesionales en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de prácticas preprofesionales y profesionales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Tercerización e intermediación laboral",
    "Información general sobre tercerización e intermediación laboral en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de tercerización e intermediación laboral",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Trabajadores de confianza y dirección",
    "Información general sobre trabajadores de confianza y dirección en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de trabajadores de confianza y dirección",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Contratación y vínculo laboral",
    "Negociación colectiva y sindicatos",
    "Información general sobre negociación colectiva y sindicatos en el Derecho peruano. Materia: contratación y vínculo laboral.",
    [
      "Aspectos y alcance de negociación colectiva y sindicatos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Jornada laboral y horas extras",
    "Información general sobre jornada laboral y horas extras en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de jornada laboral y horas extras",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Descanso semanal y feriados",
    "Información general sobre descanso semanal y feriados en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de descanso semanal y feriados",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Remuneración y descuentos",
    "Información general sobre remuneración y descuentos en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de remuneración y descuentos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Hostigamiento sexual laboral",
    "Información general sobre hostigamiento sexual laboral en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de hostigamiento sexual laboral",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Discriminación e igualdad salarial",
    "Información general sobre discriminación e igualdad salarial en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de discriminación e igualdad salarial",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Seguridad y salud en el trabajo",
    "Información general sobre seguridad y salud en el trabajo en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de seguridad y salud en el trabajo",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Accidentes de trabajo y enfermedades ocupacionales",
    "Información general sobre accidentes de trabajo y enfermedades ocupacionales en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de accidentes de trabajo y enfermedades ocupacionales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Maternidad, paternidad y lactancia",
    "Información general sobre maternidad, paternidad y lactancia en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de maternidad, paternidad y lactancia",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Acoso laboral y hostilidad",
    "Información general sobre acoso laboral y hostilidad en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de acoso laboral y hostilidad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Licencias y permisos",
    "Información general sobre licencias y permisos en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de licencias y permisos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Seguridad social y EsSalud",
    "Información general sobre seguridad social y essalud en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de seguridad social y essalud",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Derechos durante el trabajo",
    "Aportes ONP y AFP",
    "Información general sobre aportes onp y afp en el Derecho peruano. Materia: derechos durante el trabajo.",
    [
      "Aspectos y alcance de aportes onp y afp",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "CTS y compensación por tiempo de servicios",
    "Información general sobre cts y compensación por tiempo de servicios en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de cts y compensación por tiempo de servicios",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Gratificaciones y bonificaciones",
    "Información general sobre gratificaciones y bonificaciones en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de gratificaciones y bonificaciones",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Vacaciones y vacaciones truncas",
    "Información general sobre vacaciones y vacaciones truncas en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de vacaciones y vacaciones truncas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Liquidación de beneficios sociales",
    "Información general sobre liquidación de beneficios sociales en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de liquidación de beneficios sociales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Despido arbitrario",
    "Información general sobre despido arbitrario en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de despido arbitrario",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Despido nulo",
    "Información general sobre despido nulo en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de despido nulo",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Despido fraudulento",
    "Información general sobre despido fraudulento en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de despido fraudulento",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Reposición y estabilidad laboral",
    "Información general sobre reposición y estabilidad laboral en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de reposición y estabilidad laboral",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Renuncia y mutuo disenso",
    "Información general sobre renuncia y mutuo disenso en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de renuncia y mutuo disenso",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Suspensión perfecta e imperfecta",
    "Información general sobre suspensión perfecta e imperfecta en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de suspensión perfecta e imperfecta",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Inspecciones SUNAFIL",
    "Información general sobre inspecciones sunafil en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de inspecciones sunafil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Denuncias ante MTPE",
    "Información general sobre denuncias ante mtpe en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de denuncias ante mtpe",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Conciliación y juicio laboral",
    "Información general sobre conciliación y juicio laboral en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de conciliación y juicio laboral",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Ejecución de sentencias laborales",
    "Información general sobre ejecución de sentencias laborales en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de ejecución de sentencias laborales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Negociación de deudas laborales",
    "Información general sobre negociación de deudas laborales en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de negociación de deudas laborales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Beneficios, cese y defensa",
    "Empleo informal y acreditación del vínculo",
    "Información general sobre empleo informal y acreditación del vínculo en el Derecho peruano. Materia: beneficios, cese y defensa.",
    [
      "Aspectos y alcance de empleo informal y acreditación del vínculo",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Régimen laboral de micro y pequeña empresa",
    "Información general sobre régimen laboral de micro y pequeña empresa en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de régimen laboral de micro y pequeña empresa",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Construcción civil",
    "Información general sobre construcción civil en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de construcción civil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Régimen agrario",
    "Información general sobre régimen agrario en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de régimen agrario",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Trabajadores del sector salud",
    "Información general sobre trabajadores del sector salud en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de trabajadores del sector salud",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Trabajadores docentes y auxiliares",
    "Información general sobre trabajadores docentes y auxiliares en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de trabajadores docentes y auxiliares",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Servidores públicos 276 y 728",
    "Información general sobre servidores públicos 276 y 728 en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de servidores públicos 276 y 728",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Servicio civil SERVIR",
    "Información general sobre servicio civil servir en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de servicio civil servir",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Trabajo de adolescentes y protección laboral",
    "Información general sobre trabajo de adolescentes y protección laboral en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de trabajo de adolescentes y protección laboral",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Movilidad laboral internacional",
    "Información general sobre movilidad laboral internacional en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de movilidad laboral internacional",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "laboral",
    "Sectores y regímenes específicos",
    "Prestación de servicios por recibo de honorarios",
    "Información general sobre prestación de servicios por recibo de honorarios en el Derecho peruano. Materia: sectores y regímenes específicos.",
    [
      "Aspectos y alcance de prestación de servicios por recibo de honorarios",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Compraventa de inmuebles",
    "Información general sobre compraventa de inmuebles en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de compraventa de inmuebles",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Compraventa de vehículos",
    "Información general sobre compraventa de vehículos en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de compraventa de vehículos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Arrendamiento y desalojo",
    "Información general sobre arrendamiento y desalojo en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de arrendamiento y desalojo",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Préstamo y reconocimiento de deuda",
    "Información general sobre préstamo y reconocimiento de deuda en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de préstamo y reconocimiento de deuda",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Mutuo, comodato y depósito",
    "Información general sobre mutuo, comodato y depósito en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de mutuo, comodato y depósito",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Obligaciones de dar, hacer y no hacer",
    "Información general sobre obligaciones de dar, hacer y no hacer en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de obligaciones de dar, hacer y no hacer",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Incumplimiento contractual y resolución",
    "Información general sobre incumplimiento contractual y resolución en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de incumplimiento contractual y resolución",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Nulidad, anulabilidad y simulación",
    "Información general sobre nulidad, anulabilidad y simulación en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de nulidad, anulabilidad y simulación",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Prescripción y caducidad civil",
    "Información general sobre prescripción y caducidad civil en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de prescripción y caducidad civil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Responsabilidad civil contractual",
    "Información general sobre responsabilidad civil contractual en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de responsabilidad civil contractual",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Responsabilidad extracontractual e indemnización",
    "Información general sobre responsabilidad extracontractual e indemnización en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de responsabilidad extracontractual e indemnización",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Conciliación extrajudicial",
    "Información general sobre conciliación extrajudicial en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de conciliación extrajudicial",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Cartas notariales y requerimientos",
    "Información general sobre cartas notariales y requerimientos en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de cartas notariales y requerimientos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Garantías personales y reales",
    "Información general sobre garantías personales y reales en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de garantías personales y reales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Hipotecas y garantías mobiliarias",
    "Información general sobre hipotecas y garantías mobiliarias en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de hipotecas y garantías mobiliarias",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Donación y anticipo de legítima",
    "Información general sobre donación y anticipo de legítima en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de donación y anticipo de legítima",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Contratos y obligaciones",
    "Contratos electrónicos y firma digital",
    "Información general sobre contratos electrónicos y firma digital en el Derecho peruano. Materia: contratos y obligaciones.",
    [
      "Aspectos y alcance de contratos electrónicos y firma digital",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Derecho de propiedad",
    "Información general sobre derecho de propiedad en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de derecho de propiedad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Posesión y defensa posesoria",
    "Información general sobre posesión y defensa posesoria en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de posesión y defensa posesoria",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Prescripción adquisitiva de dominio",
    "Información general sobre prescripción adquisitiva de dominio en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de prescripción adquisitiva de dominio",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Reivindicación",
    "Información general sobre reivindicación en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de reivindicación",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Saneamiento físico legal",
    "Información general sobre saneamiento físico legal en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de saneamiento físico legal",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Independización y acumulación de predios",
    "Información general sobre independización y acumulación de predios en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de independización y acumulación de predios",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Copropiedad y división y partición",
    "Información general sobre copropiedad y división y partición en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de copropiedad y división y partición",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Servidumbres",
    "Información general sobre servidumbres en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de servidumbres",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Linderos y áreas",
    "Información general sobre linderos y áreas en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de linderos y áreas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Régimen de propiedad exclusiva y común",
    "Información general sobre régimen de propiedad exclusiva y común en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de régimen de propiedad exclusiva y común",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Calificación e inscripción en SUNARP",
    "Información general sobre calificación e inscripción en sunarp en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de calificación e inscripción en sunarp",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Rectificación registral",
    "Información general sobre rectificación registral en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de rectificación registral",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Mejor derecho de propiedad",
    "Información general sobre mejor derecho de propiedad en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de mejor derecho de propiedad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Bienes, posesión y registros",
    "Mejoras en inmuebles",
    "Información general sobre mejoras en inmuebles en el Derecho peruano. Materia: bienes, posesión y registros.",
    [
      "Aspectos y alcance de mejoras en inmuebles",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Pensión de alimentos",
    "Información general sobre pensión de alimentos en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de pensión de alimentos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Tenencia y régimen de visitas",
    "Información general sobre tenencia y régimen de visitas en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de tenencia y régimen de visitas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Filiación y reconocimiento de paternidad",
    "Información general sobre filiación y reconocimiento de paternidad en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de filiación y reconocimiento de paternidad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Divorcio y separación",
    "Información general sobre divorcio y separación en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de divorcio y separación",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Unión de hecho",
    "Información general sobre unión de hecho en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de unión de hecho",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Régimen patrimonial del matrimonio",
    "Información general sobre régimen patrimonial del matrimonio en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de régimen patrimonial del matrimonio",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Adopción",
    "Información general sobre adopción en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de adopción",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Tutela, curatela y apoyos",
    "Información general sobre tutela, curatela y apoyos en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de tutela, curatela y apoyos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Violencia familiar: medidas de protección",
    "Información general sobre violencia familiar: medidas de protección en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de violencia familiar: medidas de protección",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Sucesión intestada",
    "Información general sobre sucesión intestada en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de sucesión intestada",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Testamentos y legítima",
    "Información general sobre testamentos y legítima en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de testamentos y legítima",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Petición de herencia",
    "Información general sobre petición de herencia en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de petición de herencia",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Partición hereditaria",
    "Información general sobre partición hereditaria en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de partición hereditaria",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Rectificación de partida y nombre",
    "Información general sobre rectificación de partida y nombre en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de rectificación de partida y nombre",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Familia, personas y sucesiones",
    "Capacidad jurídica y derechos de la personalidad",
    "Información general sobre capacidad jurídica y derechos de la personalidad en el Derecho peruano. Materia: familia, personas y sucesiones.",
    [
      "Aspectos y alcance de capacidad jurídica y derechos de la personalidad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Demanda y contestación civil",
    "Información general sobre demanda y contestación civil en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de demanda y contestación civil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Medidas cautelares civiles",
    "Información general sobre medidas cautelares civiles en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de medidas cautelares civiles",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Ejecución de obligación y cobro de deuda",
    "Información general sobre ejecución de obligación y cobro de deuda en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de ejecución de obligación y cobro de deuda",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Títulos valores y protesto",
    "Información general sobre títulos valores y protesto en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de títulos valores y protesto",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Proceso de conocimiento y abreviado",
    "Información general sobre proceso de conocimiento y abreviado en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de proceso de conocimiento y abreviado",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Proceso sumarísimo",
    "Información general sobre proceso sumarísimo en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de proceso sumarísimo",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Arbitraje civil",
    "Información general sobre arbitraje civil en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de arbitraje civil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Defensa del consumidor en contratos",
    "Información general sobre defensa del consumidor en contratos en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de defensa del consumidor en contratos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Propiedad intelectual y derechos de autor",
    "Información general sobre propiedad intelectual y derechos de autor en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de propiedad intelectual y derechos de autor",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Asociaciones y personas jurídicas",
    "Información general sobre asociaciones y personas jurídicas en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de asociaciones y personas jurídicas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Sociedades y acuerdos privados",
    "Información general sobre sociedades y acuerdos privados en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de sociedades y acuerdos privados",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Protección de datos personales",
    "Información general sobre protección de datos personales en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de protección de datos personales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Responsabilidad médica civil",
    "Información general sobre responsabilidad médica civil en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de responsabilidad médica civil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Contratos de seguros",
    "Información general sobre contratos de seguros en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de contratos de seguros",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "civil",
    "Proceso y actividad económica civil",
    "Comercio electrónico y contratos digitales",
    "Información general sobre comercio electrónico y contratos digitales en el Derecho peruano. Materia: proceso y actividad económica civil.",
    [
      "Aspectos y alcance de comercio electrónico y contratos digitales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Presentación de denuncia penal",
    "Información general sobre presentación de denuncia penal en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de presentación de denuncia penal",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Diligencias preliminares",
    "Información general sobre diligencias preliminares en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de diligencias preliminares",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Investigación preparatoria",
    "Información general sobre investigación preparatoria en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de investigación preparatoria",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Derecho de defensa y asesoría",
    "Información general sobre derecho de defensa y asesoría en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de derecho de defensa y asesoría",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Presunción de inocencia",
    "Información general sobre presunción de inocencia en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de presunción de inocencia",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Flagrancia y detención",
    "Información general sobre flagrancia y detención en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de flagrancia y detención",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Prisión preventiva y comparecencia",
    "Información general sobre prisión preventiva y comparecencia en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de prisión preventiva y comparecencia",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Control de plazos procesales",
    "Información general sobre control de plazos procesales en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de control de plazos procesales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Medidas de protección de víctimas",
    "Información general sobre medidas de protección de víctimas en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de medidas de protección de víctimas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Constitución en actor civil",
    "Información general sobre constitución en actor civil en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de constitución en actor civil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Etapa intermedia y acusación",
    "Información general sobre etapa intermedia y acusación en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de etapa intermedia y acusación",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Juicio oral y prueba",
    "Información general sobre juicio oral y prueba en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de juicio oral y prueba",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Recursos e impugnaciones penales",
    "Información general sobre recursos e impugnaciones penales en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de recursos e impugnaciones penales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Hábeas corpus y derechos fundamentales",
    "Información general sobre hábeas corpus y derechos fundamentales en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de hábeas corpus y derechos fundamentales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Terminación anticipada y salidas alternativas",
    "Información general sobre terminación anticipada y salidas alternativas en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de terminación anticipada y salidas alternativas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Denuncias, garantías y proceso",
    "Ejecución penal y beneficios penitenciarios",
    "Información general sobre ejecución penal y beneficios penitenciarios en el Derecho peruano. Materia: denuncias, garantías y proceso.",
    [
      "Aspectos y alcance de ejecución penal y beneficios penitenciarios",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Lesiones y agresiones",
    "Información general sobre lesiones y agresiones en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de lesiones y agresiones",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Violencia contra integrantes del grupo familiar",
    "Información general sobre violencia contra integrantes del grupo familiar en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de violencia contra integrantes del grupo familiar",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Amenazas y coacción",
    "Información general sobre amenazas y coacción en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de amenazas y coacción",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Acoso y hostigamiento",
    "Información general sobre acoso y hostigamiento en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de acoso y hostigamiento",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Omisión a la asistencia familiar",
    "Información general sobre omisión a la asistencia familiar en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de omisión a la asistencia familiar",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Homicidio y delitos contra la vida",
    "Información general sobre homicidio y delitos contra la vida en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de homicidio y delitos contra la vida",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Delitos contra la libertad personal",
    "Información general sobre delitos contra la libertad personal en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de delitos contra la libertad personal",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Delitos contra el honor",
    "Información general sobre delitos contra el honor en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de delitos contra el honor",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Delitos contra la intimidad",
    "Información general sobre delitos contra la intimidad en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de delitos contra la intimidad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Trata de personas: protección y denuncia",
    "Información general sobre trata de personas: protección y denuncia en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de trata de personas: protección y denuncia",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos contra las personas",
    "Delitos sexuales: protección de víctimas",
    "Información general sobre delitos sexuales: protección de víctimas en el Derecho peruano. Materia: delitos contra las personas.",
    [
      "Aspectos y alcance de delitos sexuales: protección de víctimas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Hurto y robo",
    "Información general sobre hurto y robo en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de hurto y robo",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Estafa y estafa informática",
    "Información general sobre estafa y estafa informática en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de estafa y estafa informática",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Apropiación ilícita",
    "Información general sobre apropiación ilícita en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de apropiación ilícita",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Usurpación",
    "Información general sobre usurpación en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de usurpación",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Daños y delitos patrimoniales",
    "Información general sobre daños y delitos patrimoniales en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de daños y delitos patrimoniales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Extorsión: denuncia y protección",
    "Información general sobre extorsión: denuncia y protección en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de extorsión: denuncia y protección",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Receptación",
    "Información general sobre receptación en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de receptación",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Lavado de activos: nociones legales",
    "Información general sobre lavado de activos: nociones legales en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de lavado de activos: nociones legales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Delitos tributarios y aduaneros",
    "Información general sobre delitos tributarios y aduaneros en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de delitos tributarios y aduaneros",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Delitos contra la fe pública",
    "Información general sobre delitos contra la fe pública en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de delitos contra la fe pública",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Falsificación de documentos",
    "Información general sobre falsificación de documentos en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de falsificación de documentos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Fraude en la administración de personas jurídicas",
    "Información general sobre fraude en la administración de personas jurídicas en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de fraude en la administración de personas jurídicas",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Delitos informáticos",
    "Información general sobre delitos informáticos en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de delitos informáticos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Delitos patrimoniales y económicos",
    "Fraude mediante medios electrónicos",
    "Información general sobre fraude mediante medios electrónicos en el Derecho peruano. Materia: delitos patrimoniales y económicos.",
    [
      "Aspectos y alcance de fraude mediante medios electrónicos",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Corrupción de funcionarios",
    "Información general sobre corrupción de funcionarios en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de corrupción de funcionarios",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Cohecho",
    "Información general sobre cohecho en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de cohecho",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Peculado",
    "Información general sobre peculado en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de peculado",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Colusión",
    "Información general sobre colusión en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de colusión",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Negociación incompatible",
    "Información general sobre negociación incompatible en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de negociación incompatible",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Abuso de autoridad",
    "Información general sobre abuso de autoridad en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de abuso de autoridad",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Falsedad ideológica",
    "Información general sobre falsedad ideológica en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de falsedad ideológica",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Delitos ambientales",
    "Información general sobre delitos ambientales en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de delitos ambientales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Delitos contra la seguridad pública",
    "Información general sobre delitos contra la seguridad pública en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de delitos contra la seguridad pública",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Organización criminal: garantías procesales",
    "Información general sobre organización criminal: garantías procesales en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de organización criminal: garantías procesales",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Responsabilidad penal de adolescentes",
    "Información general sobre responsabilidad penal de adolescentes en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de responsabilidad penal de adolescentes",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Derechos de víctimas y reparación civil",
    "Información general sobre derechos de víctimas y reparación civil en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de derechos de víctimas y reparación civil",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Prescripción de la acción penal",
    "Información general sobre prescripción de la acción penal en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de prescripción de la acción penal",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Extradición y cooperación judicial",
    "Información general sobre extradición y cooperación judicial en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de extradición y cooperación judicial",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ],
  [
    "penal",
    "Administración pública y temas especiales",
    "Delitos contra la administración de justicia",
    "Información general sobre delitos contra la administración de justicia en el Derecho peruano. Materia: administración pública y temas especiales.",
    [
      "Aspectos y alcance de delitos contra la administración de justicia",
      "Documentación que puede resultar pertinente",
      "Entidades competentes y vías de consulta",
      "Normativa vigente y jurisprudencia oficial aplicable"
    ]
  ]
]


@contextmanager
def db():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def slugify_for_seed(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+','-',s).strip('-')[:90] or 'asunto'

def init_db():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS guides(id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, area TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, details TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, position INTEGER NOT NULL DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS faqs(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, answer TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if c.execute("SELECT COUNT(*) FROM guides").fetchone()[0] == 0:
            for i, x in enumerate(seed_guides):
                slug, area, title, summary, details = x
                if area not in ('laboral','civil'): continue
                c.execute("INSERT INTO guides(slug,area,title,summary,details,enabled,position) VALUES(?,?,?,?,?,1,?)", (slug,area,title,summary,json.dumps(details,ensure_ascii=False),i))
        if c.execute("SELECT COUNT(*) FROM faqs").fetchone()[0] == 0:
            for i, (q, a) in enumerate(seed_faqs):
                c.execute("INSERT INTO faqs(question,answer,position) VALUES(?,?,?)", (q,a,i))
        # Se añaden temas faltantes sin reescribir ni borrar guías editadas previamente.
        for index,(area,grupo,titulo,resumen,detalles) in enumerate(expanded_topics, start=100):
            if area not in ('laboral','civil'): continue
            slug=slugify_for_seed(grupo+'-'+titulo)
            c.execute("INSERT OR IGNORE INTO guides(slug,area,title,summary,details,enabled,position) VALUES(?,?,?,?,?,1,?)",
                      (slug,area,titulo,resumen,json.dumps(detalles,ensure_ascii=False),index))
        c.execute("DELETE FROM guides WHERE area='penal'")
        c.execute("DELETE FROM settings WHERE key='whatsapp_darly'")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('whatsapp','51927859384')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('contact_name','Janier Carloman Paz Supo')")

init_db()


def guide_dict(row):
    d=dict(row)
    try: d['details']=json.loads(d['details'])
    except (ValueError, TypeError): d['details']=[]
    d['enabled']=bool(d['enabled'])
    return d

@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

@app.get("/api/public")
def public():
    with db() as c:
        guides=[guide_dict(row) for row in c.execute("SELECT * FROM guides WHERE enabled=1 AND area IN ('laboral','civil') ORDER BY position,id")]
        faqs=[dict(row) for row in c.execute("SELECT * FROM faqs ORDER BY position,id")]
        settings=dict(c.execute("SELECT key,value FROM settings"))
    # Avoid caching when administrators update content.
    return JSONResponse({"guides":guides,"faqs":faqs,"whatsapp":settings.get("whatsapp"),"contact_name":settings.get("contact_name")}, headers={"Cache-Control":"no-store"})

@app.get("/orientacion/{slug}", response_class=HTMLResponse)
def detail(slug: str):
    with db() as c:
        row=c.execute("SELECT * FROM guides WHERE slug=? AND enabled=1 AND area IN ('laboral','civil')",(slug,)).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="No se encontró esa materia")
    item=guide_dict(row); clean=html.escape
    area={"civil":"Derecho Civil","laboral":"Derecho Laboral"}.get(item['area'],"Información jurídica")
    lis=''.join(f'<li>{clean(str(x))}</li>' for x in item['details'])
    return f'''<!doctype html><html lang="es-PE"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{clean(item['title'])} | JCPS</title><meta name="description" content="{clean(item['summary'])}"><style>body{{font-family:system-ui,sans-serif;background:#0a1725;color:#f6f2e8;margin:0;line-height:1.7}}main{{max-width:770px;margin:10vh auto;padding:28px}}a{{color:#e2bf89}}h1{{font-family:Georgia,serif;font-size:clamp(2.2rem,6vw,4.1rem)}}.tag{{color:#e2bf89;text-transform:uppercase;letter-spacing:2px;font-size:.82rem}}.card{{background:#142538;border:1px solid #4e4b42;padding:30px;border-radius:20px}}li{{padding:9px 0}}.btn{{display:inline-block;padding:12px 20px;margin:10px 10px 0 0;background:#d4b07a;color:#102030;border-radius:10px;font-weight:700;text-decoration:none}}</style></head><body><main><a href="/#especialidades">← Regresar a las especialidades</a><p class="tag">JCPS · {clean(area)}</p><h1>{clean(item['title'])}</h1><p>{clean(item['summary'])}</p><div class="card"><h2>Temas generales</h2><ul>{lis}</ul><p>Material informativo: no sustituye la atención profesional ni el análisis individual de un caso.</p></div><a class="btn" href="/#contacto">Enviar consulta ↗</a></main></body></html>'''

# Small per-IP backoff for password attempts (memory only); use a proxy-level rate limit in production.
login_attempts: dict[str,list[float]]={}

def esc(v): return html.escape(str(v or ''), quote=True)

async def parse_form(req:Request):
    data=(await req.body()).decode('utf-8',errors='replace')
    if len(data)>18000: raise HTTPException(413, "Formulario demasiado grande")
    return {k:v[0] for k,v in parse_qs(data,keep_blank_values=True).items()}

def authorized(req:Request):
    return bool(ADMIN_PASSWORD) and req.session.get('admin') is True

def require_admin(req:Request,form:dict):
    if not authorized(req): raise HTTPException(403,"Acceso no autorizado")
    a=req.session.get('csrf','');b=form.get('csrf','')
    if not a or not hmac.compare_digest(a,b): raise HTTPException(403,"Token de formulario inválido")

def go_admin(msg=""):
    url='/admin' + ('?msg='+str(msg) if msg else '')
    return RedirectResponse(url, status_code=303)

@app.get('/admin',response_class=HTMLResponse)
def admin(req:Request):
    head='''<!doctype html><html lang="es-PE"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Administración | JCPS</title><style>body{font-family:system-ui,Arial,sans-serif;margin:0;background:#0a1725;color:#eee7d8;line-height:1.5}main{max-width:1120px;margin:0 auto;padding:38px 20px}h1,h2{font-family:Georgia,serif;font-weight:500}h1{font-size:2.3rem}h2{color:#e1bd87}a{color:#e1bd87}form,.panel{background:#122338;border:1px solid #4b4750;border-radius:14px;padding:19px;margin:15px 0}input,select,textarea{box-sizing:border-box;width:100%;padding:11px;border-radius:8px;border:1px solid #788194;background:#fbf9f4;color:#102030;font:inherit;margin:5px 0 13px}label{display:block;font-size:.91rem}button{background:#dab77e;color:#102030;font-weight:700;border:0;border-radius:8px;padding:11px 17px;cursor:pointer}button.danger{background:#de9d9d}small,.hint{color:#b8c2cf}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:12px}.grid>form{margin:0}.info{background:#194331;color:#c6f6dd;padding:12px;border-radius:8px}.top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}details{padding:8px 0}summary{cursor:pointer;color:#e1bd87}textarea{min-height:95px}</style></head><body><main>'''
    foot='</main></body></html>'
    if not ADMIN_PASSWORD:
        return head+'''<h1>Panel deshabilitado</h1><p>Define las variables de entorno <code>JCPS_ADMIN_PASSWORD</code> y <code>JCPS_SESSION_SECRET</code> en el servidor antes de gestionar contenidos.</p><a href="/">Volver al sitio</a>'''+foot
    if not authorized(req):
        return head+'''<h1>Administración JCPS</h1><p>Acceso reservado para la persona responsable del portal.</p><form method="post" action="/admin/login" style="max-width:430px"><label>Contraseña<input type="password" name="password" required autocomplete="current-password"></label><button>Ingresar</button></form><p><a href="/">Volver al portal</a></p>'''+foot
    if 'csrf' not in req.session: req.session['csrf']=secrets.token_urlsafe(32)
    token=esc(req.session['csrf']);h=f'<input type="hidden" name="csrf" value="{token}">'
    with db() as c:
        gs=[guide_dict(x) for x in c.execute("SELECT * FROM guides WHERE area IN ('laboral','civil') ORDER BY area,position,id")]
        fs=[dict(x) for x in c.execute('SELECT * FROM faqs ORDER BY position,id')]
        cfg=dict(c.execute('SELECT key,value FROM settings'))
    body=f'<div class="top"><h1>Panel de contenidos JCPS</h1><form action="/admin/logout" method="post">{h}<button>Cerrar sesión</button></form></div><div class="panel"><h2>Consultas recibidas</h2><p>Abre la bandeja privada para revisar mensajes y descargar documentos enviados desde la página.</p><p><a href="/admin/consultas" style="display:inline-block;background:#dab77e;color:#102030;padding:12px 18px;border-radius:9px;text-decoration:none;font-weight:bold">Abrir bandeja de consultas →</a></p><p><a href="/admin/comunidad" style="display:inline-block;background:#dab77e;color:#102030;padding:12px 18px;border-radius:9px;text-decoration:none;font-weight:bold">Administrar Comunidad, Eventos y Promociones →</a></p></div><p>Edita especialidades, temas y contactos. Los cambios de contenido guardados en la base local pueden perderse en el plan gratuito.</p>'
    if req.query_params.get('msg'): body+='<p class="info">Cambios procesados. Revisa el contenido a continuación.</p>'
    body+=f'''<h2>Logotipos originales en el encabezado</h2><div class="panel"><p>Sube únicamente tus archivos originales. Se mostrarán arriba, junto a «PAZ SUPO». Si no hay archivo, el sitio no inventa ni muestra un logotipo de relleno.</p><div class="grid"><label>Logotipo izquierdo<input type="file" id="original-izquierdo" accept="image/png,image/jpeg,image/webp"></label><label>Logotipo derecho<input type="file" id="original-derecho" accept="image/png,image/jpeg,image/webp"></label></div><button type="button" onclick="subirLogo('izquierdo')">Subir logotipo izquierdo</button> <button type="button" onclick="subirLogo('derecho')">Subir logotipo derecho</button><p class="hint" id="logoStatus" role="status"></p></div><script>async function subirLogo(side){{const input=document.getElementById('original-'+side),msg=document.getElementById('logoStatus'),file=input.files[0];if(!file){{msg.textContent='Selecciona primero el archivo original.';return}}if(file.size>5*1024*1024){{msg.textContent='El archivo supera 5 MB.';return}}try{{const response=await fetch('/admin/logo/'+side,{{method:'POST',headers:{{'X-CSRF-Token':'{token}','Content-Type':file.type}},body:file}});if(!response.ok)throw new Error('No se pudo subir el archivo original (HTTP '+response.status+').');msg.textContent='Logotipo original guardado. Actualiza la portada para comprobarlo.';}}catch(error){{msg.textContent=error.message}}}}</script>'''
    body+=f'''<h2>Contacto WhatsApp</h2><form action="/admin/config" method="post">{h}<div class="grid"><label>Número en formato internacional, solo dígitos (Perú: 51 + 9 cifras)<input name="whatsapp" required pattern="51[0-9]{{9}}" maxlength="11" value="{esc(cfg.get('whatsapp'))}"></label><label>Persona de contacto<input name="contact_name" maxlength="90" required value="{esc(cfg.get('contact_name'))}"></label></div><button>Guardar WhatsApp</button></form><p class="hint">El aviso automático por WhatsApp utiliza WhatsApp Business Platform: el destinatario debe coincidir con la variable privada JCPS_WA_TO configurada en Render. Revisa WHATSAPP_CONFIGURACION.md; cambiar este número visible no cambia por sí solo las credenciales ni el número autorizado de Meta.</p><h2>Crear nueva guía</h2><form method="post" action="/admin/guide">{h}<div class="grid"><label>Especialidad<select name="area"><option value="laboral">Laboral</option><option value="civil">Civil</option></select></label><label>Título<input name="title" maxlength="110" required></label></div><label>Descripción breve<input name="summary" maxlength="350" required></label><label>Temas (uno por línea)<textarea name="details" required maxlength="1500"></textarea></label><button>Crear guía</button></form><h2>Guías existentes</h2><div class="grid">'''
    for g in gs:
        selected=''.join(f'<option value="{x}" {"selected" if g["area"]==x else ""}>{x.title()}</option>' for x in ('laboral','civil'))
        topics='\n'.join(g['details'])
        body+=f'''<form action="/admin/guide" method="post">{h}<input type="hidden" name="id" value="{g['id']}"><label>Área<select name="area">{selected}</select></label><label>Título<input name="title" maxlength="110" required value="{esc(g['title'])}"></label><label>Resumen<textarea name="summary" required maxlength="350">{esc(g['summary'])}</textarea></label><label>Temas<textarea name="details" maxlength="1500">{esc(topics)}</textarea></label><label>Orden<input type="number" name="position" min="0" max="999" value="{g['position']}"></label><label><input type="checkbox" name="enabled" value="1" {"checked" if g['enabled'] else ""} style="width:auto"> Visible</label><button>Guardar</button><button class="danger" type="submit" name="delete" value="1" onclick="return confirm('¿Eliminar definitivamente esta guía?')">Eliminar</button></form>'''
    body+='</div><h2>Preguntas frecuentes</h2><div class="grid">'
    for f in fs:
        body+=f'''<form method="post" action="/admin/faq">{h}<input type="hidden" name="id" value="{f['id']}"><label>Pregunta<input name="question" required maxlength="180" value="{esc(f['question'])}"></label><label>Respuesta<textarea name="answer" required maxlength="900">{esc(f['answer'])}</textarea></label><button>Guardar</button><button type="submit" class="danger" name="delete" value="1" onclick="return confirm('¿Eliminar la pregunta?')">Eliminar</button></form>'''
    body+=f'''</div><h3>Añadir una pregunta</h3><form method="post" action="/admin/faq">{h}<label>Pregunta<input name="question" required maxlength="180"></label><label>Respuesta<textarea name="answer" required maxlength="900"></textarea></label><button>Añadir pregunta</button></form><p class="hint">Las consultas del nuevo formulario se guardan en una bandeja protegida. En alojamiento gratuito, el almacenamiento local no es permanente; se requiere configurar una base externa para conservar la información. <a href="/">Ver página pública ↗</a></p>'''
    return head+body+foot

@app.post('/admin/login')
async def login(req:Request):
    if not ADMIN_PASSWORD: raise HTTPException(503, "Panel no configurado")
    ip=req.client.host if req.client else 'unknown';now=time.monotonic()
    attempts=[x for x in login_attempts.get(ip,[]) if now-x<900]
    if len(attempts)>=10: raise HTTPException(429,'Demasiados intentos. Inténtalo más tarde.')
    f=await parse_form(req)
    if not hmac.compare_digest(f.get('password',''),ADMIN_PASSWORD):
        attempts.append(now);login_attempts[ip]=attempts
        return HTMLResponse('<p>Contraseña incorrecta. <a href="/admin">Volver</a></p>',status_code=401)
    login_attempts.pop(ip,None)
    req.session.clear();req.session['admin']=True;req.session['csrf']=secrets.token_urlsafe(32)
    return go_admin()

@app.post('/admin/logout')
async def logout(req:Request):
    f=await parse_form(req);require_admin(req,f);req.session.clear()
    return RedirectResponse('/admin',status_code=303)

@app.post('/admin/config')
async def edit_config(req:Request):
    f=await parse_form(req);require_admin(req,f)
    phone=re.sub(r'\D','',f.get('whatsapp',''))
    name=f.get('contact_name','').strip()
    if not re.fullmatch(r'51\d{9}',phone) or not(1<=len(name)<=90): raise HTTPException(422,'Número o nombre inválido')
    with db() as c:
        c.execute("INSERT INTO settings(key,value) VALUES('whatsapp',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(phone,))
        c.execute("INSERT INTO settings(key,value) VALUES('contact_name',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(name,))
    return go_admin('ok')

def slugify(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode('ascii').lower()
    return (re.sub(r'[^a-z0-9]+','-',s).strip('-')[:65] or 'tema')

@app.post('/admin/guide')
async def edit_guide(req:Request):
    f=await parse_form(req);require_admin(req,f)
    identifier=f.get('id','')
    if f.get('delete')=='1' and identifier.isdigit():
        with db() as c:c.execute('DELETE FROM guides WHERE id=?',(int(identifier),))
        return go_admin('ok')
    area=f.get('area','');title=f.get('title','').strip();summary=f.get('summary','').strip()
    details=[x.strip() for x in f.get('details','').splitlines() if x.strip()]
    if area not in ('laboral','civil') or not(3<=len(title)<=110) or not(8<=len(summary)<=350) or len(details)>15 or sum(len(x) for x in details)>1450:raise HTTPException(422,'Datos de guía inválidos')
    position=min(max(int(f.get('position','0')) if f.get('position','0').isdigit() else 0,0),999)
    enabled=1 if f.get('enabled')=='1' else 0
    with db() as c:
        if identifier.isdigit():
            c.execute('UPDATE guides SET area=?,title=?,summary=?,details=?,enabled=?,position=? WHERE id=?',(area,title,summary,json.dumps(details,ensure_ascii=False),enabled,position,int(identifier)))
        else:
            slug=slugify(title)+'-'+secrets.token_hex(3)
            c.execute('INSERT INTO guides(slug,area,title,summary,details,enabled,position) VALUES(?,?,?,?,?,?,?)',(slug,area,title,summary,json.dumps(details,ensure_ascii=False),1,position))
    return go_admin('ok')

@app.post('/admin/faq')
async def edit_faq(req:Request):
    f=await parse_form(req);require_admin(req,f)
    identifier=f.get('id','')
    with db() as c:
        if f.get('delete')=='1' and identifier.isdigit():
            c.execute('DELETE FROM faqs WHERE id=?',(int(identifier),))
        else:
            question=f.get('question','').strip();answer=f.get('answer','').strip()
            if not(5<=len(question)<=180) or not(10<=len(answer)<=900):raise HTTPException(422,'Pregunta o respuesta inválida')
            if identifier.isdigit():
                c.execute('UPDATE faqs SET question=?,answer=? WHERE id=?',(question,answer,int(identifier)))
            else:
                c.execute('INSERT INTO faqs(question,answer,position) VALUES(?,?,(SELECT COALESCE(MAX(position),0)+1 FROM faqs))',(question,answer))
    return go_admin('ok')


@app.post('/admin/logo/{position}')
async def upload_official_logo(position: str, req: Request):
    if position not in ('izquierdo','derecho'):
        raise HTTPException(404, 'Posición inválida')
    if not authorized(req):
        raise HTTPException(403, 'Acceso no autorizado')
    token = req.headers.get('X-CSRF-Token', '')
    expected = req.session.get('csrf', '')
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(403, 'Token inválido')
    if req.headers.get('content-type', '').split(';')[0] not in ('image/jpeg', 'image/png', 'image/webp'):
        raise HTTPException(415, 'Sube un archivo PNG, JPG o WebP')
    payload = await req.body()
    if len(payload) > 5 * 1024 * 1024 or not payload:
        raise HTTPException(413, 'El archivo debe tener menos de 5 MB')
    try:
        with Image.open(io.BytesIO(payload)) as im:
            im.verify()
        with Image.open(io.BytesIO(payload)) as im:
            if im.width > 3500 or im.height > 3500 or im.width * im.height > 8_000_000:
                raise HTTPException(422, 'Dimensiones demasiado grandes')
            im = im.convert('RGBA')
            dest = ROOT / 'static' / f'logo-{position}.png'
            temp = ROOT / 'static' / f'.logo-{position}.tmp.png'
            im.save(temp, format='PNG', optimize=True)
            os.replace(temp, dest)
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, 'El archivo no es una imagen válida')
    return JSONResponse({'ok': True, 'logo': position})

# Recepción y bandeja privada de consultas.
from consultas import router as consultas_router
app.include_router(consultas_router)

# Actualización de noticias desde canales RSS oficiales de Gob.pe.
from recursos import router as recursos_router
app.include_router(recursos_router)

# Comunidad JCPS: seguidores anónimos, reacciones, novedades y eventos.
from social import router as social_router
app.include_router(social_router)
