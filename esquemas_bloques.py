"""
Esquemas de datos para la generación segmentada por bloques.

Define las estructuras JSON para cada tipo de bloque que se solicita
por separado a la IA:

- Plan de aprendizaje (etapa A)
- Sección teórica (etapa B)
- Lote de ejercicios (etapa C)
- Componentes finales: resumen, glosario (etapa D)

Cada esquema es un diccionario con los campos obligatorios y
opcionales, junto con su validación asociada.
"""
from typing import Any, Dict, List, Optional, Tuple
import unicodedata

# ---------------------------------------------------------------------------
# Normalización de claves
# ---------------------------------------------------------------------------
#
# Los modelos en español suelen escribir las claves JSON con tilde
# ("solución" en lugar de "solucion"), lo que hacía fallar la validación
# aunque el contenido fuera correcto. Antes de validar y de usar los datos,
# las claves se normalizan a la forma canónica (sin tildes y en minúsculas)
# siempre que coincidan con un nombre de campo conocido. No se inventan
# campos ni se descarta información.

CLAVES_CANONICAS = {
    # Plan (etapa A)
    "titulo", "disciplina", "nivel", "profundidad", "tema",
    "objetivos_aprendizaje", "conocimientos_previos", "secciones",
    "recursos_visuales_planificados", "conceptos_principales",
    "ejemplos_sugeridos",
    # Sección teórica (etapa B)
    "seccion_id", "orden", "bloques", "tipo", "contenido", "items",
    # Ejercicios (etapa C)
    "id", "dificultad", "consigna", "datos", "pista", "solucion",
    "respuesta_final", "explicacion", "criterios_correccion",
    # Componentes finales (etapa D) y documento ensamblado
    "resumen_final", "glosario", "termino", "definicion", "metadatos",
    "introduccion", "actividades", "solucionario", "ejemplos_resueltos",
    "actividad_id", "respuesta", "procedimiento", "criterios",
    # Recursos visuales
    "descripcion", "ubicacion", "fuentes",
}


def _sin_tildes(texto: str) -> str:
    """Devuelve el texto sin signos diacríticos."""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _forma_normalizada(clave: str) -> str:
    """Forma comparable de una clave: sin tildes, minúsculas y sin espacios."""
    return _sin_tildes(clave).strip().lower()


def normalizar_claves(datos: Any,
                      claves_canonicas: Any = None) -> Any:
    """
    Devuelve una copia de `datos` con las claves normalizadas.

    Solo se renombran las claves cuya forma sin tildes coincide con un nombre
    de campo conocido. Si en el mismo objeto aparecen la variante con tilde y
    la canónica, prevalece la canónica. El contenido nunca se modifica.
    """
    canonicas = list(claves_canonicas if claves_canonicas is not None
                     else CLAVES_CANONICAS)
    exactas = set(canonicas)
    mapa = {_forma_normalizada(c): c for c in canonicas}
    return _normalizar_recursivo(datos, exactas, mapa)


def _normalizar_recursivo(valor: Any, exactas: set, mapa: Dict[str, str]) -> Any:
    if isinstance(valor, dict):
        resultado: Dict[Any, Any] = {}
        for clave, contenido in valor.items():
            normalizado = _normalizar_recursivo(contenido, exactas, mapa)
            if isinstance(clave, str) and clave not in exactas:
                candidata = mapa.get(_forma_normalizada(clave))
                if candidata is not None and candidata != clave:
                    # No se sobrescribe una clave canónica ya presente.
                    resultado.setdefault(candidata, normalizado)
                    continue
            resultado[clave] = normalizado
        return resultado
    if isinstance(valor, list):
        return [_normalizar_recursivo(v, exactas, mapa) for v in valor]
    return valor


# ---------------------------------------------------------------------------
# Esquema: Plan de aprendizaje (etapa A)
# ---------------------------------------------------------------------------

CAMPO_OBLIGATORIOS_PLAN = [
    "titulo", "disciplina", "nivel", "profundidad",
    "objetivos_aprendizaje", "conocimientos_previos",
    "secciones", "recursos_visuales_planificados",
]

CAMPO_OBLIGATORIOS_SECCION_PLAN = [
    "id", "orden", "titulo", "conceptos_principales",
    "ejemplos_sugeridos", "recursos_visuales",
]

CAMPO_OBLIGATORIOS_RECURSO_PLAN = [
    "id", "tipo", "titulo", "descripcion", "ubicacion",
]


def validar_plan_aprendizaje(plan: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Valida la estructura de un plan de aprendizaje."""
    errores: List[str] = []

    if not isinstance(plan, dict):
        return False, ["El plan no es un objeto JSON válido."]

    for campo in CAMPO_OBLIGATORIOS_PLAN:
        if campo not in plan or plan[campo] in (None, ""):
            errores.append(f"Falta el campo obligatorio del plan: '{campo}'.")

    # Validar secciones
    secciones = plan.get("secciones", [])
    if not isinstance(secciones, list) or len(secciones) == 0:
        errores.append("El plan debe incluir al menos una sección.")
    else:
        ids_seccion = set()
        for i, sec in enumerate(secciones):
            if not isinstance(sec, dict):
                errores.append(f"La sección {i} del plan no es un objeto.")
                continue
            for campo in CAMPO_OBLIGATORIOS_SECCION_PLAN:
                if campo not in sec or sec[campo] in (None, ""):
                    errores.append(
                        f"Sección {i}: falta el campo obligatorio '{campo}'."
                    )
            sec_id = sec.get("id")
            if sec_id:
                if sec_id in ids_seccion:
                    errores.append(f"ID de sección duplicado en el plan: {sec_id}.")
                ids_seccion.add(sec_id)

    return (len(errores) == 0), errores


# ---------------------------------------------------------------------------
# Esquema: Sección teórica (etapa B)
# ---------------------------------------------------------------------------

CAMPO_OBLIGATORIOS_SECCION_TEORICA = [
    "seccion_id", "orden", "titulo", "bloques",
]

TIPO_BLOQUE_VALIDO = {
    "heading", "paragraph", "bullet_list", "numbered_list",
    "equation", "definition", "callout", "visual_reference",
}

# Campos que indican que un bloque aporta contenido real (texto o lista).
_CAMPOS_CONTENIDO_BLOQUE = (
    "texto", "contenido", "items", "termino", "definicion",
    "expresion_texto", "expresion_matematica", "descripcion",
)


def _bloque_tiene_contenido(bloque: Dict[str, Any]) -> bool:
    """Indica si un bloque aporta algún contenido, no sólo estructura."""
    for campo in _CAMPOS_CONTENIDO_BLOQUE:
        valor = bloque.get(campo)
        if isinstance(valor, str) and valor.strip():
            return True
        if isinstance(valor, list) and len(valor) > 0:
            return True
    return False


def validar_seccion_teorica(seccion: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Valida la estructura de una sección teórica generada por bloque."""
    errores: List[str] = []

    if not isinstance(seccion, dict):
        return False, ["La sección teórica no es un objeto JSON válido."]

    for campo in CAMPO_OBLIGATORIOS_SECCION_TEORICA:
        if campo not in seccion:
            errores.append(f"Falta el campo obligatorio de sección: '{campo}'.")

    bloques = seccion.get("bloques", [])
    if not isinstance(bloques, list) or len(bloques) == 0:
        errores.append("La sección debe incluir al menos un bloque de contenido.")
    else:
        con_contenido = False
        for i, bloque in enumerate(bloques):
            if not isinstance(bloque, dict):
                errores.append(f"Bloque {i} no es un objeto.")
                continue
            tipo = bloque.get("tipo", "")
            if tipo not in TIPO_BLOQUE_VALIDO:
                errores.append(
                    f"Bloque {i}: tipo '{tipo}' no es un tipo válido."
                )
                continue
            if tipo == "visual_reference":
                if not bloque.get("recurso_id"):
                    errores.append(
                        f"Bloque {i}: visual_reference sin 'recurso_id'."
                    )
            elif _bloque_tiene_contenido(bloque):
                con_contenido = True

        if not con_contenido:
            errores.append(
                "La sección no tiene contenido textual válido (todos los "
                "bloques están vacíos)."
            )

    return (len(errores) == 0), errores


# ---------------------------------------------------------------------------
# Esquema: Lote de ejercicios (etapa C)
# ---------------------------------------------------------------------------

CAMPO_OBLIGATORIOS_EJERCICIO = [
    "id", "dificultad", "tipo", "consigna", "solucion", "respuesta_final",
]

DIFICULDADES_VALIDAS = {"inicial", "intermedio", "avanzado"}
TIPOS_EJERCICIO_VALIDOS = {
    "calculo", "analisis_conceptual", "asociacion_conceptos",
    "interpretacion_graficos", "identificacion_errores",
    "seleccion_justificada", "desarrollo_escrito", "estudio_de_casos",
    "aplicacion_practica",
}


def validar_lote_ejercicios(lote: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Valida la estructura de un lote de ejercicios."""
    errores: List[str] = []

    if not isinstance(lote, dict):
        return False, ["El lote de ejercicios no es un objeto JSON válido."]

    ejercicios = lote.get("ejercicios", [])
    if not isinstance(ejercicios, list) or len(ejercicios) == 0:
        errores.append("El lote debe incluir al menos un ejercicio.")
    else:
        ids_ej = set()
        for i, ej in enumerate(ejercicios):
            if not isinstance(ej, dict):
                errores.append(f"Ejercicio {i} no es un objeto.")
                continue
            for campo in CAMPO_OBLIGATORIOS_EJERCICIO:
                if campo not in ej or ej[campo] in (None, ""):
                    errores.append(
                        f"Ejercicio {i}: falta el campo obligatorio '{campo}'."
                    )
            dif = ej.get("dificultad", "")
            if dif and dif not in DIFICULDADES_VALIDAS:
                errores.append(
                    f"Ejercicio {i}: dificultad '{dif}' no es válida."
                )
            tipo = ej.get("tipo", "")
            if tipo and tipo not in TIPOS_EJERCICIO_VALIDOS:
                errores.append(
                    f"Ejercicio {i}: tipo '{tipo}' no es válido."
                )
            ej_id = ej.get("id")
            if ej_id:
                if ej_id in ids_ej:
                    errores.append(f"ID de ejercicio duplicado: {ej_id}.")
                ids_ej.add(ej_id)

    return (len(errores) == 0), errores


# ---------------------------------------------------------------------------
# Esquema: Componentes finales (etapa D)
# ---------------------------------------------------------------------------

CAMPO_OBLIGATORIOS_FINALES = [
    "resumen_final", "glosario", "metadatos",
]


def validar_componentes_finales(componentes: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Valida los componentes finales del documento."""
    errores: List[str] = []

    if not isinstance(componentes, dict):
        return False, ["Los componentes finales no son un objeto JSON válido."]

    for campo in CAMPO_OBLIGATORIOS_FINALES:
        if campo not in componentes:
            errores.append(f"Falta el campo obligatorio: '{campo}'.")

    metadatos = componentes.get("metadatos", {})
    if not isinstance(metadatos, dict):
        errores.append("El campo 'metadatos' debe ser un objeto.")
    else:
        for sub in ["titulo", "tema", "disciplina", "nivel"]:
            if not metadatos.get(sub):
                errores.append(f"Falta metadatos.{sub}.")

    return (len(errores) == 0), errores


# ---------------------------------------------------------------------------
# Esquema: Documento ensamblado (resultado final antes del PDF)
# ---------------------------------------------------------------------------

CAMPO_OBLIGATORIOS_DOCUMENTO = [
    "metadatos", "objetivos_aprendizaje", "conocimientos_previos",
    "introduccion", "secciones", "ejemplos_resueltos",
    "actividades", "solucionario", "glosario",
    "resumen_final", "recursos_visuales",
]


def validar_documento_ensamblado(documento: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Valida que el documento ensamblado tenga todos los campos obligatorios."""
    errores: List[str] = []

    if not isinstance(documento, dict):
        return False, ["El documento ensamblado no es un objeto JSON válido."]

    for campo in CAMPO_OBLIGATORIOS_DOCUMENTO:
        if campo not in documento:
            errores.append(f"Falta el campo obligatorio del documento: '{campo}'.")

    return (len(errores) == 0), errores


# ---------------------------------------------------------------------------
# Esquemas JSON para salida estructurada de OpenRouter
# ---------------------------------------------------------------------------
#
# Estos esquemas describen los mismos requisitos que las funciones de
# validación de arriba. Se envían a OpenRouter con response_format
# {"type": "json_schema"}. La validación local se mantiene siempre: un JSON
# sintácticamente correcto no alcanza si faltan campos obligatorios.

TIPOS_RECURSO_VISUAL = [
    "python_chart", "diagram", "timeline", "flowchart",
    "table", "ascii", "external_image",
]
POSICIONES_RECURSO = [
    "portada", "antes_bloque", "despues_bloque", "integrado",
    "final_seccion",
]


def _esquema_objeto(propiedades: Dict[str, Any],
                    requeridos: Optional[List[str]] = None) -> Dict[str, Any]:
    """Construye un objeto JSON Schema cerrado y con campos requeridos."""
    return {
        "type": "object",
        "properties": propiedades,
        "required": list(requeridos if requeridos is not None
                         else propiedades.keys()),
        "additionalProperties": False,
    }


def _cadena() -> Dict[str, Any]:
    return {"type": "string"}


def _lista_cadenas() -> Dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _esquema_ubicacion_recurso() -> Dict[str, Any]:
    return _esquema_objeto({
        "seccion_id": {"type": "string"},
        "posicion": {"type": "string", "enum": POSICIONES_RECURSO},
        "bloque_referencia": _cadena(),
        "orden_relativo": {"type": "integer"},
    })


def _esquema_recurso_seccion() -> Dict[str, Any]:
    """Recurso visual tal como aparece dentro de una sección del plan."""
    return _esquema_objeto({
        "id": {"type": "string"},
        "tipo": {"type": "string", "enum": TIPOS_RECURSO_VISUAL},
        "titulo": {"type": "string"},
        "descripcion": {"type": "string"},
        "ubicacion": _esquema_ubicacion_recurso(),
    })


def _esquema_recurso_planificado() -> Dict[str, Any]:
    """Recurso visual del catálogo canónico del plan (claves en inglés)."""
    return _esquema_objeto({
        "id": {"type": "string"},
        "type": {"type": "string", "enum": TIPOS_RECURSO_VISUAL},
        "title": {"type": "string"},
        "educational_purpose": {"type": "string"},
        "description": {"type": "string"},
        "image_generation_prompt": {"type": "string"},
        "alt_text": {"type": "string"},
        "caption": {"type": "string"},
        "ubicacion": _esquema_ubicacion_recurso(),
        "render_strategy": {"type": "string"},
        # `data` es abierto a propósito: los gráficos locales usan series,
        # eventos, nodos, filas, etc. No se puede cerrar sin perder recursos.
        "data": {"type": "object"},
        "status": {"type": "string"},
        "generated_asset_path": _cadena(),
    })


def esquema_json_plan_aprendizaje() -> Dict[str, Any]:
    """JSON Schema de la etapa A (planificación)."""
    return _esquema_objeto({
        "titulo": {"type": "string"},
        "disciplina": {"type": "string"},
        "nivel": {"type": "string"},
        "profundidad": {"type": "string"},
        "objetivos_aprendizaje": _lista_cadenas(),
        "conocimientos_previos": _lista_cadenas(),
        "secciones": {
            "type": "array",
            "items": _esquema_objeto({
                "id": {"type": "string"},
                "orden": {"type": "integer"},
                "titulo": {"type": "string"},
                "conceptos_principales": _lista_cadenas(),
                "ejemplos_sugeridos": _lista_cadenas(),
                "recursos_visuales": {
                    "type": "array",
                    "items": _esquema_recurso_seccion(),
                },
            }),
        },
        "recursos_visuales_planificados": {
            "type": "array",
            "items": _esquema_recurso_planificado(),
        },
        "distribucion_actividades": _esquema_objeto({
            "inicial": {"type": "integer"},
            "intermedio": {"type": "integer"},
            "avanzado": {"type": "integer"},
        }),
    })


def _esquema_bloque_teorico() -> Dict[str, Any]:
    """
    Bloque teórico con todos los campos posibles.

    Se usa un objeto plano (en lugar de oneOf) para que los proveedores con
    modo estricto no tengan que interpretar uniones discriminadas. El campo
    `tipo` limita los valores y la validación local exige contenido real para
    cada bloque. Los campos que no corresponden al tipo van como cadena vacía
    o lista vacía, nunca null, para evitar uniones que algunos proveedores
    rechazan.
    """
    return _esquema_objeto({
        "tipo": {"type": "string", "enum": sorted(TIPO_BLOQUE_VALIDO)},
        "texto": _cadena(),
        "contenido": _cadena(),
        "items": {"type": "array", "items": {"type": "string"}},
        "termino": _cadena(),
        "definicion": _cadena(),
        "expresion_texto": _cadena(),
        "expresion_matematica": _cadena(),
        "descripcion": _cadena(),
        "recurso_id": _cadena(),
        "posicion": _cadena(),
    })


def esquema_json_seccion_teorica() -> Dict[str, Any]:
    """JSON Schema de la etapa B (una sección teórica)."""
    return _esquema_objeto({
        "seccion_id": {"type": "string"},
        "orden": {"type": "integer"},
        "titulo": {"type": "string"},
        "bloques": {
            "type": "array",
            "items": _esquema_bloque_teorico(),
        },
    })


def esquema_json_lote_ejercicios() -> Dict[str, Any]:
    """JSON Schema de la etapa C (lote de ejercicios)."""
    return _esquema_objeto({
        "ejercicios": {
            "type": "array",
            "items": _esquema_objeto({
                "id": {"type": "string"},
                "dificultad": {
                    "type": "string", "enum": sorted(DIFICULDADES_VALIDAS),
                },
                "tipo": {
                    "type": "string", "enum": sorted(TIPOS_EJERCICIO_VALIDOS),
                },
                "consigna": {"type": "string"},
                "datos": _cadena(),
                "pista": _cadena(),
                "solucion": {"type": "string"},
                "respuesta_final": {"type": "string"},
                "explicacion": {"type": "string"},
                "criterios_correccion": {"type": "string"},
            }),
        },
    })


def esquema_json_componentes_finales() -> Dict[str, Any]:
    """JSON Schema de la etapa D (resumen, glosario y metadatos)."""
    return _esquema_objeto({
        "metadatos": _esquema_objeto({
            "titulo": {"type": "string"},
            "subtitulo": {"type": "string"},
            "tema": {"type": "string"},
            "disciplina": {"type": "string"},
            "nivel": {"type": "string"},
            "profundidad": {"type": "string"},
            "cantidad_actividades": {"type": "integer"},
            "fecha_generacion": {"type": "string"},
            "generado_por_ia": {"type": "boolean"},
            "modo_demostracion": {"type": "boolean"},
        }),
        "introduccion": {"type": "string"},
        "resumen_final": {"type": "string"},
        "glosario": {
            "type": "array",
            "items": _esquema_objeto({
                "termino": {"type": "string"},
                "definicion": {"type": "string"},
            }),
        },
        "fuentes": _lista_cadenas(),
    })


def obtener_esquema_openrouter(etapa: str) -> Tuple[str, Dict[str, Any], bool]:
    """
    Devuelve (nombre, esquema, estricto) para la etapa indicada.

    El plan no usa strict porque `data` es un objeto abierto para los gráficos
    locales y el plan admite dos formas de recursos visuales. Las demás etapas
    usan un esquema cerrado compatible con strict.
    """
    clave = (etapa or "").strip().lower()
    if clave in ("plan", "planificacion", "planificación"):
        return "plan_aprendizaje", esquema_json_plan_aprendizaje(), False
    if clave in ("seccion", "seccion_teorica", "sección teórica"):
        return "seccion_teorica", esquema_json_seccion_teorica(), True
    if clave in ("ejercicios", "lote_ejercicios"):
        return "lote_ejercicios", esquema_json_lote_ejercicios(), True
    if clave in ("componentes", "componentes_finales"):
        return "componentes_finales", esquema_json_componentes_finales(), True
    raise ValueError(f"Etapa desconocida para el esquema JSON: {etapa}")
