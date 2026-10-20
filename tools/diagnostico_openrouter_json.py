#!/usr/bin/env python3
"""
Diagnóstico manual de la salida JSON de OpenRouter.

Uso:
    python tools/diagnostico_openrouter_json.py --catalogo
    python tools/diagnostico_openrouter_json.py --probar-modelo ID_DEL_MODELO
    python tools/diagnostico_openrouter_json.py --probar-modelo ID --sin-razonamiento
    python tools/diagnostico_openrouter_json.py --probar-modelo ID --max-tokens 512

`--catalogo` (predeterminado) sólo consulta el catálogo público de OpenRouter:
no genera texto, no consume cuota y no necesita clave.

`--probar-modelo` hace exactamente UNA solicitud pequeña al modelo indicado,
con un JSON Schema mínimo, y verifica la respuesta. No recorre el catálogo ni
prueba modelos alternativos.

`--max-tokens` sólo cambia el límite de esta prueba; no modifica
TOKEN_MAX_SALIDA ni .env. En modelos con razonamiento, `max_tokens` cubre
razonamiento + salida visible, así que un valor chico puede agotarse antes de
producir el JSON final.

`--sin-razonamiento` envía `reasoning: {"enabled": false}`. Usalo sólo si la
ficha del modelo indica `reasoning.mandatory=false`. No se envían `effort` ni
`reasoning.max_tokens` si el modelo no los anuncia en su ficha.

La clave se lee de OPENROUTER_API_KEY (a través de .env). Nunca se imprime ni
se guarda en los resultados.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from configuracion import (  # noqa: E402
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_MODELS,
)

CATALOGO_URL = "https://openrouter.ai/api/v1/models"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SEGUNDOS = 60

ESQUEMA_PRUEBA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "campo": {"type": "string", "enum": ["prueba"]},
    },
    "required": ["ok", "campo"],
    "additionalProperties": False,
}

PROMPT_PRUEBA = (
    'Responde únicamente con un objeto JSON que tenga exactamente '
    '{"ok": true, "campo": "prueba"}. No agregues texto, explicaciones ni '
    "bloques de código markdown."
)

# Límite de la prueba individual. Es deliberadamente pequeño para verificar el
# esquema con bajo coste, pero en modelos con razonamiento también cubre los
# tokens de razonamiento. No se debe confundir con TOKEN_MAX_SALIDA de la app.
MAX_TOKENS_PRUEBA = 120


def _entero_seguro(valor: Any) -> Optional[int]:
    """Convierte un contador de tokens sin aceptar booleanos."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return None


def _uso_tokens(cuerpo: Any) -> Dict[str, Optional[int]]:
    """
    Extrae sólo contadores de tokens seguros del bloque `usage`.

    No copia el objeto completo para no arrastrar campos innecesarios. Admite
    las dos formas habituales de OpenRouter/proveedores:
    `usage.completion_tokens_details.reasoning_tokens` y
    `usage.reasoning_tokens`.
    """
    if not isinstance(cuerpo, dict):
        return {}
    usage = cuerpo.get("usage")
    if not isinstance(usage, dict):
        return {}

    detalles = usage.get("completion_tokens_details")
    if not isinstance(detalles, dict):
        detalles = {}

    razonamiento = _entero_seguro(detalles.get("reasoning_tokens"))
    if razonamiento is None:
        razonamiento = _entero_seguro(usage.get("reasoning_tokens"))

    salida = _entero_seguro(usage.get("completion_tokens"))
    entrada = _entero_seguro(usage.get("prompt_tokens"))
    total = _entero_seguro(usage.get("total_tokens"))

    visible: Optional[int] = None
    if salida is not None and razonamiento is not None:
        if salida >= razonamiento:
            visible = salida - razonamiento
        else:
            # Algunos proveedores informan razonamiento por separado del
            # completion_tokens; no inventamos una resta negativa.
            visible = None

    return {
        "prompt_tokens": entrada,
        "completion_tokens": salida,
        "reasoning_tokens": razonamiento,
        "visible_output_tokens": visible,
        "total_tokens": total,
    }


def _describir_uso(uso: Dict[str, Optional[int]]) -> List[str]:
    """Devuelve líneas legibles con los contadores disponibles."""
    if not uso:
        return ["  (no informado por la API)"]

    etiquetas = (
        ("prompt_tokens", "Entrada (prompt_tokens)"),
        ("completion_tokens", "Salida total (completion_tokens)"),
        ("reasoning_tokens", "Razonamiento (reasoning_tokens)"),
        ("visible_output_tokens", "Salida visible (completion - reasoning)"),
        ("total_tokens", "Total (total_tokens)"),
    )
    lineas = []
    for clave, etiqueta in etiquetas:
        valor = uso.get(clave)
        if valor is not None:
            lineas.append(f"  {etiqueta}: {valor}")
    return lineas or ["  (no informado por la API)"]



# ---------------------------------------------------------------------------
# Catálogo (funciones puras, verificables con tests)
# ---------------------------------------------------------------------------

def es_modelo_gratuito(modelo: Dict[str, Any]) -> bool:
    """True si el precio de prompt y completion es exactamente cero."""
    precios = modelo.get("pricing") or {}
    for clave in ("prompt", "completion"):
        try:
            if float(precios.get(clave, "1")) != 0.0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def soporta_json_schema(modelo: Dict[str, Any]) -> bool:
    """True si la ficha anuncia structured_outputs (JSON Schema)."""
    parametros = modelo.get("supported_parameters") or []
    return "structured_outputs" in parametros


def soporta_json_object(modelo: Dict[str, Any]) -> bool:
    """True si la ficha anuncia response_format (modo json_object)."""
    parametros = modelo.get("supported_parameters") or []
    return "response_format" in parametros


def filtrar_modelos_gratuitos(modelos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filtra precio cero y soporte de JSON Schema; ordena por ID."""
    filtrados = [
        modelo for modelo in modelos
        if isinstance(modelo, dict)
        and es_modelo_gratuito(modelo)
        and soporta_json_schema(modelo)
    ]
    return sorted(filtrados, key=lambda m: str(m.get("id", "")).lower())


def _max_salida(modelo: Dict[str, Any]) -> str:
    top = modelo.get("top_provider") or {}
    valor = top.get("max_completion_tokens")
    return str(valor) if valor is not None else "?"


def _contexto(modelo: Dict[str, Any]) -> str:
    valor = modelo.get("context_length")
    return str(valor) if valor is not None else "?"


def _expiracion(modelo: Dict[str, Any]) -> str:
    valor = modelo.get("expiration_date")
    return str(valor) if valor else "-"


def formatear_catalogo(modelos: List[Dict[str, Any]]) -> str:
    """Devuelve una tabla legible de modelos gratuitos con JSON Schema."""
    filtrados = filtrar_modelos_gratuitos(modelos)
    lineas = [
        "Catálogo de OpenRouter: modelos gratuitos con JSON Schema",
        "=" * 90,
        f"Modelos encontrados: {len(filtrados)}",
        "",
    ]
    if not filtrados:
        lineas.append(
            "No se encontraron modelos con precio cero y structured_outputs."
        )
        return "\n".join(lineas)

    lineas.append(
        f"{'ID':<54} {'ctx':>9} {'max_out':>9} {'json_obj':>8} {'expira':>11}"
    )
    lineas.append("-" * 96)
    for modelo in filtrados:
        lineas.append(
            f"{str(modelo.get('id', '?')):<54} "
            f"{_contexto(modelo):>9} "
            f"{_max_salida(modelo):>9} "
            f"{'sí' if soporta_json_object(modelo) else 'no':>8} "
            f"{_expiracion(modelo):>11}"
        )

    solo_objeto = sorted(
        [
            modelo for modelo in modelos
            if isinstance(modelo, dict)
            and es_modelo_gratuito(modelo)
            and soporta_json_object(modelo)
            and not soporta_json_schema(modelo)
        ],
        key=lambda m: str(m.get("id", "")).lower(),
    )
    lineas.extend([
        "",
        "Modelos gratuitos con sólo response_format (json_object, menos "
        f"estricto): {len(solo_objeto)}",
    ])
    for modelo in solo_objeto[:15]:
        lineas.append(f"  - {modelo.get('id')}")
    if len(solo_objeto) > 15:
        lineas.append(f"  ... y {len(solo_objeto) - 15} más")

    lineas.extend([
        "",
        "Notas:",
        "- structured_outputs habilita response_format json_schema.",
        "- response_format habilita el modo json_object (menos estricto).",
        "- El soporte real es por endpoint. ClassIA envía",
        "  provider.require_parameters=true para no enrutar a endpoints",
        "  que no admitan los parámetros pedidos.",
        "- Verificá un modelo concreto con:",
        "  python tools/diagnostico_openrouter_json.py --probar-modelo ID",
    ])
    return "\n".join(lineas)


def obtener_catalogo(timeout: int = TIMEOUT_SEGUNDOS) -> List[Dict[str, Any]]:
    """Descarga el catálogo público. No genera texto ni requiere clave."""
    import requests

    respuesta = requests.get(CATALOGO_URL, timeout=timeout)
    respuesta.raise_for_status()
    cuerpo = respuesta.json()
    datos = cuerpo.get("data") if isinstance(cuerpo, dict) else None
    if not isinstance(datos, list):
        raise ValueError("El catálogo no tiene el formato esperado.")
    return datos


# ---------------------------------------------------------------------------
# Prueba de un modelo (exactamente una solicitud)
# ---------------------------------------------------------------------------

def _texto_de_contenido(mensaje: Any) -> str:
    if not isinstance(mensaje, dict):
        return ""
    contenido = mensaje.get("content")
    if isinstance(contenido, str):
        return contenido.strip()
    if isinstance(contenido, list):
        partes = []
        for parte in contenido:
            if isinstance(parte, dict) and isinstance(parte.get("text"), str):
                partes.append(parte["text"])
            elif isinstance(parte, str):
                partes.append(parte)
        return "".join(partes).strip()
    return ""


def _mensaje_error(cuerpo: Any) -> str:
    if isinstance(cuerpo, dict):
        error = cuerpo.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:300]
        if error:
            return str(error)[:300]
    return ""


def _categoria_por_texto(mensaje: str) -> str:
    bajo = (mensaje or "").lower()
    if any(pista in bajo for pista in ("rate limit", "quota", "429", "too many")):
        return "limite"
    if any(pista in bajo for pista in ("unauthorized", "invalid key", "401", "403")):
        return "auth"
    if any(pista in bajo for pista in (
        "response_format", "structured", "json_schema", "json schema",
        "no endpoints", "not supported", "unsupported",
    )):
        return "no_soportado"
    return "proveedor"


def validar_esquema_prueba(datos: Any) -> Tuple[bool, str]:
    """Valida el objeto mínimo pedido en la prueba."""
    if not isinstance(datos, dict):
        return False, "la respuesta no es un objeto JSON."
    if set(datos.keys()) != {"ok", "campo"}:
        return False, f"claves inesperadas: {sorted(datos.keys())}."
    if datos.get("ok") is not True:
        return False, "'ok' no es el booleano true."
    if datos.get("campo") != "prueba":
        return False, "'campo' no es la cadena 'prueba'."
    return True, ""


def evaluar_respuesta(
    status: int,
    cuerpo: Any,
    modelo_solicitado: str,
) -> Dict[str, Any]:
    """
    Clasifica una respuesta HTTP de OpenRouter sin imprimir ni guardar nada.

    Devuelve un diccionario con ok, categoria, detalle, modelo_real,
    finish_reason, native_finish_reason, proveedor, usage y datos (sólo si la
    validación fue correcta). No imprime ni guarda la clave.
    """
    modelo_real = ""
    if isinstance(cuerpo, dict):
        modelo_real = str(cuerpo.get("model") or "")
    base: Dict[str, Any] = {
        "ok": False,
        "categoria": "proveedor",
        "detalle": "",
        "modelo_real": modelo_real or "(no informado)",
        "finish_reason": "",
        "native_finish_reason": "",
        "proveedor": "",
        "usage": _uso_tokens(cuerpo),
        "datos": None,
    }
    if isinstance(cuerpo, dict):
        proveedor = cuerpo.get("provider")
        if isinstance(proveedor, str) and proveedor.strip():
            base["proveedor"] = proveedor.strip()

    if status in (401, 403):
        base.update(categoria="auth", detalle=(
            f"HTTP {status}: clave inválida o sin permisos. "
            "Revisá OPENROUTER_API_KEY en .env."
        ))
        return base
    if status in (402, 429):
        base.update(categoria="limite", detalle=(
            f"HTTP {status}: saldo insuficiente o límite de uso alcanzado. "
            "Esperá o revisá la cuota del modelo."
        ))
        return base
    if status == 404:
        base.update(categoria="no_soportado", detalle=(
            f"HTTP 404: el modelo '{modelo_solicitado}' no existe o no tiene "
            "endpoints que admitan los parámetros pedidos."
        ))
        return base
    if status in (400, 422):
        detalle = _mensaje_error(cuerpo)
        base.update(categoria="no_soportado", detalle=(
            f"HTTP {status}: solicitud rechazada. Posible falta de soporte de "
            f"JSON Schema o parámetro no admitido. {detalle}".strip()
        ))
        return base
    if status >= 500:
        base.update(categoria="proveedor", detalle=(
            f"HTTP {status}: error del servidor o del proveedor."
        ))
        return base
    if status != 200:
        base.update(categoria="proveedor", detalle=(
            f"HTTP {status}: respuesta inesperada. "
            f"{_mensaje_error(cuerpo)}".strip()
        ))
        return base

    if isinstance(cuerpo, dict) and cuerpo.get("error"):
        detalle = _mensaje_error(cuerpo) or "error sin detalle"
        base.update(
            categoria=_categoria_por_texto(detalle),
            detalle=f"HTTP 200 con error lógico: {detalle}",
        )
        return base

    if not isinstance(cuerpo, dict):
        base.update(categoria="json_invalido", detalle=(
            "HTTP 200 pero el cuerpo no es JSON."
        ))
        return base

    opciones = cuerpo.get("choices")
    if not isinstance(opciones, list) or not opciones:
        base.update(categoria="respuesta_vacia", detalle=(
            "HTTP 200 sin 'choices'."
        ))
        return base

    opcion = opciones[0] if isinstance(opciones[0], dict) else {}
    mensaje = opcion.get("message") or {}
    motivo = opcion.get("finish_reason")
    nativo = opcion.get("native_finish_reason")
    base["finish_reason"] = str(motivo or "")
    base["native_finish_reason"] = str(nativo or "")
    texto = _texto_de_contenido(mensaje)
    hubo_razonamiento = bool(
        isinstance(mensaje, dict)
        and (mensaje.get("reasoning") or mensaje.get("reasoning_details"))
    )

    if motivo == "length":
        detalle = (
            "finish_reason=length: la respuesta se cortó por límite de tokens."
        )
        uso = base.get("usage") or {}
        if uso.get("reasoning_tokens") is not None:
            detalle += (
                f" Tokens de razonamiento: {uso['reasoning_tokens']}; "
                f"salida visible: {uso.get('visible_output_tokens', 'n/d')}."
            )
            if uso.get("visible_output_tokens") == 0:
                detalle += (
                    " El presupuesto se agotó en razonamiento antes de "
                    "producir el JSON final."
                )
        base.update(categoria="truncada", detalle=detalle)
        return base
    if motivo == "content_filter":
        base.update(categoria="respuesta_vacia", detalle=(
            "finish_reason=content_filter: el contenido fue bloqueado."
        ))
        return base
    if not texto:
        if hubo_razonamiento:
            detalle = (
                "El modelo devolvió razonamiento pero ningún contenido final "
                "(message.content vacío)."
            )
            uso = base.get("usage") or {}
            if uso.get("reasoning_tokens") is not None:
                detalle += (
                    f" Tokens de razonamiento: {uso['reasoning_tokens']}."
                )
            base.update(categoria="solo_razonamiento", detalle=detalle)
        else:
            base.update(categoria="respuesta_vacia", detalle=(
                f"message.content vacío (finish_reason={motivo})."
            ))
        return base

    limpio = texto.strip()
    if limpio.startswith("```"):
        lineas = limpio.splitlines()
        if lineas and lineas[0].strip().startswith("```"):
            lineas = lineas[1:]
        if lineas and lineas[-1].strip().startswith("```"):
            lineas = lineas[:-1]
        limpio = "\n".join(lineas).strip()

    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError as e:
        base.update(categoria="json_invalido", detalle=(
            f"JSON inválido o truncado: {e.msg} (posición {e.pos})."
        ))
        return base

    ok, detalle = validar_esquema_prueba(datos)
    if not ok:
        base.update(categoria="esquema_invalido", detalle=detalle)
        return base

    base.update(
        ok=True,
        categoria="ok",
        detalle="JSON válido y esquema mínimo cumplido.",
        datos=datos,
    )
    return base


def construir_solicitud_prueba(
    modelo: str,
    max_tokens: int = MAX_TOKENS_PRUEBA,
    desactivar_razonamiento: bool = False,
) -> Dict[str, Any]:
    """
    Payload de la única solicitud de prueba.

    `max_tokens` es el límite total de la prueba (razonamiento + salida). No
    modifica TOKEN_MAX_SALIDA. `desactivar_razonamiento` sólo se debe usar si
    la ficha del modelo indica `reasoning.mandatory=false`; en ese caso se
    envía `reasoning.enabled=false`, el único control de razonamiento que el
    catálogo anuncia para modelos sin `supported_efforts` ni
    `supports_max_tokens`.
    """
    payload: Dict[str, Any] = {
        "model": modelo,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Responde únicamente con JSON válido. No uses markdown ni "
                    "agregues texto fuera del JSON."
                ),
            },
            {"role": "user", "content": PROMPT_PRUEBA},
        ],
        "temperature": 0,
        "max_tokens": int(max_tokens),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "prueba_openrouter_json",
                "strict": True,
                "schema": ESQUEMA_PRUEBA,
            },
        },
        "provider": {"require_parameters": True},
    }
    if desactivar_razonamiento:
        payload["reasoning"] = {"enabled": False}
    return payload


def probar_modelo(
    modelo: str,
    api_key: Optional[str] = None,
    max_tokens: int = MAX_TOKENS_PRUEBA,
    desactivar_razonamiento: bool = False,
) -> int:
    """Hace exactamente una solicitud al modelo y muestra el resultado."""
    import requests

    clave = (api_key if api_key is not None else OPENROUTER_API_KEY) or ""
    print("Prueba de salida JSON en OpenRouter")
    print("=" * 78)
    print(f"Modelo solicitado: {modelo}")
    print(f"Clave configurada: {'sí (oculta)' if clave else 'NO'}")
    print("Solicitudes que se realizarán: 1 (sin reintentos ni fallback)")
    print(f"Límite solicitado (max_tokens): {max_tokens}")
    print(
        "Razonamiento solicitado: "
        + (
            "desactivado (reasoning.enabled=false)"
            if desactivar_razonamiento
            else "no especificado (predeterminado del modelo)"
        )
    )
    print("Formato solicitado: json_schema (strict=True)")
    print("")

    if not clave:
        print("ERROR: falta OPENROUTER_API_KEY en .env.")
        print("No se realizó ninguna solicitud.")
        return 2

    solicitud = construir_solicitud_prueba(
        modelo,
        max_tokens=max_tokens,
        desactivar_razonamiento=desactivar_razonamiento,
    )
    headers = {
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": "https://localhost/aula-ia",
        "X-Title": "Aula IA - diagnóstico JSON",
    }

    try:
        respuesta = requests.post(
            CHAT_URL,
            headers=headers,
            json=solicitud,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.Timeout:
        print(f"ERROR: sin respuesta en {TIMEOUT_SEGUNDOS} segundos.")
        return 1
    except requests.ConnectionError as e:
        print(f"ERROR de conexión: {e}")
        return 1
    except requests.RequestException as e:
        print(f"ERROR de red: {e}")
        return 1

    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = None

    resultado = evaluar_respuesta(respuesta.status_code, cuerpo, modelo)
    uso = resultado.get("usage") or {}

    print(f"Estado HTTP: {respuesta.status_code}")
    print(f"Modelo informado por OpenRouter: {resultado['modelo_real']}")
    if resultado.get("proveedor"):
        print(f"Proveedor informado: {resultado['proveedor']}")
    print(f"finish_reason: {resultado['finish_reason'] or '(no informado)'}")
    if resultado.get("native_finish_reason"):
        print(
            "native_finish_reason: "
            f"{resultado['native_finish_reason']}"
        )
    print("Uso de tokens informado por la API:")
    for linea in _describir_uso(uso):
        print(linea)
    print(f"Categoría: {resultado['categoria']}")
    print(f"Detalle: {resultado['detalle']}")
    if (
        resultado["categoria"] == "truncada"
        and uso.get("reasoning_tokens") is not None
        and uso.get("visible_output_tokens") == 0
    ):
        print("")
        print(
            "CAUSA PROBABLE: el modelo consumió todo el presupuesto de "
            "max_tokens en razonamiento y no dejó tokens para el JSON final. "
            "Para esta prueba, usá --sin-razonamiento (sólo si la ficha del "
            "modelo indica mandatory=false) o --max-tokens con un valor mayor."
        )
    if resultado["ok"]:
        print("")
        print("VALIDACIÓN: OK")
        print("Objeto recibido:")
        print(json.dumps(resultado["datos"], ensure_ascii=False, indent=2))
        print("")
        print(
            "El modelo devolvió contenido final, JSON parseable y el esquema "
            "mínimo se cumple."
        )
        return 0

    print("")
    print("VALIDACIÓN: FALLÓ")
    sugerencias = {
        "auth": "Revisá la clave en .env y sus permisos.",
        "limite": "Esperá o usá otro modelo gratuito del catálogo.",
        "no_soportado": (
            "El modelo no admite JSON Schema en sus endpoints. Probá otro "
            "modelo con structured_outputs o configurá "
            "OPENROUTER_RESPONSE_FORMAT=json_object."
        ),
        "proveedor": "Error transitorio o del proveedor. Probá más tarde.",
        "respuesta_vacia": (
            "El modelo no devolvió contenido final. Probá otro modelo o "
            "revisá si exige razonamiento."
        ),
        "solo_razonamiento": (
            "El modelo sólo devolvió razonamiento. No es una respuesta "
            "utilizable; probá otro modelo."
        ),
        "truncada": (
            "La prueba se cortó por max_tokens. Si el modelo razona, probá "
            "--sin-razonamiento (sólo si la ficha indica mandatory=false) o "
            "--max-tokens mayor; esto no cambia TOKEN_MAX_SALIDA ni .env."
        ),
        "json_invalido": "El modelo no respetó el JSON. Probá otro modelo.",
        "esquema_invalido": (
            "El JSON no cumple el esquema mínimo. No debe aceptarse como "
            "respuesta válida."
        ),
    }
    print(f"Sugerencia: {sugerencias.get(resultado['categoria'], 'Revisá el detalle.')}")
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def mostrar_catalogo() -> int:
    print("Consultando el catálogo público de OpenRouter...")
    print(f"URL: {CATALOGO_URL}")
    print("Esta consulta no genera texto ni consume cuota.")
    print("")
    try:
        modelos = obtener_catalogo()
    except Exception as e:
        print(f"ERROR: no se pudo consultar el catálogo: {e}")
        return 1
    print(formatear_catalogo(modelos))
    print("")
    print(f"OPENROUTER_MODEL (preferido): {OPENROUTER_MODEL or '(vacío)'}")
    print("OPENROUTER_MODELS (candidatos):")
    for modelo in OPENROUTER_MODELS:
        print(f"  - {modelo}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnóstico manual de OpenRouter: catálogo gratuito con JSON "
            "Schema o una única solicitud de prueba."
        )
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--catalogo",
        action="store_true",
        help="consultar el catálogo (predeterminado; no genera texto).",
    )
    grupo.add_argument(
        "--probar-modelo",
        metavar="ID",
        help="hacer UNA sola solicitud pequeña al modelo indicado.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=MAX_TOKENS_PRUEBA,
        metavar="N",
        help=(
            "límite de tokens para la prueba (predeterminado: "
            f"{MAX_TOKENS_PRUEBA}). No cambia TOKEN_MAX_SALIDA ni .env."
        ),
    )
    parser.add_argument(
        "--sin-razonamiento",
        action="store_true",
        help=(
            "enviar reasoning.enabled=false; usalo sólo si la ficha del "
            "modelo indica reasoning.mandatory=false."
        ),
    )
    args = parser.parse_args(argv)

    if args.max_tokens < 1:
        print("ERROR: --max-tokens debe ser un entero mayor o igual a 1.")
        return 2
    if not args.probar_modelo and (
        args.max_tokens != MAX_TOKENS_PRUEBA or args.sin_razonamiento
    ):
        print(
            "ERROR: --max-tokens y --sin-razonamiento sólo se aplican con "
            "--probar-modelo."
        )
        return 2

    if args.probar_modelo:
        return probar_modelo(
            args.probar_modelo,
            max_tokens=args.max_tokens,
            desactivar_razonamiento=args.sin_razonamiento,
        )
    return mostrar_catalogo()


if __name__ == "__main__":
    raise SystemExit(main())
