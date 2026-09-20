# gunicorn.conf.py
"""
Configuración de Gunicorn para DevForge AI (producción).

Ejecuta la app FastAPI usando UvicornWorker (ASGI).
Comando típico:
    gunicorn app.main:app -c gunicorn.conf.py
"""

import multiprocessing
import os

# ----------------------------------------------------------------------
# Binding
# ----------------------------------------------------------------------
# Nginx hace reverse-proxy hacia esta dirección local.
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")

# ----------------------------------------------------------------------
# Workers
# ----------------------------------------------------------------------
# Regla habitual para apps ASGI: (2 * núcleos) + 1
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"

# ----------------------------------------------------------------------
# Timeouts
# ----------------------------------------------------------------------
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))
graceful_timeout = 30
keepalive = 5

# ----------------------------------------------------------------------
# Reciclado de workers (evita fugas de memoria en procesos largos)
# ----------------------------------------------------------------------
max_requests = 1000
max_requests_jitter = 100

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")   # "-" = stdout
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")     # "-" = stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# ----------------------------------------------------------------------
# Proceso
# ----------------------------------------------------------------------
proc_name = "devforge-ai-backend"
pidfile = os.getenv("GUNICORN_PIDFILE", "/tmp/devforge-gunicorn.pid")
daemon = False           # systemd se encarga del daemonizado
preload_app = True       # carga la app antes de forkear (ahorra memoria)