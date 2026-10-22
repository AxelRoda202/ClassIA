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

# NVIDIA NIM: API alojada compatible con OpenAI.
# La clave y los modelos son independientes: si falta cualquiera de los dos,
# el proveedor se omite sin realizar solicitudes.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = (
    os.getenv("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1"
).strip().rstrip("/")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "").strip()
NVIDIA_RESPONSE_FORMAT = os.getenv(
    "NVIDIA_RESPONSE_FORMAT", "guided_json"
).strip().lower()
if NVIDIA_RESPONSE_FORMAT not in ("guided_json", "json_object", "text"):
    NVIDIA_RESPONSE_FORMAT = "guided_json"

# Groq: API compatible con OpenAI. Igual que NVIDIA, sólo se habilita cuando
# hay clave y al menos un modelo candidato configurado.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = (
    os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1"
).strip().rstrip("/")
GROQ_MODEL = os.getenv("GROQ_MODEL", "").strip()
GROQ_RESPONSE_FORMAT = os.getenv(
    "GROQ_RESPONSE_FORMAT", "json_object"
).strip().lower()
if GROQ_RESPONSE_FORMAT not in ("json_schema", "json_object", "text"):
    GROQ_RESPONSE_FORMAT = "json_object"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")


def _modelos_configurados(preferido: str, variable_lista: str) -> list:
    """
    Devuelve la lista ordenada de modelos de un proveedor.

    El modelo preferido se intenta primero. La variable de lista aporta los
    candidatos restantes (separados por comas). Se deduplica y se ignoran los
    valores vacíos. No se agregan modelos por defecto: cada candidato debe
    estar habilitado explícitamente en la configuración.
    """
    orden = []
    preferido = (preferido or "").strip()
    if preferido:
        orden.append(preferido)
    crudo = os.getenv(variable_lista, "")
    for modelo in (m.strip() for m in crudo.split(",")):
        if modelo and modelo not in orden:
            orden.append(modelo)
    return orden


def _modelos_openrouter_configurados() -> list:
    """Compatibilidad histórica para la lista de modelos de OpenRouter."""
    return _modelos_configurados(OPENROUTER_MODEL, "OPENROUTER_MODELS")


# Candidatos gratuitos de OpenRouter, en orden de intento. Nunca se agregan
# modelos de pago automáticamente: la lista se configura en .env.
OPENROUTER_MODELS = _modelos_openrouter_configurados()

# Los identificadores de NVIDIA y Groq son candidatos configurables, no una
# lista de modelos verificados. No se habilita ninguno por defecto.
NVIDIA_MODELS = _modelos_configurados(NVIDIA_MODEL, "NVIDIA_MODELS")
GROQ_MODELS = _modelos_configurados(GROQ_MODEL, "GROQ_MODELS")

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

def _normalizar_orden_proveedores(texto: str) -> list:
    """Convierte una lista separada por comas en nombres únicos y ordenados."""
    orden = []
    for nombre in (texto or "").split(","):
        nombre = nombre.strip().lower()
        if nombre and nombre not in orden:
            orden.append(nombre)
    return orden


# Orden de proveedores. Gemini primero; NVIDIA y Groq sólo se usan si están
# configurados; OpenRouter queda como respaldo final.
AI_PROVIDER_ORDER = _normalizar_orden_proveedores(
    os.getenv("AI_PROVIDER_ORDER", "gemini,nvidia,groq,openrouter")
)

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

    En NVIDIA y Groq no alcanza con la clave: también debe haber al menos un
    modelo candidato habilitado. Así una clave presente no dispara solicitudes
    a modelos que el usuario no eligió.
    """
    nombre_proveedor = nombre_proveedor.lower().strip()
    if nombre_proveedor == "gemini":
        return bool(GEMINI_API_KEY)
    if nombre_proveedor == "nvidia":
        return bool(NVIDIA_API_KEY) and bool(NVIDIA_MODELS)
    if nombre_proveedor == "groq":
        return bool(GROQ_API_KEY) and bool(GROQ_MODELS)
    if nombre_proveedor == "openrouter":
        return bool(OPENROUTER_API_KEY)
    if nombre_proveedor == "omniroute":
        return bool(OMNIROUTE_BASE_URL) and bool(OMNIROUTE_API_KEY)
    return False


def motivo_proveedor_no_configurado(nombre_proveedor: str) -> str:
    """
    Explica por qué un proveedor se omite, sin exponer credenciales.

    Se usa sólo para diagnóstico y mensajes de error.
    """
    nombre_proveedor = nombre_proveedor.lower().strip()
    if nombre_proveedor == "gemini":
        return "falta GEMINI_API_KEY"
    if nombre_proveedor == "nvidia":
        if not NVIDIA_API_KEY:
            return "falta NVIDIA_API_KEY"
        if not NVIDIA_MODELS:
            return "falta NVIDIA_MODEL o NVIDIA_MODELS"
        return "configurado"
    if nombre_proveedor == "groq":
        if not GROQ_API_KEY:
            return "falta GROQ_API_KEY"
        if not GROQ_MODELS:
            return "falta GROQ_MODEL o GROQ_MODELS"
        return "configurado"
    if nombre_proveedor == "openrouter":
        return "falta OPENROUTER_API_KEY" if not OPENROUTER_API_KEY else "configurado"
    if nombre_proveedor == "omniroute":
        if not OMNIROUTE_BASE_URL:
            return "falta OMNIROUTE_BASE_URL"
        if not OMNIROUTE_API_KEY:
            return "falta OMNIROUTE_API_KEY"
        return "configurado"
    return "proveedor desconocido"


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
