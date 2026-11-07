# app/services/generador_frontend_service.py
"""
Lógica del GENERADOR DE FRONTEND REACT (módulo F, CU24) — CICLO 2.

ARCHIVO NUEVO del Ciclo 2: en el Ciclo 1 el módulo F generaba SOLO el
backend (Spring Boot + JPA + PostgreSQL). En el Ciclo 2 el mismo módulo
se extiende al FRONTEND: a partir del lienzo EMBEBIDO del Diagrama produce
un proyecto React + Vite + TypeScript con un CRUD por cada clase UML
(tipos TS + cliente API + listado + formulario), usando las plantillas
Jinja2 de app/code_generator/templates_react/.

Flujo de `generar_frontend()`:
1. PERMISOS (solo lectura del lienzo): diagrama existente + membresía del
   proyecto (mismo criterio defensivo del gestor: ajeno → 404 genérico).
   Generar NO muta el diagrama: exige LECTURA, no EDITOR (los productos
   son el trabajo del propio usuario y los archivos del servidor).
2. GATE del modelo: sin clases no hay CRUD ("El diagrama no tiene
   clases…"). El informe FORMAL de validación (ProblemaModelo) llega con
   la Tanda 18 junto a utils/validators; aquí el gate es el mínimo que
   evita generar un proyecto vacío.
3. TRABAJO: crea TrabajoGeneracionCodigo (stack_destino="REACT_TS_VITE")
   y lo marca EN_PROCESO con los helpers del repositorio (started_at).
4. RENDERIZADO: Jinja2 sobre templates_react — esqueleto una vez
   (package.json, vite.config.ts, index.html, main.tsx, App.tsx, cliente
   API, README) y CRUD por cada clase (tipos, api, lista, formulario).
5. ESCRITURA: cada generación crea su propia subcarpeta de
   settings.GENERATED_PROJECTS_DIR (NUNCA sobrescribe: fecha + id del
   diagrama en el nombre) y el ZIP junto a ella.
6. RESULTADO: trabajo.entidades con UNA EntidadGenerada por clase y
   marcar_exitoso(ruta_salida=<zip>.name). Cualquier error de
   renderizado/escritura marca FALLIDO (finished_at) y RELANZA la
   excepción — los routers (T19) la mapean a HTTP.

Re-utilización documentada de EntidadGenerada (modelo del Ciclo 1):
- id_clase_uml       → uuid del ClaseUML embebido (igual que el backend).
- nombre_clase_java  → nombre de la ENTIDAD React en PascalCase (es el
  nombre del componente/tipo TS; el campo se reinterpreta, no se creó una
  columna nueva para no romper el documento cerrado en la Tanda 3).
- nombre_tabla       → nombre snake del recurso REST/archivos.
- reglas_mapeo       → [] en el frontend: el mapeo UML → TypeScript es
  determinista (str→string, int/float→number, bool→boolean, resto→string)
  y vive en el código generado; el mapeo UML → SQL del backend es cosa de
  mapping_engine (Tanda 18).

Ciclo fetch → modificar → save (hallazgo T12): el trabajo se manipula con
los helpers del repositorio (marcar_*), que SIEMPRE re-leen el documento
antes de guardar; las entidades se asignan sobre el documento re-leído y
se persisten ANTES de marcar_exitoso (que vuelve a re-leer: el documento
devuelto ya trae las entidades).
"""

import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.code_generator.templates_react import (
    PLANTILLAS_ENTIDAD,
    PLANTILLAS_PROYECTO,
    entorno_jinja,
)
from app.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.diagrama import ClaseUML, Diagrama
from app.models.generacion import EntidadGenerada, TrabajoGeneracionCodigo
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.generacion_repository import TrabajoGeneracionRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository

# Stack del frontend (texto libre en el modelo; el schema Literal se
# amplía en el router de la Tanda 19).
STACK_FRONTEND = "REACT_TS_VITE"

# Ruta destino (relativa al proyecto generado) por plantilla: esqueleto.
_RUTAS_PROYECTO = {
    "package.json.j2": "package.json",
    "vite.config.ts.j2": "vite.config.ts",
    "index.html.j2": "index.html",
    "src_main.tsx.j2": "src/main.tsx",
    "src_App.tsx.j2": "src/App.tsx",
    "src_api_client.ts.j2": "src/api/client.ts",
    "README.md.j2": "README.md",
}

# Mapeo determinista UML → TypeScript (clave en minúsculas y sin espacios).
_MAPA_TIPOS_TS = {
    "str": "string",
    "string": "string",
    "text": "string",
    "int": "number",
    "integer": "number",
    "float": "number",
    "double": "number",
    "decimal": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "date": "string",
    "datetime": "string",
    "time": "string",
}


# ======================================================================
# Sanitizadores de nombres (UML → TypeScript/npm/archivos)
# ======================================================================
def _sin_acentos(texto: str) -> str:
    """'Clínica' → 'Clinica' (NFD separa el acento y se descarta).
    Los identificadores, paquetes npm y nombres de archivo generados
    quedan ASCII puros aunque el nombre UML lleve tildes/ñ."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )


def _palabras(nombre: str) -> list[str]:
    """'Historia Clinica-2024' → ['Historia', 'Clinica', '2024'] (sin
    acentos: los productos de código van en ASCII)."""
    return [
        p
        for p in re.split(r"[^0-9a-zA-Z]+", _sin_acentos(nombre))
        if p
    ]


def _a_pascal(nombre: str) -> str:
    """Nombre de entidad/componente React: 'historia clinica' →
    'HistoriaClinica'."""
    return "".join(p[0].upper() + p[1:] for p in _palabras(nombre)) or "Entidad"


def _a_snake(nombre: str) -> str:
    """Nombre de recurso en archivos/campos: 'HistoriaClinica' →
    'historia_clinica'."""
    return "_".join(p.lower() for p in _palabras(nombre)) or "entidad"


def _a_recurso(nombre: str) -> str:
    """Nombre kebab-case para rutas REST y archivos: 'HistoriaClinica' →
    'historia-clinica'."""
    return "-".join(p.lower() for p in _palabras(nombre)) or "entidad"


def _nombre_js(nombre: str) -> str:
    """Identificador TypeScript válido para un atributo UML."""
    identificador = re.sub(r"[^0-9a-zA-Z_]", "_", nombre or "").strip("_")
    if not identificador:
        identificador = "campo"
    if identificador[0].isdigit():
        identificador = f"_{identificador}"
    return identificador


def _tipo_ts(tipo_dato: str) -> str:
    """UML → TypeScript (los desconocidos degradan a 'string')."""
    clave = (tipo_dato or "").strip().lower()
    return _MAPA_TIPOS_TS.get(clave, "string")


def _tipo_input(tipo_dato: str) -> str:
    """UML → type del <input> del formulario generado."""
    clave = (tipo_dato or "").strip().lower()
    if clave in {"int", "integer", "float", "double", "decimal", "number"}:
        return "number"
    if clave in {"bool", "boolean"}:
        return "checkbox"
    if clave in {"date"}:
        return "date"
    return "text"


# ======================================================================
# GeneradorFrontendService
# ======================================================================
class GeneradorFrontendService:
    """
    CU24: diagrama UML → proyecto React CRUD (REACT_TS_VITE), registrado
    como TrabajoGeneracionCodigo con su resultado EMBEBIDO.
    """

    def __init__(self) -> None:
        # Repositorios SIN ESTADO: la conexión la lleva Beanie. Sin
        # costuras: el E2E usa mongomock + GENERATED_PROJECTS_DIR temporal.
        self.trabajos = TrabajoGeneracionRepository()
        self.diagramas = DiagramaRepository()
        self.miembros = MiembroProyectoRepository()

    # ==================================================================
    # GENERACIÓN (CU24)
    # ==================================================================
    async def generar_frontend(
        self,
        id_usuario: PydanticObjectId,
        id_diagrama: PydanticObjectId,
        *,
        nombre_proyecto: Optional[str] = None,
    ) -> TrabajoGeneracionCodigo:
        """
        Genera el proyecto React CRUD del diagrama y lo registra como
        TrabajoGeneracionCodigo (stack REACT_TS_VITE). Devuelve el trabajo
        re-leído en estado EXITOSO (con entidades y ruta_salida del ZIP).
        Errores del llamante (inexistente/ajeno/sin clases) se propagan
        ANTES de crear el trabajo; un fallo de renderizado/escritura marca
        el trabajo FALLIDO y relanza la excepción original.
        """
        # 1. Lectura del lienzo + membresía (errores del llamante: fuera).
        diagrama = await self._diagrama_para_lectura(id_diagrama, id_usuario)
        if not diagrama.clases:
            raise ValidationError(
                "El diagrama no tiene clases: no hay entidades para "
                "generar el frontend"
            )

        # 2. Trabajo PENDIENTE → EN_PROCESO (helpers re-leen el documento).
        trabajo = await self.trabajos.create(
            TrabajoGeneracionCodigo(
                id_diagrama=diagrama.id,
                id_usuario=id_usuario,
                stack_destino=STACK_FRONTEND,
            )
        )
        trabajo = await self.trabajos.marcar_en_proceso(trabajo.id)
        if trabajo is None:
            raise NotFoundError("Trabajo de generación no encontrado")

        try:
            # 3. Contexto de plantillas + renderizado a memoria.
            nombre_app = (nombre_proyecto or diagrama.nombre or "").strip()
            entidades_ctx = [
                self._contexto_de_clase(clase) for clase in diagrama.clases
            ]
            archivos = self._renderizar(
                self._contexto_de_proyecto(nombre_app, entidades_ctx),
                entidades_ctx,
            )

            # 4. Escritura en su propia carpeta + ZIP (nunca sobrescribe).
            carpeta = self._carpeta_destino(nombre_app, diagrama.id)
            self._escribir(carpeta, archivos)
            ruta_zip = self._empaquetar(carpeta)

            # 5. Resultado EMBEBIDO: una EntidadGenerada por clase UML.
            trabajo.entidades = [
                EntidadGenerada(
                    id_clase_uml=clase.id,
                    nombre_clase_java=_a_pascal(clase.nombre),
                    nombre_tabla=_a_snake(clase.nombre),
                )
                for clase in diagrama.clases
            ]
            await self.trabajos.update(trabajo)

            # 6. EXITOSO con la ruta RELATIVA del ZIP (el helper re-lee:
            #    el documento devuelto trae las entidades ya guardadas).
            final = await self.trabajos.marcar_exitoso(
                trabajo.id, ruta_salida=ruta_zip.name
            )
            if final is None:
                raise NotFoundError("Trabajo de generación no encontrado")
            return final
        except Exception:
            # Render/escritura falló: auditoría FALLIDO y relanza (T19
            # mapea a HTTP). El llamante NO pierde el motivo real.
            await self.trabajos.marcar_fallido(trabajo.id)
            raise

    # ==================================================================
    # LECTURAS
    # ==================================================================
    async def listar_trabajos_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[TrabajoGeneracionCodigo]:
        """Trabajos de generación (backend y frontend) de un diagrama, el
        más nuevo primero (membresía de lectura del proyecto)."""
        await self._diagrama_para_lectura(diagrama_id, usuario_id)
        return await self.trabajos.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )

    async def obtener_trabajo(
        self,
        trabajo_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> TrabajoGeneracionCodigo:
        """Un trabajo con su resultado EMBEBIDO (entidades + reglas). En
        el Ciclo 2 todo va embebido: 1 lectura (antes 3 tablas con joins).
        Membresía de lectura del proyecto del diagrama del trabajo."""
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
        return trabajo

    # ==================================================================
    # CONTEXTOS DE PLANTILLAS (UML → diccionarios para Jinja2)
    # ==================================================================
    def _contexto_de_proyecto(
        self, nombre_app: str, entidades: list[dict]
    ) -> dict:
        """Contexto de las plantillas de esqueleto (una vez por generación)."""
        return {
            "nombre_app": nombre_app or "DevForge Frontend",
            "nombre_paquete": f"frontend-{_a_recurso(nombre_app)}",
            "fecha_generacion": datetime.now(timezone.utc)
            .date()
            .isoformat(),
            "api_base_url": settings.BACKEND_PUBLIC_URL.rstrip("/"),
            "total_entidades": len(entidades),
            "entidades": entidades,
        }

    @staticmethod
    def _contexto_de_clase(clase: ClaseUML) -> dict:
        """ClaseUML → contexto de las plantillas de entidad (CRUD)."""
        return {
            "nombre": _a_pascal(clase.nombre),
            "recurso": _a_recurso(clase.nombre),
            "tabla": _a_snake(clase.nombre),
            "es_abstracta": clase.es_abstracta,
            "atributos": [
                {
                    "nombre_original": atributo.nombre,
                    "nombre_js": _nombre_js(atributo.nombre),
                    "tipo_original": atributo.tipo_dato,
                    "tipo_ts": _tipo_ts(atributo.tipo_dato),
                    "tipo_input": _tipo_input(atributo.tipo_dato),
                    "visibilidad": atributo.visibilidad,
                    "valor_defecto": atributo.valor_defecto,
                    "es_estatico": atributo.es_estatico,
                }
                for atributo in clase.atributos
            ],
            "operaciones": [
                {
                    "nombre": operacion.nombre,
                    "tipo_retorno": _tipo_ts(operacion.tipo_retorno),
                }
                for operacion in clase.operaciones
            ],
        }

    # ==================================================================
    # RENDERIZADO Y ESCRITURA
    # ==================================================================
    def _renderizar(
        self,
        contexto: dict,
        entidades: list[dict],
    ) -> dict[str, str]:
        """
        Plantillas → {ruta relativa del proyecto: contenido}. Esqueleto
        una vez + CRUD por entidad. Sync y sin I/O: el arnés puede
        interceptarlo para probar la ruta FALLIDO del trabajo.
        """
        entorno = entorno_jinja()
        archivos: dict[str, str] = {}
        for plantilla in PLANTILLAS_PROYECTO:
            archivos[_RUTAS_PROYECTO[plantilla]] = (
                entorno.get_template(plantilla).render(**contexto)
            )
        for entidad in entidades:
            for plantilla in PLANTILLAS_ENTIDAD:
                destino = self._ruta_de_entidad(plantilla, entidad)
                archivos[destino] = entorno.get_template(plantilla).render(
                    ent=entidad
                )
        return archivos

    @staticmethod
    def _ruta_de_entidad(plantilla: str, entidad: dict) -> str:
        """Ruta destino de una plantilla de entidad (CRUD por clase)."""
        return {
            "src_tipos_entidad.ts.j2": (
                f"src/tipos/{entidad['recurso']}.ts"
            ),
            "src_api_entidad.ts.j2": f"src/api/{entidad['recurso']}.ts",
            "src_componentes_lista.tsx.j2": (
                f"src/components/{entidad['nombre']}Lista.tsx"
            ),
            "src_componentes_formulario.tsx.j2": (
                f"src/components/{entidad['nombre']}Formulario.tsx"
            ),
        }[plantilla]

    def _carpeta_destino(self, nombre_app: str, id_diagrama: PydanticObjectId) -> Path:
        """Subcarpeta ÚNICA por generación (fecha + id del diagrama:
        dos corridas del mismo diagrama nunca se pisan)."""
        marca = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        carpeta = (
            Path(settings.GENERATED_PROJECTS_DIR)
            / f"frontend_{_a_recurso(nombre_app)}_{str(id_diagrama)[:8]}_{marca}"
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
    # PERMISOS (mismo criterio defensivo del módulo C y del gestor)
    # ==================================================================
    async def _diagrama_para_lectura(
        self,
        id_diagrama: PydanticObjectId,
        id_usuario: PydanticObjectId,
    ) -> Diagrama:
        """Diagrama existente + membresía de lectura. Ajeno → 404
        genérico (no se revela existencia); inexistente → mensaje
        explícito."""
        diagrama = await self.diagramas.get_by_id(id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        miembro = await self.miembros.get_by_proyecto_usuario(
            diagrama.id_proyecto, id_usuario
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        return diagrama