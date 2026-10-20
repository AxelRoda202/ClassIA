
"""
Generación de gráficos y diagramas locales con Matplotlib.

Todos los gráficos se interpretan a partir de datos estructurados del JSON.
No se ejecuta código generado por la IA.
"""
import os
from typing import Any, Dict, List, Optional
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


def _generar_grafico_numerico(
    datos: Dict[str, Any], titulo: str, carpeta_destino: Path, recurso_id: str
) -> Optional[str]:
    """Genera gráficos de líneas, barras o dispersión a partir de datos."""
    series = datos.get("series", [])
    if not series:
        return None

    tipo_grafico = datos.get("tipo_grafico", "lineas").lower()

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if tipo_grafico == "barras":
        x = range(len(series[0].get("valores", [])))
        for s in series:
            valores = s.get("valores", [])
            ax.bar([str(i) for i in x], valores, label=s.get("etiqueta", "serie"))
        ax.set_xlabel("Categoría")
    elif tipo_grafico == "dispersion":
        for s in series:
            valores = s.get("valores", [])
            ax.scatter(range(len(valores)), valores, label=s.get("etiqueta", "serie"))
        ax.set_xlabel("Índice")
    else:  # lineas por defecto
        for s in series:
            valores = s.get("valores", [])
            ax.plot(valores, marker="o", label=s.get("etiqueta", "serie"))
        ax.set_xlabel("Índice")

    ax.set_title(titulo, fontsize=12, color=COLOR_ROJO_INSTITUCIONAL)
    ax.set_ylabel("Valor")
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
