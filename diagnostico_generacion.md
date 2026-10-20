# Diagnóstico y Reparación del Flujo de Generación - Aula IA

## Fecha
19 de octubre de 2026

## 0. Actualización: corrección definitiva de la integración con Gemini y cierre de ventana

Esta sección documenta la última iteración, posterior al primer informe. Se
conserva el resto del documento como registro histórico.

### 0.1. Error reproducido

```
Error en Gemini: TypeError: Models.generate_content() got an unexpected keyword argument 'timeout'
Trabajo a82096e86689: Error en generación segmentada: El plan de aprendizaje no es JSON válido:
Expecting value: line 242 column 30 (char 7772). Respuesta cruda guardada en plan_crudo.json
```

### 0.2. Causa raíz confirmada

Se inspeccionó la API real instalada, no la documentación genérica:

| Comprobación | Resultado |
|---|---|
| Versión de `google-genai` | **2.31.0** |
| Firma de `Models.generate_content` | `(self, *, model, contents, config=None)` |
| `timeout` en `generate_content` | **No admitido** |
| `request_options` en `generate_content` | **No admitido** |
| Firma de `genai.Client.__init__` | incluye `http_options` |
| `types.HttpOptions.timeout` | `int` en **milisegundos** |

Por lo tanto, las dos variantes probadas antes (`request_options=...` y
`timeout=...`) eran inválidas. El tiempo de espera HTTP solo puede fijarse al
crear el cliente, mediante `types.HttpOptions(timeout=<ms>)`.

**Efecto en cadena:** el `TypeError` no era una respuesta del modelo. Al
propagarse como excepción genérica, el flujo cayó al proveedor alternativo,
que devolvió un JSON truncado. El error secundario "El plan de aprendizaje no
es JSON válido" fue una consecuencia, no la causa.

### 0.3. Corrección aplicada

`proveedores_ia.py`:

- Se agregó `_opciones_http_gemini()`, que construye
  `types.HttpOptions(timeout=int(TIMEOUT_SEGUNDOS) * 1000)`.
- Se agregó `_crear_cliente_gemini(api_key)`, único punto donde se crea el
  cliente: `genai.Client(api_key=..., http_options=...)`.
- `generate_content()` se llama **solo** con `model`, `contents` y `config`.
- Se agregó `ErrorIntegracion`, que clasifica `TypeError`, `AttributeError`,
  `NameError` e `ImportError` como errores de programación.
- `generar_contenido_educativo()` propaga `ErrorIntegracion` de inmediato: no
  prueba otros proveedores ni lo trata como JSON truncado.
- Se agregó `_motivo_finalizacion_gemini()` para distinguir `MAX_TOKENS` de
  otros motivos cuando la respuesta llega vacía.

`generador_bloques.py`:

- `_generar_plan()` ahora tiene reintentos limitados (`MAX_REINTENTOS_BLOQUE`),
  igual que el resto de bloques. Antes fallaba al primer intento.
- Las respuestas crudas se conservan sin sobrescribir: `plan_crudo.json`,
  `plan_intento2_crudo.json`, etc.
- `ErrorIntegracion` se propaga sin reintentos en secciones, lotes y
  componentes finales.
- El mensaje de error final distingue explícitamente un fallo de integración.

### 0.4. Error `RuntimeError: An attempt to fetch destroyed session.`

**Causa:** al cerrar la ventana durante la generación, el hilo de trabajo
seguía vivo y llamaba a `page.update()`. En Flet 1.0.4, `page.session` es una
`weakref`; cuando la sesión muere, el acceso lanza:

```python
raise RuntimeError("An attempt to fetch destroyed session.")
```

**Corrección en `interfaz.py`:**

- `_sesion_disponible()` consulta `page.session` (el mismo mecanismo que usa
  Flet) y captura el `RuntimeError`, marcando la sesión como inactiva.
- `_actualizar_pagina()` es el único punto de refresco: no propaga el error de
  sesión destruida y devuelve `False` si no se pudo actualizar.
- `_on_sesion_finalizada()` se registra en `page.on_disconnect` y
  `page.on_close`.
- `_on_evento_ventana()` detecta `ft.WindowEventType.CLOSE` en
  `page.window.on_event`.
- El callback de progreso se reenvía al hilo del event loop con
  `loop.call_soon_threadsafe`, y un fallo de refresco nunca cancela la
  generación.
- Al terminar, si la sesión murió, no se toca la UI: el trabajo ya quedó
  guardado en `temporal/<trabajo_id>/`.
- `_on_generar()` no inicia trabajo nuevo si la sesión ya no existe.
- Al cerrar se activa una **cancelación cooperativa**: `_cancelacion`
  (`threading.Event`) se marca y el generador la comprueba entre bloques
  (`_verificar_cancelacion`). Nunca se interrumpe una solicitud HTTP en curso.
- Se cancela además la **espera** de la tarea asíncrona
  (`_cancelar_tarea_generacion`). Así el proceso termina en segundos, en lugar
  de esperar varios minutos a que el hilo de trabajo acabe en segundo plano.
- El trabajo cancelado queda con `estado = failed`, `tipo_error = cancelado` y
  `cancelado = true`; nunca se marca como `completed`. Los bloques ya
  validados permanecen en `temporal/<trabajo_id>/` y se pueden reanudar.
- Los diálogos (`_abrir_configuracion`) y el `FilePicker`
  (`_guardar_copia`) también verifican la sesión antes de usarla.
- Un `RuntimeError` distinto de "destroyed session" se registra como
  advertencia y no se propaga desde un refresco de UI.
- Se corrigió el tamaño de ventana a la API de Flet 1.x (`page.window.width`,
  `page.window.height`, `page.window.resizable`), antes se usaban atributos
  inexistentes (`page.window_width`).

### 0.5. Progreso por hitos reales

Antes la barra solo avanzaba al inicio (0.05) y al final (1.0). Ahora se
informa cada operación terminada:

| Hito | Progreso |
|---|---|
| Planificación iniciada | 0.05 |
| Plan validado | 0.10 |
| Secciones teóricas | 0.10 → 0.55 |
| Lotes de ejercicios | 0.55 → 0.80 |
| Resumen y glosario | 0.80 |
| Ensamblado | 0.85 |
| Recursos visuales | 0.88 → 0.92 |
| Construcción del PDF | 0.95 |
| Completado | 1.00 |

El progreso es monótono y corresponde a operaciones reales; no hay esperas
artificiales.

### 0.6. Pruebas agregadas

`tests/test_proveedores_gemini.py` (15 pruebas):

1. El cliente recibe `HttpOptions` con timeout en milisegundos.
2. `TIMEOUT_SEGUNDOS=60` → `60000` ms.
3. `generate_content()` no recibe `timeout` ni `request_options`.
4. Una respuesta válida simulada se procesa correctamente.
5. Una excepción de Gemini se propaga y no se interpreta como JSON.
6. Un fallo de Gemini no sobrescribe `plan.json` ni bloques previos.
7. Todos los módulos se importan.

Además: un `TypeError` se clasifica como `ErrorIntegracion`, un error de
integración no prueba otro proveedor, y una respuesta vacía informa el motivo
de finalización.

`tests/test_flujo_segmentado.py` (15 pruebas):

1. Progreso monótono en el flujo completo.
2. Hitos de plan, secciones y lotes de ejercicios.
3. Las secciones validadas no se regeneran.
4. Una sección truncada se recupera con una versión más corta.
5. Los reintentos son limitados.
6. Un error de integración no se reintenta.
7. Un fallo de proveedor no se convierte en contenido.
8. Un callback de progreso roto no interrumpe la generación.
9. El manifiesto queda `completed` solo si el PDF se construyó.
10. Un fallo deja el manifiesto en `failed`.
11. La cancelación corta el flujo y conserva el plan validado.
12. Un trabajo cancelado queda `failed`, nunca `completed`.
13. Sin señal de cancelación, el flujo termina normalmente.
14. Un lote con claves acentuadas genera el documento completo.
15. El modo demostración construye el PDF sin llamar a ninguna API.

`tests/test_normalizacion_claves.py` (10 pruebas):

1. `solución` → `solucion` (reproduce el fallo real).
2. Se normalizan `explicación`, `criterios_corrección` y `respuesta_final`.
3. Si están ambas formas, gana la canónica.
4. Solo cambian las claves, nunca los valores.
5. Una clave desconocida se conserva.
6. La normalización recorre listas y objetos anidados.
7. Plan con `título` acentuado.
8. Sección con `sección_id` acentuado.
9. Componentes finales con `término` acentuado.
10. El lote real del trabajo fallido valida tras normalizar.

`tests/test_interfaz_sesion.py` (19 pruebas):

1. La app inicia con sesión viva.
2. No se actualiza una sesión destruida.
3. `_actualizar_estado` ignora una sesión destruida.
4. El evento de cierre marca la sesión inactiva.
5. La desconexión marca la sesión inactiva.
6. El `RuntimeError` de sesión no se propaga.
7. `_on_generar` no arranca si la sesión murió.
8. Cerrar la ventana durante la generación no lanza ni refresca la UI.
9. El callback de progreso no rompe tras el cierre.
10. El callback informa hitos reales.
11. Un callback que falla no cancela la generación.
12. El cierre cancela la espera de la tarea asíncrona.
13. Cancelar una tarea ya terminada es un no-op.
14. La configuración no abre diálogos en una sesión muerta.
15. Un error vuelve a mostrarse en rojo tras una copia guardada.
16. El cierre activa la señal de cancelación.
17. El evento de ventana activa la señal de cancelación.
18. El generador recibe el mismo evento de cancelación.
19. Un trabajo nuevo reinicia la señal de cancelación.

### 0.7. Resultado de la suite

```
Ran 115 tests
OK
```

No se realizaron llamadas reales a Gemini, OpenRouter ni Pollinations: todas
las pruebas usan mocks. El único mensaje de error de PDF que aparece en la
salida (`subcarpeta_inexistente`) es una prueba negativa intencional.

### 0.8. Clave `solución` (con tilde) rechazada por el validador

**Síntoma real, en una generación en vivo:**

```
Trabajo a6f221a59640: Error en generación segmentada: Lote de ejercicios no válido:
Ejercicio 0: falta el campo obligatorio 'solucion'.; Ejercicio 1: ...; Ejercicio 2: ...
```

**No fue un problema del armado del PDF.** El fallo ocurrió en la **etapa C
(ejercicios)**, antes de ensamblar el documento. Con 10 ejercicios la
distribución es 3 / 4 / 3 y los lotes son 4, por lo que la barra marcaba
`0.55 + 0.25 * (3/4) = 0.7625` (~76 %) cuando se detuvo.

**Evidencia** (`temporal/a6f221a59640/`): el lote
`lote_ejercicios_avanzado_3_crudo.json` traía las claves `solución`,
`explicación` y `criterios_corrección` (con tilde), mientras los otros tres
lotes usaban la forma sin tilde. El validador exige `solucion` exacto, así que
el contenido era correcto pero la validación fallaba. El modelo alterna entre
ambas formas de manera impredecible.

**Corrección:**

- `esquemas_bloques.normalizar_claves()`: lleva las claves a su forma canónica
  (sin diacríticos, en minúsculas) **solo** cuando coinciden con un campo
  conocido; recorre listas y objetos anidados; nunca modifica los valores; si
  aparecen ambas formas, prevalece la canónica. Una clave desconocida se deja
  intacta.
- Se aplica inmediatamente después de `json.loads`, en las cuatro etapas:
  plan, sección teórica, lote de ejercicios y componentes finales.
- `plantillas.py`: cada instrucción ahora exige explícitamente usar los
  nombres de campo del ejemplo, en minúsculas y **sin tildes**.

**Verificación con el dato real:** el lote que falló pasa de `False` a `True` en
la validación, con `solucion` presente y no vacía; el solucionario del PDF toma
`procedimiento` de `solucion`.

### 0.9. Trabajo previo conservado

El trabajo `temporal/a82096e86689/` se conservó intacto:

- `estado.json` con `"estado": "failed"` y el mensaje original.
- `plan_crudo.json` con la respuesta truncada (8074 bytes, termina en
  `"distribucion_actividades":`).

También se conserva el trabajo `temporal/a6f221a59640/` completo, que sirvió
como caso de prueba real para esta corrección.

No se borró ni se sobrescribió ningún archivo de diagnóstico anterior.

### 0.10. Errores 504 / JSON no válido / referencias visuales (trabajo `cd72a7516ba3`)

Una corrida en vivo reportó tres errores encadenados:

```
google.genai.errors.ServerError: 504 DEADLINE_EXCEEDED  (en generar_con_gemini)
Sección seccion1: JSON inválido en intento 1: Expecting value: line 1 column 1 (char 0)
Referencia a recurso visual inexistente: 'mapa_migraciones_germanicas_siglos_iv_v'
Referencia a recurso visual inexistente: 'mapa_transicion_mediterraneo_siglo_v'
```

#### 0.10.1. Causas confirmadas

| Error | Causa real (verificada en código y artefactos) |
|---|---|
| 504 | `HttpOptions` sólo fijaba `timeout`; con `retry_options=None` el SDK 2.31.0 usa `stop_after_attempt(1)` (no reintenta). El 504 es un timeout del gateway de Google, no del cliente local. |
| JSON inválido | `seccion_seccion1_crudo.json` (17 bytes) contiene literalmente `User Safety: safe`. Tras el 504, el fallback a OpenRouter devolvió texto no-JSON y se pasó a `json.loads`. |
| Referencias visuales | El plan define `recurso1/2/3`; el prompt de sección nunca comunicaba esos ids (el ejemplo decía `"id_del_recurso"`), así que el modelo inventó ids y omitió la referencia de `seccion1`. `validar_seccion_teorica` no validaba ids. |

El 504 y las referencias son **independientes**: las secciones se validaron bien; el
504 ocurrió en el intento 1 de `seccion1` y se recuperó en el intento 2.

#### 0.10.2. Correcciones aplicadas

- **`proveedores_ia.py`**
  - `_opciones_http_gemini()` agrega `types.HttpRetryOptions(attempts=3, initial_delay=1,
    max_delay=8, exp_base=2, jitter=1, http_status_codes=[408,429,500,502,503,504])`.
    Reintentos acotados en un único nivel (el SDK); no se multiplican con el bucle de bloques.
  - `clasificar_error()` usa `excepcion.code` si existe (5xx -> `ErrorServidor`, 401/403 ->
    `ErrorClaveInvalida`, 429 -> `ErrorCuotaAgotada`, 408 -> `ErrorRed`). Un 504 nunca se
    confunde con JSON truncado.
  - Nueva `ErrorContenidoNoJson` para respuestas que no son JSON (mensajes de seguridad).
  - Logging de proveedor usado y del fallback (sin claves ni secretos).
- **`generador_bloques.py`**
  - `_preparar_texto_json()`: distingue respuesta vacía (`ErrorRespuestaIncompleta`), texto
    no-JSON (`ErrorContenidoNoJson`) y JSON inválido/truncado (`json.JSONDecodeError`); quita
    cercas de código. Se aplica en plan, secciones, lotes y componentes. Una excepción nunca
    se parsea como contenido ni una respuesta vacía se acepta como válida.
  - Reconciliación de referencias visuales (fuente de verdad = catálogo del plan):
    `_reconciliar_referencias_de_seccion()` reconecta un id inventado a un recurso
    planificado libre, agrega los planificados omitidos y elimina colgantes sin destino;
    `_reconciliar_referencias_visuales()` lo aplica a todo el documento antes de validar.
  - **Recuperación (`regenerar_desde_trabajo`)**: ya no carga archivos `*_crudo.json` como
    bloques válidos, valida cada bloque antes de reutilizarlo, deduplica secciones por
    `seccion_id` y ejercicios por `id`, y **no ensambla** si falta alguna sección planificada.
- **`esquemas_bloques.py`**: `validar_seccion_teorica` exige `recurso_id` en cada
  `visual_reference` y rechaza secciones con todos los bloques vacíos.
- **`plantillas.py`**: la instrucción de sección lista los recursos planificados con sus
  ids exactos, prohíbe inventar identificadores y usa un id real en el ejemplo.

#### 0.10.3. Verificación con el trabajo real

Sobre una **copia** de `temporal/cd72a7516ba3/` (el original quedó intacto, 18 archivos),
`regenerar_desde_trabajo` ahora reconstruye `recuperado_*.pdf` (1.6 MB) con:

```
catalogo:    ['recurso1', 'recurso2', 'recurso3']
referencias: ['recurso1', 'recurso2', 'recurso3']
sin colgantes: True
```

Antes de reconciliar, ese documento fallaba con las dos referencias inexistentes; después
valida. La validación previa al PDF siguió activa en todo momento (no se desactivó).

#### 0.10.4. Suite

```
Ran 151 tests
OK
```

Se agregaron `tests/test_proveedores_504.py` (16 pruebas: reintentos, 504, fallback,
clasificación de texto) y `tests/test_referencias_visuales.py` (16 pruebas: prompt, esquema,
reconciliación y replay del trabajo real), más `tests/test_recuperacion_trabajo.py` (4 pruebas
de recuperación: crudos, duplicados y secciones faltantes). Sin llamadas reales a proveedores.

---

## 0.11. Actualización: cuota diaria de Gemini agotada (429) y cambio automático a OpenRouter

### 0.11.1. Lo que reportó el usuario

Durante una generación, Gemini respondió `ClientError: 429 RESOURCE_EXHAUSTED`
(cuota diaria del plan gratuito: 20 solicitudes/día para `gemini-3.8-flash`,
reintentar en ~18 h). En consola sólo se veía:

```
Error en Gemini: ClientError: 429 RESOURCE_EXHAUSTED. ...
...traceback...
Proveedor gemini no disponible: cuota agotada.
```

El usuario preguntó si el programa debería cambiar automáticamente a OpenRouter.

### 0.11.2. Diagnóstico

1. **El cambio de proveedor ya existía.** `generar_contenido_educativo` recorre
   `AI_PROVIDER_ORDER` (`gemini,openrouter`); al clasificar el 429 como
   `ErrorCuotaAgotada` continúa con OpenRouter. OpenRouter está configurado
   (`OPENROUTER_API_KEY` presente) y `openrouter/free` es un modelo válido de
   OpenRouter (enruta a un modelo gratuito).
2. **El cambio era invisible.** La aplicación no llamaba a `logging.basicConfig`, así
   que el logger raíz sólo usaba el "last resort" de Python (advertencias y errores).
   Los `logger.info` (incluido `Proveedor de IA usado: openrouter`) se descartaban: por
   eso no se veía que el flujo continuaba con OpenRouter.
3. **Trabajo desperdiciado.** Aunque el fallback funcionaba, cada bloque volvía a
   intentar Gemini primero (y el SDK reintentaba el 429) antes de pasar a OpenRouter.
   Con cuota **diaria** agotada, reintentar es inútil.

### 0.11.3. Cambios

- **`main.py`**: `_configurar_logging()` configura consola + `temporal/aula_ia.log`
  (rotativo, 2 MB x 3), nivel `INFO` por defecto (`AULA_IA_LOG_LEVEL`). Así el cambio de
  proveedor y los errores de red/cuota quedan visibles y auditables.
- **`proveedores_ia.py`**
  - `cuota_es_persistente(mensaje)`: distingue un 429 diario (`PerDay`, `retry in Nh`)
    de un límite por minuto (segundos).
  - `generar_contenido_educativo(..., proveedores_agotados=None)`: conjunto compartido
    durante la ejecución; si un proveedor agota su cuota diaria se recuerda y se omite
    en los bloques siguientes (paso directo al proveedor alternativo). Si todos quedan
    agotados, el error explica cuáles y por qué.
  - `_resumen_error_http()` + mensajes accionables de OpenRouter: `401` (clave),
    `402` (falta de crédito / usar `:free`), `404` (revisar `OPENROUTER_MODEL`),
    `429` (cuota, con detalle del límite gratuito), `5xx` (servidor) y errores
    reportados en el cuerpo con HTTP 200.
- **`generador_bloques.py`**: `GeneradorBloques.proveedores_agotados` (conjunto por
  instancia/sesión) se pasa a las cuatro llamadas al pipeline de proveedores.

> No se modificaron claves, modelos configurados ni el orden de proveedores.

### 0.11.4. Verificación

- `cuota_es_persistente` del mensaje real (18 h) → `True`; de `retry in 30s` → `False`.
- Flujo simulado: primer bloque intenta Gemini (429 diario) y usa OpenRouter; los
  bloques siguientes **no vuelven a llamar a Gemini** (`call_count == 1`) y la
  generación termina con éxito.
- Errores de OpenRouter: `402/404/429/401` y error-en-cuerpo-200 producen mensajes
  claros y la clasificación esperada.

### 0.11.5. Suite

```
Ran 163 tests
OK
```

Nuevas pruebas en `tests/test_fallback_cuota.py` (12). Se ajustaron dos dobles de
`tests/test_flujo_segmentado.py` para aceptar el nuevo parámetro `proveedores_agotados`.
Sin llamadas reales a proveedores.

### 0.11.6. Nota operativa (no es un cambio de código)

Con los planes gratuitos, el flujo segmentado (plan + secciones + lotes + componentes)
consume ~15–25 solicitudes por documento. Con Gemini gratuito (20/día) y OpenRouter
gratuito (50/día, o 1000/día si se cargan 10 créditos) se pueden generar uno o dos
documentos por día. Si se necesita más volumen conviene cargar crédito o reducir la
segmentación. `openrouter/free` enruta a un modelo gratuito distinto en cada solicitud;
si se prioriza la consistencia del JSON puede fijarse un modelo concreto con `:free`
(decisión del usuario: no se cambió la configuración).

---

## 0.12. Actualización: `openrouter/free` devolvía JSON truncado o vacío

### 0.12.1. Lo observado en la segunda prueba (con logging activo)

Ya con el logging visible se vio el flujo completo: Gemini quedó marcado como
agotado y **todo el trabajo se hizo con OpenRouter**. Pero `openrouter/free`
resultó poco fiable:

| Etapa | Resultado de la primera respuesta |
| --- | --- |
| Planificación | truncada (`Unterminated string`, sólo 181 caracteres) → función **2** |
| Sección 1 | contenido vacío → sección **2** |
| Lote avanzado | intento 1: `User Safety: safe` (no JSON); intento 2: JSON truncado → **falló** |

La causa no era el programa sino el **enrutado aleatorio** de `openrouter/free`:
elegía modelos gratuitos distintos en cada solicitud, incluidos modelos de
razonamiento (que gastan el presupuesto de tokens "pensando" y devuelven el JSON
cortado) y modelos que responden texto libre o quedan en blanco. El flujo hizo
todo bien: reintentó los bloques y, ante dos fallos seguidos, **abortó con error
claro** en lugar de generar un PDF incompleto.

### 0.12.2. Cambio aplicado (`proveedores_ia.py`)

- La solicitud a OpenRouter ahora incluye `response_format: {"type":
  "json_object"}`. Esto **fuerza el modo JSON** y, según la documentación de
  OpenRouter, hace que `openrouter/free` **filtre** y sólo enrute a modelos que
  admiten salida estructurada (evita el enrutado aleatorio a modelos que no
  pueden devolver JSON).
- Si un proveedor rechaza `response_format` o `reasoning` (400/404/422), se
  **reintenta una vez sin esos parámetros opcionales**, sin perder el bloque ni
  fallar la generación.
- Se envía `reasoning: {"enabled": false}` para no gastar el presupuesto de
  tokens en "pensamiento" (motivo de los JSON truncados).
- Diagnóstico reforzado: cuando el contenido llega vacío se informa
  `finish_reason` y si el modelo devolvió sólo razonamiento; si la respuesta se
  corta por límite de tokens (`finish_reason=length`) se registra una advertencia.

### 0.12.3. Pruebas

Nuevas en `tests/test_fallback_cuota.py` (`TestModoJsonOpenRouter`, 5): envío de
`response_format` y `reasoning`, reintento sin parámetros opcionales ante 400
(por `response_format` o por `reasoning`), y mensajes de contenido vacío con
`finish_reason`/razonamiento.

```
Ran 168 tests
OK
```

### 0.12.4. Modelo fijado (decisión del usuario)

`openrouter/free` sigue eligiendo un modelo distinto por solicitud, así que el
usuario aprobó fijar uno concreto. Se consultó la lista real de modelos de
OpenRouter (`/api/v1/models`): entre los gratuitos con salida JSON están Gemma 4,
Nemotron 3, MiniMax M3.1 Flash, Dots3 y Xing4.0. Se fijó:

```
OPENROUTER_MODEL=google/gemma-4-31b-it:free
```

Motivos: modelo **instruct** multimodal con **español sólido** y modo JSON nativo.
Es gratuito (sujeto al límite diario de OpenRouter). Cambio de una sola línea en
`.env`. (Más tarde se volvió a `openrouter/free`: ver 0.13.5.)

---

## 0.13. Actualización: `reasoning` rechazado y campos obligatorios faltantes

### 0.13.1. Lo observado

- Con `openrouter/free`, una solicitud devolvió **HTTP 200** con un cuerpo de error:
  `"Reasoning is mandatory for this endpoint and cannot be disabled."`
  (causado por el parámetro `reasoning: {enabled: false}` que se había agregado).
- Un lote de ejercicios falló con `falta el campo obligatorio 'dificultad'` y
  **abortó sin reintentar**.

### 0.13.2. Causas

1. `reasoning.enabled=false` no es compatible con todos los endpoints que el
   router gratuito puede elegir; algunos **exigen** razonamiento. El rechazo llega
   como error dentro de un HTTP 200, por lo que el reintento anterior (que sólo
   miraba 400/404/422) no lo cubría.
2. En `_generar_un_lote_ejercicios` y `_generar_componentes_finales` se lanzaba
   `ErrorBloque` **dentro** del `try`. Como `ErrorBloque` no hereda de `ErrorIA`,
   la excepción salía del bucle y **saltaba los reintentos**. (Las secciones ya
   estaban corregidas de esta forma.)

### 0.13.3. Cambios

- **`proveedores_ia.py`**: se quitó `reasoning` del payload. El reintento sin
  parámetros opcionales ahora también detecta un `error` en el cuerpo con
  HTTP 200 (además de 400/404/422).
- **`generador_bloques.py`**:
  - `_completar_campos_derivables_ejercicios()`: completa **sólo** lo que el
    programa ya conoce (la dificultad pedida para el lote, con equivalencias
    como "media"→"intermedio", y los ids correlativos). **No inventa contenido**:
    si falta `consigna`, `solucion` o `respuesta_final`, el lote sigue inválido.
  - Lotes y componentes: ante un fallo de esquema se registra el error, se agrega
    una **instrucción correctiva con los errores concretos** y se reintenta
    (hasta `MAX_REINTENTOS_BLOQUE`), en lugar de abortar.
- **`plantillas.py`**: se declaran explícitamente los campos obligatorios y que
  la dificultad debe ser exactamente la pedida en todos los ejercicios.

### 0.13.4. Pruebas

- `tests/test_campos_obligatorios.py` (6): campos derivables, variantes de
  dificultad, no invención de contenido, reintento de lote y de componentes.
- 2 nuevas en `tests/test_fallback_cuota.py`: error en cuerpo con HTTP 200 y
  ausencia de `reasoning` en el payload.

```
Ran 175 tests
OK
```

### 0.13.5. Nota sobre el modelo

Fijar `google/gemma-4-31b-it:free` concentró todo el uso en **un solo** modelo
gratuito y agotó su límite diario, por lo que el usuario volvió a
`openrouter/free`, que reparte las solicitudes entre varios modelos gratuitos.
Con crédito cargado (o un modelo pago) la estabilidad sería mucho mayor; no se
cambió la configuración sin esa decisión.

### 0.13.6. Límite de esta solución

La garantía total de esquema requeriría `response_format` con
`json_schema` estricto por tipo de bloque. No se implementó ahora porque cada
bloque (plan, sección, lote, componentes) tiene un esquema distinto y no todos
los modelos gratuitos soportan modo estricto. Las tres capas aplicadas
(completar campos derivables, reintentar con feedback y prompt explícito) cubren
los fallos observados sin inventar contenido.

---

## 0.14. Actualización: OpenRouter con JSON Schema por etapa y diagnósticos separados

### 0.14.1. Error observado y causa

La generación segmentada falló al validar un lote:

```
No se pudo generar lote de 3 ejercicios de dificultad 'inicial' después de 2 intentos.
Último error: Lote de ejercicios no válido: Ejercicio 0: falta el campo obligatorio
'respuesta_final'
```

El artefacto guardado mostraba `respusta_final` (un typo), no la ausencia total
del campo. `openrouter/free` es un router: elige endpoints distintos en cada
solicitud y no garantiza que respeten el esquema. La normalización de claves
existente corrige tildes y mayúsculas, pero no typos, y el prompt por sí solo no
alcanzaba.

Los tres modelos pedidos (`qwen/qwen3.8-27b`, `nex-agi/nex-n2.5-mini`,
`nex-agi/nex-n2.5-pro`) **no existen como variantes `:free`** en el catálogo
actual; sólo tienen variantes de pago. Por eso no se usaron.

### 0.14.2. Modelos gratuitos verificados

Se consultó el catálogo público y las fichas de endpoints. Los candidatos
elegidos tienen precio `0` en prompt/completion, anuncian
`structured_outputs` y `response_format`, y el endpoint declara
`require_parameters`:

| Modelo | Contexto | Salida máx. | Expira |
|---|---:|---:|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | 262 144 | 235 929 | — |
| `dots-studio/dots-3-note-preview:free` | 512 000 | 460 800 | 2026-12-31 |
| `xingchen-agi/xing4.0-29b-a4b:free` | 262 144 | 235 929 | — |
| `nvidia/nemotron-3.5-super-vl:free` | 1 000 000 | 131 072 | — |

Se excluyó `openrouter/free`: su endpoint de detalles no devuelve una lista
estable de endpoints y su comportamiento anterior produjo respuestas vacías,
razonamiento sin contenido y JSON truncado. También se excluyó
`liquid/lfm-2.5-2.6b:free` por ser un modelo pequeño con salida máxima de 8192,
poco adecuado para planes largos.

> El límite gratuito de OpenRouter es **por cuenta**: 50 solicitudes/día (1000
> con 10 créditos). El fallback entre modelos no evita ese límite; sirve para
> sortear modelos caídos, endpoints que no admiten el esquema o límites
> puntuales por minuto.

### 0.14.3. Configuración aplicada

En `.env` (sin imprimir ni modificar las claves):

```
AI_PROVIDER_ORDER=openrouter
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
OPENROUTER_MODELS=nvidia/nemotron-3-super-120b-a12b:free,dots-studio/dots-3-note-preview:free,xingchen-agi/xing4.0-29b-a4b:free,nvidia/nemotron-3.5-super-vl:free
OPENROUTER_RESPONSE_FORMAT=json_schema
```

`OPENROUTER_MODEL` es el preferido y se intenta primero; `OPENROUTER_MODELS`
aporta el resto, sin duplicados. `.env.example` documenta ambas variables y las
notas de Pollinations.

### 0.14.4. Esquemas reales por etapa

`esquemas_bloques.py` construye un esquema distinto para cada etapa. No hay un
esquema genérico:

- **Planificación** (`plan_aprendizaje`, `strict: false`): títulos, objetivos,
  secciones, recursos visuales y distribución. `data` queda abierto a propósito
  porque los gráficos locales usan series, eventos, nodos o filas.
- **Sección teórica** (`seccion_teorica`, `strict: true`): `seccion_id`, `orden`,
  `titulo` y `bloques`. Cada bloque es un objeto plano con `tipo` enumerado y
  todos los campos posibles; los que no corresponden van como cadena o lista
  vacía.
- **Lote de ejercicios** (`lote_ejercicios`, `strict: true`): cada ejercicio
  exige `id`, `dificultad`, `tipo`, `consigna`, `datos`, `pista`, `solucion`,
  `respuesta_final`, `explicacion` y `criterios_correccion`, con
  `additionalProperties: false`. Esto impide que un typo como `respusta_final`
  pase como campo válido.
- **Componentes finales** (`componentes_finales`, `strict: true`): `metadatos`,
  `introduccion`, `resumen_final`, `glosario` y `fuentes`.

Se quitaron las uniones `["string", "null"]` y `["array", "null"]`: algunos
proveedores las rechazan al traducir el esquema. Los campos opcionales usan
`""` o `[]`, y la validación local sigue siendo obligatoria antes de aceptar.

### 0.14.5. Flujo de fallback y límite de intentos

`generar_con_openrouter_estructurado()`:

- Hace **una sola** solicitud por modelo y por solicitud lógica.
- Envía `response_format` `json_schema` con `strict` según la etapa y
  `provider.require_parameters=true`.
- Verifica `message.content` (cadena o lista de partes), `finish_reason`, el
  modelo real devuelto y el validador local antes de aceptar.
- Pasa al siguiente modelo ante 400/404/422, 429, 5xx, error lógico en HTTP 200,
  contenido vacío, sólo razonamiento, JSON inválido/truncado o esquema
  incumplido.
- Aborta sin probar otro modelo ante 401/403 (clave inválida).
- Recuerda en `modelos_agotados` los 404, los 400/422 de esquema no admitido y
  los 429 con cuota persistente (`per-day`); un 429 transitorio no se recuerda.
- Si se agotan todos, lanza `ErrorModelosAgotados`. `generador_bloques.py` no
  repite el lote: el límite es global y evita multiplicar llamadas.
- Registra etapa, modelo solicitado, modelo real, estado HTTP, tipo de error,
  intento y resultado de validación. Nunca registra la clave.

En modo `json_object` (respaldo configurable) se conserva toda la validación
local; el esquema no se envía, pero un JSON válido que no cumpla los campos
obligatorios se rechaza.

### 0.14.6. Diagnósticos separados

**OpenRouter** — `tools/diagnostico_openrouter_json.py`:

- `--catalogo` (predeterminado): consulta el catálogo público y muestra modelos
  gratuitos con JSON Schema, contexto, salida máxima, soporte `json_object` y
  fecha de expiración. No genera texto, no consume cuota y no necesita clave.
- `--probar-modelo ID`: hace exactamente una solicitud pequeña con el esquema
  mínimo `{"ok": true, "campo": "prueba"}`, valida el objeto y muestra el modelo
  real. Clasifica autenticación, límite, proveedor, falta de soporte, respuesta
  vacía, sólo razonamiento, truncada, JSON inválido y esquema incumplido. Lee la
  clave de `.env` y nunca la imprime ni la guarda.

**Pollinations** — `tools/probar_pollinations.py`:

- Por defecto sólo verifica configuración y consulta el catálogo de modelos: no
  genera imágenes, no consume saldo y no requiere clave.
- `--generar-una --confirmar-posible-consumo`: hace **una** solicitud de
  512×512, con un prompt simple y semilla aleatoria. Verifica HTTP,
  `Content-Type`, tamaño, que Pillow abra la imagen y que el archivo sea nuevo;
  guarda en `temporal/pruebas_pollinations/` con nombre único y nunca guarda un
  error como imagen. Muestra el coste de catálogo y advierte si no puede
  verificarlo.
- No se ejecuta al iniciar ClassIA ni desde los tests.

Endpoint vigente: `https://gen.pollinations.ai/image/{prompt}`. Exige clave
secreta y consume Pollen. Para `black-forest-labs/flux.1-schnell` el catálogo
informa `0.002` Pollen por imagen (`flat_rate: true`, `paid_only: false`). La API
clásica `https://image.pollinations.ai/prompt/{prompt}` es gratuita y sin clave,
pero usa otro endpoint, otro modelo y un máximo de 768×768 en JPEG.

### 0.14.7. Pruebas

Se agregaron 40 pruebas con mocks:

- `tests/test_openrouter_estructurado.py`: JSON Schema y `require_parameters`,
  fallback por HTTP 400/404/429/5xx, 401 sin fallback, contenido vacío con
  razonamiento, truncado, JSON inválido, esquema incumplido, `json_object` con
  validación local, modelo real, omisión de `modelos_agotados`, cuota diaria vs.
  transitoria, límite global y propagación de `ErrorModelosAgotados`.
- `tests/test_herramientas.py`: filtrado del catálogo, clasificación del
  diagnóstico OpenRouter, construcción de URL de Pollinations, búsqueda por
  alias, validación de PNG real con Pillow, rechazo de HTML/JSON/SVG/MIME
  incorrecto/tamaño pequeño, guardado sin sobrescritura y confirmación
  obligatoria.

Resultado de la suite completa:

```
Ran 215 tests
OK
```

Comando:

```
python -m unittest discover -s tests
```

### 0.14.8. Comandos manuales pendientes

```
python tools/diagnostico_openrouter_json.py --catalogo
python tools/diagnostico_openrouter_json.py --probar-modelo nvidia/nemotron-3-super-120b-a12b:free
python tools/probar_pollinations.py
python tools/probar_pollinations.py --generar-una --confirmar-posible-consumo
```

Requieren prueba manual: las dos pruebas reales de OpenRouter y Pollinations, y
una generación completa de material. No se ejecutó ninguna generación completa
en esta tarea. La primera ejecución accidental de la suite, antes de corregir un
mock desactualizado, dejó pasar llamadas reales a OpenRouter; se corrigió el
test y la suite posterior ya no hace llamadas. No hubo llamadas a Pollinations
ni consumo de imágenes.

### 0.14.9. Límites y notas

- El límite diario gratuito de OpenRouter es de cuenta, no por modelo. Si se
  agota, hay que esperar o cargar 10 créditos; el fallback no lo evita.
- `dots-studio/dots-3-note-preview:free` expira el 2026-12-31. El diagnóstico
  muestra la fecha; si expira, hay que reemplazarlo.
- El coste de Pollinations puede cambiar. El script lee el catálogo y no genera
  si no puede verificar modelo y coste.
- La generación de imágenes de la aplicación sigue usando su ruta actual; el
  diagnóstico usa sólo parámetros documentados (`model`, `width`, `height`,
  `seed`). Si la app recibiera un 400 por `nologo`, `private` o `enhance`, esos
  parámetros son candidatos a quitar.

### 0.15. Revisión de `dots-studio/dots-3-note-preview:free`

La prueba individual devolvió HTTP 200 con `finish_reason=length` y sin JSON
válido. La causa probable está en el límite de la propia prueba:

- `construir_solicitud_prueba()` envía `max_tokens=120`.
- En modelos con razonamiento, `max_tokens` cubre **razonamiento + salida
  visible**. Si el razonamiento consume todo el presupuesto, la API devuelve
  `finish_reason=length` con `message.content` vacío. Es el modo de fallo que
  documenta OpenRouter para presupuestos chicos.
- El catálogo del modelo declara `reasoning: {"mandatory": false}`. No anuncia
  `supported_efforts` ni `supports_max_tokens`, así que no corresponde enviar
  `reasoning.effort` ni `reasoning.max_tokens`. El endpoint sí admite
  `reasoning`, `include_reasoning`, `max_tokens` y `structured_outputs`.
- El control compatible es `reasoning: {"enabled": false}` (el modelo no es
  obligatorio) o aumentar sólo el `max_tokens` de la prueba. `include_reasoning`
  no sirve para esto: oculta el razonamiento de la respuesta, pero no libera el
  presupuesto.

Cambios en `tools/diagnostico_openrouter_json.py`:

- Imprime el `max_tokens` solicitado, el modo de razonamiento solicitado y el
  formato (`json_schema`, `strict=True`).
- Informa `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, salida
  visible (`completion - reasoning`) y `total_tokens` cuando la API los envía.
- Informa `native_finish_reason` y el proveedor real cuando están disponibles.
- Si `finish_reason=length` y la salida visible es 0, muestra una “CAUSA
  PROBABLE” indicando que el razonamiento agotó el presupuesto.
- Agrega `--max-tokens N` (sólo para la prueba; no toca `TOKEN_MAX_SALIDA` ni
  `.env`) y `--sin-razonamiento` (`reasoning.enabled=false`).
- No imprime ni guarda la clave.

Recomendación: retirar **temporalmente** el modelo de la lista de respaldo
hasta que pase una prueba individual corregida. El fallo actual no demuestra
que sea inviable en la app (la app usa `TOKEN_MAX_SALIDA=8192`, no 120), pero
tampoco lo valida, y cada intento fallido consume cuota gratuita de cuenta. Si
pasa `--sin-razonamiento`, volver a probarlo con razonamiento y un presupuesto
mayor antes de reincorporarlo; si falla aun sin razonamiento, retirarlo de
forma definitiva. No se hizo otra llamada real en esta revisión.

Comandos previstos (ejecutar manualmente, uno por vez):

```powershell
python tools/diagnostico_openrouter_json.py --probar-modelo dots-studio/dots-3-note-preview:free --sin-razonamiento
python tools/diagnostico_openrouter_json.py --probar-modelo dots-studio/dots-3-note-preview:free --max-tokens 8192
```

El segundo comando usa el mismo presupuesto que la app (`TOKEN_MAX_SALIDA=8192`),
pero sólo para esa prueba: no modifica el global ni `.env`. Si con 8192 el
razonamiento sigue agotando el presupuesto, el modelo no es adecuado para el
flujo actual.

---

## 0.16. Actualización: timeout real, restauración de trabajos y modelo de imagen

### 0.16.1. Timeout: causa y corrección

El trabajo `5e0b5dc2a057` había completado **todas** las etapas de IA
(plan, tres secciones, tres lotes de ejercicios y componentes finales) y
falló al entrar en `ensamblando documento` con:

```text
Tiempo máximo de generación excedido (600 segundos).
```

Causa: `configuracion.py` tenía el valor fijo

```python
TIEMPO_MAX_GENERACION_SEGUNDOS = 600
```

y no leía `TIEMPO_MAX_GENERACION_SEGUNDOS=1200` del `.env`.

Correcciones:

- `TIMEOUT_SEGUNDOS`, `MAX_REINTENTOS`, `TOKEN_MAX_SALIDA` y
  `TIEMPO_MAX_GENERACION_SEGUNDOS` se leen del entorno con un helper que
  valida enteros y usa un valor seguro si el `.env` está mal escrito.
- El valor global por defecto ahora es **1200 segundos** (20 minutos).
- El límite global se aplica a las etapas que llaman a la IA. Una vez que
  todo el contenido está validado, el **ensamblado, los gráficos y el PDF
  locales se terminan aunque se haya alcanzado el límite**. Así no se pierde
  trabajo ya generado por unos segundos de ensamblado.
- La UI espera `TIEMPO_MAX_GENERACION_SEGUNDOS + 120` para dar margen al
  ensamblado y al PDF.
- Si el hilo de generación termina correctamente justo después del límite de
  espera, la UI muestra ese resultado en lugar de un error engañoso. Antes de
  habilitar otra operación espera a que el hilo deje de escribir en el mismo
  trabajo, porque un hilo de `run_in_executor` no se puede cancelar.
- `.env.example` documenta la variable y el valor recomendado.

Verificación: `configuracion.TIEMPO_MAX_GENERACION_SEGUNDOS` devuelve
`1200` con el `.env` actual.

### 0.16.2. Restauración sin repetir la generación

Se comprobó que `regenerar_desde_trabajo()` ya podía reconstruir el PDF del
trabajo fallido sin IA. Ahora también está disponible desde la interfaz y
se amplió la reanudación:

- `analizar_trabajo(trabajo_id)`: cuenta secciones, ejercicios y componentes
  válidos, detecta secciones faltantes y reconstruye la configuración.
- `listar_trabajos_recuperables()`: lista trabajos fallidos o interrumpidos
  con plan o documento recuperable. Excluye los completados cuyo PDF existe.
- `continuar_desde_trabajo(trabajo_id)`: reanuda con IA sólo lo que falte.
- `_generar_ejercicios` reutiliza los lotes guardados por dificultad y
  genera únicamente la dificultad faltante, con ids correlativos sin
  colisiones.
- `_generar_componentes_finales` reutiliza `componentes_finales.json` si es
  válido.
- El plan y las secciones guardadas se validan antes de reutilizarse; un
  bloque inválido se regenera.
- `_guardar_estado` ahora **fusiona** el estado anterior en lugar de
  reemplazarlo, así no se pierde `configuracion`. Además se guarda
  `configuracion.json` al iniciar cada trabajo.
- La UI incorpora el botón **“Restaurar trabajo”**. El diálogo permite:
  - **Reconstruir PDF sin IA**, cuando ya están todos los bloques.
  - **Continuar con IA**, cuando faltan bloques; reutiliza lo guardado.

Resultado de la recuperación manual del trabajo fallido:

| Dato | Valor |
|------|-------|
| Trabajo | `5e0b5dc2a057` |
| Método | `regenerar_desde_trabajo` (sin IA) |
| PDF | `salida/recuperado_5e0b5dc2a057.pdf` |
| Bytes | 1.588.671 |
| Páginas | 7 |
| Estado final | `completed` |

### 0.16.3. Pollinations: parámetros y modelo recomendado

El OpenAPI vigente de `gen.pollinations.ai` documenta para
`/image/{prompt}` los parámetros `model`, `width`, `height` y `seed`. El
código enviaba además `nologo`, `private` y `enhance`, que no están
documentados; se quitaron de la URL de la app.

`STRICT_FREE_IMAGE_MODE` reemplazaba en silencio cualquier modelo nuevo por
`flux.1-schnell`. Ahora usa una lista de bajo coste que incluye los modelos
recomendados. Importante: **la lista no implica gratuidad**; el endpoint
descuenta Pollen incluso en modelos con `paid_only=false`.

Precios del catálogo (1 Pollen = 1 USD) y coste para 1024×768:

| Modelo | Coste | 2 imágenes/PDF | Texto/mapas |
|--------|-------|----------------|-------------|
| `black-forest-labs/flux.1-schnell` | 0,002/imagen | 0,004 | Flojo |
| `tongyi-mai/z-image-turbo` | 0,004/imagen | 0,008 | Flojo para texto largo |
| `black-forest-labs/flux.2-klein-4b` | 0,005/imagen | 0,010 | Mejora general; no garantiza texto |
| `qwen/qwen-image-2.1` | 0,02/MP ≈ 0,0157 | ≈ 0,031 | **Recomendado**: texto preciso |
| `bytedance/seedream-5.0-flash` | 0,019/imagen | 0,038 | Buen diseño/texto |
| `qwen/qwen-image` | 0,025/imagen | 0,050 | Muy bueno para texto |
| `ideogram-ai/ideogram-v4-turbo` | 0,03/imagen | 0,060 | Mejor tipografía |

Recomendación principal: **`qwen/qwen-image-2.1`** para mapas conceptuales,
diagramas o cualquier imagen con etiquetas. Es ~8× el coste actual, pero
sigue siendo ~0,016 USD por imagen. La alternativa económica es
`flux.2-klein-4b`; la mejor tipografía es `ideogram-v4-turbo`.

La solución más fiable y gratuita es no pedirle texto a un modelo de imagen:
- Los prompts de planificación ahora indican usar `diagram`, `flowchart`,
  `timeline` o `table` para mapas conceptuales, diagramas y todo recurso con
  etiquetas. Esos recursos se renderizan localmente con Matplotlib y el
  texto queda legible.
- `external_image` queda reservado para ilustraciones, fotografías o escenas
  sin texto; la leyenda va en `caption`/`alt_text`.

`tools/probar_pollinations.py` ahora acepta `--modelo`, `--ancho` y
`--alto` para comparar sin editar `.env`. La verificación de configuración
(consulta pública, **sin generar imagen**) confirmó:

```text
qwen/qwen-image-2.1
0.020000 pollen/MP; aprox. 0.015729 pollen para 1024x768
salud: healthy (éxito=100%)
```

Para comparar visualmente hace falta una solicitud real (consume saldo):

```powershell
python tools/probar_pollinations.py --generar-una `
  --confirmar-posible-consumo --modelo qwen/qwen-image-2.1 `
  --ancho 1024 --alto 768
```

No se cambió `POLLINATIONS_IMAGE_MODEL` en `.env`: la decisión de gastar
~0,016 USD por imagen queda en manos del usuario. Si se quiere usar, basta
con cambiar esa línea a `qwen/qwen-image-2.1` (ya está permitido por la
lista de bajo coste).

### 0.16.4. Pruebas y pendientes

- Suite completa: **235 pruebas OK**.
- Nuevas pruebas: lectura de enteros de entorno, análisis y listado de
  trabajos, fusión de estado, reanudación completa sin IA, generación sólo
  de la dificultad faltante, coste por megapíxel, diálogo de restauración y
  resultado tardío tras un timeout.
- Recuperación real del trabajo `5e0b5dc2a057`: OK, sin IA.
- No se hizo ninguna generación de imagen real en esta revisión.
- Pendiente: comparar visualmente `flux.1-schnell` vs `qwen-image-2.1` a
  1024×768; probar dots-studio; ejecutar una generación completa nueva con
  el flujo de reanudación.

### 0.16.5. Archivos modificados en esta iteración

| Archivo | Cambio |
|---------|--------|
| `configuracion.py` | Límites desde `.env`; timeout global por defecto 1200 |
| `.env.example` | Documentación de timeout y modelos de imagen |
| `generador_bloques.py` | Timeout local, configuración persistida, reanudación y reutilización |
| `generador_ia.py` | Delegación de `listar_trabajos_recuperables` y `continuar_desde_trabajo` |
| `interfaz.py` | Botón y diálogo “Restaurar trabajo”; margen de espera |
| `generador_imagenes.py` | Parámetros documentados; lista de modelos de bajo coste |
| `plantillas.py` | Regla para evitar texto generado por modelos de imagen |
| `tools/probar_pollinations.py` | `--modelo`, `--ancho`, `--alto`; coste por MP |
| `tests/` | Pruebas nuevas de configuración, recuperación, reanudación y UI |

---

## 1. Problema Reportado

El usuario reportó que al generar un material sobre "Causas de la caída del Imperio romano de Occidente" con profundidad estándar y generación de imágenes con IA activada:

- La aplicación permanecía ejecutándose más de 10 minutos.
- La barra de progreso avanzaba muy poco y parecía detenida.
- No aparecía el PDF final ni un mensaje claro de error.
- El panel de actividad de Pollinations no mostraba solicitudes de imágenes recientes.

## 2. Causas Confirmadas

### 2.1. `generar_con_gemini` sin timeout explícito (CRÍTICO)

**Archivo:** `proveedores_ia.py`, función `generar_con_gemini` (línea ~109)

La llamada `client.models.generate_content()` **NO pasaba un parámetro de timeout**. La biblioteca `google-genai` puede no tener un timeout por defecto razonable, o puede usar uno muy grande. Si Gemini se quedaba procesando o la red se quedaba silenciosa, la aplicación se bloqueaba indefinidamente sin que el usuario viera ningún mensaje.

**Solución (corregida en la sección 0):** El timeout no se pasa a
`generate_content()`. Se configura con `types.HttpOptions(timeout=<ms>)` al
crear el cliente de Gemini. Las variantes `request_options=...` y
`timeout=...` no son admitidas por `google-genai` 2.31.0.

### 2.2. `_generar_componentes_finales` no manejaba `json.JSONDecodeError`

**Archivo:** `generador_bloques.py`, función `_generar_componentes_finales` (línea ~468)

La función capturaba `ErrorRespuestaIncompleta` y `ErrorIA`, pero **NO capturaba `json.JSONDecodeError`**. Si Gemini devolvía un JSON mal formado (no vacío, pero inválido), se lanzaba una excepción no capturada que llegaba al `except Exception as e` del flujo principal, marcando como error inesperado sin información útil sobre qué bloque falló.

**Solución:** Se agregó manejo de `json.JSONDecodeError` en todas las funciones de generación de bloques (`_generar_una_sección`, `_generar_un_lote_ejercicios`, `_generar_componentes_finales`).

### 2.3. Endpoint de Pollinations obsoleto

**Archivo:** `generador_imagenes.py`, función `_descargar_imagen_pollinations` (línea ~150)

El código utilizaba el endpoint antiguo:
```
https://image.pollinations.ai/prompt/{prompt}
```

La documentación oficial actual de Pollinations utiliza:
```
https://gen.pollinations.ai/image/{prompt}
```

Además, el modelo configurado por defecto era `"flux"`, pero el identificador canónico documentado es `black-forest-labs/flux.1-schnell`.

**Solución:** 
- Endpoint cambiado a `https://gen.pollinations.ai/image/{prompt}`
- Modelo cambiado a `black-forest-labs/flux.1-schnell`
- Se agregó logging detallado de la solicitud y respuesta

### 2.4. Sin logging estructurado

Ningún módulo utilizaba la biblioteca `logging` de Python. Era imposible saber en qué etapa se detenía el trabajo sin revisar manualmente los archivos temporales.

**Solución:** Se agregó `logging` en todos los módulos clave con eventos estructurados:
- `generador_bloques.py`: inicio/completado de cada etapa y bloque
- `generador_ia.py`: inicio/final de generación completa
- `generador_imagenes.py`: inicio/completado de cada imagen
- `proveedores_ia.py`: solicitud/respuesta a proveedores de texto
- `interfaz.py`: inicio/final de la generación desde la UI

### 2.5. Sin tiempo de espera total para la generación completa

No había un límite global para toda la generación. Si una etapa se atasca, se quedaba para siempre.

**Solución:** Se agregó `TIEMPO_MAX_GENERACION_SEGUNDOS = 600` (10 minutos) en `configuracion.py`. Si la generación completa supera este tiempo, se detiene y se informa al usuario.

### 2.6. Progreso de la UI estático

En `interfaz.py`, `_actualizar_estado` se llamaba con valores fijos (0.05 al inicio, 1.0 al final). Durante la generación de secciones y ejercicios, la barra de progreso no se actualizaba, dando la impresión de que la aplicación estaba congelada.

**Solución:**
- Se agregó un callback de progreso (`callback_progreso`) que se ejecuta en cada etapa
- La generación se ejecuta en un hilo separado (`asyncio.to_thread`) para no bloquear la UI
- Se agregó `asyncio.wait_for` con timeout para toda la generación
- La barra de progreso se actualiza con porcentajes reales por etapa:
  - Planificación: 0.10
  - Cada sección completada: incremento proporcional
  - Cada lote de ejercicios completado: incremento proporcional
  - Componentes finales: 0.85
  - Ensamblado: 0.90
  - PDF construido: 0.95
  - Completado: 1.00

## 3. Archivos Modificados

| Archivo | Cambio Principal |
|---------|-----------------|
| `configuracion.py` | Agregado `TIEMPO_MAX_GENERACION_SEGUNDOS = 600` |
| `proveedores_ia.py` | Timeout en llamadas a Gemini y OpenRouter + logging |
| `generador_bloques.py` | Manejo de `json.JSONDecodeError`, logging, tiempo máximo, callback de progreso |
| `generador_imagenes.py` | Endpoint actualizado a `gen.pollinations.ai`, modelo `black-forest-labs/flux.1-schnell`, logging |
| `interfaz.py` | Callback de progreso, ejecución en hilo separado, `asyncio.wait_for` |
| `generador_ia.py` | Paso de `callback_progreso` a `generador_bloques` |
| `diagnostico_generacion.md` | Documentación completa del diagnóstico y solución |

## 4. Pruebas Ejecutadas

| Prueba | Resultado |
|--------|-----------|
| Suite completa actual | **115/115 OK** |
| Suite anterior a esta iteración | 71/71 OK |
| Suite original del MVP | 55/56 (fallo ambiental por `.env`, ya neutralizado) |

El fallo `test_seleccionar_recursos_externos_vacio_sin_habilitado` se
corrigió: la prueba ahora fuerza `IMAGE_GENERATION_ENABLED` en el módulo en
lugar de depender del valor real de `.env`.

Todas las pruebas de generación segmentada pasan:
- Plan válido seguido de secciones válidas ✓
- Diez ejercicios distribuidos por dificultad ✓
- Respuesta truncada (MAX_TOKENS) rechazada ✓
- Respuesta JSON inválida rechazada ✓
- Bloque que falla y se recupera reduciendo tamaño ✓
- Bloque que agota reintentos → error claro ✓
- Reinicio con secciones previamente validadas ✓
- Preservación de respuestas crudas ✓
- Ensamblado correcto de todos los bloques ✓
- Rechazo de documento con contenido obligatorio ausente ✓
- PDF con datos simulados ✓
- Sin duplicación de ejercicios al reintentar ✓
- Error de cuota gestionado correctamente ✓

## 5. Limitaciones Pendientes

- La generación de imágenes externas requiere `IMAGE_GENERATION_ENABLED=1` en `.env` y una clave de Pollinations válida.
- El máximo predeterminado es 2 imágenes externas por documento.
- No se realizaron llamadas reales a Pollinations durante las pruebas (se usaron mocks).
- La disponibilidad gratuita de Pollinations debe verificarse por el usuario antes de usar en producción.
- Para verificar realmente Pollinations, el usuario debe:
  1. Consultar https://gen.pollinations.ai/docs para verificar condiciones actuales
  2. Configurar `IMAGE_GENERATION_ENABLED=1` y `POLLINATIONS_API_KEY` en `.env`
  3. Probar con un tema simple y verificar que se genera al menos una imagen

## 6. Cómo Probar Manualmente

1. Ejecutar `python main.py` con el entorno virtual activado.
2. Ingresar un tema (ej: "Caída del Imperio Romano").
3. Seleccionar profundidad "breve" para una prueba rápida.
4. Dejar "Habilitar imágenes generadas por IA (externas)" desactivado para la primera prueba.
5. Pulsar "Generar material PDF".
6. Verificar que la barra de progreso avance y el PDF se genere en menos de 10 minutos.
7. Para probar imágenes externas, configurar `.env` con `IMAGE_GENERATION_ENABLED=1` y `POLLINATIONS_API_KEY`, luego activar el interruptor.
8. Los logs se guardan en consola y en los archivos temporales de `temporal/<trabajo_id>/`.

## 7. Trabajo Guardado en `temporal/`

Cada generación crea una carpeta en `temporal/<trabajo_id>/` con:
- `estado.json`: estado actual del trabajo
- `plan_crudo.json`: respuesta original de la IA para el plan
- `plan.json`: plan validado
- `seccion_<id>.json`: cada sección generada y validada
- `lote_ejercicios_<dificultad>_<inicio>.json`: cada lote de ejercicios
- `componentes_finales.json`: resumen, glosario, metadatos
- `documento_ensamblado.json`: documento completo antes del PDF
- `respuesta_ia_cruda.json`: respuesta cruda de la IA (si falló validación)
- `graficos/`: imágenes generadas por Matplotlib
- `imagenes_externas/`: imágenes generadas por Pollinations (si está habilitado)
