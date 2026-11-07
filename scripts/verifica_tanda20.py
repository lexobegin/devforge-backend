# scripts/verifica_tanda20.py
"""
Arnés de verificación de la Tanda 20 (CIERRE DEL CICLO 2) de DevForge AI.

Cubre:
  A. Sintaxis: app/main.py, gunicorn.conf.py, scripts/verificar_ollama.py
     y sanidad del seed_mongo.js.
  B. main.py por fuente: los MISMOS 13 routers del Ciclo 1 (Tanda 19),
     SIN canal_router/asistente_router (borrador T2 superado), 14
     include_router (13 REST + agregador WS), prefijo /ia, lifespan
     init_db/close_db, register_exception_handlers, CORS, docs ocultas.
  C. Los 3 .env (.env.example, .env.produccion, .env) contra el
     Settings REAL de app/config.py: sin huérfanos, instanciables,
     sin variables del Ciclo 1 (POSTGRES_/DB_POOL_/AI_*), y casos
     específicos (JWT no vacío, CORS sin JSON, prod = production).
  D. IMPORT REAL de app.main con mongomock + FastAPI TestClient:
     lifespan (init_db), root/health, /docs + /openapi.json, mapa de
     rutas (13 prefijos REST + /ws/diagramas/{diagrama_id} como
     WebSocketRoute + sin /canal ni /asistente), manejadores de
     excepciones de dominio, y humo E2E registro→login→/auth/me→
     /proyectos. Más escenario de PRODUCCIÓN en subprocess
     (docs/redoc/openapi = None).
  E. nginx/devforgeai.conf y gunicorn.conf.py: binding y WS coherentes
     con el backend (puerto 8000, /ws/, client_max_body_size).
  F. requirements.txt / README.md / .gitignore del cierre.
  G. scripts/verificar_ollama.py contra un servidor Ollama FALSO
     (tags + embeddings + chat) → 6 OK / 0 FAIL; y caso de fallo.

Uso (desde la raíz del repo):
    python scripts/verifica_tanda20.py
"""

import ast
import json
import os
import py_compile
import re
import runpy
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.chdir(BASE)
sys.path.insert(0, str(BASE))

OK = 0
FAIL = 0


def check(nombre: str, cond, detalle: str = "") -> bool:
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {nombre}")
        return True
    FAIL += 1
    print(f"  [FAIL] {nombre}" + (f" — {detalle}" if detalle else ""))
    return False


def seccion(titulo: str) -> None:
    print(f"\n{'=' * 64}\n{titulo}\n{'=' * 64}")


# ======================================================================
# A. SINTAXIS
# ======================================================================
seccion("A. Sintaxis de los archivos del cierre")

for rel in ("app/main.py", "gunicorn.conf.py", "scripts/verificar_ollama.py"):
    try:
        py_compile.compile(str(BASE / rel), doraise=True)
        check(f"py_compile {rel}", True)
    except Exception as e:  # noqa: BLE001
        check(f"py_compile {rel}", False, str(e))

seed_path = BASE / "scripts" / "seed_mongo.js"
if seed_path.is_file():
    seed_txt = seed_path.read_text(encoding="utf-8")
    # Balance SOLO del código: las líneas de comentario // pueden llevar
    # numeración tipo "1)" que no cuenta (falso positivo del contador bruto).
    seed_codigo = "\n".join(
        ln for ln in seed_txt.splitlines() if not ln.lstrip().startswith("//")
    )
    check(
        "seed_mongo.js existe y balancea llaves/paréntesis (código)",
        seed_codigo.count("{") == seed_codigo.count("}")
        and seed_codigo.count("(") == seed_codigo.count(")"),
    )
    campos_seed = [
        "usuarios", "proyectos", "diagramas",
        "nombre_completo", "password_hash", "rol_en_proyecto",
        "id_propietario", "id_proyecto", "id_creador",
        "version_uml", "numero_version", "es_abstracta",
        "id_clase_origen", "id_clase_destino", "tipo_relacion",
        "multiplicidad_origen", "nombre_asociacion",
        "GENERALIZACION", "COMPOSICION", "AGREGACION", "DEPENDENCIA", "ASOCIACION",
        "interfaces", "atributos", "operaciones", "parametros",
    ]
    faltan = [c for c in campos_seed if c not in seed_txt]
    check("seed_mongo.js usa los campos EXACTOS de los modelos Beanie", not faltan, f"faltan: {faltan}")
    check(
        "seed_mongo.js avisa del dropDatabase (solo desarrollo)",
        "dropDatabase" in seed_txt and "devforge_prod_db" in seed_txt,
    )
    check(
        "seed_mongo.js usa hash bcrypt REAL (rondas 12) para devforge123",
        "$2b$12$" in seed_txt and "devforge123" in seed_txt,
    )
else:
    check("seed_mongo.js existe", False)

# ======================================================================
# B. MAIN.PY POR FUENTE
# ======================================================================
seccion("B. app/main.py — los 13 routers del Ciclo 1 + agregador WS")

main_txt = (BASE / "app" / "main.py").read_text(encoding="utf-8")

imports_router = set(
    re.findall(r"^\s{4}(\w+_router),\s*(?:#.*)?$", main_txt, re.M)
)
esperados = {
    "ai_vision_router", "auditoria_router", "auth_router", "colaboracion_router",
    "diagramas_router", "generacion_router", "ia_router", "intercambio_router",
    "notificaciones_router", "proyectos_router", "sincronizacion_router",
    "trazabilidad_router", "usuarios_router",
}
check("importa EXACTAMENTE los 13 routers de la Tanda 19", imports_router == esperados,
      f"extra={imports_router - esperados} faltan={esperados - imports_router}")

check(
    "SIN canal_router/asistente_router importados ni registrados (borrador T2 superado)",
    "canal_router.router" not in main_txt
    and "asistente_router.router" not in main_txt
    and not re.search(r"^\s+(canal_router|asistente_router),\s*$", main_txt, re.M),
)
check("14 include_router (13 REST + 1 agregador WS)", main_txt.count("app.include_router(") == 14,
      f"hay {main_txt.count('app.include_router(')}")
check("ia_router registrado bajo /ia", 'f"{settings.API_V1_PREFIX}/ia"' in main_txt)
check(
    "WebSocket = agregador del paquete app/websocket (Tanda 19b)",
    "from app.websocket import router as ws_router" in main_txt
    and "app.include_router(ws_router)" in main_txt,
)
check("register_exception_handlers(app) (core Tanda 19)", "register_exception_handlers(app)" in main_txt)
check("lifespan con init_db() y close_db()", "await init_db()" in main_txt and "await close_db()" in main_txt)
check("CORS desde Settings", "CORSMiddleware" in main_txt and "settings.CORS_ORIGINS" in main_txt)
check(
    "docs/redoc/openapi ocultos en producción",
    'docs_url="/docs" if not settings.IS_PRODUCTION else None' in main_txt
    and 'redoc_url="/redoc" if not settings.IS_PRODUCTION else None' in main_txt
    and 'openapi_url="/openapi.json" if not settings.IS_PRODUCTION else None' in main_txt,
)
check("root y health intactos", '@app.get("/", tags=["Root"])' in main_txt and '@app.get("/health"' in main_txt)

# ======================================================================
# C. LOS 3 .env CONTRA EL SETTINGS REAL
# ======================================================================
seccion("C. .env.example / .env.produccion / .env ↔ app/config.py")

sys.path.insert(0, str(BASE))
from app.config import Settings, settings  # noqa: E402

CAMPOS_SETTINGS = set(Settings.model_fields.keys())


def parse_env(ruta: Path):
    valores = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, _, v = linea.partition("=")
        valores[k.strip()] = v.split(" #", 1)[0].strip()
    return valores


envs = {
    ".env.example": parse_env(BASE / ".env.example"),
    ".env.produccion": parse_env(BASE / ".env.produccion"),
    ".env": parse_env(BASE / ".env"),
}

for nombre, valores in envs.items():
    check(f"{nombre}: existe y tiene variables", len(valores) >= 30, f"{len(valores)} vars")
    huerfanos = [k for k in valores if k not in CAMPOS_SETTINGS]
    check(f"{nombre}: 0 variables huérfanas (todas existen en Settings)", not huerfanos, str(huerfanos))
    try:
        Settings(**valores)
        check(f"{nombre}: Settings(**vars) instancia REAL (Literals/validadores/ints OK)", True)
    except Exception as e:  # noqa: BLE001
        check(f"{nombre}: Settings(**vars) instancia REAL", False, str(e)[:200])

CICLO1 = ["POSTGRES_HOST", "POSTGRES_DB", "DB_POOL_SIZE", "DATABASE_URL",
          "AI_PROVIDER", "AI_API_KEY", "AI_MODEL_TEXT", "AI_MODEL_VISION", "AI_TIMEOUT_SECONDS"]
for nombre, valores in envs.items():
    restos = [k for k in valores if k in CICLO1] + [
        k for k in valores if k.startswith(("POSTGRES_", "DB_POOL_", "AI_"))
    ]
    check(f"{nombre}: SIN variables del Ciclo 1", not restos, str(restos))

check(".env: JWT_SECRET_KEY NO vacío (un '=' vacío pisa el default con '')",
      bool(envs[".env"].get("JWT_SECRET_KEY")))
check(".env: CORS_ORIGINS separado por comas SIN corchetes/quotes (trampa del validador)",
      "[" not in envs[".env"].get("CORS_ORIGINS", "") and '"' not in envs[".env"].get("CORS_ORIGINS", ""))
check(".env: APP_VERSION=0.2.0", envs[".env"].get("APP_VERSION") == "0.2.0")
check(".env: bloque IA_* completo con Ollama",
      envs[".env"].get("IA_PROVIDER") == "ollama"
      and "OLLAMA_MODEL_TEXT" in envs[".env"] and "OLLAMA_MODEL_EMBEDDINGS" in envs[".env"])
check(".env: bloques VOZ_* y VISION_* presentes",
      "VOZ_MODELO_WHISPER" in envs[".env"] and "VISION_MAX_CLASES" in envs[".env"])

s_prod = Settings(**envs[".env.produccion"])
check(".env.produccion: IS_PRODUCTION real con APP_ENV=production", s_prod.IS_PRODUCTION is True)
check(".env.produccion: BD de producción separada (devforge_prod_db)",
      s_prod.MONGODB_DB == "devforge_prod_db")
check(".env.produccion: artefactos bajo /var/devforge/",
      str(s_prod.GENERATED_PROJECTS_DIR).startswith("/var/devforge/")
      and str(s_prod.EXPORT_DIR).startswith("/var/devforge/"))

paridad = set(envs[".env.example"]) ^ set(envs[".env.produccion"])
check(".env.example y .env.produccion: MISMA paridad de variables (48/48)", not paridad, str(paridad))

# ======================================================================
# D. IMPORT REAL DE APP.MAIN + E2E CON MONGOMOCK
# ======================================================================
seccion("D. Import real de app.main (mongomock) + mapa de rutas + humo E2E")

import mongomock_motor  # noqa: E402
import app.mongo as app_mongo  # noqa: E402

app_mongo.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

import app.main as app_main  # noqa: E402  (lifespan NO corre al importar)
from fastapi.testclient import TestClient  # noqa: E402
from starlette.routing import WebSocketRoute  # noqa: E402

app = app_main.app

with TestClient(app) as client:
    r = client.get("/")
    check("GET / → 200 con app/version/env", r.status_code == 200
          and r.json().get("app") == settings.APP_NAME and r.json().get("version") == "0.2.0")
    r = client.get("/health")
    check("GET /health → 200 {status: ok}", r.status_code == 200 and r.json().get("status") == "ok")
    r = client.get("/docs")
    check("GET /docs → 200 en desarrollo", r.status_code == 200)
    r = client.get("/openapi.json")
    check("GET /openapi.json → 200 y esquema construible",
          r.status_code == 200 and "/api/v1/auth/login" in r.json()["paths"])

    # --- Mapa de rutas ---
    rutas = {getattr(rt, "path", "") for rt in app.routes}
    prefijos = ["auth", "usuarios", "proyectos", "colaboracion", "diagramas",
                "trazabilidad", "intercambio", "generacion", "ia", "ai-vision",
                "sincronizacion", "notificaciones", "auditoria"]
    faltan = [p for p in prefijos if not any(x.startswith(f"/api/v1/{p}") for x in rutas)]
    check("13 prefijos REST presentes en la app real", not faltan, f"faltan: {faltan}")

    ws_routes = [rt for rt in app.routes if isinstance(rt, WebSocketRoute)]
    check("WebSocketRoute /ws/diagramas/{diagrama_id} registrada (agregador T19b)",
          any(rt.path == "/ws/diagramas/{diagrama_id}" for rt in ws_routes))
    check("SIN rutas /api/v1/canal ni /api/v1/asistente",
          not any("/canal" in x or "/asistente" in x for x in rutas))

    # --- Manejadores de excepciones (core Tanda 19: UN handler para la
    #     clase base DevForgeException + StarletteHTTPException + RequestValidationError;
    #     los códigos por subclase se resuelven dentro del handler) ---
    nombres_handlers = {getattr(k, "__name__", "") for k in app.exception_handlers}
    check("manejadores de excepciones: base DevForgeException + HTTP + validación",
          "DevForgeException" in nombres_handlers and len(app.exception_handlers) >= 3,
          f"hallados: {sorted(nombres_handlers)}")
    exc_txt = (BASE / "app" / "core" / "exceptions.py").read_text(encoding="utf-8")
    check("manejador de dominio distingue subclases (WWW-Authenticate en 401)",
          "isinstance(exc, UnauthorizedError)" in exc_txt)

    # --- Humo E2E: registro → login → me → proyectos ---
    r = client.post("/api/v1/auth/registro", json={
        "nombre_completo": "E2E Tanda 20", "email": "e2e-t20@devforge.ai",
        "password": "clave-e2e-123", "rol": "LIDER",
    })
    check("E2E POST /auth/registro → 201", r.status_code == 201, f"status={r.status_code} body={r.text[:150]}")

    r = client.post("/api/v1/auth/login", json={"email": "e2e-t20@devforge.ai", "password": "clave-e2e-123"})
    token = r.json().get("access_token") if r.status_code == 200 else None
    check("E2E POST /auth/login → 200 + access_token", bool(token), f"status={r.status_code} body={r.text[:150]}")

    if token:
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        check("E2E GET /auth/me con Bearer → 200 y email correcto",
              r.status_code == 200 and r.json().get("email") == "e2e-t20@devforge.ai")
        r = client.get("/api/v1/proyectos", headers={"Authorization": f"Bearer {token}"})
        check("E2E GET /proyectos con Bearer → 200 (lista vacía)", r.status_code == 200)
        r = client.get("/api/v1/proyectos")
        check("GET /proyectos SIN token → 401 (seguridad activa)", r.status_code == 401)
    else:
        check("E2E GET /auth/me (depende del login)", False, "sin token")

# --- Escenario de PRODUCCIÓN en subprocess (no toca BD: lifespan no corre) ---
PROD_SCRIPT = (
    "import app.main as m; a=m.app;"
    "assert a.docs_url is None and a.redoc_url is None and a.openapi_url is None, 'docs activas en prod';"
    "from app.config import settings; assert settings.IS_PRODUCTION, 'no es prod';"
    "print('PROD-OK')"
)
proc = subprocess.run(
    [sys.executable, "-c", PROD_SCRIPT],
    cwd=str(BASE), capture_output=True, text=True,
    env={**os.environ, "APP_ENV": "production", "JWT_SECRET_KEY": "prod-test-key-t20",
         "MONGODB_URI": "mongodb://127.0.0.1:27017", "PYTHONPATH": str(BASE)},
    timeout=120,
)
check("PRODUCCIÓN: import app.main con docs/redoc/openapi = None",
      proc.returncode == 0 and "PROD-OK" in proc.stdout, (proc.stderr or proc.stdout)[-300:])

# ======================================================================
# E. NGINX + GUNICORN
# ======================================================================
seccion("E. nginx/devforgeai.conf + gunicorn.conf.py")

nginx_txt = (BASE / "nginx" / "devforgeai.conf").read_text(encoding="utf-8")


def sin_comentar(txt: str, patron: str) -> bool:
    return any(re.search(patron, ln) for ln in txt.splitlines() if not ln.lstrip().startswith("#"))


check("nginx: proxy_pass al backend en 127.0.0.1:8000 (igual que PORT del .env.produccion)",
      sin_comentar(nginx_txt, r"proxy_pass\s+http://127\.0\.0\.1:8000;"))
check("nginx: location /ws/ con Upgrade (ruta real /ws/diagramas/{diagrama_id})",
      sin_comentar(nginx_txt, r"location\s+/ws/") and "proxy_set_header   Upgrade" in nginx_txt)
check("nginx: client_max_body_size 25M activo en el bloque :80",
      sin_comentar(nginx_txt, r"client_max_body_size\s+25M;"))
check("nginx: un solo server activo (:80) y el :443 solo como referencia",
      sin_comentar(nginx_txt, r"server\s*\{") and "# server {" in nginx_txt)
check("nginx: server_name = host del BACKEND_PUBLIC_URL de producción",
      sin_comentar(nginx_txt, r"server_name\s+api-devforgeai\.duckdns\.org;"))
check("nginx: cabeceras X-Forwarded-* (Host/Real-IP/For/Proto)", nginx_txt.count("X-Forwarded-Proto") >= 1)

gconf = runpy.run_path(str(BASE / "gunicorn.conf.py"))
check("gunicorn: bind default 127.0.0.1:8000 (coincide con nginx y PORT prod)",
      gconf["bind"] == "127.0.0.1:8000")
check("gunicorn: worker_class = uvicorn.workers.UvicornWorker",
      "UvicornWorker" in gconf["worker_class"])
check("gunicorn: preload_app=True es seguro (mongo.py no crea el cliente al importar)",
      gconf["preload_app"] is True and "se crea al importar" in (BASE / "app" / "mongo.py").read_text(encoding="utf-8"))

# ======================================================================
# F. REQUIREMENTS / README / .GITIGNORE
# ======================================================================
seccion("F. requirements.txt / README.md / .gitignore del cierre")

req_txt = (BASE / "requirements.txt").read_text(encoding="utf-8")
for linea in ("beanie==1.26.2", "motor==3.6.0", "dnspython==2.7.0", "faster-whisper==1.0.3",
              "lxml==5.3.0", "httpx==0.27.2", "python-multipart==0.0.12", "jinja2==3.1.4",
              "openpyxl==3.1.5", "reportlab==4.2.2", "uvicorn[standard]==0.31.0", "gunicorn==22.0.0"):
    check(f"requirements: {linea}", linea in req_txt)
deps_reales = {
    m.group(1).lower()
    for m in (re.match(r"^([A-Za-z0-9_.\[\]-]+)\s*==", ln) for ln in req_txt.splitlines())
    if m
}
prohibidos = [p for p in ("sqlalchemy", "alembic", "asyncpg", "psycopg2", "psycopg2-binary") if p in deps_reales]
check("requirements: SIN dependencias del Ciclo 1 (en líneas de paquete reales)", not prohibidos, str(prohibidos))

readme_txt = (BASE / "README.md").read_text(encoding="utf-8")
check("README: stack MongoDB + Beanie en la tabla", "| Base de datos | **MongoDB**" in readme_txt and "Beanie" in readme_txt)
check("README: comandos clave (uvicorn, gunicorn, seed, verificar_ollama)",
      "uvicorn app.main:app" in readme_txt and "gunicorn app.main:app -c gunicorn.conf.py" in readme_txt
      and "seed_mongo.js" in readme_txt and "verificar_ollama.py" in readme_txt)
check("README: estructura SIN database.py ni alembic/ activos en el árbol",
      "├── alembic/" not in readme_txt and "├── database.py" not in readme_txt
      and "alembic/` del Ciclo 1 **no existen más**" in readme_txt)
check("README: 13 routers y WS documentados", "13 routers REST" in readme_txt and "/ws/diagramas/{diagrama_id}" in readme_txt)
check("README: tests marcados como pendientes (decisión del equipo)", "pendiente" in readme_txt.lower())

gi_txt = (BASE / ".gitignore").read_text(encoding="utf-8")
check(".gitignore: ignora .env y suelta .env.example/.env.produccion",
      re.search(r"^\.env$", gi_txt, re.M) and re.search(r"^!\.env\.example$", gi_txt, re.M)
      and re.search(r"^!\.env\.produccion$", gi_txt, re.M))
check(".gitignore: generated_projects/uploads/exports ignorados",
      all(x in gi_txt for x in ("generated_projects/*", "uploads/*", "exports/*")))
check(".gitignore: SIN reglas activas de Alembic", not re.search(r"^alembic", gi_txt, re.M))
check(".gitattributes presente (LF normalization)",
      (BASE / ".gitattributes").is_file() and "text=auto" in (BASE / ".gitattributes").read_text(encoding="utf-8"))

# ======================================================================
# G. VERIFICAR_OLLAMA.PY CONTRA UN OLLAMA FALSO
# ======================================================================
seccion("G. scripts/verificar_ollama.py (E2E con servidor Ollama falso)")


class FakeOllamaHandler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/tags":
            self._json({"models": [
                {"name": "qwen2.5:7b:latest"},
                {"name": "llama3.2:3b"},
                {"name": "nomic-embed-text:latest"},
            ]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        if self.path == "/api/embeddings":
            self._json({"embedding": [0.01] * 8})
        elif self.path == "/api/chat":
            self._json({"message": {"role": "assistant", "content": "OK"}})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, *args):  # silencio
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
puerto = srv.server_address[1]

env_falso = BASE / ".env.fake-ollama-t20"
env_falso.write_text(
    "OLLAMA_BASE_URL=http://127.0.0.1:11434\n"
    "OLLAMA_MODEL_TEXT=qwen2.5:7b\n"
    "OLLAMA_MODEL_LIGERO=llama3.2:3b\n"
    "OLLAMA_MODEL_EMBEDDINGS=nomic-embed-text\n",
    encoding="utf-8",
)

proc = subprocess.run(
    [sys.executable, "scripts/verificar_ollama.py", "--base-url", f"http://127.0.0.1:{puerto}",
     "--env", ".env.fake-ollama-t20"],
    cwd=str(BASE), capture_output=True, text=True, timeout=120,
)
check("verificar_ollama: contra Ollama falso → 6 OK / 0 FAIL (tags+3 modelos+embeddings+chat)",
      proc.returncode == 0 and "6 OK / 0 FAIL" in proc.stdout,
      f"rc={proc.returncode}\n{proc.stdout[-400:]}{proc.stderr[-200:]}")

proc = subprocess.run(
    [sys.executable, "scripts/verificar_ollama.py", "--base-url", "http://127.0.0.1:1", "--sin-pruebas"],
    cwd=str(BASE), capture_output=True, text=True, timeout=120,
)
check("verificar_ollama: servidor caído → exit 1 con [FAIL] claro",
      proc.returncode == 1 and "[FAIL]" in proc.stdout and "ollama serve" in proc.stdout)

env_falso.unlink(missing_ok=True)
srv.shutdown()

# ======================================================================
# RESUMEN
# ======================================================================
print(f"\n{'=' * 64}")
print(f"RESULTADO TANDA 20: {OK} [OK] / {FAIL} FAIL")
print(f"{'=' * 64}")
sys.exit(1 if FAIL else 0)
