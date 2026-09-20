# app/ai_vision/__init__.py
"""
Módulo de IA de visión: reconocimiento de bocetos/imágenes de diagramas
de clases y reconstrucción como elementos editables.

- sketch_recognition: detecta cajas, líneas y texto en la imagen.
- uml_reconstructor: reconstruye clases, atributos, operaciones y relaciones
  a partir de lo detectado.
- vision_service: orquesta el pipeline completo.

Este módulo corre del lado del BACKEND (requiere más cómputo que el
reconocimiento de voz offline, que vive en el dispositivo móvil).
"""

from app.ai_vision.vision_service import VisionService

__all__ = ["VisionService"]