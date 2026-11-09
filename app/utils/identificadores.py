# app/utils/identificadores.py
"""
Normalización de IDENTIFICADORES redundantes (Tanda B25) — parte no-OCR
del punto 3 del reporte de pruebas del 2026-11-07.

SÍNTOMA: una clase `Producto` con atributos `id` + `idproducto` (muy
común en bocetos: la IA de visión y el Agente Dev a veces agregan `id`
"por convención" aunque el boceto ya traiga `idproducto`, y el usuario
también puede dibujarlos juntos) llega al export XMI/EA y al generador
de código con DOS identificadores: la PK sintética/`id` y el atributo
`idproducto` como columna más → entidad con doble identificador
(`id` + `idproducto`).

REGLA (conservadora, para no destruir modelos válidos):
1. Solo hay redundancia si la clase tiene el atributo literal `id`
   (cualquier caso). Sin `id` explícito NO se toca nada: el generador
   sintetiza su PK y `idproducto` queda como atributo de negocio.
2. Se descartan atributos cuyo nombre sea `id` + el nombre de la CLASE
   en cualquiera de sus formas habituales: `idproducto`, `id_producto`,
   `id producto`, `idProducto`, `IDProducto`, `IdProducto`…
   - `Producto` + `id` + `idproveedor` → NO se toca (¡es una FK a
     Proveedor, no un identificador de Producto!).
   - `OrdenDetalle` + `id` + `id_ordendetalle` → se descarta el segundo.
3. El literal `id` jamás se descarta: es la PK que el generador usa.

Puntos de aplicación (defensa en profundidad, cada capa es autónoma):
- uml_reconstructor.reconstruir      → boceto/IA de visión (dicts)
- diagrama_service.crear_clase       → REST CRUD (y el cliente de visión)
- ejecutor_acciones._op_crear_clase  → Agente Dev (canal)
- code_generator.mapping_engine      → generación Spring/React (objetos)
- utils.xmi_converter._clase_a_xml   → export XMI/EA (objetos)

Las dos últimas cubren diagramas VIEJOS que ya guardaron el duplicado.
"""

import re
from typing import Any, Iterable


def _normalizar(texto: str) -> str:
    """Minúsculas y sin separadores: `id_Producto` → `idproducto`."""
    return re.sub(r"[ _\-]+", "", texto).lower()


def es_identificador_redundante(
    nombre_atributo: str, nombre_clase: str
) -> bool:
    """
    True SOLO si `nombre_atributo` es `id` + nombre de la clase
    (ej. clase `Producto`, atributo `idproducto`/`id_producto`/
    `idProducto`). El literal `id` NO es redundante (es la PK).
    """
    atributo = _normalizar(nombre_atributo)
    clase = _normalizar(nombre_clase)
    if not atributo or not clase or atributo == "id":
        return False
    return atributo == f"id{clase}"


def hay_id_literal(nombres_atributos: Iterable[str]) -> bool:
    """¿Alguno de los nombres es `id` (cualquier caso)?"""
    return any(
        _normalizar(n) == "id" for n in nombres_atributos if n
    )


def filtrar_identificadores_redundantes(
    items: list[Any],
    nombre_clase: str,
    *,
    extraer_nombre,
) -> list[Any]:
    """
    Filtra una lista de atributos (dicts, modelos Pydantic u objetos)
    aplicando la regla. `extraer_nombre(item)` devuelve el nombre del
    atributo. Devuelve una NUEVA lista; los duplicados se omiten.

    Si la clase no tiene `id` literal, devuelve la lista intacta
    (misma referencia) para no copiar en vano.
    """
    if not hay_id_literal(
        extraer_nombre(i) for i in items if i is not None
    ):
        return items
    return [
        item
        for item in items
        if item is None
        or not es_identificador_redundante(
            extraer_nombre(item), nombre_clase
        )
    ]
