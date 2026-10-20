#!/usr/bin/env python3
"""
Diagnóstico manual de Pollinations para ClassIA.

Uso:
    python tools/probar_pollinations.py
    python tools/probar_pollinations.py --generar-una --confirmar-posible-consumo

Por defecto sólo verifica la configuración y consulta el catálogo público de
modelos: no genera ninguna imagen, no consume saldo y no necesita clave.

Con `--generar-una` realiza exactamente UNA solicitud de imagen (512x512) al
endpoint actual. Exige `--confirmar-posible-consumo` porque la ruta
gen.pollinations.ai descuenta Pollen del saldo de la clave. El archivo se
guarda en temporal/pruebas_pollinations/ con un nombre único, sin sobrescribir.

Este script no se ejecuta al iniciar ClassIA y no se usa en los tests
automáticos: todas las llamadas de red están dentro de las funciones que
invoca `main`.
"""
import argparse
import hashlib
import io
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from configuracion import (  # noqa: E402
    CARPETA_TEMPORAL,
    IMAGE_GENERATION_ENABLED,
    IMAGE_PROVIDER,
    POLLINATIONS_API_KEY,
    POLLINATIONS_IMAGE_MODEL,
    STRICT_FREE_IMAGE_MODE,
)

URL_IMAGEN = "https://gen.pollinations.ai/image/{prompt}"
URL_MODELOS = "https://gen.pollinations.ai/image/models"
CARPETA_PRUEBAS = CARPETA_TEMPORAL / "pruebas_pollinations"
PROMPT_PRUEBA = (
    "Ilustración educativa simple de una brújula y un mapa, "
    "estilo plano, fondo claro"
)
ANCHO_PRUEBA = 512
ALTO_PRUEBA = 512
TIMEOUT_SEGUNDOS = 120

EXTENSIONES = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
}


class ErrorDiagnosticoImagen(Exception):
    """La respuesta no es una imagen utilizable."""


# ---------------------------------------------------------------------------
# Funciones puras (verificables sin red)
# ---------------------------------------------------------------------------

def buscar_modelo(
    modelos: List[Dict[str, Any]], modelo: str
) -> Optional[Dict[str, Any]]:
    """Busca por nombre canónico o alias, sin distinguir mayúsculas."""
    buscado = (modelo or "").strip().lower()
    if not buscado:
        return None
    for item in modelos:
        if not isinstance(item, dict):
            continue
        nombre = str(item.get("name") or "").strip().lower()
        if nombre == buscado:
            return item
        alias = [str(a).strip().lower() for a in (item.get("aliases") or [])]
        if buscado in alias:
            return item
    return None


def resumir_modelo(modelo: Dict[str, Any]) -> Dict[str, Any]:
    """Extrae sólo los datos útiles para el diagnóstico."""
    return {
        "id": modelo.get("name") or "(sin id)",
        "title": modelo.get("title") or "",
        "aliases": modelo.get("aliases") or [],
        "pricing": modelo.get("pricing") or {},
        "pricing_units": modelo.get("pricing_units") or {},
        "paid_only": modelo.get("paid_only"),
        "flat_rate": modelo.get("flat_rate"),
        "per_user_rpm": modelo.get("per_user_rpm"),
        "supported_endpoints": modelo.get("supported_endpoints") or [],
        "health": modelo.get("health") or {},
    }


def construir_url_imagen(
    prompt: str,
    modelo: str,
    ancho: int = ANCHO_PRUEBA,
    alto: int = ALTO_PRUEBA,
    seed: Optional[int] = None,
) -> str:
    """Construye la URL con parámetros documentados del endpoint actual."""
    base = URL_IMAGEN.format(prompt=quote(prompt, safe=""))
    parametros = {
        "model": modelo,
        "width": str(int(ancho)),
        "height": str(int(alto)),
    }
    if seed is not None:
        parametros["seed"] = str(int(seed))
    return f"{base}?{urlencode(parametros, safe='/:')}"


def validar_imagen_bytes(contenido: bytes, content_type: str) -> Dict[str, Any]:
    """
    Comprueba que la respuesta sea una imagen raster que Pillow pueda abrir.

    Lanza ErrorDiagnosticoImagen si es HTML, JSON, SVG, demasiado pequeña o
    si Pillow no puede abrirla. No guarda nada.
    """
    tipo = (content_type or "").lower()
    if not tipo or "image" not in tipo:
        raise ErrorDiagnosticoImagen(
            f"El servidor no devolvió una imagen. Content-Type: {content_type!r}"
        )
    if not contenido or len(contenido) < 100:
        raise ErrorDiagnosticoImagen(
            "La respuesta es demasiado pequeña para ser una imagen válida."
        )

    inicio = contenido[:300].lstrip().lower()
    if inicio.startswith(b"<!doctype html") or inicio.startswith(b"<html"):
        raise ErrorDiagnosticoImagen(
            "La respuesta es HTML, no una imagen. No se guardará."
        )
    if inicio.startswith(b"{") or inicio.startswith(b"["):
        raise ErrorDiagnosticoImagen(
            "La respuesta es JSON, no una imagen. No se guardará."
        )
    if b"<svg" in inicio:
        raise ErrorDiagnosticoImagen(
            "La respuesta es SVG. Pillow no puede verificar SVG; no se "
            "guardará como imagen raster."
        )

    try:
        from PIL import Image
    except ImportError as e:
        raise ErrorDiagnosticoImagen(
            "Pillow no está instalado; no se puede verificar la imagen."
        ) from e

    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen.verify()
        with Image.open(io.BytesIO(contenido)) as imagen:
            ancho, alto = imagen.size
            formato = (imagen.format or "").upper()
            imagen.load()
    except Exception as e:
        raise ErrorDiagnosticoImagen(
            f"Pillow no pudo abrir la imagen: {e}"
        ) from e

    if ancho <= 0 or alto <= 0:
        raise ErrorDiagnosticoImagen(
            f"Dimensiones inválidas: {ancho}x{alto}."
        )

    return {
        "formato": formato or "desconocido",
        "ancho": ancho,
        "alto": alto,
        "bytes": len(contenido),
    }


def guardar_imagen_unica(
    carpeta: Path,
    contenido: bytes,
    formato: str,
) -> Path:
    """Guarda la imagen con un nombre único; nunca sobrescribe un archivo."""
    carpeta.mkdir(parents=True, exist_ok=True)
    extension = EXTENSIONES.get((formato or "").upper(), ".img")
    for _ in range(5):
        nombre = (
            f"pollinations_{datetime.now():%Y%m%d_%H%M%S}_"
            f"{uuid.uuid4().hex[:10]}{extension}"
        )
        ruta = carpeta / nombre
        try:
            with open(ruta, "xb") as archivo:
                archivo.write(contenido)
            return ruta
        except FileExistsError:
            continue
    raise ErrorDiagnosticoImagen(
        "No se pudo crear un nombre de archivo único."
    )


# ---------------------------------------------------------------------------
# Red
# ---------------------------------------------------------------------------

def consultar_catalogo_modelos(timeout: int = 30) -> List[Dict[str, Any]]:
    """Consulta el catálogo público de imágenes. No genera ni consume."""
    import requests

    respuesta = requests.get(URL_MODELOS, timeout=timeout)
    respuesta.raise_for_status()
    cuerpo = respuesta.json()
    if isinstance(cuerpo, list):
        return [m for m in cuerpo if isinstance(m, dict)]
    if isinstance(cuerpo, dict):
        for clave in ("data", "models", "images"):
            valor = cuerpo.get(clave)
            if isinstance(valor, list):
                return [m for m in valor if isinstance(m, dict)]
    raise ValueError("El catálogo de imágenes no tiene el formato esperado.")


def _detalle_coste(
    resumen: Dict[str, Any],
    ancho: Optional[int] = None,
    alto: Optional[int] = None,
) -> str:
    """
    Describe el coste del catálogo y, si es posible, lo estima para el tamaño.

    No inventa un precio exacto cuando el modelo cobra por tokens: en ese
    caso lo indica explícitamente.
    """
    precios = resumen.get("pricing") or {}
    unidades = resumen.get("pricing_units") or {}
    valor = precios.get("completionImageTokens")
    moneda = precios.get("currency") or "pollen"
    if valor is None:
        return "no informado por el catálogo"

    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        return f"{valor} {moneda} (formato de precio no interpretable)"

    unidad = unidades.get("completionImageTokens") or {}
    tipo_unidad = str(unidad.get("unit") or "").lower()
    try:
        cantidad = float(unidad.get("quantity") or 1)
    except (TypeError, ValueError):
        cantidad = 1.0

    if tipo_unidad == "megapixel":
        precio_mp = valor_float * cantidad
        if ancho and alto:
            megapixeles = (int(ancho) * int(alto)) / 1_000_000
            estimado = precio_mp * megapixeles
            return (
                f"{precio_mp:.6f} {moneda}/MP; "
                f"aprox. {estimado:.6f} {moneda} para {ancho}x{alto}"
            )
        return f"{precio_mp:.6f} {moneda}/MP"

    if resumen.get("flat_rate"):
        return (
            f"{valor} {moneda} por imagen "
            f"(flat_rate={resumen.get('flat_rate')}, "
            f"paid_only={resumen.get('paid_only')})"
        )

    return (
        f"{valor} {moneda} por token de imagen; el coste exacto no se "
        "puede confirmar sin los tokens consumidos (flat_rate="
        f"{resumen.get('flat_rate')}, paid_only={resumen.get('paid_only')})"
    )


def _mostrar_resumen_modelo(
    resumen: Dict[str, Any],
    ancho: Optional[int] = None,
    alto: Optional[int] = None,
) -> None:
    print(f"  ID canónico: {resumen['id']}")
    if resumen.get("title"):
        print(f"  Título: {resumen['title']}")
    if resumen.get("aliases"):
        print(f"  Alias: {', '.join(resumen['aliases'])}")
    print(f"  Coste de catálogo: {_detalle_coste(resumen, ancho, alto)}")
    print(
        "  Endpoints admitidos: "
        + (", ".join(resumen.get("supported_endpoints") or []) or "(no informados)")
    )
    print(
        "  Límite por usuario: "
        f"{resumen.get('per_user_rpm') or 'no informado'} req/min"
    )
    salud = resumen.get("health") or {}
    if salud:
        print(
            f"  Salud: {salud.get('status', '?')} "
            f"(éxito={salud.get('success_rate', '?')}%, "
            f"requests={salud.get('requests', '?')})"
        )


def _leer_catalogo_para_modelo(
    modelo: Optional[str] = None,
    ancho: Optional[int] = None,
    alto: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Devuelve el resumen del modelo solicitado o None si no se verifica."""
    print(f"Consultando catálogo de imágenes: {URL_MODELOS}")
    print("Esta consulta no genera imágenes ni consume saldo.")
    try:
        modelos = consultar_catalogo_modelos()
    except Exception as e:
        print(f"ADVERTENCIA: no se pudo consultar el catálogo: {e}")
        print(
            "No se puede verificar el modelo ni el coste exacto. "
            "No se generará ninguna imagen sin esa verificación."
        )
        return None

    modelo_configurado = (modelo or POLLINATIONS_IMAGE_MODEL or "").strip()
    encontrado = buscar_modelo(modelos, modelo_configurado)
    if not encontrado:
        print(
            f"ADVERTENCIA: el modelo '{modelo_configurado}' no aparece en el "
            "catálogo actual. Revisá POLLINATIONS_IMAGE_MODEL o el valor de "
            "--modelo."
        )
        return None

    resumen = resumir_modelo(encontrado)
    _mostrar_resumen_modelo(resumen, ancho, alto)
    if "/image/{prompt}" not in (resumen.get("supported_endpoints") or []):
        print(
            "ADVERTENCIA: el catálogo no anuncia /image/{prompt} para este "
            "modelo. No se generará la prueba."
        )
        return None
    return resumen


def verificar_configuracion(
    modelo: Optional[str] = None,
    ancho: int = ANCHO_PRUEBA,
    alto: int = ALTO_PRUEBA,
) -> int:
    """Sólo verifica configuración y catálogo; no genera imágenes."""
    print("Diagnóstico de Pollinations para ClassIA")
    print("=" * 78)
    print(f"Endpoint de generación: {URL_IMAGEN.format(prompt='{prompt}')}")
    print(f"Proveedor configurado (IMAGE_PROVIDER): {IMAGE_PROVIDER}")
    print(
        "Generación de imágenes habilitada (IMAGE_GENERATION_ENABLED): "
        f"{'sí' if IMAGE_GENERATION_ENABLED else 'no'}"
    )
    print(
        "Modo de bajo coste (STRICT_FREE_IMAGE_MODE): "
        f"{'sí' if STRICT_FREE_IMAGE_MODE else 'no'}"
    )
    print(f"Modelo configurado: {POLLINATIONS_IMAGE_MODEL or '(vacío)'}")
    if modelo and modelo != POLLINATIONS_IMAGE_MODEL:
        print(f"Modelo solicitado para la consulta: {modelo}")
    if ancho != ANCHO_PRUEBA or alto != ALTO_PRUEBA:
        print(f"Tamaño para estimar el coste: {ancho}x{alto}")
    print(
        "Clave configurada (POLLINATIONS_API_KEY): "
        f"{'sí (oculta)' if POLLINATIONS_API_KEY else 'NO'}"
    )
    print("")
    print(
        "Documentación vigente: gen.pollinations.ai exige una clave secreta "
        "(sk_...) para generar y descuenta Pollen del saldo. La API clásica "
        "image.pollinations.ai es gratuita y sin clave, pero usa otro "
        "endpoint, otro modelo y tiene límites propios."
    )
    print("")

    resumen = _leer_catalogo_para_modelo(modelo, ancho, alto)
    print("")
    if resumen is None:
        print("RESULTADO: configuración NO verificada.")
        print("No se realizó ninguna solicitud de generación.")
        return 1

    print(
        "RESULTADO: modelo verificado; coste: "
        f"{_detalle_coste(resumen, ancho, alto)}"
    )
    if not POLLINATIONS_API_KEY:
        print(
            "ADVERTENCIA: falta POLLINATIONS_API_KEY. El endpoint actual "
            "requiere clave para generar, así que la prueba real fallará."
        )
        print("No se realizó ninguna solicitud de generación.")
        return 1

    if (IMAGE_PROVIDER or "").strip().lower() != "pollinations":
        print(
            "ADVERTENCIA: IMAGE_PROVIDER no es 'pollinations'. Este "
            "diagnóstico no puede validar otro proveedor."
        )
        return 1

    if not IMAGE_GENERATION_ENABLED:
        print(
            "ADVERTENCIA: IMAGE_GENERATION_ENABLED=0. La aplicación no "
            "generará imágenes aunque el endpoint funcione."
        )

    print("No se realizó ninguna solicitud de generación.")
    print("")
    print("Para hacer UNA solicitud real (puede consumir saldo):")
    print(
        "  python tools/probar_pollinations.py --generar-una "
        "--confirmar-posible-consumo"
    )
    return 0


def _cabecera(cabeceras: Any, *nombres: str) -> str:
    bajo = {str(k).lower(): v for k, v in (cabeceras or {}).items()}
    for nombre in nombres:
        valor = bajo.get(nombre.lower())
        if valor:
            return str(valor)
    return ""


def _categoria_error_http(status: int) -> str:
    if status in (401, 403):
        return "autenticación fallida (clave inválida o sin permisos)"
    if status == 402:
        return "saldo/crédito insuficiente"
    if status == 429:
        return "límite de uso alcanzado"
    if status >= 500:
        return "error del servidor o del proveedor"
    return "solicitud rechazada"


def generar_una(
    confirmado: bool,
    modelo: Optional[str] = None,
    ancho: int = ANCHO_PRUEBA,
    alto: int = ALTO_PRUEBA,
) -> int:
    """Hace exactamente una solicitud de imagen y valida el resultado."""
    if not confirmado:
        print("ERROR: falta --confirmar-posible-consumo.")
        print(
            "La ruta gen.pollinations.ai descuenta Pollen del saldo de la "
            "clave. No se realizó ninguna solicitud."
        )
        print(
            "Si aceptás el posible consumo, ejecutá:\n"
            "  python tools/probar_pollinations.py --generar-una "
            "--confirmar-posible-consumo"
        )
        return 2

    if not (64 <= int(ancho) <= 2048 and 64 <= int(alto) <= 2048):
        print(
            "ERROR: ancho y alto deben estar entre 64 y 2048 píxeles. "
            "No se realizó ninguna solicitud."
        )
        return 2

    print("Prueba real de Pollinations (UNA sola solicitud)")
    print("=" * 78)
    print(f"Endpoint: {URL_IMAGEN.format(prompt='{prompt}')}")
    print(f"Modelo configurado: {POLLINATIONS_IMAGE_MODEL or '(vacío)'}")
    if modelo and modelo != POLLINATIONS_IMAGE_MODEL:
        print(f"Modelo solicitado: {modelo}")
    print(f"Tamaño: {ancho}x{alto}")
    print(
        "Clave configurada (POLLINATIONS_API_KEY): "
        f"{'sí (oculta)' if POLLINATIONS_API_KEY else 'NO'}"
    )
    print("")

    if (IMAGE_PROVIDER or "").strip().lower() != "pollinations":
        print(
            f"ERROR: IMAGE_PROVIDER='{IMAGE_PROVIDER}' no es 'pollinations'. "
            "No se realizó ninguna solicitud."
        )
        return 1
    if not POLLINATIONS_API_KEY:
        print(
            "ERROR: falta POLLINATIONS_API_KEY. El endpoint actual exige una "
            "clave secreta para generar. No se realizó ninguna solicitud."
        )
        return 1

    resumen = _leer_catalogo_para_modelo(modelo, ancho, alto)
    print("")
    if resumen is None:
        print(
            "ERROR: no se pudo verificar el modelo ni el coste exacto. "
            "No se realizó ninguna solicitud de generación."
        )
        return 1

    modelo_canonico = str(resumen.get("id") or modelo or POLLINATIONS_IMAGE_MODEL)
    print(f"Modelo canónico verificado: {modelo_canonico}")
    print(
        "Coste de catálogo verificado: "
        f"{_detalle_coste(resumen, ancho, alto)}"
    )
    print("Se realizará exactamente 1 solicitud. No hay reintentos.")
    print("")

    import requests

    seed = random.randint(1, 2_147_483_647)
    url = construir_url_imagen(
        PROMPT_PRUEBA, modelo_canonico,
        ancho, alto, seed=seed,
    )
    headers = {
        "User-Agent": "AulaIA-diagnostico/1.0 (educational use)",
        "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
    }

    try:
        respuesta = requests.get(url, headers=headers, timeout=TIMEOUT_SEGUNDOS)
    except requests.Timeout:
        print(f"ERROR: sin respuesta en {TIMEOUT_SEGUNDOS} segundos.")
        return 1
    except requests.ConnectionError as e:
        print(f"ERROR de conexión: {e}")
        return 1
    except requests.RequestException as e:
        print(f"ERROR de red: {e}")
        return 1

    content_type = respuesta.headers.get("Content-Type", "")
    print(f"Estado HTTP: {respuesta.status_code}")
    print(f"Content-Type: {content_type or '(no informado)'}")
    print(f"Bytes recibidos: {len(respuesta.content)}")
    print(f"Modelo informado por el servidor: "
          f"{_cabecera(respuesta.headers, 'x-model', 'x-pollinations-model', 'x-image-model') or '(no informado)'}")
    print(f"Seed: {seed}")
    print("")

    if respuesta.status_code != 200:
        categoria = _categoria_error_http(respuesta.status_code)
        print(f"ERROR: {categoria} (HTTP {respuesta.status_code}).")
        vista = (respuesta.text or "")[:300].replace("\n", " ").strip()
        if vista:
            print(f"Respuesta (primeros 300 caracteres): {vista}")
        print(
            "No se guardó ningún archivo: una respuesta de error no es una "
            "imagen."
        )
        return 1

    try:
        datos = validar_imagen_bytes(respuesta.content, content_type)
    except ErrorDiagnosticoImagen as e:
        print(f"ERROR: {e}")
        print("No se guardó ningún archivo.")
        return 1

    try:
        ruta = guardar_imagen_unica(CARPETA_PRUEBAS, respuesta.content, datos["formato"])
    except ErrorDiagnosticoImagen as e:
        print(f"ERROR al guardar: {e}")
        return 1

    sha256 = hashlib.sha256(respuesta.content).hexdigest()
    print("IMAGEN RECIBIDA DE POLLINATIONS")
    print("-" * 78)
    print(
        "Origen: respuesta HTTP directa de gen.pollinations.ai "
        "(no es una imagen local, un marcador ni un archivo residual)."
    )
    print(f"Modelo solicitado: {modelo_canonico}")
    print(f"Formato abierto por Pillow: {datos['formato']}")
    print(f"Dimensiones: {datos['ancho']}x{datos['alto']}")
    print(f"Bytes: {datos['bytes']}")
    print(f"SHA-256: {sha256}")
    print(f"Archivo nuevo (sin sobrescribir): {ruta}")
    print(f"Coste de catálogo: {_detalle_coste(resumen, ancho, alto)}")
    print("")
    print("VERIFICACIÓN: OK. Pillow abrió la imagen correctamente.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verifica la configuración de Pollinations o genera UNA sola "
            "imagen de prueba con confirmación explícita."
        )
    )
    parser.add_argument(
        "--generar-una",
        action="store_true",
        help="realizar exactamente una solicitud de imagen (512x512 por defecto).",
    )
    parser.add_argument(
        "--confirmar-posible-consumo",
        action="store_true",
        help="confirmar que aceptás un posible consumo de saldo/créditos.",
    )
    parser.add_argument(
        "--modelo",
        default=None,
        help=(
            "ID canónico del catálogo para consultar o probar sin editar "
            ".env (por ejemplo, qwen/qwen-image-2.1)."
        ),
    )
    parser.add_argument(
        "--ancho",
        type=int,
        default=ANCHO_PRUEBA,
        help="ancho en píxeles; por defecto 512. Sólo afecta la prueba.",
    )
    parser.add_argument(
        "--alto",
        type=int,
        default=ALTO_PRUEBA,
        help="alto en píxeles; por defecto 512. Sólo afecta la prueba.",
    )
    args = parser.parse_args(argv)

    if args.confirmar_posible_consumo and not args.generar_una:
        print(
            "ERROR: --confirmar-posible-consumo sólo tiene sentido junto con "
            "--generar-una."
        )
        return 2

    if args.generar_una:
        return generar_una(
            args.confirmar_posible_consumo,
            modelo=args.modelo,
            ancho=args.ancho,
            alto=args.alto,
        )
    return verificar_configuracion(
        modelo=args.modelo, ancho=args.ancho, alto=args.alto
    )


if __name__ == "__main__":
    raise SystemExit(main())
