# Plan de etapas 2 a 4 (no implementadas)

Este documento es sólo un plan. En la rama
`feat/classia-proveedores-graficos-paralelismo` se implementó únicamente la
etapa 1 de proveedores de texto. Las etapas 2, 3 y 4 **no** están
implementadas ni verificadas.

## Etapa 2: contratos de gráficos y diagramas

Objetivo: que cada recurso visual tenga datos verificables antes de intentar
dibujarlo, sin depender de que el modelo invente campos.

Trabajo previsto:

1. Definir un contrato explícito por tipo de recurso (`grafico_barras`,
   `grafico_lineas`, `grafico_circular`, `diagrama`, etc.).
2. Exigir en el JSON del plan y de las secciones los datos mínimos de cada
   contrato, en lugar de aceptar `data: {}`.
3. Validar localmente tipos, longitudes, etiquetas y valores antes de generar
   el PNG o la tarjeta de respaldo.
4. Diferenciar un recurso válido de un recurso incompleto y registrar el
   motivo del descarte.
5. Calcular los gráficos localmente con Matplotlib; no usar IA para dibujar.
6. Agregar pruebas de contrato para datos válidos, vacíos, incompletos y con
   tipos incorrectos.
7. Mantener una tarjeta de respaldo clara cuando no haya datos suficientes.

Criterio de aceptación: ningún `data: {}` llega a Matplotlib; todo gráfico
generado tiene datos comprobables y una prueba asociada.

## Etapa 3: concurrencia de dos secciones

Objetivo: reducir el tiempo de generación sin romper el orden, la recuperación
ni la UI.

Trabajo previsto:

1. Auditar el estado mutable de `GeneradorBloques` y aislar lo que no sea
   seguro compartir entre hilos.
2. Diseñar un ejecutor acotado a dos secciones simultáneas.
3. Mantener el orden final de las secciones, independientemente del orden de
   finalización.
4. Serializar o proteger la escritura de archivos y los contadores de
   progreso.
5. Definir qué ocurre si una sección falla: cancelar la otra, esperar y
   reintentar, o conservar lo ya validado.
6. Respetar `proveedores_agotados`, `modelos_agotados`, los límites de
   reintentos y la cancelación desde la interfaz.
7. Agregar pruebas con mocks que demuestren orden, aislamiento, progreso y
   errores concurrentes.

Criterio de aceptación: dos secciones se generan en paralelo con un límite
estricto de dos, sin duplicar llamadas ni mezclar estado, y la suite local
sigue pasando.

## Etapa 4: imágenes externas con Cloudflare Workers AI

Objetivo: evaluar el reemplazo de Pollinations por Cloudflare Workers AI, sin
afirmar que los modelos funcionan hasta probarlos con una cuenta real.

Candidatos **no verificados**:

- `@cf/black-forest-labs/flux-2-klein-9b`
- `@cf/leonardo/phoenix-1.0`
- `@cf/black-forest-labs/flux-2-klein-4b`

Trabajo previsto:

1. Confirmar en la documentación oficial de Cloudflare Workers AI los
   identificadores, la disponibilidad por cuenta y los límites vigentes.
2. Definir variables de entorno para cuenta, token y modelos candidatos, sin
   valores reales en el repositorio.
3. Implementar una prueba manual de una sola imagen por invocación.
4. Mantener la generación de imágenes como opcional y con respaldo local.
5. Validar tipo, tamaño y decodificación de la imagen antes de insertarla en
   el PDF.
6. Agregar pruebas con mocks; no llamar a Cloudflare durante la suite.
7. Documentar costos, límites y calidad observada sólo después de una prueba
   autorizada.

Criterio de aceptación: ningún candidato se presenta como verificado o
gratuito sin evidencia de una cuenta real; si falla la imagen externa, el PDF
sigue generándose con una tarjeta o recurso local.

## Fuera de alcance de esta rama

- No se modificó `main`.
- No se implementaron las etapas 2, 3 ni 4.
- No se hicieron llamadas reales a NVIDIA, Groq, OpenRouter, Pollinations ni
  Cloudflare.
- No se verificó en producción ningún modelo nuevo.
