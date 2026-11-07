# scripts/verificar_ollama.py
"""
Verificador de Ollama para DevForge AI — CICLO 2.

Comprueba, en este orden:
  1. Que el servidor Ollama responde (GET /api/tags).
  2. Que los 3 modelos del Ciclo 2 están descargados (los lee del .env):
       OLLAMA_MODEL_TEXT       (qwen2.5:7b)          → Agente Dev (CU16-CU21)
       OLLAMA_MODEL_LIGERO     (llama3.2:3b)         → Asistente Guía (CU23)
       OLLAMA_MODEL_EMBEDDINGS (nomic-embed-text)    → contexto persistente (CU17)
  3. (opcional) POST /api/embeddings con el modelo de embeddings.
  4. (opcional) POST /api/chat con el modelo de texto (prueba mínima).

Es STANDALONE: no importa app.config ni la BD; solo httpx (ya está en
requirements.txt) y la librería estándar. Se puede correr ANTES de tener
el backend funcionando, justo después de instalar Ollama y bajar modelos.

Uso:
    python scripts/verificar_ollama.py                 # verificación completa
    python scripts/verificar_ollama.py --sin-pruebas   # solo servidor + modelos
    python scripts/verificar_ollama.py --base-url http://127.0.0.1:11434
    python scripts/verificar_ollama.py --env .env.produccion

Salida: líneas [OK]/[FAIL] + resumen; exit code 0 si todo OK, 1 si algo falló.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("[FAIL] Falta httpx: instala requirements.txt (pip install -r requirements.txt)")
    sys.exit(1)

# ----------------------------------------------------------------------
# Defaults (espejan app/config.py — Ciclo 2)
# ----------------------------------------------------------------------
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODELS = {
    "OLLAMA_MODEL_TEXT": "qwen2.5:7b",
    "OLLAMA_MODEL_LIGERO": "llama3.2:3b",
    "OLLAMA_MODEL_EMBEDDINGS": "nomic-embed-text",
}
TIMEOUT_TAGS = 10.0        # /api/tags
TIMEOUT_EMBED = 60.0       # /api/embeddings
TIMEOUT_CHAT = 120.0       # /api/chat (el primer call puede cargar el modelo)


def cargar_env(ruta: Path) -> dict:
    """Parser mínimo de .env: KEY=VALUE, ignora # comentarios y líneas vacías.

    Soporta comentarios al final de la línea (OLLAMA_MODEL_TEXT=qwen2.5:7b  # x)
    y valores con la forma "clave" sin comillas.
    """
    valores: dict = {}
    if not ruta.is_file():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip()
        # quitar comentario inline solo si hay espacio antes del # (los
        # valores no llevan # legítimo: URLs, nombres de modelo, etc.)
        if " #" in valor:
            valor = valor.split(" #", 1)[0].strip()
        valores[clave] = valor
    return valores


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica Ollama para DevForge AI (Ciclo 2)")
    parser.add_argument("--base-url", default=None, help="URL de Ollama (default: OLLAMA_BASE_URL del .env o %(default)s)")
    parser.add_argument("--env", default=".env", help="archivo .env a leer (default: %(default)s)")
    parser.add_argument("--sin-pruebas", action="store_true", help="no ejecutar las pruebas de embeddings ni chat")
    args = parser.parse_args()

    env = cargar_env(Path(args.env))
    base_url = (
        args.base_url
        or env.get("OLLAMA_BASE_URL", "").strip()
        or DEFAULT_BASE_URL
    ).rstrip("/")
    modelos = {k: env.get(k, "").strip() or v for k, v in DEFAULT_MODELS.items()}

    print("=" * 60)
    print("DevForge AI — verificación de Ollama (Ciclo 2)")
    print(f"  base-url : {base_url}")
    print(f"  .env     : {args.env} {'(encontrado)' if env else '(no encontrado; usando defaults)'}")
    print(f"  modelos  : {modelos['OLLAMA_MODEL_TEXT']}, {modelos['OLLAMA_MODEL_LIGERO']}, {modelos['OLLAMA_MODEL_EMBEDDINGS']}")
    print("=" * 60)

    ok_total = 0
    fail_total = 0

    def marcar(bien: bool, texto_ok: str, texto_fail: str) -> bool:
        nonlocal ok_total, fail_total
        print(f"[{'OK' if bien else 'FAIL'}] {texto_ok if bien else texto_fail}")
        if bien:
            ok_total += 1
        else:
            fail_total += 1
        return bien

    # ------------------------------------------------------------------
    # 1) Servidor arriba
    # ------------------------------------------------------------------
    descargados: list = []
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=TIMEOUT_TAGS)
        r.raise_for_status()
        data = r.json()
        descargados = [m.get("name", "") for m in data.get("models", [])]
        marcar(True, f"Servidor Ollama responde: {len(descargados)} modelo(s) descargado(s)", "Servidor Ollama no respondió correctamente")
    except Exception as e:  # noqa: BLE001 — el verificador reporta cualquier error
        marcar(False, "", f"Servidor Ollama inaccesible en {base_url}: {e}")
        print("\nResumen: 0 OK / 1 FAIL")
        print("¿Está corriendo?  → systemctl status ollama  |  ollama serve")
        return 1

    # ------------------------------------------------------------------
    # 2) Modelos requeridos por el Ciclo 2
    # ------------------------------------------------------------------
    for clave, nombre in modelos.items():
        # Ollama lista 'name' como 'modelo:tag' (qwen2.5:7b:latest). El nombre
        # del modelo TAMBIÉN lleva ':' (qwen2.5:7b), así que la etiqueta se
        # recorta por la DERECHA (rsplit) o se acepta la coincidencia exacta.
        def base(d: str) -> str:
            return d[: -len(":latest")] if d.endswith(":latest") else d

        presente = any(d == nombre or base(d) == nombre for d in descargados)
        marcar(
            presente,
            f"{clave}: '{nombre}' está descargado",
            f"{clave}: '{nombre}' NO está descargado → ejecuta: ollama pull {nombre}",
        )

    if not args.sin_pruebas:

        # --------------------------------------------------------------
        # 3) Embeddings (CU17 — contexto persistente)
        # --------------------------------------------------------------
        try:
            r = httpx.post(
                f"{base_url}/api/embeddings",
                json={"model": modelos["OLLAMA_MODEL_EMBEDDINGS"], "prompt": "clase Estudiante con atributo nombre"},
                timeout=TIMEOUT_EMBED,
            )
            r.raise_for_status()
            emb = r.json().get("embedding", [])
            marcar(
                len(emb) > 0,
                f"/api/embeddings OK con {modelos['OLLAMA_MODEL_EMBEDDINGS']} (dimensión={len(emb)})",
                f"/api/embeddings falló con {modelos['OLLAMA_MODEL_EMBEDDINGS']}",
            )
        except Exception as e:  # noqa: BLE001
            marcar(False, "", f"/api/embeddings lanzó error: {e}")

        # --------------------------------------------------------------
        # 4) Chat mínimo (Agente Dev — CU16/CU18/CU20/CU21)
        # --------------------------------------------------------------
        try:
            r = httpx.post(
                f"{base_url}/api/chat",
                json={
                    "model": modelos["OLLAMA_MODEL_TEXT"],
                    "messages": [{"role": "user", "content": "Responde únicamente con la palabra: OK"}],
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=TIMEOUT_CHAT,
            )
            r.raise_for_status()
            contenido = (r.json().get("message") or {}).get("content", "")
            marcar(
                bool(contenido.strip()),
                f"/api/chat OK con {modelos['OLLAMA_MODEL_TEXT']} (respuesta: {contenido.strip()[:40]!r})",
                f"/api/chat respondió vacío con {modelos['OLLAMA_MODEL_TEXT']}",
            )
        except Exception as e:  # noqa: BLE001
            marcar(False, "", f"/api/chat lanzó error: {e}")

    print("-" * 60)
    print(f"Resumen: {ok_total} OK / {fail_total} FAIL")
    if fail_total == 0:
        print("Ollama listo para DevForge AI.")
    else:
        print("Revisa los [FAIL] de arriba antes de arrancar el backend.")
    print("=" * 60)
    return 0 if fail_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
