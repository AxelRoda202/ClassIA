"""
Generación de contenido educativo por bloques segmentados.

Este módulo implementa el sistema de generación segmentada para evitar
respuestas JSON truncadas de los proveedores de IA. En lugar de solicitar
todo el documento de una sola vez, el flujo se divide en etapas:

A. Planificación general (plan de aprendizaje)
B. Desarrollo de secciones teóricas por bloque
C. Generación de ejercicios en lotes
D. Componentes finales (resumen, glosario, metadatos)
E. Ensamblado local del documento completo

Cada etapa valida su respuesta antes de continuar, guarda el progreso
en disco y permite recuperación si falla un bloque.

No se realizan llamadas reales a APIs durante las pruebas automatizadas;
se utilizan sustitutos (mocks) para verificar el flujo.
"""
import json
import logging
import re
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from configuracion import (
    CARPETA_TEMPORAL, CARPETA_SALIDA, MODO_DEMOSTRACION,
    TIMEOUT_SEGUNDOS, MAX_REINTENTOS, TIEMPO_MAX_GENERACION_SEGUNDOS,
    MAX_EXTERNAL_IMAGES_PER_PDF,
)
from plantillas import (
    obtener_instruccion_planificacion,
    obtener_instruccion_seccion_teorica,
    obtener_instruccion_lote_ejercicios,
    obtener_instruccion_componentes_finales,
)
from modelos_datos import (
    material_educativo_vacio, obtener_ejemplo_por_disciplina,
)
from validador import validar_estructura_material, ErrorValidacion
from proveedores_ia import (
    generar_contenido_educativo, ErrorIA, ErrorRespuestaIncompleta,
    ErrorIntegracion, ErrorContenidoNoJson, ErrorModelosAgotados,
)
from esquemas_bloques import (
    validar_plan_aprendizaje,
    validar_seccion_teorica,
    validar_lote_ejercicios,
    validar_componentes_finales,
    validar_documento_ensamblado,
    normalizar_claves,
    obtener_esquema_openrouter,
)
from generador_imagenes import (
    seleccionar_recursos_externos,
    generar_imagenes_seleccionadas,
    proveedor_imagenes_esta_habilitado,
)
from graficos import generar_grafico_desde_recurso
from generador_pdf import construir_pdf


logger = logging.getLogger(__name__)


def _leer_json(ruta: Path) -> Optional[Dict[str, Any]]:
    """Lee un JSON de disco sin propagar errores de formato o permisos."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return None
    return datos if isinstance(datos, dict) else None


def _sufijo_numerico(valor: Any) -> Optional[int]:
    """Extrae el número final de un id (`act12` -> 12) para no repetirlo."""
    coincidencia = re.search(r"(\d+)\s*$", str(valor or ""))
    return int(coincidencia.group(1)) if coincidencia else None


# ---------------------------------------------------------------------------
# Estados de la generación segmentada
# ---------------------------------------------------------------------------

ESTADO_PLANNING = "planning"
ESTADO_PLAN_VALIDATED = "plan_validated"
ESTADO_GENERATING_SECTIONS = "generating_sections"
ESTADO_GENERATING_EXERCISES = "generating_exercises"
ESTADO_ASSEMBLING_CONTENT = "assembling_content"
ESTADO_GENERATING_VISUALS = "generating_visuals"
ESTADO_BUILDING_PDF = "building_pdf"
ESTADO_COMPLETED = "completed"
ESTADO_FAILED = "failed"


# ---------------------------------------------------------------------------
# Constantes de configuración
# ---------------------------------------------------------------------------

MAX_REINTENTOS_BLOQUE = 2
TAMANIO_LOTE_EJERCICIOS = 3
TOKEN_ESTIMADO_POR_BLOQUE = 1500


class ErrorBloque(Exception):
    """Excepción lanzada cuando un bloque no puede generarse o validarse."""
    pass


class ErrorCancelado(Exception):
    """Se lanza cuando se pide detener la generación (cierre de ventana)."""
    pass


def _limpiar_cercas_markdown(texto: str) -> str:
    """Quita las cercas ``` (con o sin lenguaje) que agregan algunos modelos."""
    limpio = texto.strip()
    if not limpio.startswith("```"):
        return limpio
    lineas = limpio.splitlines()
    if lineas and lineas[0].strip().startswith("```"):
        lineas = lineas[1:]
    if lineas and lineas[-1].strip().startswith("```"):
        lineas = lineas[:-1]
    return "\n".join(lineas).strip()


def _preparar_texto_json(texto: Any, etapa: str) -> str:
    """
    Clasifica el texto de un proveedor antes de analizarlo como JSON.

    Distingue tres situaciones que no deben confundirse entre sí:
    - respuesta vacía -> ErrorRespuestaIncompleta;
    - texto que no es JSON (mensaje de seguridad, explicación) ->
      ErrorContenidoNoJson;
    - JSON sintácticamente inválido o truncado -> lo detecta json.loads.

    Nunca convierte una excepción en contenido ni acepta texto vacío.
    """
    if texto is None or not str(texto).strip():
        raise ErrorRespuestaIncompleta(
            f"{etapa}: el proveedor devolvió una respuesta vacía."
        )
    limpio = _limpiar_cercas_markdown(str(texto))
    if not limpio or limpio[0] not in "{[":
        fragmento = " ".join(limpio[:60].split())
        raise ErrorContenidoNoJson(
            f"{etapa}: la respuesta no es un objeto JSON "
            f"(comienza con «{fragmento}»)."
        )
    return limpio


# Equivalencias frecuentes de dificultad. El valor canónico es el que usa el
# esquema; se aplican sólo para corregir variantes del modelo.
_EQUIVALENCIAS_DIFICULTAD = {
    "basico": "inicial", "básico": "inicial",
    "facil": "inicial", "fácil": "inicial",
    "inicial": "inicial", "principiante": "inicial",
    "medio": "intermedio", "media": "intermedio",
    "intermedio": "intermedio",
    "dificil": "avanzado", "difícil": "avanzado",
    "avanzado": "avanzado", "alta": "avanzado",
}


def _completar_campos_derivables_ejercicios(
    lote: Dict[str, Any],
    dificultad: str,
    contador_inicio: int,
) -> Dict[str, Any]:
    """
    Completa sólo campos que el programa ya conoce de forma determinista.

    No inventa contenido educativo: la dificultad es la que se pidió para el
    lote y los ids son correlativos. Si el modelo omite esos campos (o usa una
    variante como "media"), el lote deja de fallar por un detalle de formato.
    El contenido (consigna, solución, respuesta) sigue siendo obligatorio.
    """
    if not isinstance(lote, dict):
        return lote
    ejercicios = lote.get("ejercicios")
    if not isinstance(ejercicios, list):
        return lote

    for indice, ejercicio in enumerate(ejercicios):
        if not isinstance(ejercicio, dict):
            continue
        valor = str(ejercicio.get("dificultad") or "").strip().lower()
        ejercicio["dificultad"] = _EQUIVALENCIAS_DIFICULTAD.get(
            valor, dificultad
        )
        if not ejercicio.get("id"):
            ejercicio["id"] = f"act{contador_inicio + indice}"
    return lote


# ---------------------------------------------------------------------------
# Validadores para la capa de OpenRouter
# ---------------------------------------------------------------------------
#
# OpenRouter valida el JSON contra el esquema de la etapa antes de aceptarlo.
# Las mismas funciones de validación de ClassIA se aplican aquí (sobre una
# copia con claves normalizadas) para que un HTTP 200 con campos faltantes no
# se considere una respuesta válida.

def _validar_plan_para_openrouter(datos: Any) -> Tuple[bool, List[str]]:
    return validar_plan_aprendizaje(normalizar_claves(datos))


def _validar_seccion_para_openrouter(datos: Any) -> Tuple[bool, List[str]]:
    return validar_seccion_teorica(normalizar_claves(datos))


def _validar_componentes_para_openrouter(datos: Any) -> Tuple[bool, List[str]]:
    return validar_componentes_finales(normalizar_claves(datos))


class GeneradorBloques:
    """
    Coordina la generación segmentada de material educativo.

    El flujo es:
    1. Planificación general (una solicitud pequeña)
    2. Desarrollo de secciones teóricas (una solicitud por sección)
    3. Generación de ejercicios en lotes (una solicitud por lote)
    4. Componentes finales (una solicitud para resumen y glosario)
    5. Ensamblado local y generación de PDF
    """

    def __init__(self):
        self.trabajo_id: Optional[str] = None
        self.carpeta_trabajo: Optional[Path] = None
        self.plan: Optional[Dict[str, Any]] = None
        self.secciones_validadas: List[Dict[str, Any]] = []
        self.ejercicios_validos: List[Dict[str, Any]] = []
        self.componentes_finales: Optional[Dict[str, Any]] = None
        self.rutas_graficos: Dict[str, str] = {}
        self.rutas_imagenes_externas: Dict[str, str] = {}
        # Callback opcional para informar hitos reales a la interfaz.
        self._callback_progreso = None
        # Evento opcional (threading.Event) para cancelación cooperativa.
        self._cancelacion = None
        # Proveedores con cuota diaria agotada en esta ejecución: se omiten
        # para no reintentar en vano en cada bloque. Se recuerda mientras
        # viva la instancia (una sesión de la aplicación).
        self.proveedores_agotados: Set[str] = set()
        # Modelos de OpenRouter no disponibles (404, formato no admitido o
        # cuota persistente). Se omiten en los bloques siguientes.
        self.modelos_agotados: Set[str] = set()
        # Indica si el trabajo actual se está reanudando desde disco. En ese
        # caso se reutilizan lotes de ejercicios y componentes ya validados.
        self._reanudando = False

    # ------------------------------------------------------------------
    # Cancelación cooperativa
    # ------------------------------------------------------------------

    def _cancelacion_solicitada(self) -> bool:
        """Indica si la interfaz pidió detener la generación."""
        evento = getattr(self, "_cancelacion", None)
        try:
            return bool(evento is not None and evento.is_set())
        except Exception:
            return False

    def _verificar_cancelacion(self) -> None:
        """
        Detiene el flujo en el próximo punto seguro.

        No se interrumpe una solicitud HTTP en curso; se espera a que termine
        el bloque actual. Los bloques ya validados quedan guardados en disco.
        """
        if self._cancelacion_solicitada():
            raise ErrorCancelado(
                "Generación cancelada porque se cerró la ventana."
            )

    # ------------------------------------------------------------------
    # Gestión de trabajos en disco
    # ------------------------------------------------------------------

    def _crear_carpeta_trabajo(self, trabajo_id: str) -> Path:
        carpeta = CARPETA_TEMPORAL / trabajo_id
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta

    def _guardar_estado(self, estado: str, datos: Dict[str, Any],
                        mensaje_error: str = "") -> None:
        """
        Guarda el estado actual del trabajo en un archivo JSON.

        Se conservan los campos anteriores (por ejemplo, `configuracion`)
        para que un fallo o un cierre no borre los datos necesarios para
        reanudar el trabajo.
        """
        if not self.carpeta_trabajo:
            return
        ruta = self.carpeta_trabajo / "estado.json"
        anterior: Dict[str, Any] = {}
        if ruta.exists():
            cargado = _leer_json(ruta)
            if cargado:
                anterior = cargado
        registro = {
            "trabajo_id": self.trabajo_id,
            "estado": estado,
            "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mensaje_error": mensaje_error,
        }
        registro.update(datos)
        anterior.update(registro)
        ruta.write_text(json.dumps(anterior, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    def _guardar_respuesta_cruda(self, nombre_archivo: str,
                                 texto: str) -> None:
        """Guarda una respuesta cruda de la IA para diagnóstico."""
        if not self.carpeta_trabajo:
            return
        ruta = self.carpeta_trabajo / nombre_archivo
        ruta.write_text(texto, encoding="utf-8")

    def _guardar_bloque_validado(self, nombre_archivo: str,
                                 datos: Dict[str, Any]) -> None:
        """Guarda un bloque ya validado en disco."""
        if not self.carpeta_trabajo:
            return
        ruta = self.carpeta_trabajo / nombre_archivo
        ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    def _cargar_bloque_si_existe(self, nombre_archivo: str
                                 ) -> Optional[Dict[str, Any]]:
        """Carga un bloque previamente guardado si existe."""
        if not self.carpeta_trabajo:
            return None
        ruta = self.carpeta_trabajo / nombre_archivo
        if not ruta.exists():
            return None
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Modo demostración
    # ------------------------------------------------------------------

    def _material_demostracion(self, tema: str, disciplina: str, nivel: str,
                               cantidad_actividades: int) -> Dict[str, Any]:
        """Devuelve un material de ejemplo para modo demostración."""
        material = obtener_ejemplo_por_disciplina(disciplina)
        material["metadatos"]["tema"] = tema
        material["metadatos"]["titulo"] = f"Material de demostración: {tema}"
        material["metadatos"]["nivel"] = nivel
        material["metadatos"]["disciplina"] = disciplina
        material["metadatos"]["cantidad_actividades"] = cantidad_actividades
        material["metadatos"]["fecha_generacion"] = (
            datetime.datetime.now().strftime("%d/%m/%Y")
        )
        material["metadatos"]["modo_demostracion"] = True
        material["advertencia_ia"] = (
            "MODO DEMOSTRACIÓN: Este material es un ejemplo estático. "
            "No fue generado por un modelo de IA real. "
            "Úsalo solo para probar la interfaz y la generación de PDF."
        )
        return material

    # ------------------------------------------------------------------
    # Etapa A: Planificación general
    # ------------------------------------------------------------------

    def _generar_plan(self, tema: str, disciplina: str, nivel: str,
                      profundidad: str, cantidad_actividades: int,
                      recursos_visuales: bool) -> Dict[str, Any]:
        """Ejecuta la solicitud de planificación (etapa A) con reintentos."""
        from plantillas import obtener_instruccion_planificacion
        instruccion = obtener_instruccion_planificacion(
            tema=tema, nivel=nivel, disciplina=disciplina,
            profundidad=profundidad,
            cantidad_actividades=cantidad_actividades,
            recursos_visuales=recursos_visuales,
        )

        nombre_esquema, esquema, estricto = obtener_esquema_openrouter(
            "planificacion"
        )
        ultimo_error = ""
        for intento in range(MAX_REINTENTOS_BLOQUE):
            # Cancelación cooperativa: se comprueba antes de cada intento,
            # nunca en medio de una solicitud HTTP en curso.
            self._verificar_cancelacion()
            try:
                texto_respuesta, proveedor = generar_contenido_educativo(
                    instruccion, self._orden_proveedores(),
                    proveedores_agotados=self.proveedores_agotados,
                    esquema=esquema,
                    nombre_esquema=nombre_esquema,
                    estricto=estricto,
                    validador=_validar_plan_para_openrouter,
                    etapa="planificacion",
                    modelos_agotados=self.modelos_agotados,
                )

                # Guardar respuesta cruda antes de validar.
                # El primer intento conserva el nombre histórico
                # plan_crudo.json; los siguientes no lo sobrescriben.
                sufijo = f"_intento{intento+1}" if intento > 0 else ""
                self._guardar_respuesta_cruda(
                    f"plan{sufijo}_crudo.json", texto_respuesta
                )

                logger.info(
                    f"Planificación: respuesta de {proveedor} recibida, "
                    f"longitud={len(texto_respuesta)}, intento={intento + 1}"
                )

                try:
                    texto_json = _preparar_texto_json(
                        texto_respuesta, "Planificación"
                    )
                    plan = json.loads(texto_json)
                except json.JSONDecodeError as e:
                    ultimo_error = f"JSON inválido: {e}"
                    logger.warning(
                        f"Planificación: respuesta no es JSON válido en "
                        f"intento {intento + 1}: {e}"
                    )
                    instruccion += (
                        "\n\nIMPORTANTE: La respuesta anterior quedó "
                        "truncada o no era JSON válido. Genera un plan más "
                        "conciso: menos secciones y descripciones breves, "
                        "pero conservando TODOS los campos obligatorios."
                    )
                    continue

                # Normalizar claves (p. ej. "solución" -> "solucion").
                plan = normalizar_claves(plan)

                exito, errores = validar_plan_aprendizaje(plan)
                if not exito:
                    ultimo_error = f"Validación: {'; '.join(errores)}"
                    logger.warning(
                        f"Planificación: plan no válido en intento "
                        f"{intento + 1}: {'; '.join(errores)}"
                    )
                    instruccion += (
                        "\n\nIMPORTANTE: La respuesta anterior no cumplió el "
                        "esquema. Revisa los campos obligatorios y devuelve "
                        "un plan completo y válido."
                    )
                    continue

                self._guardar_bloque_validado("plan.json", plan)
                self.plan = plan
                logger.info(
                    f"Planificación: plan validado con "
                    f"{len(plan.get('secciones', []))} secciones"
                )
                return plan

            except ErrorRespuestaIncompleta as e:
                ultimo_error = str(e)
                logger.warning(
                    f"Planificación: respuesta incompleta en intento "
                    f"{intento + 1}: {e}"
                )
                instruccion += (
                    "\n\nIMPORTANTE: La respuesta anterior fue truncada o "
                    "estaba vacía. Genera un plan más conciso y asegúrate "
                    "de cerrar el JSON."
                )
                continue
            except ErrorContenidoNoJson as e:
                ultimo_error = str(e)
                logger.warning(
                    f"Planificación: la respuesta no fue JSON en intento "
                    f"{intento + 1}: {e}"
                )
                instruccion += (
                    "\n\nIMPORTANTE: Tu respuesta anterior no fue un objeto "
                    "JSON. Responde ÚNICAMENTE con el JSON, sin explicaciones, "
                    "comentarios ni mensajes de seguridad."
                )
                continue
            except ErrorModelosAgotados:
                # OpenRouter ya agotó su lista de modelos para esta solicitud.
                # No se repite el bloque: el límite de intentos es global.
                raise
            except ErrorIA:
                # Errores de proveedor/red/cuota y errores de integración:
                # se propagan sin convertirlos en contenido ni reintentarlos
                # aquí (el orden de proveedores ya hizo su propio recorrido).
                raise

        raise ErrorBloque(
            f"No se pudo generar el plan de aprendizaje después de "
            f"{MAX_REINTENTOS_BLOQUE} intentos. Último error: {ultimo_error}"
        )

    def _recuperar_plan_si_existe(self) -> Optional[Dict[str, Any]]:
        """Intenta recuperar un plan previamente validado."""
        plan = self._cargar_bloque_si_existe("plan.json")
        if plan is None:
            return None
        plan = normalizar_claves(plan)
        exito, errores = validar_plan_aprendizaje(plan)
        if not exito:
            logger.warning(
                "Plan guardado no válido; se regenera: %s",
                "; ".join(errores),
            )
            return None
        self.plan = plan
        return plan

    # ------------------------------------------------------------------
    # Etapa B: Desarrollo de secciones teóricas
    # ------------------------------------------------------------------

    def _generar_secciones(self, tema: str, disciplina: str, nivel: str,
                           profundidad: str) -> List[Dict[str, Any]]:
        """Genera cada sección teórica por separado."""
        if not self.plan:
            raise ErrorBloque("No hay plan aprobado para generar secciones.")

        secciones_plan = self.plan.get("secciones", [])
        secciones_validadas: List[Dict[str, Any]] = []
        total = len(secciones_plan) or 1

        for i, sec_plan in enumerate(secciones_plan):
            self._verificar_cancelacion()
            seccion_id = sec_plan.get("id", f"seccion{i+1}")
            nombre_archivo = f"seccion_{seccion_id}.json"

            # Verificar si ya existe validado
            existente = self._cargar_bloque_si_existe(nombre_archivo)
            if existente is not None:
                existente = normalizar_claves(existente)
                exito_guardado, errores_guardado = validar_seccion_teorica(
                    existente
                )
                if exito_guardado:
                    secciones_validadas.append(existente)
                    self._notificar_progreso(
                        0.10 + 0.45 * ((i + 1) / total),
                        f"Sección {i + 1} de {total} recuperada de disco",
                    )
                    continue
                logger.warning(
                    "Sección %s: el bloque guardado no es válido (%s); "
                    "se regenera.",
                    seccion_id, "; ".join(errores_guardado),
                )

            # Generar con reintentos
            seccion_valida = self._generar_una_seccion(
                sec_plan, tema, disciplina, nivel, profundidad,
                nombre_archivo,
            )
            secciones_validadas.append(seccion_valida)
            self._notificar_progreso(
                0.10 + 0.45 * ((i + 1) / total),
                f"Sección {i + 1} de {total} completada",
            )

        self.secciones_validadas = secciones_validadas
        return secciones_validadas

    def _notificar_progreso(self, progreso: float, etapa: str) -> None:
        """Informa un hito real a la interfaz, si hay callback registrado."""
        callback = getattr(self, "_callback_progreso", None)
        if not callback:
            return
        try:
            callback(progreso, etapa)
        except Exception:
            # Un fallo al refrescar la UI no debe interrumpir la generación.
            logger.debug("No se pudo notificar el progreso a la interfaz")

    def _generar_una_seccion(self, sec_plan: Dict[str, Any], tema: str,
                             disciplina: str, nivel: str, profundidad: str,
                             nombre_archivo: str) -> Dict[str, Any]:
        """Genera una sola sección teórica con reintentos limitados."""
        desde_plantillas = __import__("plantillas")
        instruccion = desde_plantillas.obtener_instruccion_seccion_teorica(
            seccion_plan=sec_plan,
            tema=tema,
            disciplina=disciplina,
            nivel=nivel,
            profundidad=profundidad,
        )

        ids_planificados = [
            recurso.get("id")
            for recurso in sec_plan.get("recursos_visuales", []) or []
            if isinstance(recurso, dict) and recurso.get("id")
        ]

        nombre_esquema, esquema, estricto = obtener_esquema_openrouter(
            "seccion_teorica"
        )
        ultimo_error = ""
        for intento in range(MAX_REINTENTOS_BLOQUE):
            # Cancelación cooperativa: se comprueba antes de cada intento,
            # nunca en medio de una solicitud HTTP en curso.
            self._verificar_cancelacion()
            try:
                texto_respuesta, proveedor = generar_contenido_educativo(
                    instruccion, self._orden_proveedores(),
                    proveedores_agotados=self.proveedores_agotados,
                    esquema=esquema,
                    nombre_esquema=nombre_esquema,
                    estricto=estricto,
                    validador=_validar_seccion_para_openrouter,
                    etapa=f"seccion_{sec_plan.get('id', '')}",
                    modelos_agotados=self.modelos_agotados,
                )

                # Guardar respuesta cruda
                sufijo = f"_intento{intento+1}" if intento > 0 else ""
                self._guardar_respuesta_cruda(
                    f"seccion_{sec_plan.get('id', 'sin_id')}{sufijo}_crudo.json",
                    texto_respuesta,
                )

                logger.info(f"Sección {sec_plan.get('id', '')}: respuesta recibida, longitud={len(texto_respuesta)}")

                try:
                    texto_json = _preparar_texto_json(
                        texto_respuesta, f"Sección {sec_plan.get('id', '')}"
                    )
                    seccion = json.loads(texto_json)
                except json.JSONDecodeError as e:
                    ultimo_error = str(e)
                    logger.warning(f"Sección {sec_plan.get('id', '')}: JSON inválido en intento {intento+1}: {e}")
                    # Truncamiento de JSON: reducir tamaño para el siguiente intento
                    instruccion += (
                        "\n\nIMPORTANTE: La respuesta anterior no es JSON válido "
                        "(posiblemente truncada). Genera una versión más corta."
                    )
                    continue

                # Normalizar claves (p. ej. "solución" -> "solucion").
                seccion = normalizar_claves(seccion)
                exito, errores = validar_seccion_teorica(seccion)
                if not exito:
                    ultimo_error = f"Sección no válida: {'; '.join(errores)}"
                    logger.warning(f"Sección {sec_plan.get('id', '')}: no válida en intento {intento+1}: {'; '.join(errores)}")
                    instruccion += (
                        "\n\nIMPORTANTE: La respuesta anterior no cumplió el "
                        "esquema (bloques vacíos o tipos inválidos). Devuelve "
                        "una sección completa con bloques con contenido real."
                    )
                    continue

                # Reconciliar referencias visuales con el catálogo del plan:
                # nunca se guarda una referencia a un recurso inexistente.
                seccion = self._reconciliar_referencias_de_seccion(
                    seccion, ids_planificados
                )

                self._guardar_bloque_validado(nombre_archivo, seccion)
                logger.info(f"Sección {sec_plan.get('id', '')}: generada y validada correctamente")
                return seccion

            except ErrorRespuestaIncompleta as e:
                ultimo_error = str(e)
                logger.warning(f"Sección {sec_plan.get('id', '')}: respuesta incompleta en intento {intento+1}: {e}")
                # Reducir tamaño del bloque para el siguiente intento
                instruccion += (
                    "\n\nIMPORTANTE: La respuesta anterior fue truncada o "
                    "estaba vacía. Genera una versión más concisa de esta "
                    "sección, con menos ejemplos y explicaciones más breves."
                )
                continue
            except ErrorContenidoNoJson as e:
                ultimo_error = str(e)
                logger.warning(f"Sección {sec_plan.get('id', '')}: la respuesta no fue JSON en intento {intento+1}: {e}")
                instruccion += (
                    "\n\nIMPORTANTE: Tu respuesta anterior no fue un objeto "
                    "JSON. Responde ÚNICAMENTE con el JSON de la sección, sin "
                    "explicaciones, comentarios ni mensajes de seguridad."
                )
                continue
            except ErrorModelosAgotados:
                # OpenRouter ya agotó su lista de modelos para esta solicitud.
                # No se repite la sección: el límite de intentos es global.
                raise
            except ErrorIntegracion:
                # Error de programación/integración: no es reintentable.
                raise
            except ErrorIA as e:
                ultimo_error = str(e)
                logger.error(f"Sección {sec_plan.get('id', '')}: error de IA en intento {intento+1}: {e}")
                continue

        raise ErrorBloque(
            f"No se pudo generar la sección '{sec_plan.get('titulo', '')}' "
            f"después de {MAX_REINTENTOS_BLOQUE} intentos. Último error: "
            f"{ultimo_error}"
        )

    # ------------------------------------------------------------------
    # Etapa C: Generación de ejercicios en lotes
    # ------------------------------------------------------------------

    def _cargar_lotes_ejercicios_guardados(
        self,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Carga y agrupa por dificultad los lotes de ejercicios ya validados.

        Ignora los archivos `*_crudo.json` y los lotes inválidos. Deduplica
        por id para que dos archivos no cuenten el mismo ejercicio dos veces.
        """
        agrupados: Dict[str, List[Dict[str, Any]]] = {}
        if not self.carpeta_trabajo:
            return agrupados
        vistos: Set[str] = set()
        for archivo in sorted(self.carpeta_trabajo.glob("lote_ejercicios_*.json")):
            if "_crudo" in archivo.name:
                continue
            lote = _leer_json(archivo)
            if not lote:
                continue
            lote = normalizar_claves(lote)
            exito, errores = validar_lote_ejercicios(lote)
            if not exito:
                logger.warning(
                    "Reanudación: se ignora '%s' (lote no válido): %s",
                    archivo.name, "; ".join(errores),
                )
                continue
            for ejercicio in lote.get("ejercicios", []):
                if not isinstance(ejercicio, dict):
                    continue
                eid = str(ejercicio.get("id") or "")
                if eid:
                    if eid in vistos:
                        logger.warning(
                            "Reanudación: ejercicio duplicado '%s' en '%s'; "
                            "se ignora el repetido.", eid, archivo.name,
                        )
                        continue
                    vistos.add(eid)
                dificultad = str(
                    ejercicio.get("dificultad") or ""
                ).strip().lower()
                agrupados.setdefault(dificultad, []).append(ejercicio)
        return agrupados

    def _generar_ejercicios(self, cantidad_actividades: int,
                            profundidad: str) -> List[Dict[str, Any]]:
        """Genera ejercicios en lotes pequeños, reutilizando los ya guardados."""
        if not self.plan:
            raise ErrorBloque("No hay plan aprobado para generar ejercicios.")

        distribucion = self._calcular_distribucion(cantidad_actividades)
        ejercicios_validos: List[Dict[str, Any]] = []
        guardados = (
            self._cargar_lotes_ejercicios_guardados()
            if self._reanudando else {}
        )
        # Los ids recuperados no deben repetirse si hay que generar sólo una
        # dificultad faltante. Se empieza después del mayor id numérico.
        max_id = 0
        for lista in guardados.values():
            for ejercicio in lista:
                numero = _sufijo_numerico(ejercicio.get("id"))
                if numero is not None:
                    max_id = max(max_id, numero)
        contador_id = max_id + 1
        total_lotes = sum(
            len(self._dividir_en_lotes(c, TAMANIO_LOTE_EJERCICIOS))
            for c in distribucion.values() if c > 0
        ) or 1
        lotes_completados = 0

        for dificultad, cantidad in distribucion.items():
            if cantidad <= 0:
                continue

            lotes = self._dividir_en_lotes(cantidad, TAMANIO_LOTE_EJERCICIOS)
            recuperados = guardados.get(dificultad, [])
            if len(recuperados) == cantidad:
                # Un lote guardado por dificultad ya cubre exactamente lo
                # pedido: no se vuelve a llamar a la IA.
                ejercicios_validos.extend(recuperados)
                lotes_completados += len(lotes)
                self._notificar_progreso(
                    0.55 + 0.25 * (lotes_completados / total_lotes),
                    f"Ejercicios: {cantidad} recuperados de disco "
                    f"({dificultad})",
                )
                logger.info(
                    "Ejercicios %s: %d recuperados de disco",
                    dificultad, len(recuperados),
                )
                continue

            for lote_cantidad in lotes:
                self._verificar_cancelacion()
                lote_valido = self._generar_un_lote_ejercicios(
                    dificultad=dificultad,
                    cantidad=lote_cantidad,
                    contador_inicio=contador_id,
                    profundidad=profundidad,
                )
                ejercicios_validos.extend(lote_valido)
                contador_id += len(lote_valido)
                lotes_completados += 1
                self._notificar_progreso(
                    0.55 + 0.25 * (lotes_completados / total_lotes),
                    f"Ejercicios: lote {lotes_completados} de {total_lotes} "
                    f"({dificultad})",
                )

        self.ejercicios_validos = ejercicios_validos
        return ejercicios_validos

    def _calcular_distribucion(self, cantidad: int) -> Dict[str, int]:
        """Calcula la distribución de ejercicios por dificultad."""
        if cantidad <= 8:
            inicial = max(2, round(cantidad * 0.3))
            intermedio = max(2, round(cantidad * 0.4))
            avanzado = cantidad - inicial - intermedio
        elif cantidad <= 10:
            inicial, intermedio, avanzado = 3, 4, 3
        else:
            inicial, intermedio, avanzado = 4, 5, 3
        return {
            "inicial": inicial,
            "intermedio": intermedio,
            "avanzado": avanzado,
        }

    def _dividir_en_lotes(self, cantidad: int, tamano_lote: int) -> List[int]:
        """Divide una cantidad en lotes de tamaño máximo dado."""
        lotes = []
        restante = cantidad
        while restante > 0:
            lote = min(tamano_lote, restante)
            lotes.append(lote)
            restante -= lote
        return lotes

    def _generar_un_lote_ejercicios(self, dificultad: str, cantidad: int,
                                    contador_inicio: int,
                                    profundidad: str
                                    ) -> List[Dict[str, Any]]:
        """Genera un lote de ejercicios con reintentos limitados."""
        desde_plantillas = __import__("plantillas")
        instruccion = desde_plantillas.obtener_instruccion_lote_ejercicios(
            dificultad=dificultad,
            cantidad=cantidad,
            contador_inicio=contador_inicio,
            profundidad=profundidad,
            disciplina=self.plan.get("disciplina", "") if self.plan else "",
            tema=self.plan.get("titulo", "") if self.plan else "",
            plan=self.plan,
        )

        nombre_esquema, esquema, estricto = obtener_esquema_openrouter(
            "lote_ejercicios"
        )

        def _validar_lote_para_openrouter(
            datos: Any,
        ) -> Tuple[bool, List[str]]:
            normalizado = normalizar_claves(datos)
            completo = _completar_campos_derivables_ejercicios(
                normalizado, dificultad, contador_inicio
            )
            return validar_lote_ejercicios(completo, exigir_espanol=True)

        ultimo_error = ""
        for intento in range(MAX_REINTENTOS_BLOQUE):
            # Cancelación cooperativa: se comprueba antes de cada intento,
            # nunca en medio de una solicitud HTTP en curso.
            self._verificar_cancelacion()
            try:
                texto_respuesta, proveedor = generar_contenido_educativo(
                    instruccion, self._orden_proveedores(),
                    proveedores_agotados=self.proveedores_agotados,
                    esquema=esquema,
                    nombre_esquema=nombre_esquema,
                    estricto=estricto,
                    validador=_validar_lote_para_openrouter,
                    etapa=f"lote_ejercicios_{dificultad}",
                    modelos_agotados=self.modelos_agotados,
                )

                sufijo = f"_intento{intento+1}" if intento > 0 else ""
                self._guardar_respuesta_cruda(
                    f"lote_ejercicios_{dificultad}_{cantidad}{sufijo}_crudo.json",
                    texto_respuesta,
                )

                logger.info(f"Lote ejercicios {dificultad}: respuesta recibida, longitud={len(texto_respuesta)}")

                texto_json = _preparar_texto_json(
                    texto_respuesta, f"Lote de ejercicios {dificultad}"
                )
                lote = json.loads(texto_json)
                # Normalizar claves (p. ej. "solución" -> "solucion").
                lote = normalizar_claves(lote)
                # Completar sólo lo que el programa ya sabe (dificultad e ids).
                lote = _completar_campos_derivables_ejercicios(
                    lote, dificultad, contador_inicio
                )
                exito, errores = validar_lote_ejercicios(
                    lote, exigir_espanol=True
                )
                if not exito:
                    ultimo_error = (
                        f"Lote de ejercicios no válido: {'; '.join(errores)}"
                    )
                    logger.warning(
                        "Lote ejercicios %s: no válido en intento %d: %s",
                        dificultad, intento + 1, ultimo_error,
                    )
                    instruccion += (
                        "\n\nIMPORTANTE: La respuesta anterior NO cumplió el "
                        f"esquema. Errores: {'; '.join(errores[:6])}. "
                        "Vuelve a generar el lote COMPLETO. Cada ejercicio "
                        "debe incluir, sin excepción y sin dejar vacíos: id, "
                        "dificultad, tipo, consigna, solucion y "
                        "respuesta_final. La dificultad de TODOS los "
                        f"ejercicios debe ser exactamente '{dificultad}'. "
                        "Redactá todo en español y limitate al tema central "
                        "y a las secciones indicadas."
                    )
                    continue

                ejercicios = lote.get("ejercicios", [])
                self._guardar_bloque_validado(
                    f"lote_ejercicios_{dificultad}_{contador_inicio}.json",
                    lote,
                )
                logger.info(f"Lote ejercicios {dificultad}: {len(ejercicios)} ejercicios generados y validados")
                return ejercicios

            except ErrorRespuestaIncompleta as e:
                ultimo_error = str(e)
                logger.warning(f"Lote ejercicios {dificultad}: respuesta incompleta en intento {intento+1}: {e}")
                instruccion += (
                    "\n\nIMPORTANTE: La respuesta anterior fue truncada o "
                    "estaba vacía. Genera menos ejercicios por lote, con "
                    "consignas más breves."
                )
                # Reducir cantidad para el siguiente intento
                cantidad = max(1, cantidad - 1)
                continue
            except ErrorContenidoNoJson as e:
                ultimo_error = str(e)
                logger.warning(f"Lote ejercicios {dificultad}: la respuesta no fue JSON en intento {intento+1}: {e}")
                instruccion += (
                    "\n\nIMPORTANTE: Tu respuesta anterior no fue un objeto "
                    "JSON. Responde ÚNICAMENTE con el JSON, sin explicaciones "
                    "ni mensajes de seguridad."
                )
                continue
            except json.JSONDecodeError as e:
                ultimo_error = str(e)
                logger.warning(f"Lote ejercicios {dificultad}: JSON inválido en intento {intento+1}: {e}")
                instruccion += (
                    "\n\nIMPORTANTE: La respuesta anterior no es JSON válido "
                    "(posiblemente truncada). Genera una versión más corta."
                )
                # Reducir cantidad para el siguiente intento
                cantidad = max(1, cantidad - 1)
                continue
            except ErrorModelosAgotados:
                # OpenRouter ya agotó su lista de modelos para esta solicitud.
                # No se repite el lote: el límite de intentos es global.
                raise
            except ErrorIntegracion:
                # Error de programación/integración: no es reintentable.
                raise
            except ErrorIA as e:
                ultimo_error = str(e)
                logger.error(f"Lote ejercicios {dificultad}: error de IA en intento {intento+1}: {e}")
                continue

        raise ErrorBloque(
            f"No se pudo generar lote de {cantidad} ejercicios de dificultad "
            f"'{dificultad}' después de {MAX_REINTENTOS_BLOQUE} intentos. "
            f"Último error: {ultimo_error}"
        )

    # ------------------------------------------------------------------
    # Etapa D: Componentes finales
    # ------------------------------------------------------------------

    def _generar_componentes_finales(self) -> Dict[str, Any]:
        """Genera resumen, glosario y metadatos finales."""
        if self._reanudando:
            guardados = self._cargar_bloque_si_existe("componentes_finales.json")
            if guardados is not None:
                normalizado = normalizar_claves(guardados)
                exito, errores = validar_componentes_finales(normalizado)
                if exito:
                    self.componentes_finales = normalizado
                    logger.info(
                        "Componentes finales: recuperados de disco; "
                        "no se llama a la IA."
                    )
                    return normalizado
                logger.warning(
                    "Componentes finales guardados no válidos; se regeneran: %s",
                    "; ".join(errores),
                )

        desde_plantillas = __import__("plantillas")
        instruccion = desde_plantillas.obtener_instruccion_componentes_finales(
            plan=self.plan,
            secciones=self.secciones_validadas,
            ejercicios=self.ejercicios_validos,
        )

        nombre_esquema, esquema, estricto = obtener_esquema_openrouter(
            "componentes_finales"
        )
        ultimo_error = ""
        for intento in range(MAX_REINTENTOS_BLOQUE):
            # Cancelación cooperativa: se comprueba antes de cada intento,
            # nunca en medio de una solicitud HTTP en curso.
            self._verificar_cancelacion()
            try:
                texto_respuesta, proveedor = generar_contenido_educativo(
                    instruccion, self._orden_proveedores(),
                    proveedores_agotados=self.proveedores_agotados,
                    esquema=esquema,
                    nombre_esquema=nombre_esquema,
                    estricto=estricto,
                    validador=_validar_componentes_para_openrouter,
                    etapa="componentes_finales",
                    modelos_agotados=self.modelos_agotados,
                )

                sufijo = f"_intento{intento+1}" if intento > 0 else ""
                self._guardar_respuesta_cruda(
                    f"componentes_finales{sufijo}_crudo.json",
                    texto_respuesta,
                )

                logger.info(f"Componentes finales: respuesta recibida, longitud={len(texto_respuesta)}")

                texto_json = _preparar_texto_json(
                    texto_respuesta, "Componentes finales"
                )
                componentes = json.loads(texto_json)
                # Normalizar claves (p. ej. "solución" -> "solucion").
                componentes = normalizar_claves(componentes)
                exito, errores = validar_componentes_finales(componentes)
                if not exito:
                    ultimo_error = (
                        f"Componentes finales no válidos: {'; '.join(errores)}"
                    )
                    logger.warning(
                        "Componentes finales: no válidos en intento %d: %s",
                        intento + 1, ultimo_error,
                    )
                    instruccion += (
                        "\n\nIMPORTANTE: La respuesta anterior NO cumplió el "
                        f"esquema. Errores: {'; '.join(errores[:6])}. "
                        "Devuelve TODOS los campos obligatorios: "
                        "resumen_final, glosario (lista de objetos con "
                        "termino y definicion) y metadatos con titulo, tema, "
                        "disciplina y nivel."
                    )
                    continue

                self._guardar_bloque_validado("componentes_finales.json",
                                              componentes)
                self.componentes_finales = componentes
                logger.info(f"Componentes finales: generados y validados correctamente")
                return componentes

            except ErrorRespuestaIncompleta as e:
                ultimo_error = str(e)
                logger.warning(f"Componentes finales: respuesta incompleta en intento {intento+1}: {e}")
                instruccion += (
                    "\n\nIMPORTANTE: La respuesta anterior fue truncada o "
                    "estaba vacía. Genera una versión más concisa del resumen "
                    "y glosario."
                )
                continue
            except ErrorContenidoNoJson as e:
                ultimo_error = str(e)
                logger.warning(f"Componentes finales: la respuesta no fue JSON en intento {intento+1}: {e}")
                instruccion += (
                    "\n\nIMPORTANTE: Tu respuesta anterior no fue un objeto "
                    "JSON. Responde ÚNICAMENTE con el JSON, sin explicaciones "
                    "ni mensajes de seguridad."
                )
                continue
            except json.JSONDecodeError as e:
                ultimo_error = str(e)
                logger.warning(f"Componentes finales: JSON inválido en intento {intento+1}: {e}")
                instruccion += (
                    "\n\nIMPORTANTE: La respuesta anterior no es JSON válido "
                    "(posiblemente truncada). Genera una versión más corta."
                )
                continue
            except ErrorModelosAgotados:
                # OpenRouter ya agotó su lista de modelos para esta solicitud.
                # No se repiten los componentes: el límite es global.
                raise
            except ErrorIntegracion:
                # Error de programación/integración: no es reintentable.
                raise
            except ErrorIA as e:
                ultimo_error = str(e)
                logger.error(f"Componentes finales: error de IA en intento {intento+1}: {e}")
                continue

        raise ErrorBloque(
            f"No se pudieron generar los componentes finales después de "
            f"{MAX_REINTENTOS_BLOQUE} intentos. Último error: {ultimo_error}"
        )

    # ------------------------------------------------------------------
    # Reconciliación de referencias visuales
    # ------------------------------------------------------------------
    #
    # El catálogo canónico de recursos visuales es
    # `plan["recursos_visuales_planificados"]` (el que termina en
    # `documento["recursos_visuales"]`). Las secciones sólo pueden
    # referenciar ids de ese catálogo. Si el modelo inventa un id o suelta
    # la referencia, se reconecta a un recurso planificado de la sección;
    # si no hay ninguno disponible, se elimina la referencia colgante.
    # Nunca se inventan recursos: sólo se usan ids existentes.

    def _reconciliar_referencias_de_seccion(
        self, seccion: Dict[str, Any], ids_permitidos: List[str]
    ) -> Dict[str, Any]:
        """
        Devuelve una copia de la sección con referencias visuales válidas.

        `ids_permitidos` son los ids del catálogo asignados a esta sección.
        No modifica el diccionario original.
        """
        permitidos: List[str] = [i for i in (ids_permitidos or []) if i]
        sid = seccion.get("seccion_id") or seccion.get("id") or ""
        nuevos: List[Dict[str, Any]] = []
        usados = set()

        for bloque in seccion.get("bloques", []) or []:
            if isinstance(bloque, dict) and bloque.get("tipo") == "visual_reference":
                ref = bloque.get("recurso_id")
                if ref in permitidos:
                    if ref in usados:
                        logger.warning(
                            f"Sección {sid}: referencia duplicada al recurso "
                            f"'{ref}'; se elimina el duplicado."
                        )
                        continue
                    usados.add(ref)
                    nuevos.append(bloque)
                    continue
                libre = next((r for r in permitidos if r not in usados), None)
                if libre is not None:
                    logger.info(
                        f"Sección {sid}: la referencia '{ref}' no está en el "
                        f"catálogo; se reconecta al recurso planificado "
                        f"'{libre}'."
                    )
                    usados.add(libre)
                    nuevos.append({
                        "tipo": "visual_reference",
                        "recurso_id": libre,
                        "posicion": bloque.get("posicion", "despues_bloque"),
                    })
                else:
                    logger.warning(
                        f"Sección {sid}: se elimina la referencia colgante "
                        f"'{ref}' (no hay recurso planificado disponible)."
                    )
            else:
                nuevos.append(bloque)

        # Referencias a recursos planificados que el modelo no incluyó.
        for rid in permitidos:
            if rid not in usados:
                logger.info(
                    f"Sección {sid}: se agrega la referencia al recurso "
                    f"planificado '{rid}' que no estaba referenciado."
                )
                nuevos.append({
                    "tipo": "visual_reference",
                    "recurso_id": rid,
                    "posicion": "final_seccion",
                })
                usados.add(rid)

        copia = dict(seccion)
        copia["bloques"] = nuevos
        return copia

    def _recursos_por_seccion(self, documento: Dict[str, Any]
                              ) -> Dict[str, List[str]]:
        """Determina qué ids del catálogo pertenecen a cada sección."""
        catalogo = documento.get("recursos_visuales", []) or []
        ids_catalogo = [
            r.get("id") for r in catalogo
            if isinstance(r, dict) and r.get("id")
        ]
        set_catalogo = set(ids_catalogo)

        pertenencia: Dict[str, List[str]] = {}
        for recurso in catalogo:
            if not isinstance(recurso, dict):
                continue
            ubicacion = recurso.get("ubicacion")
            sid = ubicacion.get("seccion_id") if isinstance(ubicacion, dict) else None
            if sid:
                pertenencia.setdefault(sid, []).append(recurso.get("id"))

        planes = {
            s.get("id"): s
            for s in (self.plan or {}).get("secciones", [])
            if isinstance(s, dict) and s.get("id")
        }

        resultado: Dict[str, List[str]] = {}
        for seccion in documento.get("secciones", []) or []:
            if not isinstance(seccion, dict):
                continue
            sid = seccion.get("seccion_id") or seccion.get("id")
            candidatos: List[str] = []
            for recurso in (planes.get(sid, {}) or {}).get("recursos_visuales", []) or []:
                rid = recurso.get("id") if isinstance(recurso, dict) else recurso
                if rid in set_catalogo and rid not in candidatos:
                    candidatos.append(rid)
            for rid in pertenencia.get(sid, []):
                if rid in set_catalogo and rid not in candidatos:
                    candidatos.append(rid)
            resultado[sid] = candidatos
        return resultado

    def _reconciliar_referencias_visuales(self, documento: Dict[str, Any]
                                          ) -> Dict[str, Any]:
        """
        Garantiza que el documento no tenga referencias visuales colgantes.

        Devuelve una copia del documento con las secciones reconciliadas
        contra el catálogo `recursos_visuales`. Deja constancia en el log
        del origen de cada corrección.
        """
        recursos_por_seccion = self._recursos_por_seccion(documento)
        nuevas_secciones = []
        for seccion in documento.get("secciones", []) or []:
            if not isinstance(seccion, dict):
                nuevas_secciones.append(seccion)
                continue
            sid = seccion.get("seccion_id") or seccion.get("id")
            nuevas_secciones.append(
                self._reconciliar_referencias_de_seccion(
                    seccion, recursos_por_seccion.get(sid, [])
                )
            )

        copia = dict(documento)
        copia["secciones"] = nuevas_secciones
        return copia

    # ------------------------------------------------------------------
    # Etapa E: Ensamblado local
    # ------------------------------------------------------------------

    def _ensamblar_documento(self, cantidad_actividades: int
                             ) -> Dict[str, Any]:
        """Ensambla todas las partes en el documento final."""
        if not self.plan:
            raise ErrorBloque("No hay plan para ensamblar el documento.")
        if not self.secciones_validadas:
            raise ErrorBloque("No hay secciones validadas para ensamblar.")
        if not self.ejercicios_validos:
            raise ErrorBloque("No hay ejercicios validados para ensamblar.")
        if not self.componentes_finales:
            raise ErrorBloque(
                "No hay componentes finales para ensamblar el documento."
            )

        metadatos_finales = self.componentes_finales.get("metadatos", {})
        if not isinstance(metadatos_finales, dict):
            metadatos_finales = {}
        else:
            metadatos_finales = dict(metadatos_finales)
        # La fecha es un dato local, no una invención del modelo. Se asigna
        # siempre al ensamblar para que un JSON viejo no vuelva a mostrarla.
        metadatos_finales["fecha_generacion"] = (
            datetime.datetime.now().strftime("%d/%m/%Y")
        )

        documento = {
            "metadatos": metadatos_finales,
            "objetivos_aprendizaje": self.plan.get("objetivos_aprendizaje", []),
            "conocimientos_previos": self.plan.get("conocimientos_previos", []),
            "introduccion": self.componentes_finales.get("introduccion", ""),
            "secciones": self.secciones_validadas,
            "ejemplos_resueltos": self._extraer_ejemplos_de_secciones(),
            "actividades": self.ejercicios_validos,
            "solucionario": self._extraer_solucionario_de_ejercicios(),
            "glosario": self.componentes_finales.get("glosario", []),
            "resumen_final": self.componentes_finales.get("resumen_final", ""),
            "fuentes": [],
            "recursos_visuales": self.plan.get("recursos_visuales_planificados", []),
            "advertencia_ia": (
                "Este material fue generado con inteligencia artificial. "
                "Se recomienda contrastar la información importante con fuentes "
                "confiables o con un docente."
            ),
        }

        # Garantizar que las referencias visuales apunten al catálogo del plan
        # (única fuente de verdad) antes de validar el documento.
        documento = self._reconciliar_referencias_visuales(documento)

        exito, errores = validar_documento_ensamblado(documento)
        if not exito:
            raise ErrorBloque(
                f"El documento ensamblado no es válido: {'; '.join(errores)}"
            )

        # Validar contra el esquema completo del PDF
        exito_pdf, errores_pdf = validar_estructura_material(
            documento, cantidad_actividades
        )
        if not exito_pdf:
            raise ErrorBloque(
                f"El documento no cumple los requisitos del PDF: "
                f"{'; '.join(errores_pdf)}"
            )

        self._guardar_bloque_validado("documento_ensamblado.json", documento)
        return documento

    def _extraer_ejemplos_de_secciones(self) -> List[Dict[str, Any]]:
        """Extrae ejemplos resueltos de las secciones validadas."""
        ejemplos = []
        for seccion in self.secciones_validadas:
            for bloque in seccion.get("bloques", []):
                if bloque.get("tipo") == "ejemplo_resuelto":
                    ejemplos.append(bloque)
        return ejemplos

    def _extraer_solucionario_de_ejercicios(self) -> List[Dict[str, Any]]:
        """Extrae el solucionario de los ejercicios validados."""
        solucionario = []
        for ej in self.ejercicios_validos:
            solucionario.append({
                "actividad_id": ej.get("id", ""),
                "respuesta": ej.get("respuesta_final", ""),
                "procedimiento": ej.get("solucion", ""),
                "explicacion": ej.get("explicacion", ""),
                "criterios": ej.get("criterios_correccion", ""),
            })
        return solucionario

    # ------------------------------------------------------------------
    # Flujo principal
    # ------------------------------------------------------------------

    def _orden_proveedores(self) -> list:
        """Obtiene el orden de proveedores configurado."""
        from configuracion import AI_PROVIDER_ORDER, proveedor_esta_configurado
        orden = []
        for nombre in AI_PROVIDER_ORDER:
            nombre = nombre.strip().lower()
            if nombre and proveedor_esta_configurado(nombre):
                orden.append(nombre)
        return orden

    def generar(
        self,
        tema: str,
        disciplina: str,
        nivel: str,
        profundidad: str,
        cantidad_actividades: int,
        recursos_visuales: bool,
        usar_imagenes_externas: bool = False,
        usar_demostracion: bool = False,
        trabajo_id: Optional[str] = None,
        callback_progreso: Optional[callable] = None,
        cancelacion: Optional[object] = None,
        reanudar: bool = False,
    ) -> Dict[str, Any]:
        """
        Ejecuta el flujo completo de generación segmentada.

        Si `reanudar=True` y `trabajo_id` apunta a una carpeta existente, se
        reutilizan el plan, las secciones, los lotes de ejercicios y los
        componentes ya validados. Sólo se pide a la IA lo que falte.
        """
        self.trabajo_id = trabajo_id or uuid.uuid4().hex[:12]
        self.carpeta_trabajo = self._crear_carpeta_trabajo(self.trabajo_id)
        self._reanudando = bool(reanudar)
        # Callback de progreso disponible para todas las etapas internas.
        self._callback_progreso = callback_progreso
        self._cancelacion = cancelacion

        resultado: Dict[str, Any] = {
            "exito": False,
            "trabajo_id": self.trabajo_id,
            "ruta_pdf": None,
            "material": None,
            "mensaje": "",
            "proveedor_usado": None,
            "advertencia_imagenes": "",
            "cancelado": False,
        }

        try:
            tiempo_inicio = datetime.datetime.now()
            tiempo_limite = datetime.timedelta(seconds=TIEMPO_MAX_GENERACION_SEGUNDOS)

            def verificar_tiempo_limite():
                """Verifica corte por tiempo o por cierre de la ventana."""
                self._verificar_cancelacion()
                if datetime.datetime.now() - tiempo_inicio > tiempo_limite:
                    raise ErrorBloque(
                        f"Tiempo máximo de generación excedido "
                        f"({TIEMPO_MAX_GENERACION_SEGUNDOS} segundos). "
                        f"Los bloques ya validados quedaron guardados; "
                        f"podés reanudar el trabajo con 'Restaurar trabajo'."
                    )

            # Configuración guardada: se escribe también en un archivo
            # independiente para poder reanudar aunque el estado se actualice.
            configuracion_trabajo = {
                "tema": tema, "disciplina": disciplina, "nivel": nivel,
                "profundidad": profundidad,
                "cantidad_actividades": cantidad_actividades,
                "recursos_visuales": recursos_visuales,
                "usar_imagenes_externas": usar_imagenes_externas,
                "usar_demostracion": usar_demostracion,
            }
            self._guardar_bloque_validado(
                "configuracion.json", configuracion_trabajo
            )
            self._guardar_estado(
                ESTADO_PLANNING, {"configuracion": configuracion_trabajo}
            )

            if usar_demostracion or MODO_DEMOSTRACION:
                logger.info(f"Trabajo {self.trabajo_id}: modo demostración activado")
                material = self._material_demostracion(
                    tema, disciplina, nivel, cantidad_actividades
                )
                resultado["proveedor_usado"] = "demostracion"
                # Guardar material en disco para recuperación posterior
                self._guardar_bloque_validado("material_validado.json", material)
                self._guardar_bloque_validado("documento_ensamblado.json", material)
                self._guardar_estado(ESTADO_COMPLETED, {"modo": "demostracion"})
                self._notificar_progreso(0.85, "Contenido de demostración listo")
            else:
                # --- ETAPA A: Planificación ---
                logger.info(f"Trabajo {self.trabajo_id}: iniciando planificación")
                verificar_tiempo_limite()
                self._guardar_estado(ESTADO_PLANNING, {"etapa": "planificacion"})
                self._notificar_progreso(0.05, "Planificación")
                plan = self._recuperar_plan_si_existe()
                if plan is None:
                    plan = self._generar_plan(
                        tema, disciplina, nivel, profundidad,
                        cantidad_actividades, recursos_visuales,
                    )
                self._guardar_estado(ESTADO_PLAN_VALIDATED, {
                    "secciones_planificadas": len(self.plan.get("secciones", []))
                })
                logger.info(f"Trabajo {self.trabajo_id}: planificación completada, {len(self.plan.get('secciones', []))} secciones")
                self._notificar_progreso(
                    0.10,
                    f"Planificación completada "
                    f"({len(self.plan.get('secciones', []))} secciones)",
                )

                # --- ETAPA B: Secciones teóricas ---
                logger.info(f"Trabajo {self.trabajo_id}: generando {len(self.plan.get('secciones', []))} secciones")
                self._guardar_estado(ESTADO_GENERATING_SECTIONS, {
                    "etapa": "secciones_teoricas",
                    "total_secciones": len(self.plan.get("secciones", []))
                })
                self._notificar_progreso(0.10, "Generando secciones teóricas")
                secciones = self._generar_secciones(
                    tema, disciplina, nivel, profundidad
                )

                # --- ETAPA C: Ejercicios ---
                logger.info(f"Trabajo {self.trabajo_id}: generando {cantidad_actividades} ejercicios")
                verificar_tiempo_limite()
                self._guardar_estado(ESTADO_GENERATING_EXERCISES, {
                    "etapa": "ejercicios",
                    "total_ejercicios": cantidad_actividades
                })
                self._notificar_progreso(0.55, "Generando ejercicios")
                ejercicios = self._generar_ejercicios(
                    cantidad_actividades, profundidad
                )

                # --- ETAPA D: Componentes finales ---
                logger.info(f"Trabajo {self.trabajo_id}: generando componentes finales")
                verificar_tiempo_limite()
                self._guardar_estado(ESTADO_ASSEMBLING_CONTENT, {
                    "etapa": "componentes_finales"
                })
                self._notificar_progreso(0.80, "Generando resumen y glosario")
                componentes = self._generar_componentes_finales()

                # --- ETAPA E: Ensamblado ---
                # A partir de aquí el trabajo es local (ensamblado, gráficos
                # y PDF). No se aplica el límite global: una vez generado y
                # validado todo el contenido, sería un desperdicio perderlo
                # por unos segundos de ensamblado.
                logger.info(f"Trabajo {self.trabajo_id}: ensamblando documento")
                self._guardar_estado(ESTADO_ASSEMBLING_CONTENT, {
                    "etapa": "ensamblado"
                })
                self._notificar_progreso(0.85, "Ensamblando el documento")
                material = self._ensamblar_documento(cantidad_actividades)

                resultado["proveedor_usado"] = "segmentado_multiples_solicitudes"

            # --- Gráficos y recursos visuales ---
            logger.info(f"Trabajo {self.trabajo_id}: preparando gráficos y recursos visuales")
            self._guardar_estado(ESTADO_GENERATING_VISUALS, {
                "etapa": "recursos_visuales"
            })
            self._notificar_progreso(0.88, "Generando recursos visuales")
            rutas_graficos: Dict[str, str] = {}
            if recursos_visuales:
                for recurso in material.get("recursos_visuales", []):
                    recurso_id = recurso.get("id", "")
                    ruta = generar_grafico_desde_recurso(
                        recurso, self.carpeta_trabajo / "graficos"
                    )
                    if ruta:
                        rutas_graficos[recurso_id] = ruta
                        recurso["status"] = "generado"
                        recurso["generated_asset_path"] = ruta
                    else:
                        recurso["status"] = "pendiente"

            # Imágenes externas
            rutas_imagenes_externas: Dict[str, str] = {}
            if usar_imagenes_externas:
                if not proveedor_imagenes_esta_habilitado():
                    resultado["advertencia_imagenes"] = (
                        "Imágenes generadas por IA desactivadas: no hay "
                        "proveedor configurado."
                    )
                    logger.warning(f"Trabajo {self.trabajo_id}: imágenes externas solicitadas pero proveedor no habilitado")
                else:
                    recursos_externos = seleccionar_recursos_externos(
                        material.get("recursos_visuales", []),
                        maximo=MAX_EXTERNAL_IMAGES_PER_PDF,
                    )
                    if recursos_externos:
                        rutas_imagenes_externas = generar_imagenes_seleccionadas(
                            recursos_externos,
                            self.carpeta_trabajo / "imagenes_externas",
                        )

            todas_rutas = {**rutas_graficos, **rutas_imagenes_externas}
            self._guardar_estado(ESTADO_GENERATING_VISUALS, {
                "graficos": len(rutas_graficos),
                "imagenes_externas": len(rutas_imagenes_externas),
            })
            self._notificar_progreso(0.92, "Recursos visuales preparados")

            # --- Construir PDF ---
            logger.info(f"Trabajo {self.trabajo_id}: construyendo PDF")
            self._guardar_estado(ESTADO_BUILDING_PDF, {
                "etapa": "construyendo_pdf"
            })
            self._notificar_progreso(0.95, "Construyendo el PDF")
            nombre_pdf = (
                f"{self.trabajo_id}_{tema.replace(' ', '_')[:30]}.pdf"
            )
            ruta_pdf = CARPETA_SALIDA / nombre_pdf

            exito_pdf = construir_pdf(material, todas_rutas, ruta_pdf)
            if not exito_pdf:
                raise ErrorIA("No se pudo construir el PDF con ReportLab.")

            tiempo_total = (datetime.datetime.now() - tiempo_inicio).total_seconds()
            self._guardar_estado(ESTADO_COMPLETED, {
                "ruta_pdf": str(ruta_pdf),
                "tiempo_total_segundos": tiempo_total,
            })

            resultado["exito"] = True
            resultado["ruta_pdf"] = str(ruta_pdf)
            resultado["material"] = material
            resultado["mensaje"] = "Documento generado correctamente."
            logger.info(f"Trabajo {self.trabajo_id}: completado en {tiempo_total:.1f} segundos")
            self._notificar_progreso(1.0, "Completado")
            return resultado

        except ErrorCancelado as e:
            mensaje = (
                f"Generación cancelada: {e} Los bloques ya completados quedaron "
                f"guardados en temporal/{self.trabajo_id}/ y podés reanudar el "
                f"trabajo más tarde."
            )
            logger.info(f"Trabajo {self.trabajo_id}: {mensaje}")
            self._guardar_estado(ESTADO_FAILED, {"tipo_error": "cancelado"},
                                 mensaje_error=mensaje)
            resultado["cancelado"] = True
            resultado["mensaje"] = mensaje
            return resultado

        except ErrorBloque as e:
            mensaje = f"Error en generación segmentada: {e}"
            logger.error(f"Trabajo {self.trabajo_id}: {mensaje}")
            self._guardar_estado(ESTADO_FAILED, {},
                                 mensaje_error=mensaje)
            resultado["mensaje"] = mensaje
            return resultado

        except ErrorIntegracion as e:
            mensaje = (
                "Error de integración con el proveedor de IA. No es un "
                "problema del contenido generado ni de la clave de API: el "
                "código llamó al SDK con parámetros no admitidos por la "
                f"versión instalada. Detalle: {e}"
            )
            logger.error(f"Trabajo {self.trabajo_id}: {mensaje}")
            self._guardar_estado(ESTADO_FAILED, {"tipo_error": "integracion"},
                                 mensaje_error=mensaje)
            resultado["mensaje"] = mensaje
            return resultado

        except ErrorValidacion as e:
            mensaje = f"Error de validación: {e}"
            logger.error(f"Trabajo {self.trabajo_id}: {mensaje}")
            self._guardar_estado(ESTADO_FAILED, {},
                                 mensaje_error=mensaje)
            resultado["mensaje"] = mensaje
            return resultado

        except ErrorModelosAgotados as e:
            mensaje = (
                "Ningún modelo gratuito de OpenRouter devolvió una respuesta "
                "válida. Revisá OPENROUTER_MODELS y ejecutá el diagnóstico: "
                "python tools/diagnostico_openrouter_json.py --catalogo. "
                "Los bloques ya validados quedaron guardados para reanudar. "
                f"Detalle: {e}"
            )
            logger.error(f"Trabajo {self.trabajo_id}: {mensaje}")
            self._guardar_estado(
                ESTADO_FAILED, {"tipo_error": "modelos_agotados"},
                mensaje_error=mensaje,
            )
            resultado["mensaje"] = mensaje
            return resultado

        except ErrorIA as e:
            mensaje = f"Error de proveedor de IA: {e}"
            logger.error(f"Trabajo {self.trabajo_id}: {mensaje}")
            self._guardar_estado(ESTADO_FAILED, {},
                                 mensaje_error=mensaje)
            resultado["mensaje"] = mensaje
            return resultado

        except Exception as e:
            mensaje = f"Error inesperado: {e}"
            logger.error(f"Trabajo {self.trabajo_id}: {mensaje}", exc_info=True)
            self._guardar_estado(ESTADO_FAILED, {},
                                 mensaje_error=mensaje)
            resultado["mensaje"] = mensaje
            return resultado

    # ------------------------------------------------------------------
    # Recuperación de trabajo interrumpido
    # ------------------------------------------------------------------

    def _rutas_visuales_guardadas(self, carpeta: Path) -> Dict[str, str]:
        """Recupera las rutas de gráficos e imágenes externas de un trabajo."""
        rutas: Dict[str, str] = {}
        carpeta_graficos = carpeta / "graficos"
        if carpeta_graficos.exists():
            for archivo in carpeta_graficos.iterdir():
                if archivo.suffix.lower() != ".png":
                    continue
                partes = archivo.stem.split("_", 1)
                if len(partes) == 2:
                    rutas[partes[1]] = str(archivo)
        carpeta_externas = carpeta / "imagenes_externas"
        if carpeta_externas.exists():
            for archivo in carpeta_externas.glob("imagen_ext_*.png"):
                recurso_id = archivo.stem[len("imagen_ext_"):]
                if recurso_id:
                    rutas[recurso_id] = str(archivo)
        return rutas

    def _configuracion_desde_trabajo(
        self,
        carpeta: Path,
        plan: Optional[Dict[str, Any]] = None,
        componentes: Optional[Dict[str, Any]] = None,
        ejercicios: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Reconstruye la configuración original de un trabajo.

        Prioriza `configuracion.json` y el bloque `configuracion` del estado.
        Para trabajos antiguos, completa lo que se pueda deducir del plan y
        de los metadatos. Nunca inventa contenido: sólo usa datos guardados.
        """
        configuracion: Dict[str, Any] = {}
        estado = _leer_json(carpeta / "estado.json") or {}
        if isinstance(estado.get("configuracion"), dict):
            configuracion.update(estado["configuracion"])
        guardada = _leer_json(carpeta / "configuracion.json")
        if guardada:
            configuracion.update(guardada)

        plan = plan or {}
        metadatos = (componentes or {}).get("metadatos", {}) or {}
        ejercicios = ejercicios or []

        if not configuracion.get("tema"):
            configuracion["tema"] = (
                plan.get("titulo") or metadatos.get("tema")
                or metadatos.get("titulo") or ""
            )
        if not configuracion.get("disciplina"):
            configuracion["disciplina"] = (
                plan.get("disciplina") or metadatos.get("disciplina")
                or "Detectar automáticamente"
            )
        if not configuracion.get("nivel"):
            configuracion["nivel"] = (
                plan.get("nivel") or metadatos.get("nivel") or "Secundario"
            )
        if not configuracion.get("profundidad"):
            configuracion["profundidad"] = (
                plan.get("profundidad") or "estandar"
            )
        if not configuracion.get("cantidad_actividades"):
            configuracion["cantidad_actividades"] = (
                metadatos.get("cantidad_actividades")
                or len(ejercicios) or 10
            )
        if "recursos_visuales" not in configuracion:
            configuracion["recursos_visuales"] = bool(
                plan.get("recursos_visuales_planificados")
                or (carpeta / "graficos").exists()
            )
        if "usar_imagenes_externas" not in configuracion:
            carpeta_externas = carpeta / "imagenes_externas"
            configuracion["usar_imagenes_externas"] = bool(
                carpeta_externas.exists()
                and any(carpeta_externas.glob("imagen_ext_*.png"))
            )
        if "usar_demostracion" not in configuracion:
            configuracion["usar_demostracion"] = False
        return configuracion

    def analizar_trabajo(self, trabajo_id: str) -> Optional[Dict[str, Any]]:
        """
        Describe un trabajo guardado sin llamar a la IA ni modificar archivos.

        Devuelve cuántas secciones, ejercicios y componentes válidos hay, si
        se puede reconstruir el PDF sin IA y la configuración recuperable.
        """
        carpeta = CARPETA_TEMPORAL / trabajo_id
        if not carpeta.is_dir():
            return None
        estado = _leer_json(carpeta / "estado.json") or {}

        plan = _leer_json(carpeta / "plan.json")
        if plan is not None:
            plan = normalizar_claves(plan)
            if not validar_plan_aprendizaje(plan)[0]:
                plan = None

        secciones: List[Dict[str, Any]] = []
        ids_seccion: Set[str] = set()
        for archivo in sorted(carpeta.glob("seccion_*.json")):
            if "_crudo" in archivo.name:
                continue
            seccion = _leer_json(archivo)
            if not seccion:
                continue
            seccion = normalizar_claves(seccion)
            if not validar_seccion_teorica(seccion)[0]:
                continue
            sid = seccion.get("seccion_id")
            if sid in ids_seccion:
                continue
            ids_seccion.add(sid)
            secciones.append(seccion)

        ejercicios: List[Dict[str, Any]] = []
        ids_ejercicio: Set[str] = set()
        for archivo in sorted(carpeta.glob("lote_ejercicios_*.json")):
            if "_crudo" in archivo.name:
                continue
            lote = _leer_json(archivo)
            if not lote:
                continue
            lote = normalizar_claves(lote)
            if not validar_lote_ejercicios(lote)[0]:
                continue
            for ejercicio in lote.get("ejercicios", []):
                if not isinstance(ejercicio, dict):
                    continue
                eid = ejercicio.get("id")
                if eid in ids_ejercicio:
                    continue
                ids_ejercicio.add(eid)
                ejercicios.append(ejercicio)

        componentes = _leer_json(carpeta / "componentes_finales.json")
        if componentes is not None:
            componentes = normalizar_claves(componentes)
            if not validar_componentes_finales(componentes)[0]:
                componentes = None

        documento = _leer_json(carpeta / "documento_ensamblado.json")
        material = _leer_json(carpeta / "material_validado.json")

        ids_plan = [
            seccion.get("id") for seccion in (plan or {}).get("secciones", [])
            if isinstance(seccion, dict) and seccion.get("id")
        ]
        faltantes = [sid for sid in ids_plan if sid not in ids_seccion]
        puede_sin_ia = bool(documento or material) or bool(
            plan and ids_plan and not faltantes and ejercicios and componentes
        )
        configuracion = self._configuracion_desde_trabajo(
            carpeta, plan, componentes, ejercicios
        )

        return {
            "trabajo_id": trabajo_id,
            "estado": str(estado.get("estado") or "desconocido"),
            "fecha": str(estado.get("fecha") or ""),
            "mensaje_error": str(estado.get("mensaje_error") or ""),
            "titulo": str(configuracion.get("tema") or "Trabajo sin título"),
            "secciones_ok": len(secciones),
            "secciones_total": len(ids_plan),
            "secciones_faltantes": faltantes,
            "ejercicios": len(ejercicios),
            "componentes": bool(componentes),
            "tiene_plan": bool(plan),
            "puede_reconstruir_sin_ia": puede_sin_ia,
            "puede_continuar_con_ia": bool(
                configuracion.get("tema")
                and (plan or secciones or ejercicios or componentes)
            ),
            "configuracion": configuracion,
        }

    def listar_trabajos_recuperables(self) -> List[Dict[str, Any]]:
        """Lista trabajos fallidos o interrumpidos que se pueden reanudar."""
        if not CARPETA_TEMPORAL.exists():
            return []
        estados_incompletos = {
            ESTADO_PLANNING, ESTADO_PLAN_VALIDATED,
            ESTADO_GENERATING_SECTIONS, ESTADO_GENERATING_EXERCISES,
            ESTADO_ASSEMBLING_CONTENT, ESTADO_GENERATING_VISUALS,
            ESTADO_BUILDING_PDF, ESTADO_FAILED,
        }
        recuperables: List[Dict[str, Any]] = []
        for carpeta in CARPETA_TEMPORAL.iterdir():
            if not carpeta.is_dir():
                continue
            estado = _leer_json(carpeta / "estado.json")
            if not estado:
                continue
            info = self.analizar_trabajo(carpeta.name)
            if info is None:
                continue
            if not (info.get("puede_reconstruir_sin_ia")
                    or info.get("tiene_plan")):
                # Sin plan ni documento no hay nada que reanudar: sería una
                # generación nueva, no una restauración.
                continue
            estado_actual = info.get("estado") or ""
            if estado_actual not in estados_incompletos:
                # Un trabajo completado sólo interesa si su PDF desapareció.
                ruta_pdf = estado.get("ruta_pdf")
                if estado_actual != ESTADO_COMPLETED:
                    continue
                if ruta_pdf and Path(str(ruta_pdf)).exists():
                    continue
            recuperables.append(info)
        recuperables.sort(key=lambda item: item.get("fecha", ""),
                          reverse=True)
        return recuperables

    def continuar_desde_trabajo(
        self,
        trabajo_id: str,
        callback_progreso: Optional[callable] = None,
        cancelacion: Optional[object] = None,
    ) -> Dict[str, Any]:
        """
        Reanuda un trabajo incompleto reutilizando los bloques ya validados.

        Sólo se llama a la IA para las secciones, lotes o componentes que
        falten. Si el trabajo ya tiene todo, no se hace ninguna llamada.
        """
        info = self.analizar_trabajo(trabajo_id)
        if info is None:
            return {
                "exito": False,
                "mensaje": "No se encontró el trabajo especificado.",
            }
        configuracion = info.get("configuracion") or {}
        tema = str(configuracion.get("tema") or "").strip()
        if not tema:
            return {
                "exito": False,
                "mensaje": (
                    "No se pudo recuperar el tema del trabajo. No se reanudó "
                    "para evitar generar contenido con datos incorrectos."
                ),
            }
        try:
            cantidad = int(configuracion.get("cantidad_actividades") or 10)
        except (TypeError, ValueError):
            cantidad = 10
        return self.generar(
            tema=tema,
            disciplina=str(
                configuracion.get("disciplina")
                or "Detectar automáticamente"
            ),
            nivel=str(configuracion.get("nivel") or "Secundario"),
            profundidad=str(configuracion.get("profundidad") or "estandar"),
            cantidad_actividades=cantidad,
            recursos_visuales=bool(
                configuracion.get("recursos_visuales", False)
            ),
            usar_imagenes_externas=bool(
                configuracion.get("usar_imagenes_externas", False)
            ),
            usar_demostracion=bool(
                configuracion.get("usar_demostracion", False)
            ),
            trabajo_id=trabajo_id,
            callback_progreso=callback_progreso,
            cancelacion=cancelacion,
            reanudar=True,
        )

    def regenerar_desde_trabajo(self, trabajo_id: str) -> Dict[str, Any]:
        """
        Reconstruye el PDF de un trabajo usando sólo bloques guardados.

        No llama a la IA. Prioriza el documento ensamblado o el material
        validado; si no existen, ensambla desde plan, secciones, lotes y
        componentes, pero sólo si están todas las secciones planificadas.
        """
        carpeta = CARPETA_TEMPORAL / trabajo_id
        if not carpeta.is_dir():
            return {
                "exito": False,
                "mensaje": "No se encontró el trabajo especificado.",
            }

        self.trabajo_id = trabajo_id
        self.carpeta_trabajo = carpeta
        self._reanudando = False
        rutas_visuales = self._rutas_visuales_guardadas(carpeta)
        ruta_pdf = CARPETA_SALIDA / f"recuperado_{trabajo_id}.pdf"

        def _exito(material: Dict[str, Any], mensaje: str) -> Dict[str, Any]:
            self._guardar_estado(
                ESTADO_COMPLETED,
                {"ruta_pdf": str(ruta_pdf), "recuperado_sin_ia": True},
            )
            return {
                "exito": True,
                "ruta_pdf": str(ruta_pdf),
                "mensaje": mensaje,
                "material": material,
            }

        # Primero: documento ensamblado completo.
        documento = self._cargar_bloque_si_existe("documento_ensamblado.json")
        if documento:
            if construir_pdf(documento, rutas_visuales, ruta_pdf):
                return _exito(
                    documento,
                    "PDF regenerado desde el documento ensamblado guardado.",
                )
            return {
                "exito": False,
                "mensaje": (
                    "No se pudo regenerar el PDF desde el documento "
                    "ensamblado."
                ),
            }

        # Segundo: material validado (modo demostración o flujo antiguo).
        material_validado = self._cargar_bloque_si_existe(
            "material_validado.json"
        )
        if material_validado:
            if construir_pdf(material_validado, rutas_visuales, ruta_pdf):
                return _exito(
                    material_validado,
                    "PDF regenerado desde material validado guardado.",
                )
            return {
                "exito": False,
                "mensaje": (
                    "No se pudo regenerar el PDF desde el material validado."
                ),
            }

        estado = _leer_json(carpeta / "estado.json")
        if estado is None:
            return {
                "exito": False,
                "mensaje": "No se encontró el estado del trabajo.",
            }
        trabajo_guardado = estado.get("trabajo_id", trabajo_id)

        # Cargar bloques válidos.
        #
        # IMPORTANTE: los archivos crudos (`*_crudo.json`) son respuestas sin
        # validar; nunca deben reutilizarse como bloques buenos ni contarse
        # dos veces. Sólo se reutilizan bloques que pasan su validación y,
        # además, se descartan duplicados por id.
        plan = _leer_json(carpeta / "plan.json")
        if plan is not None:
            plan = normalizar_claves(plan)
            if not validar_plan_aprendizaje(plan)[0]:
                logger.warning(
                    "Recuperación: el plan guardado no es válido; se ignora."
                )
                plan = None

        secciones: List[Dict[str, Any]] = []
        ids_seccion: Set[str] = set()
        for archivo in sorted(carpeta.glob("seccion_*.json")):
            if "_crudo" in archivo.name:
                continue
            sec = _leer_json(archivo)
            if not sec:
                continue
            sec = normalizar_claves(sec)
            if not validar_seccion_teorica(sec)[0]:
                logger.warning(
                    "Recuperación: se ignora '%s' "
                    "(la sección guardada no es válida).", archivo.name,
                )
                continue
            sid = sec.get("seccion_id")
            if sid in ids_seccion:
                logger.warning(
                    "Recuperación: sección duplicada '%s'; "
                    "se ignora '%s'.", sid, archivo.name,
                )
                continue
            ids_seccion.add(sid)
            secciones.append(sec)

        ejercicios: List[Dict[str, Any]] = []
        ids_ejercicio: Set[str] = set()
        for archivo in sorted(carpeta.glob("lote_ejercicios_*.json")):
            if "_crudo" in archivo.name:
                continue
            lote = _leer_json(archivo)
            if not lote:
                continue
            lote = normalizar_claves(lote)
            if not validar_lote_ejercicios(lote)[0]:
                logger.warning(
                    "Recuperación: se ignora '%s' "
                    "(el lote guardado no es válido).", archivo.name,
                )
                continue
            for ejercicio in lote.get("ejercicios", []):
                if not isinstance(ejercicio, dict):
                    continue
                eid = ejercicio.get("id")
                if eid in ids_ejercicio:
                    logger.warning(
                        "Recuperación: ejercicio duplicado '%s'; "
                        "se ignora el repetido.", eid,
                    )
                    continue
                ids_ejercicio.add(eid)
                ejercicios.append(ejercicio)

        componentes = _leer_json(carpeta / "componentes_finales.json")
        if componentes is not None:
            componentes = normalizar_claves(componentes)
            if not validar_componentes_finales(componentes)[0]:
                logger.warning(
                    "Recuperación: los componentes finales guardados no son "
                    "válidos; se ignoran."
                )
                componentes = None

        # Si no hay documento ensamblado pero hay bloques, intentar ensamblar.
        if plan and secciones and ejercicios and componentes:
            # No reconstruir un documento incompleto: deben estar todas las
            # secciones planificadas. Si falta alguna, se informa con claridad
            # en lugar de generar un PDF que omita contenido obligatorio.
            ids_plan = [
                seccion.get("id") for seccion in plan.get("secciones", [])
                if isinstance(seccion, dict) and seccion.get("id")
            ]
            faltantes = [sid for sid in ids_plan if sid not in ids_seccion]
            if faltantes:
                logger.error(
                    "Recuperación: faltan secciones válidas %s; "
                    "no se ensambla un documento incompleto.", faltantes,
                )
                return {
                    "exito": False,
                    "mensaje": (
                        "No hay suficientes bloques válidos para reanudar el "
                        f"trabajo: faltan las secciones {faltantes}. "
                        "Regenerá esas secciones antes de reintentar."
                    ),
                }

            self.trabajo_id = trabajo_guardado
            self.carpeta_trabajo = carpeta
            self.plan = plan
            self.secciones_validadas = secciones
            self.ejercicios_validos = ejercicios
            self.componentes_finales = componentes

            material = self._ensamblar_documento(len(ejercicios))
            if construir_pdf(material, rutas_visuales, ruta_pdf):
                return _exito(
                    material,
                    "PDF reconstruido desde bloques guardados.",
                )
            return {
                "exito": False,
                "mensaje": "No se pudo reconstruir el PDF desde los bloques.",
            }

        return {
            "exito": False,
            "mensaje": (
                "No hay suficientes bloques válidos para reanudar el trabajo."
            ),
        }
