"""
Pruebas de resiliencia ante errores del proveedor de IA (504 y similares).

Cubren el objetivo A (error 504: timeouts, reintentos acotados y fallback) y
el objetivo B (una respuesta fallida nunca se procesa como JSON).

No se realizan llamadas reales: el SDK y los proveedores están sustituidos
por dobles de prueba.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generador_bloques as gb
import proveedores_ia as pi
from proveedores_ia import (
    ErrorContenidoNoJson,
    ErrorIA,
    ErrorRespuestaIncompleta,
    ErrorServidor,
    clasificar_error,
    generar_contenido_educativo,
)


def _error_504() -> Exception:
    """Construye el mismo error que lanzó el SDK en producción."""
    from google.genai import errors as gerrors

    return gerrors.ServerError(
        504, {"error": {"message": "Deadline Exceeded", "status": "DEADLINE_EXCEEDED"}}
    )


class TestReintentosGemini(unittest.TestCase):
    """El cliente debe reintentar de forma acotada los 5xx transitorios."""

    def test_opciones_http_incluyen_reintentos_acotados(self):
        """1. HttpOptions trae timeout en ms y reintentos acotados."""
        opciones = pi._opciones_http_gemini()

        self.assertEqual(opciones.timeout, 60000)
        self.assertIsNotNone(opciones.retry_options)
        # attempts incluye el intento inicial; nunca debe ser ilimitado.
        self.assertEqual(opciones.retry_options.attempts, 3)
        self.assertIn(504, list(opciones.retry_options.http_status_codes))

    def test_cliente_gemini_recibe_reintentos(self):
        """2. El cliente de Gemini se crea con las HttpOptions y sus reintentos."""
        from google.genai import types

        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value.models.generate_content.return_value = (
                _respuesta_texto('{"ok": true}')
            )
            pi.generar_con_gemini("instrucción", api_key="clave-test")

            http_options = mock_client_cls.call_args.kwargs["http_options"]
            self.assertIsInstance(http_options, types.HttpOptions)
            self.assertEqual(http_options.retry_options.attempts, 3)


def _respuesta_texto(texto: str):
    from unittest.mock import MagicMock

    respuesta = MagicMock()
    respuesta.text = texto
    respuesta.candidates = []
    return respuesta


class TestClasificacion504(unittest.TestCase):
    """Un 504 debe reconocerse como error de servidor, nunca como JSON."""

    def test_servererror_504_es_error_de_servidor(self):
        """3. El ServerError(504) del SDK se clasifica como ErrorServidor."""
        error = clasificar_error(_error_504())

        self.assertIsInstance(error, ErrorServidor)
        self.assertNotIsInstance(error, ErrorRespuestaIncompleta)
        self.assertIn("504", str(error))

    def test_texto_504_es_error_de_servidor(self):
        """4. Un mensaje con 504/DEADLINE se clasifica como ErrorServidor."""
        self.assertIsInstance(
            clasificar_error(RuntimeError("504 DEADLINE_EXCEEDED")),
            ErrorServidor,
        )
        self.assertIsInstance(
            clasificar_error(RuntimeError("503 UNAVAILABLE")),
            ErrorServidor,
        )

    def test_errores_de_programacion_no_son_de_servidor(self):
        from proveedores_ia import ErrorIntegracion

        self.assertIsInstance(
            clasificar_error(TypeError("argumento inesperado")),
            ErrorIntegracion,
        )


class TestFallbackProveedores(unittest.TestCase):
    """El sistema debe poder recurrir al proveedor alternativo."""

    def test_504_en_gemini_usa_openrouter(self):
        """5. Un 504 de Gemini no aborta: se usa el proveedor alternativo."""
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorServidor("504 DEADLINE_EXCEEDED")), \
             patch.object(pi, "generar_con_openrouter",
                          return_value='{"ok": true}') as mock_or:
            texto, proveedor = generar_contenido_educativo(
                "instrucción", ["gemini", "openrouter"]
            )

        self.assertEqual(proveedor, "openrouter")
        self.assertEqual(texto, '{"ok": true}')
        mock_or.assert_called_once()

    def test_todos_los_proveedores_fallan_dan_error_claro(self):
        """6. Si todos fallan, el error es claro e identifica a cada proveedor."""
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorServidor("504 DEADLINE_EXCEEDED")), \
             patch.object(pi, "generar_con_openrouter",
                          side_effect=ErrorServidor("503 UNAVAILABLE")):
            with self.assertRaises(ErrorIA) as contexto:
                generar_contenido_educativo("instrucción", ["gemini", "openrouter"])

        mensaje = str(contexto.exception)
        self.assertIn("gemini", mensaje)
        self.assertIn("openrouter", mensaje)

    def test_un_error_de_integracion_no_prueba_alternativas(self):
        from proveedores_ia import ErrorIntegracion

        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorIntegracion("argumento no admitido")), \
             patch.object(pi, "generar_con_openrouter") as mock_or:
            with self.assertRaises(ErrorIntegracion):
                generar_contenido_educativo("instrucción", ["gemini", "openrouter"])

        mock_or.assert_not_called()


class TestClasificacionTextoRespuesta(unittest.TestCase):
    """Proveer la clasificación de vacío / no-JSON / JSON inválido."""

    def test_texto_vacio_es_respuesta_incompleta(self):
        """7. Una respuesta vacía se distingue como incompleta."""
        for vacio in ("", "   ", "\n\t "):
            with self.subTest(valor=repr(vacio)):
                with self.assertRaises(ErrorRespuestaIncompleta):
                    gb._preparar_texto_json(vacio, "Sección seccion1")

    def test_texto_no_json_es_contenido_no_json(self):
        """8. Un mensaje de seguridad no es JSON ni una respuesta vacía."""
        with self.assertRaises(ErrorContenidoNoJson) as contexto:
            gb._preparar_texto_json("User Safety: safe", "Sección seccion1")

        mensaje = str(contexto.exception)
        self.assertIn("Sección seccion1", mensaje)
        self.assertIn("User Safety: safe", mensaje)
        self.assertNotIsInstance(contexto.exception, ErrorRespuestaIncompleta)

    def test_se_quitan_cercas_markdown(self):
        """9. Un JSON envuelto en ```json se acepta tras quitar las cercas."""
        texto = '```json\n{"seccion_id": "s1"}\n```'
        self.assertEqual(
            gb._preparar_texto_json(texto, "Sección s1"),
            '{"seccion_id": "s1"}',
        )

    def test_json_valido_pasa_sin_cambios(self):
        """10. Un JSON válido se devuelve tal cual."""
        self.assertEqual(
            gb._preparar_texto_json('{"a": 1}', "etapa"),
            '{"a": 1}',
        )


class TestSeccionAnteRespuestasFallidas(unittest.TestCase):
    """La etapa de secciones frente a 504, vacíos y no-JSON."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _seccion_plan(self) -> dict:
        return {
            "id": "seccion1", "orden": 1, "titulo": "Sección 1",
            "conceptos_principales": ["Concepto"],
            "ejemplos_sugeridos": ["Ejemplo"],
            "recursos_visuales": [],
        }

    def _seccion_valida(self) -> dict:
        return {
            "seccion_id": "seccion1", "orden": 1, "titulo": "Sección 1",
            "bloques": [{"tipo": "paragraph", "texto": "Contenido real."}],
        }

    def _generador(self) -> gb.GeneradorBloques:
        generador = gb.GeneradorBloques()
        generador.trabajo_id = "seccion_prueba"
        generador.carpeta_trabajo = self.carpeta
        return generador

    def test_recupera_de_respuesta_no_json_en_el_primer_intento(self):
        """11. Un texto no-JSON se reintenta y la sección se recupera."""
        generador = self._generador()
        respuestas = [
            ("User Safety: safe", "openrouter"),
            (json.dumps(self._seccion_valida()), "gemini"),
        ]
        iterador = iter(respuestas)

        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=lambda *a, **k: next(iterador),
        ):
            seccion = generador._generar_una_seccion(
                self._seccion_plan(), "Tema", "Historia", "Secundario",
                "breve", "seccion_seccion1.json",
            )

        self.assertEqual(seccion["seccion_id"], "seccion1")
        # La respuesta cruda del intento fallido se conserva.
        crudo = (self.carpeta / "seccion_seccion1_crudo.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(crudo, "User Safety: safe")

    def test_respuesta_vacia_agota_reintentos_sin_marcar_exito(self):
        """12. Respuestas vacías agotan los reintentos y no generan sección."""
        generador = self._generador()
        with patch.object(
            gb, "generar_contenido_educativo",
            return_value=("", "gemini"),
        ) as mock_generar:
            with self.assertRaises(gb.ErrorBloque):
                generador._generar_una_seccion(
                    self._seccion_plan(), "Tema", "Historia", "Secundario",
                    "breve", "seccion_seccion1.json",
                )

        self.assertEqual(mock_generar.call_count, gb.MAX_REINTENTOS_BLOQUE)
        self.assertFalse((self.carpeta / "seccion_seccion1.json").exists())

    def test_seccion_sin_contenido_no_se_acepta(self):
        """13. Una sección con bloques vacíos no se acepta como válida."""
        generador = self._generador()
        vacia = {
            "seccion_id": "seccion1", "orden": 1, "titulo": "Sección 1",
            "bloques": [{"tipo": "paragraph", "texto": "   "}],
        }
        respuestas = [
            (json.dumps(vacia), "gemini"),
            (json.dumps(self._seccion_valida()), "gemini"),
        ]
        iterador = iter(respuestas)

        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=lambda *a, **k: next(iterador),
        ):
            seccion = generador._generar_una_seccion(
                self._seccion_plan(), "Tema", "Historia", "Secundario",
                "breve", "seccion_seccion1.json",
            )

        self.assertTrue(seccion["bloques"][0]["texto"])

    def test_plan_no_json_agota_reintentos_y_conserva_crudos(self):
        """14. Un plan no-JSON se reintenta y, si persiste, falla claro."""
        generador = self._generador()
        with patch.object(
            gb, "generar_contenido_educativo",
            return_value=("User Safety: safe", "openrouter"),
        ) as mock_generar:
            with self.assertRaises(gb.ErrorBloque):
                generador._generar_plan(
                    tema="Tema", disciplina="Historia", nivel="Secundario",
                    profundidad="breve", cantidad_actividades=5,
                    recursos_visuales=False,
                )

        self.assertEqual(mock_generar.call_count, gb.MAX_REINTENTOS_BLOQUE)
        self.assertTrue((self.carpeta / "plan_crudo.json").exists())
        self.assertTrue((self.carpeta / "plan_intento2_crudo.json").exists())
        self.assertFalse((self.carpeta / "plan.json").exists())


if __name__ == "__main__":
    unittest.main()
