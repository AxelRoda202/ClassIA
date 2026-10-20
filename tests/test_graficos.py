"""
Pruebas de generación de gráficos locales.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from pathlib import Path
from graficos import (
    generar_grafico_desde_recurso,
    _normalizar_series_grafico,
    _etiquetas_desde_titulo,
)
from configuracion import CARPETA_TEMPORAL


class TestGraficos(unittest.TestCase):
    """Pruebas para el generador de gráficos."""

    def setUp(self):
        self.carpeta_prueba = CARPETA_TEMPORAL / "test_graficos"
        self.carpeta_prueba.mkdir(parents=True, exist_ok=True)

    def test_grafico_lineas(self):
        """6. Generación de gráfico de líneas con datos de ejemplo."""
        recurso = {
            "id": "test_lineas",
            "type": "python_chart",
            "title": "Gráfico de prueba",
            "data": {
                "tipo_grafico": "lineas",
                "series": [
                    {"etiqueta": "Serie A", "valores": [1, 3, 2, 5, 4]},
                    {"etiqueta": "Serie B", "valores": [2, 1, 4, 3, 5]},
                ],
            },
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNotNone(ruta, "El gráfico de líneas debería generarse")
        self.assertTrue(Path(ruta).exists(), "El archivo del gráfico debería existir")

    def test_grafico_barras(self):
        """Generación de gráfico de barras."""
        recurso = {
            "id": "test_barras",
            "type": "python_chart",
            "title": "Gráfico de barras",
            "data": {
                "tipo_grafico": "barras",
                "series": [
                    {"etiqueta": "Grupo 1", "valores": [10, 20, 15]},
                ],
            },
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNotNone(ruta)
        self.assertTrue(Path(ruta).exists())

    def test_linea_tiempo(self):
        """Generación de línea de tiempo."""
        recurso = {
            "id": "test_timeline",
            "type": "timeline",
            "title": "Línea de tiempo",
            "data": {
                "eventos": [
                    {"anio": 1789, "evento": "Toma de la Bastilla"},
                    {"anio": 1792, "evento": "República"},
                ],
            },
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNotNone(ruta)
        self.assertTrue(Path(ruta).exists())

    def test_diagrama_flujo(self):
        """Generación de diagrama de flujo."""
        recurso = {
            "id": "test_flowchart",
            "type": "flowchart",
            "title": "Diagrama de flujo",
            "data": {
                "nodos": [
                    {"id": "n1", "texto": "Inicio"},
                    {"id": "n2", "texto": "Proceso"},
                    {"id": "n3", "texto": "Fin"},
                ],
                "relaciones": [
                    {"origen": "n1", "destino": "n2"},
                    {"origen": "n2", "destino": "n3"},
                ],
            },
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNotNone(ruta)
        self.assertTrue(Path(ruta).exists())

    def test_tabla_imagen(self):
        """Generación de imagen de tabla."""
        recurso = {
            "id": "test_tabla",
            "type": "table",
            "title": "Tabla de prueba",
            "data": {
                "cabeceras": ["Concepto", "Valor"],
                "filas": [["A", "10"], ["B", "20"]],
            },
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNotNone(ruta)
        self.assertTrue(Path(ruta).exists())

    def test_grafico_acepta_formato_name_y(self):
        """La IA puede devolver {"name": ..., "y": [...]}; no debe quedar vacío."""
        datos = {
            "x": [0, 1, 2, 3],
            "series": [
                {"name": "m = 1 kg", "y": [0, 1, 2, 3]},
                {"name": "m = 2 kg", "y": [0, 2, 4, 6]},
            ],
        }
        normalizadas = _normalizar_series_grafico(datos)

        self.assertEqual(len(normalizadas), 2)
        self.assertEqual(normalizadas[0][0], "m = 1 kg")
        self.assertEqual([y for _, y in normalizadas[0][1]], [0, 1, 2, 3])
        self.assertEqual([x for x, _ in normalizadas[1][1]], [0, 1, 2, 3])

        recurso = {
            "id": "test_name_y",
            "type": "python_chart",
            "title": "Fuerza versus aceleración",
            "data": datos,
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNotNone(ruta)
        self.assertTrue(Path(ruta).exists())

    def test_titulo_versus_define_los_ejes(self):
        """Un título "Fuerza versus Aceleración" orienta los ejes X/Y."""
        etiquetas = _etiquetas_desde_titulo(
            "Gráfica de Fuerza versus Aceleración"
        )
        self.assertEqual(etiquetas, ("Aceleración", "Fuerza"))

    def test_grafico_sin_series_no_genera_imagen_vacia(self):
        """Sin datos válidos no se genera un gráfico en blanco."""
        recurso = {
            "id": "test_vacio",
            "type": "python_chart",
            "title": "Sin datos",
            "data": {"series": []},
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNone(ruta)

    def test_tipo_no_soporte_devuelve_none(self):
        """Un tipo de recurso no soportado debe devolver None sin fallar."""
        recurso = {
            "id": "test_externo",
            "type": "external_image",
            "title": "Externo",
            "data": {},
        }
        ruta = generar_grafico_desde_recurso(recurso, self.carpeta_prueba)
        self.assertIsNone(ruta)


if __name__ == "__main__":
    unittest.main()
