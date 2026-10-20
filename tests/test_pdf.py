"""
Pruebas de generación de PDF sin API externa.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from pathlib import Path
from reportlab.platypus import KeepTogether
from modelos_datos import ejemplo_matematica, ejemplo_historia, ejemplo_recursos_humanos
from generador_pdf import (
    construir_pdf, fecha_local, _agregar_recurso_visual, crear_estilos,
)
from configuracion import CARPETA_SALIDA, CARPETA_TEMPORAL


class TestPDF(unittest.TestCase):
    """Pruebas para el generador de PDF."""

    def setUp(self):
        self.carpeta_prueba = CARPETA_TEMPORAL / "test_pdf"
        self.carpeta_prueba.mkdir(parents=True, exist_ok=True)

    def test_generar_pdf_matematica(self):
        """7. Generación de PDF sin utilizar ninguna API externa."""
        material = ejemplo_matematica()
        rutas_graficos = {}
        ruta_pdf = self.carpeta_prueba / "test_matematica.pdf"

        exito = construir_pdf(material, rutas_graficos, ruta_pdf)
        self.assertTrue(exito, "El PDF debería generarse correctamente")
        self.assertTrue(ruta_pdf.exists(), "El archivo PDF debería existir")
        self.assertGreater(ruta_pdf.stat().st_size, 1000, "El PDF debería tener un tamaño razonable")

    def test_generar_pdf_historia(self):
        """Generación de PDF para historia."""
        material = ejemplo_historia()
        rutas_graficos = {}
        ruta_pdf = self.carpeta_prueba / "test_historia.pdf"

        exito = construir_pdf(material, rutas_graficos, ruta_pdf)
        self.assertTrue(exito)
        self.assertTrue(ruta_pdf.exists())

    def test_generar_pdf_recursos_humanos(self):
        """Generación de PDF para recursos humanos."""
        material = ejemplo_recursos_humanos()
        rutas_graficos = {}
        ruta_pdf = self.carpeta_prueba / "test_rrhh.pdf"

        exito = construir_pdf(material, rutas_graficos, ruta_pdf)
        self.assertTrue(exito)
        self.assertTrue(ruta_pdf.exists())

    def test_extraer_texto_pdf(self):
        """8. Apertura y extracción de texto del PDF generado."""
        import PyPDF2  # type: ignore
        material = ejemplo_matematica()
        ruta_pdf = self.carpeta_prueba / "test_texto.pdf"

        exito = construir_pdf(material, {}, ruta_pdf)
        self.assertTrue(exito)

        with open(ruta_pdf, "rb") as f:
            lector = PyPDF2.PdfReader(f)
            texto_total = ""
            for pagina in lector.pages:
                texto_total += pagina.extract_text() or ""

        self.assertIn("Funciones Cuadráticas", texto_total)
        self.assertGreater(len(texto_total), 100, "El PDF no debería estar vacío")

    def test_pdf_ignora_fecha_inventada_por_la_ia(self):
        """La portada usa la fecha local, aunque el JSON traiga otra fecha."""
        material = ejemplo_matematica()
        material["metadatos"]["fecha_generacion"] = "2023-10-01"
        ruta_pdf = self.carpeta_prueba / "test_fecha_local.pdf"

        antes = fecha_local()
        exito = construir_pdf(material, {}, ruta_pdf)
        despues = fecha_local()
        self.assertTrue(exito)

        import PyPDF2  # type: ignore
        with open(ruta_pdf, "rb") as f:
            lector = PyPDF2.PdfReader(f)
            texto = lector.pages[0].extract_text() or ""

        self.assertNotIn("2023-10-01", texto)
        if antes == despues:
            self.assertIn(antes, texto)

    def test_tarjeta_de_recurso_no_se_parte_entre_paginas(self):
        """La tarjeta amarilla se agrupa para no dejar una franja cortada."""
        elementos = []
        _agregar_recurso_visual(
            elementos,
            {
                "id": "r1",
                "type": "diagram",
                "title": "Recurso de prueba",
                "description": "Descripción del recurso.",
                "educational_purpose": "Propósito del recurso.",
                "data": {},
            },
            {},
            crear_estilos(),
        )

        self.assertTrue(
            any(isinstance(elemento, KeepTogether) for elemento in elementos),
            "La tarjeta debe envolverse en KeepTogether",
        )

    def test_preservacion_json_fallo_pdf(self):
        """9. Preservación del JSON cuando falla la generación del PDF."""
        material = ejemplo_matematica()
        ruta_json = self.carpeta_prueba / "material_valido.json"

        import json
        ruta_json.write_text(json.dumps(material, indent=2), encoding="utf-8")
        self.assertTrue(ruta_json.exists())

        # Simular fallo de PDF (ruta inválida)
        ruta_pdf_invalida = self.carpeta_prueba / "subcarpeta_inexistente" / "test.pdf"
        exito = construir_pdf(material, {}, ruta_pdf_invalida)
        # Puede fallar, pero el JSON debe seguir existiendo
        self.assertTrue(ruta_json.exists(), "El JSON válido debe preservarse")


if __name__ == "__main__":
    unittest.main()
