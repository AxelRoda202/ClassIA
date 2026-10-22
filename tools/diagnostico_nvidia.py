"""
Diagnóstico manual de un modelo NVIDIA NIM.

Uso seguro (no realiza ninguna llamada):
    python tools/diagnostico_nvidia.py
    python tools/diagnostico_nvidia.py --modelo MODELO --etapa lote_ejercicios

Consulta del catálogo (una sola solicitud GET):
    python tools/diagnostico_nvidia.py --catalogo --ejecutar

Prueba real de un modelo (una sola solicitud POST):
    python tools/diagnostico_nvidia.py --modelo MODELO --etapa lote_ejercicios --ejecutar

La clave se lee de NVIDIA_API_KEY. Nunca se imprime. Este script no forma
parte de la suite automática y no se ejecuta durante la instalación.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from configuracion import (  # noqa: E402
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_MODELS,
    NVIDIA_RESPONSE_FORMAT,
    TOKEN_MAX_SALIDA,
    TIMEOUT_SEGUNDOS,
)
from esquemas_bloques import (  # noqa: E402
    normalizar_claves,
    obtener_esquema_openrouter,
    validar_componentes_finales,
    validar_lote_ejercicios,
    validar_plan_aprendizaje,
    validar_seccion_teorica,
)
from proveedores_ia import clasificar_error  # noqa: E402


ETAPAS = {
    "planificacion": validar_plan_aprendizaje,
    "seccion_teorica": validar_seccion_teorica,
    "lote_ejercicios": lambda d: validar_lote_ejercicios(
        normalizar_claves(d), exigir_espanol=True
    ),
    "componentes_finales": validar_componentes_finales,
}

PROMPTS = {
    "planificacion": (
        "Genera un plan de aprendizaje mínimo en español para el tema "
        "'Leyes de Newton', nivel secundario. Cumple exactamente el esquema "
        "JSON adjunto."
    ),
    "seccion_teorica": (
        "Genera una sección teórica mínima en español sobre la primera ley "
        "de Newton. Cumple exactamente el esquema JSON adjunto."
    ),
    "lote_ejercicios": (
        "Genera un lote de un ejercicio en español sobre las leyes de "
        "Newton, dificultad inicial. Cumple exactamente el esquema JSON "
        "adjunto."
    ),
    "componentes_finales": (
        "Genera un resumen, un glosario mínimo y metadatos en español para "
        "un material sobre las leyes de Newton. Cumple exactamente el "
        "esquema JSON adjunto."
    ),
}


def construir_payload(modelo: str, formato: str, etapa: str) -> Dict[str, Any]:
    """Construye el cuerpo exacto de una solicitud de diagnóstico."""
    _, esquema, _ = obtener_esquema_openrouter(etapa)
    payload: Dict[str, Any] = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": (
                "Responde ÚNICAMENTE con un objeto JSON válido que cumpla "
                "exactamente el esquema solicitado. No uses bloques de "
                "código markdown. No agregues texto fuera del JSON."
            )},
            {"role": "user", "content": PROMPTS[etapa]},
        ],
        "temperature": 0.4,
        "max_tokens": TOKEN_MAX_SALIDA,
        "stream": False,
    }
    if formato == "guided_json":
        payload["nvext"] = {"guided_json": esquema}
    elif formato == "json_object":
        payload["response_format"] = {"type": "json_object"}
    return payload


def _imprimir_clave_configurada() -> bool:
    if NVIDIA_API_KEY:
        print("NVIDIA_API_KEY: configurada (valor oculto)")
        return True
    print("NVIDIA_API_KEY: no configurada")
    return False


def _modelo_unico(modelo: Optional[str]) -> Optional[str]:
    """Evita probar varios modelos en una misma ejecución."""
    if modelo:
        return modelo.strip()
    candidatos = [m for m in NVIDIA_MODELS if m]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        print("ERROR: no hay modelos configurados (NVIDIA_MODEL/NVIDIA_MODELS).")
        return None
    print(
        "ERROR: hay varios modelos configurados. Indicá exactamente uno con "
        "--modelo para no realizar varias solicitudes."
    )
    for candidato in candidatos:
        print(f"  - {candidato}")
    return None


def _validar_respuesta(texto: str, etapa: str) -> Tuple[bool, str]:
    """Valida JSON y esquema local. Devuelve (ok, detalle)."""
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        return False, f"JSON inválido o truncado: {e.msg} (posición {e.pos})"
    if not isinstance(datos, (dict, list)):
        return False, "El JSON no es un objeto ni una lista."
    validador = ETAPAS[etapa]
    try:
        ok, errores = validador(datos)
    except Exception as e:
        return False, f"No se pudo validar el esquema: {e}"
    if not ok:
        return False, "Esquema incumplido: " + "; ".join(errores[:8])
    return True, "JSON válido y esquema cumplido."


def consultar_catalogo() -> int:
    """Hace una sola solicitud GET al catálogo de modelos."""
    import requests

    url = f"{NVIDIA_BASE_URL}/models"
    print(f"GET {url}")
    try:
        respuesta = requests.get(
            url,
            headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except Exception as e:
        print(f"ERROR de red: {type(clasificar_error(e)).__name__}: {e}")
        return 1

    print(f"HTTP {respuesta.status_code}")
    if respuesta.status_code != 200:
        try:
            detalle = respuesta.json()
        except Exception:
            detalle = (respuesta.text or "")[:300]
        print(f"Detalle: {detalle}")
        return 1
    try:
        cuerpo = respuesta.json()
    except Exception:
        print("ERROR: el catálogo no devolvió JSON.")
        return 1
    modelos = cuerpo.get("data") if isinstance(cuerpo, dict) else None
    if not isinstance(modelos, list):
        print("ERROR: el catálogo no tiene la lista 'data'.")
        return 1
    ids = sorted(
        str(m.get("id")) for m in modelos
        if isinstance(m, dict) and m.get("id")
    )
    print(f"Modelos visibles para esta cuenta: {len(ids)}")
    for modelo in ids:
        print(f"  - {modelo}")
    print(
        "Nota: aparecer en el catálogo no prueba acceso, gratuidad, "
        "compatibilidad con JSON ni calidad educativa."
    )
    return 0


def probar_modelo(modelo: str, formato: str, etapa: str) -> int:
    """Hace exactamente una solicitud POST y valida la respuesta."""
    import requests

    url = f"{NVIDIA_BASE_URL}/chat/completions"
    payload = construir_payload(modelo, formato, etapa)
    print(f"POST {url}")
    print(f"Modelo: {modelo}")
    print(f"Formato: {formato}")
    print(f"Etapa/esquema: {etapa}")
    print("Solicitudes planificadas: 1")

    inicio = time.monotonic()
    try:
        respuesta = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.Timeout:
        print(f"ERROR: timeout después de {TIMEOUT_SEGUNDOS} segundos.")
        return 1
    except requests.RequestException as e:
        print(f"ERROR de red: {type(clasificar_error(e)).__name__}: {e}")
        return 1
    finally:
        print(f"Duración: {time.monotonic() - inicio:.2f} segundos")

    print(f"HTTP {respuesta.status_code}")
    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = None
        print("Cuerpo no JSON (primeros 300 caracteres):")
        print((respuesta.text or "")[:300])
        return 1

    if respuesta.status_code != 200:
        if isinstance(cuerpo, dict) and cuerpo.get("error"):
            print(f"Error del proveedor: {cuerpo['error']}")
        else:
            print(f"Detalle: {str(cuerpo)[:300]}")
        return 1

    if isinstance(cuerpo, dict) and cuerpo.get("error"):
        print(f"Error lógico del proveedor: {cuerpo['error']}")
        return 1

    opciones = cuerpo.get("choices") if isinstance(cuerpo, dict) else None
    if not isinstance(opciones, list) or not opciones:
        print("ERROR: la respuesta no contiene 'choices'.")
        return 1
    opcion = opciones[0] if isinstance(opciones[0], dict) else {}
    mensaje = opcion.get("message") or {}
    contenido = mensaje.get("content") if isinstance(mensaje, dict) else ""
    if isinstance(contenido, list):
        contenido = "".join(
            parte.get("text", "") for parte in contenido
            if isinstance(parte, dict)
        )
    motivo = opcion.get("finish_reason")
    print(f"finish_reason: {motivo}")
    print(f"Modelo informado: {cuerpo.get('model') or '(no informado)'}")

    if not contenido:
        print("ERROR: contenido final vacío.")
        return 1
    if motivo == "length":
        print("ERROR: respuesta truncada por límite de tokens.")
        return 1

    ok, detalle = _validar_respuesta(str(contenido), etapa)
    print(f"Validación local: {detalle}")
    print("Vista previa:")
    print(str(contenido)[:600])
    return 0 if ok else 1


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnóstico manual de NVIDIA NIM. Sin --ejecutar no realiza "
            "ninguna llamada de red."
        )
    )
    parser.add_argument(
        "--ejecutar", action="store_true",
        help="realiza la solicitud real (sin esta opción sólo muestra el plan)",
    )
    parser.add_argument(
        "--catalogo", action="store_true",
        help="consulta GET /v1/models; no se combina con --modelo",
    )
    parser.add_argument(
        "--modelo", help="modelo exacto a probar (una sola solicitud POST)",
    )
    parser.add_argument(
        "--formato", choices=("guided_json", "json_object", "text"),
        default=NVIDIA_RESPONSE_FORMAT,
        help="formato de salida estructurada",
    )
    parser.add_argument(
        "--etapa", choices=tuple(ETAPAS), default="lote_ejercicios",
        help="esquema real de ClassIA que se usará para validar",
    )
    args = parser.parse_args(argv)

    print("Diagnóstico NVIDIA NIM")
    print(f"Endpoint: {NVIDIA_BASE_URL}")
    print(f"Modelos configurados: {len(NVIDIA_MODELS)}")
    clave_ok = _imprimir_clave_configurada()
    if not clave_ok:
        print("No se realizará ninguna solicitud. Configurá NVIDIA_API_KEY.")
        return 2

    if args.catalogo:
        if args.modelo:
            print("ERROR: --catalogo y --modelo son mutuamente excluyentes.")
            return 2
        if not args.ejecutar:
            print("Plan: GET /v1/models (una solicitud).")
            print("Agregá --ejecutar para consultar el catálogo real.")
            return 0
        return consultar_catalogo()

    modelo = _modelo_unico(args.modelo)
    if not modelo:
        return 2

    payload = construir_payload(modelo, args.formato, args.etapa)
    if not args.ejecutar:
        print("Plan: una sola solicitud POST a /v1/chat/completions.")
        print(f"Modelo: {modelo}")
        print(f"Formato: {args.formato}")
        print(f"Etapa/esquema: {args.etapa}")
        print("Cuerpo (sin credenciales):")
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:2000])
        print("Agregá --ejecutar para realizar la llamada real.")
        return 0

    return probar_modelo(modelo, args.formato, args.etapa)


if __name__ == "__main__":
    raise SystemExit(main())
