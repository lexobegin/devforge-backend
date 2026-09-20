# app/ai_vision/sketch_recognition.py
"""
Detección de elementos visuales en un boceto de diagrama de clases.

Pipeline:
1. Carga la imagen (bytes) y la convierte a escala de grises.
2. Umbraliza (threshold) para separar trazos de fondo.
3. Detecta contornos/rectángulos → candidatos a cajas de clase.
4. Filtra cajas por tamaño mínimo (evita ruido).
5. Para cada caja, recorta la región y aplica detección de texto (OCR).
6. Detecta líneas largas (relaciones) entre cajas.

Dependencias:
- Pillow (PIL)          → manipulación de imagen.
- OpenCV (cv2)          → contornos, Hough lines, threshold.
- pytesseract           → OCR (requiere tesseract instalado en el sistema).

Si alguna dependencia no está disponible, el módulo degrada con un
mensaje claro en lugar de romper el servidor.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("devforge.ai_vision")


# ======================================================================
# Estructuras de salida
# ======================================================================
@dataclass
class BoundingBox:
    """Caja detectada en la imagen."""

    x: int
    y: int
    ancho: int
    alto: int

    @property
    def area(self) -> int:
        return self.ancho * self.alto

    @property
    def centro(self) -> tuple[int, int]:
        return (self.x + self.ancho // 2, self.y + self.alto // 2)


@dataclass
class CajaDetectada:
    """Caja de clase con su texto OCR crudo (líneas)."""

    box: BoundingBox
    lineas_texto: list[str] = field(default_factory=list)

    @property
    def texto_completo(self) -> str:
        return "\n".join(self.lineas_texto)


@dataclass
class LineaDetectada:
    """Línea detectada (candidata a relación entre dos cajas)."""

    x1: int
    y1: int
    x2: int
    y2: int

    def extremos(self) -> tuple[tuple[int, int], tuple[int, int]]:
        return ((self.x1, self.y1), (self.x2, self.y2))


@dataclass
class ResultadoReconocimiento:
    """Resultado crudo del paso de detección (antes de reconstruir UML)."""

    cajas: list[CajaDetectada] = field(default_factory=list)
    lineas: list[LineaDetectada] = field(default_factory=list)
    ancho_imagen: int = 0
    alto_imagen: int = 0
    advertencias: list[str] = field(default_factory=list)


# ======================================================================
# Detector
# ======================================================================
class SketchRecognizer:
    """
    Detector de elementos visuales en un boceto de diagrama.

    Los umbrales son heurísticos y configurables. Se pueden afinar sin
    reescribir la lógica de reconstrucción UML.
    """

    # Tamaños mínimos para que una caja sea considerada "clase"
    AREA_MINIMA_CAJA = 2000          # px²
    LADO_MINIMO_CAJA = 40            # px
    # Tamaño máximo razonable (evita el borde de la imagen completa)
    FRACCION_MAXIMA_ANCHO = 0.9
    FRACCION_MAXIMA_ALTO = 0.9

    def __init__(self) -> None:
        self._cv2: Optional[Any] = None
        self._np: Optional[Any] = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def detectar(
        self, imagen_bytes: bytes, *, idioma: str = "es"
    ) -> ResultadoReconocimiento:
        """
        Ejecuta el pipeline de detección sobre la imagen.
        Devuelve un `ResultadoReconocimiento` con cajas y líneas.
        """
        advertencias: list[str] = []

        # 1) Cargar dependencias de visión
        if not self._cargar_dependencias():
            raise RuntimeError(
                "El módulo de visión requiere OpenCV y NumPy. "
                "Instale: pip install opencv-python-headless numpy pillow"
            )

        # 2) Decodificar imagen
        img = self._decodificar_imagen(imagen_bytes)
        if img is None:
            raise ValueError("No se pudo decodificar la imagen (formato inválido)")

        alto, ancho = img.shape[:2]
        resultado = ResultadoReconocimiento(
            ancho_imagen=ancho,
            alto_imagen=alto,
            advertencias=advertencias,
        )

        # 3) Preprocesar
        gris = self._cv2.cvtColor(img, self._cv2.COLOR_BGR2GRAY)
        binaria = self._cv2.adaptiveThreshold(
            gris,
            255,
            self._cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            self._cv2.THRESH_BINARY_INV,
            15,
            10,
        )

        # 4) Detectar cajas
        cajas = self._detectar_cajas(binaria, ancho, alto)
        if not cajas:
            advertencias.append(
                "No se detectaron cajas de clase en la imagen. "
                "Pruebe con una imagen más nítida o con contraste."
            )
            return resultado

        # 5) OCR por caja
        for caja in cajas:
            caja.lineas_texto = self._ocr_region(
                gris, caja.box, idioma=idioma
            )

        resultado.cajas = cajas

        # 6) Detectar líneas (relaciones)
        resultado.lineas = self._detectar_lineas(binaria, cajas)

        return resultado

    # ------------------------------------------------------------------
    # Carga de dependencias
    # ------------------------------------------------------------------
    def _cargar_dependencias(self) -> bool:
        if self._cv2 is not None and self._np is not None:
            return True
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore

            self._cv2 = cv2
            self._np = np
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Decodificación
    # ------------------------------------------------------------------
    def _decodificar_imagen(self, imagen_bytes: bytes) -> Optional[Any]:
        try:
            import numpy as np

            arr = np.frombuffer(imagen_bytes, dtype=np.uint8)
            img = self._cv2.imdecode(arr, self._cv2.IMREAD_COLOR)
            return img
        except Exception as exc:
            logger.warning("Error decodificando imagen: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Detección de cajas
    # ------------------------------------------------------------------
    def _detectar_cajas(
        self, binaria: Any, ancho: int, alto: int
    ) -> list[CajaDetectada]:
        # Dilatar para unir trazos y cerrar contornos
        kernel = self._cv2.getStructuringElement(
            self._cv2.MORPH_RECT, (3, 3)
        )
        dilatada = self._cv2.dilate(binaria, kernel, iterations=2)

        contornos, _ = self._cv2.findContours(
            dilatada, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE
        )

        cajas: list[CajaDetectada] = []
        ancho_max = int(ancho * self.FRACCION_MAXIMA_ANCHO)
        alto_max = int(alto * self.FRACCION_MAXIMA_ALTO)

        for c in contornos:
            x, y, w, h = self._cv2.boundingRect(c)

            # Filtrar por tamaño mínimo
            if w < self.LADO_MINIMO_CAJA or h < self.LADO_MINIMO_CAJA:
                continue
            if w * h < self.AREA_MINIMA_CAJA:
                continue
            # Filtrar si ocupa casi toda la imagen (borde exterior)
            if w >= ancho_max and h >= alto_max:
                continue

            cajas.append(CajaDetectada(box=BoundingBox(x=x, y=y, ancho=w, alto=h)))

        # Orden de lectura: por fila (y) y luego por columna (x)
        cajas.sort(key=lambda c: (c.box.y // 50, c.box.x))
        return cajas

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------
    def _ocr_region(
        self, gris: Any, box: BoundingBox, *, idioma: str
    ) -> list[str]:
        """
        Aplica OCR a la región de la caja. Devuelve las líneas de texto
        no vacías. Si pytesseract no está disponible, devuelve lista vacía.
        """
        try:
            import pytesseract  # type: ignore
        except ImportError:
            logger.info("pytesseract no disponible; se omite OCR")
            return []

        # Recorte con un pequeño padding para no cortar texto pegado al borde
        pad = 3
        y1 = max(0, box.y + pad)
        y2 = box.y + box.alto - pad
        x1 = max(0, box.x + pad)
        x2 = box.x + box.ancho - pad

        recorte = gris[y1:y2, x1:x2]
        if recorte.size == 0:
            return []

        # Binarizar para mejorar OCR
        try:
            _, rec_bin = self._cv2.threshold(
                recorte, 0, 255, self._cv2.THRESH_BINARY + self._cv2.THRESH_OTSU
            )
        except Exception:
            rec_bin = recorte

        try:
            texto = pytesseract.image_to_string(
                rec_bin, lang=idioma or "spa"
            )
        except Exception as exc:
            logger.debug("Error OCR: %s", exc)
            return []

        lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
        return lineas

    # ------------------------------------------------------------------
    # Detección de líneas
    # ------------------------------------------------------------------
    def _detectar_lineas(
        self, binaria: Any, cajas: list[CajaDetectada]
    ) -> list[LineaDetectada]:
        """
        Detecta segmentos largos (candidatos a relaciones) usando
        HoughLinesP. Filtra líneas cortas o dentro de cajas.
        """
        try:
            lineas_cv = self._cv2.HoughLinesP(
                binaria,
                rho=1,
                theta=3.14159 / 180,
                threshold=80,
                minLineLength=60,
                maxLineGap=10,
            )
        except Exception as exc:
            logger.debug("HoughLinesP falló: %s", exc)
            return []

        if lineas_cv is None:
            return []

        resultado: list[LineaDetectada] = []
        for l in lineas_cv:
            x1, y1, x2, y2 = l[0]
            # Ignorar líneas cortas
            if abs(x2 - x1) + abs(y2 - y1) < 60:
                continue
            # Ignorar si ambos extremos caen dentro de la misma caja
            if self._ambos_extremos_en_misma_caja((x1, y1), (x2, y2), cajas):
                continue
            resultado.append(LineaDetectada(x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2)))

        return resultado

    @staticmethod
    def _ambos_extremos_en_misma_caja(
        p1: tuple[int, int],
        p2: tuple[int, int],
        cajas: list[CajaDetectada],
    ) -> bool:
        caja1 = _caja_que_contiene(p1, cajas)
        caja2 = _caja_que_contiene(p2, cajas)
        return caja1 is not None and caja1 is caja2


# ----------------------------------------------------------------------
# Helper a nivel módulo (usado por otros archivos)
# ----------------------------------------------------------------------
def _caja_que_contiene(
    punto: tuple[int, int], cajas: list[CajaDetectada]
) -> Optional[CajaDetectada]:
    x, y = punto
    for c in cajas:
        b = c.box
        if b.x <= x <= b.x + b.ancho and b.y <= y <= b.y + b.alto:
            return c
    return None