"""
Estructura central del contenido educativo (JSON).

Este módulo documenta el esquema esperado de la respuesta de la IA y
proporciona funciones de utilidad para crear estructuras vacías y
ejemplos de demostración.

Todos los nombres de campo están en español para que un estudiante
de secundaria técnica pueda leer y modificar el código fácilmente.
"""

from typing import Any, Dict, List
import uuid
import datetime


def generar_id() -> str:
    """Genera un identificador único corto."""
    return uuid.uuid4().hex[:8]


def material_educativo_vacio() -> Dict[str, Any]:
    """Devuelve un diccionario con la estructura completa vacía."""
    return {
        "metadatos": {
            "titulo": "",
            "subtitulo": "",
            "tema": "",
            "disciplina": "",
            "nivel": "",
            "profundidad": "",
            "cantidad_actividades": 0,
            "fecha_generacion": "",
            "generado_por_ia": True,
            "modo_demostracion": False,
        },
        "objetivos_aprendizaje": [],
        "conocimientos_previos": [],
        "introduccion": "",
        "secciones": [],
        "ejemplos_resueltos": [],
        "actividades": [],
        "solucionario": [],
        "glosario": [],
        "resumen_final": "",
        "fuentes": [],
        "recursos_visuales": [],
        "advertencia_ia": (
            "Este material fue generado con inteligencia artificial. "
            "Se recomienda contrastar la información importante con fuentes "
            "confiables o con un docente."
        ),
    }


def ejemplo_matematica() -> Dict[str, Any]:
    """Ejemplo completo de estructura para el tema 'Funciones cuadráticas'."""
    ahora = datetime.datetime.now().strftime("%d/%m/%Y")
    return {
        "metadatos": {
            "titulo": "Funciones Cuadráticas",
            "subtitulo": "Desde los fundamentos hasta la aplicación práctica",
            "tema": "Funciones cuadráticas",
            "disciplina": "Matemática",
            "nivel": "Secundario",
            "profundidad": "estándar",
            "cantidad_actividades": 10,
            "fecha_generacion": ahora,
            "generado_por_ia": True,
            "modo_demostracion": True,
        },
        "objetivos_aprendizaje": [
            "Identificar una función cuadrática y su forma estándar.",
            "Calcular el vértice, el eje de simetria y las intersecciones con los ejes.",
            "Graficar una parábola a partir de su ecuación.",
            "Resolver problemas reales que se modelan con funciones cuadráticas.",
        ],
        "conocimientos_previos": [
            "Operaciones con números enteros y fracciones.",
            "Cartesian plano y coordenadas (x, y).",
            "Ecuaciones de primer grado.",
        ],
        "introduccion": (
            "Una función cuadrática es una función polinómica de grado 2. "
            "Su gráfica es una parábola y aparece en situaciones como el tiro parabólico, "
            "el área de figuras y la optimización de beneficios."
        ),
        "secciones": [
            {
                "id": "seccion1",
                "orden": 1,
                "titulo": "Qué es una función cuadrática",
                "bloques": [
                    {
                        "tipo": "heading",
                        "texto": "Definición",
                    },
                    {
                        "tipo": "paragraph",
                        "texto": (
                            "Una función cuadrática tiene la forma f(x) = ax² + bx + c, "
                            "donde a, b y c son números reales y a ≠ 0."
                        ),
                    },
                    {
                        "tipo": "visual_reference",
                        "recurso_id": "grafico_parametro_a",
                        "posicion": "despues_bloque",
                    },
                    {
                        "tipo": "definition",
                        "termino": "Parábola",
                        "definicion": (
                            "Curva abierta que representa gráficamente a toda función cuadrática."
                        ),
                    },
                ],
            },
            {
                "id": "seccion2",
                "orden": 2,
                "titulo": "Elementos de la parábola",
                "bloques": [
                    {
                        "tipo": "heading",
                        "texto": "Vértice y eje de simetría",
                    },
                    {
                        "tipo": "paragraph",
                        "texto": (
                            "El vértice es el punto más alto o más bajo de la parábola. "
                            "Su coordenada x se calcula con x = -b / (2a)."
                        ),
                    },
                    {
                        "tipo": "equation",
                        "expresion_texto": "x = -b / (2a)",
                        "expresion_matematica": "\\frac{-b}{2a}",
                        "descripcion": "Fórmula de la abscisa del vértice.",
                    },
                ],
            },
        ],
        "ejemplos_resueltos": [
            {
                "id": "ejemplo1",
                "titulo": "Encontrar el vértice de f(x) = x² - 4x + 3",
                "pasos": [
                    "Identificar a = 1, b = -4, c = 3.",
                    "Calcular x = -(-4) / (2·1) = 2.",
                    "Calcular f(2) = 2² - 4·2 + 3 = -1.",
                    "El vértice es (2, -1).",
                ],
                "resultado": "Vértice: (2, -1). La parábola abre hacia arriba.",
            }
        ],
        "actividades": [
            {
                "id": "act1",
                "dificultad": "inicial",
                "tipo": "calculo",
                "consigna": "Dada f(x) = 2x² + 3x - 5, identificá los valores de a, b y c.",
                "datos": "f(x) = 2x² + 3x - 5",
                "pista": "Recordá que la forma es ax² + bx + c.",
                "solucion": "a = 2, b = 3, c = -5.",
                "respuesta_final": "a = 2, b = 3, c = -5.",
                "explicacion": "Se comparan los coeficientes directamente con la forma estándar.",
                "criterios_correccion": "Los tres valores deben coincidir exactamente.",
            },
            {
                "id": "act2",
                "dificultad": "inicial",
                "tipo": "calculo",
                "consigna": "Calculá la abscisa del vértice de f(x) = x² - 6x + 8.",
                "datos": "f(x) = x² - 6x + 8",
                "pista": "Usá x = -b / (2a).",
                "solucion": "a = 1, b = -6, entonces x = -(-6) / 2 = 3.",
                "respuesta_final": "x = 3.",
                "explicacion": "Sustituyendo en la fórmula se obtiene 3.",
                "criterios_correccion": "El valor debe ser 3.",
            },
            {
                "id": "act3",
                "dificultad": "inicial",
                "tipo": "analisis_conceptual",
                "consigna": "¿Para qué valores de a la parábola abre hacia arriba?",
                "datos": None,
                "pista": "Pensá en el signo del coeficiente principal.",
                "solucion": "La parábola abre hacia arriba cuando a > 0.",
                "respuesta_final": "Cuando a > 0.",
                "explicacion": "Si a es positivo, los brazos de la parábola apuntan hacia arriba.",
                "criterios_correccion": "Responder que a debe ser mayor que cero.",
            },
            {
                "id": "act4",
                "dificultad": "intermedio",
                "tipo": "calculo",
                "consigna": "Graficá f(x) = x² - 4x + 3 indicando vértice y cortes con el eje x.",
                "datos": "f(x) = x² - 4x + 3",
                "pista": "Primero hallá el vértice, luego resolvé x² - 4x + 3 = 0.",
                "solucion": "Vértice (2, -1). Cortes: x = 1 y x = 3.",
                "respuesta_final": "Vértice (2, -1); corte x = 1 y x = 3.",
                "explicacion": "Factorizando (x-1)(x-3)=0 se obtienen las raíces.",
                "criterios_correccion": "Vértice correcto y ambas raíces bien identificadas.",
            },
            {
                "id": "act5",
                "dificultad": "intermedio",
                "tipo": "interpretacion_grafico",
                "consigna": "Una pelota se lanza y su altura sigue h(t) = -5t² + 20t. ¿Cuánto tarda en llegar al suelo?",
                "datos": "h(t) = -5t² + 20t",
                "pista": "El suelo corresponde a h(t) = 0.",
                "solucion": "-5t² + 20t = 0 → -5t(t - 4) = 0 → t = 0 o t = 4. Tarda 4 segundos.",
                "respuesta_final": "4 segundos.",
                "explicacion": "La solución positiva t = 4 es el momento de impacto.",
                "criterios_correccion": "Identificar t = 4 como respuesta válida.",
            },
            {
                "id": "act6",
                "dificultad": "intermedio",
                "tipo": "seleccion_justificada",
                "consigna": "¿Qué efecto tiene aumentar el valor de |a| en la anchura de la parábola?",
                "datos": None,
                "pista": "Compará parábolas abiertas y cerradas.",
                "solucion": "Al aumentar |a|, la parábola se vuelve más estrecha.",
                "respuesta_final": "Se vuelve más estrecha.",
                "explicacion": "Un |a| mayor hace que la curva crezca más rápido.",
                "criterios_correccion": "Mencionar que se estrecha.",
            },
            {
                "id": "act7",
                "dificultad": "intermedio",
                "tipo": "asociacion_conceptos",
                "consigna": "Asociá cada forma de la función cuadrática con su utilidad.",
                "datos": None,
                "pista": "Recordá para qué sirve cada forma.",
                "solucion": (
                    "Forma estándar: identificar coeficientes. "
                    "Forma vértice: conocer vértice directamente. "
                    "Forma factorizada: conocer raíces."
                ),
                "respuesta_final": (
                    "Estándar → coeficientes; Vértice → vértice; Factorizada → raíces."
                ),
                "explicacion": "Cada forma resalta diferentes características de la parábola.",
                "criterios_correccion": "Asociaciones correctas para las tres formas.",
            },
            {
                "id": "act8",
                "dificultad": "avanzado",
                "tipo": "aplicacion_practica",
                "consigna": "Un agricultor quiere cercar un terreno rectangular junto a un río con 100 m de alambrado. ¿Qué dimensiones maximizan el área?",
                "datos": "100 m de alambrado, un lado es el río (no se cercan).",
                "pista": "Si x es el lado perpendicular al río, el otro lado mide 100 - 2x. El área es A(x) = x(100 - 2x).",
                "solucion": "A(x) = -2x² + 100x. Vértice: x = 25. Dimensiones: 25 m × 50 m. Área máxima: 1250 m².",
                "respuesta_final": "25 m × 50 m, área 1250 m².",
                "explicacion": "Se modela con una función cuadrática y se busca su vértice (máximo).",
                "criterios_correccion": "Dimensiones 25 m y 50 m, área 1250 m².",
            },
            {
                "id": "act9",
                "dificultad": "avanzado",
                "tipo": "estudio_de_caso",
                "consigna": "Una empresa produce x unidades y su ganancia es G(x) = -x² + 40x - 300. ¿Cuántas unidades maximizan la ganancia?",
                "datos": "G(x) = -x² + 40x - 300",
                "pista": "Buscá el vértice de la parábola que abre hacia abajo.",
                "solucion": "a = -1, b = 40 → x = -40 / (2·-1) = 20 unidades. Ganancia: G(20) = 100.",
                "respuesta_final": "20 unidades, ganancia 100.",
                "explicacion": "El vértice da el punto de máximo de la ganancia.",
                "criterios_correccion": "20 unidades y ganancia 100.",
            },
            {
                "id": "act10",
                "dificultad": "avanzado",
                "tipo": "desarrollo_escrito",
                "consigna": "Explicá con tus propias palabras por qué toda función cuadrática representa una parábola y dar un ejemplo de la vida real.",
                "datos": None,
                "pista": "Pensá en la forma de la gráfica y en situaciones de tiro o área.",
                "solucion": "Respuesta abierta. Debe mencionar que el grado 2 produce una curva simétrica (parábola).",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "No hay una única redacción correcta; se valora la comprensión del concepto.",
                "criterios_correccion": "Mencionar parábola, simetría y un ejemplo real válido.",
            },
        ],
        "solucionario": [
            {
                "actividad_id": "act1",
                "respuesta": "a = 2, b = 3, c = -5.",
                "procedimiento": "Comparar coeficientes de f(x) = 2x² + 3x - 5 con ax² + bx + c.",
                "explicacion": "Coincidencia directa de términos.",
                "criterios": "Los tres valores exactos.",
            },
            {
                "actividad_id": "act2",
                "respuesta": "x = 3.",
                "procedimiento": "x = -(-6) / (2·1) = 3.",
                "explicacion": "Aplicación directa de la fórmula del vértice.",
                "criterios": "Valor 3.",
            },
        ],
        "glosario": [
            {
                "termino": "Parábola",
                "definicion": "Gráfica de una función cuadrática.",
            },
            {
                "termino": "Vértice",
                "definicion": "Punto más alto o más bajo de la parábola.",
            },
        ],
        "resumen_final": (
            "Una función cuadrática tiene forma f(x) = ax² + bx + c y su gráfica es una parábola. "
            "El vértice se halla con x = -b/(2a). Sirve para modelar situaciones de tiro, área y optimización."
        ),
        "fuentes": [],
        "recursos_visuales": [
            {
                "id": "grafico_parametro_a",
                "tipo": "python_chart",
                "titulo": "Efecto del parámetro a en la parábola",
                "propósito_educativo": "Comprender cómo cambia la apertura y anchura al variar 'a'.",
                "descripcion": "Gráfico de varias parábolas con distintos valores de a.",
                "prompt_generacion_imagen": (
                    "Ilustración didáctica de tres parábolas con distintos valores de a, "
                    "etiquetadas y con ejes coordenados."
                ),
                "texto_alternativo": "Gráfico que muestra parábolas más anchas y más estrechas.",
                "pie_imagen": "Comparación de parábolas según el coeficiente a.",
                "ubicacion": {
                    "seccion_id": "seccion1",
                    "posicion": "despues_bloque",
                    "bloque_referencia": None,
                    "orden_relativo": 1,
                },
                "estrategia_renderizado": "python_chart",
                "datos": {
                    "tipo_grafico": "lineas",
                    "titulo": "Efecto de a en f(x) = ax²",
                    "ejes_x": ["x"],
                    "series": [
                        {"etiqueta": "a = 0.5", "valores": [0.5, 2, 4.5, 8, 12.5]},
                        {"etiqueta": "a = 1", "valores": [1, 4, 9, 16, 25]},
                        {"etiqueta": "a = 2", "valores": [2, 8, 18, 32, 50]},
                    ],
                },
                "estado": "pendiente",
                "ruta_archivo_generado": None,
            },
        ],
    }


def ejemplo_historia() -> Dict[str, Any]:
    """Ejemplo completo de estructura para el tema 'Revolución Francesa'."""
    ahora = datetime.datetime.now().strftime("%d/%m/%Y")
    return {
        "metadatos": {
            "titulo": "La Revolución Francesa",
            "subtitulo": "Causas, desarrollo y consecuencias",
            "tema": "Revolución Francesa",
            "disciplina": "Historia y geografía",
            "nivel": "Secundario",
            "profundidad": "estándar",
            "cantidad_actividades": 10,
            "fecha_generacion": ahora,
            "generado_por_ia": True,
            "modo_demostracion": True,
        },
        "objetivos_aprendizaje": [
            "Comprender las causas de la Revolución Francesa.",
            "Conocer las etapas principales de la revolución.",
            "Analizar la Declaración de los Derechos del Hombre y del Ciudadano.",
            "Valorar el impacto de la revolución en la historia universal.",
        ],
        "conocimientos_previos": [
            "Conocimiento básico de la Edad Moderna.",
            "Qué es la monarquía absoluta.",
            "División de la sociedad francesa en estamentos.",
        ],
        "introduccion": (
            "La Revolución Francesa (1789-1799) fue un proceso de cambios políticos y sociales "
            "que terminó con el Antiguo Régimen en Francia y sentó las bases de la ciudadanía moderna."
        ),
        "secciones": [
            {
                "id": "seccion1",
                "orden": 1,
                "titulo": "Causas de la Revolución",
                "bloques": [
                    {
                        "tipo": "heading",
                        "texto": "Crisis financiera y social",
                    },
                    {
                        "tipo": "paragraph",
                        "texto": (
                            "Francia enfrentaba una grave deuda por las guerras y el mantenimiento de la corte. "
                            "La sociedad estaba dividida en tres estamentos, y el Tercer Estado soportaba la carga impositiva."
                        ),
                    },
                    {
                        "tipo": "visual_reference",
                        "recurso_id": "linea_tiempo_revolucion",
                        "posicion": "final_seccion",
                    },
                ],
            },
        ],
        "ejemplos_resueltos": [],
        "actividades": [
            {
                "id": "act1",
                "dificultad": "inicial",
                "tipo": "analisis_conceptual",
                "consigna": "¿Cuáles eran los tres estamentos de la sociedad francesa antes de la Revolución?",
                "datos": None,
                "pista": "Recordá la división social del Antiguo Régimen.",
                "solucion": "Primer Estado (clero), Segundo Estado (nobleza) y Tercer Estado (burguesía, artesanos, campesinos).",
                "respuesta_final": "Primer Estado, Segundo Estado y Tercer Estado.",
                "explicacion": "La sociedad francesa estaba dividida en tres estamentos con distintos privilegios y obligaciones.",
                "criterios_correccion": "Mencionar los tres estamentos correctamente.",
            },
            {
                "id": "act2",
                "dificultad": "inicial",
                "tipo": "asociacion_conceptos",
                "consigna": "Asociá cada evento con su año: Toma de la Bastilla, Proclamación de la República, Ejecución de Luis XVI.",
                "datos": None,
                "pista": "Pensá en el orden cronológico de la Revolución.",
                "solucion": "Toma de la Bastilla: 1789. Proclamación de la República: 1792. Ejecución de Luis XVI: 1793.",
                "respuesta_final": "1789, 1792, 1793.",
                "explicacion": "Estas fechas marcan hitos clave de la Revolución Francesa.",
                "criterios_correccion": "Asociar correctamente cada evento con su año.",
            },
            {
                "id": "act3",
                "dificultad": "intermedio",
                "tipo": "desarrollo_escrito",
                "consigna": "Explicá con tus propias palabras cuáles fueron las causas principales de la Revolución Francesa.",
                "datos": None,
                "pista": "Pensá en la crisis financiera, la desigualdad social y las ideas ilustradas.",
                "solucion": "Respuesta abierta. Debe mencionar al menos: deuda financiera, desigualdad de los estamentos, influencia de la Ilustración.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "No hay una única redacción correcta; se valora la identificación de múltiples causas.",
                "criterios_correccion": "Mencionar al menos dos causas válidas con explicación breve.",
            },
            {
                "id": "act4",
                "dificultad": "intermedio",
                "tipo": "analisis_conceptual",
                "consigna": "¿Qué importancia tuvo la Declaración de los Derechos del Hombre y del Ciudadano?",
                "datos": None,
                "pista": "Pensá en los derechos que proclamó y su impacto.",
                "solucion": "Estableció los principios de libertad, igualdad y soberanía popular, sentando las bases de los derechos humanos modernos.",
                "respuesta_final": "Proclamó libertad, igualdad y soberanía popular.",
                "explicacion": "Fue un documento fundacional de los derechos ciudadanos.",
                "criterios_correccion": "Mencionar libertad, igualdad y su importancia histórica.",
            },
            {
                "id": "act5",
                "dificultad": "avanzado",
                "tipo": "estudio_de_casos",
                "consigna": "Analizá qué cambios trajo la Revolución Francesa para el campesinado francés.",
                "datos": None,
                "pista": "Pensá en la abolición de los derechos señoriales y la tenencia de la tierra.",
                "solucion": "Se abolieron los derechos señoriales, los campesinos pudieron ser propietarios de la tierra y se eliminaron los diezmos.",
                "respuesta_final": "Abolición de derechos señoriales, propiedad de la tierra, eliminación de diezmos.",
                "explicacion": "La Revolución transformó la estructura rural francesa.",
                "criterios_correccion": "Mencionar la abolición de señoríos y cambios en la tenencia de tierras.",
            },
            {
                "id": "act6",
                "dificultad": "avanzado",
                "tipo": "seleccion_justificada",
                "consigna": "¿Fue Napoleón Bonaparte un continuador o un traidor de los ideales de la Revolución? Justificá tu respuesta.",
                "datos": None,
                "pista": "Pensá en el Código Civil, el Imperio y los principios de 1789.",
                "solucion": "Respuesta abierta. Se puede argumentar ambas posiciones con evidencia histórica.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "Napoleón consolidó algunos logros (Código Civil) pero terminó estableciendo un imperio autoritario.",
                "criterios_correccion": "Argumentar la posición con evidencia histórica coherente.",
            },
            {
                "id": "act7",
                "dificultad": "avanzado",
                "tipo": "desarrollo_escrito",
                "consigna": "Describí cómo cambió la vida cotidiana en París antes y después de la Revolución Francesa.",
                "datos": None,
                "pista": "Pensá en la abolición de privilegios, nuevos símbolos y organización política.",
                "solucion": "Respuesta abierta. Debe mencionar cambios en vestimenta, lenguaje, participación política y símbolos nacionales.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "La Revolución transformó la vida cotidiana más allá de lo político.",
                "criterios_correccion": "Mencionar al menos dos cambios en la vida cotidiana.",
            },
            {
                "id": "act8",
                "dificultad": "avanzado",
                "tipo": "interpretacion_graficos",
                "consigna": "Interpretá un gráfico que muestra la evolución de la deuda pública de Francia entre 1770 y 1790. ¿Qué tendencia observás y cómo se relaciona con el estallido de la Revolución?",
                "datos": None,
                "pista": "Pensá en el aumento de la deuda por guerras y su relación con la crisis financiera.",
                "solucion": "La deuda creció sostenidamente, especialmente por las guerras de independencia de Estados Unidos y los conflictos europeos, lo que provocó la crisis financiera que desencadenó la Revolución.",
                "respuesta_final": "Tendencia creciente de la deuda relacionada con la crisis financiera.",
                "explicacion": "La deuda pública insostenible fue una causa directa de la Revolución.",
                "criterios_correccion": "Identificar tendencia creciente y relación con la crisis financiera.",
            },
        ],
        "solucionario": [
            {
                "actividad_id": "act1",
                "respuesta": "Primer Estado (clero), Segundo Estado (nobleza) y Tercer Estado (burguesía, artesanos, campesinos).",
                "procedimiento": "Recordar la división social del Antiguo Régimen.",
                "explicacion": "Los tres estamentos tenían distintos privilegios y obligaciones.",
                "criterios": "Mencionar los tres estamentos correctamente.",
            },
            {
                "actividad_id": "act2",
                "respuesta": "1789, 1792, 1793.",
                "procedimiento": "Asociar cada evento con su fecha histórica.",
                "explicacion": "Fechas clave de la Revolución Francesa.",
                "criterios": "Asociaciones correctas.",
            },
            {
                "actividad_id": "act7",
                "respuesta": "Respuesta abierta sobre cambios en la vida cotidiana.",
                "procedimiento": "Describir cambios sociales, culturales y políticos.",
                "explicacion": "La Revolución transformó múltiples aspectos de la vida diaria.",
                "criterios": "Mencionar al menos dos cambios.",
            },
            {
                "actividad_id": "act8",
                "respuesta": "Tendencia creciente de la deuda pública relacionada con la crisis financiera.",
                "procedimiento": "Analizar la relación entre deuda y revolución.",
                "explicacion": "La deuda insostenible fue una causa directa.",
                "criterios": "Identificar tendencia y causa-efecto.",
            },
        ],
        "glosario": [
            {
                "termino": "Antiguo Régimen",
                "definicion": "Sistema político y social basado en la monarquía absoluta y los estamentos.",
            },
            {
                "termino": "Tercer Estado",
                "definicion": "Estamento integrado por burguesía, artesanos y campesinos.",
            },
        ],
        "resumen_final": (
            "La Revolución Francesa transformó la sociedad francesa, abolió los privilegios de los estamentos "
            "y proclamó los derechos del hombre y del ciudadano."
        ),
        "fuentes": [],
        "recursos_visuales": [
            {
                "id": "linea_tiempo_revolucion",
                "tipo": "timeline",
                "titulo": "Línea de tiempo de la Revolución Francesa",
                "propósito_educativo": "Ubicar cronológicamente los eventos principales.",
                "descripcion": "Cronología desde 1789 hasta 1799 con hitos clave.",
                "prompt_generacion_imagen": (
                    "Línea de tiempo histórica con los eventos principales de la Revolución Francesa, "
                    "estilo educativo, sin textos extensos dentro de la imagen."
                ),
                "texto_alternativo": "Línea temporal de la Revolución Francesa.",
                "pie_imagen": "Cronología resumida de la Revolución Francesa (1789-1799).",
                "ubicacion": {
                    "seccion_id": "seccion1",
                    "posicion": "final_seccion",
                    "bloque_referencia": None,
                    "orden_relativo": 1,
                },
                "estrategia_renderizado": "python_diagrama",
                "datos": {
                    "eventos": [
                        {"anio": 1789, "evento": "Toma de la Bastilla"},
                        {"anio": 1789, "evento": "Declaración de los Derechos del Hombre"},
                        {"anio": 1792, "evento": "Proclamación de la República"},
                        {"anio": 1793, "evento": "Ejecución de Luis XVI"},
                        {"anio": 1799, "evento": "Golpe de Estado de Napoleón"},
                    ],
                },
                "estado": "pendiente",
                "ruta_archivo_generado": None,
            },
        ],
    }


def ejemplo_recursos_humanos() -> Dict[str, Any]:
    """Ejemplo completo de estructura para el tema 'Gestión de Recursos Humanos'."""
    ahora = datetime.datetime.now().strftime("%d/%m/%Y")
    return {
        "metadatos": {
            "titulo": "Gestión de Recursos Humanos",
            "subtitulo": "Fundamentos para administrar el capital humano",
            "tema": "Gestión de Recursos Humanos",
            "disciplina": "Recursos humanos, administración y economía",
            "nivel": "Secundario",
            "profundidad": "estándar",
            "cantidad_actividades": 10,
            "fecha_generacion": ahora,
            "generado_por_ia": True,
            "modo_demostracion": True,
        },
        "objetivos_aprendizaje": [
            "Conocer qué es la gestión de recursos humanos y para qué sirve.",
            "Identificar las etapas del proceso de reclutamiento y selección.",
            "Comprender la importancia de la capacitación y el clima laboral.",
            "Aplicar conceptos básicos a una situación laboral simulada.",
        ],
        "conocimientos_previos": [
            "Qué es una empresa y sus áreas básicas.",
            "Qué significa trabajar en equipo.",
        ],
        "introduccion": (
            "La gestión de recursos humanos es el área encargada de atraer, desarrollar y retener al talento "
            "dentro de una organización, buscando que tanto la empresa como los empleados crezcan juntos."
        ),
        "secciones": [
            {
                "id": "seccion1",
                "orden": 1,
                "titulo": "Qué es la gestión de recursos humanos",
                "bloques": [
                    {
                        "tipo": "heading",
                        "texto": "Definición y objetivo",
                    },
                    {
                        "tipo": "paragraph",
                        "texto": (
                            "Se ocupa de planificar las necesidades de personal, seleccionar candidatos, "
                            "capacitar al personal y evaluar el desempeño."
                        ),
                    },
                ],
            },
        ],
        "ejemplos_resueltos": [],
        "actividades": [
            {
                "id": "act1",
                "dificultad": "inicial",
                "tipo": "analisis_conceptual",
                "consigna": "¿Qué es la gestión de recursos humanos y cuál es su objetivo principal?",
                "datos": None,
                "pista": "Pensá en el área de personas de una empresa.",
                "solucion": "Es el área encargada de atraer, desarrollar y retener al talento dentro de una organización.",
                "respuesta_final": "Gestionar el capital humano de la organización.",
                "explicacion": "Busca que tanto la empresa como los empleados crezcan juntos.",
                "criterios_correccion": "Mencionar atraer, desarrollar y retener talento.",
            },
            {
                "id": "act2",
                "dificultad": "inicial",
                "tipo": "asociacion_conceptos",
                "consigna": "Asociá cada etapa del proceso de selección con su descripción: Publicar oferta, Revisar currículos, Entrevistar.",
                "datos": None,
                "pista": "Recordá el orden lógico del proceso de contratación.",
                "solucion": "Publicar oferta: dar a conocer la vacante. Revisar currículos: seleccionar candidatos. Entrevistar: conocer a los candidatos.",
                "respuesta_final": "Publicar oferta → dar a conocer vacante; Revisar currículos → seleccionar candidatos; Entrevistar → conocer candidatos.",
                "explicacion": "Cada etapa tiene un propósito específico en el proceso de selección.",
                "criterios_correccion": "Asociar correctamente cada etapa con su descripción.",
            },
            {
                "id": "act3",
                "dificultad": "intermedio",
                "tipo": "aplicacion_practica",
                "consigna": "Una empresa necesita contratar un vendedor. Describí los pasos que seguirías para seleccionar al mejor candidato.",
                "datos": None,
                "pista": "Seguí el proceso: definir el perfil, publicar, revisar, entrevistar, decidir.",
                "solucion": "Respuesta abierta. Debe incluir: definir el perfil del puesto, publicar la oferta, revisar currículos, entrevistar, seleccionar y contratar.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "No hay una única forma correcta; se valora un proceso ordenado y lógico.",
                "criterios_correccion": "Incluir al menos 4 pasos del proceso de selección.",
            },
            {
                "id": "act4",
                "dificultad": "intermedio",
                "tipo": "seleccion_justificada",
                "consigna": "¿Por qué es importante la capacitación continua del personal?",
                "datos": None,
                "pista": "Pensá en la adaptación a cambios y el rendimiento laboral.",
                "solucion": "Permite que los empleados actualicen sus conocimientos, se adapten a nuevas tecnologías y mejoren su desempeño.",
                "respuesta_final": "Actualizar conocimientos y mejorar el desempeño.",
                "explicacion": "La capacitación beneficia tanto al empleado como a la organización.",
                "criterios_correccion": "Mencionar actualización de conocimientos y mejora de desempeño.",
            },
            {
                "id": "act5",
                "dificultad": "avanzado",
                "tipo": "estudio_de_casos",
                "consigna": "Una empresa tiene alta rotación de personal. ¿Qué medidas de recursos humanos aplicarías para mejorarlo?",
                "datos": None,
                "pista": "Pensá en clima laboral, capacitación, reconocimientos y beneficios.",
                "solucion": "Respuesta abierta. Medidas posibles: mejorar el clima laboral, ofrecer capacitación, reconocer el desempeño, revisar salarios y beneficios.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "La rotación alta suele deberse a insatisfacción laboral; se requieren múltiples acciones.",
                "criterios_correccion": "Proponer al menos dos medidas concretas y justificadas.",
            },
            {
                "id": "act6",
                "dificultad": "avanzado",
                "tipo": "desarrollo_escrito",
                "consigna": "Explicá con tus propias palabras por qué el clima laboral es importante para el rendimiento de una empresa.",
                "datos": None,
                "pista": "Pensá en motivación, trabajo en equipo y productividad.",
                "solucion": "Respuesta abierta. Debe relacionar buen clima laboral con mayor motivación, mejor trabajo en equipo y mayor productividad.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "Un buen clima laboral reduce el ausentismo y mejora el desempeño general.",
                "criterios_correccion": "Relacionar clima laboral con rendimiento/productividad.",
            },
            {
                "id": "act7",
                "dificultad": "avanzado",
                "tipo": "estudio_de_casos",
                "consigna": "Una empresa de tecnología tiene problemas para retener programadores senior. ¿Qué estrategia de recursos humanos propondrías?",
                "datos": None,
                "pista": "Pensá en salarios, beneficios, capacitación y posibilidades de crecimiento.",
                "solucion": "Respuesta abierta. Estrategias: revisar salarios al mercado, ofrecer capacitación especializada, planes de carrera, beneficios flexibles, buen clima de trabajo.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "La retención de talento requiere un paquete completo de beneficios y desarrollo.",
                "criterios_correccion": "Proponer al menos dos estrategias concretas.",
            },
            {
                "id": "act8",
                "dificultad": "avanzado",
                "tipo": "seleccion_justificada",
                "consigna": "¿Es más importante contratar personas con experiencia o con potencial de aprendizaje? Justificá.",
                "datos": None,
                "pista": "Pensá en el tipo de empresa, el puesto y los recursos disponibles.",
                "solucion": "Respuesta abierta. Depende del contexto: experiencia para puestos críticos, potencial para puestos de desarrollo a largo plazo.",
                "respuesta_final": "Respuesta abierta, variada.",
                "explicacion": "No hay una respuesta única; depende de las necesidades organizacionales.",
                "criterios_correccion": "Argumentar la posición con criterios razonables.",
            },
        ],
        "solucionario": [
            {
                "actividad_id": "act1",
                "respuesta": "Es el área encargada de atraer, desarrollar y retener al talento dentro de una organización.",
                "procedimiento": "Definición de gestión de recursos humanos.",
                "explicacion": "Busca que la empresa y los empleados crezcan juntos.",
                "criterios": "Mencionar atraer, desarrollar y retener talento.",
            },
            {
                "actividad_id": "act2",
                "respuesta": "Publicar oferta → dar a conocer vacante; Revisar currículos → seleccionar candidatos; Entrevistar → conocer candidatos.",
                "procedimiento": "Asociar cada etapa con su propósito.",
                "explicacion": "Cada etapa del proceso de selección tiene una función específica.",
                "criterios": "Asociaciones correctas.",
            },
            {
                "actividad_id": "act7",
                "respuesta": "Respuesta abierta sobre estrategias de retención.",
                "procedimiento": "Proponer medidas de recursos humanos.",
                "explicacion": "La retención requiere beneficios, desarrollo y buen clima.",
                "criterios": "Proponer al menos dos estrategias.",
            },
            {
                "actividad_id": "act8",
                "respuesta": "Respuesta abierta sobre experiencia vs potencial.",
                "procedimiento": "Argumentar con criterios organizacionales.",
                "explicacion": "Depende del contexto y las necesidades de la empresa.",
                "criterios": "Argumentar con criterios razonables.",
            },
        ],
        "glosario": [
            {
                "termino": "Reclutamiento",
                "definicion": "Proceso de atraer candidatos para ocupar vacantes.",
            },
            {
                "termino": "Capacitación",
                "definicion": "Entrenamiento para mejorar las habilidades del personal.",
            },
        ],
        "resumen_final": (
            "La gestión de recursos humanos busca que la organización cuente con las personas adecuadas, "
            "motivadas y capacitadas para alcanzar sus metas."
        ),
        "fuentes": [],
        "recursos_visuales": [
            {
                "id": "diagrama_proceso_rrhh",
                "tipo": "flowchart",
                "titulo": "Proceso de selección de personal",
                "propósito_educativo": "Visualizar las etapas del reclutamiento y selección.",
                "descripcion": "Diagrama de flujo con los pasos desde detectar la vacante hasta contratar.",
                "prompt_generacion_imagen": (
                    "Diagrama de flujo educativo del proceso de selección de personal, "
                    "con cuadros y flechas, sin textos largos dentro."
                ),
                "texto_alternativo": "Diagrama de flujo del proceso de selección de personal.",
                "pie_imagen": "Etapas del proceso de selección en recursos humanos.",
                "ubicacion": {
                    "seccion_id": "seccion1",
                    "posicion": "final_seccion",
                    "bloque_referencia": None,
                    "orden_relativo": 1,
                },
                "estrategia_renderizado": "python_diagrama",
                "datos": {
                    "nodos": [
                        {"id": "n1", "texto": "Detectar vacante"},
                        {"id": "n2", "texto": "Publicar oferta"},
                        {"id": "n3", "texto": "Revisar currículos"},
                        {"id": "n4", "texto": "Entrevistar"},
                        {"id": "n5", "texto": "Seleccionar y contratar"},
                    ],
                    "relaciones": [
                        {"origen": "n1", "destino": "n2"},
                        {"origen": "n2", "destino": "n3"},
                        {"origen": "n3", "destino": "n4"},
                        {"origen": "n4", "destino": "n5"},
                    ],
                },
                "estado": "pendiente",
                "ruta_archivo_generado": None,
            },
        ],
    }


def obtener_ejemplo_por_disciplina(disciplina: str) -> Dict[str, Any]:
    """Devuelve el ejemplo de demostración correspondiente a la disciplina."""
    disciplina = disciplina.lower().strip()
    if "matem" in disciplina:
        return ejemplo_matematica()
    if "historia" in disciplina or "geografía" in disciplina:
        return ejemplo_historia()
    if "recurso" in disciplina or "administra" in disciplina or "economía" in disciplina:
        return ejemplo_recursos_humanos()
    # Por defecto, devuelve matemática
    return ejemplo_matematica()
