"""
Pruebas de la integración con Gemini (google-genai).

Verifican que el tiempo de espera HTTP se configura con
types.HttpOptions al crear el cliente (único mecanismo admitido por la
versión instalada) y que los errores del SDK nunca se confunden con
contenido generado por el modelo.

No se realizan llamadas reales: el cliente del SDK está sustituido por
dobles de prueba.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import configuracion
import proveedores_ia
from proveedores_ia import (
    ErrorIA,
    ErrorIntegracion,
    ErrorRespuestaIncompleta,
    clasificar_error,
    generar_con_gemini,
    generar_contenido_educativo,
)


def _respuesta_gemini(texto: str, motivo: str = None) -> MagicMock:
    """Construye una respuesta simulada de Gemini."""
    respuesta = MagicMock()
    respuesta.text = texto
    candidato = MagicMock()
    candidato.finish_reason = motivo
    respuesta.candidates = [candidato]
    return respuesta


class TestTimeoutGemini(unittest.TestCase):
    """El timeout debe configurarse en el cliente, en milisegundos."""

    def test_timeout_se_configura_con_http_options(self):
        """1. El cliente recibe HttpOptions con el timeout en milisegundos."""
        respuesta = _respuesta_gemini('{"ok": true}')

        with patch("google.genai.Client") as mock_client_cls:
            instancia = mock_client_cls.return_value
            instancia.models.generate_content.return_value = respuesta

            generar_con_gemini("instrucción", modelo="modelo-test", api_key="clave-test")

            self.assertEqual(mock_client_cls.call_count, 1)
            kwargs = mock_client_cls.call_args.kwargs

            self.assertIn("http_options", kwargs)
            http_options = kwargs["http_options"]
            self.assertEqual(http_options.timeout, 60000)

    def test_timeout_segundos_a_milisegundos(self):
        """2. TIMEOUT_SEGUNDOS=60 se convierte en 60000 ms."""
        with patch.object(proveedores_ia, "TIMEOUT_SEGUNDOS", 60):
            opciones = proveedores_ia._opciones_http_gemini()
            self.assertEqual(opciones.timeout, 60000)

        with patch.object(proveedores_ia, "TIMEOUT_SEGUNDOS", 45):
            opciones = proveedores_ia._opciones_http_gemini()
            self.assertEqual(opciones.timeout, 45000)

    def test_generate_content_sin_timeout_ni_request_options(self):
        """3. generate_content() no recibe timeout ni request_options."""
        respuesta = _respuesta_gemini('{"ok": true}')

        with patch("google.genai.Client") as mock_client_cls:
            instancia = mock_client_cls.return_value
            instancia.models.generate_content.return_value = respuesta

            generar_con_gemini("instrucción", modelo="modelo-test", api_key="clave-test")

            kwargs = instancia.models.generate_content.call_args.kwargs
            self.assertNotIn("timeout", kwargs)
            self.assertNotIn("request_options", kwargs)
            self.assertEqual(kwargs["model"], "modelo-test")
            self.assertEqual(kwargs["contents"], "instrucción")


class TestRespuestaGemini(unittest.TestCase):
    """Procesamiento de respuestas y propagación de errores."""

    def test_procesa_respuesta_valida_simulada(self):
        """4. Una respuesta válida simulada se devuelve sin modificar."""
        respuesta = _respuesta_gemini('  {"metadatos": {"titulo": "Tema"}}  ')

        with patch("google.genai.Client") as mock_client_cls:
            instancia = mock_client_cls.return_value
            instancia.models.generate_content.return_value = respuesta

            texto = generar_con_gemini("instrucción", api_key="clave-test")

        self.assertEqual(texto, '{"metadatos": {"titulo": "Tema"}}')
        self.assertEqual(json.loads(texto)["metadatos"]["titulo"], "Tema")

    def test_excepcion_gemini_se_propaga_y_no_es_json(self):
        """5. Una excepción de Gemini se propaga y no se interpreta como JSON."""
        with patch("google.genai.Client") as mock_client_cls:
            instancia = mock_client_cls.return_value
            instancia.models.generate_content.side_effect = RuntimeError(
                "503 UNAVAILABLE: service overloaded"
            )

            with self.assertRaises(ErrorIA) as contexto:
                generar_con_gemini("instrucción", api_key="clave-test")

            error = contexto.exception
            # Se propaga como error, nunca como texto de respuesta.
            self.assertNotIsInstance(error, ErrorRespuestaIncompleta)
            self.assertIn("503", str(error))

    def test_typeerror_es_error_de_integracion(self):
        """Un TypeError del SDK se clasifica como integración, no como JSON."""
        with patch("google.genai.Client") as mock_client_cls:
            instancia = mock_client_cls.return_value
            instancia.models.generate_content.side_effect = TypeError(
                "generate_content() got an unexpected keyword argument 'timeout'"
            )

            with self.assertRaises(ErrorIntegracion):
                generar_con_gemini("instrucción", api_key="clave-test")

    def test_error_integracion_no_prueba_otro_proveedor(self):
        """Un error de integración aborta el recorrido de proveedores."""
        with patch("proveedores_ia.generar_con_gemini") as mock_gemini, \
             patch("proveedores_ia.generar_con_openrouter") as mock_openrouter, \
             patch("proveedores_ia.proveedor_esta_configurado", return_value=True):

            mock_gemini.side_effect = ErrorIntegracion("argumento no admitido")

            with self.assertRaises(ErrorIntegracion):
                generar_contenido_educativo("instrucción", ["gemini", "openrouter"])

            mock_openrouter.assert_not_called()

    def test_respuesta_vacia_reporta_motivo(self):
        """Una respuesta sin texto informa el motivo de finalización."""
        respuesta = _respuesta_gemini("", motivo="MAX_TOKENS")

        with patch("google.genai.Client") as mock_client_cls:
            instancia = mock_client_cls.return_value
            instancia.models.generate_content.return_value = respuesta

            with self.assertRaises(ErrorRespuestaIncompleta) as contexto:
                generar_con_gemini("instrucción", api_key="clave-test")

            self.assertIn("MAX_TOKENS", str(contexto.exception))


class TestClasificacionIntegracion(unittest.TestCase):
    """Los errores de programación no se confunden con errores de modelo."""

    def test_typeerror_no_es_respuesta_incompleta(self):
        self.assertIsInstance(
            clasificar_error(TypeError("argumento inesperado")),
            ErrorIntegracion,
        )
        self.assertNotIsInstance(
            clasificar_error(TypeError("argumento inesperado")),
            ErrorRespuestaIncompleta,
        )

    def test_attributeerror_es_integracion(self):
        self.assertIsInstance(
            clasificar_error(AttributeError("sin atributo")),
            ErrorIntegracion,
        )

    def test_errores_de_modelo_siguen_clasificandose(self):
        from proveedores_ia import ErrorClaveInvalida, ErrorCuotaAgotada

        self.assertIsInstance(clasificar_error(Exception("401 Unauthorized")), ErrorClaveInvalida)
        self.assertIsInstance(clasificar_error(Exception("429 Rate limit")), ErrorCuotaAgotada)


class TestPersistenciaAnteFallo(unittest.TestCase):
    """Un fallo de Gemini no debe sobrescribir bloques ya validados."""

    def setUp(self):
        import generador_bloques

        self.modulo = generador_bloques
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_fallo_gemini_no_sobrescribe_plan_guardado(self):
        """6. Un fallo de Gemini conserva plan.json y los bloques previos."""
        generador = self.modulo.GeneradorBloques()
        generador.trabajo_id = "prueba_fallo"
        generador.carpeta_trabajo = self.carpeta

        plan_previo = {
            "titulo": "Plan previo",
            "secciones": [{"id": "s1"}],
        }
        generador._guardar_bloque_validado("plan.json", plan_previo)
        generador._guardar_bloque_validado("seccion_s1.json", {"id": "s1"})

        with patch.object(
            self.modulo, "generar_contenido_educativo",
            side_effect=ErrorIA("fallo simulado del proveedor"),
        ):
            with self.assertRaises(ErrorIA):
                generador._generar_plan(
                    tema="Tema", disciplina="Historia", nivel="Secundaria",
                    profundidad="estándar", cantidad_actividades=5,
                    recursos_visuales=False,
                )

        # El plan validado sigue intacto.
        plan_disco = json.loads((self.carpeta / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan_disco, plan_previo)
        self.assertTrue((self.carpeta / "seccion_s1.json").exists())

    def test_plan_truncado_se_reintenta_y_no_marca_exito(self):
        """Un plan truncado se reintenta y, si persiste, falla con error claro."""
        generador = self.modulo.GeneradorBloques()
        generador.trabajo_id = "prueba_truncado"
        generador.carpeta_trabajo = self.carpeta

        truncado = '{"titulo": "Plan", "secciones": ['
        with patch.object(
            self.modulo, "generar_contenido_educativo",
            return_value=(truncado, "gemini"),
        ) as mock_generar:
            with self.assertRaises(self.modulo.ErrorBloque):
                generador._generar_plan(
                    tema="Tema", disciplina="Historia", nivel="Secundaria",
                    profundidad="estándar", cantidad_actividades=5,
                    recursos_visuales=False,
                )

            # Reintentos limitados, no infinitos.
            self.assertEqual(
                mock_generar.call_count,
                self.modulo.MAX_REINTENTOS_BLOQUE,
            )

        self.assertFalse((self.carpeta / "plan.json").exists())
        # Las respuestas crudas se conservan para diagnóstico.
        self.assertTrue((self.carpeta / "plan_crudo.json").exists())
        self.assertTrue((self.carpeta / "plan_intento2_crudo.json").exists())

    def test_plan_valido_se_guarda(self):
        """Un plan válido se persiste y se expone en el objeto."""
        generador = self.modulo.GeneradorBloques()
        generador.trabajo_id = "prueba_valido"
        generador.carpeta_trabajo = self.carpeta

        plan = {
            "titulo": "Plan de prueba",
            "disciplina": "Historia",
            "nivel": "Secundaria",
            "profundidad": "estándar",
            "objetivos_aprendizaje": ["Objetivo 1"],
            "conocimientos_previos": ["Conocimiento 1"],
            "secciones": [{
                "id": "s1",
                "orden": 1,
                "titulo": "Sección 1",
                "conceptos_principales": ["Concepto 1"],
                "ejemplos_sugeridos": ["Ejemplo 1"],
                "recursos_visuales": [],
            }],
            "recursos_visuales_planificados": [],
        }

        with patch.object(
            self.modulo, "generar_contenido_educativo",
            return_value=(json.dumps(plan), "gemini"),
        ):
            resultado = generador._generar_plan(
                tema="Tema", disciplina="Historia", nivel="Secundaria",
                profundidad="estándar", cantidad_actividades=5,
                recursos_visuales=False,
            )

        self.assertEqual(resultado["titulo"], "Plan de prueba")
        self.assertTrue((self.carpeta / "plan.json").exists())


class TestModulosImportables(unittest.TestCase):
    """7. El resto de los módulos se importa y está disponible."""

    def test_modulos_se_importan(self):
        for nombre in (
            "proveedores_ia",
            "generador_bloques",
            "generador_ia",
            "generador_imagenes",
            "configuracion",
            "plantillas",
            "esquemas_bloques",
            "validador",
            "generador_pdf",
        ):
            with self.subTest(modulo=nombre):
                importlib.import_module(nombre)


if __name__ == "__main__":
    unittest.main()
