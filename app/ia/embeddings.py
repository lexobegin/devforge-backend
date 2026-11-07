# app/ia/embeddings.py
"""
Servicio de EMBEDDINGS del módulo G — CICLO 2 (CU17, contexto persistente).

NUEVO en el Ciclo 2. El gestor de contexto (gestor_contexto_service, en su
tanda) necesita encontrar en el historial los mensajes RELEVANTES para el
turno actual, aunque no estén en la ventana inmediata. Para eso:
1. incrusta la consulta y los candidatos con el modelo de embeddings
   (OLLAMA_MODEL_EMBEDDINGS = 'nomic-embed-text' en Ollama),
2. los ordena por similitud coseno,
3. devuelve el top-k al ensamblador de contexto.

Decisiones de diseño:
- CONMUTACIÓN: recorre la cadena de proveedores (LlmProvider) y usa el
  primero que responda. Si NINGUNO responde lanza IAIndisponibleError
  (el service decide si el turno falla o se responde sin contexto
  semántico).
- CACHE en memoria (LRU, tam_cache entradas): en un mismo turno el
  gestor incrusta la consulta y cada candidato; sin cache, cada reenvío
  del mismo texto golpea el motor otra vez. La cache vive con el proceso
  (como los embeddings del motor no cambian entre llamadas, es segura).
- SIMILITUD coseno con math puro (sin numpy): los vectores son ~768
  dimensiones y el volumen del historial es chico; así la capa IA no
  arrastra numpy al runtime de la VM si no hace falta.
- SIN base de datos: el gestor de contexto (services) persiste lo que
  quiera en ContextoIA; este servicio solo calcula y ordena.
"""

import math
from collections import OrderedDict
from typing import List, Optional, Tuple

from app.ia.llm_provider import (
    ErrorIA,
    IAIndisponibleError,
    LlmProvider,
    RespuestaEmbeddingsIA,
)

# Par de valores mínimos aceptables para considerar válido un vector
_DIM_MINIMA = 2


# ======================================================================
# Similitud coseno (función pura, sin estado)
# ======================================================================
def similitud_coseno(a: List[float], b: List[float]) -> float:
    """
    Similitud coseno entre dos vectores: (a·b) / (|a|·|b|).

    Devuelve un float en [-1, 1]. Por convención:
    - vectores de distinta dimensión → ErrorIA (es un bug del llamador),
    - vector nulo → 0.0 (no aporta información de dirección).
    """
    if len(a) != len(b):
        raise ErrorIA(
            f"Vectores de distinta dimensión al comparar embeddings "
            f"({len(a)} vs {len(b)})"
        )
    producto = sum(x * y for x, y in zip(a, b))
    norma_a = math.sqrt(sum(x * x for x in a))
    norma_b = math.sqrt(sum(y * y for y in b))
    if norma_a == 0.0 or norma_b == 0.0:
        return 0.0
    return producto / (norma_a * norma_b)


# ======================================================================
# Servicio de embeddings con conmutación + cache LRU
# ======================================================================
class ServicioEmbeddings:
    """
    Fachada de embeddings para los services del módulo G.

    - cadena: proveedores en orden de conmutación (construir_cadena()).
    - modelo_defecto: modelo de embeddings a pedir (por defecto el de
      Ollama; los respaldos lo traducen al suyo si hace falta).
    """

    def __init__(
        self,
        cadena: List[LlmProvider],
        modelo_defecto: Optional[str] = None,
        tam_cache: int = 512,
    ):
        if not cadena:
            raise ErrorIA(
                "ServicioEmbeddings necesita al menos un proveedor en la cadena"
            )
        self.cadena = cadena
        self.modelo_defecto = modelo_defecto or self.cadena[0].modelo_embeddings
        self._cache: "OrderedDict[str, List[float]]" = OrderedDict()
        self._tam_cache = max(1, tam_cache)

    # ------------------------------------------------------------------
    # Cache LRU en memoria (por modelo+texto)
    # ------------------------------------------------------------------
    def _clave_cache(self, texto: str, modelo: str) -> str:
        return f"{modelo}::{texto}"

    def _guardar_cache(self, clave: str, vector: List[float]) -> None:
        self._cache[clave] = vector
        self._cache.move_to_end(key=clave)
        while len(self._cache) > self._tam_cache:
            self._cache.popitem(last=False)  # evicta el más viejo

    # ------------------------------------------------------------------
    # Incrustar un texto (con conmutación de proveedor)
    # ------------------------------------------------------------------
    async def incrustar(self, texto: str, modelo: Optional[str] = None) -> List[float]:
        """
        Vector del texto pedido. Conmuta por la cadena y cachea el
        resultado. Lanza IAIndisponibleError si ningún proveedor responde.
        """
        if not texto or not texto.strip():
            raise ErrorIA("No se puede calcular el embedding de un texto vacío")
        modelo = modelo or self.modelo_defecto
        clave = self._clave_cache(texto, modelo)

        en_cache = self._cache.get(clave)
        if en_cache is not None:
            self._cache.move_to_end(key=clave)
            return en_cache

        ultimo_error: Optional[Exception] = None
        for proveedor in self.cadena:
            try:
                respuesta: RespuestaEmbeddingsIA = await proveedor.incrustar(
                    texto, modelo=modelo
                )
                vector = respuesta.vector
                if len(vector) < _DIM_MINIMA:
                    # Un vector degenerado es un problema del motor, no
                    # de la red: no tiene sentido conmutar por él.
                    raise ErrorIA(
                        f"El proveedor '{proveedor.nombre}' devolvió un vector "
                        f"degenerado (dimensión {len(vector)})"
                    )
                self._guardar_cache(clave, vector)
                return vector
            except IAIndisponibleError as exc:
                ultimo_error = exc   # conmutar: intentar el siguiente
                continue

        raise IAIndisponibleError(
            f"Ningún proveedor de embeddings respondió "
            f"(cadena: {[p.nombre for p in self.cadena]}); "
            f"última falla: {ultimo_error}"
        )

    # ------------------------------------------------------------------
    # Recuperación semántica para el gestor de contexto (CU17)
    # ------------------------------------------------------------------
    async def recuperar_relevantes(
        self,
        consulta: str,
        candidatos: List[str],
        k: int = 5,
    ) -> List[Tuple[int, float]]:
        """
        Devuelve los candidatos más relevantes para la consulta:
        lista de (indice_en_candidatos, similitud) ordenada por similitud
        DESCENDENTE, con k elementos como máximo.

        Los candidatos vacíos se descartan sin gastar una llamada al motor
        (su índice queda excluido del resultado).
        """
        if not candidatos:
            return []
        if k <= 0:
            return []

        vector_consulta = await self.incrustar(consulta)

        # Incrusta cada candidato (el cache evita repetir llamadas si un
        # mismo texto aparece en turnos consecutivos)
        puntuadas: List[Tuple[int, float]] = []
        for indice, texto in enumerate(candidatos):
            if not texto or not texto.strip():
                continue
            vector = await self.incrustar(texto)
            puntuadas.append((indice, similitud_coseno(vector_consulta, vector)))

        puntuadas.sort(key=lambda par: par[1], reverse=True)
        return puntuadas[:k]