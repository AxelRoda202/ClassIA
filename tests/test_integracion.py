"""
Pruebas de integración: modo demostración y generación completa sin API.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from generador_ia import GeneradorIA
from configuracion import CARPETA_SALIDA


class TestIntegracionDemostracion(unittest.TestCase):
    """Pruebas de integración en modo demostración."""

    def test_generacion_completa_demo(self):
        """Generar PDF completo en modo demostración sin claves de API."""
        generador = GeneradorIA()
        resultado = generador.generar(
            tema="Funciones cuadráticas",
            disciplina="Matemática",
            nivel="Secundario",
            profundidad="estándar",
            cantidad_actividades=10,
            recursos_visuales=True,
            usar_demostracion=True,
        )

        self.assertTrue(resultado["exito"], f"Fallo: {resultado.get('mensaje')}")
        self.assertIsNotNone(resultado["ruta_pdf"])
        self.assertTrue(os.path.exists(resultado["ruta_pdf"]))

    def test_regenerar_pdf_desde_trabajo(self):
        """Recuperar PDF desde JSON guardado sin llamar a IA."""
        generador = GeneradorIA()
        resultado = generador.generar(
            tema="Revolución Francesa",
            disciplina="Historia y geografía",
            nivel="Secundario",
            profundidad="breve",
            cantidad_actividades=8,
            recursos_visuales=False,
            usar_demostracion=True,
        )

        self.assertTrue(resultado["exito"])
        trabajo_id = resultado["trabajo_id"]

        # Regenerar desde el trabajo guardado
        recuperacion = generador.regenerar_pdf_desde_trabajo(trabajo_id)
        self.assertTrue(recuperacion["exito"], f"Fallo recuperación: {recuperacion.get('mensaje')}")
        self.assertTrue(os.path.exists(recuperacion["ruta_pdf"]))


if __name__ == "__main__":
    unittest.main()
