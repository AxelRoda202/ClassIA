"""
Plantillas de instrucciones para la IA.

Contiene la plantilla general y pequeñas adaptaciones por disciplina.
La IA recibe una sola solicitud principal que incluye la clasificación
y la generación pedagógica juntas.
"""
from typing import Any, Dict, List, Optional


def plantilla_general(
    tema: str,
    nivel: str,
    disciplina: str,
    profundidad: str,
    cantidad_actividades: int,
    recursos_visuales: bool,
) -> str:
    """
    Construye la instrucción completa que se envía a la IA.
    La respuesta debe ser un único objeto JSON válido.
    """
    distribucion = _distribucion_actividades(cantidad_actividades)

    instruccion = f"""
Eres un docente experto que adapta sus explicaciones a estudiantes de {nivel}.
Vas a generar material educativo sobre el tema: "{tema}".

CONFIGURACIÓN:
- Nivel educativo: {nivel}
- Disciplina: {disciplina} (si es "Detectar automáticamente", infiere la disciplina más adecuada)
- Profundidad: {profundidad}
- Cantidad de actividades: {cantidad_actividades}
- Distribución sugerida: {distribucion}
- Incluir recursos visuales: {"sí" if recursos_visuales else "no"}

INSTRUCCIONES GENERALES:
1. Debes responder ÚNICAMENTE con un objeto JSON válido. No agregues texto antes ni después del JSON.
2. No uses Markdown libre. Usa la estructura de campos definidos a continuación.
3. Adapta el lenguaje al nivel educativo indicado.
4. No inventes fuentes, autores, citas ni enlaces. El campo "fuentes" debe quedarse vacío si no se verificaron fuentes externas.
5. Incluye una advertencia discreta de que el material fue generado por IA y se recomienda contrastar con un docente.

ESTRUCTURA OBLIGATORIA DEL JSON:
{{
  "metadatos": {{
    "titulo": "Título del material",
    "subtitulo": "Subtítulo breve",
    "tema": "{tema}",
    "disciplina": "nombre de la disciplina",
    "nivel": "{nivel}",
    "profundidad": "{profundidad}",
    "cantidad_actividades": {cantidad_actividades},
    "generado_por_ia": true,
    "modo_demostracion": false
  }},
  "objetivos_aprendizaje": ["objetivo 1", "objetivo 2", ...],
  "conocimientos_previos": ["conocimiento 1", "conocimiento 2", ...],
  "introduccion": "texto de introducción",
  "secciones": [
    {{
      "id": "seccion1",
      "orden": 1,
      "titulo": "Título de la sección",
      "bloques": [
        {{"tipo": "heading", "texto": "Título de bloque"}},
        {{"tipo": "paragraph", "texto": "Texto explicativo"}},
        {{"tipo": "bullet_list", "items": ["ítem 1", "ítem 2"]}},
        {{"tipo": "numbered_list", "items": ["paso 1", "paso 2"]}},
        {{"tipo": "equation", "expresion_texto": "f(x) = ax² + bx + c", "expresion_matematica": "\\frac{{-b}}{{2a}}", "descripcion": "fórmula"}},
        {{"tipo": "definition", "termino": "término", "definicion": "definición"}},
        {{"tipo": "callout", "texto": "texto resaltado"}},
        {{"tipo": "visual_reference", "recurso_id": "id_del_recurso", "posicion": "despues_bloque"}}
      ]
    }}
  ],
  "ejemplos_resueltos": [
    {{
      "id": "ejemplo1",
      "titulo": "título del ejemplo",
      "pasos": ["paso 1", "paso 2"],
      "resultado": "resultado final"
    }}
  ],
  "actividades": [
    {{
      "id": "act1",
      "dificultad": "inicial",
      "tipo": "calculo",
      "consigna": "pregunta clara",
      "datos": "datos necesarios o null",
      "pista": "pista opcional o null",
      "solucion": "solución desarrollada",
      "respuesta_final": "respuesta breve",
      "explicacion": "por qué es correcta",
      "criterios_correccion": "cómo se evalúa"
    }}
  ],
  "solucionario": [
    {{
      "actividad_id": "act1",
      "respuesta": "respuesta",
      "procedimiento": "pasos de resolución",
      "explicacion": "explicación",
      "criterios": "criterios de evaluación"
    }}
  ],
  "glosario": [
    {{"termino": "término", "definicion": "definición"}}
  ],
  "resumen_final": "resumen de ideas clave",
  "fuentes": [],
  "recursos_visuales": [
    {{
      "id": "recurso1",
      "type": "python_chart",
      "title": "título del recurso",
      "educational_purpose": "qué concepto ayuda a entender",
      "description": "descripción concreta de lo que se representa",
      "image_generation_prompt": "instrucción para futura API de imágenes (sin claves)",
      "alt_text": "descripción accesible",
      "caption": "pie de imagen",
      "placement": {{
        "seccion_id": "id_de_seccion",
        "posicion": "despues_bloque",
        "bloque_referencia": null,
        "orden_relativo": 1
      }},
      "render_strategy": "python_chart",
      "data": {{}},
      "status": "pendiente",
      "generated_asset_path": null
    }}
  ]
}}

TIPOS DE RECURSO VISUAL PERMITIDOS: python_chart, diagram, timeline, flowchart, table, ascii, external_image.
POSICIONES PERMITIDAS: portada, antes_bloque, despues_bloque, integrado, final_seccion.

REGLA SOBRE TEXTO EN IMÁGENES:
- No uses external_image para mapas conceptuales, diagramas, líneas de tiempo, tablas ni ningún recurso que necesite etiquetas, nombres, coordenadas o leyendas.
- Para esos casos usá diagram, timeline, flowchart o table: se renderizan localmente y el texto queda legible.
- Reservá external_image sólo para ilustraciones, fotografías o escenas sin texto.
- Si un recurso externo necesita una leyenda, escribila en "caption" o "alt_text", no dentro de la imagen.

ESCALONAMIENTO DE ACTIVIDADES:
- Inicial: ejercicios básicos de comprensión y cálculo simple.
- Intermedio: aplicación de conceptos, interpretación, análisis.
- Avanzado: resolución de problemas, estudio de casos, desarrollo escrito.

TIPOS DE ACTIVIDAD PERMITIDOS: calculo, analisis_conceptual, asociacion_conceptos, interpretacion_graficos, identificacion_errores, seleccion_justificada, desarrollo_escrito, estudio_de_casos, aplicacion_practica.

{_adaptacion_disciplina(disciplina)}

IMPORTANTE: Responde solo con el JSON. No uses bloques de código ```json. No agregues explicaciones fuera del JSON.
"""
    return instruccion


def _distribucion_actividades(cantidad: int) -> str:
    """Devuelve la distribución sugerida de actividades por nivel."""
    if cantidad <= 8:
        inicial = max(2, round(cantidad * 0.3))
        intermedio = max(2, round(cantidad * 0.4))
        avanzado = cantidad - inicial - intermedio
    elif cantidad <= 10:
        inicial, intermedio, avanzado = 3, 4, 3
    else:
        inicial, intermedio, avanzado = 4, 5, 3
    return f"{inicial} iniciales, {intermedio} intermedias, {avanzado} avanzadas"


def _adaptacion_disciplina(disciplina: str) -> str:
    """Devuelve el texto de adaptación pedagógica según la disciplina."""
    d = disciplina.lower().strip()

    adaptaciones = {
        "matematica": """
ADAPTACIÓN - MATEMÁTICA:
- Usa ejemplos resueltos paso a paso con justificación de cada operación.
- Incluye ecuaciones con su representación matemática.
- Actividades: cálculo, interpretación de gráficos, resolución de problemas.
- No uses preguntas de memoria puro; prioriza el razonamiento matemático.
- Incluye al menos un recurso visual de tipo python_chart con una función o gráfica.
""",
        "fisica y quimica": """
ADAPTACIÓN - FÍSICA Y QUÍMICA:
- Explica leyes y fórmulas con ejemplos de la vida cotidiana.
- Incluye ecuaciones con variables y unidades.
- Actividades: cálculo, análisis conceptual, aplicación práctica.
- Incluye recursos visuales de diagramas o gráficos de datos experimentales.
""",
        "historia y geografia": """
ADAPTACIÓN - HISTORIA Y GEOGRAFÍA:
- No uses cálculos numéricos como actividad principal.
- Prioriza análisis de causas y consecuencias, interpretación de mapas y cronologías.
- Actividades: análisis conceptual, estudio de casos, desarrollo escrito, asociación de conceptos.
- Incluye recursos visuales de tipo timeline o flowchart.
""",
        "lengua y literatura": """
ADAPTACIÓN - LENGUA Y LITERATURA:
- Enfoca en análisis de textos, figuras retóricas y comprensión lectora.
- Actividades: desarrollo escrito, análisis conceptual, identificación de errores.
- No uses cálculos numéricos.
""",
        "programacion e informatica": """
ADAPTACIÓN - PROGRAMACIÓN E INFORMÁTICA:
- Incluye ejemplos de código como bloques de texto (sin ejecutar).
- Actividades: análisis de código, identificación de errores, desarrollo escrito, aplicación práctica.
- Incluye diagramas de flujo (flowchart) para algoritmos.
""",
        "recursos humanos, administracion y economia": """
ADAPTACIÓN - RECURSOS HUMANOS, ADMINISTRACIÓN Y ECONOMÍA:
- Usa casos reales de organizaciones y toma de decisiones.
- Actividades: estudio de casos, aplicación práctica, análisis conceptual, selección justificada.
- Incluye diagramas de procesos (flowchart) y tablas.
""",
        "biologia y ciencias naturales": """
ADAPTACIÓN - BIOLOGÍA Y CIENCIAS NATURALES:
- Explica procesos naturales y clasificación de seres vivos.
- Actividades: análisis conceptual, asociación de conceptos, interpretación de diagramas.
- Incluye diagramas de procesos biológicos o diagramas de clasificación.
""",
    }

    for clave, texto in adaptaciones.items():
        if clave in d:
            return texto

    return """
ADAPTACIÓN - DISCIPLINA GENERAL:
- Explica los conceptos fundamentales del tema de forma clara y progresiva.
- Incluye ejemplos resueltos y actividades variadas.
- Adapta el tipo de actividad a la naturaleza del tema.
"""


def obtener_instruccion_para_tema(
    tema: str,
    nivel: str,
    disciplina: str,
    profundidad: str,
    cantidad_actividades: int,
    recursos_visuales: bool,
) -> str:
    """Punto de entrada para obtener la instrucción completa de la IA."""
    return plantilla_general(
        tema=tema,
        nivel=nivel,
        disciplina=disciplina,
        profundidad=profundidad,
        cantidad_actividades=cantidad_actividades,
        recursos_visuales=recursos_visuales,
    )


# ---------------------------------------------------------------------------
# Plantillas para generación segmentada por bloques
# ---------------------------------------------------------------------------

def obtener_instruccion_planificacion(
    tema: str,
    nivel: str,
    disciplina: str,
    profundidad: str,
    cantidad_actividades: int,
    recursos_visuales: bool,
) -> str:
    """
    Construye la instrucción para la etapa de planificación general.
    Esta solicitud es pequeña y solo crea el esqueleto del material.
    """
    distribucion = _distribucion_actividades(cantidad_actividades)

    instruccion = f"""
Eres un docente experto que planifica material educativo para estudiantes de {nivel}.
Vas a crear un PLAN DE APRENDIZAJE sobre el tema: "{tema}".

CONFIGURACIÓN:
- Nivel educativo: {nivel}
- Disciplina: {disciplina}
- Profundidad: {profundidad}
- Cantidad de actividades: {cantidad_actividades}
- Distribución sugerida: {distribucion}
- Incluir recursos visuales: {"sí" if recursos_visuales else "no"}

INSTRUCCIONES:
1. Debes responder ÚNICAMENTE con un objeto JSON válido. No agregues texto antes ni después.
2. NO incluyas explicaciones completas, solo el esqueleto y los conceptos principales.
3. El plan debe ser breve y estructurado. No desarrolle contenido completo aquí.
4. Usa EXACTAMENTE los nombres de campo del ejemplo: minúsculas y SIN TILDES.
5. Los campos opcionales sin contenido deben ser cadena vacía ("") o lista vacía ([]), nunca null.

ESTRUCTURA OBLIGATORIA DEL JSON:
{{
  "titulo": "Título del material educativo",
  "disciplina": "nombre de la disciplina",
  "nivel": "{nivel}",
  "profundidad": "{profundidad}",
  "objetivos_aprendizaje": ["objetivo 1", "objetivo 2", "objetivo 3"],
  "conocimientos_previos": ["conocimiento 1", "conocimiento 2"],
  "secciones": [
    {{
      "id": "seccion1",
      "orden": 1,
      "titulo": "Título de la sección",
      "conceptos_principales": ["concepto A", "concepto B"],
      "ejemplos_sugeridos": ["ejemplo 1", "ejemplo 2"],
      "recursos_visuales": [
        {{
          "id": "recurso1",
          "tipo": "python_chart",
          "titulo": "Título del recurso",
          "descripcion": "Qué se debe representar",
          "ubicacion": {{
            "seccion_id": "seccion1",
            "posicion": "despues_bloque",
            "bloque_referencia": "",
            "orden_relativo": 1
          }}
        }}
      ]
    }}
  ],
  "recursos_visuales_planificados": [
    {{
      "id": "recurso1",
      "type": "python_chart",
      "title": "Título del recurso",
      "educational_purpose": "Qué concepto ayuda a entender",
      "description": "Descripción concreta",
      "image_generation_prompt": "Instrucción para futura API de imágenes",
      "alt_text": "Descripción accesible",
      "caption": "Pie de imagen",
      "ubicacion": {{
        "seccion_id": "seccion1",
        "posicion": "despues_bloque",
        "bloque_referencia": null,
        "orden_relativo": 1
      }},
      "render_strategy": "python_chart",
      "data": {{
        "tipo_grafico": "lineas",
        "x_label": "Eje X",
        "y_label": "Eje Y",
        "x": [0, 1, 2],
        "series": [
          {{"name": "Serie 1", "y": [0, 1, 2]}}
        ]
      }},
      "status": "pendiente",
      "generated_asset_path": ""
    }}
  ],
  "distribucion_actividades": {{
    "inicial": 3,
    "intermedio": 4,
    "avanzado": 3
  }}
}}

TIPOS DE RECURSO VISUAL PERMITIDOS: python_chart, diagram, timeline, flowchart, table, ascii, external_image.
POSICIONES PERMITIDAS: portada, antes_bloque, despues_bloque, integrado, final_seccion.

DATOS DE LOS RECURSOS LOCALES (no dejes "data" vacío):
- python_chart: "tipo_grafico" (lineas, barras o dispersion), "x_label", "y_label", "x" (lista de valores) y "series" (lista de objetos con "name" e "y").
- timeline: "eventos" (lista de objetos con "anio" y "evento").
- flowchart o diagram: "nodos" (lista de objetos con "id" y "texto") y "relaciones" (lista de objetos con "origen" y "destino").
- table: "cabeceras" (lista de textos) y "filas" (lista de listas de textos).
- ascii: "contenido" (texto).
- external_image no necesita "data"; usá "image_generation_prompt".

REGLA SOBRE TEXTO EN IMÁGENES:
- No uses external_image para mapas conceptuales, diagramas, líneas de tiempo, tablas ni ningún recurso que necesite etiquetas, nombres, coordenadas o leyendas.
- Para esos casos usá diagram, timeline, flowchart o table: se renderizan localmente y el texto queda legible.
- Reservá external_image sólo para ilustraciones, fotografías o escenas sin texto.
- Si un recurso externo necesita una leyenda, escribila en "caption" o "alt_text", no dentro de la imagen.

IMPORTANTE: Responde solo con el JSON. No uses bloques de código ```json.
"""
    return instruccion


def obtener_instruccion_seccion_teorica(
    seccion_plan: Dict[str, Any],
    tema: str,
    disciplina: str,
    nivel: str,
    profundidad: str,
) -> str:
    """
    Construye la instrucción para generar una sección teórica específica.

    Incluye los recursos visuales planificados para la sección con sus
    identificadores exactos: son la única fuente de verdad. El modelo debe
    referenciarlos tal cual y no inventar identificadores nuevos.
    """
    recursos = seccion_plan.get("recursos_visuales") or []
    lineas_recursos = []
    identificadores = []
    for recurso in recursos:
        if isinstance(recurso, dict):
            rid = recurso.get("id", "")
            tipo = recurso.get("tipo") or recurso.get("type") or ""
            titulo = recurso.get("titulo") or recurso.get("title") or ""
        else:
            rid, tipo, titulo = str(recurso), "", ""
        if rid:
            identificadores.append(str(rid))
            lineas_recursos.append(
                f'  - id: "{rid}" | tipo: {tipo} | título: {titulo}'
            )

    if lineas_recursos:
        lista_ids = ", ".join(f'"{i}"' for i in identificadores)
        bloque_recursos = (
            "RECURSOS VISUALES PLANIFICADOS PARA ESTA SECCIÓN:\n"
            + "\n".join(lineas_recursos)
            + '\nUsá EXACTAMENTE esos identificadores en el campo "recurso_id" '
            "de los bloques visual_reference. No inventes identificadores "
            "nuevos. Incluí cada recurso una sola vez, en la posición donde "
            f"resulte pertinente. Identificadores válidos: {lista_ids}."
        )
        ejemplo_recurso = identificadores[0]
    else:
        bloque_recursos = (
            "RECURSOS VISUALES PLANIFICADOS PARA ESTA SECCIÓN: ninguno.\n"
            'No incluyas bloques de tipo "visual_reference".'
        )
        ejemplo_recurso = "id_del_recurso"

    instruccion = f"""
Eres un docente experto. Vas a desarrollar UNA SECCIÓN TEÓRICA de material educativo.

TEMA: "{tema}"
DISCIPLINA: {disciplina}
NIVEL: {nivel}
PROFUNDIDAD: {profundidad}

SECCIÓN A DESARROLLAR:
- ID: {seccion_plan.get('id', '')}
- TÍTULO: {seccion_plan.get('titulo', '')}
- CONCEPTOS PRINCIPALES: {', '.join(seccion_plan.get('conceptos_principales', []))}
- EJEMPLOS SUGERIDOS: {', '.join(seccion_plan.get('ejemplos_sugeridos', []))}

{bloque_recursos}

INSTRUCCIONES:
1. Debes responder ÚNICAMENTE con un objeto JSON válido.
2. Desarrolla solo esta sección. No incluyas otras secciones.
3. Incluye definiciones, explicaciones, relaciones entre conceptos y ejemplos paso a paso.
4. Adapta el lenguaje al nivel educativo indicado ({nivel}).
5. No repitas la introducción general ni los objetivos del documento completo.
6. Usa EXACTAMENTE los nombres de campo del ejemplo: minúsculas y SIN TILDES.
7. No devuelvas bloques vacíos: cada bloque debe tener contenido real.
8. Incluí TODOS los campos del esquema en cada bloque. Los que no correspondan a su tipo van como cadena vacía ("") o lista vacía ([]), nunca null.

ESTRUCTURA OBLIGATORIA DEL JSON:
{{
  "seccion_id": "{seccion_plan.get('id', '')}",
  "orden": {seccion_plan.get('orden', 1)},
  "titulo": "{seccion_plan.get('titulo', '')}",
  "bloques": [
    {{
      "tipo": "heading",
      "texto": "Título del bloque"
    }},
    {{
      "tipo": "paragraph",
      "texto": "Texto explicativo del concepto"
    }},
    {{
      "tipo": "bullet_list",
      "items": ["ítem 1", "ítem 2", "ítem 3"]
    }},
    {{
      "tipo": "definition",
      "termino": "término clave",
      "definicion": "definición clara y concisa"
    }},
    {{
      "tipo": "equation",
      "expresion_texto": "f(x) = ax² + bx + c",
      "expresion_matematica": "\\frac{{-b}}{{2a}}",
      "descripcion": "descripción de la fórmula"
    }},
    {{
      "tipo": "callout",
      "texto": "texto resaltado en recuadro"
    }},
    {{
      "tipo": "visual_reference",
      "recurso_id": "{ejemplo_recurso}",
      "posicion": "despues_bloque"
    }}
  ]
}}

TIPOS DE BLOQUE PERMITIDOS: heading, paragraph, bullet_list, numbered_list, equation, definition, callout, visual_reference.

IMPORTANTE: Responde solo con el JSON. No uses bloques de código ```json.
"""
    return instruccion


def _contexto_plan_ejercicios(
    plan: Optional[Dict[str, Any]], tema: str
) -> str:
    """Resume el tema y las secciones para anclar los ejercicios al plan."""
    if not isinstance(plan, dict) or not plan:
        return f"- Tema central: {tema or 'el tema indicado'}"

    lineas = [f"- Tema central: {plan.get('titulo') or plan.get('tema') or tema}"]
    disciplina = plan.get("disciplina") or ""
    if disciplina:
        lineas.append(f"- Disciplina del material: {disciplina}")

    objetivos = [
        str(o).strip() for o in (plan.get("objetivos_aprendizaje") or [])
        if str(o).strip()
    ]
    if objetivos:
        lineas.append("- Objetivos de aprendizaje: " + "; ".join(objetivos[:5]))

    secciones = plan.get("secciones") or []
    if isinstance(secciones, list) and secciones:
        lineas.append("- Secciones y conceptos que podés evaluar:")
        for indice, seccion in enumerate(secciones, 1):
            if not isinstance(seccion, dict):
                continue
            conceptos = [
                str(c).strip()
                for c in (seccion.get("conceptos_principales") or [])
                if str(c).strip()
            ]
            detalle = ": " + ", ".join(conceptos) if conceptos else ""
            lineas.append(
                f"  {indice}. {seccion.get('titulo', '')}{detalle}"
            )
    return "\n".join(lineas)


def obtener_instruccion_lote_ejercicios(
    dificultad: str,
    cantidad: int,
    contador_inicio: int,
    profundidad: str,
    disciplina: str = "",
    tema: str = "",
    plan: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Construye la instrucción para generar un lote de ejercicios.

    Incluye el tema y el plan aprobado para que el modelo no derive hacia
    otras materias (por ejemplo, química dentro de un tema de física) ni
    responda en otro idioma.
    """
    contexto = _contexto_plan_ejercicios(plan, tema)

    instruccion = f"""
Eres un docente experto. Vas a generar {cantidad} ejercicios de dificultad {dificultad}.

CONTEXTO OBLIGATORIO DEL MATERIAL:
{contexto}

CONFIGURACIÓN:
- Dificultad: {dificultad}
- Cantidad de ejercicios en este lote: {cantidad}
- Profundidad: {profundidad}
- Disciplina: {disciplina}
- Identificadores a usar: act{contador_inicio} a act{contador_inicio + cantidad - 1}

INSTRUCCIONES:
1. Debes responder ÚNICAMENTE con un objeto JSON válido.
2. Genera exactamente {cantidad} ejercicios de dificultad {dificultad}.
3. Cada ejercicio debe tener consigna clara, solución desarrollada y explicación.
4. No uses cálculos numéricos en historia ni preguntas de memoria en matemáticas.
5. Adapta el tipo de ejercicio a la naturaleza de la disciplina.
6. Usa EXACTAMENTE los nombres de campo del ejemplo, en minúsculas y SIN TILDES: "solucion" (no "solución"), "explicacion" (no "explicación").
7. Todos los campos del ejemplo son OBLIGATORIOS y no pueden faltar; sólo "datos" y "pista" pueden quedar como cadena vacía (""). No omitas "id", "dificultad", "tipo", "consigna", "solucion" ni "respuesta_final".
8. La dificultad debe ser exactamente "{dificultad}" en TODOS los ejercicios.
9. Escribe TODOS los campos en español neutro. No respondas en inglés, aunque el tema tenga un nombre en inglés.
10. Cada ejercicio debe evaluar exclusivamente el tema central y alguno de los conceptos de las secciones listadas. No incluyas ejercicios de química, biología, historia ni de otras materias ajenas al tema.
11. Si la disciplina abarca varias materias (por ejemplo, "Física y química"), elegí solamente la materia del tema central. No mezcles temas de la otra materia.

TIPOS DE EJERCICIO PERMITIDOS: calculo, analisis_conceptual, asociacion_conceptos, interpretacion_graficos, identificacion_errores, seleccion_justificada, desarrollo_escrito, estudio_de_casos, aplicacion_practica.

ESTRUCTURA OBLIGATORIA DEL JSON:
{{
  "ejercicios": [
    {{
      "id": "act{contador_inicio}",
      "dificultad": "{dificultad}",
      "tipo": "calculo",
      "consigna": "pregunta clara y específica",
      "datos": "datos necesarios (o cadena vacía si no aplica)",
      "pista": "pista opcional (o cadena vacía si no aplica)",
      "solucion": "solución desarrollada paso a paso",
      "respuesta_final": "respuesta breve",
      "explicacion": "por qué es correcta",
      "criterios_correccion": "cómo se evalúa el ejercicio"
    }}
  ]
}}

IMPORTANTE: Responde solo con el JSON. No uses bloques de código ```json.
"""
    return instruccion


def obtener_instruccion_componentes_finales(
    plan: Dict[str, Any],
    secciones: List[Dict[str, Any]],
    ejercicios: List[Dict[str, Any]],
) -> str:
    """
    Construye la instrucción para generar componentes finales (resumen, glosario, metadatos).
    """
    titulos_secciones = [s.get("titulo", "") for s in secciones]
    num_ejercicios = len(ejercicios)

    instruccion = f"""
Eres un docente experto. Vas a generar los COMPONENTES FINALES de un material educativo.

PLAN APROBADO:
- Título: {plan.get('titulo', 'Material educativo')}
- Disciplina: {plan.get('disciplina', '')}
- Nivel: {plan.get('nivel', '')}
- Secciones desarrolladas: {', '.join(titulos_secciones)}
- Total de ejercicios: {num_ejercicios}

INSTRUCCIONES:
1. Debes responder ÚNICAMENTE con un objeto JSON válido.
2. Genera el resumen final, el glosario y los metadatos del documento.
3. El resumen debe repensar las ideas fundamentales de todas las secciones.
4. El glosario debe incluir los términos clave de las secciones.
5. No inventes fuentes, autores ni citas. El campo "fuentes" queda vacío.
6. Usa EXACTAMENTE los nombres de campo del ejemplo: minúsculas y SIN TILDES.
7. Todos los campos del ejemplo son OBLIGATORIOS: no omitas "resumen_final", "glosario" ni "metadatos". "metadatos" debe incluir titulo, tema, disciplina y nivel.
8. No inventes ni devuelvas una fecha de generación: el programa la asigna localmente.

ESTRUCTURA OBLIGATORIA DEL JSON:
{{
  "metadatos": {{
    "titulo": "Título del material educativo",
    "subtitulo": "Subtítulo breve",
    "tema": "tema principal",
    "disciplina": "nombre de la disciplina",
    "nivel": "nivel educativo",
    "profundidad": "profundidad solicitada",
    "cantidad_actividades": {num_ejercicios},
    "generado_por_ia": true,
    "modo_demostracion": false
  }},
  "introduccion": "Breve introducción que conecta con las secciones desarrolladas.",
  "resumen_final": "Resumen de las ideas fundamentales del material.",
  "glosario": [
    {{
      "termino": "término clave 1",
      "definicion": "definición clara"
    }},
    {{
      "termino": "término clave 2",
      "definicion": "definición clara"
    }}
  ],
  "fuentes": []
}}

IMPORTANTE: Responde solo con el JSON. No uses bloques de código ```json.
"""
    return instruccion



