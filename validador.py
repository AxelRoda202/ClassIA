"""
Validador de respuestas JSON de la IA.

Comprueba que la respuesta tenga la estructura esperada y los campos
obligatorios antes de usarla para generar el PDF.
"""
from typing import Any, Dict, List, Tuple

# Campos obligatorios en el nivel raíz del JSON
CAMPOS_OBLIGATORIOS_RAIZ = [
    "metadatos",
    "objetivos_aprendizaje",
    "conocimientos_previos",
    "introduccion",
    "secciones",
    "actividades",
    "solucionario",
    "recursos_visuales",
]

# Campos obligatorios dentro de metadatos
CAMPOS_OBLIGATORIOS_METADATOS = [
    "titulo",
    "tema",
    "disciplina",
    "nivel",
]

# Tipos esperados para campos clave
TIPOS_ESPERADOS = {
    "objetivos_aprendizaje": list,
    "conocimientos_previos": list,
    "secciones": list,
    "actividades": list,
    "solucionario": list,
    "recursos_visuales": list,
    "glosario": list,
    "fuentes": list,
}


class ErrorValidacion(Exception):
    """Excepción lanzada cuando la respuesta no pasa la validación."""
    pass


def validar_estructura_material(material: Dict[str, Any], cantidad_actividades_esperada: int) -> Tuple[bool, List[str]]:
    """
    Valida la estructura completa del material educativo.

    Devuelve (True, []) si todo está correcto, o (False, lista_de_errores)
    si hay problemas.
    """
    errores: List[str] = []

    if not isinstance(material, dict):
        errores.append("La respuesta no es un objeto JSON válido.")
        return False, errores

    # 1. Campos obligatorios en la raíz
    for campo in CAMPOS_OBLIGATORIOS_RAIZ:
        if campo not in material:
            errores.append(f"Falta el campo obligatorio '{campo}' en la raíz.")

    # 2. Tipos esperados
    for campo, tipo_esperado in TIPOS_ESPERADOS.items():
        if campo in material and not isinstance(material[campo], tipo_esperado):
            errores.append(f"El campo '{campo}' debe ser una lista.")

    # 3. Metadatos
    metadatos = material.get("metadatos", {})
    if not isinstance(metadatos, dict):
        errores.append("El campo 'metadatos' debe ser un objeto.")
    else:
        for campo in CAMPOS_OBLIGATORIOS_METADATOS:
            if not metadatos.get(campo):
                errores.append(f"Falta el campo obligatorio 'metadatos.{campo}'.")

    # 4. Cantidad de actividades compatible
    actividades = material.get("actividades", [])
    if cantidad_actividades_esperada > 0:
        if len(actividades) < cantidad_actividades_esperada * 0.75:
            errores.append(
                f"Se esperaban aproximadamente {cantidad_actividades_esperada} actividades, "
                f"pero se recibieron {len(actividades)}."
            )

    # 5. Validar cada actividad
    ids_actividades = set()
    for i, actividad in enumerate(actividades):
        if not isinstance(actividad, dict):
            errores.append(f"La actividad {i} no es un objeto.")
            continue

        if not actividad.get("consigna"):
            errores.append(f"La actividad {i + 1} no tiene consigna.")
        if not actividad.get("solucion") and not actividad.get("respuesta_final"):
            errores.append(
                f"La actividad {i + 1} no tiene solución ni respuesta de referencia."
            )
        if not actividad.get("dificultad"):
            errores.append(f"La actividad {i + 1} no tiene nivel de dificultad.")
        if not actividad.get("tipo"):
            errores.append(f"La actividad {i + 1} no tiene tipo de actividad.")

        id_act = actividad.get("id")
        if id_act:
            if id_act in ids_actividades:
                errores.append(f"ID de actividad duplicado: {id_act}.")
            ids_actividades.add(id_act)

    # 6. Validar secciones no vacías injustificadas
    secciones = material.get("secciones", [])
    for i, seccion in enumerate(secciones):
        if not isinstance(seccion, dict):
            errores.append(f"La sección {i} no es un objeto.")
            continue
        if not seccion.get("titulo"):
            errores.append(f"La sección {i + 1} no tiene título.")
        bloques = seccion.get("bloques", [])
        if not isinstance(bloques, list) or len(bloques) == 0:
            errores.append(f"La sección '{seccion.get('titulo', i + 1)}' no tiene bloques de contenido.")

    # 7. Validar referencias de recursos visuales
    recursos = material.get("recursos_visuales", [])
    ids_recursos = set()
    for recurso in recursos:
        if isinstance(recurso, dict) and recurso.get("id"):
            ids_recursos.add(recurso["id"])

    for seccion in secciones:
        if not isinstance(seccion, dict):
            continue
        for bloque in seccion.get("bloques", []):
            if not isinstance(bloque, dict):
                continue
            if bloque.get("tipo") == "visual_reference":
                ref_id = bloque.get("recurso_id")
                if ref_id and ref_id not in ids_recursos:
                    errores.append(
                        f"Referencia a recurso visual inexistente: '{ref_id}'."
                    )

    # 8. Que haya información suficiente para el PDF
    if not metadatos.get("titulo"):
        errores.append("No hay título para construir la portada del PDF.")
    if not material.get("introduccion"):
        errores.append("Falta la introducción del material.")

    return (len(errores) == 0), errores


def validar_json_texto(texto: str) -> Tuple[bool, Any, List[str]]:
    """
    Intenta parsear un texto como JSON y devuelve (éxito, objeto_o_None, errores).
    """
    import json
    errores: List[str] = []
    try:
        objeto = json.loads(texto)
        return True, objeto, []
    except json.JSONDecodeError as e:
        errores.append(f"El texto no es JSON válido: {str(e)}")
        return False, None, errores
