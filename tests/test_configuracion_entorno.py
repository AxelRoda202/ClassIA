"""
Pruebas de lectura de límites desde variables de entorno.

No se modifica el .env real: se parchea `os.environ` y se prueba el helper
que usan los límites de configuración.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import configuracion


class TestEnteroDesdeEntorno(unittest.TestCase):
    """Lectura segura de enteros de configuración."""

    def test_lee_un_valor_valido(self):
        with patch.dict(os.environ, {"AULA_IA_TEST_ENTERO": "1200"}):
            self.assertEqual(
                configuracion._entero_desde_entorno(
                    "AULA_IA_TEST_ENTERO", 60
                ),
                1200,
            )

    def test_usa_el_defecto_si_no_existe(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                configuracion._entero_desde_entorno(
                    "AULA_IA_TEST_ENTERO", 1200
                ),
                1200,
            )

    def test_usa_el_defecto_si_esta_vacio(self):
        with patch.dict(os.environ, {"AULA_IA_TEST_ENTERO": "   "}):
            self.assertEqual(
                configuracion._entero_desde_entorno(
                    "AULA_IA_TEST_ENTERO", 1200
                ),
                1200,
            )

    def test_usa_el_defecto_si_no_es_numero(self):
        with patch.dict(os.environ, {"AULA_IA_TEST_ENTERO": "20min"}):
            self.assertEqual(
                configuracion._entero_desde_entorno(
                    "AULA_IA_TEST_ENTERO", 1200
                ),
                1200,
            )

    def test_usa_el_defecto_si_queda_bajo_el_minimo(self):
        with patch.dict(os.environ, {"AULA_IA_TEST_ENTERO": "0"}):
            self.assertEqual(
                configuracion._entero_desde_entorno(
                    "AULA_IA_TEST_ENTERO", 1200, minimo=60
                ),
                1200,
            )

    def test_acepta_el_minimo_exacto(self):
        with patch.dict(os.environ, {"AULA_IA_TEST_ENTERO": "60"}):
            self.assertEqual(
                configuracion._entero_desde_entorno(
                    "AULA_IA_TEST_ENTERO", 1200, minimo=60
                ),
                60,
            )


if __name__ == "__main__":
    unittest.main()
