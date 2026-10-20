"""
Pruebas de proveedores de IA con sustitutos (mocks).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import os
import importlib
from unittest.mock import patch, MagicMock

import configuracion
from proveedores_ia import (
    generar_contenido_educativo,
    ErrorIA,
    ErrorClaveInvalida,
    ErrorCuotaAgotada,
    ErrorRed,
    ErrorServidor,
    ErrorRespuestaIncompleta,
    clasificar_error,
)
from configuracion import proveedor_esta_configurado


class TestProveedores(unittest.TestCase):
    """Pruebas para los proveedores de IA con sustitutos."""

    def setUp(self):
        """Configura variables de entorno y recarga configuración."""
        os.environ["GEMINI_API_KEY"] = "test_gemini_key"
        os.environ["OPENROUTER_API_KEY"] = "test_openrouter_key"
        importlib.reload(configuracion)

    def tearDown(self):
        """Limpia variables de entorno."""
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        importlib.reload(configuracion)

    def test_gestion_error_proveedor_y_paso_al_siguiente(self):
        """11. Tratamiento de error de proveedor y paso al siguiente."""
        instruccion = "Instrucción de prueba"

        # Simular que Gemini falla y OpenRouter tiene éxito
        with patch("proveedores_ia.generar_con_gemini") as mock_gemini, \
             patch("proveedores_ia.generar_con_openrouter") as mock_openrouter:

            mock_gemini.side_effect = ErrorCuotaAgotada("Cuota agotada")
            mock_openrouter.return_value = '{"metadatos": {"titulo": "Test"}}'

            texto, proveedor = generar_contenido_educativo(
                instruccion, ["gemini", "openrouter"]
            )
            self.assertEqual(proveedor, "openrouter")
            self.assertIn("Test", texto)

    def test_todos_los_proveedores_fallan(self):
        """Cuando todos los proveedores fallan, se lanza ErrorIA."""
        with patch("proveedores_ia.generar_con_gemini") as mock_gemini, \
             patch("proveedores_ia.generar_con_openrouter") as mock_openrouter:

            mock_gemini.side_effect = ErrorClaveInvalida("Clave inválida")
            mock_openrouter.side_effect = ErrorCuotaAgotada("Cuota agotada")

            with self.assertRaises(ErrorIA):
                generar_contenido_educativo("instrucción", ["gemini", "openrouter"])

    def test_no_llamar_proveedor_sin_credenciales(self):
        """5. No llamar a proveedores sin credenciales."""
        # Verificar que proveedor_esta_configurado responde correctamente
        # según las credenciales disponibles en el entorno.
        # Si .env tiene claves configuradas, el proveedor estará configurado.
        # Si no, no estará. La prueba valida la lógica de la función.
        import configuracion as cfg

        # Parchear temporalmente las variables del módulo para simular
        # ausencia de credenciales, sin tocar os.environ ni .env.
        _gemini_backup = cfg.GEMINI_API_KEY
        _openrouter_backup = cfg.OPENROUTER_API_KEY
        cfg.GEMINI_API_KEY = ""
        cfg.OPENROUTER_API_KEY = ""
        try:
            self.assertFalse(cfg.proveedor_esta_configurado("gemini"))
            self.assertFalse(cfg.proveedor_esta_configurado("openrouter"))
        finally:
            cfg.GEMINI_API_KEY = _gemini_backup
            cfg.OPENROUTER_API_KEY = _openrouter_backup

    def test_clasificacion_errores(self):
        """7. Clasificación de errores."""
        self.assertIsInstance(clasificar_error(Exception("401 Unauthorized")), ErrorClaveInvalida)
        self.assertIsInstance(clasificar_error(Exception("429 Rate limit")), ErrorCuotaAgotada)
        self.assertIsInstance(clasificar_error(Exception("Connection timeout")), ErrorRed)
        self.assertIsInstance(clasificar_error(Exception("500 Internal Server Error")), ErrorServidor)
        self.assertIsInstance(clasificar_error(Exception("JSON parse error")), ErrorRespuestaIncompleta)


if __name__ == "__main__":
    unittest.main()
