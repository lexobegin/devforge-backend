# app/services/auditoria_service.py
"""
Lógica de negocio del módulo de Auditoría.

Cubre:
- Registrar eventos relevantes del sistema en `bitacora_sistema`
  (login, creación de proyecto, generación completada, etc.).
- Consultar la bitácora con filtros y paginación (CU3).
- Exportar la bitácora a Excel y PDF (streaming, sin persistir).

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Servicio SIN ESTADO: sin AsyncSession. El registro es inmediato:
  `evento.insert()` persiste en el momento, así que el parámetro
  `commit` del Ciclo 1 DESAPARECE (no hay transacción que diferir; el
  registro ya no puede "irse con el rollback" del llamador).
- id_usuario → Optional[PydanticObjectId] (None = evento del sistema).
- id_entidad_afectada (BIGINT polimórfico) → Optional[str]: str(ObjectId)
  del Document o id uuid de un elemento embebido, según
  `entidad_afectada`. Los helpers semánticos reciben el ObjectId y lo
  guardan como str.
- El sello de tiempo del PDF usa datetime.now(timezone.utc) (aware), en
  lugar del utcnow() naive del Ciclo 1.
"""

from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.core.exceptions import ValidationError
from app.models.auditoria import BitacoraSistema
from app.repositories.auditoria_repository import BitacoraRepository


class AuditoriaService:
    """Bitácora general del sistema: registro fire-and-forget + consulta."""

    def __init__(self) -> None:
        self.bitacora = BitacoraRepository()

    # ==================================================================
    # REGISTRO
    # ==================================================================
    async def registrar(
        self,
        *,
        tipo_evento: str,
        descripcion: str,
        id_usuario: Optional[PydanticObjectId] = None,
        entidad_afectada: Optional[str] = None,
        id_entidad_afectada: Optional[str] = None,
    ) -> BitacoraSistema:
        """
        Registra un evento en la bitácora. En MongoDB el insert es
        inmediato: el evento ya queda persistido al salir de este método
        (el `commit` opcional del Ciclo 1 desaparece junto con las
        transacciones).
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
        # insert() persiste y asigna el ObjectId; sin commit/refresh
        evento = await self.bitacora.create(evento)

        return evento

    # ------------------------------------------------------------------
    # Helpers semánticos (atajos para los servicios llamadores)
    # ------------------------------------------------------------------
    async def log_login(
        self, usuario_id: PydanticObjectId
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="LOGIN",
            descripcion=f"El usuario #{usuario_id} inició sesión",
            id_usuario=usuario_id,
            entidad_afectada="USUARIO",
            id_entidad_afectada=str(usuario_id),
        )

    async def log_registro(
        self, usuario_id: PydanticObjectId
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="USUARIO_REGISTRADO",
            descripcion=f"Se registró el usuario #{usuario_id}",
            id_usuario=usuario_id,
            entidad_afectada="USUARIO",
            id_entidad_afectada=str(usuario_id),
        )

    async def log_proyecto_creado(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
        nombre: str,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="PROYECTO_CREADO",
            descripcion=f"Proyecto '{nombre}' creado (#{proyecto_id})",
            id_usuario=usuario_id,
            entidad_afectada="PROYECTO",
            id_entidad_afectada=str(proyecto_id),
        )

    async def log_generacion_completada(
        self,
        trabajo_id: PydanticObjectId,
        diagrama_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="GENERACION_COMPLETADA",
            descripcion=(
                f"Generación #{trabajo_id} completada para el "
                f"diagrama #{diagrama_id}"
            ),
            id_usuario=usuario_id,
            entidad_afectada="TRABAJO_GENERACION",
            id_entidad_afectada=str(trabajo_id),
        )

    async def log_generacion_fallida(
        self,
        trabajo_id: PydanticObjectId,
        diagrama_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
        motivo: str = "",
    ) -> BitacoraSistema:
        desc = f"Generación #{trabajo_id} falló para el diagrama #{diagrama_id}"
        if motivo:
            desc += f" — {motivo[:150]}"
        return await self.registrar(
            tipo_evento="GENERACION_FALLIDA",
            descripcion=desc,
            id_usuario=usuario_id,
            entidad_afectada="TRABAJO_GENERACION",
            id_entidad_afectada=str(trabajo_id),
        )

    async def log_exportacion(
        self,
        exportacion_id: PydanticObjectId,
        diagrama_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="DIAGRAMA_EXPORTADO",
            descripcion=(
                f"Diagrama #{diagrama_id} exportado "
                f"(exportación #{exportacion_id})"
            ),
            id_usuario=usuario_id,
            entidad_afectada="DIAGRAMA",
            id_entidad_afectada=str(diagrama_id),
        )

    async def log_importacion(
        self,
        importacion_id: PydanticObjectId,
        diagrama_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> BitacoraSistema:
        return await self.registrar(
            tipo_evento="DIAGRAMA_IMPORTADO",
            descripcion=(
                f"Diagrama #{diagrama_id} importado "
                f"(importación #{importacion_id})"
            ),
            id_usuario=usuario_id,
            entidad_afectada="DIAGRAMA",
            id_entidad_afectada=str(diagrama_id),
        )

    # ==================================================================
    # CONSULTA (CU3 — Bitácora del Sistema)
    # ==================================================================
    async def listar(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        id_usuario: Optional[PydanticObjectId] = None,
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
        self, entidad_afectada: str, id_entidad_afectada: str
    ) -> Sequence[BitacoraSistema]:
        """Historial completo de eventos sobre un recurso concreto."""
        return await self.bitacora.list_by_entidad(
            entidad_afectada.upper(), id_entidad_afectada
        )

    async def listar_por_usuario(
        self,
        usuario_id: PydanticObjectId,
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
        id_usuario: Optional[PydanticObjectId] = None,
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

        # Filas (los ObjectId se escriben como string hex)
        for e in items:
            ws.append(
                [
                    str(e.id),
                    e.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if e.created_at
                    else "",
                    str(e.id_usuario) if e.id_usuario else "",
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
        id_usuario: Optional[PydanticObjectId] = None,
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
                f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
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