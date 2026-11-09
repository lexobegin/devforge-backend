# app/api/v1/admin_router.py
"""
Endpoints de ADMINISTRACIÓN de archivos del servidor (Tanda B24) —
punto 5 del reporte de pruebas del 2026-11-07.

- GET    /api/v1/admin/archivos            → listar (skip/limit/tipo)
- GET    /api/v1/admin/archivos/descargar  → descargar uno (FileResponse)
- DELETE /api/v1/admin/archivos            → eliminar uno (204)

Los tres exigen rol global ADMIN (require_admin).

¿Qué administra?
- exports/            → XMI/XML del intercambio con EA (intercambio_service).
- generated_projects/ → ZIPs + carpetas de los proyectos generados
                        (Spring Boot y React, CU23/CU24).
- uploads/            → imágenes subidas para IA de visión (hoy el
                        reconocimiento es en memoria; si el módulo pasa a
                        persistirlas, quedan administradas desde ya).

Reglas de seguridad (misma disciplina que intercambio_router.descargar_
exportado y generacion_router):
- `tipo` mapea a UNA raíz fija de settings; `ruta` es relativa y se
  resuelve con Path.resolve() + is_relative_to(raiz) → un `../` o ruta
  absoluta sale en 400, nunca se sale de la raíz.
- DELETE: si se borra un ZIP de `generated_projects/` TAMBIÉN se borra su
  carpeta hermana extraída (mismo stem) — es la unidad que produce el
  generador (`carpeta.with_suffix(".zip")`); así el espacio se libera
  entero y no quedan carpetas huérfanas.
- DELETE sobre directorio → 400 (solo archivos; el ZIP+carpeta se cubren
  con la regla anterior).

TODOS los handler son sincrónicos salvo el DELETE del ZIP+carpeta
(shutil.rmtree en hilo de worker — endpoint async con llamada directa:
rmtree de carpetas de proyectos generados es rápido y acotado).
"""

import logging
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from app.config import settings
from app.core.dependencies import require_admin
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.usuario import Usuario
from app.schemas.admin_schema import (
    ArchivoAdminResponse,
    ListadoArchivosAdminResponse,
    TipoArchivoAdmin,
    TIPOS_VALIDOS,
)

router = APIRouter()
logger = logging.getLogger("devforge.admin")

# Límite duro de entradas por listado: el directorio puede crecer mucho
# y el panel ADMIN pagina; leer 10k entradas de una vez no sirve a nadie.
MAX_LISTADO = 500


# ======================================================================
# Helpers de rutas (defensa anti path-traversal)
# ======================================================================
def _raices() -> dict[str, Path]:
    """Raíces administrables resueltas a absoluto, según settings."""
    return {
        "exports": Path(settings.EXPORT_DIR).resolve(),
        "generados": Path(settings.GENERATED_PROJECTS_DIR).resolve(),
        "uploads": Path(settings.UPLOAD_DIR).resolve(),
    }


def _resolver_en_raiz(tipo: str, ruta: str) -> Path:
    """
    Resuelve (tipo, ruta) a un archivo REAL dentro de su raíz.
    Cualquier intento de escape (`..`, rutas absolutas, symlinks fuera)
    termina en 400; lo inexistente en 404. Devuelve la ruta absoluta.
    """
    if tipo not in TIPOS_VALIDOS:
        raise BadRequestError(
            f"tipo inválido: {tipo!r}. Use: {', '.join(TIPOS_VALIDOS)}"
        )
    if not ruta or ruta.strip() in ("", ".", "/"):
        raise BadRequestError("Debe indicar la ruta del archivo")

    raiz = _raices()[tipo]
    # Path base + relativa: un ruta absoluta del cliente se ignora como
    # tal (Pathjoin con absoluto descarta la base) y resolve() normaliza.
    candidata = (raiz / ruta).resolve()
    try:
        candidata.relative_to(raiz)
    except ValueError:
        # Path absoluto del cliente o ../: mismo mensaje, sin detalles.
        raise BadRequestError("Ruta inválida")

    if not candidata.is_file():
        raise NotFoundError("Archivo no encontrado")
    return candidata


def _a_response(ruta_abs: Path, tipo: str, raiz: Path) -> ArchivoAdminResponse:
    stat = ruta_abs.stat()
    return ArchivoAdminResponse(
        nombre=ruta_abs.name,
        tipo=tipo,  # type: ignore[arg-type]
        ruta=ruta_abs.relative_to(raiz).as_posix(),
        tamano_bytes=stat.st_size,
        modificado_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )


# ======================================================================
# GET /archivos — listar
# ======================================================================
@router.get(
    "/archivos",
    response_model=ListadoArchivosAdminResponse,
    summary="Listar archivos del servidor (solo ADMIN) — Tanda B24",
    description=(
        "Lista los artefactos en disco: exports (XMI del intercambio), "
        "generados (ZIPs y carpetas de proyectos generados) y uploads. "
        "Sin `tipo` lista las tres raíces. Ordenado por fecha de "
        "modificación descendente (lo más nuevo primero)."
    ),
)
async def listar_archivos(
    tipo: Optional[str] = Query(None, description="exports | generados | uploads"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=MAX_LISTADO),
    _admin: Usuario = Depends(require_admin),
) -> ListadoArchivosAdminResponse:
    tipos: tuple[str, ...]
    if tipo is None:
        tipos = TIPOS_VALIDOS
    else:
        if tipo not in TIPOS_VALIDOS:
            raise BadRequestError(
                f"tipo inválido: {tipo!r}. Use: {', '.join(TIPOS_VALIDOS)}"
            )
        tipos = (tipo,)

    raices = _raices()
    archivos: list[ArchivoAdminResponse] = []

    for t in tipos:
        raiz = raices[t]
        if not raiz.is_dir():
            continue  # carpeta aún sin crear (p. ej. uploads): vacía
        for ruta_abs in raiz.rglob("*"):
            if not ruta_abs.is_file():
                continue
            archivos.append(_a_response(ruta_abs, t, raiz))
            if len(archivos) >= MAX_LISTADO * 4:
                # Cinta de seguridad: raíces gigantes no tiran el server.
                break

    archivos.sort(key=lambda a: a.modificado_at, reverse=True)
    total = len(archivos)
    pagina = archivos[skip : skip + limit]
    return ListadoArchivosAdminResponse(
        items=pagina, total=total, skip=skip, limit=limit
    )


# ======================================================================
# GET /archivos/descargar — descargar uno
# ======================================================================
@router.get(
    "/archivos/descargar",
    summary="Descargar un archivo administrado (solo ADMIN) — Tanda B24",
    description=(
        "Devuelve el contenido por `tipo` + `ruta` (la misma ruta que "
        "emite el listado). FileResponse fija Content-Disposition con el "
        "nombre real (expuesto al JS por CORS desde la Tanda B22)."
    ),
    response_class=FileResponse,
)
async def descargar_archivo(
    tipo: str = Query(..., description="exports | generados | uploads"),
    ruta: str = Query(..., description="Ruta relativa a la raíz del tipo"),
    _admin: Usuario = Depends(require_admin),
) -> FileResponse:
    ruta_abs = _resolver_en_raiz(tipo, ruta)
    media_type = (
        mimetypes.guess_type(ruta_abs.name)[0] or "application/octet-stream"
    )
    return FileResponse(
        path=ruta_abs,
        filename=ruta_abs.name,
        media_type=media_type,
    )


# ======================================================================
# DELETE /archivos — eliminar uno
# ======================================================================
@router.delete(
    "/archivos",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un archivo administrado (solo ADMIN) — Tanda B24",
    description=(
        "Borra el archivo indicado. En `generados`, si se borra un ZIP "
        "también se borra su carpeta hermana extraída (mismo stem): es la "
        "unidad que produce el generador y así no quedan huérfanos. "
        "Operación IRREVERSIBLE."
    ),
)
async def eliminar_archivo(
    tipo: str = Query(..., description="exports | generados | uploads"),
    ruta: str = Query(..., description="Ruta relativa a la raíz del tipo"),
    _admin: Usuario = Depends(require_admin),
) -> None:
    ruta_abs = _resolver_en_raiz(tipo, ruta)
    ruta_abs.unlink()

    extra = ""
    if tipo == "generados" and ruta_abs.suffix.lower() == ".zip":
        carpeta = ruta_abs.with_suffix("")
        if carpeta.is_dir():
            shutil.rmtree(carpeta)
            extra = f" (+ carpeta {carpeta.name}/)"

    logger.info(
        "ADMIN borró archivo: tipo=%s ruta=%s%s",
        tipo,
        ruta,
        extra,
    )
