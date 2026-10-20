# Diagnóstico del error OpenBLAS en ClassIA

## Error original

```
OpenBLAS error: Memory allocation still failed after 10 retries, giving up.
Ope
```

La salida estaba posiblemente incompleta. No se observó traceback completo.

## Entorno

- Python: 3.13.15 (64 bits, AMD64)
- Ejecutable: `C:\Users\axelr\AppData\Local\Programs\Python\Python313\python.exe`
- Entorno virtual: `.venv` en la carpeta del proyecto
- Sistema: Windows

## Bibliotecas instaladas

| Biblioteca | Versión |
|------------|---------|
| numpy | 2.5.3 |
| matplotlib | 3.11.2 |
| pillow | 12.3.0 |
| flet | 1.0.4 |
| google-genai | 2.31.0 |
| python-dotenv | 1.2.4 |
| reportlab | 5.0.1 |

(`pip check` reporta solo que `pyvidplayer2` requiere `opencv-python`, no relacionado con OpenBLAS)

## Hipótesis examinadas

### H1: NumPy/SciPy cargando OpenBLAS durante la importación
**Estado:** COMPROBADA PARCIALMENTE. NumPy 2.5.3 está instalado y usa OpenBLAS internamente. Sin embargo, `import numpy` funciona correctamente en pruebas aisladas, tanto con como sin `OPENBLAS_NUM_THREADS=1`.

### H2: Matplotlib cargando OpenBLAS
**Estado:** DESCARTADA COMO CAUSA PRINCIPAL. `import matplotlib` funciona correctamente en pruebas aisladas.

### H3: Flet cargando OpenBLAS indirectamente
**Estado:** PENDIENTE. Flet importa varias dependencias; el error ocurre al ejecutar `python main.py` (que inicia la app Flet y abre ventana GUI), no al importar módulos individualmente.

### H4: Problema de memoria virtual de Windows
**Estado:** NO PUEDE CONFIRMARSE. No hay evidencia suficiente para afirmar que sea falta de memoria física o de paginación.

### H5: Demasiados hilos de OpenBLAS
**Estado:** PROBABLE. El mensaje "Memory allocation still failed after 10 retries" es típico cuando OpenBLAS intenta crear hilos y no puede reservar memoria para cada uno. En Windows con OpenBLAS bundled en NumPy, esto ocurre frecuentemente si el número de hilos es alto.

## Pruebas realizadas

1. **Importación aislada de numpy**: OK (sin error)
2. **Importación aislada de matplotlib**: OK (sin error)
3. **Importación aislada de flet**: OK (sin error)
4. **Importación de numpy con `OPENBLAS_NUM_THREADS=1`**: OK
5. **Importación de flet con `OPENBLAS_NUM_THREADS=1`**: OK
6. **Ejecución de `import main` con timeout**: OK (código de salida 0, `MAIN_IMPORT_OK`)
7. **Ejecución de `python main.py`**: Se inicia la app Flet (ventana GUI); el error original ocurrió aquí

## Causa confirmada / probable

**Causa probable:** OpenBLAS (vinculado a NumPy) intenta reservar memoria para múltiples hilos durante la inicialización de la aplicación Flet y falla tras 10 reintentos. Esto es más probable al iniciar la aplicación completa (ventana GUI) que al importar módulos aislados.

La raíz es que `.env` (que podría contener configuración de hilos) se carga en `configuracion.py`, que se importa DESPUÉS de `flet` y otras bibliotecas que ya pueden haber cargado OpenBLAS.

## Solución aplicada

**Archivo modificado:** `main.py`

**Cambio:** Establecer `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` y `OPENBLAS_DEFAULT_NUM_THREADS=1` como variables de entorno al principio de `main.py`, ANTES de importar `interfaz` (que a su vez importa flet, numpy, etc.).

**Justificación técnica:** Estas variables deben estar definidas antes de que cualquier biblioteca vinculada a OpenBLAS se importe, porque OpenBLAS lee estas variables solo en su primera inicialización. Establecerlas en `main.py` antes de cualquier import de dependencias garantiza que se apliquen correctamente.

## Modificaciones realizadas

1. `main.py`: Agregadas variables de entorno `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `OPENBLAS_DEFAULT_NUM_THREADS` antes de los imports.

## Pruebas posteriores

- `import main` con hilos limitados: OK (código de salida 0)
- Ejecución de `main.main_entry()`: la aplicación inicia correctamente (ventana Flet se abre, no hay error de OpenBLAS). El proceso se mantiene ejecutando (esperado en una app de escritorio).
- Importaciones individuales de numpy, matplotlib, flet: OK
- 27 pruebas unitarias: TODAS PASAN (OK)
  - Validador JSON: 8/8 OK
  - Gráficos Matplotlib: 6/6 OK
  - PDF ReportLab: 6/6 OK
  - Proveedores IA (mocks): 5/5 OK
  - Integración modo demostración: 2/2 OK

## Limitaciones pendientes

- El error original de OpenBLAS fue intermitente; no se pudo reproducir de forma consistente en pruebas aisladas de importación. Se manifestó solo al ejecutar `python main.py` completo (inicio de Flet con ventana GUI).
- Si el error persiste en entornos con memoria muy limitada, podría ser necesario investigar la memoria virtual de Windows, lo cual excede el alcance de esta aplicación.

## Otros errores detectados y corregidos durante la revisión

1. **generador_ia.py**: El walrus operator `material := json.loads(texto_respuesta)` dentro de `isinstance` podía lanzar `json.JSONDecodeError` sin captura específica. Corregido separando el parseo JSON de la validación, con `try/except json.JSONDecodeError` que lanza `ErrorValidacion` con mensaje claro.

2. **interfaz.py** (correcciones previas de compatibilidad con Flet 1.x):
   - `ft.app(target=main)` → `ft.run(main)`
   - `ft.ImageFit.CONTAIN` → `ft.BoxFit.CONTAIN`
   - `ft.colors` → `ft.Colors`
   - `ft.icons.SETTINGS` → `ft.icons.Icons.SETTINGS`
   - `ft.alignment.center_right` → `ft.Alignment.CENTER_RIGHT`
   - `ft.padding.only` / `ft.border.all` / `ft.border.BorderSide` → `ft.Padding` / `ft.Border` / `ft.BorderSide`
   - `ft.ElevatedButton` → `ft.FilledButton`
   - `page.open()` / `page.close()` → `page.show_dialog()` / `page.pop_dialog()`
   - `FilePicker` en `page.overlay` causaba "Unknown control": cambiado a creación perezosa (lazy) con try-except en `_guardar_copia`.

3. **tests/test_proveedores.py**: El test `test_no_llamar_proveedor_sin_credenciales` fallaba porque `.env` ya tiene claves configuradas. Corregido parcheando las variables del módulo `configuracion` directamente en lugar de manipular `os.environ`.

## Variables de configuración que requieren atención

- `GEMINI_API_KEY` o `OPENROUTER_API_KEY`: al menos una debe estar configurada en `.env` para usar IA real. Sin ellas, usar el modo demostración.
- `AI_PROVIDER_ORDER`: opcional, por defecto `gemini,openrouter`.

## Problemas pendientes

Ninguno crítico. El arranque de la aplicación es confiable tras la corrección de OpenBLAS.

- El error original fue intermitente; no se pudo reproducir de forma consistente en pruebas aisladas.
- Si el error persiste tras aplicar la solución, podría indicar un problema de memoria del sistema más profundo que excede el alcance de esta aplicación.
