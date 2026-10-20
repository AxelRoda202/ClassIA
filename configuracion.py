"""
Configuración de la aplicación Aula IA.

Lee variables de entorno desde un archivo .env y define los parámetros
del proyecto. Todas las claves de API se leen del entorno, nunca del código.
"""
import os
from pathlib import Path

# Carga de variables de entorno (opcional, requiere python-dotenv)
try:
    from dotenv import load_dotenv
    # Busca .env en la carpeta raíz del proyecto
    _env_path = Path(__file__).resolve().parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
except Exception:
    # Si no se puede cargar .env, se siguen usando las variables de entorno del sistema
    pass

# --- Rutas del proyecto ---
CARPETA_RAIZ = Path(__file__).resolve().parent
CARPETA_ASSETS = CARPETA_RAIZ / "assets"
CARPETA_SALIDA = CARPETA_RAIZ / "salida"
CARPETA_TEMPORAL = CARPETA_RAIZ / "temporal"
CARPETA_TESTS = CARPETA_RAIZ / "tests"

LOGO_POR_DEFECTO = CARPETA_ASSETS / "logo_instituto.jpg"  # Interfaz Flet
LOGO_PDF_POR_DEFECTO = CARPETA_ASSETS / "escudo_pdf.png"   # PDF generado

# --- Claves de API y modelos (desde variables de entorno) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")


def _modelos_openrouter_configurados() -> list:
    """
    Devuelve la lista ordenada de modelos de OpenRouter.

    `OPENROUTER_MODEL` es el modelo preferido y se intenta primero.
    `OPENROUTER_MODELS` aporta los candidatos restantes (separados por comas).
    Se mantiene `OPENROUTER_MODEL` por compatibilidad con configuraciones
    anteriores que sólo definían esa variable.
    """
    preferido = (OPENROUTER_MODEL or "").strip()
    crudo = os.getenv("OPENROUTER_MODELS", "")
    candidatos = [m.strip() for m in crudo.split(",") if m.strip()]
    orden = []
    if preferido:
        orden.append(preferido)
    for modelo in candidatos:
        if modelo not in orden:
            orden.append(modelo)
    return orden


# Candidatos gratuitos de OpenRouter, en orden de intento. Nunca se agregan
# modelos de pago automáticamente: la lista se configura en .env.
OPENROUTER_MODELS = _modelos_openrouter_configurados()

# Formato de salida estructurada para OpenRouter:
# - "json_schema": JSON Schema estricto por etapa (recomendado).
# - "json_object": sólo objeto JSON, con validación local de ClassIA.
OPENROUTER_RESPONSE_FORMAT = os.getenv(
    "OPENROUTER_RESPONSE_FORMAT", "json_schema"
).strip().lower()
if OPENROUTER_RESPONSE_FORMAT not in ("json_schema", "json_object"):
    OPENROUTER_RESPONSE_FORMAT = "json_schema"

# OmniRoute (opcional, sin valores inventados)
OMNIROUTE_BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "")
OMNIROUTE_API_KEY = os.getenv("OMNIROUTE_API_KEY", "")
OMNIROUTE_MODEL = os.getenv("OMNIROUTE_MODEL", "")

# Orden de proveedores (por defecto: Gemini primero, luego OpenRouter)
AI_PROVIDER_ORDER = os.getenv("AI_PROVIDER_ORDER", "gemini,openrouter").split(",")

# --- Límites de solicitud ---
def _entero_desde_entorno(nombre: str, por_defecto: int,
                          minimo: int = 1) -> int:
    """
    Lee un entero positivo de una variable de entorno.

    Si la variable no existe, está vacía, no es un número o queda por debajo
    del mínimo, se usa el valor por defecto. Así un .env mal escrito no
    desactiva los límites de seguridad.
    """
    crudo = os.getenv(nombre)
    if crudo is None or str(crudo).strip() == "":
        return por_defecto
    try:
        valor = int(str(crudo).strip())
    except (TypeError, ValueError):
        return por_defecto
    return valor if valor >= minimo else por_defecto


TIMEOUT_SEGUNDOS = _entero_desde_entorno("TIMEOUT_SEGUNDOS", 60, 1)
MAX_REINTENTOS = _entero_desde_entorno("MAX_REINTENTOS", 2, 1)
TOKEN_MAX_SALIDA = _entero_desde_entorno("TOKEN_MAX_SALIDA", 8192, 1)
# 20 minutos por defecto: los modelos gratuitos pueden tardar varios minutos
# por etapa. Se puede ajustar en .env con TIEMPO_MAX_GENERACION_SEGUNDOS.
# El límite protege las llamadas a IA; el ensamblado y el PDF locales se
# terminan aunque se haya alcanzado el límite (ver generador_bloques.generar).
TIEMPO_MAX_GENERACION_SEGUNDOS = _entero_desde_entorno(
    "TIEMPO_MAX_GENERACION_SEGUNDOS", 1200, 1
)

# --- Configuración de profundidad y extensión ---
PROFUNDIDAD_PAGINAS = {
    "breve": "4-5",
    "estandar": "6-8",
    "profunda": "9-12",
}

# --- Colores institucionales (extraídos del escudo) ---
COLOR_ROJO_INSTITUCIONAL = "#A52A2A"   # rojo oscuro del escudo
COLOR_AMARILLO_INSTITUCIONAL = "#FFD700"  # amarillo/dorado del escudo
COLOR_FONDO_OSCURO = "#2B2B2B"
COLOR_PANEL = "#3A3A3A"
COLOR_TEXTO_CLARO = "#FFFFFF"

# --- Modo demostración ---
MODO_DEMOSTRACION = os.getenv("AULA_IA_DEMO", "0") == "1"

# --- Generación de imágenes externas (IA) ---
IMAGE_GENERATION_ENABLED = os.getenv("IMAGE_GENERATION_ENABLED", "0") == "1"
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "pollinations")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "")  # Opcional, Pollinations funciona sin clave
POLLINATIONS_IMAGE_MODEL = os.getenv(
    "POLLINATIONS_IMAGE_MODEL", "black-forest-labs/flux.1-schnell"
)
MAX_EXTERNAL_IMAGES_PER_PDF = int(os.getenv("MAX_EXTERNAL_IMAGES_PER_PDF", "2"))
STRICT_FREE_IMAGE_MODE = os.getenv("STRICT_FREE_IMAGE_MODE", "1") == "1"


def proveedor_esta_configurado(nombre_proveedor: str) -> bool:
    """
    Devuelve True si el proveedor tiene las credenciales mínimas configuradas.
    """
    nombre_proveedor = nombre_proveedor.lower().strip()
    if nombre_proveedor == "gemini":
        return bool(GEMINI_API_KEY)
    if nombre_proveedor == "openrouter":
        return bool(OPENROUTER_API_KEY)
    if nombre_proveedor == "omniroute":
        return bool(OMNIROUTE_BASE_URL) and bool(OMNIROUTE_API_KEY)
    return False


def proveedores_habilitados() -> list:
    """
    Devuelve la lista de proveedores que están configurados, respetando el orden
    indicado en AI_PROVIDER_ORDER.
    """
    habilitados = []
    for nombre in AI_PROVIDER_ORDER:
        nombre = nombre.strip().lower()
        if nombre and proveedor_esta_configurado(nombre):
            habilitados.append(nombre)
    return habilitados


def asegurar_carpetas() -> None:
    """Crea las carpetas de salida y temporal si no existen."""
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    CARPETA_TEMPORAL.mkdir(parents=True, exist_ok=True)
