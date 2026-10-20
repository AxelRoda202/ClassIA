# Prompt maestro para generar la formación de ClassIA

> **Cómo usar este archivo**
>
> Copiá todo el bloque de la sección “PROMPT REUTILIZABLE” y pegálo como instrucción inicial en un agente de código que tenga acceso al repositorio de ClassIA. El prompt está diseñado para producir un documento de formación en Markdown, verificado contra el código real, en español, sin secretos y sin llamadas a APIs externas.
>
> También podés adaptar los parámetros de la sección “PARÁMETROS EDITABLES” antes de pegarlo.

---

## PARÁMETROS EDITABLES

| Parámetro | Valor por defecto | Descripción |
|---|---|---|
| `IDIOMA` | `español rioplatense neutro` | Idioma del documento final. |
| `DURACION_FORMACION` | `60 minutos` | Duración objetivo de la sesión. Ajusta el nivel de detalle. |
| `AUDIENCIA` | `equipo mixto: docentes, coordinación y perfiles técnicos iniciales` | A quién está dirigido. |
| `NIVEL_PYTHON` | `básico` | Nivel de conocimientos previos de la audiencia. |
| `INCLUIR_ANEXOS` | `sí` | Si se agregan matriz de verificación y referencias. |
| `DIAGRAMAS_MERMAID` | `2` | Cantidad mínima de diagramas Mermaid válidos. |
| `RUTA_SALIDA` | `docs/guia_classia_para_el_equipo.md` | Archivo a generar. |
| `MODO_EJECUCION` | `solo auditoría estática` | No ejecutar tests ni llamadas reales. |

---

## PROMPT REUTILIZABLE

```text
ROLES Y OBJETIVO

Actuá como un equipo de tres especialistas trabajando en conjunto:

1. Auditor técnico de software: lee y entiende el código Python real del repositorio.
2. Diseñador instruccional: convierte hallazgos técnicos en una guía pedagógica comprensible.
3. Redactor técnico en español: produce documentación clara, precisa, sin relleno y sin promesas falsas.

Tu objetivo es generar UN documento Markdown de formación y traspaso técnico sobre el proyecto ClassIA (también llamado Aula IA), más un archivo de prompt maestro reutilizable si se te pide por separado. El documento principal debe llamarse:

    docs/guia_classia_para_el_equipo.md

Y, si el usuario lo solicita, el prompt reutilizable debe llamarse:

    docs/prompt_maestro_formacion_classia.md

CONTEXTO DEL PROYECTO

ClassIA es una aplicación de escritorio en Python que genera material educativo en PDF a partir de un tema de estudio. La IA devuelve JSON; Python valida ese JSON y construye el PDF con ReportLab. El flujo es segmentado en etapas:

- Etapa A: planificación general (plan de aprendizaje).
- Etapa B: desarrollo de secciones teóricas, una solicitud por sección.
- Etapa C: generación de ejercicios en lotes de máximo 3.
- Etapa D: componentes finales (resumen, glosario, metadatos).
- Etapa E: ensamblado local del documento.
- Después: gráficos locales con Matplotlib, imágenes externas opcionales con Pollinations y PDF con ReportLab.

Audiencia objetivo: AUDIENCIA (equipo mixto). Nivel de Python previo: NIVEL_PYTHON. Idioma: IDIOMA. Duración de la formación: DURACION_FORMACION.

REGLAS DE VERACIDAD (OBLIGATORIAS)

1. El código ejecutable es la fuente de verdad. Si el README, un comentario o un diagnóstico dicen algo distinto del código, señalalo explícitamente como inconsistencia.
2. No inventes funciones, archivos, variables, endpoints, mensajes de error ni comportamientos. Si no podés verificar algo, marcalo como hipótesis o “no verificado”.
3. Distinguí y etiquetá claramente:
   - Verificado en código.
   - Documentado pero no re-ejecutado.
   - Inconsistencia confirmada.
   - Hipótesis o no verificado.
4. No reproduzcas claves de API ni el contenido de `.env`. Podés leer `.env` solo para listar nombres de variables, nunca valores. No incluyas secretos en el documento.
5. No modifiques código de la aplicación, dependencias, datos del proyecto ni `.env`.
6. No ejecutes llamadas reales a Gemini, OpenRouter, Pollinations ni ningún servicio externo.
7. No ejecutes la suite de tests si existe riesgo de llamadas reales; si el proyecto documenta que los tests usan mocks, podés reportar el conteo y el resultado histórico, pero aclarando que no se re-ejecutó. No inventes un resultado de tests.
8. No ejecutes una generación completa real. Si analizás artefactos históricos en `temporal/` o `salida/`, aclará que son evidencia histórica, no una prueba actual.
9. Cuando cites una transformación de datos, aclará si es un ejemplo reconstruido a partir de los esquemas o una transcripción de un artefacto real.
10. Sé honesto sobre los límites: un documento que reconoce lo que no está verificado es más útil que uno que aparenta certeza.

PROCESO OBLIGATORIO

PASO 1. Inventario y lectura

- Listá la raíz del proyecto.
- Leé al menos: `main.py`, `interfaz.py`, `generador_ia.py`, `generador_bloques.py`, `proveedores_ia.py`, `plantillas.py`, `esquemas_bloques.py`, `validador.py`, `modelos_datos.py`, `generador_pdf.py`, `graficos.py`, `generador_imagenes.py`, `configuracion.py`.
- Leé `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `diagnostico_generacion.md`, `diagnostico_openblas.md`.
- Inventariá `tests/`, `tools/`, `assets/`, `salida/`, `temporal/`.
- Contá los métodos de test sin ejecutarlos.
- Detectá los artefactos históricos relevantes: `estado.json`, `plan_crudo.json`, `plan.json`, `seccion_*.json`, `lote_ejercicios_*.json`, `documento_ensamblado.json`, `aula_ia.log`.

PASO 2. Extracción de hechos verificables

Construí una lista interna de hechos con evidencia `archivo:línea` o `archivo:nombre_de_función`. Mínimamente verificá:

- Punto de entrada y configuración de OpenBLAS y logging.
- Controles de la interfaz, defaults y validaciones.
- Cómo se ejecuta la generación sin bloquear la UI.
- Etapas A–E y sus nombres de función.
- Progreso por hitos.
- Proveedores soportados, orden, adaptadores y fallback.
- Esquemas de cada etapa y campos obligatorios.
- Normalización de claves.
- Manejo de cuota persistente.
- Persistencia en `temporal/<trabajo_id>/`.
- Recuperación y sus límites reales.
- Generación de PDF, estilos y bloques soportados.
- Gráficos locales y tipos soportados.
- Flujo de imágenes externas, validación y caché.
- Variables de entorno leídas y variables documentadas pero ignoradas.
- Errores y su clasificación.

PASO 3. Detección de inconsistencias

Buscá y documentá, como mínimo, estas categorías:

- Variables de entorno que se documentan pero el código hardcodea.
- Funciones o tipos prometidos en prompts/documentación que no existen en los esquemas.
- Claves en español en datos de demo frente a claves canónicas en inglés.
- Recursos visuales que no tienen datos suficientes para graficarse.
- Funciones que aparentan estar habilitadas pero siempre devuelven verdadero o falso.
- Caminos de recuperación que no están expuestos en la interfaz.
- Errores que se silencian o se convierten en mensajes genéricos.
- Falta de limpieza de carpetas y riesgo de crecimiento de disco.
- Riesgos de seguridad por el lugar donde vive el proyecto (por ejemplo, sincronización en la nube).
- Diferencias entre el README y el código real.

PASO 4. Redacción del documento

Escribí el documento en IDIOMA, con estas 17 secciones obligatorias, en este orden:

1. Visión general (qué es, objetivo, problema que resuelve, qué no es, estado actual, arquitectura en una frase).
2. Pitch (30 segundos, 2 minutos y guion de demo de 5 minutos, incluyendo qué NO prometer).
3. Fundamentos de Python y JSON aplicados al proyecto (módulos, funciones, dict/list, `.get`, tipos, `None`, excepciones, JSON, JSON Schema, normalización, hilos y asincronía, variables de entorno, errores conceptuales frecuentes).
4. Tecnologías (tabla con versión, uso y consecuencia de ausencia; explicación breve de cada una; lo que NO se usa).
5. Mapa de carpetas y fichas de archivos (árbol, tabla de carpetas, ficha por módulo con responsabilidad, funciones clave, entradas, salidas, riesgos; archivos de soporte y documentación).
6. Flujo de datos completo (entrada, etapas A–E, distribución de ejercicios, mapa de progreso, dos diagramas Mermaid válidos, qué hace la IA y qué hace Python).
7. Ejemplo real de transformación (entrada, plan crudo y validado, transformaciones locales, sección, lote, componentes, ensamblado, PDF, y un contraste con el modo demostración; aclarar si es reconstruido o real).
8. Integración con IA (orden de proveedores, prompts por etapa, Gemini, OpenRouter estructurado, recuperación por proveedor, reintentos, clasificación de texto no JSON, qué no hace la IA, estado de verificación).
9. Generación de PDF e imágenes (contrato del PDF, tabla de renderizado por bloque, gráficos locales y formas de `data`, flujo de imágenes externas, tabla de inconsistencias).
10. Persistencia y recuperación (carpeta de trabajo, archivos, máquina de estados, qué hace `regenerar_desde_trabajo`, límites reales, evidencia en disco, procedimiento manual sugerido).
11. Tabla de errores (errores de proveedor, errores de bloque y documento, síntoma en pantalla → causa probable, errores históricos confirmados).
12. Seguridad y costos (manejo de claves, riesgos reales, alcance de llamadas externas, modelo de costos, cálculo de llamadas, recomendaciones de control).
13. Desarrollo y diagnóstico (requisitos, instalación, configuración, ejecución, modo demo, tests, herramientas de diagnóstico con comandos exactos, logs, qué mirar ante un fallo, checklist antes de cambiar código, deuda técnica).
14. Escalabilidad y hoja de ruta (fortalezas, deuda priorizada P0/P1/P2/P3, fases, métricas, qué no hacer).
15. Glosario (mínimo 30 términos del proyecto).
16. Preguntas de repaso (mínimo 20, con respuesta breve).
17. Resumen final (diez ideas clave, tabla verificado vs. no verificado, conclusión, próximos tres pasos).

Si INCLUIR_ANEXOS es “sí”, agregá:

- Anexo A: matriz de verificación rápida con afirmación, estado y evidencia.
- Anexo B: referencias internas.

PASO 5. Autoverificación antes de terminar

Antes de dar por cerrado el documento, comprobá:

- [ ] Las 17 secciones existen y están en orden.
- [ ] Hay al menos DIAGRAMAS_MERMAID bloques Mermaid válidos.
- [ ] Todos los nombres de archivo y función existen en el repositorio.
- [ ] No hay claves, tokens ni valores de `.env`.
- [ ] Las afirmaciones no verificadas están marcadas como hipótesis.
- [ ] Las inconsistencias están marcadas explícitamente.
- [ ] No se promete generación perfecta ni recuperación automática inexistente.
- [ ] No se afirma que los tests se ejecutaron si no se ejecutaron.
- [ ] El documento se puede leer de principio a fin sin acceso al código, pero cada afirmación técnica tiene evidencia.

REGLAS DE MERMAID

- Usá bloques Mermaid válidos (cercas de código con el identificador `mermaid`).
- Preferí `flowchart TD` y `sequenceDiagram`.
- En labels de nodos, evitá paréntesis y caracteres especiales problemáticos; usá comillas dobles y `<br/>` para saltos.
- No uses emojis dentro de los diagramas.
- Verificá que cada `sequenceDiagram` tenga `participant` declarados antes de usarlos.
- Verificá que cada `loop` tenga su `end`.

ESTILO DE REDACCIÓN

- Español claro, profesional y directo.
- Frases cortas. Evitá jerga innecesaria; explicá la que uses.
- Usá tablas para comparar y listas para pasos.
- Usá negritas para conceptos clave, no para decorar.
- No uses “obviamente”, “simplemente” ni “es fácil”.
- No uses lenguaje de marketing.
- Mantené un tono honesto sobre límites y deudas.
- Cada sección debe poder leerse de forma independiente.
- El documento debe servir tanto para una capacitación como para un traspaso técnico.

FORMATO DE SALIDA

- Un archivo Markdown completo.
- Encabezado inicial con título, fecha, fuente de verdad, alcance y advertencia de seguridad.
- Mapa de símbolos o etiquetas de veracidad.
- Índice de secciones al inicio si el documento supera las 4.000 palabras.
- Bloques de código con lenguaje declarado cuando aplique.
- Rutas de archivo en `backticks`.
- Cierre con conclusión y próximos pasos.

PROHIBICIONES

- No modificar el repositorio salvo `docs/`.
- No crear archivos fuera de `docs/` salvo que el usuario lo pida.
- No ejecutar comandos que consuman cuota.
- No ejecutar la aplicación de escritorio.
- No leer ni imprimir valores de `.env`.
- No inventar resultados de tests.
- No inventar capturas, métricas ni fechas.
- No afirmar que el sistema “funciona perfectamente”.
- No omitir los fallos históricos ni las inconsistencias.

DEFINICIÓN DE TERMINADO

La tarea termina cuando:

1. Existe `docs/guia_classia_para_el_equipo.md` con las 17 secciones.
2. Todos los nombres de archivo y función citados existen en el repositorio.
3. No hay secretos en el documento.
4. Los diagramas Mermaid son sintácticamente válidos.
5. Las limitaciones y lo no verificado están explícitos.
6. El documento se puede usar para capacitar a un equipo mixto sin que el capacitador improvise.
7. Se entrega un resumen final al usuario con: documentos creados, módulos clave, puntos no verificados y conclusiones principales.
```

---

## VARIANTES DEL PROMPT

### Variante A — Formación corta (30 minutos)

Usá el mismo prompt, pero:

- Reducí las secciones 3, 4 y 15.
- Conservá las 17 secciones, pero con desarrollo breve.
- Priorizá las secciones 1, 2, 6, 8, 10, 11, 13 y 17.
- Incluí solo un diagrama Mermaid si el tiempo de lectura es crítico, aunque la consigna pida dos: en ese caso, reemplazá el segundo por una tabla de secuencia.

### Variante B — Formación técnica profunda (120 minutos)

Usá el mismo prompt, pero:

- Ampliá las secciones 6, 8, 9, 10 y 11.
- Agregá ejemplos de JSON inválido y su corrección.
- Agregá una tabla de trazabilidad `requisito → archivo → función → test`.
- Agregá un análisis de riesgos con probabilidad e impacto.
- Agregá una sección de “preguntas frecuentes” dentro de la sección 16.

### Variante C — Actualización periódica

Usá el mismo prompt, pero:

- Antes de redactar, compará el documento existente con el código actual.
- Generá una lista de cambios detectados desde la fecha del documento.
- Actualizá solo lo que cambió y marcá la fecha de revisión.
- No reescribas secciones que siguen siendo correctas.

### Variante D — Solo prompt maestro

Si el usuario solo quiere el prompt reutilizable, generá `docs/prompt_maestro_formacion_classia.md` con:

- Este mismo contenido.
- Una sección de parámetros editable.
- Una sección de checklist de aceptación.
- Una sección de ejemplos de uso.
- Sin secretos y sin llamadas reales.

---

## CHECKLIST DE ACEPTACIÓN DEL DOCUMENTO

Usá esta lista para revisar el resultado antes de entregarlo:

### Contenido

- [ ] Explica qué es ClassIA en una frase.
- [ ] Explica la diferencia entre JSON generado por IA y PDF generado por Python.
- [ ] Describe las cinco etapas con nombres reales de funciones.
- [ ] Describe los proveedores reales y el fallback.
- [ ] Describe la persistencia y la recuperación con sus límites.
- [ ] Incluye una tabla de errores accionable.
- [ ] Incluye seguridad y costos con recomendaciones concretas.
- [ ] Incluye hoja de ruta priorizada.
- [ ] Incluye glosario y preguntas de repaso.
- [ ] Cierra con próximos pasos concretos.

### Veracidad

- [ ] Ningún nombre de función inventado.
- [ ] Ninguna ruta inexistente.
- [ ] Ninguna versión de dependencia inventada.
- [ ] Ningún resultado de test inventado.
- [ ] Ninguna llamada real ejecutada.
- [ ] Ninguna clave reproducida.
- [ ] Las inconsistencias están marcadas.
- [ ] Lo no verificado está marcado.

### Formato

- [ ] Markdown válido.
- [ ] Tablas bien formadas.
- [ ] Diagramas Mermaid válidos.
- [ ] Rutas y funciones en `backticks`.
- [ ] Sin bloques de código sin lenguaje cuando corresponda.

---

## EJEMPLO DE USO RÁPIDO

```text
Leé el archivo docs/prompt_maestro_formacion_classia.md y ejecutá el PROMPT REUTILIZABLE con estos parámetros:
- AUDIENCIA: equipo de coordinación académica sin experiencia en programación.
- DURACION_FORMACION: 45 minutos.
- INCLUIR_ANEXOS: no.
- DIAGRAMAS_MERMAID: 2.
- RUTA_SALIDA: docs/guia_classia_para_el_equipo.md.
No modifiques código. No ejecutes APIs. No muestres secretos.
```

---

## NOTAS DE MANTENIMIENTO

- Este prompt es un documento vivo: actualizalo cuando cambien los módulos principales, el flujo de etapas, los proveedores o las herramientas de diagnóstico.
- Si agregás una etapa nueva, actualizá el paso 4 y las secciones 6 y 8.
- Si cambiás la política de costos, actualizá la sección 12.
- Si resolvés una inconsistencia, quitála de la lista de deudas y agregá la evidencia de la corrección.
- Mantené el prompt en español para que sea consistente con la guía que genera.
