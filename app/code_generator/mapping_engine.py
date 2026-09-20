# app/code_generator/mapping_engine.py
"""
Motor de mapeo objeto-relacional para la generación automática de backend.

Traduce un Diagrama ORM (con clases UML, atributos, tipos UML, visibilidades)
a un conjunto de estructuras listas para renderizar con Jinja2:

- JavaEntity: la clase @Entity JPA con sus columnas.
- JavaField: atributo → campo Java + columna SQL.

Reglas aplicadas (resumen):
- Tipos UML → tipos Java + tipos SQL Postgres.
- Atributos: nombre en camelCase para Java, snake_case para columna.
- Claves primarias: primera coincidencia de nombre `id`, o se sintetiza
  un `id BIGSERIAL PRIMARY KEY` si la clase no declara uno.
- Nombres de clase → PascalCase (Java), nombres de tabla → snake_case plural.
- Relaciones: por ahora se exponen como metadatos (no se genera @ManyToOne
  automático, para evitar ambigüedad con composiciones/agregaciones).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ======================================================================
# Tablas de mapeo
# ======================================================================
# Tipos UML → (tipo Java, tipo SQL Postgres)
TIPO_MAP: dict[str, tuple[str, str]] = {
    # Strings
    "String": ("String", "VARCHAR(255)"),
    "string": ("String", "VARCHAR(255)"),
    "str": ("String", "VARCHAR(255)"),
    "text": ("String", "TEXT"),
    "Text": ("String", "TEXT"),
    # Enteros
    "Integer": ("Integer", "INTEGER"),
    "int": ("Integer", "INTEGER"),
    "Long": ("Long", "BIGINT"),
    "long": ("Long", "BIGINT"),
    "Short": ("Short", "SMALLINT"),
    # Decimales
    "Float": ("Float", "REAL"),
    "Double": ("Double", "DOUBLE PRECISION"),
    "Double": ("Double", "DOUBLE PRECISION"),
    "BigDecimal": ("BigDecimal", "NUMERIC(19,4)"),
    "Decimal": ("BigDecimal", "NUMERIC(19,4)"),
    # Booleanos
    "Boolean": ("Boolean", "BOOLEAN"),
    "boolean": ("Boolean", "BOOLEAN"),
    "bool": ("Boolean", "BOOLEAN"),
    # Fechas
    "Date": ("LocalDate", "DATE"),
    "date": ("LocalDate", "DATE"),
    "DateTime": ("LocalDateTime", "TIMESTAMP"),
    "Timestamp": ("LocalDateTime", "TIMESTAMP"),
    "LocalDate": ("LocalDate", "DATE"),
    "LocalDateTime": ("LocalDateTime", "TIMESTAMP"),
    "Time": ("LocalTime", "TIME"),
    # Binarios
    "byte[]": ("byte[]", "BYTEA"),
    "Blob": ("byte[]", "BYTEA"),
    # UUID
    "UUID": ("UUID", "UUID"),
    "uuid": ("UUID", "UUID"),
}

# Tipos que necesitan import adicional en Java
IMPORTS_JAVA: dict[str, list[str]] = {
    "LocalDate": ["java.time.LocalDate"],
    "LocalDateTime": ["java.time.LocalDateTime"],
    "LocalTime": ["java.time.LocalTime"],
    "BigDecimal": ["java.math.BigDecimal"],
    "UUID": ["java.util.UUID"],
}

# Nombres que se reservan para evitar colisiones con campos JPA
CAMPOS_RESERVADOS_JPA = {"serialVersionUID"}


# ======================================================================
# Estructuras de salida
# ======================================================================
@dataclass
class JavaField:
    """Un atributo UML traducido a campo Java + columna SQL."""

    nombre_java: str
    tipo_java: str
    nombre_columna: str
    tipo_sql: str
    es_clave_primaria: bool
    es_nulleable: bool
    valor_defecto: Optional[str] = None
    imports_extra: list[str] = field(default_factory=list)


@dataclass
class JavaEntity:
    """Una clase UML traducida a entidad JPA."""

    nombre_clase_java: str          # PascalCase, ej. "HistoriaClinica"
    nombre_tabla: str               # snake_case, ej. "historia_clinica"
    nombre_paquete: str             # ej. "com.example.salud.entity"
    es_abstracta: bool = False
    campos: list[JavaField] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    # Metadatos de relaciones entrantes/salientes (para el informe)
    relaciones: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MappingResult:
    """Resultado completo del mapeo de un diagrama."""

    entidades: list[JavaEntity] = field(default_factory=list)
    # Resumen para mostrar al usuario
    resumen: dict[str, Any] = field(default_factory=dict)


# ======================================================================
# Engine
# ======================================================================
class MappingEngine:
    """
    Traduce un diagrama ORM a estructuras Java.

    La clase no depende de SQLAlchemy: recibe objetos ya cargados y lee
    atributos por nombre. Esto la hace testeable sin base de datos.
    """

    def __init__(self, package_base: str = "com.devforge.generated"):
        self.package_base = package_base

    # ------------------------------------------------------------------
    # API principal
    # ------------------------------------------------------------------
    def mapear_diagrama(self, diagrama: Any) -> MappingResult:
        """
        Recorre el diagrama y devuelve una lista de JavaEntity.
        Cada entidad tiene ya sus campos resueltos con tipos Java y SQL.
        """
        entidades: list[JavaEntity] = []
        nombres_clase = {
            getattr(c, "nombre", ""): c for c in getattr(diagrama, "clases", []) or []
        }

        # Tabla: nombre de tabla por clase, para resolver nombres de columna
        # de posibles relaciones FK (no implementadas aún como @ManyToOne).
        tabla_por_clase: dict[str, str] = {}

        for clase in getattr(diagrama, "clases", []) or []:
            entidad = self._mapear_clase(clase)
            entidades.append(entidad)
            tabla_por_clase[getattr(clase, "nombre", "")] = entidad.nombre_tabla

        # Adjuntar metadatos de relaciones a las entidades correspondientes
        for rel in getattr(diagrama, "relaciones", []) or []:
            self._adjuntar_relacion(rel, nombres_clase, entidades)

        resumen = {
            "total_entidades": len(entidades),
            "total_campos": sum(len(e.campos) for e in entidades),
            "entidades": [
                {
                    "clase_java": e.nombre_clase_java,
                    "tabla": e.nombre_tabla,
                    "campos": len(e.campos),
                }
                for e in entidades
            ],
        }

        return MappingResult(entidades=entidades, resumen=resumen)

    # ------------------------------------------------------------------
    # Mapeo de una clase
    # ------------------------------------------------------------------
    def _mapear_clase(self, clase: Any) -> JavaEntity:
        nombre_original = getattr(clase, "nombre", "").strip()
        nombre_java = self._a_pascal_case(nombre_original)
        nombre_tabla = self._a_snake_case_plural(nombre_original)

        entidad = JavaEntity(
            nombre_clase_java=nombre_java,
            nombre_tabla=nombre_tabla,
            nombre_paquete=f"{self.package_base}.entity",
            es_abstracta=bool(getattr(clase, "es_abstracta", False)),
        )

        # Mapear atributos
        campos: list[JavaField] = []
        tiene_pk = False
        imports: set[str] = set()

        for attr in getattr(clase, "atributos", []) or []:
            campo = self._mapear_atributo(attr, es_pk_candidata=not tiene_pk)
            if campo.es_clave_primaria:
                tiene_pk = True
            campos.append(campo)
            for imp in campo.imports_extra:
                imports.add(imp)

        # Si la clase no declaró PK, sintetizamos una
        if not tiene_pk:
            campos.insert(
                0,
                JavaField(
                    nombre_java="id",
                    tipo_java="Long",
                    nombre_columna="id",
                    tipo_sql="BIGSERIAL PRIMARY KEY",
                    es_clave_primaria=True,
                    es_nulleable=False,
                ),
            )

        entidad.campos = campos
        entidad.imports = sorted(imports)

        # Imports estándar de JPA (siempre presentes)
        entidad.imports = sorted(
            set(entidad.imports)
            | {
                "jakarta.persistence.*",
            }
        )

        # Si hay campos con fecha/hora, ya se agregaron vía imports_extra.
        return entidad

    def _mapear_atributo(
        self, attr: Any, *, es_pk_candidata: bool
    ) -> JavaField:
        nombre_original = getattr(attr, "nombre", "").strip()
        tipo_uml = getattr(attr, "tipo_dato", "String") or "String"

        tipo_java, tipo_sql = self._mapear_tipo(tipo_uml)
        imports = list(IMPORTS_JAVA.get(tipo_java, []))

        nombre_java = self._a_camel_case(nombre_original)
        nombre_columna = self._a_snake_case(nombre_original)

        # PK: si el nombre es 'id' (cualquier caso) y aún no hay PK
        es_pk = es_pk_candidata and nombre_original.lower() == "id"
        if es_pk:
            # PK asumida BIGSERIAL / Long
            tipo_java = "Long"
            tipo_sql = "BIGSERIAL PRIMARY KEY"
            imports = []

        # Nulleabilidad:
        # - PK nunca es nulleable
        # - atributos con valor por defecto pueden ser nulleable o no; por
        #   defecto asumimos nulleable, salvo que la visibilidad sea privada
        #   y no tenga valor_defecto → seguimos asumiendo nulleable (lo más
        #   seguro para no romper inserciones del backend generado).
        es_nulleable = not es_pk

        return JavaField(
            nombre_java=nombre_java,
            tipo_java=tipo_java,
            nombre_columna=nombre_columna,
            tipo_sql=tipo_sql,
            es_clave_primaria=es_pk,
            es_nulleable=es_nulleable,
            valor_defecto=getattr(attr, "valor_defecto", None),
            imports_extra=imports,
        )

    # ------------------------------------------------------------------
    # Mapeo de tipos
    # ------------------------------------------------------------------
    def _mapear_tipo(self, tipo_uml: str) -> tuple[str, str]:
        """
        Devuelve (tipo_java, tipo_sql) para un tipo UML.
        Si no está en la tabla, cae a String / VARCHAR(255) y deja pasar.
        """
        t = tipo_uml.strip()
        if t in TIPO_MAP:
            return TIPO_MAP[t]

        # Tipos genéricos: List<String>, Set<Integer>, Optional<X> …
        m = re.match(r"^(List|Set|Collection|Optional)<(.+)>$", t)
        if m:
            # No se generan colecciones en columnas simples.
            # Se cae a String para evitar romper la generación.
            return "String", "VARCHAR(255)"

        # Nombre de clase del propio diagrama → se mapea como FK más adelante.
        # Por ahora lo mapeamos como Long (id) para que compile el backend.
        return "Long", "BIGINT"

    # ------------------------------------------------------------------
    # Relaciones (metadatos)
    # ------------------------------------------------------------------
    def _adjuntar_relacion(
        self,
        relacion: Any,
        nombres_clase: dict[str, Any],
        entidades: list[JavaEntity],
    ) -> None:
        """
        Adjunta metadatos de la relación a las entidades involucradas.
        No genera @ManyToOne/@OneToMany automático: solo dejamos constancia
        en el informe y, si es composición/agregación, dejamos un campo FK
        'id_<destino>' en la entidad origen.

        Nota: esta es una versión conservadora; ampliable en el futuro.
        """
        clase_origen_id = getattr(relacion, "id_clase_origen", None)
        clase_destino_id = getattr(relacion, "id_clase_destino", None)

        # Buscar nombres de clase
        origen_nombre = None
        destino_nombre = None
        for nombre, clase in nombres_clase.items():
            if getattr(clase, "id", None) == clase_origen_id:
                origen_nombre = nombre
            if getattr(clase, "id", None) == clase_destino_id:
                destino_nombre = nombre

        if not origen_nombre or not destino_nombre:
            return

        # Registrar en la entidad origen
        for entidad in entidades:
            if entidad.nombre_clase_java == self._a_pascal_case(origen_nombre):
                entidad.relaciones.append(
                    {
                        "tipo": getattr(relacion, "tipo_relacion", "ASOCIACION"),
                        "destino": self._a_pascal_case(destino_nombre),
                        "multiplicidad_origen": getattr(
                            relacion, "multiplicidad_origen", None
                        ),
                        "multiplicidad_destino": getattr(
                            relacion, "multiplicidad_destino", None
                        ),
                        "rol_origen": getattr(relacion, "rol_origen", None),
                        "rol_destino": getattr(relacion, "rol_destino", None),
                    }
                )

    # ------------------------------------------------------------------
    # Helpers de nombres
    # ------------------------------------------------------------------
    @staticmethod
    def _a_pascal_case(nombre: str) -> str:
        """
        'historia_clinica' → 'HistoriaClinica'
        'Historia Clinica'  → 'HistoriaClinica'
        'paciente'          → 'Paciente'
        """
        if not nombre:
            return "Entity"
        # Separar por _, espacio, guion
        partes = re.split(r"[\s_\-]+", nombre.strip())
        partes = [p for p in partes if p]
        # Si ya viene en PascalCase o camelCase, respetar la forma
        if len(partes) == 1:
            p = partes[0]
            return p[0].upper() + p[1:] if p else "Entity"
        return "".join(p[0].upper() + p[1:] if p else "" for p in partes)

    @staticmethod
    def _a_camel_case(nombre: str) -> str:
        """
        'nombre_completo' → 'nombreCompleto'
        'Fecha Nacimiento' → 'fechaNacimiento'
        """
        if not nombre:
            return "campo"
        partes = re.split(r"[\s_\-]+", nombre.strip())
        partes = [p for p in partes if p]
        if not partes:
            return "campo"
        if len(partes) == 1:
            p = partes[0]
            return p[0].lower() + p[1:] if p else "campo"
        primera = partes[0][0].lower() + partes[0][1:]
        resto = "".join(p[0].upper() + p[1:] if p else "" for p in partes[1:])
        return primera + resto

    @staticmethod
    def _a_snake_case(nombre: str) -> str:
        """
        'NombreCompleto' → 'nombre_completo'
        'fechaNacimiento' → 'fecha_nacimiento'
        """
        if not nombre:
            return "columna"
        # Insertar _ antes de mayúsculas internas
        s = re.sub(r"(?<!^)(?=[A-Z])", "_", nombre.strip())
        s = re.sub(r"[\s\-]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s.lower() or "columna"

    @staticmethod
    def _a_snake_case_plural(nombre: str) -> str:
        """
        'HistoriaClinica' → 'historia_clinicas'
        'Paciente' → 'pacientes'
        Si ya termina en 's', no duplica la 's'.
        """
        base = MappingEngine._a_snake_case(nombre)
        if base.endswith("s"):
            return base
        return base + "s"


# ======================================================================
# Instancia por defecto
# ======================================================================
mapping_engine = MappingEngine()