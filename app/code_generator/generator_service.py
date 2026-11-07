# app/code_generator/generator_service.py
"""
Servicio orquestador de la generación automática de backend Spring Boot
(módulo F, CU6) — CICLO 2.

RECONVERTIDO del Ciclo 1 (SQLAlchemy/AsyncSession) a Beanie/MongoDB con
los textos del Ciclo 1 como base. Se conserva el PIPELINE y el CONTRATO
DE PLANTILLAS (mismos contextos, mismos .jinja en templates/); lo que
cambia es la capa de datos y el control de calidad:

1. PERMISOS: diagrama existente + membresía del proyecto. En el Ciclo 1
   exigía EDITOR para crear el trabajo; en el Ciclo 2 se alinea con CU24
   (Tanda 17): generar NO muta el diagrama, así que basta LECTURA
   (criterio defensivo idéntico: ajeno → 404 genérico "Recurso no
   encontrado", inexistente → "Diagrama no encontrado").
2. GATE FORMAL (NUEVO Ciclo 2): validar_diagrama_para_generar()
   (app/utils/validators) recorre el diagrama y COLECTA ProblemaModelo.
   Si hay ERRORes se rechaza la generación con el informe completo
   ANTES de crear el trabajo (0 documentos huérfanos). En el Ciclo 1 no
   había gate: el pipeline fallaba a mitad con GenerationError (excepción
   que el Ciclo 2 ya no tiene; los fallos de modelado ahora son
   ValidationError del llamante y los de I/O relanzan la excepción
   original para que el router T19 la mapee a 500).
3. TRABAJO: TrabajoGeneracionCodigo (stack SPRING_BOOT_JPA_POSTGRES,
   default del modelo) con PENDIENTE → EN_PROCESO → EXITOSO/FALLIDO a
   través de TrabajoGeneracionRepository (marcar_* SIEMPRE re-leen el
   documento: hallazgo T12).
4. RESULTADO EMBEBIDO: en el Ciclo 1 se creaban filas en
   entidades_generadas y reglas_mapeo (bulk_create con flush para ids);
   en el Ciclo 2 ambas viven EMBEBIDAS en trabajo.entidades[] →
   reglas_mapeo[] (Tanda 4): una EntidadGenerada por clase UML, cada una
   con UNA ReglaMapeo por atributo real (la PK sintética no tiene
   atributo UML y no genera regla). El documento se guarda con
   update() ANTES de marcar_exitoso (que re-lee y devuelve el trabajo
   completo).
5. ARCHIVOS: cada generación escribe su propia subcarpeta de
   GENERATED_PROJECTS_DIR (fecha + id del diagrama: NUNCA sobrescribe —
   el Ciclo 1 hacía shutil.rmtree del destino) y el ZIP junto a ella;
   ruta_salida = nombre del ZIP (relativo).
6. BITÁCORA + NOTIFICACIÓN (igual que el Ciclo 1, con las firmas del
   Ciclo 2): AuditoriaService.log_generacion_completada/fallida y
   NotificacionService.crear_para_miembros_de_proyecto(tipo
   GENERACION_COMPLETA, excluyendo al que disparó). Ambos van en
   try/except: un fallo de bitácora NO tumba una generación exitosa.

Estructura del proyecto generado (igual que el Ciclo 1):
    backend/
      pom.xml
      src/main/java/<paquete>/BackendApplication.java
      src/main/java/<paquete>/entity/<Entidad>.java
      src/main/java/<paquete>/repository/<Entidad>Repository.java
      src/main/java/<paquete>/service/<Entidad>Service.java
      src/main/java/<paquete>/controller/<Entidad>Controller.java
      src/main/java/<paquete>/dto/<Entidad>DTO.java
      src/main/resources/application.properties
      postman/<artifact>.postman_collection.json
    README.md
"""

import logging
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from beanie import PydanticObjectId
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.code_generator.mapping_engine import MappingEngine, MappingResult
from app.code_generator.postman_export import generar_coleccion_postman
from app.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.diagrama import Diagrama
from app.models.generacion import (
    EntidadGenerada,
    ReglaMapeo,
    TrabajoGeneracionCodigo,
)
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.generacion_repository import TrabajoGeneracionRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.utils.validators import (
    formatear_problemas,
    hay_errores,
    validar_diagrama_para_generar,
)

logger = logging.getLogger("devforge.generator")

# Stack del backend (default del modelo; el schema Literal del Ciclo 1 ya
# lo trae — el router T19 solo valida la entrada del cliente).
STACK_BACKEND = "SPRING_BOOT_JPA_POSTGRES"

# Rutas de plantillas (mismas 8 .jinja del Ciclo 1: la VM del usuario las
# conserva intactas; aquí van equivalentes funcionales para el arnés).
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


# ======================================================================
# Sanitizadores de nombres (copia de los del generador de frontend T17)
# ======================================================================
# Copia LOCAL y justificada: el paquete code_generator no se acopla a
# app.services (importar generador_frontend_service desde aquí crearía un
# ciclo de imports: services/__init__ → generador_frontend →
# code_generator.__init__ → generator_service → services…). Mismos
# sanitizadores, mismo hallazgo T17 (salida ASCII pura).
def _sin_acentos(texto: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )


def _palabras(nombre: str) -> list[str]:
    return [
        p
        for p in re.split(r"[^0-9a-zA-Z]+", _sin_acentos(nombre))
        if p
    ]


def _a_recurso(nombre: str) -> str:
    """Nombre kebab-case para la carpeta/ZIP: 'Clínica V2' → 'clinica-v2'."""
    return "-".join(p.lower() for p in _palabras(nombre)) or "backend"


class GeneratorService:
    """
    CU6: diagrama UML → backend Spring Boot + JPA + PostgreSQL
    (SPRING_BOOT_JPA_POSTGRES), registrado como TrabajoGeneracionCodigo
    con el resultado EMBEBIDO (entidades + reglas de mapeo).
    """

    def __init__(
        self,
        *,
        package_base: Optional[str] = None,
        artifact: Optional[str] = None,
    ) -> None:
        # Repositorios SIN ESTADO: la conexión la lleva Beanie (el Ciclo 1
        # recibía AsyncSession y creaba 6 repositorios por sesión).
        self.trabajos = TrabajoGeneracionRepository()
        self.diagramas = DiagramaRepository()
        self.miembros = MiembroProyectoRepository()

        # Overrides del config (los pasa el router T19 desde
        # GenerarBackendRequest; por defecto manda el config).
        self.package_base = (
            package_base or settings.GENERATED_BACKEND_GROUP_ID
        ).strip()
        self.artifact = (
            artifact or settings.GENERATED_BACKEND_ARTIFACT_PREFIX
        ).strip()

        self.logger = logging.getLogger("devforge.generator")

        # Jinja2 (mismo entorno que el Ciclo 1: los .jinja del usuario
        # renderizan igual — autoescape solo para html/xml de la colección
        # de nombre, trim/lstrip para salidas limpias).
        self.jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml")),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    # ==================================================================
    # API pública
    # ==================================================================
    async def generar_backend(
        self,
        id_usuario: PydanticObjectId,
        id_diagrama: PydanticObjectId,
        *,
        incluir_postman: bool = True,
        nombre_proyecto: Optional[str] = None,
    ) -> TrabajoGeneracionCodigo:
        """
        Ejecuta el pipeline completo: gate → mapeo → renderizado →
        escritura → ZIP → resultado embebido → EXITOSO. Devuelve el
        trabajo re-leído en estado EXITOSO (con entidades y reglas y la
        ruta relativa del ZIP).

        - Errores del llamante (inexistente, ajeno, sin clases, gate con
          ERRORes) se propagan ANTES de crear el trabajo: 0 documentos
          huérfanos.
        - Un fallo de renderizado/escritura marca el trabajo FALLIDO
          (finished_at, con bitácora GENERACION_FALLIDA) y RELANZA la
          excepción original (el router T19 la mapea a HTTP).
        """
        # 1. Lectura del lienzo + membresía (errores del llamante: fuera).
        diagrama = await self._diagrama_para_lectura(id_diagrama, id_usuario)

        # 2. Gate mínimo: sin clases no hay entidades que generar.
        if not diagrama.clases:
            raise ValidationError(
                "El diagrama no tiene clases: no hay entidades para "
                "generar el backend"
            )

        # 3. GATE FORMAL (Ciclo 2): colecta ProblemaModelo y rechaza con
        #    el informe completo si hay ERRORes (antes de crear trabajo).
        problemas = validar_diagrama_para_generar(diagrama)
        if hay_errores(problemas):
            raise ValidationError(formatear_problemas(problemas))
        if problemas:
            # Solo advertencias: se registran, la generación continúa.
            logger.warning(
                "Generación con advertencias de modelo: %s",
                formatear_problemas(problemas).replace("\n", " | "),
            )

        # 4. Mapeo UML → Java/SQL (puro y determinista: un fallo aquí es
        #    del modelo del llamante, también ANTES de crear el trabajo).
        engine = MappingEngine(package_base=self.package_base)
        mapeo = engine.mapear_diagrama(diagrama)
        if not mapeo.entidades:
            raise ValidationError(
                "No se pudo mapear ninguna entidad del diagrama"
            )

        # 5. Trabajo PENDIENTE → EN_PROCESO (helpers re-leen el documento).
        trabajo = await self.trabajos.create(
            TrabajoGeneracionCodigo(
                id_diagrama=diagrama.id,
                id_usuario=id_usuario,
                stack_destino=STACK_BACKEND,
            )
        )
        trabajo = await self.trabajos.marcar_en_proceso(trabajo.id)
        if trabajo is None:
            raise NotFoundError("Trabajo de generación no encontrado")

        try:
            # 6. Renderizado a memoria (sync y sin I/O: costura del arnés
            #    para probar la ruta FALLIDO).
            archivos = self._renderizar(
                diagrama=diagrama,
                mapeo=mapeo,
                trabajo_id=trabajo.id,
                incluir_postman=incluir_postman,
            )

            # 7. Escritura en carpeta ÚNICA + ZIP (nunca sobrescribe).
            carpeta = self._carpeta_destino(
                nombre_proyecto or diagrama.nombre, diagrama.id
            )
            self._escribir(carpeta, archivos)
            ruta_zip = self._empaquetar(carpeta)

            # 8. Resultado EMBEBIDO sobre el documento en mano y save() del
            #    padre (1 documento = 1 escritura coherente).
            trabajo.entidades = self._resultado_embebido(diagrama, mapeo)
            await self.trabajos.update(trabajo)

            # 9. EXITOSO con la ruta RELATIVA del ZIP (el helper re-lee:
            #    el documento devuelto trae las entidades ya guardadas).
            final = await self.trabajos.marcar_exitoso(
                trabajo.id, ruta_salida=ruta_zip.name
            )
            if final is None:
                raise NotFoundError("Trabajo de generación no encontrado")

            # 10. Bitácora + notificación (guardadas: no tumban el éxito).
            await self._log_generacion_exitosa(final, diagrama, id_usuario)
            await self._notificar_exito(final, diagrama, id_usuario)
            return final
        except Exception as exc:
            # Render/escritura falló: FALLIDO + bitácora del fallo y
            # RELANZA el motivo real (T19 lo mapea a HTTP).
            await self.trabajos.marcar_fallido(trabajo.id)
            await self._log_generacion_fallida(
                trabajo.id, diagrama, id_usuario, motivo=str(exc)
            )
            raise

    # ==================================================================
    # Descarga
    # ==================================================================
    async def obtener_ruta_zip(
        self,
        trabajo_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> Path:
        """
        Ruta absoluta del ZIP de un trabajo EXITOSO, lista para
        FileResponse (el router T19 la sirve). Mismas defensas de
        lectura que el resto del módulo: ajeno → 404 genérico.
        """
        trabajo = await self.trabajos.get_by_id(trabajo_id)
        if trabajo is None:
            raise NotFoundError("Trabajo de generación no encontrado")

        diagrama = await self.diagramas.get_by_id(trabajo.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")

        miembro = await self.miembros.get_by_proyecto_usuario(
            diagrama.id_proyecto, usuario_id
        )
        if miembro is None:
            # 404 genérico para no revelar proyectos ajenos.
            raise NotFoundError("Recurso no encontrado")

        if not trabajo.fue_exitoso or not trabajo.ruta_salida:
            raise ValidationError(
                f"El trabajo no está listo para descarga "
                f"(estado actual: {trabajo.estado})"
            )

        ruta = Path(settings.GENERATED_PROJECTS_DIR) / trabajo.ruta_salida
        if not ruta.is_file():
            raise NotFoundError("El archivo ZIP no está disponible")
        return ruta

    # ==================================================================
    # Renderizado (plantillas .jinja del Ciclo 1, mismos contextos)
    # ==================================================================
    def _renderizar(
        self,
        *,
        diagrama: Diagrama,
        mapeo: MappingResult,
        trabajo_id: PydanticObjectId,
        incluir_postman: bool = True,
    ) -> dict[str, str]:
        """
        Plantillas → {ruta relativa del proyecto: contenido}. Esqueleto
        una vez + un bloque de 5 archivos por entidad + colección Postman
        + README. Sync y sin I/O: el arnés puede interceptarlo para
        probar la ruta FALLIDO del trabajo (costura, igual que T17).
        """
        ctx_base = {
            "package_base": self.package_base,
            "artifact": self.artifact,
            "java_version": settings.GENERATED_BACKEND_JAVA_VERSION,
            "spring_boot_version": settings.GENERATED_BACKEND_SPRING_BOOT_VERSION,
            "postgres_version": settings.GENERATED_BACKEND_POSTGRES_VERSION,
            "diagrama_nombre": diagrama.nombre,
            "trabajo_id": str(trabajo_id),
        }

        # Ruta base del código Java dentro del proyecto generado.
        paquete = "/".join(self.package_base.split("."))
        java_base = f"backend/src/main/java/{paquete}"

        archivos: dict[str, str] = {}

        # pom.xml + application.properties + BackendApplication
        archivos["backend/pom.xml"] = self._render("pom.xml.jinja", ctx_base)
        archivos["backend/src/main/resources/application.properties"] = (
            self._render("application.properties.jinja", ctx_base)
        )
        archivos[f"{java_base}/BackendApplication.java"] = self._render(
            "main_application.java.jinja", ctx_base
        )

        # Por cada entidad: los 5 archivos del Ciclo 1.
        for entidad in mapeo.entidades:
            ctx = {**ctx_base, "entidad": entidad}
            nombre = entidad.nombre_clase_java
            archivos[f"{java_base}/entity/{nombre}.java"] = self._render(
                "entity.java.jinja", ctx
            )
            archivos[f"{java_base}/repository/{nombre}Repository.java"] = (
                self._render("repository.java.jinja", ctx)
            )
            archivos[f"{java_base}/service/{nombre}Service.java"] = (
                self._render("service.java.jinja", ctx)
            )
            archivos[f"{java_base}/controller/{nombre}Controller.java"] = (
                self._render("controller.java.jinja", ctx)
            )
            archivos[f"{java_base}/dto/{nombre}DTO.java"] = self._render(
                "dto.java.jinja", ctx
            )

        # Colección Postman (si el trabajo la pidió).
        if incluir_postman:
            coleccion = generar_coleccion_postman(
                mapeo=mapeo, nombre_proyecto=self.artifact
            )
            archivos[
                f"backend/postman/{self.artifact}.postman_collection.json"
            ] = coleccion

        # README con instrucciones rápidas (lo escribe el service, igual
        # que el Ciclo 1 con _escribir_readme).
        archivos["README.md"] = self._leeme(ctx_base, mapeo)
        return archivos

    def _render(self, nombre_plantilla: str, contexto: dict[str, Any]) -> str:
        """Renderiza UNA plantilla con errores explicativos (el Ciclo 1
        envolvía en GenerationError; el Ciclo 2 relanza RuntimeError con
        el motivo y el router T19 lo mapea a 500)."""
        try:
            plantilla = self.jinja.get_template(nombre_plantilla)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Plantilla no encontrada o inválida: '{nombre_plantilla}': {exc}"
            ) from exc
        try:
            return plantilla.render(**contexto)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Error renderizando '{nombre_plantilla}': {exc}"
            ) from exc

    def _leeme(self, ctx: dict[str, Any], mapeo: MappingResult) -> str:
        """README.md del proyecto generado (contenido del Ciclo 1)."""
        lineas = [
            f"# Backend generado por DevForge AI — trabajo #{ctx['trabajo_id']}",
            "",
            f"**Diagrama origen:** {ctx['diagrama_nombre']}",
            f"**Stack:** Java {ctx['java_version']} · Spring Boot {ctx['spring_boot_version']} · PostgreSQL {ctx['postgres_version']}",
            "",
            "## Entidades",
            "",
        ]
        for e in mapeo.entidades:
            lineas.append(f"- `{e.nombre_clase_java}` → tabla `{e.nombre_tabla}`")
        lineas += [
            "",
            "## Cómo ejecutarlo",
            "",
            "1. Crear una base de datos PostgreSQL.",
            "2. Ajustar `backend/src/main/resources/application.properties`.",
            "3. `mvn spring-boot:run` dentro de `backend/`.",
            "",
            "La colección Postman está en `backend/postman/` para probar la API.",
        ]
        return "\n".join(lineas)

    # ==================================================================
    # Escritura y empaquetado (carpeta ÚNICA: nunca sobrescribe)
    # ==================================================================
    def _carpeta_destino(
        self, nombre_proyecto: str, id_diagrama: PydanticObjectId
    ) -> Path:
        """Subcarpeta ÚNICA por generación (fecha con MICROSEGUNDOS + id
        del diagrama: dos corridas del mismo diagrama nunca se pisan, ni
        siquiera en el mismo segundo — el Ciclo 1 reutilizaba
        generated_projects/{id}/ y hacía rmtree del destino)."""
        marca = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        carpeta = (
            Path(settings.GENERATED_PROJECTS_DIR)
            / f"backend_{_a_recurso(nombre_proyecto)}_{str(id_diagrama)[:8]}_{marca}"
        )
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta

    @staticmethod
    def _escribir(carpeta: Path, archivos: dict[str, str]) -> None:
        """Escribe cada archivo (creando las carpetas intermedias)."""
        for ruta_relativa, contenido in archivos.items():
            destino = carpeta / ruta_relativa
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")

    @staticmethod
    def _empaquetar(carpeta: Path) -> Path:
        """ZIP del proyecto (junto a la carpeta, mismo nombre). El ZIP
        contiene la carpeta raíz, lista para descomprimir y correr."""
        ruta_zip = carpeta.with_suffix(".zip")
        with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as paquete:
            for archivo in sorted(carpeta.rglob("*")):
                if archivo.is_file():
                    paquete.write(
                        archivo, archivo.relative_to(carpeta.parent)
                    )
        return ruta_zip

    # ==================================================================
    # Resultado EMBEBIDO (antes _persistir_mapeo con bulk_create)
    # ==================================================================
    def _resultado_embebido(
        self, diagrama: Diagrama, mapeo: MappingResult
    ) -> list[EntidadGenerada]:
        """
        Mapea por nombre cada JavaEntity con su ClaseUML y arma:
        EntidadGenerada(id_clase_uml=<uuid del embebido>,
                        nombre_clase_java, nombre_tabla,
                        reglas_mapeo=[ReglaMapeo(id_atributo_uml=<uuid>,
                                                 columna, tipo_sql,
                                                 pk, nulleable)]).

        - La PK SINTÉTICA (clase sin atributo 'id') no tiene atributo UML:
          no genera ReglaMapeo (igual que el Ciclo 1 con sus campos
          sintéticos).
        - En el Ciclo 1 esto hacía bulk_create + flush para obtener los ids
          de las 3 tablas; en el Ciclo 2 todo viaja embebido en el trabajo
          y se persiste con UN save() del padre.
        """
        engine = MappingEngine()  # solo para los helpers de nombres

        entidades_java = {e.nombre_clase_java: e for e in mapeo.entidades}
        resultado: list[EntidadGenerada] = []

        for clase in diagrama.clases:
            entidad_java = entidades_java.get(
                engine._a_pascal_case(clase.nombre)
            )
            if entidad_java is None:
                continue

            # Índice de atributos UML por nombre camelCase (igual que el
            # Ciclo 1) para vincular cada campo Java con su uuid origen.
            atributos_por_java = {
                engine._a_camel_case(atributo.nombre): atributo
                for atributo in clase.atributos
            }

            reglas: list[ReglaMapeo] = []
            for campo in entidad_java.campos:
                atributo = atributos_por_java.get(campo.nombre_java)
                if atributo is None:
                    # Campo sintético (la PK generada) → sin atributo UML.
                    continue
                reglas.append(
                    ReglaMapeo(
                        id_atributo_uml=atributo.id,
                        nombre_columna=campo.nombre_columna,
                        tipo_sql=campo.tipo_sql,
                        es_clave_primaria=campo.es_clave_primaria,
                        es_nulleable=campo.es_nulleable,
                    )
                )

            resultado.append(
                EntidadGenerada(
                    id_clase_uml=clase.id,
                    nombre_clase_java=entidad_java.nombre_clase_java,
                    nombre_tabla=entidad_java.nombre_tabla,
                    reglas_mapeo=reglas,
                )
            )
        return resultado

    # ==================================================================
    # Bitácora / notificaciones (mismas llamadas que el Ciclo 1)
    # ==================================================================
    async def _log_generacion_exitosa(
        self,
        trabajo: TrabajoGeneracionCodigo,
        diagrama: Diagrama,
        usuario_id: PydanticObjectId,
    ) -> None:
        """Bitácora del éxito. En el Ciclo 1 recibía el db y hacía
        commit; en el Ciclo 2 el repositorio de Beanie persiste por
        operación y basta llamar al service (los fallos NO tumban la
        generación exitosa, igual que el Ciclo 1)."""
        try:
            from app.services.auditoria_service import AuditoriaService

            await AuditoriaService().log_generacion_completada(
                trabajo.id, diagrama.id, usuario_id
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("No se pudo registrar en bitácora: %s", exc)

    async def _log_generacion_fallida(
        self,
        trabajo_id: PydanticObjectId,
        diagrama: Diagrama,
        usuario_id: PydanticObjectId,
        *,
        motivo: str = "",
    ) -> None:
        try:
            from app.services.auditoria_service import AuditoriaService

            await AuditoriaService().log_generacion_fallida(
                trabajo_id, diagrama.id, usuario_id, motivo=motivo
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "No se pudo registrar el fallo en bitácora: %s", exc
            )

    async def _notificar_exito(
        self,
        trabajo: TrabajoGeneracionCodigo,
        diagrama: Diagrama,
        usuario_id: PydanticObjectId,
    ) -> None:
        """Notifica GENERACION_COMPLETA a los miembros del proyecto
        (excluyendo al que disparó). En el Ciclo 1 id_referencia era INT;
        en el Ciclo 2 es str (uuid del trabajo)."""
        try:
            from app.services.notificacion_service import NotificacionService

            await NotificacionService().crear_para_miembros_de_proyecto(
                diagrama.id_proyecto,
                tipo="GENERACION_COMPLETA",
                mensaje=(
                    f"Backend generado listo para el diagrama "
                    f"'{diagrama.nombre}' (#{trabajo.id})"
                ),
                id_referencia=str(trabajo.id),
                excluir_usuario_id=usuario_id,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("No se pudo notificar la generación: %s", exc)

    # ==================================================================
    # Permisos (mismo criterio defensivo del módulo C y de la T17)
    # ==================================================================
    async def _diagrama_para_lectura(
        self,
        id_diagrama: PydanticObjectId,
        id_usuario: PydanticObjectId,
    ) -> Diagrama:
        """Diagrama existente + membresía de lectura. Ajeno → 404
        genérico (no se revela existencia); inexistente → mensaje
        explícito. (Ciclo 1: exigía EDITOR para crear el trabajo; Ciclo 2:
        generar no muta el lienzo, basta LECTURA — misma decisión
        documentada de la Tanda 17 para CU24.)"""
        diagrama = await self.diagramas.get_by_id(id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")

        miembro = await self.miembros.get_by_proyecto_usuario(
            diagrama.id_proyecto, id_usuario
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        return diagrama