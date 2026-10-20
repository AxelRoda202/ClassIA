"""
Generación de imágenes externas mediante IA (Pollinations).

Módulo independiente encargado de:
1. Seleccionar recursos visuales que requieren imágenes externas.
2. Consultar disponibilidad de configuración y proveedor.
3. Generar únicamente los recursos seleccionados (máximo 2 por PDF).
4. Verificar que la respuesta contenga un archivo de imagen válido.
5. Guardar el archivo localmente y asociar la ruta al identificador del recurso.

Restricción de costes:
- No se compran créditos.
- No se activan recargas automáticas.
- No se invocan modelos de pago.
- No se usa como respaldo de proveedores de pago.
- No se realizan llamadas reales durante pruebas automatizadas.
"""
import hashlib
import io
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from pathlib import Path

import requests
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

from configuracion import (
    CARPETA_TEMPORAL,
    IMAGE_GENERATION_ENABLED,
    IMAGE_PROVIDER,
    MAX_EXTERNAL_IMAGES_PER_PDF,
    POLLINATIONS_API_KEY,
    POLLINATIONS_IMAGE_MODEL,
    STRICT_FREE_IMAGE_MODE,
)


# Modelos permitidos en modo de bajo coste. La lista NO implica gratuidad:
# gen.pollinations.ai descuenta Pollen incluso en modelos paid_only=false.
# Se incluyen alternativas económicas y el modelo recomendado para texto.
MODELOS_IMAGEN_PERMITIDOS = {
    "black-forest-labs/flux.1-schnell",
    "tongyi-mai/z-image-turbo",
    "black-forest-labs/flux.2-klein-4b",
    "qwen/qwen-image-2.1",
    "qwen/qwen-image",
}


class ErrorImagenExterna(Exception):
    """Excepción base para errores de generación de imágenes externas."""
    pass


class ErrorProveedorImagenes(ErrorImagenExterna):
    """El proveedor de imágenes no está disponible o configurado."""
    pass


class ErrorRespuestaImagen(ErrorImagenExterna):
    """La respuesta del proveedor no contiene una imagen válida."""
    pass


def proveedor_imagenes_esta_habilitado() -> bool:
    """
    Devuelve True si la generación de imágenes externas está habilitada
    y el proveedor está configurado (o puede usarse anónimamente).
    """
    if not IMAGE_GENERATION_ENABLED:
        return False
    if IMAGE_PROVIDER.lower() != "pollinations":
        return False
    # Pollinations puede usarse sin clave en modo gratuito estricto
    if STRICT_FREE_IMAGE_MODE and not POLLINATIONS_API_KEY:
        return True  # Modo anónimo gratuito
    return bool(POLLINATIONS_API_KEY) or True  # Siempre disponible si está habilitado


def _normalizar_prompt(prompt: str) -> str:
    """Normaliza el prompt para generar una clave de caché estable."""
    return " ".join(prompt.split()).strip()


def _clave_cache(prompt: str, modelo: str, ancho: int, alto: int) -> str:
    """Genera una clave de caché basada en prompt, modelo y dimensiones."""
    datos = f"{prompt}|{modelo}|{ancho}|{alto}"
    return hashlib.sha256(datos.encode("utf-8")).hexdigest()[:16]


def _ruta_cache(clave: str) -> Path:
    """Devuelve la ruta del archivo en caché para una clave dada."""
    carpeta_cache = CARPETA_TEMPORAL / "imagenes_cache"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    return carpeta_cache / f"{clave}.png"


def _obtener_desde_cache(clave: str) -> Optional[str]:
    """Intenta obtener una imagen desde la caché local."""
    ruta = _ruta_cache(clave)
    if ruta.exists() and ruta.stat().st_size > 0:
        return str(ruta)
    return None


def _guardar_en_cache(clave: str, contenido_bytes: bytes) -> str:
    """Guarda una imagen en la caché y devuelve la ruta."""
    ruta = _ruta_cache(clave)
    ruta.write_bytes(contenido_bytes)
    return str(ruta)


def _validar_imagen_contenido(contenido_bytes: bytes, contenido_tipo: str) -> None:
    """
    Valida que el contenido descargado sea realmente una imagen.

    Comprueba:
    - Código de respuesta (llamado antes).
    - Tipo de contenido.
    - Que Pillow pueda abrir el archivo.
    - Dimensiones y tamaño razonables.
    - Que no sea un mensaje de error HTML o JSON.
    """
    if not contenido_tipo or "image" not in contenido_tipo.lower():
        raise ErrorRespuestaImagen(
            f"El servidor no devolvió una imagen. Content-Type: {contenido_tipo}"
        )

    if len(contenido_bytes) < 100:
        raise ErrorRespuestaImagen(
            "La respuesta es demasiado pequeña para ser una imagen válida."
        )

    # Verificar que no sea HTML o JSON disfrazado
    inicio = contenido_bytes[:50].lower()
    if inicio.startswith(b"<!doctype") or inicio.startswith(b"<html") or inicio.startswith(b"{"):
        raise ErrorRespuestaImagen(
            "El servidor devolvió HTML o JSON en lugar de una imagen."
        )

    try:
        imagen = PILImage.open(io.BytesIO(contenido_bytes))
        imagen.verify()
        imagen = PILImage.open(io.BytesIO(contenido_bytes))
        ancho, alto = imagen.size
        if ancho < 50 or alto < 50:
            raise ErrorRespuestaImagen(
                f"La imagen es demasiado pequeña: {ancho}x{alto} píxeles."
            )
        if ancho > 4096 or alto > 4096:
            raise ErrorRespuestaImagen(
                f"La imagen excede el tamaño máximo permitido: {ancho}x{alto}."
            )
    except Exception as e:
        if isinstance(e, ErrorImagenExterna):
            raise
        raise ErrorRespuestaImagen(f"No se pudo validar la imagen: {e}")


def _descargar_imagen_pollinations(
    prompt: str,
    modelo: str,
    ancho: int = 1024,
    alto: int = 768,
    timeout: int = 60,
) -> str:
    """
    Descarga una imagen generada por Pollinations.

    Endpoint oficial vigente:
    https://gen.pollinations.ai/image/{prompt}

    Parámetros documentados que se usan:
    - model: nombre del modelo canónico
    - width, height: dimensiones exactas

    Restricción de costes: en modo STRICT_FREE_IMAGE_MODE sólo se permiten
    los modelos de MODELOS_IMAGEN_PERMITIDOS. Si el modelo configurado no
    está en la lista, se usa flux.1-schnell para no generar un gasto
    inesperado. Esta lista es una política de coste, no una garantía de
    gratuidad: el endpoint descuenta Pollen en todos sus modelos.
    """
    import logging
    logger = logging.getLogger(__name__)

    if STRICT_FREE_IMAGE_MODE and modelo not in MODELOS_IMAGEN_PERMITIDOS:
        logger.warning(
            "Modelo de imagen '%s' fuera de la lista de bajo coste; se usa "
            "black-forest-labs/flux.1-schnell.", modelo,
        )
        modelo = "black-forest-labs/flux.1-schnell"

    url = (
        f"https://gen.pollinations.ai/image/{quote(prompt, safe='')}"
        f"?model={modelo}&width={ancho}&height={alto}"
    )

    headers = {
        "User-Agent": "AulaIA/1.0 (educational use)",
    }
    if POLLINATIONS_API_KEY:
        headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"

    logger.info(f"Solicitando imagen a Pollinations: modelo={modelo}, prompt_inicio={prompt[:50]}...")

    try:
        respuesta = requests.get(
            url, headers=headers, timeout=timeout, stream=True
        )

        logger.info(f"Respuesta de Pollinations: status={respuesta.status_code}, content_type={respuesta.headers.get('Content-Type', '')}")

        if respuesta.status_code == 429:
            raise ErrorProveedorImagenes("Cuota de Pollinations agotada.")
        if respuesta.status_code == 401 or respuesta.status_code == 403:
            raise ErrorProveedorImagenes("Autenticación de Pollinations fallida.")
        if respuesta.status_code >= 500:
            raise ErrorProveedorImagenes(
                f"Error del servidor Pollinations: {respuesta.status_code}"
            )
        if not respuesta.ok:
            raise ErrorProveedorImagenes(
                f"Error de Pollinations: {respuesta.status_code} {respuesta.text[:200]}"
            )

        contenido_tipo = respuesta.headers.get("Content-Type", "")
        contenido_bytes = respuesta.content

        _validar_imagen_contenido(contenido_bytes, contenido_tipo)

        logger.info(f"Imagen recibida de Pollinations: {len(contenido_bytes)} bytes")
        return contenido_bytes

    except requests.Timeout:
        raise ErrorProveedorImagenes("Tiempo de espera agotado en Pollinations.")
    except requests.ConnectionError:
        raise ErrorProveedorImagenes("No se pudo conectar con Pollinations.")
    except ErrorImagenExterna:
        raise
    except Exception as e:
        raise ErrorProveedorImagenes(f"Error inesperado en Pollinations: {e}")


def generar_imagen_externa(
    recurso: Dict[str, Any],
    carpeta_destino: Path,
    ancho: int = 1024,
    alto: int = 768,
) -> Optional[str]:
    """
    Genera una imagen externa para un recurso visual del JSON.

    Flujo:
    1. Verificar que el proveedor esté habilitado.
    2. Verificar caché local (prompt, modelo, dimensiones).
    3. Descargar imagen del proveedor.
    4. Validar que sea una imagen real.
    5. Guardar localmente y devolver la ruta.

    Devuelve la ruta del archivo generado, o None si no se pudo construir.
    """
    if not proveedor_imagenes_esta_habilitado():
        return None

    prompt = recurso.get("image_generation_prompt", "") or ""
    if not prompt:
        return None

    recurso_id = recurso.get("id", "desconocido")
    titulo = recurso.get("title", "Imagen")

    # Verificar caché
    clave = _clave_cache(_normalizar_prompt(prompt), POLLINATIONS_IMAGE_MODEL, ancho, alto)
    ruta_cache = _obtener_desde_cache(clave)
    if ruta_cache:
        return ruta_cache

    try:
        contenido_bytes = _descargar_imagen_pollinations(
            prompt=prompt,
            modelo=POLLINATIONS_IMAGE_MODEL,
            ancho=ancho,
            alto=alto,
        )

        # Guardar en caché
        ruta_cache = _guardar_en_cache(clave, contenido_bytes)

        # Copiar a la carpeta del trabajo para asociarla al recurso
        carpeta_destino.mkdir(parents=True, exist_ok=True)
        ruta_final = carpeta_destino / f"imagen_ext_{recurso_id}.png"
        ruta_final.write_bytes(contenido_bytes)

        return str(ruta_final)

    except ErrorImagenExterna as e:
        print(f"[generador_imagenes] Error generando '{recurso_id}': {e}")
        return None
    except Exception as e:
        print(f"[generador_imagenes] Error inesperado '{recurso_id}': {e}")
        return None


def seleccionar_recursos_externos(
    recursos: list,
    maximo: int = MAX_EXTERNAL_IMAGES_PER_PDF,
) -> list:
    """
    Selecciona del JSON los recursos que requieren generación externa.

    Solo selecciona recursos de tipo 'external_image' hasta el máximo permitido.
    Prioriza los que tienen un prompt válido y propósito educativo claro.
    """
    if not IMAGE_GENERATION_ENABLED:
        return []

    externos = []
    for recurso in recursos:
        if not isinstance(recurso, dict):
            continue
        if recurso.get("type", "").strip().lower() == "external_image":
            prompt = recurso.get("image_generation_prompt", "") or ""
            if prompt.strip():
                externos.append(recurso)
                if len(externos) >= maximo:
                    break

    return externos


def generar_imagenes_seleccionadas(
    recursos_externos: list,
    carpeta_destino: Path,
) -> Dict[str, str]:
    """
    Genera todas las imágenes externas seleccionadas.

    Devuelve un diccionario mapeando recurso_id -> ruta del archivo generado.
    """
    rutas: Dict[str, str] = {}
    for recurso in recursos_externos:
        recurso_id = recurso.get("id", "")
        if not recurso_id:
            continue
        ruta = generar_imagen_externa(recurso, carpeta_destino)
        if ruta:
            rutas[recurso_id] = ruta
    return rutas
