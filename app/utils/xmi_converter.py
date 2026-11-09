# app/utils/xmi_converter.py
"""
Conversión entre diagrama de clases y XMI/XML — CICLO 2.

Soporta DOS formatos:

1. **Formato DevForge AI** (round-trip propio):
   - Usa namespaces XMI 2.5/UML 2.5 estándar.
   - `<Class>`, `<Attribute>`, `<Operation>`, `<Parameter>`, `<Interface>`.
   - Relaciones como elemento con el tag de su tipo (`<Association>`,
     `<Aggregation>`, `<Composition>`, `<Dependency>`,
     `<Generalization>`, `<InterfaceRealization>`) y source/target.
   - Tipos como atributo `type="String"`.

2. **Formato Enterprise Architect** (XMI 1.1 / UML 1.3):
   - `<XMI>` con `<UML:Model>` dentro de `<XMI.content>`.
   - Clases en `<UML:Namespace.ownedElement>` dentro de `<UML:Package>`.
   - Atributos/operaciones en `<UML:Classifier.feature>`.
   - Tipos vía `<UML:TaggedValue tag="type" value="char">` o por
     `xmi.idref` contra los `<UML:DataType>` declarados.
   - Relaciones vía `<UML:Association>` con `<UML:Association.connection>`
     (el atributo `aggregation="composite|aggregate"` de los extremos
     distingue composición/agregación) y `<UML:Generalization>` con
     child/parent. Las Association Classes de EA (M:N con clase
     intermedia) se convierten en DOS relaciones 1:N intermediadas.
   - Posiciones en `<UML:DiagramElement geometry="Left=..;Top=..">`.

La exportación (`diagrama_a_xmi`) sale en formato DevForge AI por
defecto; con formato="ea" se genera XMI 1.1/UML 1.3 que Enterprise
Architect puede abrir y que DevForge reimporta sin pérdidas.
La importación (`xmi_a_estructura`) detecta el formato automáticamente
y lanza `BadRequestError` si el XML es inválido o desconocido.

Cambios de la reconversión Ciclo 1 → Ciclo 2 (Tanda 19c):

- Módulo PURO (sin imports de Beanie/SQLAlchemy): el Diagrama llega
  duck-typed (getattr) con sus embebidos ClaseUML/AtributoUML/
  OperacionUML/ParametroOperacionUML/InterfazUML/OperacionInterfazUML/
  RelacionUML, así que sigue testeable sin base de datos (misma política
  que mapping_engine y postman_export en la Tanda 18).
- IDS: el Diagrama pasa de int a PydanticObjectId (str() explícito en
  los atributos XML) y los elementos embebidos usan ids uuid hex
  generados en la aplicación (en el Ciclo 1 eran ints de fila). Los
  xmi:id quedan "clase_<uuid>", "attr_<uuid>", "op_<uuid>", "rel_<uuid>";
  como el parser DevForge resuelve source/target vía id→nombre, el
  cambio es transparente para el round-trip.
- datetime.utcnow() (deprecado en Python 3.12) → datetime.now(timezone.utc)
  con los MISMOS formatos de timestamp de salida.
- BUG de detección corregido: el chequeo del formato DevForge (raíz
  <xmi:XMI> con el namespace OMG) va PRIMERO. En el Ciclo 1 quedaba
  DESPUÉS del chequeo EA y, como la raíz DevForge también tiene
  localname "XMI" y un <Model> dentro, caía en la rama de EA: el
  round-trip DevForge→DevForge se parseaba con clases vacías (el parser
  EA busca Classifier.feature, que el exportador DevForge no escribe).
  Cazado por el arnés de esta tanda.
- FIDELIDAD del exportador EA (el del Ciclo 1 solo escribía clases con
  atributos y asociaciones; reimportar perdía operaciones, interfaces,
  herencias, roles, valores por defecto y estáticos):
  * escribe <UML:Operation> (con <UML:Parameter> tipado) y
    <UML:Interface> (con sus operaciones y posición en el diagrama);
  * las GENERALIZACIONES viajan como <UML:Generalization child/parent>;
  * DEPENDENCIA y REALIZACION viajan como <UML:Association> + un
    TaggedValue "tipo_relacion" que el importador lee con prioridad
    sobre el atributo aggregation de los extremos (EA ignora los
    tagged values desconocidos: sigue siendo XMI 1.1 válido);
  * es_aspecto estático viaja en ownerScope="classifier" (y el
    importador ya lo lee), el valor por defecto en un TaggedValue
    "defaultValue", el estereotipo en un TaggedValue "stereotype", el
    nombre de la asociación en un TaggedValue "name" y los roles en el
    atributo name de cada AssociationEnd (convención UML 1.3).
- Fix del importador EA: el tipo de retorno de las operaciones de
  interfaz ya no es "void" fijo: se lee el TaggedValue del tipo y se
  normaliza al vocabulario DevForge (misma regla que las operaciones
  de clase).
- Código muerto eliminado del original: diagrama_a_xmiiii (duplicado
  con typo de _diagrama_a_xmi_devforge), el bloque _TIPOS_EA_A_DEVFORE
  comentado, el "Paso 4" comentado del parser EA y su primera pasada
  association_class_ids/associations_por_id (nadie consultaba esos
  acumuladores: la segunda pasada usa _extraer_association_class_id
  elemento a elemento). Typo interno corregido: _DEVFORE_A_EA →
  _DEVFORGE_A_EA (y _TIPOS_EA_A_DEVFORE → _TIPOS_EA_A_DEVFORGE).
- El CONTRATO con IntercambioService NO cambia: xmi_a_estructura
  devuelve {"clases": [...], "interfaces": [...], "relaciones": [...]}
  con exactamente las claves que consume
  _aplicar_estructura_a_diagrama (nombre/es_abstracta/estereotipo/
  pos_x/pos_y/atributos/operaciones; origen/destino/tipo/
  multiplicidad_origen/multiplicidad_destino/nombre_asociacion/
  rol_origen/rol_destino).
- app/utils/__init__.py (Tanda 18) sigue sin exportar este módulo: el
  servicio lo importa por ruta completa (lazy) y el arnés de la Tanda
  13 mantiene su stub deliberado en sys.modules.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from xml.etree import ElementTree as ET

from app.core.exceptions import BadRequestError
from app.utils.identificadores import filtrar_identificadores_redundantes
from app.utils.validators import validar_multiplicidad


# Namespaces estándar (OMG XMI / UML) — usados por DevForge AI
XMI_NS = "http://www.omg.org/spec/XMI/20131001"
UML_NS = "http://www.omg.org/spec/UML/20131001"

ET.register_namespace("xmi", XMI_NS)
ET.register_namespace("uml", UML_NS)


# Tipos de relación válidos en el vocabulario DevForge (los 6 del
# modelo; se usa para aceptar el TaggedValue "tipo_relacion" del XMI
# sin importar app.models — este módulo es puro).
_TIPOS_RELACION = (
    "ASOCIACION",
    "AGREGACION",
    "COMPOSICION",
    "DEPENDENCIA",
    "GENERALIZACION",
    "REALIZACION",
)

# Mapeo tipo_relacion (BD) → tag XMI/UML
_TIPO_A_TAG = {
    "ASOCIACION": "Association",
    "AGREGACION": "Aggregation",
    "COMPOSICION": "Composition",
    "DEPENDENCIA": "Dependency",
    "GENERALIZACION": "Generalization",
    "REALIZACION": "InterfaceRealization",
}

# Mapeo inverso (tag → tipo_relacion BD)
_TAG_A_TIPO = {
    "Association": "ASOCIACION",
    "Aggregation": "AGREGACION",
    "Composition": "COMPOSICION",
    "Dependency": "DEPENDENCIA",
    "Generalization": "GENERALIZACION",
    "InterfaceRealization": "REALIZACION",
}

# Tipos canónicos DevForge → equivalentes EA (UML 1.3 usa los nombres
# de los primitivos del lenguaje: char, int, long, float, ...)
_DEVFORGE_A_EA = {
    "String": "char",
    "Text": "text",
    "Integer": "int",
    "Long": "long",
    "Short": "short",
    "Float": "float",
    "Double": "double",
    "BigDecimal": "decimal",
    "Boolean": "boolean",
    "Date": "date",
    "DateTime": "datetime",
    "Time": "time",
    "UUID": "uuid",
    "byte[]": "blob",
}

# Normalización de tipos EA (UML 1.3) → tipos canónicos DevForge.
# Los tipos desconocidos pasan tal cual (el gate de la Tanda 18 los
# reporta como TIPO_NO_MAPEADO al momento de generar código).
_TIPOS_EA_A_DEVFORGE = {
    "char": "String", "varchar": "String", "string": "String", "String": "String",
    "text": "Text", "Text": "Text",
    "int": "Integer", "integer": "Integer", "Integer": "Integer",
    "long": "Long", "Long": "Long",
    "short": "Short",
    "float": "Float", "Float": "Float",
    "double": "Double", "Double": "Double",
    "decimal": "BigDecimal", "BigDecimal": "BigDecimal",
    "boolean": "Boolean", "Boolean": "Boolean", "bool": "Boolean",
    "date": "Date", "Date": "Date",
    "datetime": "DateTime", "DateTime": "DateTime", "timestamp": "DateTime",
    "time": "Time", "Time": "Time",
    "uuid": "UUID", "UUID": "UUID",
    "blob": "byte[]", "byte[]": "byte[]",
}


# ======================================================================
# DIAGRAMA → XMI (formato DevForge AI)
# ======================================================================
def diagrama_a_xmi(diagrama: Any, formato: str = "devforge") -> str:
    """
    Serializa un Diagrama ORM a XMI.
    - formato="devforge" (default): XMI 2.5 con namespaces UML 2.5.
    - formato="ea": XMI 1.1 / UML 1.3 compatible con Enterprise Architect.
    """
    formato_norm = (formato or "devforge").lower()
    if formato_norm == "ea":
        return _diagrama_a_xmi_ea(diagrama)
    return _diagrama_a_xmi_devforge(diagrama)


def _diagrama_a_xmi_devforge(diagrama: Any) -> str:
    """
    Serializa un Diagrama (con sus clases, atributos, operaciones,
    parámetros e interfaces embebidas) a un string XML en formato
    DevForge (XMI 2.5 / UML 2.5).
    """
    diagrama_id = str(getattr(diagrama, "id", "") or "")

    root = ET.Element(
        f"{{{XMI_NS}}}XMI",
        attrib={
            "version": "2.5.1",
            "timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        },
    )
    meta = ET.SubElement(
        root,
        f"{{{XMI_NS}}}Documentation",
        attrib={
            "exporter": "DevForge AI",
            "diagrama_id": diagrama_id,
            "diagrama_nombre": getattr(diagrama, "nombre", ""),
            "version_uml": getattr(diagrama, "version_uml", "2.5.1"),
            "numero_version": str(getattr(diagrama, "numero_version", 1)),
        },
    )
    meta.text = f"Diagrama exportado por DevForge AI: {getattr(diagrama, 'nombre', '')}"

    model = ET.SubElement(
        root,
        f"{{{UML_NS}}}Model",
        attrib={f"{{{XMI_NS}}}id": f"model_{diagrama_id}"},
    )

    for clase in getattr(diagrama, "clases", []) or []:
        _clase_a_xml(model, clase)
    for interfaz in getattr(diagrama, "interfaces", []) or []:
        _interfaz_a_xml(model, interfaz)
    for relacion in getattr(diagrama, "relaciones", []) or []:
        _relacion_a_xml(model, relacion)

    _indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _clase_a_xml(parent: ET.Element, clase: Any) -> None:
    """Genera un <Class> DevForge con atributos y operaciones embebidas."""
    atrs = {
        f"{{{XMI_NS}}}id": f"clase_{clase.id}",
        f"{{{XMI_NS}}}type": "uml:Class",
        "name": clase.nombre,
        "isAbstract": "true" if getattr(clase, "es_abstracta", False) else "false",
        "pos_x": str(getattr(clase, "pos_x", 0)),
        "pos_y": str(getattr(clase, "pos_y", 0)),
    }
    if getattr(clase, "estereotipo", None):
        atrs["stereotype"] = clase.estereotipo

    clase_el = ET.SubElement(parent, "Class", attrib=atrs)

    # Tanda B25: al exportar a EA, un `id` + `id<Clase>` del diagrama
    # (diagramas viejos o dibujados a mano) sale como DOS identificadores
    # en Enterprise Architect. Se descarta el redundante en el vuelo
    # (el diagrama NO se modifica).
    atributos = filtrar_identificadores_redundantes(
        list(getattr(clase, "atributos", []) or []),
        clase.nombre,
        extraer_nombre=lambda a: getattr(a, "nombre", ""),
    )

    for attr in atributos:
        ET.SubElement(
            clase_el,
            "Attribute",
            attrib={
                f"{{{XMI_NS}}}id": f"attr_{attr.id}",
                "name": attr.nombre,
                "type": attr.tipo_dato,
                "visibility": _vis_a_xmi(attr.visibilidad),
                "isStatic": "true" if getattr(attr, "es_estatico", False) else "false",
                "defaultValue": getattr(attr, "valor_defecto", "") or "",
                "order": str(getattr(attr, "orden", 0)),
            },
        )

    for op in getattr(clase, "operaciones", []) or []:
        op_el = ET.SubElement(
            clase_el,
            "Operation",
            attrib={
                f"{{{XMI_NS}}}id": f"op_{op.id}",
                "name": op.nombre,
                "returnType": getattr(op, "tipo_retorno", "void"),
                "visibility": _vis_a_xmi(op.visibilidad),
                "isStatic": "true" if getattr(op, "es_estatico", False) else "false",
                "order": str(getattr(op, "orden", 0)),
            },
        )
        for param in getattr(op, "parametros", []) or []:
            ET.SubElement(
                op_el,
                "Parameter",
                attrib={
                    "name": param.nombre,
                    "type": param.tipo_dato,
                    "order": str(getattr(param, "orden", 0)),
                },
            )


def _interfaz_a_xml(parent: ET.Element, interfaz: Any) -> None:
    """Genera un <Interface> DevForge con sus operaciones declaradas."""
    iface_el = ET.SubElement(
        parent,
        "Interface",
        attrib={
            f"{{{XMI_NS}}}id": f"interfaz_{interfaz.id}",
            "name": interfaz.nombre,
            "pos_x": str(getattr(interfaz, "pos_x", 0)),
            "pos_y": str(getattr(interfaz, "pos_y", 0)),
        },
    )
    for op in getattr(interfaz, "operaciones", []) or []:
        ET.SubElement(
            iface_el,
            "Operation",
            attrib={
                f"{{{XMI_NS}}}id": f"ifop_{op.id}",
                "name": op.nombre,
                "returnType": getattr(op, "tipo_retorno", "void"),
            },
        )


def _relacion_a_xml(parent: ET.Element, relacion: Any) -> None:
    """Genera el elemento de relación DevForge (tag según el tipo)."""
    tag = _TIPO_A_TAG.get(relacion.tipo_relacion, "Association")
    atrs = {
        f"{{{XMI_NS}}}id": f"rel_{relacion.id}",
        "source": f"clase_{relacion.id_clase_origen}",
        "target": f"clase_{relacion.id_clase_destino}",
        "type": relacion.tipo_relacion,
    }
    if getattr(relacion, "multiplicidad_origen", None):
        atrs["sourceMultiplicity"] = relacion.multiplicidad_origen
    if getattr(relacion, "multiplicidad_destino", None):
        atrs["targetMultiplicity"] = relacion.multiplicidad_destino
    if getattr(relacion, "nombre_asociacion", None):
        atrs["name"] = relacion.nombre_asociacion
    if getattr(relacion, "rol_origen", None):
        atrs["sourceRole"] = relacion.rol_origen
    if getattr(relacion, "rol_destino", None):
        atrs["targetRole"] = relacion.rol_destino

    ET.SubElement(parent, tag, attrib=atrs)


def _vis_a_xmi(vis: str) -> str:
    """Visibilidad DevForge ('+', '-', '#', '~') → palabra XMI."""
    return {
        "+": "public",
        "-": "private",
        "#": "protected",
        "~": "package",
    }.get(vis, "private")


def _vis_desde_xmi(vis: str) -> str:
    """Palabra XMI → visibilidad DevForge ('+', '-', '#', '~')."""
    return {
        "public": "+",
        "private": "-",
        "protected": "#",
        "package": "~",
    }.get((vis or "").lower(), "-")


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Indentación en árbol para que el XML quede legible."""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


# ======================================================================
# XMI → ESTRUCTURA (detecta formato automáticamente)
# ======================================================================
def xmi_a_estructura(xml_str: str) -> dict[str, Any]:
    """
    Parsea un string XMI/XML y devuelve una estructura neutral:
    {
      "clases": [...],
      "interfaces": [...],
      "relaciones": [...]
    }

    Detecta automáticamente el formato:
    - DevForge AI (UML 2.5 / XMI 2.5, raíz <xmi:XMI> con namespace OMG)
    - Enterprise Architect (UML 1.3 / XMI 1.1, raíz <XMI> con
      <XMI.content>)

    Lanza `BadRequestError` si el XML es inválido o no se reconoce.
    """
    if not xml_str or not xml_str.strip():
        raise BadRequestError("El XML está vacío")

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        raise BadRequestError(f"XML mal formado: {exc}") from exc

    # Detectar formato
    formato = _detectar_formato(root)

    if formato == "enterprise_architect":
        return _parsear_enterprise_architect(root)
    elif formato == "devforge":
        return _parsear_devforge(root)

    raise BadRequestError(
        "Formato XMI no reconocido. Se esperaba XMI 1.1 (Enterprise "
        "Architect) o XMI 2.5 (DevForge AI)."
    )


def _detectar_formato(root: ET.Element) -> str:
    """
    Detecta el formato del XMI según la estructura de la raíz.

    IMPORTANTE: el chequeo DevForge va PRIMERO. La raíz <xmi:XMI> de
    DevForge también tiene localname "XMI" y un <Model> dentro, así que
    si se evaluara después del chequeo EA caería en la rama equivocada
    (bug del Ciclo 1 que partía el round-trip DevForge→DevForge).
    """
    tag_root = _localname(root.tag)

    # 1) DevForge AI: raíz <xmi:XMI> con el namespace OMG de XMI en el
    #    propio tag. Solo el formato propio usa namespaces.
    if tag_root == "XMI" and "omg.org/spec/XMI" in str(root.tag):
        return "devforge"

    # 2) Enterprise Architect: raíz <XMI> SIN namespace con
    #    <XMI.content> dentro.
    if tag_root == "XMI":
        for child in root:
            if _localname(child.tag) == "content":
                return "enterprise_architect"
        # Algunos XMI vienen sin XMI.content: si hay un <Model> en algún
        # lado es EA-like, salvo que las clases traigan la firma propia
        # de DevForge (pos_x como atributo plano del <Class>).
        for child in root.iter():
            if _localname(child.tag) == "Model":
                for c in child.iter():
                    if _localname(c.tag) == "Class" and "pos_x" in c.attrib:
                        return "devforge"
                return "enterprise_architect"

    # 3) Fallback: raíz rara pero con un <Model> dentro.
    for child in root.iter():
        if _localname(child.tag) == "Model":
            for c in child.iter():
                if _localname(c.tag) == "Class" and "pos_x" in c.attrib:
                    return "devforge"
            return "enterprise_architect"

    return "unknown"


# ======================================================================
# PARSER: Enterprise Architect (UML 1.3 / XMI 1.1)
# ======================================================================
def _parsear_enterprise_architect(root: ET.Element) -> dict[str, Any]:
    """
    Parser específico para XMI de Enterprise Architect.
    """
    # Paso 1: recolectar todos los DataType (para resolver xmi.idref)
    tipos_por_id: dict[str, str] = {}
    for el in root.iter():
        if _localname(el.tag) == "DataType":
            xmi_id = el.attrib.get("xmi.id")
            nombre = el.attrib.get("name", "")
            if xmi_id and nombre:
                tipos_por_id[xmi_id] = nombre

    # Paso 2: recolectar posiciones desde <UML:Diagram>
    posiciones: dict[str, tuple[float, float]] = {}
    for el in root.iter():
        if _localname(el.tag) != "DiagramElement":
            continue
        subject = el.attrib.get("subject")
        geometry = el.attrib.get("geometry", "")
        if not subject or not geometry:
            continue
        # geometry: "Left=248;Top=166;Right=338;Bottom=236;"
        partes = _parsear_geometry(geometry)
        if "left" in partes and "top" in partes:
            posiciones[subject] = (partes["left"], partes["top"])

    # Paso 3: recolectar clases e interfaces
    clases: list[dict[str, Any]] = []
    interfaces: list[dict[str, Any]] = []
    id_a_nombre: dict[str, str] = {}   # xmi.id → nombre

    for el in root.iter():
        tag = _localname(el.tag)
        if tag == "Class":
            nombre = el.attrib.get("name", "").strip()
            # Ignorar clases de infraestructura de EA
            if nombre in ("EARootClass",) or not nombre:
                continue
            xmi_id = el.attrib.get("xmi.id")
            if xmi_id:
                id_a_nombre[xmi_id] = nombre

            pos = posiciones.get(xmi_id or "", (0.0, 0.0))
            clase = _parsear_clase_ea(el, tipos_por_id, pos)
            clases.append(clase)

        elif tag == "Interface":
            nombre = el.attrib.get("name", "").strip()
            if not nombre:
                continue
            xmi_id = el.attrib.get("xmi.id")
            if xmi_id:
                id_a_nombre[xmi_id] = nombre
            pos = posiciones.get(xmi_id or "", (0.0, 0.0))
            interfaz = _parsear_interfaz_ea(el, pos)
            interfaces.append(interfaz)

    # Paso 4: recolectar relaciones (Association, Generalization, etc.).
    # Las Association Classes de EA son clases cuyo xmi.id aparece en el
    # TaggedValue "associationclass" de una Association: NO se tratan
    # como tablas sueltas; la relación M:N se reemplaza por DOS
    # relaciones 1:N intermediadas por la clase intermedia.
    relaciones: list[dict[str, Any]] = []

    for el in root.iter():
        tag = _localname(el.tag)
        if tag == "Association":
            # ¿Es una Association con AssociationClass?
            ac_id = _extraer_association_class_id(el)
            if ac_id and ac_id in id_a_nombre:
                rels = _parsear_association_con_clase_ea(
                    el, id_a_nombre, ac_id
                )
                if rels:
                    relaciones.extend(rels)
                    continue
            # Asociación normal (o AssociationClass que no se pudo
            # resolver: mejor conservarla como asociación simple)
            rel = _parsear_association_ea(el, id_a_nombre)
            if rel is not None:
                relaciones.append(rel)
        elif tag == "Generalization":
            # <UML:Generalization child="EAID_..." parent="EAID_..."/>
            # child hereda de parent → origen (hijo) → destino (padre)
            rel = _parsear_generalization_ea(el, id_a_nombre)
            if rel is not None:
                relaciones.append(rel)

    if not clases and not interfaces:
        raise BadRequestError(
            "El XMI de Enterprise Architect no contiene clases ni interfaces."
        )

    return {
        "clases": clases,
        "interfaces": interfaces,
        "relaciones": relaciones,
    }


def _extraer_association_class_id(el: ET.Element) -> Optional[str]:
    """Devuelve el xmi.id de la AssociationClass referenciada, si la hay."""
    for child in el:
        if _localname(child.tag) != "ModelElement.taggedValue":
            continue
        for tv in child:
            if _localname(tv.tag) != "TaggedValue":
                continue
            if tv.attrib.get("tag") == "associationclass":
                return tv.attrib.get("value") or None
    return None


def _parsear_association_con_clase_ea(
    el: ET.Element,
    id_a_nombre: dict[str, str],
    association_class_id: str,
) -> list[dict[str, Any]]:
    """
    Convierte una Association con AssociationClass de EA en DOS relaciones
    en el formato neutral de DevForge:

      - Origen (alumno) → AssociationClass (inscripcion)
      - AssociationClass (inscripcion) → Destino (curso)

    Esto refleja la conversión UML → relacional: la clase intermedia
    materializa la relación M:N.
    """
    ends: list[ET.Element] = []
    for child in el:
        if _localname(child.tag) != "Association.connection":
            continue
        for end in child:
            if _localname(end.tag) == "AssociationEnd":
                ends.append(end)

    if len(ends) < 2:
        return []

    origen_id = ends[0].attrib.get("type")
    destino_id = ends[1].attrib.get("type")

    origen_nombre = id_a_nombre.get(origen_id or "")
    destino_nombre = id_a_nombre.get(destino_id or "")
    intermedia_nombre = id_a_nombre.get(association_class_id)

    if not (origen_nombre and destino_nombre and intermedia_nombre):
        return []

    mult_origen = _validar_multiplicidad_segura(ends[0].attrib.get("multiplicity"))
    mult_destino = _validar_multiplicidad_segura(ends[1].attrib.get("multiplicity"))

    # Relación 1: origen → intermedia
    rel1 = {
        "origen": origen_nombre,
        "destino": intermedia_nombre,
        "tipo": "ASOCIACION",
        "multiplicidad_origen": "1",
        "multiplicidad_destino": mult_origen or "1..*",
        "nombre_asociacion": None,
        "rol_origen": None,
        "rol_destino": None,
    }

    # Relación 2: intermedia → destino
    rel2 = {
        "origen": intermedia_nombre,
        "destino": destino_nombre,
        "tipo": "ASOCIACION",
        "multiplicidad_origen": mult_destino or "1..*",
        "multiplicidad_destino": "1",
        "nombre_asociacion": None,
        "rol_origen": None,
        "rol_destino": None,
    }

    return [rel1, rel2]


def _parsear_clase_ea(
    el: ET.Element,
    tipos_por_id: dict[str, str],
    posicion: tuple[float, float],
) -> dict[str, Any]:
    """
    Convierte un <UML:Class> de EA en el formato neutral de DevForge.
    """
    atributos: list[dict[str, Any]] = []
    operaciones: list[dict[str, Any]] = []

    # Buscar <UML:Classifier.feature> dentro de la clase
    for feature in el:
        if _localname(feature.tag) != "Classifier.feature":
            continue
        for hijo in feature:
            tag = _localname(hijo.tag)
            if tag == "Attribute":
                atributos.append(_parsear_attribute_ea(hijo, tipos_por_id))
            elif tag == "Operation":
                operaciones.append(_parsear_operation_ea(hijo, tipos_por_id))

    pos_x, pos_y = posicion

    # El estereotipo viaja en un TaggedValue "stereotype" (lo escribe el
    # exportador de DevForge; EA lo ignora si no lo conoce).
    estereotipo = _tagged_value_de(el, "stereotype")

    return {
        "nombre": el.attrib.get("name", "").strip(),
        "es_abstracta": el.attrib.get("isAbstract", "false").lower() == "true",
        "estereotipo": estereotipo,
        "pos_x": pos_x,
        "pos_y": pos_y,
        "atributos": atributos,
        "operaciones": operaciones,
    }


def _parsear_attribute_ea(
    el: ET.Element,
    tipos_por_id: dict[str, str],
) -> dict[str, Any]:
    """
    Convierte un <UML:Attribute> de EA en el formato neutral.
    """
    nombre = el.attrib.get("name", "").strip()
    visibility_ea = el.attrib.get("visibility", "private")

    # TaggedValues de EA:
    # - "type": el tipo explícito (convención de EA)
    # - "position": orden del atributo dentro de la clase
    # - "defaultValue": valor inicial (lo escribe el exportador DevForge)
    tipo: Optional[str] = None
    orden = 0
    valor_defecto: Optional[str] = None

    for child in el:
        if _localname(child.tag) != "ModelElement.taggedValue":
            continue
        for tv in child:
            if _localname(tv.tag) != "TaggedValue":
                continue
            tag_tv = tv.attrib.get("tag")
            if tag_tv == "type" and tipo is None:
                tipo = (tv.attrib.get("value") or "").strip() or None
            elif tag_tv == "position":
                orden = _safe_int(tv.attrib.get("value"), 0)
            elif tag_tv == "defaultValue":
                valor_defecto = tv.attrib.get("value") or None

    # Fallback: resolver por xmi.idref apuntando a un DataType
    if not tipo:
        for child in el:
            if _localname(child.tag) == "StructuralFeature.type":
                for ref in child:
                    if _localname(ref.tag) == "Classifier":
                        idref = ref.attrib.get("xmi.idref")
                        if idref and idref in tipos_por_id:
                            tipo = tipos_por_id[idref]
                            break

    if not tipo:
        tipo = "String"

    # Normalizar el tipo al vocabulario de DevForge
    tipo = _TIPOS_EA_A_DEVFORGE.get(tipo, tipo)

    # EA marca los atributos estáticos con ownerScope="classifier"
    es_estatico = el.attrib.get("ownerScope", "instance").lower() == "classifier"

    return {
        "nombre": nombre,
        "tipo_dato": tipo,
        "visibilidad": _vis_desde_ea(visibility_ea),
        "es_estatico": es_estatico,
        "valor_defecto": valor_defecto,
        "orden": orden,
    }


def _parsear_operation_ea(
    el: ET.Element,
    tipos_por_id: dict[str, str],
) -> dict[str, Any]:
    """
    Convierte un <UML:Operation> de EA en el formato neutral.
    """
    nombre = el.attrib.get("name", "").strip()
    visibility_ea = el.attrib.get("visibility", "public")

    # Tipo de retorno: en EA puede estar en taggedValue "type",
    # "returnType" o "return_type" (DevForge escribe "returnType").
    tipo_retorno = "void"
    orden = 0
    for child in el:
        if _localname(child.tag) != "ModelElement.taggedValue":
            continue
        for tv in child:
            if _localname(tv.tag) != "TaggedValue":
                continue
            tag_tv = tv.attrib.get("tag")
            if tag_tv in ("type", "returnType", "return_type"):
                tipo_retorno = tv.attrib.get("value", "void") or "void"
            elif tag_tv == "position":
                orden = _safe_int(tv.attrib.get("value"), 0)

    tipo_retorno = _TIPOS_EA_A_DEVFORGE.get(tipo_retorno, tipo_retorno)

    # Parámetros: <UML:Parameter> dentro de <UML:BehavioralFeature.parameter>
    parametros: list[dict[str, Any]] = []
    for child in el:
        if _localname(child.tag) != "BehavioralFeature.parameter":
            continue
        for p in child:
            if _localname(p.tag) != "Parameter":
                continue
            p_nombre = p.attrib.get("name", "").strip()
            p_tipo = "String"
            for sub in p:
                if _localname(sub.tag) == "ModelElement.taggedValue":
                    for tv in sub:
                        if _localname(tv.tag) == "TaggedValue" and tv.attrib.get("tag") == "type":
                            p_tipo = tv.attrib.get("value", "String") or "String"
            p_tipo = _TIPOS_EA_A_DEVFORGE.get(p_tipo, p_tipo)
            parametros.append({
                "nombre": p_nombre,
                "tipo_dato": p_tipo,
                "orden": len(parametros),
            })

    # EA marca las operaciones estáticas con ownerScope="classifier"
    es_estatico = el.attrib.get("ownerScope", "instance").lower() == "classifier"

    return {
        "nombre": nombre,
        "tipo_retorno": tipo_retorno,
        "visibilidad": _vis_desde_ea(visibility_ea),
        "es_estatico": es_estatico,
        "orden": orden,
        "parametros": parametros,
    }


def _parsear_interfaz_ea(
    el: ET.Element, posicion: tuple[float, float]
) -> dict[str, Any]:
    """Convierte un <UML:Interface> de EA en el formato neutral."""
    operaciones: list[dict[str, Any]] = []
    for feature in el:
        if _localname(feature.tag) != "Classifier.feature":
            continue
        for hijo in feature:
            if _localname(hijo.tag) == "Operation":
                # El tipo de retorno ya no es "void" fijo: se lee el
                # TaggedValue del tipo (misma regla que las operaciones
                # de clase) y se normaliza.
                tipo_retorno = "void"
                for child in hijo:
                    if _localname(child.tag) != "ModelElement.taggedValue":
                        continue
                    for tv in child:
                        if _localname(tv.tag) == "TaggedValue" and tv.attrib.get("tag") in (
                            "type", "returnType", "return_type"
                        ):
                            tipo_retorno = tv.attrib.get("value", "void") or "void"
                tipo_retorno = _TIPOS_EA_A_DEVFORGE.get(tipo_retorno, tipo_retorno)
                operaciones.append({
                    "nombre": hijo.attrib.get("name", "").strip(),
                    "tipo_retorno": tipo_retorno,
                })
    pos_x, pos_y = posicion
    return {
        "nombre": el.attrib.get("name", "").strip(),
        "pos_x": pos_x,
        "pos_y": pos_y,
        "operaciones": operaciones,
    }


def _parsear_association_ea(
    el: ET.Element, id_a_nombre: dict[str, str]
) -> Optional[dict[str, Any]]:
    """
    Convierte un <UML:Association> de EA en el formato neutral.

    Estructura de EA:
      <UML:Association>
        <UML:Association.connection>
          <UML:AssociationEnd type="EAID_origen" multiplicity="1..*"/>
          <UML:AssociationEnd type="EAID_destino" multiplicity="1..*"/>
        </UML:Association.connection>
      </UML:Association>
    """
    ends: list[ET.Element] = []
    for child in el:
        if _localname(child.tag) != "Association.connection":
            continue
        for end in child:
            if _localname(end.tag) == "AssociationEnd":
                ends.append(end)

    if len(ends) < 2:
        return None

    origen_id = ends[0].attrib.get("type")
    destino_id = ends[1].attrib.get("type")

    origen_nombre = id_a_nombre.get(origen_id or "")
    destino_nombre = id_a_nombre.get(destino_id or "")

    if not origen_nombre or not destino_nombre:
        return None

    mult_origen = _validar_multiplicidad_segura(ends[0].attrib.get("multiplicity"))
    mult_destino = _validar_multiplicidad_segura(ends[1].attrib.get("multiplicity"))

    # TaggedValues de la asociación (un solo barrido):
    # - "name": nombre de la asociación (lo escribe DevForge; EA también
    #   guarda el nombre en un tagged value cuando la hay)
    # - "tipo_relacion": hint que escribe el exportador de DevForge para
    #   las relaciones que EA serializa como Association igual que las
    #   asociaciones (DEPENDENCIA, REALIZACION)
    nombre_asociacion: Optional[str] = None
    hint_tipo: Optional[str] = None
    for child in el:
        if _localname(child.tag) != "ModelElement.taggedValue":
            continue
        for tv in child:
            if _localname(tv.tag) != "TaggedValue":
                continue
            tag_tv = tv.attrib.get("tag")
            if tag_tv == "name" and nombre_asociacion is None:
                nombre_asociacion = tv.attrib.get("value") or None
            elif tag_tv == "tipo_relacion":
                hint_tipo = (tv.attrib.get("value") or "").strip().upper() or None

    # Roles: en UML 1.3 el nombre del extremo ES el rol
    rol_origen = ends[0].attrib.get("name") or None
    rol_destino = ends[1].attrib.get("name") or None

    # Tipo de la relación, en orden de prioridad:
    # 1) hint "tipo_relacion" del exportador de DevForge;
    # 2) atributo aggregation de los extremos (EA nativo):
    #    composite → COMPOSICION, aggregate → AGREGACION;
    # 3) ASOCIACION por defecto.
    if hint_tipo in _TIPOS_RELACION:
        tipo = hint_tipo
    else:
        tipo = "ASOCIACION"
        for end in ends:
            agg = end.attrib.get("aggregation", "none").lower()
            if agg == "composite":
                tipo = "COMPOSICION"
                break
            elif agg == "aggregate":
                tipo = "AGREGACION"
                break

    return {
        "origen": origen_nombre,
        "destino": destino_nombre,
        "tipo": tipo,
        "multiplicidad_origen": mult_origen,
        "multiplicidad_destino": mult_destino,
        "nombre_asociacion": nombre_asociacion,
        "rol_origen": rol_origen,
        "rol_destino": rol_destino,
    }


def _parsear_generalization_ea(
    el: ET.Element, id_a_nombre: dict[str, str]
) -> Optional[dict[str, Any]]:
    """
    Convierte un <UML:Generalization> de EA.

    Estructura típica:
      <UML:Generalization child="EAID_hijo" parent="EAID_padre"/>
    El child HEREDA del parent. Se representa como relación con
    origen=child, destino=parent, tipo=GENERALIZACION.
    """
    child_id = el.attrib.get("child") or el.attrib.get("subtype")
    parent_id = el.attrib.get("parent") or el.attrib.get("supertype")

    origen_nombre = id_a_nombre.get(child_id or "")
    destino_nombre = id_a_nombre.get(parent_id or "")

    if not origen_nombre or not destino_nombre:
        return None

    return {
        "origen": origen_nombre,
        "destino": destino_nombre,
        "tipo": "GENERALIZACION",
        "multiplicidad_origen": None,
        "multiplicidad_destino": None,
        "nombre_asociacion": None,
        "rol_origen": None,
        "rol_destino": None,
    }


def _vis_desde_ea(vis: str) -> str:
    """EA usa: public, private, protected, package."""
    return _vis_desde_xmi(vis)


def _parsear_geometry(geometry: str) -> dict[str, float]:
    """
    Parsea 'Left=248;Top=166;Right=338;Bottom=236;' a dict numérico.
    """
    result: dict[str, float] = {}
    for parte in geometry.split(";"):
        if "=" not in parte:
            continue
        k, v = parte.split("=", 1)
        k = k.strip().lower()
        try:
            result[k] = float(v)
        except (TypeError, ValueError):
            continue
    return result


def _validar_multiplicidad_segura(valor: Optional[str]) -> Optional[str]:
    """Intenta validar; si falla, devuelve el string tal cual."""
    try:
        return validar_multiplicidad(valor)
    except Exception:
        return valor


def _tagged_value_de(el: ET.Element, tag_buscado: str) -> Optional[str]:
    """Devuelve el value del primer TaggedValue con ese tag (o None)."""
    for child in el:
        if _localname(child.tag) != "ModelElement.taggedValue":
            continue
        for tv in child:
            if _localname(tv.tag) != "TaggedValue":
                continue
            if tv.attrib.get("tag") == tag_buscado:
                return tv.attrib.get("value") or None
    return None


# ======================================================================
# PARSER: DevForge AI (UML 2.5 / XMI 2.5)
# ======================================================================
def _parsear_devforge(root: ET.Element) -> dict[str, Any]:
    """
    Parser para el formato propio de DevForge AI.
    """
    id_a_nombre: dict[str, str] = {}
    clases: list[dict[str, Any]] = []
    interfaces: list[dict[str, Any]] = []
    relaciones: list[dict[str, Any]] = []

    for el in root.iter():
        tag = _localname(el.tag)
        if tag == "Class":
            clases.append(_parse_clase_devforge(el, id_a_nombre))
        elif tag == "Interface":
            interfaces.append(_parse_interfaz_devforge(el, id_a_nombre))

    for el in root.iter():
        tag = _localname(el.tag)
        if tag in _TAG_A_TIPO:
            rel = _parse_relacion_devforge(el, id_a_nombre)
            if rel is not None:
                relaciones.append(rel)

    if not clases and not interfaces:
        raise BadRequestError(
            "El XMI no contiene clases ni interfaces reconocibles"
        )

    return {
        "clases": clases,
        "interfaces": interfaces,
        "relaciones": relaciones,
    }


def _parse_clase_devforge(
    el: ET.Element, id_a_nombre: dict[str, str]
) -> dict[str, Any]:
    nombre = el.attrib.get("name", "").strip()
    xmi_id = _get_xmi_id(el)
    if xmi_id and nombre:
        id_a_nombre[xmi_id] = nombre

    atributos: list[dict[str, Any]] = []
    operaciones: list[dict[str, Any]] = []

    for child in list(el):
        tag = _localname(child.tag)
        if tag == "Attribute":
            atributos.append({
                "nombre": child.attrib.get("name", "").strip(),
                "tipo_dato": child.attrib.get("type", "String"),
                "visibilidad": _vis_desde_xmi(
                    child.attrib.get("visibility", "private")
                ),
                "es_estatico": child.attrib.get("isStatic", "false").lower() == "true",
                "valor_defecto": child.attrib.get("defaultValue") or None,
                "orden": _safe_int(child.attrib.get("order"), 0),
            })
        elif tag == "Operation":
            params = []
            for sub in list(child):
                if _localname(sub.tag) == "Parameter":
                    params.append({
                        "nombre": sub.attrib.get("name", "").strip(),
                        "tipo_dato": sub.attrib.get("type", "String"),
                        "orden": _safe_int(sub.attrib.get("order"), 0),
                    })
            operaciones.append({
                "nombre": child.attrib.get("name", "").strip(),
                "tipo_retorno": child.attrib.get("returnType", "void"),
                "visibilidad": _vis_desde_xmi(
                    child.attrib.get("visibility", "public")
                ),
                "es_estatico": child.attrib.get("isStatic", "false").lower() == "true",
                "orden": _safe_int(child.attrib.get("order"), 0),
                "parametros": params,
            })

    return {
        "nombre": nombre,
        "es_abstracta": el.attrib.get("isAbstract", "false").lower() == "true",
        "estereotipo": el.attrib.get("stereotype") or None,
        "pos_x": _safe_float(el.attrib.get("pos_x"), 0.0),
        "pos_y": _safe_float(el.attrib.get("pos_y"), 0.0),
        "atributos": atributos,
        "operaciones": operaciones,
    }


def _parse_interfaz_devforge(
    el: ET.Element, id_a_nombre: dict[str, str]
) -> dict[str, Any]:
    nombre = el.attrib.get("name", "").strip()
    xmi_id = _get_xmi_id(el)
    if xmi_id and nombre:
        id_a_nombre[xmi_id] = nombre

    operaciones = []
    for child in list(el):
        if _localname(child.tag) == "Operation":
            operaciones.append({
                "nombre": child.attrib.get("name", "").strip(),
                "tipo_retorno": child.attrib.get("returnType", "void"),
            })

    return {
        "nombre": nombre,
        "pos_x": _safe_float(el.attrib.get("pos_x"), 0.0),
        "pos_y": _safe_float(el.attrib.get("pos_y"), 0.0),
        "operaciones": operaciones,
    }


def _parse_relacion_devforge(
    el: ET.Element, id_a_nombre: dict[str, str]
) -> Optional[dict[str, Any]]:
    tag = _localname(el.tag)
    tipo = _TAG_A_TIPO.get(tag)
    if not tipo:
        return None

    source = el.attrib.get("source", "")
    target = el.attrib.get("target", "")

    origen_nombre = id_a_nombre.get(source)
    destino_nombre = id_a_nombre.get(target)

    if not origen_nombre or not destino_nombre:
        return None

    try:
        mult_o = validar_multiplicidad(el.attrib.get("sourceMultiplicity"))
        mult_d = validar_multiplicidad(el.attrib.get("targetMultiplicity"))
    except Exception:
        mult_o = el.attrib.get("sourceMultiplicity")
        mult_d = el.attrib.get("targetMultiplicity")

    return {
        "origen": origen_nombre,
        "destino": destino_nombre,
        "tipo": tipo,
        "multiplicidad_origen": mult_o,
        "multiplicidad_destino": mult_d,
        "nombre_asociacion": el.attrib.get("name") or None,
        "rol_origen": el.attrib.get("sourceRole") or None,
        "rol_destino": el.attrib.get("targetRole") or None,
    }


# ======================================================================
# Helpers varios
# ======================================================================
def _localname(tag: str) -> str:
    """Devuelve el nombre local del tag, ignorando el namespace."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _get_xmi_id(el: ET.Element) -> Optional[str]:
    """Busca el xmi:id en cualquier namespace."""
    for k, v in el.attrib.items():
        if k.endswith("}id") or k == "id":
            return v
    return None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ======================================================================
# DIAGRAMA → XMI (formato Enterprise Architect, XMI 1.1 / UML 1.3)
# ======================================================================
def _diagrama_a_xmi_ea(diagrama: Any) -> str:
    """
    Serializa un Diagrama en formato XMI 1.1 / UML 1.3 compatible
    con Enterprise Architect.

    Fidelidad respecto al Ciclo 1: ahora también exporta las
    OPERACIONES (con parámetros), las INTERFACES (con posición) y las
    GENERALIZACIONES como <UML:Generalization>; DEPENDENCIA y
    REALIZACION viajan como Association + TaggedValue "tipo_relacion"
    que el importador de DevForge restaura.
    """
    import uuid

    # Root
    root = ET.Element("XMI", attrib={
        "xmi.version": "1.1",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })
    root.set("xmlns:UML", "omg.org/UML1.3")

    # Header
    header = ET.SubElement(root, "XMI.header")
    doc = ET.SubElement(header, "XMI.documentation")
    ET.SubElement(doc, "XMI.exporter").text = "DevForge AI"
    ET.SubElement(doc, "XMI.exporterVersion").text = "1.0"
    ET.SubElement(doc, "XMI.exporterID").text = str(uuid.uuid4().int)[:6]

    # Content
    content = ET.SubElement(root, "XMI.content")
    model = ET.SubElement(content, "UML:Model", attrib={
        "name": getattr(diagrama, "nombre", "Modelo"),
        "xmi.id": f"MX_{getattr(diagrama, 'id', 0)}",
    })
    owned = ET.SubElement(model, "UML:Namespace.ownedElement")

    # Package (EA siempre anida en un Package)
    package = ET.SubElement(owned, "UML:Package", attrib={
        "name": getattr(diagrama, "nombre", "diagrama"),
        "xmi.id": f"EAPK_{getattr(diagrama, 'id', 0)}",
        "isRoot": "false",
        "isLeaf": "false",
        "isAbstract": "false",
        "visibility": "public",
    })
    pkg_owned = ET.SubElement(package, "UML:Namespace.ownedElement")

    # Mapeo: id de clase/interfaz → xmi.id generado
    id_a_xmi: dict[str, str] = {}

    # Clases
    for clase in getattr(diagrama, "clases", []) or []:
        xmi_id = f"EAID_{clase.id}_{uuid.uuid4().hex[:8]}"
        id_a_xmi[clase.id] = xmi_id
        _clase_a_xml_ea(pkg_owned, clase, xmi_id)

    # Interfaces
    for interfaz in getattr(diagrama, "interfaces", []) or []:
        xmi_id = f"EAID_{interfaz.id}_{uuid.uuid4().hex[:8]}"
        id_a_xmi[interfaz.id] = xmi_id
        _interfaz_a_xml_ea(pkg_owned, interfaz, xmi_id)

    # Relaciones
    for relacion in getattr(diagrama, "relaciones", []) or []:
        origen_xmi = id_a_xmi.get(relacion.id_clase_origen)
        destino_xmi = id_a_xmi.get(relacion.id_clase_destino)
        if not origen_xmi or not destino_xmi:
            continue
        if relacion.tipo_relacion == "GENERALIZACION":
            # La herencia se exporta con su elemento UML propio
            # (child hereda de parent → origen=hijo, destino=padre)
            _generalizacion_a_xml_ea(
                pkg_owned, relacion, origen_xmi, destino_xmi
            )
        else:
            _relacion_a_xml_ea(pkg_owned, relacion, origen_xmi, destino_xmi)

    # Diagrama visual (posiciones) — opcional pero útil para que EA lo abra bien
    diagram = ET.SubElement(content, "UML:Diagram", attrib={
        "name": getattr(diagrama, "nombre", "diagrama"),
        "xmi.id": f"EAID_{getattr(diagrama, 'id', 0)}",
        "diagramType": "ClassDiagram",
        "owner": f"EAPK_{getattr(diagrama, 'id', 0)}",
        "toolName": "DevForge AI",
    })
    diagram_element = ET.SubElement(diagram, "UML:Diagram.element")
    for indice, elemento in enumerate(
        list(getattr(diagrama, "clases", []) or [])
        + list(getattr(diagrama, "interfaces", []) or []),
        start=1,
    ):
        xmi_id = id_a_xmi.get(elemento.id)
        if not xmi_id:
            continue
        left = int(elemento.pos_x or 0)
        top = int(elemento.pos_y or 0)
        ET.SubElement(diagram_element, "UML:DiagramElement", attrib={
            "geometry": f"Left={left};Top={top};Right={left + 90};Bottom={top + 70};",
            "subject": xmi_id,
            "seqno": str(indice),
        })

    # DataTypes (declarar los tipos usados)
    _declarar_datatypes_ea(pkg_owned, diagrama)

    # Indent para legibilidad
    _indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _clase_a_xml_ea(parent: ET.Element, clase: Any, xmi_id: str) -> None:
    """Genera un <UML:Class> en formato EA."""
    class_el = ET.SubElement(parent, "UML:Class", attrib={
        "name": clase.nombre,
        "xmi.id": xmi_id,
        "visibility": "public",
        "isRoot": "false",
        "isLeaf": "false",
        "isAbstract": "true" if clase.es_abstracta else "false",
        "isActive": "false",
    })

    if clase.atributos or clase.operaciones:
        feature = ET.SubElement(class_el, "UML:Classifier.feature")
        # Tanda B25: mismo filtro que el formato devforge — el duplicado
        # id+id<Clase> no viaja a Enterprise Architect.
        atributos = filtrar_identificadores_redundantes(
            list(clase.atributos),
            clase.nombre,
            extraer_nombre=lambda a: getattr(a, "nombre", ""),
        )
        for attr in atributos:
            attr_el = ET.SubElement(feature, "UML:Attribute", attrib={
                "name": attr.nombre,
                "visibility": _vis_a_xmi(attr.visibilidad),
                "changeable": "none",
                # Los estáticos viajan como classifier (convención UML)
                "ownerScope": (
                    "classifier" if getattr(attr, "es_estatico", False)
                    else "instance"
                ),
                "targetScope": "instance",
            })
            # StructuralFeature.type (referencia al DataType)
            sft = ET.SubElement(attr_el, "UML:StructuralFeature.type")
            tipo_ea = _DEVFORGE_A_EA.get(attr.tipo_dato, attr.tipo_dato or "char")
            ET.SubElement(sft, "UML:Classifier", attrib={
                "xmi.idref": f"eaxmiid_{tipo_ea}",
            })
            # TaggedValue con el tipo explícito
            tv_container = ET.SubElement(attr_el, "UML:ModelElement.taggedValue")
            ET.SubElement(tv_container, "UML:TaggedValue", attrib={
                "tag": "type", "value": tipo_ea,
            })
            ET.SubElement(tv_container, "UML:TaggedValue", attrib={
                "tag": "position", "value": str(attr.orden),
            })
            if getattr(attr, "valor_defecto", None):
                ET.SubElement(tv_container, "UML:TaggedValue", attrib={
                    "tag": "defaultValue", "value": attr.valor_defecto,
                })
        _operaciones_a_xml_ea(feature, clase)

    # Estereotipo (TaggedValue; EA ignora los que no conoce)
    if getattr(clase, "estereotipo", None):
        tv_clase = ET.SubElement(class_el, "UML:ModelElement.taggedValue")
        ET.SubElement(tv_clase, "UML:TaggedValue", attrib={
            "tag": "stereotype", "value": clase.estereotipo,
        })


def _operaciones_a_xml_ea(feature: ET.Element, clase: Any) -> None:
    """Genera los <UML:Operation> de una clase (con parámetros tipados)."""
    for op in getattr(clase, "operaciones", []) or []:
        tipo_retorno = getattr(op, "tipo_retorno", "void") or "void"
        op_el = ET.SubElement(feature, "UML:Operation", attrib={
            "name": op.nombre,
            "visibility": _vis_a_xmi(getattr(op, "visibilidad", "+")),
            "ownerScope": (
                "classifier" if getattr(op, "es_estatico", False)
                else "instance"
            ),
        })
        tv_container = ET.SubElement(op_el, "UML:ModelElement.taggedValue")
        ET.SubElement(tv_container, "UML:TaggedValue", attrib={
            "tag": "returnType",
            "value": _DEVFORGE_A_EA.get(tipo_retorno, tipo_retorno),
        })
        ET.SubElement(tv_container, "UML:TaggedValue", attrib={
            "tag": "position", "value": str(getattr(op, "orden", 0)),
        })
        params = ET.SubElement(op_el, "UML:BehavioralFeature.parameter")
        for param in getattr(op, "parametros", []) or []:
            p_tipo = _DEVFORGE_A_EA.get(param.tipo_dato, param.tipo_dato)
            p_el = ET.SubElement(params, "UML:Parameter", attrib={
                "name": param.nombre,
                "kind": "in",
            })
            p_tv = ET.SubElement(p_el, "UML:ModelElement.taggedValue")
            ET.SubElement(p_tv, "UML:TaggedValue", attrib={
                "tag": "type", "value": p_tipo,
            })


def _interfaz_a_xml_ea(
    parent: ET.Element, interfaz: Any, xmi_id: str
) -> None:
    """Genera un <UML:Interface> en formato EA (con sus operaciones)."""
    iface_el = ET.SubElement(parent, "UML:Interface", attrib={
        "name": interfaz.nombre,
        "xmi.id": xmi_id,
        "visibility": "public",
        "isRoot": "false",
        "isLeaf": "false",
        "isAbstract": "false",
    })
    if getattr(interfaz, "operaciones", None):
        feature = ET.SubElement(iface_el, "UML:Classifier.feature")
        for op in interfaz.operaciones:
            tipo_retorno = getattr(op, "tipo_retorno", "void") or "void"
            op_el = ET.SubElement(feature, "UML:Operation", attrib={
                "name": op.nombre,
                "visibility": "public",
            })
            tv = ET.SubElement(op_el, "UML:ModelElement.taggedValue")
            ET.SubElement(tv, "UML:TaggedValue", attrib={
                "tag": "returnType",
                "value": _DEVFORGE_A_EA.get(tipo_retorno, tipo_retorno),
            })


def _generalizacion_a_xml_ea(
    parent: ET.Element, relacion: Any, child_xmi: str, parent_xmi: str
) -> None:
    """
    Genera un <UML:Generalization> en formato EA.
    child hereda de parent: el ORIGEN de la relación es el hijo.
    """
    ET.SubElement(parent, "UML:Generalization", attrib={
        "xmi.id": f"EAID_gen_{relacion.id}",
        "visibility": "public",
        "isRoot": "false",
        "isLeaf": "false",
        "isAbstract": "false",
        "child": child_xmi,
        "parent": parent_xmi,
    })


def _relacion_a_xml_ea(
    parent: ET.Element, relacion: Any, origen_xmi: str, destino_xmi: str
) -> None:
    """
    Genera un <UML:Association> en formato EA.

    Las generalizaciones NO pasan por aquí (van como
    <UML:Generalization>); DEPENDENCIA y REALIZACION viajan como
    Association + TaggedValue "tipo_relacion" para que el round-trip
    no las degrade a asociación.
    """
    xmi_id = f"EAID_rel_{relacion.id}"

    assoc = ET.SubElement(parent, "UML:Association", attrib={
        "xmi.id": xmi_id,
        "visibility": "public",
        "isRoot": "false",
        "isLeaf": "false",
        "isAbstract": "false",
    })

    tv_container = ET.SubElement(assoc, "UML:ModelElement.taggedValue")
    ET.SubElement(tv_container, "UML:TaggedValue", attrib={"tag": "ea_type", "value": "Association"})
    if relacion.tipo_relacion in ("DEPENDENCIA", "REALIZACION"):
        ET.SubElement(tv_container, "UML:TaggedValue", attrib={
            "tag": "tipo_relacion", "value": relacion.tipo_relacion,
        })
    if getattr(relacion, "nombre_asociacion", None):
        ET.SubElement(tv_container, "UML:TaggedValue", attrib={
            "tag": "name", "value": relacion.nombre_asociacion,
        })
    if relacion.multiplicidad_origen:
        ET.SubElement(tv_container, "UML:TaggedValue", attrib={"tag": "lb", "value": relacion.multiplicidad_origen})
    if relacion.multiplicidad_destino:
        ET.SubElement(tv_container, "UML:TaggedValue", attrib={"tag": "rb", "value": relacion.multiplicidad_destino})

    # Association.connection con dos AssociationEnd. La multiplicidad
    # es OPCIONAL en el DTD de UML 1.1: si la relación no la define no
    # se rellena con "1" (el round-trip conserva el None; en el Ciclo 1
    # el default "1" fabricaba multiplicidades en DEPENDENCIA/REALIZACION).
    conn = ET.SubElement(assoc, "UML:Association.connection")
    agg_origen = "composite" if relacion.tipo_relacion == "COMPOSICION" else (
        "aggregate" if relacion.tipo_relacion == "AGREGACION" else "none"
    )
    end_origen_atrs = {
        "visibility": "public",
        "aggregation": agg_origen,
        "isOrdered": "false",
        "targetScope": "instance",
        "changeable": "none",
        "isNavigable": "true",
        "type": origen_xmi,
    }
    if relacion.multiplicidad_origen:
        end_origen_atrs["multiplicity"] = relacion.multiplicidad_origen
    if getattr(relacion, "rol_origen", None):
        # En UML 1.3 el nombre del extremo es el rol
        end_origen_atrs["name"] = relacion.rol_origen
    ET.SubElement(conn, "UML:AssociationEnd", attrib=end_origen_atrs)

    end_destino_atrs = {
        "visibility": "public",
        "aggregation": "none",
        "isOrdered": "false",
        "targetScope": "instance",
        "changeable": "none",
        "isNavigable": "true",
        "type": destino_xmi,
    }
    if relacion.multiplicidad_destino:
        end_destino_atrs["multiplicity"] = relacion.multiplicidad_destino
    if getattr(relacion, "rol_destino", None):
        end_destino_atrs["name"] = relacion.rol_destino
    ET.SubElement(conn, "UML:AssociationEnd", attrib=end_destino_atrs)


def _declarar_datatypes_ea(parent: ET.Element, diagrama: Any) -> None:
    """Declara los <UML:DataType> para todos los tipos usados
    (atributos, tipos de retorno no-void y parámetros; los tipos
    desconocidos se declaran con su nombre tal cual para que el
    xmi.idref de los atributos resuelva)."""
    tipos_usados: set[str] = set()
    for clase in getattr(diagrama, "clases", []) or []:
        for attr in getattr(clase, "atributos", []) or []:
            tipos_usados.add(_DEVFORGE_A_EA.get(attr.tipo_dato, attr.tipo_dato or "char"))
        for op in getattr(clase, "operaciones", []) or []:
            tipo_retorno = getattr(op, "tipo_retorno", "void") or "void"
            if tipo_retorno != "void":
                tipos_usados.add(_DEVFORGE_A_EA.get(tipo_retorno, tipo_retorno))
            for param in getattr(op, "parametros", []) or []:
                tipos_usados.add(_DEVFORGE_A_EA.get(param.tipo_dato, param.tipo_dato))
    for tipo in sorted(tipos_usados):
        ET.SubElement(parent, "UML:DataType", attrib={
            "xmi.id": f"eaxmiid_{tipo}",
            "name": tipo,
            "visibility": "private",
            "isRoot": "false",
            "isLeaf": "false",
            "isAbstract": "false",
        })
