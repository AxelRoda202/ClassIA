# Proveedores de texto de ClassIA

Este documento describe la etapa 1 de proveedores de texto. No cubre todavía
los cambios de gráficos, imágenes externas ni concurrencia.

## Jerarquía activa

El orden objetivo es:

```text
gemini -> nvidia -> groq -> openrouter
```

Se controla con `AI_PROVIDER_ORDER`. El valor predeterminado es
`gemini,nvidia,groq,openrouter`.

Reglas:

- Gemini sigue siendo el proveedor principal.
- NVIDIA se usa directamente contra `https://integrate.api.nvidia.com/v1`.
  No pasa por OmniRoute ni por OpenRouter.
- Groq se usa directamente contra `https://api.groq.com/openai/v1`.
- OpenRouter queda como respaldo final.
- Un proveedor se omite sin interrumpir la generación si no tiene clave o si
  no tiene al menos un modelo candidato habilitado.
- Una clave configurada no alcanza para habilitar NVIDIA o Groq: también hace
  falta `NVIDIA_MODEL`/`NVIDIA_MODELS` o `GROQ_MODEL`/`GROQ_MODELS`.
- No hay modelos NVIDIA ni Groq habilitados por defecto.

## Variables de entorno

### Gemini

```ini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.8-flash
```

### NVIDIA NIM

```ini
NVIDIA_API_KEY=...
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=
NVIDIA_MODELS=
NVIDIA_RESPONSE_FORMAT=guided_json
```

`NVIDIA_MODEL` es el modelo preferido y se intenta primero.
`NVIDIA_MODELS` agrega candidatos separados por comas. La lista se deduplica.

### Groq

```ini
GROQ_API_KEY=...
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=
GROQ_MODELS=
GROQ_RESPONSE_FORMAT=json_object
```

### OpenRouter

Se mantiene la configuración anterior:

```ini
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...
OPENROUTER_MODELS=...
OPENROUTER_RESPONSE_FORMAT=json_schema
```

## Cómo agregar o deshabilitar un modelo candidato

Para agregar un candidato NVIDIA:

1. Verificá que el identificador exista en el catálogo oficial de
   [build.nvidia.com](https://build.nvidia.com/).
2. Agregalo a `NVIDIA_MODELS` o usalo en `NVIDIA_MODEL`.
3. Ejecutá el diagnóstico manual con **un solo modelo**.
4. Confirmá que responde JSON válido y que cumple el esquema real de ClassIA.
5. Recién entonces usalo en generaciones reales.

Para deshabilitarlo, quitá el identificador de la lista. Si la lista queda
vacía, NVIDIA se omite sin realizar solicitudes. El mismo criterio aplica a
Groq.

## Formatos estructurados

La validación local de ClassIA se aplica siempre, incluso si el proveedor usó
salida estructurada. Un JSON sintácticamente válido que no cumple el esquema
se rechaza y se pasa al siguiente modelo o proveedor.

### NVIDIA

- `guided_json` (predeterminado): envía el esquema real en
  `nvext.guided_json`, que es el mecanismo recomendado por la documentación de
  NVIDIA NIM.
- `json_object`: envía `response_format={"type":"json_object"}`.
- `text`: no envía restricción de formato; la validación local sigue activa.

No hay un fallback automático de `guided_json` a `json_object`. Si el modelo o
el endpoint rechazan el formato, el diagnóstico lo muestra y la decisión de
cambiar `NVIDIA_RESPONSE_FORMAT` es explícita.

### Groq

- `json_object` (predeterminado): modo JSON de la API compatible con OpenAI.
- `json_schema`: envía un esquema estricto; debe verificarse por modelo antes
  de usarlo en producción.
- `text`: sin restricción de formato, con validación local.

## Diagnóstico manual

Los scripts de diagnóstico **no se ejecutan** en la suite automática y **no**
hacen llamadas reales salvo que se indique `--ejecutar`.

### NVIDIA

Sin `--ejecutar` sólo muestra el plan y el cuerpo de la solicitud:

```powershell
python tools/diagnostico_nvidia.py
python tools/diagnostico_nvidia.py --modelo MODELO --etapa lote_ejercicios
```

Una única solicitud POST real:

```powershell
python tools/diagnostico_nvidia.py --modelo MODELO --etapa lote_ejercicios --ejecutar
```

Una única solicitud GET al catálogo:

```powershell
python tools/diagnostico_nvidia.py --catalogo --ejecutar
```

El script exige indicar exactamente un modelo cuando hay varios candidatos. No
recorre la lista completa. Si se omite `--modelo` y hay un solo candidato
configurado, lo usa; si hay varios, se detiene.

Qué verifica:

- Código HTTP y errores de autenticación, cuota, modelo o servidor.
- `finish_reason` (incluido `length` para respuestas truncadas).
- JSON sintácticamente válido.
- Validación contra el esquema real de `planificacion`, `seccion_teorica`,
  `lote_ejercicios` o `componentes_finales`.
- Contenido vacío o respuesta no JSON.

### OpenRouter

El diagnóstico existente sigue disponible:

```powershell
python tools/diagnostico_openrouter_json.py --catalogo
```

## Prueba local frente a prueba real

- **Prueba local**: `python -m unittest discover -s tests`. Usa mocks y no
  llama a APIs externas.
- **Prueba real controlada**: los comandos de diagnóstico con `--ejecutar`.
  Consumen cuota o crédito del proveedor y requieren una clave válida.
- Aprobar los tests con mocks **no** demuestra que NVIDIA o Groq estén
  verificados en producción.

## Modelos implementados, candidatos y verificados

### Implementados en código

- Gemini (adaptador existente de `google-genai`).
- NVIDIA NIM directo, compatible con OpenAI.
- Groq directo, compatible con OpenAI.
- OpenRouter (adaptador existente).

### Candidatos documentados, pendientes de verificación

NVIDIA:

- `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- `meta/llama-3.3-70b-instruct`
- `nvidia/nemotron-3-super-120b-a12b`

Groq:

- `openai/gpt-oss-120b`
- `openai/gpt-oss-20b`

Estos identificadores aparecen en la documentación oficial consultada, pero
ClassIA no verificó todavía, con una cuenta real:

- acceso efectivo;
- gratuidad o límites actuales;
- compatibilidad con `guided_json`/`json_schema`;
- calidad del contenido educativo en español.

Al momento de preparar esta rama, las fichas oficiales de varios de estos
modelos marcaban el *free endpoint* como deprecado o sujeto a endpoints de
socios. Por eso la lista queda vacía por defecto: consultá el catálogo vigente
de tu cuenta (`tools/diagnostico_nvidia.py --catalogo --ejecutar`) y habilitá
sólo modelos con acceso comprobado.

### Verificados en producción

Ninguno de los modelos NVIDIA o Groq fue verificado en producción en esta
etapa. La suite sólo prueba el comportamiento con mocks.

La disponibilidad y los límites gratuitos no son permanentes. Deben
comprobarse en las páginas oficiales del proveedor antes de usarlos.

## Clasificación de errores

`proveedores_ia.py` distingue:

- credenciales inválidas (`ErrorClaveInvalida`);
- modelo inexistente o no disponible (`ErrorModeloNoDisponible`);
- cuota agotada (`ErrorCuotaAgotada`);
- límite de solicitudes (`ErrorLimiteSolicitudes`, subtipo de cuota para
  conservar la compatibilidad);
- timeout (`ErrorTimeout`);
- error de red (`ErrorRed`);
- error del servidor (`ErrorServidor`);
- respuesta vacía (`ErrorRespuestaVacia`);
- JSON inválido (`ErrorJSONInvalido`);
- respuesta truncada (`ErrorRespuestaTruncada`);
- JSON válido fuera de esquema (`ErrorRespuestaInvalida`).

Para NVIDIA y Groq, un error de autenticación, red, límite de solicitudes o
servidor afecta al proveedor y no se reintenta con cada modelo. Un modelo
inexistente o que rechaza el formato se omite y se prueba el siguiente
candidato habilitado. Un problema de contenido se intenta con el siguiente
modelo.

## Riesgos y pendientes

- La compatibilidad real de `nvext.guided_json` en el endpoint alojado debe
  confirmarse con una cuenta y un modelo concretos.
- Los identificadores de modelos pueden cambiar o deprecarse.
- No se implementó concurrencia: la generación sigue siendo secuencial.
- Las etapas 2 (gráficos), 3 (concurrencia) y 4 (imágenes externas) están
  planificadas, no implementadas en esta rama.
