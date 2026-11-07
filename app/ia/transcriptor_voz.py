# app/ia/transcriptor_voz.py
"""
Transcripción de VOZ local con faster-whisper — CICLO 2 (CU16).

NUEVO en el Ciclo 2: en el Ciclo 1 el audio se mandaba a un servicio online.
Ahora la transcripción corre en la propia VM (sección VOZ_* del config),
gratis y sin enviar el audio del usuario a terceros:
- VOZ_ENABLED         interruptor general (False → ErrorIA, no silencio),
- VOZ_MODELO_WHISPER  'base' en desarrollo, 'small' en producción,
- VOZ_IDIOMA          'es' por defecto (None = autodetección).

Decisiones de diseño:
- CARGA PEREZOSA: el modelo Whisper se instancia en la PRIMERA
  transcripción (no en el import ni en el arranque de la app): es pesado
  y las pruebas unitarias / la importación del paquete no deben pagar
  ese costo. Además el import de faster_whisper es DIFERIDO dentro del
  método: si la librería no está instalada, el resto del módulo IA
  sigue importando bien y el error sale recién al intentar transcribir.
- BLOQUEANTE → EXECUTOR: faster-whisper es síncrono y tarda segundos;
  se corre en un hilo del executor para no bloquear el event loop
  (los otros endpoints y el WebSocket seguirían congelados si no).
- Salida alineada con TranscripcionVozResponse (schemas del canal):
  texto_transcrito, motor, idioma_detectado, duracion_audio_seg,
  tiempo_transcripcion_seg. El service de canal solo copia campos.
- Sin base de datos y sin negocio: devolver el texto; el mensaje VOZ lo
  persiste canal_service como MensajeChat(origen='VOZ').
"""

import asyncio
import io
import time
from dataclasses import dataclass
from typing import Optional

from app.config import Settings
from app.ia.llm_provider import ErrorIA, settings_global

# Motor reportado en la salida (el schema espera 'faster-whisper' o el
# modelo concretado: 'faster-whisper:base')
_MOTOR_BASE = "faster-whisper"


# ======================================================================
# Resultado de la transcripción (dataclass interna de la capa IA)
# ======================================================================
@dataclass
class Transcripcion:
    """Audio transcrito, con metadatos para TranscripcionVozResponse."""

    texto: str
    idioma_detectado: Optional[str]
    duracion_audio_seg: Optional[float]
    tiempo_procesamiento_seg: Optional[float]
    motor: str


# ======================================================================
# Servicio
# ======================================================================
class ServicioTranscripcion:
    """
    Fachada de transcripción de voz (local, faster-whisper).

    Uso previsto (canal_service, T15):
        transcripcion = await self.transcriptor.transcribir(audio_bytes)
        if transcripcion.texto: ... crear MensajeChat(origen='VOZ')
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or settings_global()
        self._modelo = None  # carga perezosa (primera llamada)

    # ------------------------------------------------------------------
    # Carga perezosa del modelo Whisper
    # ------------------------------------------------------------------
    def _obtener_modelo(self):
        """
        Instancia (una sola vez) el WhisperModel. Lanza ErrorIA si
        faster-whisper no está instalado en la VM.
        """
        if not self.settings.VOZ_ENABLED:
            raise ErrorIA(
                "La transcripción de voz está deshabilitada (VOZ_ENABLED=false)"
            )
        if self._modelo is None:
            try:
                # Import DIFERIDO: no penaliza el arranque ni las pruebas
                # que no usan voz, y da un error claro si falta la librería.
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ErrorIA(
                    "faster-whisper no está disponible en el servidor "
                    "(instale la dependencia o desactive VOZ_ENABLED)"
                ) from exc
            # int8 en CPU: buena relación velocidad/precisión para base/small
            self._modelo = WhisperModel(
                self.settings.VOZ_MODELO_WHISPER,
                device="cpu",
                compute_type="int8",
            )
        return self._modelo

    # ------------------------------------------------------------------
    # Transcripción síncrona (corre en el executor)
    # ------------------------------------------------------------------
    def _transcribir_sync(self, bytes_audio: bytes) -> Transcripcion:
        """Trabajo bloqueante de faster-whisper (hilo del executor)."""
        inicio = time.monotonic()
        modelo = self._obtener_modelo()

        buffer = io.BytesIO(bytes_audio)
        # language=None → autodetección; VOZ_IDIOMA fija el idioma esperado
        idioma_cfg: Optional[str] = self.settings.VOZ_IDIOMA or None
        segmentos, info = modelo.transcribe(
            buffer,
            language=idioma_cfg,
            vad_filter=True,           # recorta silencios (audio de micrófono)
            beam_size=5,
        )

        # Generadores perezosos: hay que consumirlos para obtener el texto
        partes = [seg.text.strip() for seg in segmentos]
        texto = " ".join(p for p in partes if p).strip()

        tiempo = round(time.monotonic() - inicio, 3)
        if not texto:
            raise ErrorIA(
                "No se pudo transcribir el audio: la salida quedó vacía "
                "(¿silencio o formato de audio no soportado?)"
            )

        return Transcripcion(
            texto=texto,
            idioma_detectado=getattr(info, "language", None),
            duracion_audio_seg=round(float(getattr(info, "duration", 0.0) or 0.0), 3),
            tiempo_procesamiento_seg=tiempo,
            motor=f"{_MOTOR_BASE}:{self.settings.VOZ_MODELO_WHISPER}",
        )

    # ------------------------------------------------------------------
    # API async para los services
    # ------------------------------------------------------------------
    async def transcribir(self, bytes_audio: bytes) -> Transcripcion:
        """
        Transcribe un archivo de audio (bytes) con faster-whisper local.
        Corre en el executor para no bloquear el event loop.

        Contrato de errores: audio vacío / voz deshabilitada / librería
        ausente / salida vacía lanzan ErrorIA con su mensaje específico;
        cualquier otra falla del motor (audio corrupto, formato no
        soportado, modelo dañado) se ENVUELVE en ErrorIA para que el
        canal responda con un error de dominio y no un 500 crudo.
        """
        if not bytes_audio:
            raise ErrorIA("No se recibió audio para transcribir (cuerpo vacío)")
        # VOZ_ENABLED se valida en _obtener_modelo, pero fallar ANTES de
        # encolar el executor es más barato y da el mismo mensaje.
        if not self.settings.VOZ_ENABLED:
            raise ErrorIA(
                "La transcripción de voz está deshabilitada (VOZ_ENABLED=false)"
            )
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, self._transcribir_sync, bytes_audio
            )
        except ErrorIA:
            raise  # los casos conocidos conservan su mensaje exacto
        except Exception as exc:  # noqa: BLE001  (audio corrupto, modelo, etc.)
            raise ErrorIA(
                f"No se pudo transcribir el audio "
                f"({type(exc).__name__}): {exc}"
            ) from exc