"""
Pruebas del cambio automático de proveedor cuando se agota la cuota.

Verifican que:
- Un 429 diario de Gemini no detiene la generación: se continúa con OpenRouter.
- El proveedor con cuota diaria agotada se recuerda y no se reintenta en cada
  bloque de la misma ejecución.
- Los errores de OpenRouter (402, 404, 429, 401) dan mensajes accionables.

No se realizan llamadas reales: los proveedores están sustituidos por dobles.
"""
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generador_bloques as gb
import proveedores_ia as pi
from proveedores_ia import (
    ErrorClaveInvalida,
    ErrorCuotaAgotada,
    ErrorIA,
    cuota_es_persistente,
    generar_contenido_educativo,
    generar_con_openrouter,
)

# Mensaje real (recortado) del 429 diario de Gemini.
MENSAJE_GEMINI_DIARIO = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded "
    "your current quota... * Quota exceeded for metric: generativelanguage."
    "googleapis.com/generate_content_free_tier_requests, limit: 20, model: "
    "gemini-3.8-flash. Please retry in 18h9m30.898624818s.', 'status': "
    "'RESOURCE_EXHAUSTED', 'details': [{'quotaId': "
    "'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}}"
)


class TestDeteccionCuotaPersistente(unittest.TestCase):
    """Distinguir cuota diaria (persistente) de un límite por minuto."""

    def test_mensaje_diario_real_es_persistente(self):
        """1. El mensaje real (18h / PerDay) se detecta como persistente."""
        self.assertTrue(cuota_es_persistente(MENSAJE_GEMINI_DIARIO))

    def test_limite_por_minuto_no_es_persistente(self):
        """2. Un 429 de segundos no se considera diario."""
        self.assertFalse(cuota_es_persistente("429 rate limit, retry in 30s"))
        self.assertFalse(cuota_es_persistente("429 sin más detalle"))


class TestFallbackConMemoria(unittest.TestCase):
    """El fallback debe continuar con el otro proveedor y recordar el agotado."""

    def test_cuota_diaria_de_gemini_usa_openrouter(self):
        """3. Un 429 diario de Gemini continúa con OpenRouter."""
        agotados = set()
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorCuotaAgotada(MENSAJE_GEMINI_DIARIO)), \
             patch.object(pi, "generar_con_openrouter",
                          return_value='{"ejercicios": []}'):
            texto, proveedor = generar_contenido_educativo(
                "instrucción", ["gemini", "openrouter"], agotados
            )

        self.assertEqual(proveedor, "openrouter")
        self.assertIn("gemini", agotados)

    def test_proveedor_agotado_no_se_reintenta(self):
        """4. Tras agotarse, Gemini no se vuelve a llamar en el mismo run."""
        agotados = set()
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorCuotaAgotada(MENSAJE_GEMINI_DIARIO)) as mock_gemini, \
             patch.object(pi, "generar_con_openrouter",
                          return_value='{"ok": true}'):
            for _ in range(3):
                _, proveedor = generar_contenido_educativo(
                    "instrucción", ["gemini", "openrouter"], agotados
                )
                self.assertEqual(proveedor, "openrouter")

        # Sólo se intentó Gemini la primera vez.
        self.assertEqual(mock_gemini.call_count, 1)

    def test_todos_agotados_da_error_claro(self):
        """5. Si todos los proveedores están agotados, el error lo explica."""
        agotados = {"gemini", "openrouter"}
        with self.assertRaises(ErrorIA) as contexto:
            generar_contenido_educativo(
                "instrucción", ["gemini", "openrouter"], agotados
            )

        mensaje = str(contexto.exception)
        self.assertIn("omitido", mensaje)
        self.assertIn("gemini", mensaje)
        self.assertIn("openrouter", mensaje)


class TestErroresOpenRouter(unittest.TestCase):
    """Mensajes accionables para los distintos errores de OpenRouter."""

    def _respuesta(self, status, body):
        respuesta = MagicMock()
        respuesta.status_code = status
        respuesta.ok = 200 <= status < 300
        respuesta.text = json.dumps(body)
        respuesta.json.return_value = body
        return respuesta

    def _generar(self, status, body):
        with patch("requests.post", return_value=self._respuesta(status, body)):
            return generar_con_openrouter("instrucción", api_key="clave-test")

    def test_402_falta_de_credito(self):
        """6. Un 402 explica que falta crédito o hay que usar ':free'."""
        with self.assertRaises(ErrorIA) as contexto:
            self._generar(402, {"error": {"message": "Insufficient credits"}})
        self.assertIn("crédito", str(contexto.exception))

    def test_404_modelo_inexistente(self):
        """7. Un 404 indica revisar OPENROUTER_MODEL."""
        with self.assertRaises(ErrorIA) as contexto:
            self._generar(404, {"error": {"message": "No endpoints found"}})
        self.assertIn("OPENROUTER_MODEL", str(contexto.exception))

    def test_429_es_cuota_agotada(self):
        """8. Un 429 de OpenRouter se clasifica como cuota agotada."""
        with self.assertRaises(ErrorCuotaAgotada):
            self._generar(429, {"error": {"message": "Rate limit exceeded"}})

    def test_401_es_clave_invalida(self):
        """9. Un 401 se clasifica como clave inválida."""
        with self.assertRaises(ErrorClaveInvalida):
            self._generar(401, {"error": {"message": "Invalid key"}})

    def test_error_en_cuerpo_con_200_se_detecta(self):
        """10. Un error reportado en el cuerpo se detecta igual."""
        with self.assertRaises(ErrorIA):
            self._generar(200, {"error": {"message": "No disponible"}})


class TestIntegracionSkipGemini(unittest.TestCase):
    """En un flujo completo, Gemini se intenta una sola vez si se agota."""

    PLAN = {
        "titulo": "Plan de prueba",
        "disciplina": "Historia",
        "nivel": "Secundario",
        "profundidad": "breve",
        "objetivos_aprendizaje": ["Objetivo"],
        "conocimientos_previos": ["Conocimiento"],
        "secciones": [
            {"id": "s1", "orden": 1, "titulo": "Sección 1",
             "conceptos_principales": ["c"], "ejemplos_sugeridos": ["e"],
             "recursos_visuales": []},
        ],
        "recursos_visuales_planificados": [],
    }

    COMPONENTES = {
        "introduccion": "Introducción.",
        "resumen_final": "Resumen.",
        "glosario": [{"termino": "T", "definicion": "D"}],
        "metadatos": {"titulo": "T", "tema": "T", "disciplina": "Historia",
                      "nivel": "Secundario"},
    }

    @staticmethod
    def _ejercicio(numero, dificultad):
        return {"id": f"e{numero}", "dificultad": dificultad, "tipo": "calculo",
                "consigna": "C", "solucion": "S", "respuesta_final": "R"}

    def test_generacion_completa_con_cuota_de_gemini_agotada(self):
        """11. La generación termina usando OpenRouter y no reintenta Gemini."""
        seccion = {
            "seccion_id": "s1", "orden": 1, "titulo": "Sección 1",
            "bloques": [{"tipo": "paragraph", "texto": "Contenido."}],
        }
        respuestas = [
            json.dumps(self.PLAN),
            json.dumps(seccion),
            json.dumps({"ejercicios": [self._ejercicio(1, "inicial"),
                                       self._ejercicio(2, "inicial")]}),
            json.dumps({"ejercicios": [self._ejercicio(3, "intermedio"),
                                       self._ejercicio(4, "intermedio")]}),
            json.dumps(self.COMPONENTES),
        ]
        iterador = iter(respuestas)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        carpeta = Path(tmp.name)
        generador = gb.GeneradorBloques()

        with patch("configuracion.AI_PROVIDER_ORDER", ["gemini", "openrouter"]), \
             patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorCuotaAgotada(MENSAJE_GEMINI_DIARIO)) as mock_gemini, \
             patch.object(pi, "generar_con_openrouter_estructurado",
                          side_effect=lambda *a, **k: (next(iterador), "modelo-prueba")), \
             patch.object(gb, "construir_pdf", return_value=True), \
             patch.object(generador, "_crear_carpeta_trabajo",
                          return_value=carpeta):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=4,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="cuota_agotada",
            )

        self.assertTrue(resultado["exito"], resultado["mensaje"])
        # Gemini se intentó una sola vez (el resto de bloques ya no lo tocan).
        self.assertEqual(mock_gemini.call_count, 1)
        self.assertEqual(generador.proveedores_agotados, {"gemini"})


class TestConfiguracionLogging(unittest.TestCase):
    """El logging debe dejar visible el cambio de proveedor."""

    def test_configura_consola_y_archivo(self):
        """12. Se agregan handlers de consola y de archivo."""
        import main

        logging.disable(logging.NOTSET)
        raiz = logging.getLogger()
        nivel_previo = raiz.level
        handlers_previos = list(raiz.handlers)
        creados = []
        tmp = tempfile.mkdtemp()

        try:
            main._configurar_logging(tmp)
            creados = [h for h in raiz.handlers if h not in handlers_previos]
            self.assertTrue(
                any(isinstance(h, logging.FileHandler) for h in creados)
            )
            self.assertTrue((Path(tmp) / "aula_ia.log").exists())
        finally:
            # En Windows hay que soltar el archivo antes de borrar la carpeta.
            for handler in creados:
                raiz.removeHandler(handler)
                handler.close()
            raiz.setLevel(nivel_previo)
            shutil.rmtree(tmp, ignore_errors=True)


class TestModoJsonOpenRouter(unittest.TestCase):
    """
    El modo JSON nativo mejora el cumplimiento y orienta al router de modelos
    gratuitos hacia modelos que sí saben devolver JSON.
    """

    def _respuesta(self, status, body):
        respuesta = MagicMock()
        respuesta.status_code = status
        respuesta.ok = 200 <= status < 300
        respuesta.text = json.dumps(body)
        respuesta.json.return_value = body
        return respuesta

    def test_envia_response_format_json_object(self):
        """13. La solicitud incluye modo JSON y no envía 'reasoning'."""
        capturado = {}
        respuesta = self._respuesta(
            200, {"choices": [{"message": {"content": '{"ok": true}'},
                               "finish_reason": "stop"}]}
        )

        def capturar(url, headers=None, json=None, timeout=None):
            capturado.update(json or {})
            return respuesta

        with patch("requests.post", side_effect=capturar):
            generar_con_openrouter("instrucción", api_key="clave-test")

        self.assertEqual(capturado.get("response_format"), {"type": "json_object"})
        # No se envía 'reasoning': algunos endpoints lo exigen y rechazan
        # que se desactive.
        self.assertNotIn("reasoning", capturado)

    def test_reintenta_sin_response_format_si_lo_rechazan(self):
        """14. Si el proveedor rechaza response_format, se reintenta sin él."""
        cuerpos = [
            self._respuesta(400, {"error": {
                "message": "response_format is not supported"}}),
            self._respuesta(
                200, {"choices": [{"message": {"content": '{"ok": true}'},
                                   "finish_reason": "stop"}]}
            ),
        ]
        enviados = []

        def lado(*args, **kwargs):
            enviados.append(kwargs.get("json") or {})
            return cuerpos.pop(0)

        with patch("requests.post", side_effect=lado):
            texto = generar_con_openrouter("instrucción", api_key="clave-test")

        self.assertEqual(texto, '{"ok": true}')
        self.assertIn("response_format", enviados[0])
        self.assertNotIn("response_format", enviados[1])
        self.assertNotIn("reasoning", enviados[1])

    def test_reintenta_si_rechazan_el_control_de_razonamiento(self):
        """14b. Si el proveedor rechaza 'reasoning', se reintenta sin extras."""
        cuerpos = [
            self._respuesta(400, {"error": {
                "message": "reasoning is not supported by this model"}}),
            self._respuesta(
                200, {"choices": [{"message": {"content": '{"ok": true}'},
                                   "finish_reason": "stop"}]}
            ),
        ]
        enviados = []

        def lado(*args, **kwargs):
            enviados.append(kwargs.get("json") or {})
            return cuerpos.pop(0)

        with patch("requests.post", side_effect=lado):
            texto = generar_con_openrouter("instrucción", api_key="clave-test")

        self.assertEqual(texto, '{"ok": true}')
        self.assertNotIn("reasoning", enviados[1])
        self.assertNotIn("response_format", enviados[1])

    def test_reintenta_si_error_200_menciona_parametros(self):
        """14c. Un error en el cuerpo con HTTP 200 se reintenta sin extras.

        Reproduce el caso real: "Reasoning is mandatory for this endpoint and
        cannot be disabled."
        """
        cuerpos = [
            self._respuesta(200, {"error": {"message": (
                "Reasoning is mandatory for this endpoint and cannot be "
                "disabled.")}}),
            self._respuesta(
                200, {"choices": [{"message": {"content": '{"ok": true}'},
                                   "finish_reason": "stop"}]}
            ),
        ]
        enviados = []

        def lado(*args, **kwargs):
            enviados.append(kwargs.get("json") or {})
            return cuerpos.pop(0)

        with patch("requests.post", side_effect=lado):
            texto = generar_con_openrouter("instrucción", api_key="clave-test")

        self.assertEqual(texto, '{"ok": true}')
        self.assertEqual(len(enviados), 2)
        self.assertNotIn("response_format", enviados[1])

    def test_contenido_vacio_reporta_finish_reason(self):
        """15. Un contenido vacío se informa con finish_reason y se reintenta."""
        with patch("requests.post", return_value=self._respuesta(
            200, {"choices": [{"message": {"content": ""},
                               "finish_reason": "content_filter"}]}
        )):
            with self.assertRaises(pi.ErrorRespuestaIncompleta) as contexto:
                generar_con_openrouter("instrucción", api_key="clave-test")

        self.assertIn("finish_reason=content_filter", str(contexto.exception))

    def test_contenido_vacio_con_razonamiento(self):
        """16. Si sólo hubo razonamiento, el mensaje lo indica."""
        with patch("requests.post", return_value=self._respuesta(
            200, {"choices": [{"message": {"content": "",
                                           "reasoning": "pensando..."},
                               "finish_reason": "stop"}]}
        )):
            with self.assertRaises(pi.ErrorRespuestaIncompleta) as contexto:
                generar_con_openrouter("instrucción", api_key="clave-test")

        self.assertIn("razonamiento", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
