# app/services/auditoria_service.py
"""
Lógica de negocio del módulo de Auditoría.

Cubre:
- Registrar eventos relevantes del sistema en `bitacora_sistema`
  (login, creación de proyecto, generación completada, etc.).
- Consultar la bitácora con filtros y paginación (CU3).
- Exportar la bitácora a Excel y PDF (streaming, sin persistir).

Regla clave: el registro es fire-and-forget desde los demás servicios.
`registrar()` acepta `commit=False` para incluirse en la transacción del
llamador, o `commit=True` para autopersistirse.
"""

from datetime import datetime
from io import BytesIO
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.auditoria import BitacoraSistema
from app.repositories.auditoria_repository import BitacoraRepository


class AuditoriaService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitacora = BitacoraRepository(db)

    # ==================================================================
    # REGISTRO
    # ==================================================================
    async def registrar(
        self,
        *,
        tipo_evento: str,
        descripcion: str,
        id_usuario: Optional[int] = None,
        entidad_afectada: Optional[str] = None,
        id_entidad_afectada: Optional[int] = None,
        commit: bool = False,
    ) -> BitacoraSistema:
        """
        Registra un evento en la bitácora.

        `commit=False` (por defecto) → el evento queda en la transacción
        abierta del llamador. Si el llamador hace commit, se persiste;
        si hace rollback, el evento se descarta.

        `commit=True` → el evento se persiste en su propia transacción,
        útil para eventos standalone (login, logout).
        """
        if not tipo_evento or not tipo_evento.strip():
            raise ValidationError("El tipo de evento es obligatorio")
        if not descripcion or not descripcion.strip():
            raise ValidationError("La descripción del evento es obligatoria")

        evento = BitacoraSistema(
            id_usuario=id_usuario,
            tipo_evento=tipo_evento.strip().upper(),
            descripcion=descripcion.strip()[:255],
            entidad_afectada=(
                entidad_afectada.strip().upper() if entidad_afectada else None
            ),
            id_entidad_afectada=id_entidad_afectada,
        )
        evento = await self.bitacora.create(evento)

        if commit:
            await self.db.commit()
            await self.db.refresh(evento)

        return evento

    # ------------------------------------------------------------------
    # Helpers semánticos (atajos para los servicios llamadores)
    # ------------------------------------------------------------------
    async def log_login(
        self, usuario_id: int, *, commit: bool = True
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="LOGIN",
            descripcion=f"El usuario #{usuario_id} inició sesión",
            id_usuario=usuario_id,
            entidad_afectada="USUARIO",
            id_entidad_afectada=usuario_id,
            commit=commit,
        )

    async def log_registro(
        self, usuario_id: int, *, commit: bool = True
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="USUARIO_REGISTRADO",
            descripcion=f"Se registró el usuario #{usuario_id}",
            id_usuario=usuario_id,
            entidad_afectada="USUARIO",
            id_entidad_afectada=usuario_id,
            commit=commit,
        )

    async def log_proyecto_creado(
        self, proyecto_id: int, usuario_id: int, nombre: str,
        *, commit: bool = False,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="PROYECTO_CREADO",
            descripcion=f"Proyecto '{nombre}' creado (#{proyecto_id})",
            id_usuario=usuario_id,
            entidad_afectada="PROYECTO",
            id_entidad_afectada=proyecto_id,
            commit=commit,
        )

    async def log_generacion_completada(
        self, trabajo_id: int, diagrama_id: int, usuario_id: int,
        *, commit: bool = False,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="GENERACION_COMPLETADA",
            descripcion=(
                f"Generación #{trabajo_id} completada para el "
                f"diagrama #{diagrama_id}"
            ),
            id_usuario=usuario_id,
            entidad_afectada="TRABAJO_GENERACION",
            id_entidad_afectada=trabajo_id,
            commit=commit,
        )

    async def log_generacion_fallida(
        self, trabajo_id: int, diagrama_id: int, usuario_id: int,
        motivo: str = "",
        *, commit: bool = False,
    ) -> BitacoraSistema:
        desc = f"Generación #{trabajo_id} falló para el diagrama #{diagrama_id}"
        if motivo:
            desc += f" — {motivo[:150]}"
        return await self.registrar(
            tipo_evento="GENERACION_FALLIDA",
            descripcion=desc,
            id_usuario=usuario_id,
            entidad_afectada="TRABAJO_GENERACION",
            id_entidad_afectada=trabajo_id,
            commit=commit,
        )

    async def log_exportacion(
        self, exportacion_id: int, diagrama_id: int, usuario_id: int,
        *, commit: bool = False,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="DIAGRAMA_EXPORTADO",
            descripcion=(
                f"Diagrama #{diagrama_id} exportado "
                f"(exportación #{exportacion_id})"
            ),
            id_usuario=usuario_id,
            entidad_afectada="DIAGRAMA",
            id_entidad_afectada=diagrama_id,
            commit=commit,
        )

    async def log_importacion(
        self, importacion_id: int, diagrama_id: int, usuario_id: int,
        *, commit: bool = False,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="DIAGRAMA_IMPORTADO",
            descripcion=(
                f"Diagrama #{diagrama_id} importado "
                f"(importación #{importacion_id})"
            ),
            id_usuario=usuario_id,
            entidad_afectada="DIAGRAMA",
            id_entidad_afectada=diagrama_id,
            commit=commit,
        )

    # ==================================================================
    # CONSULTA (CU3 — Bitácora del Sistema)
    # ==================================================================
    async def listar(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        id_usuario: Optional[int] = None,
        tipo_evento: Optional[str] = None,
        entidad_afectada: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> tuple[Sequence[BitacoraSistema], int]:
        """
        Devuelve (items, total) aplicando todos los filtros.
        El endpoint arma la respuesta paginada con esto.
        """
        if desde is not None and hasta is not None and desde > hasta:
            raise ValidationError("La fecha 'desde' no puede ser mayor que 'hasta'")

        items = await self.bitacora.list_paginado(
            skip=skip,
            limit=limit,
            id_usuario=id_usuario,
            tipo_evento=tipo_evento.upper() if tipo_evento else None,
            entidad_afectada=entidad_afectada.upper() if entidad_afectada else None,
            desde=desde,
            hasta=hasta,
        )
        total = await self.bitacora.count_con_filtros(
            id_usuario=id_usuario,
            tipo_evento=tipo_evento.upper() if tipo_evento else None,
            entidad_afectada=entidad_afectada.upper() if entidad_afectada else None,
            desde=desde,
            hasta=hasta,
        )
        return items, total

    async def listar_por_entidad(
        self, entidad_afectada: str, id_entidad_afectada: int
    ) -> Sequence[BitacoraSistema]:
        """Historial completo de eventos sobre un recurso concreto."""
        return await self.bitacora.list_by_entidad(
            entidad_afectada.upper(), id_entidad_afectada
        )

    async def listar_por_usuario(
        self,
        usuario_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[BitacoraSistema]:
        return await self.bitacora.list_by_usuario(
            usuario_id, skip=skip, limit=limit
        )

    # ==================================================================
    # EXPORTACIÓN (Excel y PDF)
    # ==================================================================
    async def exportar_excel(
        self,
        *,
        id_usuario: Optional[int] = None,
        tipo_evento: Optional[str] = None,
        entidad_afectada: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> bytes:
        """
        Genera un archivo .xlsx con la bitácora filtrada.
        Devuelve los bytes para streaming directo al cliente.
        """
        # Import local: openpyxl puede no estar instalado en desarrollo
        try:
            from openpyxl import Workbook
        except ImportError as exc:  # pragma: no cover
            raise ValidationError(
                "openpyxl no está instalado. Ejecute: pip install openpyxl"
            ) from exc

        items, _ = await self.listar(
            skip=0,
            limit=10_000,
            id_usuario=id_usuario,
            tipo_evento=tipo_evento,
            entidad_afectada=entidad_afectada,
            desde=desde,
            hasta=hasta,
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "Bitácora"

        # Cabeceras
        ws.append(
            [
                "ID",
                "Fecha",
                "Usuario",
                "Tipo de evento",
                "Descripción",
                "Entidad afectada",
                "ID entidad",
            ]
        )

        # Filas
        for e in items:
            ws.append(
                [
                    e.id,
                    e.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if e.created_at
                    else "",
                    e.id_usuario if e.id_usuario else "",
                    e.tipo_evento,
                    e.descripcion,
                    e.entidad_afectada or "",
                    e.id_entidad_afectada or "",
                ]
            )

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    async def exportar_pdf(
        self,
        *,
        id_usuario: Optional[int] = None,
        tipo_evento: Optional[str] = None,
        entidad_afectada: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> bytes:
        """
        Genera un PDF con la bitácora filtrada.
        Devuelve los bytes para streaming directo al cliente.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as exc:  # pragma: no cover
            raise ValidationError(
                "reportlab no está instalado. Ejecute: pip install reportlab"
            ) from exc

        items, total = await self.listar(
            skip=0,
            limit=10_000,
            id_usuario=id_usuario,
            tipo_evento=tipo_evento,
            entidad_afectada=entidad_afectada,
            desde=desde,
            hasta=hasta,
        )

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            title="Bitácora del Sistema — DevForge AI",
            author="DevForge AI",
        )
        styles = getSampleStyleSheet()
        story = []

        # Título
        story.append(Paragraph("<b>Bitácora del Sistema — DevForge AI</b>", styles["Title"]))
        story.append(
            Paragraph(
                f"Total de eventos: {total}  |  "
                f"Generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 12))

        # Tabla
        data = [["ID", "Fecha", "Usuario", "Tipo", "Descripción", "Entidad"]]
        for e in items:
            data.append(
                [
                    str(e.id),
                    e.created_at.strftime("%Y-%m-%d %H:%M")
                    if e.created_at
                    else "",
                    str(e.id_usuario) if e.id_usuario else "-",
                    e.tipo_evento,
                    (e.descripcion or "")[:80],
                    f"{e.entidad_afectada or '-'} #{e.id_entidad_afectada or ''}".strip(),
                ]
            )

        tabla = Table(data, repeatRows=1)
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ]
            )
        )
        story.append(tabla)
        doc.build(story)

        buffer.seek(0)
        return buffer.getvalue()