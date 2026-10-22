
"""
Proveedores de inteligencia artificial.

Implementa adaptadores para Gemini (google-genai), NVIDIA NIM, Groq y
OpenRouter (API REST compatible con OpenAI). Incluye clasificación de errores,
validación local de esquemas y orden de proveedores configurable.
"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from datetime import datetime

from configuracion import (
    GEMINI_API_KEY, GEMINI_MODEL,
    NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODELS,
    NVIDIA_RESPONSE_FORMAT,
    GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODELS, GROQ_RESPONSE_FORMAT,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_MODELS,
    OPENROUTER_RESPONSE_FORMAT,
    OMNIROUTE_BASE_URL, OMNIROUTE_API_KEY, OMNIROUTE_MODEL,
    TIMEOUT_SEGUNDOS, MAX_REINTENTOS, TOKEN_MAX_SALIDA,
    proveedor_esta_configurado, motivo_proveedor_no_configurado,
)

logger = logging.getLogger(__name__)


def _limpiar_cercas_markdown(texto: str) -> str:
    """Quita las cercas ``` que algunos modelos agregan alrededor del JSON."""
    limpio = (texto or "").strip()
    if not limpio.startswith("```"):
        return limpio
    lineas = limpio.splitlines()
    if lineas and lineas[0].strip().startswith("```"):
        lineas = lineas[1:]
    if lineas and lineas[-1].strip().startswith("```"):
        lineas = lineas[:-1]
    return "\n".join(lineas).strip()


class ErrorIA(Exception):
    """Excepción base para errores de los proveedores de IA."""
    pass


class ErrorClaveInvalida(ErrorIA):
    """La clave de API no es válida."""
    pass


class ErrorCuotaAgotada(ErrorIA):
    """Se agotó la cuota disponible del proveedor."""
    pass


class ErrorLimiteSolicitudes(ErrorCuotaAgotada):
    """
    El proveedor rechazó la solicitud por límite de solicitudes (429).

    Es una subclase de ErrorCuotaAgotada para que los flujos existentes sigan
    tratándolo como un error recuperable, pero permite distinguir un límite
    temporal de un agotamiento de cuota.
    """
    pass


class ErrorRed(ErrorIA):
    """Problema de conectividad de red."""
    pass


class ErrorTimeout(ErrorRed):
    """El proveedor no respondió dentro del tiempo configurado."""
    pass


class ErrorServidor(ErrorIA):
    """Error del servidor del proveedor."""
    pass


class ErrorRespuestaIncompleta(ErrorIA):
    """La respuesta del modelo está incompleta o no es JSON válido."""
    pass


class ErrorRespuestaVacia(ErrorRespuestaIncompleta):
    """El proveedor respondió con éxito pero sin contenido final."""
    pass


class ErrorRespuestaTruncada(ErrorRespuestaIncompleta):
    """El proveedor cortó la respuesta por el límite de tokens."""
    pass


class ErrorJSONInvalido(ErrorRespuestaIncompleta):
    """El texto recibido no puede analizarse como JSON."""
    pass


class ErrorIntegracion(ErrorIA):
    """
    Error de programación o de integración con el SDK del proveedor.

    No es un problema del contenido devuelto por el modelo (JSON truncado,
    cuota, red). Indica que el código llama a la API de forma incorrecta,
    por ejemplo con un argumento no admitido por la versión instalada.
    No debe reintentarse ni interpretarse como respuesta del modelo.
    """
    pass


class ErrorContenidoNoJson(ErrorIA):
    """
    El proveedor respondió con éxito pero su texto no es un objeto JSON.

    Cubre casos como mensajes de seguridad ("User Safety: safe") o
    explicaciones en lenguaje natural. No es un error de comunicación, ni
    una respuesta vacía, ni un JSON truncado: es contenido que no puede
    analizarse como JSON y debe regenerarse pidiendo sólo el JSON.
    """
    pass


class ErrorRespuestaInvalida(ErrorIA):
    """
    La respuesta es JSON válido pero no cumple el esquema de ClassIA.

    No alcanza con que el JSON se pueda analizar: deben estar todos los
    campos obligatorios y con el tipo esperado. Este error es recuperable
    probando el siguiente modelo de OpenRouter.
    """
    pass


class ErrorModeloNoDisponible(ErrorIA):
    """
    El modelo no existe o ningún endpoint admite los parámetros requeridos.

    Es recuperable probando el siguiente modelo, pero no tiene sentido volver
    a intentarlo en los bloques siguientes de la misma ejecución.
    """
    pass


class ErrorModelosAgotados(ErrorIA):
    """
    Se probaron todos los modelos gratuitos configurados sin éxito.

    El flujo de bloques no debe reintentar esta solicitud: el límite de
    intentos es global por solicitud lógica (cada modelo se prueba una vez).
    Los bloques ya validados quedan guardados para reanudar el trabajo.
    """
    pass


def clasificar_error(excepcion: Exception) -> ErrorIA:
    """
    Clasifica una excepción genérica en un tipo específico de ErrorIA.

    Un error de programación (TypeError, AttributeError, NameError,
    ImportError) se clasifica como ErrorIntegracion: nunca es una
    respuesta del modelo y no debe tratarse como JSON truncado.

    Si la excepción trae un código HTTP (como los errores del SDK de
    Gemini), se usa ese código para clasificar con precisión: los 5xx
    (incluido el 504 DEADLINE_EXCEEDED) son errores del servidor y son
    transitorios, no respuestas del modelo.
    """
    if isinstance(excepcion, (TypeError, AttributeError, NameError, ImportError)):
        return ErrorIntegracion(
            f"Error de integración con el SDK: {type(excepcion).__name__}: {excepcion}"
        )

    codigo = getattr(excepcion, "code", None)
    if isinstance(codigo, int):
        if codigo in (401, 403):
            return ErrorClaveInvalida(str(excepcion))
        if codigo == 404:
            return ErrorModeloNoDisponible(str(excepcion))
        if codigo == 408:
            return ErrorTimeout(str(excepcion))
        if codigo == 429:
            return ErrorLimiteSolicitudes(str(excepcion))
        if 500 <= codigo < 600:
            return ErrorServidor(str(excepcion))

    mensaje = str(excepcion).lower()

    if "api key" in mensaje or "authentication" in mensaje or "unauthorized" in mensaje or "401" in mensaje or "403" in mensaje:
        return ErrorClaveInvalida(str(excepcion))
    if (
        "model not found" in mensaje or "model does not exist" in mensaje
        or "unknown model" in mensaje or "404" in mensaje
        or "no such model" in mensaje
    ):
        return ErrorModeloNoDisponible(str(excepcion))
    if "quota" in mensaje or "excedido" in mensaje:
        return ErrorCuotaAgotada(str(excepcion))
    if "rate limit" in mensaje or "too many requests" in mensaje or "429" in mensaje:
        return ErrorLimiteSolicitudes(str(excepcion))
    if (
        "500" in mensaje or "502" in mensaje or "503" in mensaje
        or "504" in mensaje or "server" in mensaje or "deadline" in mensaje
    ):
        return ErrorServidor(str(excepcion))
    if "timed out" in mensaje or "timeout" in mensaje:
        return ErrorTimeout(str(excepcion))
    if "connection" in mensaje or "network" in mensaje:
        return ErrorRed(str(excepcion))
    if "truncat" in mensaje or "incomplet" in mensaje:
        return ErrorRespuestaTruncada(str(excepcion))
    if "schema" in mensaje or "validación" in mensaje or "validation" in mensaje:
        return ErrorRespuestaInvalida(str(excepcion))
    if "json" in mensaje:
        return ErrorJSONInvalido(str(excepcion))

    return ErrorIA(str(excepcion))


def _codigo_http(excepcion: Exception) -> Optional[int]:
    """Extrae un código HTTP de una excepción o respuesta simulada."""
    for atributo in ("status_code", "code"):
        valor = getattr(excepcion, atributo, None)
        if isinstance(valor, int):
            return valor
    return None


def cuota_es_persistente(mensaje: str) -> bool:
    """
    Indica si un error de cuota parece agotamiento diario (no transitorio).

    Los 429 de Google incluyen marcas como "PerDay" o un retardo de reintento
    de horas ("retry in 18h..."). En esos casos reintentar en el mismo
    proveedor no sirve: conviene pasar a otro proveedor y recordar el
    agotamiento durante el resto de la ejecución.
    """
    texto = (mensaje or "").lower()
    if ("perday" in texto or "per_day" in texto or "per day" in texto
            or "per-day" in texto):
        return True
    coincidencia = re.search(r"retry in (\d+)\s*h", texto)
    if coincidencia and int(coincidencia.group(1)) >= 1:
        return True
    return False


def _resumen_error_http(respuesta: Any) -> str:
    """Extrae un mensaje breve del cuerpo de error, sin datos sensibles."""
    try:
        datos = respuesta.json()
    except Exception:
        return (getattr(respuesta, "text", "") or "")[:200]
    if isinstance(datos, dict):
        error = datos.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:200]
        if error:
            return str(error)[:200]
    return (getattr(respuesta, "text", "") or "")[:200]


# ---------------------------------------------------------------------------
# Proveedor: Gemini (google-genai SDK)
# ---------------------------------------------------------------------------

def _opciones_http_gemini() -> Any:
    """
    Construye las HttpOptions del cliente de Gemini.

    La versión instalada de google-genai (2.31.0) NO admite `timeout`
    ni `request_options` en `models.generate_content()`. El tiempo de
    espera HTTP se configura al crear el cliente, en milisegundos.

    Se configuran además reintentos acotados a nivel del SDK, con pausas
    progresivas. Sin `retry_options`, el SDK usa `stop_after_attempt(1)`:
    un 504 transitorio se propaga de inmediato. `attempts=3` incluye el
    intento inicial, de modo que no se multiplican reintentos con el
    bucle de bloques de ClassIA.
    """
    from google.genai import types

    return types.HttpOptions(
        timeout=int(TIMEOUT_SEGUNDOS) * 1000,
        retry_options=types.HttpRetryOptions(
            attempts=3,             # incluye el intento inicial (2 reintentos)
            initial_delay=1.0,
            max_delay=8.0,
            exp_base=2,
            jitter=1,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        ),
    )


def _crear_cliente_gemini(api_key: str) -> Any:
    """Crea el cliente de Gemini con el timeout HTTP configurado."""
    from google import genai

    return genai.Client(api_key=api_key, http_options=_opciones_http_gemini())


def generar_con_gemini(
    instruccion: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    Envía una solicitud a Gemini y devuelve el texto de respuesta.

    Utiliza salida estructurada (JSON) cuando el modelo lo admite.

    Los errores del SDK se propagan como ErrorIA. Nunca se devuelve el
    mensaje de una excepción como si fuera contenido del modelo.
    """
    if not api_key:
        api_key = GEMINI_API_KEY
    if not modelo:
        modelo = GEMINI_MODEL

    if not api_key:
        raise ErrorClaveInvalida("No se configuró GEMINI_API_KEY")

    try:
        from google.genai import types

        client = _crear_cliente_gemini(api_key)

        # Intenta salida estructurada con esquema JSON
        configuracion_generacion = types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=TOKEN_MAX_SALIDA,
            response_mime_type="application/json",
            system_instruction=(
                "Responde ÚNICAMENTE con un objeto JSON válido. "
                "No uses bloques de código markdown. No agregues texto fuera del JSON."
            ),
        )

        logger.info(
            f"Enviando solicitud a Gemini: modelo={modelo}, "
            f"longitud_instruccion={len(instruccion)}, "
            f"timeout_ms={int(TIMEOUT_SEGUNDOS) * 1000}"
        )

        respuesta = client.models.generate_content(
            model=modelo,
            contents=instruccion,
            config=configuracion_generacion,
        )

        if respuesta and respuesta.text:
            logger.info(f"Respuesta recibida de Gemini: longitud={len(respuesta.text)}")
            return respuesta.text.strip()

        # Puede haber contenido bloqueado sin texto
        motivo = _motivo_finalizacion_gemini(respuesta)
        if motivo:
            logger.warning(f"Gemini devolvió respuesta vacía. motivo={motivo}")
            if str(motivo).upper() == "MAX_TOKENS":
                raise ErrorRespuestaTruncada(
                    f"Gemini truncó la respuesta por límite de tokens "
                    f"(motivo: {motivo})."
                )
            raise ErrorRespuestaVacia(
                f"Gemini devolvió una respuesta vacía (motivo: {motivo})."
            )

        raise ErrorRespuestaVacia("Gemini devolvió una respuesta vacía.")

    except ErrorIA:
        raise
    except Exception as e:
        logger.error(
            f"Error en Gemini: {type(e).__name__}: {e}", exc_info=True
        )
        raise clasificar_error(e)


def _motivo_finalizacion_gemini(respuesta: Any) -> str:
    """
    Extrae el motivo de finalización de una respuesta de Gemini, si existe.

    Permite distinguir un límite de tokens (MAX_TOKENS) de otros motivos.
    No expone datos sensibles.
    """
    try:
        candidatos = getattr(respuesta, "candidates", None) or []
        if not candidatos:
            return ""
        motivo = getattr(candidatos[0], "finish_reason", None)
        if motivo is None:
            return ""
        return str(getattr(motivo, "name", motivo))
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Utilidades comunes para proveedores compatibles con OpenAI
# ---------------------------------------------------------------------------

def _validar_json_texto(
    texto: str,
    validador: Optional[Callable[[Any], Tuple[bool, List[str]]]],
    proveedor: str = "",
    modelo: str = "",
) -> Any:
    """
    Analiza y valida localmente un texto JSON.

    Un JSON sintácticamente válido no se acepta si el validador de ClassIA lo
    rechaza. La validación local se aplica siempre, aun cuando el proveedor
    haya usado salida estructurada.
    """
    etiqueta = proveedor or "proveedor"
    if modelo:
        etiqueta += f" ({modelo})"
    if not texto or not str(texto).strip():
        raise ErrorRespuestaVacia(f"{etiqueta} devolvió una respuesta vacía.")

    limpio = _limpiar_cercas_markdown(str(texto))
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError as e:
        raise ErrorJSONInvalido(
            f"{etiqueta} devolvió JSON inválido o truncado: {e.msg} "
            f"(posición {e.pos})."
        )
    if not isinstance(datos, (dict, list)):
        raise ErrorRespuestaInvalida(
            f"{etiqueta} devolvió un JSON que no es objeto ni lista."
        )

    if validador is not None:
        try:
            ok, errores = validador(datos)
        except Exception as e:
            raise ErrorRespuestaInvalida(
                f"No se pudo validar la respuesta de {etiqueta} contra el "
                f"esquema: {e}"
            )
        if not ok:
            raise ErrorRespuestaInvalida(
                "; ".join(errores[:5]) or "la respuesta no cumple el esquema."
            )
    return datos


def _solicitar_chat_compatible(
    url: str,
    api_key: str,
    modelo: str,
    instruccion: str,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Realiza exactamente una solicitud a una API compatible con OpenAI.

    No reintenta ni cambia de modelo. Los errores de red se convierten en
    ErrorTimeout/ErrorRed y las respuestas se devuelven sin evaluar para que
    el llamador decida si prueba otro modelo.
    """
    import requests

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": (
                "Responde ÚNICAMENTE con un objeto JSON válido que cumpla "
                "exactamente el esquema solicitado. No uses bloques de código "
                "markdown. No agregues texto fuera del JSON."
            )},
            {"role": "user", "content": instruccion},
        ],
        "temperature": 0.4,
        "max_tokens": TOKEN_MAX_SALIDA,
        "stream": False,
    }
    if extras:
        payload.update(extras)

    try:
        respuesta = requests.post(
            url, headers=headers, json=payload, timeout=TIMEOUT_SEGUNDOS
        )
    except requests.Timeout as e:
        raise ErrorTimeout(
            f"El proveedor no respondió dentro de {TIMEOUT_SEGUNDOS} segundos."
        ) from e
    except requests.ConnectionError as e:
        raise ErrorRed("No se pudo conectar con el proveedor.") from e
    except requests.RequestException as e:
        raise ErrorRed(f"Error de red con el proveedor: {e}") from e

    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = None

    logger.info(
        "Proveedor compatible OpenAI: respuesta HTTP status=%s "
        "modelo_solicitado=%s longitud_cuerpo=%d",
        respuesta.status_code, modelo, len(respuesta.text or ""),
    )
    return {
        "status": respuesta.status_code,
        "cuerpo": cuerpo,
        "texto_crudo": (respuesta.text or "")[:300],
        "modelo_solicitado": modelo,
    }


def _evaluar_respuesta_chat_compatible(
    resultado: Dict[str, Any],
    validador: Optional[Callable[[Any], Tuple[bool, List[str]]]],
    proveedor: str,
) -> Dict[str, Any]:
    """Clasifica y valida una respuesta de una API compatible con OpenAI."""
    status = int(resultado.get("status") or 0)
    cuerpo = resultado.get("cuerpo")
    modelo_solicitado = str(resultado.get("modelo_solicitado") or "")
    mensaje_error = _mensaje_error_openrouter(cuerpo)
    texto_crudo = (resultado.get("texto_crudo") or "").strip()

    if status in (401, 403):
        raise ErrorClaveInvalida(
            f"Clave de {proveedor} inválida o sin permisos (HTTP {status})."
        )
    if status == 404:
        raise ErrorModeloNoDisponible(
            f"Modelo de {proveedor} no disponible (404): "
            f"'{modelo_solicitado}'."
        )
    if status == 429:
        raise ErrorLimiteSolicitudes(
            f"{proveedor} rechazó la solicitud por límite de solicitudes "
            f"(429). Detalle: {mensaje_error or 'sin detalle'}"
        )
    if status in (400, 422):
        raise ErrorModeloNoDisponible(
            f"{proveedor} rechazó la solicitud (HTTP {status}) para "
            f"'{modelo_solicitado}': {mensaje_error or texto_crudo or 'sin detalle'}"
        )
    if status >= 500:
        raise ErrorServidor(
            f"Error del servidor de {proveedor} (HTTP {status}) para "
            f"'{modelo_solicitado}'."
        )
    if status != 200:
        raise ErrorIA(
            f"Error de {proveedor} (HTTP {status}) para "
            f"'{modelo_solicitado}': {mensaje_error or texto_crudo or 'sin detalle'}"
        )

    if isinstance(cuerpo, dict) and cuerpo.get("error"):
        detalle = mensaje_error or "error sin detalle"
        bajo = detalle.lower()
        if "unauthorized" in bajo or "api key" in bajo or "authentication" in bajo:
            raise ErrorClaveInvalida(f"{proveedor}: {detalle}")
        if "model" in bajo and ("not found" in bajo or "does not exist" in bajo):
            raise ErrorModeloNoDisponible(f"{proveedor}: {detalle}")
        if "quota" in bajo:
            raise ErrorCuotaAgotada(f"{proveedor}: {detalle}")
        if "rate limit" in bajo or "too many requests" in bajo or "429" in bajo:
            raise ErrorLimiteSolicitudes(f"{proveedor}: {detalle}")
        raise ErrorIA(f"{proveedor} devolvió un error lógico: {detalle}")

    opciones = cuerpo.get("choices") if isinstance(cuerpo, dict) else None
    if not isinstance(opciones, list) or not opciones:
        raise ErrorRespuestaVacia(
            f"{proveedor} no devolvió 'choices' en la respuesta."
        )

    opcion = opciones[0] if isinstance(opciones[0], dict) else {}
    mensaje = opcion.get("message") or {}
    if not isinstance(mensaje, dict):
        mensaje = {}
    texto = _texto_de_contenido_openrouter(mensaje)
    motivo = opcion.get("finish_reason")
    hubo_razonamiento = bool(
        mensaje.get("reasoning") or mensaje.get("reasoning_details")
    )

    if motivo == "length":
        raise ErrorRespuestaTruncada(
            f"{proveedor} truncó la respuesta por límite de tokens "
            "(finish_reason=length)."
        )
    if motivo == "content_filter":
        raise ErrorRespuestaIncompleta(
            f"{proveedor} bloqueó la respuesta por el filtro de contenido "
            "(finish_reason=content_filter)."
        )
    if not texto:
        detalle = f"contenido final vacío (finish_reason={motivo})"
        if hubo_razonamiento:
            detalle += "; el modelo sólo devolvió razonamiento"
        raise ErrorRespuestaVacia(f"{proveedor} devolvió {detalle}.")

    _validar_json_texto(texto, validador, proveedor, modelo_solicitado)

    modelo_real = ""
    if isinstance(cuerpo, dict):
        modelo_real = str(cuerpo.get("model") or "")
    logger.info(
        "%s: validación local OK modelo_solicitado=%s modelo_real=%s "
        "finish_reason=%s longitud_contenido=%d",
        proveedor, modelo_solicitado,
        modelo_real or "(no informado)", motivo, len(texto),
    )
    return {
        "texto": texto,
        "modelo_real": modelo_real or modelo_solicitado,
        "finish_reason": motivo,
    }


def _extras_nvidia(
    esquema: Optional[Dict[str, Any]], nombre_esquema: str, estricto: bool
) -> Dict[str, Any]:
    """Construye el formato de salida estructurada para NVIDIA NIM."""
    if NVIDIA_RESPONSE_FORMAT == "guided_json" and esquema:
        # Documentación oficial de NIM: nvext.guided_json es el mecanismo
        # recomendado para restringir la salida a un JSON Schema.
        return {"nvext": {"guided_json": esquema}}
    if NVIDIA_RESPONSE_FORMAT == "json_object":
        return {"response_format": {"type": "json_object"}}
    return {}


def _extras_groq(
    esquema: Optional[Dict[str, Any]], nombre_esquema: str, estricto: bool
) -> Dict[str, Any]:
    """Construye el formato de salida estructurada para Groq."""
    if GROQ_RESPONSE_FORMAT == "json_schema" and esquema:
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": nombre_esquema or "respuesta_classia",
                    "strict": bool(estricto),
                    "schema": esquema,
                },
            }
        }
    if GROQ_RESPONSE_FORMAT == "json_object":
        return {"response_format": {"type": "json_object"}}
    return {}


def _generar_estructurado_compatible(
    proveedor: str,
    base_url: str,
    api_key: str,
    modelos: List[str],
    instruccion: str,
    esquema: Optional[Dict[str, Any]],
    nombre_esquema: str,
    estricto: bool,
    validador: Optional[Callable[[Any], Tuple[bool, List[str]]]],
    etapa: str,
    modelos_agotados: Optional[Set[str]],
    construir_extras: Callable[[Optional[Dict[str, Any]], str, bool],
                                Dict[str, Any]],
) -> Tuple[str, str]:
    """
    Recorre los modelos candidatos de un proveedor compatible con OpenAI.

    - Un error de autenticación, red, límite de solicitudes o servidor afecta
      al proveedor y no se reintenta con cada modelo.
    - Un modelo inexistente o que rechaza el formato se omite y se prueba el
      siguiente candidato habilitado.
    - Un problema de contenido (vacío, truncado, JSON inválido o esquema) se
      intenta con el siguiente modelo.
    """
    if not api_key:
        raise ErrorClaveInvalida(f"No se configuró la clave de {proveedor}.")
    lista = [m.strip() for m in (modelos or []) if m and m.strip()]
    if not lista:
        raise ErrorModelosAgotados(
            f"No hay modelos configurados para {proveedor}."
        )

    url = f"{base_url.rstrip('/')}/chat/completions"
    errores: List[str] = []
    for indice, modelo in enumerate(lista, 1):
        if modelos_agotados is not None and modelo in modelos_agotados:
            errores.append(f"{modelo}: omitido (no disponible).")
            continue

        try:
            logger.info(
                "%s: solicitud etapa=%s intento=%d/%d modelo=%s",
                proveedor, etapa or "sin_etapa", indice, len(lista), modelo,
            )
            resultado = _solicitar_chat_compatible(
                url=url,
                api_key=api_key,
                modelo=modelo,
                instruccion=instruccion,
                extras=construir_extras(esquema, nombre_esquema, estricto),
            )
            evaluado = _evaluar_respuesta_chat_compatible(
                resultado, validador, proveedor
            )
            logger.info(
                "%s: respuesta aceptada etapa=%s modelo_real=%s status=%d",
                proveedor, etapa or "sin_etapa",
                evaluado["modelo_real"], resultado.get("status"),
            )
            return evaluado["texto"], evaluado["modelo_real"]

        except (
            ErrorClaveInvalida, ErrorRed, ErrorServidor,
            ErrorCuotaAgotada, ErrorIntegracion,
        ):
            # Errores del proveedor o de la cuenta: no tiene sentido probar
            # cada modelo restante.
            raise
        except ErrorModeloNoDisponible as e:
            if modelos_agotados is not None:
                modelos_agotados.add(modelo)
            errores.append(f"{modelo}: {e}")
            logger.warning(
                "%s: modelo %s no disponible; se prueba el siguiente.",
                proveedor, modelo,
            )
            continue
        except ErrorIA as e:
            errores.append(f"{modelo}: {type(e).__name__}: {e}")
            logger.warning(
                "%s: intento %d/%d con %s falló (%s). Se prueba el siguiente.",
                proveedor, indice, len(lista), modelo, type(e).__name__,
            )
            continue

    detalle = "\n".join(errores) if errores else "No se intentó ningún modelo."
    logger.error(
        "%s: se agotaron los modelos configurados para la etapa %s.\n%s",
        proveedor, etapa or "sin_etapa", detalle,
    )
    raise ErrorModelosAgotados(
        f"Se agotaron los modelos configurados de {proveedor} sin una "
        f"respuesta válida para la etapa '{etapa or 'sin_etapa'}'.\n" + detalle
    )


def generar_con_nvidia_estructurado(
    instruccion: str,
    esquema: Dict[str, Any],
    nombre_esquema: str,
    estricto: bool,
    validador: Optional[Callable[[Any], Tuple[bool, List[str]]]],
    etapa: str = "",
    modelos: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    modelos_agotados: Optional[Set[str]] = None,
) -> Tuple[str, str]:
    """
    Genera contenido estructurado con NVIDIA NIM directamente.

    No depende de OmniRoute ni de OpenRouter. La URL base y la clave se leen
    de la configuración; nunca se imprimen.
    """
    return _generar_estructurado_compatible(
        proveedor="NVIDIA",
        base_url=NVIDIA_BASE_URL,
        api_key=api_key if api_key is not None else NVIDIA_API_KEY,
        modelos=list(modelos) if modelos is not None else list(NVIDIA_MODELS),
        instruccion=instruccion,
        esquema=esquema,
        nombre_esquema=nombre_esquema,
        estricto=estricto,
        validador=validador,
        etapa=etapa,
        modelos_agotados=modelos_agotados,
        construir_extras=_extras_nvidia,
    )


def generar_con_groq_estructurado(
    instruccion: str,
    esquema: Dict[str, Any],
    nombre_esquema: str,
    estricto: bool,
    validador: Optional[Callable[[Any], Tuple[bool, List[str]]]],
    etapa: str = "",
    modelos: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    modelos_agotados: Optional[Set[str]] = None,
) -> Tuple[str, str]:
    """Genera contenido estructurado con Groq directamente."""
    return _generar_estructurado_compatible(
        proveedor="Groq",
        base_url=GROQ_BASE_URL,
        api_key=api_key if api_key is not None else GROQ_API_KEY,
        modelos=list(modelos) if modelos is not None else list(GROQ_MODELS),
        instruccion=instruccion,
        esquema=esquema,
        nombre_esquema=nombre_esquema,
        estricto=estricto,
        validador=validador,
        etapa=etapa,
        modelos_agotados=modelos_agotados,
        construir_extras=_extras_groq,
    )


# ---------------------------------------------------------------------------
# Proveedor: OpenRouter (API REST compatible con OpenAI)
# ---------------------------------------------------------------------------

def generar_con_openrouter(
    instruccion: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    Envía una solicitud a OpenRouter usando su endpoint de chat.

    Devuelve el texto de la respuesta del modelo.
    """
    import requests

    if not api_key:
        api_key = OPENROUTER_API_KEY
    if not modelo:
        modelo = OPENROUTER_MODEL

    if not api_key:
        raise ErrorClaveInvalida("No se configuró OPENROUTER_API_KEY")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/aula-ia",
        "X-Title": "Aula IA",
    }
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": (
                "Responde ÚNICAMENTE con un objeto JSON válido. "
                "No uses bloques de código markdown. No agregues texto fuera del JSON."
            )},
            {"role": "user", "content": instruccion},
        ],
        "temperature": 0.4,
        "max_tokens": TOKEN_MAX_SALIDA,
        # Modo JSON nativo. Además de mejorar el cumplimiento, hace que
        # "openrouter/free" sólo enrute a modelos que admiten JSON, en lugar de
        # elegir al azar modelos que devuelven texto libre o vacío.
        "response_format": {"type": "json_object"},
    }

    try:
        logger.info(f"Enviando solicitud a OpenRouter: modelo={modelo}, longitud_instruccion={len(instruccion)}")

        respuesta = requests.post(
            url, headers=headers, json=payload, timeout=TIMEOUT_SEGUNDOS
        )

        logger.info(f"Respuesta de OpenRouter: status={respuesta.status_code}, longitud_texto={len(respuesta.text)}")

        # Algunos endpoints rechazan parámetros opcionales. Puede llegar como
        # 400/404/422 o incluso como HTTP 200 con un objeto "error" (por
        # ejemplo: "Reasoning is mandatory for this endpoint and cannot be
        # disabled"). En esos casos se reintenta una vez sin esos parámetros.
        extras_opcionales = ("response_format", "reasoning")
        claves_rechazo = (*extras_opcionales, "json_object", "structured")

        def _menciona_parametros(texto: str) -> bool:
            bajo = (texto or "").lower()
            return any(clave in bajo for clave in claves_rechazo)

        rechazo_de_parametros = False
        if respuesta.status_code in (400, 404, 422):
            rechazo_de_parametros = _menciona_parametros(respuesta.text)
        elif respuesta.status_code == 200:
            try:
                cuerpo_error = respuesta.json()
            except Exception:
                cuerpo_error = None
            if isinstance(cuerpo_error, dict) and cuerpo_error.get("error"):
                error = cuerpo_error["error"]
                mensaje = (
                    error.get("message") if isinstance(error, dict) else error
                )
                rechazo_de_parametros = _menciona_parametros(str(mensaje))

        if rechazo_de_parametros:
            logger.warning(
                "OpenRouter rechazó parámetros opcionales (status=%s); se "
                "reintenta sin ellos.",
                respuesta.status_code,
            )
            payload_minimo = {
                clave: valor for clave, valor in payload.items()
                if clave not in extras_opcionales
            }
            respuesta = requests.post(
                url, headers=headers, json=payload_minimo,
                timeout=TIMEOUT_SEGUNDOS,
            )
            logger.info(
                "Respuesta de OpenRouter (sin parámetros opcionales): "
                f"status={respuesta.status_code}, "
                f"longitud_texto={len(respuesta.text)}"
            )

        if respuesta.status_code == 401:
            raise ErrorClaveInvalida(
                "Clave de OpenRouter inválida (401). "
                "Revisá OPENROUTER_API_KEY en el archivo .env."
            )
        if respuesta.status_code == 402:
            raise ErrorIA(
                "OpenRouter rechazó la solicitud por falta de crédito (402). "
                "Usá un modelo con sufijo ':free' o cargá crédito en OpenRouter."
            )
        if respuesta.status_code == 429:
            raise ErrorLimiteSolicitudes(
                "OpenRouter alcanzó un límite de solicitudes (429). Con el "
                "plan gratuito el límite es 50 solicitudes por día (1000 si "
                f"cargaste 10 créditos). Detalle: {_resumen_error_http(respuesta)}"
            )
        if respuesta.status_code == 404:
            raise ErrorModeloNoDisponible(
                f"Modelo de OpenRouter no encontrado (404): revisá "
                f"OPENROUTER_MODEL='{modelo}'."
            )
        if respuesta.status_code >= 500:
            raise ErrorServidor(f"Error del servidor OpenRouter: {respuesta.status_code}")
        if not respuesta.ok:
            raise ErrorIA(
                f"Error de OpenRouter: {respuesta.status_code} "
                f"{_resumen_error_http(respuesta)}"
            )

        datos = respuesta.json()
        if isinstance(datos, dict) and datos.get("error"):
            error = datos["error"]
            mensaje = error.get("message") if isinstance(error, dict) else error
            raise ErrorIA(f"OpenRouter devolvió un error: {str(mensaje)[:200]}")

        opciones = datos.get("choices", [])
        if not opciones:
            raise ErrorRespuestaIncompleta("OpenRouter no devolvió opciones.")

        opcion = opciones[0]
        mensaje = opcion.get("message", {}) or {}
        texto = mensaje.get("content", "")
        motivo_fin = opcion.get("finish_reason")

        if not texto:
            detalle = (
                "OpenRouter devolvió contenido vacío "
                f"(finish_reason={motivo_fin})"
            )
            if mensaje.get("reasoning") or mensaje.get("reasoning_details"):
                detalle += "; el modelo sólo devolvió razonamiento"
            detalle += "."
            logger.warning(
                "OpenRouter devolvió contenido vacío. finish_reason=%s, "
                "hubo_razonamiento=%s",
                motivo_fin, bool(mensaje.get("reasoning") or
                                 mensaje.get("reasoning_details")),
            )
            raise ErrorRespuestaIncompleta(detalle)

        if motivo_fin == "length":
            logger.warning(
                "OpenRouter: respuesta truncada por límite de tokens "
                "(finish_reason=length, longitud=%d). El bloque se reintentará.",
                len(texto),
            )

        logger.info(f"Respuesta de OpenRouter válida: longitud_texto={len(texto)}")
        return texto.strip()

    except ErrorIA:
        raise
    except Exception as e:
        logger.error(f"Error en OpenRouter: {type(e).__name__}: {e}")
        raise clasificar_error(e)


# ---------------------------------------------------------------------------
# OpenRouter: generación estructurada con fallback entre modelos
# ---------------------------------------------------------------------------

def _limpiar_cercas_markdown_openrouter(texto: str) -> str:
    """Compatibilidad: limpia cercas markdown de OpenRouter."""
    return _limpiar_cercas_markdown(texto)


def _texto_de_contenido_openrouter(mensaje: Dict[str, Any]) -> str:
    """
    Extrae el contenido final de `message.content`.

    Algunos endpoints devuelven una lista de partes en lugar de una cadena.
    El contenido de razonamiento (`reasoning`) no se acepta como respuesta.
    """
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


def _mensaje_error_openrouter(cuerpo: Any) -> str:
    """Extrae un mensaje breve del cuerpo de error, sin datos sensibles."""
    if isinstance(cuerpo, dict):
        error = cuerpo.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:300]
        if error:
            return str(error)[:300]
    return ""


def _solicitar_openrouter_una_vez(
    instruccion: str,
    modelo: str,
    esquema: Optional[Dict[str, Any]],
    nombre_esquema: str,
    estricto: bool,
    api_key: str,
) -> Dict[str, Any]:
    """
    Realiza exactamente una solicitud a OpenRouter para un modelo.

    No reintenta ni cambia de modelo: el fallback y el límite global se
    gestionan en `generar_con_openrouter_estructurado`.
    """
    import requests

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": "https://localhost/aula-ia",
        "X-Title": "Aula IA",
    }

    payload: Dict[str, Any] = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": (
                "Responde ÚNICAMENTE con un objeto JSON válido que cumpla "
                "exactamente el esquema solicitado. No uses bloques de código "
                "markdown. No agregues texto fuera del JSON."
            )},
            {"role": "user", "content": instruccion},
        ],
        "temperature": 0.4,
        "max_tokens": TOKEN_MAX_SALIDA,
        # Evita que OpenRouter enrute a un endpoint que no admita los
        # parámetros requeridos (response_format / structured_outputs).
        "provider": {"require_parameters": True},
    }

    if OPENROUTER_RESPONSE_FORMAT == "json_schema" and esquema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": nombre_esquema or "respuesta_classia",
                "strict": bool(estricto),
                "schema": esquema,
            },
        }
    else:
        payload["response_format"] = {"type": "json_object"}

    try:
        respuesta = requests.post(
            url, headers=headers, json=payload, timeout=TIMEOUT_SEGUNDOS
        )
    except requests.Timeout as e:
        raise ErrorRed(
            f"OpenRouter no respondió dentro de {TIMEOUT_SEGUNDOS} segundos."
        ) from e
    except requests.ConnectionError as e:
        raise ErrorRed("No se pudo conectar con OpenRouter.") from e
    except requests.RequestException as e:
        raise ErrorRed(f"Error de red con OpenRouter: {e}") from e

    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = None

    logger.info(
        "OpenRouter: respuesta HTTP status=%s modelo_solicitado=%s "
        "longitud_cuerpo=%d",
        respuesta.status_code, modelo, len(respuesta.text or ""),
    )
    return {
        "status": respuesta.status_code,
        "cuerpo": cuerpo,
        "texto_crudo": (respuesta.text or "")[:300],
        "modelo_solicitado": modelo,
    }


def _evaluar_respuesta_openrouter(
    resultado: Dict[str, Any],
    validador: Optional[Callable[[Any], Tuple[bool, List[str]]]],
) -> Dict[str, Any]:
    """
    Clasifica una respuesta HTTP de OpenRouter y valida su contenido.

    Devuelve el texto aceptado y el modelo real que respondió. Lanza un
    ErrorIA recuperable para que el llamador pruebe el siguiente modelo.
    """
    status = int(resultado.get("status") or 0)
    cuerpo = resultado.get("cuerpo")
    modelo_solicitado = resultado.get("modelo_solicitado", "")
    mensaje_error = _mensaje_error_openrouter(cuerpo)
    texto_crudo = (resultado.get("texto_crudo") or "").strip()

    if status in (401, 403):
        raise ErrorClaveInvalida(
            "Clave de OpenRouter inválida o sin permisos "
            f"(HTTP {status}). Revisá OPENROUTER_API_KEY en .env."
        )
    if status == 402:
        raise ErrorIA(
            "OpenRouter rechazó la solicitud por falta de crédito (402). "
            "Verificá que el modelo sea ':free' o cargá crédito."
        )
    if status == 429:
        raise ErrorLimiteSolicitudes(
            "OpenRouter alcanzó un límite de solicitudes (429). "
            f"Detalle: {mensaje_error or 'sin detalle'}"
        )
    if status == 404:
        raise ErrorModeloNoDisponible(
            f"Modelo de OpenRouter no disponible (404): '{modelo_solicitado}'. "
            "Puede no existir o no tener endpoints que admitan los parámetros "
            "requeridos."
        )
    if status in (400, 422):
        raise ErrorModeloNoDisponible(
            f"OpenRouter rechazó la solicitud (HTTP {status}) para "
            f"'{modelo_solicitado}': {mensaje_error or texto_crudo or 'sin detalle'}"
        )
    if status >= 500:
        raise ErrorServidor(
            f"Error del servidor de OpenRouter (HTTP {status}) para "
            f"'{modelo_solicitado}'."
        )
    if status != 200:
        raise ErrorIA(
            f"Error de OpenRouter (HTTP {status}) para '{modelo_solicitado}': "
            f"{mensaje_error or texto_crudo or 'sin detalle'}"
        )

    if isinstance(cuerpo, dict) and cuerpo.get("error"):
        detalle = mensaje_error or "error sin detalle"
        bajo = detalle.lower()
        if "rate limit" in bajo or "too many requests" in bajo or "429" in bajo:
            raise ErrorLimiteSolicitudes(
                f"OpenRouter alcanzó un límite de solicitudes: {detalle}"
            )
        if "quota" in bajo:
            raise ErrorCuotaAgotada(
                f"OpenRouter devolvió un error de cuota: {detalle}"
            )
        raise ErrorIA(
            f"OpenRouter devolvió un error lógico: {detalle}"
        )

    opciones = cuerpo.get("choices") if isinstance(cuerpo, dict) else None
    if not isinstance(opciones, list) or not opciones:
        raise ErrorRespuestaIncompleta(
            "OpenRouter no devolvió 'choices' en la respuesta."
        )

    opcion = opciones[0] if isinstance(opciones[0], dict) else {}
    mensaje = opcion.get("message") or {}
    if not isinstance(mensaje, dict):
        mensaje = {}
    texto = _texto_de_contenido_openrouter(mensaje)
    motivo = opcion.get("finish_reason")
    hubo_razonamiento = bool(
        mensaje.get("reasoning") or mensaje.get("reasoning_details")
    )

    if motivo == "length":
        raise ErrorRespuestaTruncada(
            "OpenRouter truncó la respuesta por límite de tokens "
            "(finish_reason=length)."
        )
    if motivo == "content_filter":
        raise ErrorRespuestaIncompleta(
            "OpenRouter bloqueó la respuesta por el filtro de contenido "
            "(finish_reason=content_filter)."
        )
    if not texto:
        detalle = f"contenido final vacío (finish_reason={motivo})"
        if hubo_razonamiento:
            detalle += "; el modelo sólo devolvió razonamiento"
        raise ErrorRespuestaVacia(
            f"OpenRouter devolvió {detalle}."
        )

    datos = _validar_json_texto(
        texto, validador, "OpenRouter", modelo_solicitado
    )

    modelo_real = ""
    if isinstance(cuerpo, dict):
        modelo_real = str(cuerpo.get("model") or "")
    logger.info(
        "OpenRouter: validación local OK modelo_solicitado=%s "
        "modelo_real=%s finish_reason=%s longitud_contenido=%d",
        modelo_solicitado, modelo_real or "(no informado)", motivo, len(texto),
    )
    return {
        "texto": texto,
        "modelo_real": modelo_real or modelo_solicitado,
        "finish_reason": motivo,
        "datos": datos,
    }


def generar_con_openrouter_estructurado(
    instruccion: str,
    esquema: Dict[str, Any],
    nombre_esquema: str,
    estricto: bool,
    validador: Callable[[Any], Tuple[bool, List[str]]],
    etapa: str = "",
    modelos: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    modelos_agotados: Optional[Set[str]] = None,
) -> Tuple[str, str]:
    """
    Genera contenido estructurado probando modelos gratuitos en orden.

    Cada modelo se prueba exactamente una vez por solicitud lógica. Si un
    modelo falla por HTTP, cuota, respuesta vacía, razonamiento sin contenido,
    JSON inválido o esquema incumplido, se pasa al siguiente. No hay
    reintentos del SDK ni del bucle de bloques multiplicando los intentos.

    Devuelve (texto, modelo_real). Si ningún modelo produce una respuesta
    válida, lanza ErrorModelosAgotados.
    """
    if not api_key:
        api_key = OPENROUTER_API_KEY
    if not api_key:
        raise ErrorClaveInvalida("No se configuró OPENROUTER_API_KEY")

    lista = [
        m.strip() for m in (modelos if modelos is not None
                            else OPENROUTER_MODELS)
        if m and m.strip()
    ]
    if not lista:
        raise ErrorModelosAgotados(
            "No hay modelos de OpenRouter configurados. Definí "
            "OPENROUTER_MODEL u OPENROUTER_MODELS en .env."
        )

    errores: List[str] = []
    for indice, modelo in enumerate(lista, 1):
        if modelos_agotados is not None and modelo in modelos_agotados:
            errores.append(
                f"{modelo}: omitido (no disponible en esta ejecución)."
            )
            logger.info(
                "OpenRouter: modelo %s omitido (marcado como no disponible).",
                modelo,
            )
            continue

        try:
            logger.info(
                "OpenRouter: solicitud etapa=%s intento=%d/%d modelo=%s "
                "formato=%s estricto=%s",
                etapa or "sin_etapa", indice, len(lista), modelo,
                OPENROUTER_RESPONSE_FORMAT, estricto,
            )
            resultado = _solicitar_openrouter_una_vez(
                instruccion=instruccion,
                modelo=modelo,
                esquema=esquema,
                nombre_esquema=nombre_esquema,
                estricto=estricto,
                api_key=api_key,
            )
            evaluado = _evaluar_respuesta_openrouter(resultado, validador)
            logger.info(
                "OpenRouter: respuesta aceptada etapa=%s intento=%d/%d "
                "modelo_solicitado=%s modelo_real=%s status=%d "
                "finish_reason=%s validacion=ok",
                etapa or "sin_etapa", indice, len(lista), modelo,
                evaluado["modelo_real"], resultado.get("status"),
                evaluado.get("finish_reason"),
            )
            return evaluado["texto"], evaluado["modelo_real"]

        except ErrorClaveInvalida:
            logger.error(
                "OpenRouter: autenticación fallida con el modelo %s. "
                "Se aborta sin probar más modelos.", modelo,
            )
            raise
        except ErrorIntegracion:
            raise
        except ErrorModeloNoDisponible as e:
            if modelos_agotados is not None:
                modelos_agotados.add(modelo)
            errores.append(f"{modelo}: {e}")
            logger.warning(
                "OpenRouter: modelo %s no disponible (%s). Se omite durante "
                "el resto de la ejecución y se prueba el siguiente.",
                modelo, type(e).__name__,
            )
            continue
        except ErrorCuotaAgotada as e:
            if modelos_agotados is not None and cuota_es_persistente(str(e)):
                modelos_agotados.add(modelo)
                logger.warning(
                    "OpenRouter: cuota persistente agotada para %s. Se omite "
                    "durante el resto de la ejecución.", modelo,
                )
            errores.append(f"{modelo}: {e}")
            logger.warning(
                "OpenRouter: cuota agotada para %s (%s). Se prueba el "
                "siguiente modelo.", modelo, type(e).__name__,
            )
            continue
        except ErrorIA as e:
            errores.append(f"{modelo}: {type(e).__name__}: {e}")
            logger.warning(
                "OpenRouter: intento %d/%d con %s falló (%s): %s. "
                "Se prueba el siguiente modelo.",
                indice, len(lista), modelo, type(e).__name__, e,
            )
            continue

    detalle = "\n".join(errores) if errores else "No se intentó ningún modelo."
    logger.error(
        "OpenRouter: se agotaron los modelos configurados para la etapa %s.\n%s",
        etapa or "sin_etapa", detalle,
    )
    raise ErrorModelosAgotados(
        "Se agotaron todos los modelos gratuitos de OpenRouter sin una "
        f"respuesta válida para la etapa '{etapa or 'sin_etapa'}'.\n" + detalle
    )


# ---------------------------------------------------------------------------
# Proveedor: OmniRoute (opcional, no implementado completamente)
# ---------------------------------------------------------------------------

def generar_con_omniroute(
    instruccion: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """
    Adaptador opcional para OmniRoute (compatible con API de chat).

    No se implementa completamente porque no hay documentación pública verificable.
    Se deja como esqueleto documentado.
    """
    raise ErrorIA(
        "OmniRoute no está implementado en el MVP. "
        "Configura GEMINI_API_KEY u OPENROUTER_API_KEY en su lugar."
    )


# ---------------------------------------------------------------------------
# Generador con orden de proveedores y recuperación
# ---------------------------------------------------------------------------

def generar_contenido_educativo(
    instruccion: str,
    orden_proveedores: list,
    proveedores_agotados: Optional[Set[str]] = None,
    *,
    esquema: Optional[Dict[str, Any]] = None,
    nombre_esquema: str = "respuesta",
    estricto: bool = True,
    validador: Optional[Callable[[Any], Tuple[bool, List[str]]]] = None,
    etapa: str = "",
    modelos_agotados: Optional[Set[str]] = None,
) -> Tuple[str, str]:
    """
    Intenta generar contenido educativo usando los proveedores en orden.

    Devuelve (texto_respuesta, nombre_proveedor_usado).
    Si todos fallan, lanza un ErrorIA con el detalle de cada proveedor.

    Orden objetivo: Gemini, NVIDIA, Groq, OpenRouter. Los proveedores sin
    credenciales o sin modelos candidatos se omiten sin interrumpir el flujo.

    Un ErrorIntegracion (argumento no admitido por el SDK, error de
    programación) se propaga de inmediato: no es un fallo transitorio del
    proveedor y no debe reintentarse con otro proveedor ni confundirse con
    una respuesta del modelo.

    `proveedores_agotados` es un conjunto opcional compartido por toda la
    ejecución. Cuando un proveedor agota su cuota diaria se agrega allí para
    no volver a intentarlo (ni esperar) en los bloques siguientes: el flujo
    pasa directamente al siguiente proveedor disponible.

    Cuando se pasan `esquema` y `validador`, todos los proveedores que lo
    admiten usan salida estructurada y la respuesta se valida localmente antes
    de aceptarla. Gemini no recibe el esquema en el SDK, pero su texto también
    se analiza y valida antes de devolverlo. Si ningún modelo de un proveedor
    cumple, se lanza ErrorModelosAgotados y el flujo de bloques no reintenta.
    """
    errores = []
    fallo_modelos: Optional[ErrorModelosAgotados] = None
    ultimo_recuperable: Optional[ErrorIA] = None

    for nombre in orden_proveedores:
        nombre = nombre.strip().lower()

        if proveedores_agotados is not None and nombre in proveedores_agotados:
            errores.append(
                f"{nombre}: omitido (cuota diaria agotada en esta ejecución)."
            )
            continue

        if not proveedor_esta_configurado(nombre):
            motivo = ""
            try:
                motivo = motivo_proveedor_no_configurado(nombre)
            except Exception:
                motivo = "sin credenciales"
            errores.append(f"{nombre}: no configurado ({motivo}).")
            logger.info(
                "Proveedor %s omitido: no configurado (%s).", nombre, motivo
            )
            continue

        try:
            if nombre == "gemini":
                texto = generar_con_gemini(instruccion)
                if esquema is not None and validador is not None:
                    _validar_json_texto(
                        texto, validador, "Gemini", GEMINI_MODEL
                    )
                logger.info("Proveedor de IA usado: gemini (longitud=%d)", len(texto))
                return texto, "gemini"
            elif nombre == "nvidia":
                if esquema is not None and validador is not None:
                    texto, modelo_real = generar_con_nvidia_estructurado(
                        instruccion=instruccion,
                        esquema=esquema,
                        nombre_esquema=nombre_esquema,
                        estricto=estricto,
                        validador=validador,
                        etapa=etapa,
                        modelos_agotados=modelos_agotados,
                    )
                else:
                    texto, modelo_real = _generar_estructurado_compatible(
                        proveedor="NVIDIA",
                        base_url=NVIDIA_BASE_URL,
                        api_key=NVIDIA_API_KEY,
                        modelos=list(NVIDIA_MODELS),
                        instruccion=instruccion,
                        esquema=None,
                        nombre_esquema=nombre_esquema,
                        estricto=estricto,
                        validador=None,
                        etapa=etapa,
                        modelos_agotados=modelos_agotados,
                        construir_extras=_extras_nvidia,
                    )
                logger.info(
                    "Proveedor de IA usado: nvidia (modelo=%s, etapa=%s, "
                    "longitud=%d)",
                    modelo_real, etapa or "sin_etapa", len(texto),
                )
                return texto, "nvidia"
            elif nombre == "groq":
                if esquema is not None and validador is not None:
                    texto, modelo_real = generar_con_groq_estructurado(
                        instruccion=instruccion,
                        esquema=esquema,
                        nombre_esquema=nombre_esquema,
                        estricto=estricto,
                        validador=validador,
                        etapa=etapa,
                        modelos_agotados=modelos_agotados,
                    )
                else:
                    texto, modelo_real = _generar_estructurado_compatible(
                        proveedor="Groq",
                        base_url=GROQ_BASE_URL,
                        api_key=GROQ_API_KEY,
                        modelos=list(GROQ_MODELS),
                        instruccion=instruccion,
                        esquema=None,
                        nombre_esquema=nombre_esquema,
                        estricto=estricto,
                        validador=None,
                        etapa=etapa,
                        modelos_agotados=modelos_agotados,
                        construir_extras=_extras_groq,
                    )
                logger.info(
                    "Proveedor de IA usado: groq (modelo=%s, etapa=%s, "
                    "longitud=%d)",
                    modelo_real, etapa or "sin_etapa", len(texto),
                )
                return texto, "groq"
            elif nombre == "openrouter":
                if esquema is not None and validador is not None:
                    texto, modelo_real = generar_con_openrouter_estructurado(
                        instruccion=instruccion,
                        esquema=esquema,
                        nombre_esquema=nombre_esquema,
                        estricto=estricto,
                        validador=validador,
                        etapa=etapa,
                        modelos_agotados=modelos_agotados,
                    )
                    logger.info(
                        "Proveedor de IA usado: openrouter "
                        "(modelo=%s, etapa=%s, longitud=%d)",
                        modelo_real, etapa or "sin_etapa", len(texto),
                    )
                    return texto, "openrouter"
                texto = generar_con_openrouter(instruccion)
                logger.info("Proveedor de IA usado: openrouter (longitud=%d)", len(texto))
                return texto, "openrouter"
            elif nombre == "omniroute":
                texto = generar_con_omniroute(instruccion)
                logger.info("Proveedor de IA usado: omniroute (longitud=%d)", len(texto))
                return texto, "omniroute"
        except ErrorIntegracion as e:
            # Error de programación: abortar sin probar otros proveedores.
            logger.error(
                "Proveedor %s: error de integración (%s). Se aborta sin "
                "probar proveedores alternativos.",
                nombre, type(e).__name__,
            )
            raise
        except ErrorClaveInvalida as e:
            errores.append(f"{nombre}: clave inválida ({e}).")
            logger.warning("Proveedor %s no disponible: clave inválida.", nombre)
            continue
        except ErrorModeloNoDisponible as e:
            errores.append(f"{nombre}: modelo no disponible ({e}).")
            logger.warning(
                "Proveedor %s no tiene un modelo disponible: %s", nombre, e
            )
            continue
        except ErrorTimeout as e:
            errores.append(f"{nombre}: timeout ({e}).")
            logger.warning("Proveedor %s agotó el tiempo de espera: %s", nombre, e)
            continue
        except ErrorLimiteSolicitudes as e:
            errores.append(f"{nombre}: límite de solicitudes ({e}).")
            logger.warning(
                "Proveedor %s alcanzó un límite de solicitudes. Se intentará "
                "el siguiente proveedor.", nombre,
            )
            continue
        except ErrorCuotaAgotada as e:
            errores.append(f"{nombre}: cuota agotada ({e}).")
            if proveedores_agotados is not None and cuota_es_persistente(str(e)):
                proveedores_agotados.add(nombre)
                logger.warning(
                    "Proveedor %s: cuota diaria agotada. Se omite durante el "
                    "resto de la ejecución y se continúa con el siguiente "
                    "proveedor disponible.",
                    nombre,
                )
            else:
                logger.warning(
                    "Proveedor %s no disponible: cuota agotada. Se intentará "
                    "el siguiente proveedor.",
                    nombre,
                )
            continue
        except ErrorRed as e:
            errores.append(f"{nombre}: error de red ({e}).")
            logger.warning("Proveedor %s falló por red: %s", nombre, e)
            continue
        except ErrorServidor as e:
            errores.append(f"{nombre}: error del servidor ({e}).")
            logger.warning(
                "Proveedor %s falló con error del servidor: %s. "
                "Se intentará el siguiente proveedor si está configurado.",
                nombre, e,
            )
            continue
        except ErrorRespuestaIncompleta as e:
            ultimo_recuperable = e
            errores.append(f"{nombre}: respuesta incompleta ({e}).")
            logger.warning("Proveedor %s devolvió una respuesta incompleta.", nombre)
            continue
        except ErrorRespuestaInvalida as e:
            ultimo_recuperable = e
            errores.append(f"{nombre}: respuesta fuera de esquema ({e}).")
            logger.warning(
                "Proveedor %s devolvió JSON válido pero fuera del esquema.",
                nombre,
            )
            continue
        except ErrorContenidoNoJson as e:
            ultimo_recuperable = e
            errores.append(f"{nombre}: contenido no JSON ({e}).")
            logger.warning("Proveedor %s devolvió contenido que no es JSON.", nombre)
            continue
        except ErrorModelosAgotados as e:
            fallo_modelos = e
            errores.append(f"{nombre}: {e}")
            logger.error(
                "Proveedor %s: se agotaron sus modelos sin una respuesta "
                "válida.", nombre,
            )
            continue
        except ErrorIA as e:
            errores.append(f"{nombre}: error ({e}).")
            logger.warning("Proveedor %s falló: %s", nombre, e)
            continue

    detalle = "\n".join(errores) if errores else "No se especificaron proveedores."
    if fallo_modelos is not None:
        logger.error(
            "Se agotaron todos los modelos configurados sin respuesta "
            "válida.\n%s", detalle,
        )
        raise ErrorModelosAgotados(
            "Se agotaron todos los modelos configurados sin una respuesta "
            "válida.\n" + detalle
        ) from fallo_modelos

    if ultimo_recuperable is not None:
        logger.error(
            "Ningún proveedor devolvió una respuesta válida.\n%s", detalle
        )
        raise type(ultimo_recuperable)(
            "Ningún proveedor devolvió una respuesta válida.\n" + detalle
        ) from ultimo_recuperable

    logger.error(
        "Se agotaron todos los proveedores de IA disponibles.\n%s", detalle
    )
    raise ErrorIA(
        "Se agotaron todos los proveedores de IA.\n" + detalle
    )


def obtener_proveedores_disponibles() -> list:
    """Devuelve los proveedores configurados (clave y modelos cuando aplica)."""
    from configuracion import AI_PROVIDER_ORDER
    disponibles = []
    for nombre in AI_PROVIDER_ORDER:
        nombre = nombre.strip().lower()
        if nombre and proveedor_esta_configurado(nombre):
            disponibles.append(nombre)
    return disponibles
