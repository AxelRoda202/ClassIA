
"""
Generación de gráficos y diagramas locales con Matplotlib.

Todos los gráficos se interpretan a partir de datos estructurados del JSON.
No se ejecuta código generado por la IA.
"""
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend sin interfaz gráfica
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

from configuracion import CARPETA_TEMPORAL, COLOR_ROJO_INSTITUCIONAL, COLOR_AMARILLO_INSTITUCIONAL


def generar_grafico_desde_recurso(
    recurso: Dict[str, Any], carpeta_destino: Path
) -> Optional[str]:
    """
    Genera un archivo de imagen a partir de un recurso visual del JSON.

    Devuelve la ruta del archivo generado, o None si no se pudo construir.
    """
    tipo = recurso.get("type", "").strip().lower()
    datos = recurso.get("data", {}) or {}
    titulo = recurso.get("title", "Gráfico")

    try:
        if tipo == "python_chart":
            return _generar_grafico_numerico(datos, titulo, carpeta_destino, recurso.get("id"))
        elif tipo == "timeline":
            return _generar_linea_tiempo(datos, titulo, carpeta_destino, recurso.get("id"))
        elif tipo == "flowchart":
            return _generar_diagrama_flujo(datos, titulo, carpeta_destino, recurso.get("id"))
        elif tipo == "diagram":
            return _generar_esquema_conceptos(datos, titulo, carpeta_destino, recurso.get("id"))
        elif tipo == "table":
            return _generar_tabla_imagen(datos, titulo, carpeta_destino, recurso.get("id"))
        elif tipo == "ascii":
            return _generar_ascii_imagen(datos, titulo, carpeta_destino, recurso.get("id"))
        else:
            # Tipo no soportado localmente: se deja para futura API de imágenes
            return None
    except Exception as e:
        print(f"[graficos] Error generando '{tipo}': {e}")
        return None


def _nombre_archivo(recurso_id: str, prefijo: str) -> str:
    return f"{prefijo}_{recurso_id}.png"


def _guardar_figura(fig, carpeta_destino: Path, nombre_archivo: str) -> str:
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    ruta = carpeta_destino / nombre_archivo
    fig.savefig(ruta, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(ruta)


def _numero(valor: Any) -> Optional[float]:
    """Convierte un valor numérico sin aceptar booleanos ni NaN/infinitos."""
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if numero != numero or numero in (float("inf"), float("-inf")):
        return None
    return numero


def _valores_serie(serie: Any) -> List[Any]:
    """Acepta el formato canónico y las variantes que devuelve la IA."""
    if isinstance(serie, dict):
        for clave in ("valores", "y", "datos", "data"):
            if clave in serie:
                valores = serie.get(clave)
                return list(valores) if isinstance(valores, (list, tuple)) else []
        return []
    if isinstance(serie, (list, tuple)):
        return list(serie)
    return []


def _etiqueta_serie(serie: Any) -> str:
    if isinstance(serie, dict):
        for clave in ("etiqueta", "name", "label", "nombre"):
            if serie.get(clave):
                return str(serie[clave])
    return "serie"


def _eje_x(datos: Dict[str, Any], cantidad: int) -> List[Any]:
    """Devuelve el eje X explícito o los índices si no fue provisto."""
    for clave in ("x", "eje_x", "categorias"):
        valores = datos.get(clave)
        if isinstance(valores, (list, tuple)) and valores:
            eje = []
            for valor in valores[:cantidad]:
                numero = _numero(valor)
                eje.append(numero if numero is not None else str(valor))
            return eje
    return list(range(cantidad))


def _normalizar_series_grafico(
    datos: Dict[str, Any],
) -> List[Tuple[str, List[Tuple[Any, float]]]]:
    """
    Normaliza las series a pares (x, y).

    Los modelos a veces devuelven `{"name": ..., "y": [...]}` en lugar del
    formato documentado `{"etiqueta": ..., "valores": [...]}`. Ambos son
    válidos; antes el segundo formato producía un gráfico vacío.
    """
    series_raw = datos.get("series")
    if not isinstance(series_raw, list) or not series_raw:
        return []

    resultado: List[Tuple[str, List[Tuple[Any, float]]]] = []
    for serie in series_raw:
        valores = _valores_serie(serie)
        if not valores:
            continue
        eje_x = _eje_x(datos, len(valores))
        pares: List[Tuple[Any, float]] = []
        for indice, valor in enumerate(valores):
            numero = _numero(valor)
            if numero is None or indice >= len(eje_x):
                continue
            pares.append((eje_x[indice], numero))
        if pares:
            resultado.append((_etiqueta_serie(serie), pares))
    return resultado


def _etiquetas_desde_titulo(titulo: str) -> Optional[Tuple[str, str]]:
    """
    Deduce (x_label, y_label) de títulos como "Fuerza versus Aceleración".

    Es sólo un respaldo para planes antiguos que no incluían x_label/y_label.
    """
    texto = re.sub(
        r"^(gr[áa]fic[ao]|plot)\s+(de\s+)?", "", str(titulo or "").strip(),
        flags=re.IGNORECASE,
    )
    separador = re.compile(
        r"\s+(?:versus|vs\.?|frente\s+a)\s+", re.IGNORECASE
    )
    partes = separador.split(texto, maxsplit=1)
    if len(partes) == 2 and partes[0].strip() and partes[1].strip():
        return partes[1].strip(), partes[0].strip()
    return None


def _generar_grafico_numerico(
    datos: Dict[str, Any], titulo: str, carpeta_destino: Path, recurso_id: str
) -> Optional[str]:
    """Genera gráficos de líneas, barras o dispersión a partir de datos."""
    series = _normalizar_series_grafico(datos)
    if not series:
        return None

    tipo_grafico = str(
        datos.get("tipo_grafico")
        or datos.get("chart_type")
        or datos.get("tipo")
        or "lineas"
    ).lower()
    x_label = (
        datos.get("x_label") or datos.get("etiqueta_x")
        or datos.get("xlabel") or ""
    )
    y_label = (
        datos.get("y_label") or datos.get("etiqueta_y")
        or datos.get("ylabel") or ""
    )
    if not x_label or not y_label:
        desde_titulo = _etiquetas_desde_titulo(titulo)
        if desde_titulo:
            x_titulo, y_titulo = desde_titulo
            x_label = x_label or x_titulo
            y_label = y_label or y_titulo
    if not x_label:
        x_label = "Categoría" if tipo_grafico == "barras" else "Índice"
    if not y_label:
        y_label = "Valor"

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if tipo_grafico == "barras":
        for etiqueta, pares in series:
            ax.bar(
                [str(x) for x, _ in pares],
                [y for _, y in pares],
                label=etiqueta,
            )
    elif tipo_grafico == "dispersion":
        for etiqueta, pares in series:
            ax.scatter(
                [x for x, _ in pares],
                [y for _, y in pares],
                label=etiqueta,
            )
    else:  # lineas por defecto
        for etiqueta, pares in series:
            ax.plot(
                [x for x, _ in pares],
                [y for _, y in pares],
                marker="o",
                label=etiqueta,
            )

    ax.set_title(titulo, fontsize=12, color=COLOR_ROJO_INSTITUCIONAL)
    ax.set_xlabel(str(x_label))
    ax.set_ylabel(str(y_label))
    ax.grid(True, alpha=0.3)
    ax.legend()

    return _guardar_figura(fig, carpeta_destino, _nombre_archivo(recurso_id, "chart"))


def _generar_linea_tiempo(
    datos: Dict[str, Any], titulo: str, carpeta_destino: Path, recurso_id: str
) -> Optional[str]:
    """Genera una línea de tiempo con eventos."""
    eventos = datos.get("eventos", [])
    if not eventos:
        return None

    fig, ax = plt.subplots(figsize=(9, 3.5))
    años = [e.get("anio", 0) for e in eventos]
    descripciones = [e.get("evento", "") for e in eventos]

    y = range(len(eventos))
    ax.scatter(años, y, color=COLOR_ROJO_INSTITUCIONAL, zorder=3)
    ax.plot(años, y, color=COLOR_AMARILLO_INSTITUCIONAL, alpha=0.6, zorder=2)

    for i, (anio, desc) in enumerate(zip(años, descripciones)):
        ax.annotate(
            f"{anio}: {desc}",
            xy=(anio, i),
            xytext=(10, 0),
            textcoords="offset points",
            fontsize=9,
            va="center",
        )

    ax.set_yticks([])
    ax.set_title(titulo, fontsize=12, color=COLOR_ROJO_INSTITUCIONAL)
    ax.set_xlabel("Año")
    ax.grid(axis="x", alpha=0.3)

    return _guardar_figura(fig, carpeta_destino, _nombre_archivo(recurso_id, "timeline"))


def _generar_diagrama_flujo(
    datos: Dict[str, Any], titulo: str, carpeta_destino: Path, recurso_id: str
) -> Optional[str]:
    """Genera un diagrama de flujo simple a partir de nodos y relaciones."""
    nodos = datos.get("nodos", [])
    relaciones = datos.get("relaciones", [])
    if not nodos:
        return None

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    posiciones = {}
    n = len(nodos)
    for i, nodo in enumerate(nodos):
        x = 5
        y = 9 - (i * (8 / max(n - 1, 1)))
        posiciones[nodo["id"]] = (x, y)
        caja = FancyBboxPatch(
            (x - 2.2, y - 0.5),
            4.4,
            1,
            boxstyle="round,pad=0.1",
            facecolor="#FDFDFD",
            edgecolor=COLOR_ROJO_INSTITUCIONAL,
            linewidth=1.5,
        )
        ax.add_patch(caja)
        ax.text(
            x, y, nodo["texto"],
            ha="center", va="center", fontsize=9, wrap=True
        )

    for rel in relaciones:
        origen = posiciones.get(rel["origen"])
        destino = posiciones.get(rel["destino"])
        if origen and destino:
            flecha = FancyArrowPatch(
                (origen[0], origen[1] - 0.5),
                (destino[0], destino[1] + 0.5),
                arrowstyle="->",
                color=COLOR_AMARILLO_INSTITUCIONAL,
                linewidth=1.5,
                mutation_scale=15,
            )
            ax.add_patch(flecha)

    ax.set_title(titulo, fontsize=12, color=COLOR_ROJO_INSTITUCIONAL)

    return _guardar_figura(fig, carpeta_destino, _nombre_archivo(recurso_id, "flowchart"))


def _generar_esquema_conceptos(
    datos: Dict[str, Any], titulo: str, carpeta_destino: Path, recurso_id: str
) -> Optional[str]:
    """Genera un esquema de conceptos simple (nodos centrados)."""
    return _generar_diagrama_flujo(datos, titulo, carpeta_destino, recurso_id)


def _generar_tabla_imagen(
    datos: Dict[str, Any], titulo: str, carpeta_destino: Path, recurso_id: str
) -> Optional[str]:
    """Genera una imagen de tabla a partir de filas y columnas."""
    cabeceras = datos.get("cabeceras", [])
    filas = datos.get("filas", [])
    if not cabeceras or not filas:
        return None

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.axis("off")

    tabla = ax.table(
        cellText=filas,
        colLabels=cabeceras,
        loc="center",
        cellLoc="center",
    )
    tabla.auto_set_font_size(False)
    tabla.set_fontsize(9)
    tabla.scale(1, 1.5)

    for i in range(len(cabeceras)):
        tabla[(0, i)].set_facecolor(COLOR_ROJO_INSTITUCIONAL)
        tabla[(0, i)].set_text_props(color="white", weight="bold")

    ax.set_title(titulo, fontsize=12, color=COLOR_ROJO_INSTITUCIONAL)

    return _guardar_figura(fig, carpeta_destino, _nombre_archivo(recurso_id, "table"))


def _generar_ascii_imagen(
    datos: Dict[str, Any], titulo: str, carpeta_destino: Path, recurso_id: str
) -> Optional[str]:
    """Genera una imagen con texto ASCII/monospacio."""
    contenido = datos.get("contenido", "")
    if not contenido:
        return None

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.axis("off")
    ax.text(
        0.05, 0.95, contenido,
        fontfamily="monospace", fontsize=9,
        va="top", ha="left",
        wrap=True,
    )
    ax.set_title(titulo, fontsize=12, color=COLOR_ROJO_INSTITUCIONAL)

    return _guardar_figura(fig, carpeta_destino, _nombre_archivo(recurso_id, "ascii"))
