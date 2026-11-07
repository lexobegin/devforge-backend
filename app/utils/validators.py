# app/utils/validators.py
"""
Validaciones UML 2.5+ reutilizables por servicios y routers — CICLO 2.

RECONVERTIDO del Ciclo 1 conservando los 5 validadores que LANZAN
`ValidationError` (de app.core.exceptions) cuando fallan y devuelven el
valor normalizado cuando pasan. Los routers y servicios del Ciclo 2 los
usan igual que en el Ciclo 1 (misma firma, mismos mensajes).

NUEVO en el Ciclo 2 (Tanda 18): el GATE FORMAL de generación (CU6/CU24).
En el Ciclo 1 el generador validaba poco y fallaba tarde; en el Ciclo 2
`validar_diagrama_para_generar()` RECORRE el diagrama completo, COLECTA
todos los ProblemaModelo (no corta en el primero) y el generador rechaza
la generación si hay al menos un ERROR:

- ProblemaModelo: hallazgo del modelo (severidad ERROR/ADVERTENCIA,
  código estable, mensaje en español y elemento involucrado).
- ERROR   → bloquea la generación (nombres inválidos/duplicados, relación
            que apunta a clases inexistentes, atributo sin nombre o sin
            tipo…). El llamante recibió un modelo que no se puede generar.
- ADVERTENCIA → NO bloquea (la clase no declaró PK y se sintetiza `id`,
            clase sin atributos, tipo no mapeable que degradará a
            Long/BIGINT…): el backend generado funciona igual.

Nota de import perezoso: `validar_diagrama_para_generar` necesita
MappingEngine/TIPO_MAP de app.code_generator.mapping_engine, pero NO los
importa arriba: el `app/code_generator/__init__.py` importa
generator_service, que importa este módulo — un import de nivel superior
aquí rompería el ciclo de importación (code_generator →
generator_service → utils.validators → code_generator). Dentro de la
función ya no hay ciclo.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from app.core.exceptions import ValidationError


# ----------------------------------------------------------------------
# Patrones (mismos del Ciclo 1)
# ----------------------------------------------------------------------
# Identificador UML: letra inicial, luego letras/dígitos/guion_bajo.
_IDENTIFICADOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Multiplicidades típicas: 1, 0..1, *, 0..*, 1..*, n, 1..n, 2..5
_MULTIPLICIDADES_FIJAS = {"1", "0..1", "*", "0..*", "1..*", "n", "1..n"}
_MULTIPLICIDAD_RANGO_RE = re.compile(r"^\d+\.\.\d+$")

# Visibilidades UML
_VISIBILIDADES = {"+", "-", "#", "~"}

# Estereotipo: <<nombre>> (guardamos "nombre" sin los ángulos)
_ESTEREOTIPO_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\- ]{0,48}$")

# Tipos genéricos que mapping_engine degrada a String/VARCHAR(255)
_GENERICO_RE = re.compile(r"^(List|Set|Collection|Optional)<(.+)>$")


# ----------------------------------------------------------------------
# Validadores que LANZAN (misma firma y mensajes que el Ciclo 1)
# ----------------------------------------------------------------------
def validar_identificador_uml(nombre: str, *, campo: str = "nombre") -> str:
    """
    Valida que el nombre sea un identificador UML aceptable:
    empieza con letra, sigue con letras/dígitos/_, y no está vacío.
    Devuelve el nombre sin espacios extremos.
    """
    if not nombre or not nombre.strip():
        raise ValidationError(f"El {campo} no puede estar vacío")

    n = nombre.strip()
    if not _IDENTIFICADOR_RE.match(n):
        raise ValidationError(
            f"El {campo} '{nombre}' no es un identificador UML válido "
            "(debe empezar con letra y contener solo letras, dígitos y _)"
        )
    return n


def validar_multiplicidad(multiplicidad: Optional[str]) -> Optional[str]:
    """
    Valida multiplicidad UML. Acepta None (sin multiplicidad).
    Formatos aceptados: 1, 0..1, *, 0..*, 1..*, n, 1..n, 2..5, etc.
    """
    if multiplicidad is None:
        return None

    m = multiplicidad.strip()
    if m in _MULTIPLICIDADES_FIJAS:
        return m
    if _MULTIPLICIDAD_RANGO_RE.match(m):
        return m
    raise ValidationError(f"Multiplicidad inválida: '{multiplicidad}'")


def validar_visibilidad(visibilidad: str) -> str:
    """Valida visibilidad UML: +, -, #, ~."""
    if visibilidad not in _VISIBILIDADES:
        raise ValidationError(
            f"Visibilidad inválida: '{visibilidad}'. "
            "Use uno de: +, -, #, ~"
        )
    return visibilidad


def validar_estereotipo(estereotipo: Optional[str]) -> Optional[str]:
    """
    Valida estereotipo UML. Acepta None.
    Acepta tanto '<<entity>>' como 'entity' (devuelve 'entity').
    """
    if estereotipo is None or not estereotipo.strip():
        return None

    e = estereotipo.strip()
    # Quitar << >> si vienen incluidos
    if e.startswith("<<") and e.endswith(">>"):
        e = e[2:-2].strip()

    if not _ESTEREOTIPO_RE.match(e):
        raise ValidationError(
            f"Estereotipo inválido: '{estereotipo}'"
        )
    return e


def validar_tipo_dato(tipo: str) -> str:
    """
    Valida tipo de dato UML. Es flexible: acepta primitivos (String,
    Integer, Date, Boolean…), tipos genéricos (List<String>), o nombres
    de clases del propio diagrama.
    """
    if not tipo or not tipo.strip():
        raise ValidationError("El tipo de dato no puede estar vacío")
    t = tipo.strip()
    if len(t) > 50:
        raise ValidationError("El tipo de dato excede los 50 caracteres")
    # No hacer regex estricto aquí: permitimos "List<String>", etc.
    return t


# ----------------------------------------------------------------------
# GATE FORMAL (NUEVO Ciclo 2): ProblemaModelo + colector
# ----------------------------------------------------------------------
@dataclass
class ProblemaModelo:
    """Un hallazgo del gate formal de generación (CU6/CU24).

    severidad  → "ERROR" (bloquea) o "ADVERTENCIA" (no bloquea).
    codigo     → identificador estable del hallazgo (NOMBRE_CLASE_INVALIDO,
                 RELACION_ROTA, PK_SINTETICA…), útil para tests y para el
                 informe del trabajo.
    mensaje    → descripción en español, lista para mostrar al usuario.
    elemento   → ubicación legible ("Clase 'Paciente' › atributo 'ci'").
    """

    severidad: str
    codigo: str
    mensaje: str
    elemento: str = ""

    @property
    def es_error(self) -> bool:
        return self.severidad == "ERROR"

    def __str__(self) -> str:
        ubicacion = f" @ {self.elemento}" if self.elemento else ""
        return f"[{self.severidad}] ({self.codigo}) {self.mensaje}{ubicacion}"


def hay_errores(problemas: list[ProblemaModelo]) -> bool:
    """True si hay al menos un ProblemaModelo de severidad ERROR."""
    return any(p.es_error for p in problemas)


def formatear_problemas(problemas: list[ProblemaModelo]) -> str:
    """
    Reporte multi-línea para el mensaje de la excepción y para la
    bitácora: 'El modelo UML tiene N problema(s)...' + un ítem por línea.
    """
    if not problemas:
        return "El modelo UML no tiene problemas de generación"
    errores = sum(1 for p in problemas if p.es_error)
    advertencias = len(problemas) - errores
    lineas = [
        "El modelo UML tiene "
        f"{len(problemas)} problema(s) de generación "
        f"({errores} ERROR(es), {advertencias} advertencia(s)):"
    ]
    lineas.extend(f"- {p}" for p in problemas)
    return "\n".join(lineas)


def _sin_acentos(texto: str) -> str:
    """'Clínica' → 'Clinica' (mismo hallazgo T17: los identificadores
    Java/SQL generados van en ASCII puro)."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )


def validar_diagrama_para_generar(diagrama: Any) -> list[ProblemaModelo]:
    """
    GATE FORMAL de generación (CU6): recorre el diagrama COMPLETO y
    colecta TODOS los ProblemaModelo (no corta en el primero, para que
    el usuario corrija todo de una sola vez). El generador (CU6) rechaza
    si hay ERRORes; las ADVERTENCIA(s) solo se registran.

    Reglas (Ciclo 2):
    - Clase sin nombre o con nombre que no es identificador UML → ERROR.
    - Dos clases con el mismo nombre (casefold) → ERROR (el engine
      generaría dos entidades con el mismo nombre de tabla).
    - Dos clases que colisionan en PascalCase al quitar acentos
      ('Historia Clínica' vs 'HistoriaClinica') → ERROR: el engine
      generaría DOS entidades Java con el MISMO nombre de clase.
    - Clase sin atributos → ADVERTENCIA (se genera la entidad con la
      PK sintética, sin columnas de negocio).
    - Clase sin atributo 'id' → ADVERTENCIA (mapping_engine sintetiza
      `id BIGSERIAL PRIMARY KEY`).
    - Atributo sin nombre → ERROR; tipo vacío → ERROR; tipo que el
      engine no sabe mapear (no primitivo, no genérico List<...> y no
      clase del propio diagrama) → ADVERTENCIA (degradará a Long/BIGINT).
    - Relación que apunta a clases inexistentes (uuid roto, típico tras
      ediciones del lienzo) → ERROR.

    Dos PASADAS: la 0 registra TODOS los nombres e ids de clases (un
    atributo puede tipar con una clase declarada más adelante en el
    diagrama: 'med: Medicamento' no debe advertir aunque Medicamento
    esté después en la lista); la 1 colecta los hallazgos.
    """
    from app.code_generator.mapping_engine import MappingEngine  # perezoso

    problemas: list[ProblemaModelo] = []
    clases = list(getattr(diagrama, "clases", []) or [])

    # ---- PASADA 0: registrar nombres e ids de TODAS las clases ----
    ids_clases: set[str] = set()
    nombres_clase: set[str] = set()
    for clase in clases:
        ids_clases.add(getattr(clase, "id", ""))
        nombre = (getattr(clase, "nombre", "") or "").strip()
        if nombre:
            nombres_clase.add(nombre.casefold())

    # ---- PASADA 1: hallazgos por clase ----
    nombres_vistos: set[str] = set()          # casefold del nombre original
    pascal_vistos: dict[str, str] = {}        # PascalCase (sin acentos) → 1er nombre

    for clase in clases:
        nombre = (getattr(clase, "nombre", "") or "").strip()
        elemento = f"Clase '{nombre or '?'}'"

        if not nombre:
            problemas.append(
                ProblemaModelo(
                    "ERROR", "NOMBRE_CLASE_VACIO",
                    "Hay una clase sin nombre: no se puede generar "
                    "una entidad Java para ella",
                    elemento,
                )
            )
            continue

        if not _IDENTIFICADOR_RE.match(nombre):
            problemas.append(
                ProblemaModelo(
                    "ERROR", "NOMBRE_CLASE_INVALIDO",
                    f"El nombre '{nombre}' no es un identificador UML "
                    "válido (debe empezar con letra y contener solo "
                    "letras, dígitos y _)",
                    elemento,
                )
            )

        clave = nombre.casefold()
        if clave in nombres_vistos:
            problemas.append(
                ProblemaModelo(
                    "ERROR", "NOMBRE_CLASE_DUPLICADO",
                    f"Hay dos clases llamadas '{nombre}': el generador "
                    "no sabe a cuál corresponde cada atributo",
                    elemento,
                )
            )
        nombres_vistos.add(clave)

        pascal = MappingEngine._a_pascal_case(nombre)
        if pascal in pascal_vistos and pascal_vistos[pascal] != nombre:
            problemas.append(
                ProblemaModelo(
                    "ERROR", "NOMBRE_CLASE_COLISION",
                    f"'{nombre}' y '{pascal_vistos[pascal]}' generan la "
                    f"MISMA clase Java '{pascal}': renombra una de las dos",
                    elemento,
                )
            )
        else:
            pascal_vistos.setdefault(pascal, nombre)

        atributos = list(getattr(clase, "atributos", []) or [])
        if not atributos:
            problemas.append(
                ProblemaModelo(
                    "ADVERTENCIA", "CLASE_SIN_ATRIBUTOS",
                    f"La clase '{nombre}' no tiene atributos: la tabla "
                    "generada solo tendrá la clave primaria",
                    elemento,
                )
            )
        elif not any(
            (getattr(a, "nombre", "") or "").strip().lower() == "id"
            for a in atributos
        ):
            problemas.append(
                ProblemaModelo(
                    "ADVERTENCIA", "PK_SINTETICA",
                    f"La clase '{nombre}' no declara atributo 'id': se "
                    "sintetizará id BIGSERIAL PRIMARY KEY",
                    elemento,
                )
            )

        for atributo in atributos:
            nom_attr = (getattr(atributo, "nombre", "") or "").strip()
            tipo = (getattr(atributo, "tipo_dato", "") or "").strip()
            elem_attr = f"{elemento} › atributo '{nom_attr or '?'}'"

            if not nom_attr:
                problemas.append(
                    ProblemaModelo(
                        "ERROR", "ATRIBUTO_SIN_NOMBRE",
                        "Hay un atributo sin nombre: no se puede generar "
                        "una columna para él",
                        elem_attr,
                    )
                )
            if not tipo:
                problemas.append(
                    ProblemaModelo(
                        "ERROR", "TIPO_ATRIBUTO_VACIO",
                        f"El atributo '{nom_attr}' no tiene tipo de dato",
                        elem_attr,
                    )
                )
            elif not _tipo_mapeable(tipo, nombres_clase):
                problemas.append(
                    ProblemaModelo(
                        "ADVERTENCIA", "TIPO_NO_MAPEADO",
                        f"El tipo '{tipo}' del atributo '{nom_attr}' no es "
                        "un primitivo UML ni una clase del diagrama: se "
                        "degradará a Long/BIGINT",
                        elem_attr,
                    )
                )

    # ---- PASADA 2: relaciones rotas ----
    for relacion in list(getattr(diagrama, "relaciones", []) or []):
        origen = getattr(relacion, "id_clase_origen", "")
        destino = getattr(relacion, "id_clase_destino", "")
        if origen in ids_clases and destino in ids_clases:
            continue
        problemas.append(
            ProblemaModelo(
                "ERROR", "RELACION_ROTA",
                "Una relación apunta a clases que ya no existen en el "
                "diagrama (elimínala o revínculala en el lienzo)",
                f"Relación {getattr(relacion, 'tipo_relacion', '?')} "
                f"{origen or '?'} → {destino or '?'}",
            )
        )

    return problemas


def _tipo_mapeable(tipo: str, nombres_clase: set[str]) -> bool:
    """True si mapping_engine tiene un destino claro para el tipo:
    primitivo de TIPO_MAP (exacto o en minúsculas — el lienzo del Ciclo 2
    escribe 'float'/'bool'), genérico List<...>/Set<…>/…, o una clase del
    propio diagrama (que mapea como FK a Long/BIGINT a propósito)."""
    from app.code_generator.mapping_engine import (  # perezoso
        TIPO_MAP,
        TIPO_MAP_MINUSCULAS,
    )

    t = tipo.strip()
    if t in TIPO_MAP or t.lower() in TIPO_MAP_MINUSCULAS:
        return True
    if _GENERICO_RE.match(t):
        return True
    return t.casefold() in {n.casefold() for n in nombres_clase}