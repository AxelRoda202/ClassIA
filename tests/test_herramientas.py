"""
Pruebas de las herramientas manuales de diagnóstico.

No realizan llamadas de red: sólo verifican las funciones puras de filtrado,
clasificación y validación de imágenes. Las funciones que usan requests se
ejecutan manualmente desde la línea de comandos.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from tools import diagnostico_openrouter_json as dor
from tools import probar_pollinations as pp


class RespuestaFalsa:
    """Doble mínimo de requests.Response para probar el diagnóstico."""

    def __init__(self, status_code=200, cuerpo=None):
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self):
        if self._cuerpo is None:
            raise ValueError("sin JSON")
        return self._cuerpo


class TestCatalogoOpenRouter(unittest.TestCase):
    """Filtrado del catálogo y clasificación de respuestas."""

    def test_filtra_gratuitos_con_structured_outputs(self):
        modelos = [
            {
                "id": "gratis-bueno",
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": ["structured_outputs", "response_format"],
            },
            {
                "id": "gratis-solo-objeto",
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": ["response_format"],
            },
            {
                "id": "pago",
                "pricing": {"prompt": "0.1", "completion": "0.2"},
                "supported_parameters": ["structured_outputs"],
            },
            {
                "id": "gratis-sin-json",
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": [],
            },
        ]
        filtrados = dor.filtrar_modelos_gratuitos(modelos)
        self.assertEqual([m["id"] for m in filtrados], ["gratis-bueno"])

    def test_formato_del_catalogo(self):
        modelos = [{
            "id": "modelo/free",
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["structured_outputs", "response_format"],
            "context_length": 1000,
            "top_provider": {"max_completion_tokens": 500},
        }]
        texto = dor.formatear_catalogo(modelos)
        self.assertIn("modelo/free", texto)
        self.assertIn("structured_outputs", texto)
        self.assertIn("json_schema", texto)

    def test_solicitud_de_prueba_es_estricta(self):
        solicitud = dor.construir_solicitud_prueba("modelo/free")
        self.assertEqual(solicitud["model"], "modelo/free")
        formato = solicitud["response_format"]
        self.assertEqual(formato["type"], "json_schema")
        self.assertTrue(formato["json_schema"]["strict"])
        self.assertEqual(
            solicitud["provider"], {"require_parameters": True}
        )

    def test_solicitud_limite_y_razonamiento(self):
        por_defecto = dor.construir_solicitud_prueba("modelo/free")
        self.assertEqual(por_defecto["max_tokens"], dor.MAX_TOKENS_PRUEBA)
        self.assertNotIn("reasoning", por_defecto)

        personalizada = dor.construir_solicitud_prueba(
            "modelo/free",
            max_tokens=300,
            desactivar_razonamiento=True,
        )
        self.assertEqual(personalizada["max_tokens"], 300)
        self.assertEqual(personalizada["reasoning"], {"enabled": False})
        # No se envían effort ni reasoning.max_tokens sin respaldo del catálogo.
        self.assertNotIn("effort", personalizada["reasoning"])
        self.assertNotIn("max_tokens", personalizada["reasoning"])

    def test_evaluar_respuesta_valida(self):
        cuerpo = {
            "model": "modelo-real",
            "choices": [{
                "message": {
                    "content": '{"ok": true, "campo": "prueba"}'
                },
                "finish_reason": "stop",
            }],
        }
        resultado = dor.evaluar_respuesta(200, cuerpo, "modelo-solicitado")
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["categoria"], "ok")
        self.assertEqual(resultado["modelo_real"], "modelo-real")
        self.assertEqual(resultado["datos"], {"ok": True, "campo": "prueba"})

    def test_evaluar_respuesta_vacia_y_razonamiento(self):
        cuerpo_vacio = {
            "model": "m",
            "choices": [{
                "message": {"content": ""},
                "finish_reason": "stop",
            }],
        }
        resultado = dor.evaluar_respuesta(200, cuerpo_vacio, "m")
        self.assertEqual(resultado["categoria"], "respuesta_vacia")

        cuerpo_razonamiento = {
            "model": "m",
            "choices": [{
                "message": {"content": "", "reasoning": "pensando"},
                "finish_reason": "stop",
            }],
        }
        resultado = dor.evaluar_respuesta(200, cuerpo_razonamiento, "m")
        self.assertEqual(resultado["categoria"], "solo_razonamiento")

    def test_evaluar_respuesta_json_invalido_y_esquema(self):
        cuerpo_json = {
            "model": "m",
            "choices": [{
                "message": {"content": "no es json"},
                "finish_reason": "stop",
            }],
        }
        resultado = dor.evaluar_respuesta(200, cuerpo_json, "m")
        self.assertEqual(resultado["categoria"], "json_invalido")

        cuerpo_esquema = {
            "model": "m",
            "choices": [{
                "message": {"content": '{"ok": false, "campo": "prueba"}'},
                "finish_reason": "stop",
            }],
        }
        resultado = dor.evaluar_respuesta(200, cuerpo_esquema, "m")
        self.assertEqual(resultado["categoria"], "esquema_invalido")

    def test_evaluar_errores_http(self):
        casos = {
            401: "auth",
            403: "auth",
            402: "limite",
            429: "limite",
            404: "no_soportado",
            400: "no_soportado",
            422: "no_soportado",
            500: "proveedor",
            503: "proveedor",
        }
        for status, categoria in casos.items():
            with self.subTest(status=status):
                resultado = dor.evaluar_respuesta(
                    status, {"error": {"message": "detalle"}}, "modelo"
                )
                self.assertEqual(resultado["categoria"], categoria)
                self.assertFalse(resultado["ok"])

    def test_validar_esquema_prueba(self):
        self.assertTrue(dor.validar_esquema_prueba(
            {"ok": True, "campo": "prueba"}
        )[0])
        self.assertFalse(dor.validar_esquema_prueba(
            {"ok": 1, "campo": "prueba"}
        )[0])
        self.assertFalse(dor.validar_esquema_prueba(
            {"ok": True, "campo": "otro"}
        )[0])
        self.assertFalse(dor.validar_esquema_prueba(
            {"ok": True, "campo": "prueba", "extra": 1}
        )[0])

    def test_evaluar_usage_de_razonamiento_agota_presupuesto(self):
        cuerpo = {
            "model": "dots-studio/dots-3-note-preview:free",
            "provider": "AtlasCloud",
            "usage": {
                "prompt_tokens": 30,
                "completion_tokens": 120,
                "total_tokens": 150,
                "completion_tokens_details": {"reasoning_tokens": 120},
            },
            "choices": [{
                "message": {
                    "content": "",
                    "reasoning": "razonamiento interno",
                },
                "finish_reason": "length",
                "native_finish_reason": "length",
            }],
        }
        resultado = dor.evaluar_respuesta(200, cuerpo, "modelo")
        self.assertEqual(resultado["categoria"], "truncada")
        self.assertEqual(resultado["proveedor"], "AtlasCloud")
        self.assertEqual(resultado["native_finish_reason"], "length")
        self.assertEqual(resultado["usage"]["reasoning_tokens"], 120)
        self.assertEqual(resultado["usage"]["visible_output_tokens"], 0)
        self.assertEqual(resultado["usage"]["completion_tokens"], 120)
        self.assertIn("razonamiento", resultado["detalle"].lower())

    def test_evaluar_usage_ausente_no_falla(self):
        cuerpo = {
            "model": "m",
            "choices": [{
                "message": {"content": '{"ok": true, "campo": "prueba"}'},
                "finish_reason": "stop",
            }],
        }
        resultado = dor.evaluar_respuesta(200, cuerpo, "m")
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["usage"], {})

    def test_probar_modelo_muestra_uso_sin_clave(self):
        cuerpo = {
            "model": "modelo-real",
            "provider": "AtlasCloud",
            "usage": {
                "prompt_tokens": 25,
                "completion_tokens": 64,
                "total_tokens": 89,
                "completion_tokens_details": {"reasoning_tokens": 64},
            },
            "choices": [{
                "message": {"content": "", "reasoning": "interno"},
                "finish_reason": "length",
                "native_finish_reason": "length",
            }],
        }
        respuesta = RespuestaFalsa(status_code=200, cuerpo=cuerpo)
        salida = io.StringIO()
        with redirect_stdout(salida):
            with patch(
                "requests.post", return_value=respuesta
            ) as mock_post:
                codigo = dor.probar_modelo(
                    "modelo/free",
                    api_key="clave-secreta-123",
                    max_tokens=64,
                    desactivar_razonamiento=True,
                )
        texto = salida.getvalue()
        self.assertEqual(codigo, 1)
        self.assertIn("Límite solicitado (max_tokens): 64", texto)
        self.assertIn(
            "Razonamiento solicitado: desactivado (reasoning.enabled=false)",
            texto,
        )
        self.assertIn("Razonamiento (reasoning_tokens): 64", texto)
        self.assertIn("Salida visible (completion - reasoning): 0", texto)
        self.assertIn("CAUSA PROBABLE", texto)
        self.assertNotIn("clave-secreta-123", texto)
        solicitud = mock_post.call_args.kwargs["json"]
        self.assertEqual(solicitud["max_tokens"], 64)
        self.assertEqual(solicitud["reasoning"], {"enabled": False})

    def test_probar_modelo_sin_clave_no_hace_solicitud(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = dor.probar_modelo("modelo/free", api_key="")
        self.assertEqual(codigo, 2)
        self.assertIn("No se realizó ninguna solicitud", salida.getvalue())


class TestPollinations(unittest.TestCase):
    """Búsqueda en catálogo y validación de imágenes."""

    @staticmethod
    def _png_valido(lado=32):
        buffer = io.BytesIO()
        Image.new("RGB", (lado, lado), "white").save(buffer, format="PNG")
        return buffer.getvalue()

    def test_busca_por_nombre_y_alias(self):
        modelos = [
            {"name": "publisher/modelo", "aliases": ["alias1", "alias2"]},
            {"name": "otro/modelo", "aliases": []},
        ]
        self.assertEqual(
            pp.buscar_modelo(modelos, "publisher/modelo")["name"],
            "publisher/modelo",
        )
        self.assertEqual(
            pp.buscar_modelo(modelos, "alias2")["name"],
            "publisher/modelo",
        )
        self.assertIsNone(pp.buscar_modelo(modelos, "inexistente"))

    def test_resumen_de_modelo(self):
        resumen = pp.resumir_modelo({
            "name": "publisher/modelo",
            "aliases": ["alias"],
            "pricing": {"completionImageTokens": "0.002"},
            "paid_only": False,
            "flat_rate": True,
            "per_user_rpm": 60,
            "supported_endpoints": ["/image/{prompt}"],
            "health": {"status": "healthy"},
        })
        self.assertEqual(resumen["id"], "publisher/modelo")
        self.assertEqual(resumen["pricing"]["completionImageTokens"], "0.002")
        self.assertIn("/image/{prompt}", resumen["supported_endpoints"])
        self.assertEqual(resumen["pricing_units"], {})

    def test_coste_por_megapixel_se_estima_para_el_tamano(self):
        resumen = pp.resumir_modelo({
            "name": "qwen/qwen-image-2.1",
            "pricing": {
                "currency": "pollen",
                "completionImageTokens": "0.00000002",
            },
            "pricing_units": {
                "completionImageTokens": {
                    "unit": "megapixel",
                    "quantity": 1000000,
                }
            },
            "paid_only": True,
            "flat_rate": True,
            "supported_endpoints": ["/image/{prompt}"],
        })
        detalle = pp._detalle_coste(resumen, 1024, 768)
        self.assertIn("0.020000 pollen/MP", detalle)
        self.assertIn("0.015729 pollen", detalle)
        self.assertIn("1024x768", detalle)

    def test_coste_por_tokens_no_se_inventa(self):
        resumen = pp.resumir_modelo({
            "name": "modelo/tokens",
            "pricing": {
                "currency": "pollen",
                "completionImageTokens": "0.00001425",
            },
            "paid_only": False,
            "flat_rate": False,
            "supported_endpoints": ["/image/{prompt}"],
        })
        detalle = pp._detalle_coste(resumen)
        self.assertIn("no se", detalle)
        self.assertIn("confirmar", detalle)

    def test_construir_url_imagen(self):
        url = pp.construir_url_imagen(
            "brújula y mapa", "black-forest-labs/flux.1-schnell",
            ancho=512, alto=512, seed=123,
        )
        self.assertIn("https://gen.pollinations.ai/image/", url)
        self.assertIn("br%C3%BAjula%20y%20mapa", url)
        self.assertIn("model=black-forest-labs/flux.1-schnell", url)
        self.assertIn("width=512", url)
        self.assertIn("height=512", url)
        self.assertIn("seed=123", url)
        self.assertNotIn("Authorization", url)

    def test_valida_png_real(self):
        contenido = self._png_valido()
        datos = pp.validar_imagen_bytes(contenido, "image/png")
        self.assertEqual(datos["formato"], "PNG")
        self.assertEqual(datos["ancho"], 32)
        self.assertEqual(datos["alto"], 32)
        self.assertEqual(datos["bytes"], len(contenido))

    def test_rechaza_html_json_y_svg(self):
        casos = [
            (b"<!doctype html>" + b"x" * 200, "image/png"),
            (b"<html>" + b"x" * 200, "image/png"),
            (b'{"error": "cuota"}', "application/json"),
            (b"<svg>" + b"x" * 200, "image/svg+xml"),
        ]
        for contenido, tipo in casos:
            with self.subTest(tipo=tipo):
                with self.assertRaises(pp.ErrorDiagnosticoImagen):
                    pp.validar_imagen_bytes(contenido, tipo)

    def test_rechaza_mime_no_imagen_y_tamano_pequeno(self):
        with self.assertRaises(pp.ErrorDiagnosticoImagen):
            pp.validar_imagen_bytes(b"x" * 200, "text/html")
        with self.assertRaises(pp.ErrorDiagnosticoImagen):
            pp.validar_imagen_bytes(b"\x89PNG", "image/png")

    def test_guardar_imagen_unica_no_sobrescribe(self):
        contenido = self._png_valido()
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            primera = pp.guardar_imagen_unica(carpeta, contenido, "PNG")
            segunda = pp.guardar_imagen_unica(carpeta, contenido, "PNG")
            self.assertNotEqual(primera, segunda)
            self.assertTrue(primera.exists())
            self.assertTrue(segunda.exists())
            self.assertEqual(primera.read_bytes(), contenido)
            self.assertEqual(segunda.read_bytes(), contenido)

    def test_generar_una_exige_confirmacion(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = pp.generar_una(confirmado=False)
        self.assertEqual(codigo, 2)
        self.assertIn("--confirmar-posible-consumo", salida.getvalue())

    def test_main_confirmacion_sin_generar_es_error(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = pp.main(["--confirmar-posible-consumo"])
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()
