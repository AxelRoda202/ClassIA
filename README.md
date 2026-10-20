# Aula IA — Generador Educativo de PDF

Aplicación de escritorio desarrollada en Python con **Flet** que recibe un tema de estudio y genera un PDF educativo personalizado, desde los fundamentos hasta la aplicación práctica. Está orientada a estudiantes de secundaria.

## Objetivo y funcionamiento

El usuario ingresa un tema (por ejemplo: "Leyes de Newton", "Funciones cuadráticas", "Revolución Francesa"), selecciona opciones de generación y la aplicación:

1. **Planificación**: Genera un plan de aprendizaje estructurado (etapa A).
2. **Desarrollo por secciones**: Genera el contenido teórico sección por sección (etapa B).
3. **Ejercicios**: Genera los ejercicios en lotes pequeños por dificultad (etapa C).
4. **Componentes finales**: Genera resumen, glosario y metadatos (etapa D).
5. **Ensamblado**: Python ensambla todas las partes en el documento final (etapa E).
6. **Recursos visuales**: Genera gráficos locales con Matplotlib y, opcionalmente, ilustraciones externas mediante IA (Pollinations).
7. **PDF**: ReportLab compila el documento final con portada, identidad institucional, encabezados, pies de página y numeración.

La IA **no genera el PDF**; Python interpreta el JSON y construye el documento.

### Generación segmentada (bloques)

Para evitar que las respuestas de la IA se truncen en temas extensos, Aula IA utiliza un sistema de generación por bloques:

- **Una solicitud por sección**: Cada sección teórica se genera por separado, reduciendo el riesgo de truncamiento.
- **Lotes de ejercicios**: Los ejercicios se generan en grupos pequeños (máximo 3 por solicitud).
- **Validación incremental**: Cada bloque se valida individualmente antes de continuar.
- **Recuperación automática**: Si un bloque falla, se intenta regenerar con un tamaño menor. Si falla nuevamente, se informa al usuario y se conserva el progreso.
- **Reanudación**: Si la generación se interrumpe, se puede reanudar desde los bloques ya validados sin volver a llamar a la IA.

Este enfoque consume más solicitudes que un único JSON grande, pero disminuye drásticamente la posibilidad de perder todo el trabajo por una respuesta incompleta.

## Requisitos

- Python 3.9 o superior (probado con Python 3.13)
- Windows (la aplicación está preparada para ejecutarse localmente en Windows)

## Instalación de dependencias

### 1. Clonar o descargar el proyecto

Los archivos del proyecto están en la carpeta actual.

### 2. Crear y activar un entorno virtual (Windows PowerShell)

```powershell
# Crear entorno virtual
python -m venv .venv

# Activar entorno virtual
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la ejecución de scripts, ejecuta primero:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Instalar dependencias

```powershell
pip install -r requirements.txt
```

## Configuración de variables de entorno

### Crear el archivo .env

Copia `.env.example` a `.env`:

```powershell
Copy-Item .env.example .env
```

Edita `.env` y configura al menos una de las claves:

```ini
GEMINI_API_KEY=tu_clave_de_gemini
GEMINI_MODEL=gemini-3.8-flash

OPENROUTER_API_KEY=tu_clave_de_openrouter
OPENROUTER_MODEL=openrouter/free

AI_PROVIDER_ORDER=gemini,openrouter

# Modo demostración (1 = activar, 0 = desactivar)
AULA_IA_DEMO=0
```

### Cómo obtener las claves

- **Gemini**: https://aistudio.google.com/app/apikey (Google AI Studio)
- **OpenRouter**: https://openrouter.ai/keys

No compartas tus claves. El archivo `.env` está incluido en `.gitignore` y no debe subirse a control de versiones.

### Configuración de generación de imágenes externas (opcional)

Aula IA puede generar ilustraciones educativas mediante IA usando **Pollinations** (proveedor con modalidad gratuita). Esta función está **desactivada por defecto** para evitar cargos inesperados.

Para activarla, edita `.env`:

```ini
# Generación de imágenes externas (1 = activar, 0 = desactivar)
IMAGE_GENERATION_ENABLED=0

# Proveedor de imágenes
IMAGE_PROVIDER=pollinations

# Clave de API de Pollinations (opcional, funciona sin clave en modo gratuito)
POLLINATIONS_API_KEY=

# Modelo de imagen (flux es gratuito por defecto)
POLLINATIONS_IMAGE_MODEL=flux

# Máximo de imágenes externas por documento
MAX_EXTERNAL_IMAGES_PER_PDF=2

# Modo estricto gratuito (1 = solo modelos y endpoints gratuitos verificados)
STRICT_FREE_IMAGE_MODE=1
```

**Importante:**
- No se compran créditos ni se activan recargas automáticas.
- No se invocan modelos de pago.
- El máximo predeterminado es **2 imágenes por documento**.
- En ausencia de una modalidad gratuita verificada, la generación externa permanece desactivada por defecto.
- Las pruebas automatizadas **no realizan llamadas reales** a APIs externas.

## Cómo ejecutar la aplicación

Con el entorno virtual activado:

```powershell
python main.py
```

La aplicación se abrirá en una ventana de escritorio.

### Modo demostración

Para probar la interfaz y generar un PDF sin claves de API, activa el modo demostración en el archivo `.env`:

```ini
AULA_IA_DEMO=1
```

O marca la casilla "Modo demostración" en la interfaz. Los datos generados son de ejemplo y **no** provienen de un modelo de IA real.

## Cómo ejecutar las pruebas

Desde la carpeta raíz del proyecto:

```powershell
python -m unittest discover -s tests -v
```

Las pruebas no realizan llamadas reales a APIs externas. Usan sustitutos (mocks) y datos de demostración.

## Dónde se guardan los archivos

| Carpeta | Contenido |
|---------|-----------|
| `salida/` | PDF generados |
| `temporal/` | Datos de recuperación por trabajo (JSON original, validado, gráficos, imágenes externas, caché) |
| `assets/` | Logo institucional (copia del escudo del instituto) |

## Estructura de módulos

| Archivo | Responsabilidad |
|---------|-----------------|
| `main.py` | Inicia la aplicación Flet |
| `interfaz.py` | Construye y gestiona la UI |
| `generador_ia.py` | Coordina el flujo: IA, validación, gráficos, PDF, recuperación |
| `proveedores_ia.py` | Adaptadores para Gemini, OpenRouter y OmniRoute (opcional) |
| `plantillas.py` | Instrucciones pedagógicas y adaptaciones por disciplina |
| `modelos_datos.py` | Estructura del JSON esperado y ejemplos de demostración |
| `validador.py` | Validación estructural de respuestas JSON |
| `generador_pdf.py` | Construcción del PDF con ReportLab |
| `graficos.py` | Generación de gráficos y diagramas con Matplotlib (local) |
| `generador_imagenes.py` | Generación de imágenes externas mediante IA (Pollinations) |
| `generador_bloques.py` | Generación segmentada por bloques (plan, secciones, ejercicios, ensamblado) |
| `esquemas_bloques.py` | Esquemas de validación para cada tipo de bloque |
| `configuracion.py` | Lectura de variables de entorno y parámetros |

## Plantillas pedagógicas

La aplicación incluye una plantilla general con adaptaciones por disciplina:

1. **Matemática**: ejemplos paso a paso, ecuaciones, gráficos de funciones.
2. **Física y química**: leyes, fórmulas, diagramas de datos experimentales.
3. **Historia y geografía**: cronologías, análisis de causas y consecuencias, sin cálculos numéricos.
4. **Lengua y literatura**: análisis de textos, comprensión lectora, sin cálculos.
5. **Programación e informática**: ejemplos de código, diagramas de flujo.
6. **Recursos humanos, administración y economía**: casos de estudio, diagramas de procesos.
7. **Biología y ciencias naturales**: procesos naturales, diagramas de clasificación.
8. **Otras disciplinas**: plantilla genérica.

La clasificación del tema y la generación pedagógica ocurren en una **única solicitud** a la IA.

## Recursos visuales en el JSON

Cada recurso visual incluye:

- `id`: identificador único
- `type`: tipo (`python_chart`, `diagram`, `timeline`, `flowchart`, `table`, `ascii`, `external_image`)
- `title`, `educational_purpose`, `description`, `alt_text`, `caption`
- `placement`: sección, posición (portada, antes_bloque, despues_bloque, integrado, final_seccion), bloque de referencia, orden relativo
- `render_strategy`: estrategia de renderizado
- `data`: datos estructurados para gráficos y diagramas
- `status`: estado (pendiente, generado)
- `generated_asset_path`: ruta del archivo generado (nula inicialmente)
- `image_generation_prompt`: instrucción para futura API de generación de imágenes (sin claves)

Los recursos `external_image` pueden generarse mediante la API de imágenes configurada (Pollinations). El prompt (`image_generation_prompt`) se usa para generar el archivo y se inserta en el punto de inserción definido por `placement`. Si la generación falla o está desactivada, se muestra una tarjeta provisional con el título, descripción y propósito educativo.

## Generación de imágenes mediante IA (implementada)

La aplicación puede generar ilustraciones educativas externas mediante Pollinations, un proveedor con modalidad gratuita. El flujo es:

1. El JSON define qué recursos son de tipo `external_image` con su `image_generation_prompt`.
2. El programa selecciona hasta 2 recursos externos por documento (configurable).
3. Se verifica que el proveedor esté habilitado y configurado.
4. Se genera cada imagen, se valida que sea una imagen real y se guarda localmente.
5. La imagen se inserta en el PDF en la posición indicada por `placement`.

Si una imagen no puede generarse, se muestra una tarjeta provisional y el documento se completa sin ella.

## Seguridad y privacidad

- Las claves de API **no se guardan en el código** ni se muestran en la interfaz.
- Se leen exclusivamente del archivo `.env`.
- El uso gratuito de los proveedores puede estar sujeto a condiciones de tratamiento de datos distintas del uso pago. No envíes información personal innecesaria a los modelos.

## Limitaciones del MVP

- La generación de imágenes externas está desactivada por defecto (requiere configurar `IMAGE_GENERATION_ENABLED=1` en `.env`).
- El máximo predeterminado es 2 imágenes externas por documento.
- No hay sistema de usuarios, autenticación ni almacenamiento en la nube.
- La disponibilidad de proveedores gratuitos de imágenes no está garantizada (cuotas, límites de tasa).
- El modo demostración usa datos estáticos y no llama a ningún modelo de IA.
- Las pruebas automatizadas no realizan llamadas reales a APIs externas.
- La generación segmentada consume más solicitudes de IA que un único JSON grande, pero reduce el riesgo de truncamiento.

## Licencia

Uso educativo interno.
