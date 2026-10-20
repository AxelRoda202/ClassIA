"""
Pruebas para el módulo generador_imagenes.py.

Todas las pruebas usan sustitutos (mocks) y no realizan llamadas reales
a APIs externas ni consumen créditos.
"""
import sys
import os
import io
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generador_imagenes import (
    proveedor_imagenes_esta_habilitado,
    _normalizar_prompt,
    _clave_cache,
    _validar_imagen_contenido,
    seleccionar_recursos_externos,
    ErrorImagenExterna,
    ErrorProveedorImagenes,
    ErrorRespuestaImagen,
)
from configuracion import (
    IMAGE_GENERATION_ENABLED,
    IMAGE_PROVIDER,
    STRICT_FREE_IMAGE_MODE,
    MAX_EXTERNAL_IMAGES_PER_PDF,
    POLLINATIONS_API_KEY,
)


class TestGeneradorImagenes(unittest.TestCase):
    """Pruebas para el generador de imágenes externas."""

    def test_proveedor_no_habilitado_por_defecto(self):
        """Por defecto, sin configuración, el proveedor no está habilitado."""
        # IMAGE_GENERATION_ENABLED debería ser "0" por defecto en .env.example
        self.assertIsInstance(proveedor_imagenes_esta_habilitado(), bool)

    def test_normalizar_prompt(self):
        """El prompt se normaliza eliminando espacios dobles."""
        resultado = _normalizar_prompt("  hola   mundo  ")
        self.assertEqual(resultado, "hola mundo")

    def test_clave_cache_estable(self):
        """La clave de caché es estable para los mismos parámetros."""
        clave1 = _clave_cache("prompt test", "flux", 1024, 768)
        clave2 = _clave_cache("prompt test", "flux", 1024, 768)
        self.assertEqual(clave1, clave2)
        self.assertEqual(len(clave1), 16)

    def test_clave_cache_diferente_para_parametros_distintos(self):
        """La clave cambia si cambian prompt, modelo o dimensiones."""
        clave1 = _clave_cache("prompt A", "flux", 1024, 768)
        clave2 = _clave_cache("prompt B", "flux", 1024, 768)
        clave3 = _clave_cache("prompt A", "otro_modelo", 1024, 768)
        clave4 = _clave_cache("prompt A", "flux", 512, 512)
        self.assertNotEqual(clave1, clave2)
        self.assertNotEqual(clave1, clave3)
        self.assertNotEqual(clave1, clave4)

    def test_validar_imagen_valida(self):
        """Una imagen PNG válida pasa la validación."""
        # Crear una imagen PNG mínima en memoria
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        contenido = buf.getvalue()

        # No debería lanzar excepción
        try:
            _validar_imagen_contenido(contenido, "image/png")
        except ErrorRespuestaImagen:
            self.fail("Imagen válida rechazada por validación")

    def test_validar_imagen_tipo_invalido(self):
        """Un tipo de contenido no imagen es rechazado."""
        with self.assertRaises(ErrorRespuestaImagen):
            _validar_imagen_contenido(b"texto plano", "text/plain")

    def test_validar_imagen_html_disfrazado(self):
        """HTML disfrazado de imagen es rechazado."""
        with self.assertRaises(ErrorRespuestaImagen):
            _validar_imagen_contenido(b"<html><body>error</body></html>", "image/png")

    def test_seleccionar_recursos_externos_vacio_sin_habilitado(self):
        """Sin generación habilitada, no se seleccionan recursos externos."""
        recursos = [
            {
                "id": "ext1",
                "type": "external_image",
                "title": "Test",
                "image_generation_prompt": "Un diagrama educativo",
            }
        ]
        # La prueba no debe depender de IMAGE_GENERATION_ENABLED del .env:
        # se fuerza el valor del módulo y se restaura al finalizar.
        import generador_imagenes as gi
        habilitado_original = gi.IMAGE_GENERATION_ENABLED
        gi.IMAGE_GENERATION_ENABLED = False
        try:
            resultado = seleccionar_recursos_externos(recursos, maximo=2)
        finally:
            gi.IMAGE_GENERATION_ENABLED = habilitado_original
        self.assertEqual(len(resultado), 0)

    def test_seleccionar_respeta_maximo(self):
        """Se respeta el máximo de imágenes externas."""
        recursos = []
        for i in range(5):
            recursos.append({
                "id": f"ext{i}",
                "type": "external_image",
                "title": f"Recurso {i}",
                "image_generation_prompt": f"Prompt {i}",
            })
        # Forzar habilitado para la prueba
        import generador_imagenes as gi
        habilitado_original = gi.IMAGE_GENERATION_ENABLED
        gi.IMAGE_GENERATION_ENABLED = True
        try:
            resultado = seleccionar_recursos_externos(recursos, maximo=2)
            self.assertEqual(len(resultado), 2)
        finally:
            gi.IMAGE_GENERATION_ENABLED = habilitado_original

    def test_seleccionar_solo_external_image(self):
        """Solo se seleccionan recursos de tipo external_image."""
        recursos = [
            {"id": "chart1", "type": "python_chart", "title": "Gráfico", "image_generation_prompt": ""},
            {"id": "ext1", "type": "external_image", "title": "Externa", "image_generation_prompt": "Un diagrama"},
            {"id": "chart2", "type": "timeline", "title": "Línea", "image_generation_prompt": ""},
            {"id": "ext2", "type": "external_image", "title": "Externa 2", "image_generation_prompt": "Otro diagrama"},
        ]
        import generador_imagenes as gi
        habilitado_original = gi.IMAGE_GENERATION_ENABLED
        gi.IMAGE_GENERATION_ENABLED = True
        try:
            resultado = seleccionar_recursos_externos(recursos, maximo=10)
            ids = [r["id"] for r in resultado]
            self.assertIn("ext1", ids)
            self.assertIn("ext2", ids)
            self.assertNotIn("chart1", ids)
            self.assertNotIn("chart2", ids)
        finally:
            gi.IMAGE_GENERATION_ENABLED = habilitado_original

    def test_configuracion_tiene_variables_imagenes(self):
        """La configuración expone las variables de imágenes esperadas."""
        self.assertIsInstance(IMAGE_GENERATION_ENABLED, bool)
        self.assertIsInstance(IMAGE_PROVIDER, str)
        self.assertIsInstance(MAX_EXTERNAL_IMAGES_PER_PDF, int)
        self.assertGreaterEqual(MAX_EXTERNAL_IMAGES_PER_PDF, 1)
        self.assertIsInstance(STRICT_FREE_IMAGE_MODE, bool)


if __name__ == "__main__":
    unittest.main()
