# app/ai_vision/uml_reconstructor.py
"""
Reconstrucción de un diagrama de clases UML a partir del resultado crudo
de la detección visual (`ResultadoReconocimiento`).

Tareas:
1. Parsear el texto OCR de cada caja en: nombre de clase + atributos +
   operaciones, según el formato típico de un diagrama UML:
       ┌───────────────────────┐
       │     NombreClase       │
       ├───────────────────────┤
       │ - atributo: Tipo      │
       │ + otroAtributo: Tipo  │
       ├───────────────────────┤
       │ + operacion(): Tipo   │
       └───────────────────────┘
2. Emparejar líneas detectadas con pares de cajas (relaciones).
3. Inferir tipo de relación según proximidad y heurísticas (por defecto
   ASOCIACION; si el texto lo indica, GENERALIZACION, etc.).
4. Producir un dict neutral compatible con el formato que consume el
   editor y el motor de generación.

El resultado es tolerante: si el OCR falla, la clase igual se crea con
el nombre genérico `ClaseN` y sin atributos.

CICLO 2: archivo conservado TAL CUAL del Ciclo 1 (Python puro, sin BD).
El dict que produce alimenta VisionReconocimientoResponse
.diagrama_restruido (mismo formato que DiagramaCompletoResponse: el
cliente inserta las clases por los endpoints CRUD del módulo C y
resuelve los nombres origen/destino a ids del lienzo).
"""

import logging
import re
from typing import Any, Optional

from app.ai_vision.sketch_recognition import (
    CajaDetectada,
    LineaDetectada,
    ResultadoReconocimiento,
    _caja_que_contiene,
)

logger = logging.getLogger("devforge.ai_vision")


# ======================================================================
# Regex y patrones
# ======================================================================
# Formato "nombre: Tipo"  → atributo
_ATRIBUTO_RE = re.compile(
    r"^([+\-#~]?)\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_\[\]<>, ]*)$"
)
# Formato "nombre(params): Tipo"  → operación
_OPERACION_RE = re.compile(
    r"^([+\-#~]?)\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?::\s*([A-Za-z_][A-Za-z0-9_\[\]<>, ]*))?$"
)
# Nombre de clase: empieza con mayúscula, solo letras/dígitos/_
_CLASE_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")

# Visibilidad por símbolo
_VIS_A_UML = {
    "+": "+",
    "-": "-",
    "#": "#",
    "~": "~",
    "": "-",     # sin símbolo → privado por defecto
}


# ======================================================================
# Reconstructor
# ======================================================================
class UMLReconstructor:
    """Convierte `ResultadoReconocimiento` en estructura de diagrama UML."""

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def reconstruir(
        self, deteccion: ResultadoReconocimiento
    ) -> dict[str, Any]:
        """
        Devuelve un dict con el mismo formato que `DiagramaCompletoResponse`:
        {
          "clases": [{nombre, es_abstracta, estereotipo, pos_x, pos_y,
                      atributos: [...], operaciones: [...]}],
          "relaciones": [{origen, destino, tipo, ...}],
          "advertencias": [...]
        }
        """
        advertencias = list(deteccion.advertencias)

        # 1) Parsear clases desde las cajas
        clases: list[dict[str, Any]] = []
        caja_a_nombre: dict[int, str] = {}

        for i, caja in enumerate(deteccion.cajas):
            clase = self._parsear_caja(caja, indice=i, advertencias=advertencias)
            clases.append(clase)
            caja_a_nombre[id(caja)] = clase["nombre"]

        # 2) Resolver relaciones desde las líneas
        relaciones = self._resolver_relaciones(
            deteccion.lineas, deteccion.cajas, caja_a_nombre, advertencias
        )

        return {
            "clases": clases,
            "relaciones": relaciones,
            "advertencias": advertencias,
        }

    # ------------------------------------------------------------------
    # Parseo de cajas → clases
    # ------------------------------------------------------------------
    def _parsear_caja(
        self,
        caja: CajaDetectada,
        *,
        indice: int,
        advertencias: list[str],
    ) -> dict[str, Any]:
        lineas = caja.lineas_texto or []

        nombre = "Clase" + str(indice + 1)
        atributos: list[dict[str, Any]] = []
        operaciones: list[dict[str, Any]] = []
        es_abstracta = False
        estereotipo: Optional[str] = None

        # El nombre es normalmente la primera línea con mayúscula inicial
        idx_nombre = self._detectar_indice_nombre(lineas)
        if idx_nombre is not None:
            nombre_bruto = lineas[idx_nombre].strip()
            nombre = self._limpiar_nombre_clase(nombre_bruto)
            # Estereotipo <<...>>
            m = re.search(r"<<\s*([^>]+)\s*>>", nombre_bruto)
            if m:
                estereotipo = m.group(1).strip()

            # Parsear el resto como miembros
            for ln in lineas[idx_nombre + 1 :]:
                ln = ln.strip()
                if not ln:
                    continue
                # Salta separadores (líneas de guiones o iguales)
                if re.fullmatch(r"[\-=_]{3,}", ln):
                    continue
                # Operación (contiene paréntesis)
                if "(" in ln and ")" in ln:
                    op = self._parsear_operacion(ln)
                    if op:
                        operaciones.append(op)
                        continue
                # Atributo (contiene ':')
                if ":" in ln:
                    attr = self._parsear_atributo(ln)
                    if attr:
                        atributos.append(attr)
                        continue
                # Línea suelta sin formato reconocible: se ignora
        else:
            advertencias.append(
                f"No se pudo identificar el nombre de la clase en la caja {indice + 1}"
            )

        # Nota: `es_abstracta` se infiere de la cursiva, que OCR no
        # transmite. Lo dejamos en False por defecto y lo detectamos
        # con una heurística simple: si el nombre está en minúsculas o
        # no respeta el patrón, se asume concreta igual.
        if nombre and not _CLASE_RE.match(nombre):
            # Reajustar a PascalCase
            nombre = self._a_pascal_case(nombre)

        return {
            "nombre": nombre,
            "es_abstracta": es_abstracta,
            "estereotipo": estereotipo,
            "pos_x": float(caja.box.x),
            "pos_y": float(caja.box.y),
            "atributos": atributos,
            "operaciones": operaciones,
        }

    # ------------------------------------------------------------------
    # Parseo de miembros
    # ------------------------------------------------------------------
    def _parsear_atributo(self, linea: str) -> Optional[dict[str, Any]]:
        m = _ATRIBUTO_RE.match(linea)
        if not m:
            # Intento más permisivo: "tipo nombre" sin dos puntos
            partes = linea.split()
            if len(partes) == 2:
                a, b = partes
                # Si el segundo empieza con mayúscula, asumimos "tipo nombre"
                if b and b[0].isupper():
                    return {
                        "nombre": self._to_camel(a),
                        "tipo_dato": self._normalizar_tipo(b),
                        "visibilidad": "-",
                        "es_estatico": False,
                        "valor_defecto": None,
                        "orden": 0,
                    }
            return None

        vis, nombre, tipo = m.group(1), m.group(2), m.group(3).strip()
        return {
            "nombre": self._to_camel(nombre),
            "tipo_dato": self._normalizar_tipo(tipo),
            "visibilidad": _VIS_A_UML.get(vis, "-"),
            "es_estatico": False,
            "valor_defecto": None,
            "orden": 0,
        }

    def _parsear_operacion(self, linea: str) -> Optional[dict[str, Any]]:
        m = _OPERACION_RE.match(linea)
        if not m:
            return None

        vis, nombre, params_str, retorno = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
        )

        parametros: list[dict[str, Any]] = []
        if params_str and params_str.strip():
            for p in params_str.split(","):
                p = p.strip()
                if not p:
                    continue
                if ":" in p:
                    pn, pt = p.split(":", 1)
                    parametros.append(
                        {
                            "nombre": self._to_camel(pn.strip()),
                            "tipo_dato": self._normalizar_tipo(pt.strip()),
                            "orden": len(parametros),
                        }
                    )
                else:
                    parametros.append(
                        {
                            "nombre": self._to_camel(p),
                            "tipo_dato": "String",
                            "orden": len(parametros),
                        }
                    )

        return {
            "nombre": self._to_camel(nombre),
            "tipo_retorno": self._normalizar_tipo(retorno or "void"),
            "visibilidad": _VIS_A_UML.get(vis, "+"),
            "es_estatico": False,
            "orden": 0,
            "parametros": parametros,
        }

    # ------------------------------------------------------------------
    # Resolución de relaciones
    # ------------------------------------------------------------------
    def _resolver_relaciones(
        self,
        lineas: list[LineaDetectada],
        cajas: list[CajaDetectada],
        caja_a_nombre: dict[int, str],
        advertencias: list[str],
    ) -> list[dict[str, Any]]:
        relaciones: list[dict[str, Any]] = []
        vistas: set[tuple[str, str]] = set()

        for linea in lineas:
            p1 = (linea.x1, linea.y1)
            p2 = (linea.x2, linea.y2)

            caja1 = _caja_que_contiene(p1, cajas) or _caja_mas_cercana(p1, cajas)
            caja2 = _caja_que_contiene(p2, cajas) or _caja_mas_cercana(p2, cajas)

            if caja1 is None or caja2 is None or caja1 is caja2:
                continue

            nombre1 = caja_a_nombre.get(id(caja1))
            nombre2 = caja_a_nombre.get(id(caja2))
            if not nombre1 or not nombre2:
                continue

            clave = (nombre1, nombre2)
            if clave in vistas:
                continue
            vistas.add(clave)

            # Heurística de tipo: por defecto ASOCIACION.
            # Si la línea es más vertical y la caja origen está arriba,
            # podría ser generalización, pero sin información adicional
            # dejamos ASOCIACION.
            relaciones.append(
                {
                    "origen": nombre1,
                    "destino": nombre2,
                    "tipo": "ASOCIACION",
                    "multiplicidad_origen": None,
                    "multiplicidad_destino": None,
                    "nombre_asociacion": None,
                    "rol_origen": None,
                    "rol_destino": None,
                }
            )

        return relaciones

    # ------------------------------------------------------------------
    # Helpers de texto
    # ------------------------------------------------------------------
    @staticmethod
    def _detectar_indice_nombre(lineas: list[str]) -> Optional[int]:
        """
        Busca el índice de la primera línea que parece nombre de clase:
        empieza con mayúscula, sin ':' ni '('.
        Si ninguna cumple, devuelve 0 (primera línea) como fallback.
        """
        for i, ln in enumerate(lineas):
            s = ln.strip()
            if not s:
                continue
            if ":" in s or "(" in s:
                continue
            # Quitar estereotipos antes de validar
            limpio = re.sub(r"<<[^>]*>>", "", s).strip()
            if not limpio:
                continue
            if _CLASE_RE.match(limpio):
                return i
        return 0 if lineas else None

    @staticmethod
    def _limpiar_nombre_clase(texto: str) -> str:
        s = texto.strip()
        # Quitar estereotipo si está al inicio:  <<entity> Paciente
        s = re.sub(r"<<[^>]*>>", "", s).strip()
        # Quitar caracteres obvios de ruido
        s = re.sub(r"[^A-Za-z0-9_ ]", "", s).strip()
        return s

    @staticmethod
    def _a_pascal_case(nombre: str) -> str:
        partes = re.split(r"[\s_\-]+", nombre.strip())
        partes = [p for p in partes if p]
        if not partes:
            return "Clase"
        return "".join(p[0].upper() + p[1:] if p else "" for p in partes)

    @staticmethod
    def _to_camel(nombre: str) -> str:
        partes = re.split(r"[\s_\-]+", nombre.strip())
        partes = [p for p in partes if p]
        if not partes:
            return "campo"
        if len(partes) == 1:
            p = partes[0]
            return p[0].lower() + p[1:]
        return partes[0][0].lower() + partes[0][1:] + "".join(
            p[0].upper() + p[1:] for p in partes[1:]
        )

    @staticmethod
    def _normalizar_tipo(tipo: str) -> str:
        """
        Normaliza nombres de tipo comunes que el OCR puede haber escrito
        con minúsculas o variantes.
        """
        if not tipo:
            return "String"
        t = tipo.strip()
        mapping = {
            "string": "String", "str": "String", "texto": "String",
            "int": "Integer", "integer": "Integer", "entero": "Integer",
            "long": "Long",
            "float": "Float", "double": "Double",
            "boolean": "Boolean", "bool": "Boolean",
            "date": "Date", "fecha": "Date",
            "datetime": "DateTime",
            "void": "void",
        }
        return mapping.get(t.lower(), t[0].upper() + t[1:] if t else "String")


# ======================================================================
# Helpers a nivel módulo
# ======================================================================
def _caja_mas_cercana(
    punto: tuple[int, int], cajas: list[CajaDetectada], *, margen: int = 30
) -> Optional[CajaDetectada]:
    """
    Devuelve la caja cuyo borde está a menos de `margen` px del punto,
    priorizando la más cercana. Sirve para líneas que terminan apenas
    afuera del rectángulo (típico de flechas y conexiones).
    """
    if not cajas:
        return None
    x, y = punto
    mejor: Optional[CajaDetectada] = None
    mejor_dist = float("inf")

    for c in cajas:
        b = c.box
        # Distancia al rectángulo (0 si está dentro)
        dx = max(b.x - x, 0, x - (b.x + b.ancho))
        dy = max(b.y - y, 0, y - (b.y + b.alto))
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= margen and dist < mejor_dist:
            mejor_dist = dist
            mejor = c

    return mejor