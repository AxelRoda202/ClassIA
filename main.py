"""
Punto de entrada de la aplicación Aula IA.
"""
import os

# Configurar OpenBLAS ANTES de importar cualquier biblioteca que pueda cargarlo
# (numpy, matplotlib, flet, etc.). Estas variables deben estar definidas antes
# de la primera inicialización de OpenBLAS para evitar errores de asignación
# de memoria en Windows ("Memory allocation still failed after 10 retries").
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_DEFAULT_NUM_THREADS", "1")

import flet as ft
from interfaz import main


def _configurar_logging(carpeta_log=None) -> None:
    """
    Configura el registro de eventos de la aplicación.

    Sin esto, Python sólo muestra advertencias y errores (y el cambio a un
    proveedor alternativo queda invisible). Se escribe en la consola y en
    `temporal/aula_ia.log` para poder diagnosticar problemas de cuota o red.
    El nivel se puede ajustar con la variable de entorno AULA_IA_LOG_LEVEL
    (por defecto INFO).
    """
    import logging
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    nivel = os.getenv("AULA_IA_LOG_LEVEL", "INFO").upper()
    formato = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    raiz = logging.getLogger()
    raiz.setLevel(getattr(logging, nivel, logging.INFO))

    # Librerías HTTP muy conversadoras: su traza no aporta al diagnóstico.
    for ruidoso in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)

    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz.addHandler(consola)

    try:
        destino = Path(carpeta_log) if carpeta_log else (
            Path(__file__).resolve().parent / "temporal"
        )
        destino.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(
            destino / "aula_ia.log",
            maxBytes=2_000_000,
            backupCount=2,
            encoding="utf-8",
        )
        archivo.setFormatter(formato)
        raiz.addHandler(archivo)
    except Exception:
        # Si no se puede escribir el archivo de log, la consola sigue activa.
        pass


def main_entry():
    _configurar_logging()
    ft.run(main)


if __name__ == "__main__":
    main_entry()
