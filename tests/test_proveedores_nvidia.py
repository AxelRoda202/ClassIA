"""
Pruebas de los proveedores directos NVIDIA NIM y Groq.

No se realizan llamadas reales: `requests.post` y los proveedores se
sustituyen por dobles. Se verifica la integración con la jerarquía
Gemini -> NVIDIA -> Groq -> OpenRouter, la validación local de esquemas y la
prevención de reintentos innecesarios.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import configuracion
import proveedores_ia as pi
import requests
from proveedores_ia import (
    ErrorClaveInvalida,
    ErrorIntegracion,
    ErrorModelosAgotados,
    ErrorRed,
    ErrorServidor,
    generar_con_groq_estructurado,
    generar_con_nvidia_estructurado,
)

ESQUEMA = {
    "type": "object",
    "properties": {"valor": {"type": "string"}},
    "required": ["valor"],
    "additionalProperties": False,
}


def validador(datos):
    if not isinstance(datos, dict):
        return False, ["no es un objeto"]
    if not isinstance(datos.get("valor"), str) or not datos["valor"].strip():
        return False, ["falta el campo obligatorio 'valor'"]
    return True, []


class RespuestaFalsa:
    """Doble de requests.Response."""

    def __init__(self, status_code=200, cuerpo=None, texto=None):
        self.status_code = status_code
        self._cuerpo = cuerpo
        if texto is not None:
            self.text = texto
        elif cuerpo is not None:
            self.text = json.dumps(cuerpo)
        else:
            self.text = ""

    def json(self):
        if self._cuerpo is None:
            raise ValueError("sin JSON")
        return self._cuerpo


def respuesta(status=200, cuerpo=None, texto=None):
    return RespuestaFalsa(status_code=status, cuerpo=cuerpo, texto=texto)


def cuerpo_modelo(texto, finish="stop", modelo="modelo-real"):
    return {
        "model": modelo,
        "choices": [{
            "message": {"content": texto},
            "finish_reason": finish,
        }],
    }


class TestNvidiaEstructurado(unittest.TestCase):
    """Solicitud directa, formatos y fallback entre modelos candidatos."""

    def _ejecutar(self, respuestas, modelos=("m1", "m2"),
                  modelos_agotados=None, formato="guided_json"):
        with patch.object(pi, "NVIDIA_API_KEY", "clave-test"), \
             patch.object(pi, "NVIDIA_MODELS", list(modelos)), \
             patch.object(pi, "NVIDIA_RESPONSE_FORMAT", formato), \
             patch("requests.post", side_effect=respuestas) as mock_post:
            resultado = generar_con_nvidia_estructurado(
                "instrucción",
                ESQUEMA,
                "prueba",
                True,
                validador,
                etapa="prueba",
                modelos=list(modelos),
                api_key="clave-test",
                modelos_agotados=modelos_agotados,
            )
        return resultado, mock_post

    def test_guided_json_envia_nvext_con_esquema_real(self):
        (texto, modelo), mock_post = self._ejecutar([
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}')),
        ])
        self.assertEqual(texto, '{"valor": "ok"}')
        self.assertEqual(modelo, "modelo-real")
        self.assertEqual(mock_post.call_count, 1)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "m1")
        self.assertEqual(payload["nvext"]["guided_json"], ESQUEMA)
        self.assertNotIn("response_format", payload)

    def test_json_object_envia_response_format(self):
        _, mock_post = self._ejecutar(
            [respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}'))],
            formato="json_object",
        )
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("nvext", payload)

    def test_401_realiza_una_sola_solicitud(self):
        with patch.object(pi, "NVIDIA_API_KEY", "clave-test"), \
             patch.object(pi, "NVIDIA_MODELS", ["m1", "m2"]), \
             patch("requests.post", side_effect=[
                 respuesta(status=401,
                           cuerpo={"error": {"message": "unauthorized"}}),
             ]) as mock_post:
            with self.assertRaises(ErrorClaveInvalida):
                generar_con_nvidia_estructurado(
                    "instrucción", ESQUEMA, "prueba", True, validador,
                    modelos=["m1", "m2"], api_key="clave-test",
                )
        self.assertEqual(mock_post.call_count, 1)

    def test_error_de_red_no_prueba_cada_modelo(self):
        with patch.object(pi, "NVIDIA_API_KEY", "clave-test"), \
             patch.object(pi, "NVIDIA_MODELS", ["m1", "m2"]), \
             patch("requests.post",
                   side_effect=requests.ConnectionError("network down")) as mock_post:
            with self.assertRaises(ErrorRed):
                generar_con_nvidia_estructurado(
                    "instrucción", ESQUEMA, "prueba", True, validador,
                    modelos=["m1", "m2"], api_key="clave-test",
                )
        self.assertEqual(mock_post.call_count, 1)

    def test_limite_de_solicitudes_no_prueba_cada_modelo(self):
        with patch.object(pi, "NVIDIA_API_KEY", "clave-test"), \
             patch.object(pi, "NVIDIA_MODELS", ["m1", "m2"]), \
             patch("requests.post", side_effect=[
                 respuesta(status=429,
                           cuerpo={"error": {"message": "rate limit"}}),
             ]) as mock_post:
            with self.assertRaises(pi.ErrorLimiteSolicitudes):
                generar_con_nvidia_estructurado(
                    "instrucción", ESQUEMA, "prueba", True, validador,
                    modelos=["m1", "m2"], api_key="clave-test",
                )
        self.assertEqual(mock_post.call_count, 1)

    def test_json_invalido_pasa_al_siguiente_modelo(self):
        (texto, modelo), mock_post = self._ejecutar([
            respuesta(cuerpo=cuerpo_modelo("{no es json")),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ])
        self.assertEqual(texto, '{"valor": "ok"}')
        self.assertEqual(modelo, "modelo-2")
        self.assertEqual(mock_post.call_count, 2)

    def test_json_valido_fuera_de_esquema_pasa_al_siguiente(self):
        (texto, modelo), mock_post = self._ejecutar([
            respuesta(cuerpo=cuerpo_modelo('{"otro": "dato"}')),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ])
        self.assertEqual(texto, '{"valor": "ok"}')
        self.assertEqual(modelo, "modelo-2")
        self.assertEqual(mock_post.call_count, 2)

    def test_respuesta_truncada_pasa_al_siguiente(self):
        _, mock_post = self._ejecutar([
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}', finish="length")),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ])
        self.assertEqual(mock_post.call_count, 2)

    def test_todos_los_modelos_fallan(self):
        with self.assertRaises(ErrorModelosAgotados):
            self._ejecutar([
                respuesta(cuerpo=cuerpo_modelo('{"otro": "dato"}')),
                respuesta(cuerpo=cuerpo_modelo("")),
            ])

    def test_modelo_agotado_se_omite(self):
        agotados = {"m1"}
        (_, modelo), mock_post = self._ejecutar(
            [respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                            modelo="modelo-2"))],
            modelos=("m1", "m2"),
            modelos_agotados=agotados,
        )
        self.assertEqual(modelo, "modelo-2")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args.kwargs["json"]["model"], "m2")


class TestGroqEstructurado(unittest.TestCase):
    """Groq usa el mismo contrato OpenAI, con su propia configuración."""

    def test_json_object_y_validacion_local(self):
        with patch.object(pi, "GROQ_API_KEY", "clave-test"), \
             patch.object(pi, "GROQ_MODELS", ["g1"]), \
             patch.object(pi, "GROQ_RESPONSE_FORMAT", "json_object"), \
             patch("requests.post", return_value=respuesta(
                 cuerpo=cuerpo_modelo('{"valor": "ok"}', modelo="g-real")
             )) as mock_post:
            texto, modelo = generar_con_groq_estructurado(
                "instrucción", ESQUEMA, "prueba", True, validador,
                modelos=["g1"], api_key="clave-test",
            )
        self.assertEqual(texto, '{"valor": "ok"}')
        self.assertEqual(modelo, "g-real")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_401_no_prueba_otros_modelos(self):
        with patch.object(pi, "GROQ_API_KEY", "clave-test"), \
             patch.object(pi, "GROQ_MODELS", ["g1", "g2"]), \
             patch("requests.post", side_effect=[
                 respuesta(status=401,
                           cuerpo={"error": {"message": "unauthorized"}}),
             ]) as mock_post:
            with self.assertRaises(ErrorClaveInvalida):
                generar_con_groq_estructurado(
                    "instrucción", ESQUEMA, "prueba", True, validador,
                    modelos=["g1", "g2"], api_key="clave-test",
                )
        self.assertEqual(mock_post.call_count, 1)


class TestJerarquiaProveedores(unittest.TestCase):
    """Orden Gemini -> NVIDIA -> Groq -> OpenRouter con mocks."""

    def _llamar(self, orden=("gemini", "nvidia", "groq", "openrouter")):
        return pi.generar_contenido_educativo(
            "instrucción", list(orden),
            esquema=ESQUEMA, nombre_esquema="prueba",
            estricto=True, validador=validador, etapa="prueba",
        )

    def test_gemini_falla_y_usa_nvidia(self):
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorServidor("503")) as mock_gemini, \
             patch.object(pi, "generar_con_nvidia_estructurado",
                          return_value=('{"valor": "ok"}', "modelo-n")) as mock_nvidia:
            texto, proveedor = self._llamar()
        self.assertEqual(proveedor, "nvidia")
        self.assertEqual(texto, '{"valor": "ok"}')
        mock_gemini.assert_called_once()
        mock_nvidia.assert_called_once()

    def test_respuesta_invalida_de_gemini_usa_nvidia(self):
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          return_value="no es json") as mock_gemini, \
             patch.object(pi, "generar_con_nvidia_estructurado",
                          return_value=('{"valor": "ok"}', "modelo-n")):
            texto, proveedor = self._llamar()
        self.assertEqual(proveedor, "nvidia")
        self.assertEqual(texto, '{"valor": "ok"}')
        mock_gemini.assert_called_once()

    def test_usa_groq_si_nvidia_falla(self):
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorServidor("503")), \
             patch.object(pi, "generar_con_nvidia_estructurado",
                          side_effect=ErrorServidor("502")), \
             patch.object(pi, "generar_con_groq_estructurado",
                          return_value=('{"valor": "ok"}', "modelo-g")) as mock_groq:
            texto, proveedor = self._llamar()
        self.assertEqual(proveedor, "groq")
        self.assertEqual(texto, '{"valor": "ok"}')
        mock_groq.assert_called_once()

    def test_openrouter_es_el_ultimo_respaldo(self):
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorServidor("503")), \
             patch.object(pi, "generar_con_nvidia_estructurado",
                          side_effect=ErrorServidor("502")), \
             patch.object(pi, "generar_con_groq_estructurado",
                          side_effect=ErrorServidor("501")), \
             patch.object(pi, "generar_con_openrouter_estructurado",
                          return_value=('{"valor": "ok"}', "modelo-o")) as mock_or:
            texto, proveedor = self._llamar()
        self.assertEqual(proveedor, "openrouter")
        self.assertEqual(texto, '{"valor": "ok"}')
        mock_or.assert_called_once()

    def test_omite_proveedores_sin_credenciales(self):
        def configurado(nombre):
            return nombre == "openrouter"

        with patch.object(pi, "proveedor_esta_configurado",
                          side_effect=configurado), \
             patch.object(pi, "generar_con_gemini") as mock_gemini, \
             patch.object(pi, "generar_con_nvidia_estructurado") as mock_nvidia, \
             patch.object(pi, "generar_con_groq_estructurado") as mock_groq, \
             patch.object(pi, "generar_con_openrouter_estructurado",
                          return_value=('{"valor": "ok"}', "modelo-o")):
            texto, proveedor = self._llamar()
        self.assertEqual(proveedor, "openrouter")
        mock_gemini.assert_not_called()
        mock_nvidia.assert_not_called()
        mock_groq.assert_not_called()

    def test_error_de_integracion_aborta_sin_probar_alternativas(self):
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorIntegracion("argumento no admitido")), \
             patch.object(pi, "generar_con_nvidia_estructurado") as mock_nvidia:
            with self.assertRaises(ErrorIntegracion):
                self._llamar()
        mock_nvidia.assert_not_called()

    def test_todos_fallan_devuelve_error_con_detalle(self):
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(pi, "generar_con_gemini",
                          side_effect=ErrorServidor("503")), \
             patch.object(pi, "generar_con_nvidia_estructurado",
                          side_effect=ErrorServidor("502")), \
             patch.object(pi, "generar_con_groq_estructurado",
                          side_effect=ErrorServidor("501")), \
             patch.object(pi, "generar_con_openrouter_estructurado",
                          side_effect=ErrorServidor("500")):
            with self.assertRaises(pi.ErrorIA) as contexto:
                self._llamar()
        mensaje = str(contexto.exception)
        for nombre in ("gemini", "nvidia", "groq", "openrouter"):
            self.assertIn(nombre, mensaje)


class TestConfiguracionProveedores(unittest.TestCase):
    """La habilitación exige clave y modelos, sin activar candidatos solos."""

    def test_nvidia_requiere_clave_y_modelos(self):
        with patch.object(configuracion, "NVIDIA_API_KEY", "clave"), \
             patch.object(configuracion, "NVIDIA_MODELS", ["m1"]):
            self.assertTrue(configuracion.proveedor_esta_configurado("nvidia"))
        with patch.object(configuracion, "NVIDIA_API_KEY", ""), \
             patch.object(configuracion, "NVIDIA_MODELS", ["m1"]):
            self.assertFalse(configuracion.proveedor_esta_configurado("nvidia"))
        with patch.object(configuracion, "NVIDIA_API_KEY", "clave"), \
             patch.object(configuracion, "NVIDIA_MODELS", []):
            self.assertFalse(configuracion.proveedor_esta_configurado("nvidia"))

    def test_groq_requiere_clave_y_modelos(self):
        with patch.object(configuracion, "GROQ_API_KEY", "clave"), \
             patch.object(configuracion, "GROQ_MODELS", ["g1"]):
            self.assertTrue(configuracion.proveedor_esta_configurado("groq"))
        with patch.object(configuracion, "GROQ_API_KEY", "clave"), \
             patch.object(configuracion, "GROQ_MODELS", []):
            self.assertFalse(configuracion.proveedor_esta_configurado("groq"))

    def test_lista_deduplica_y_respeta_preferido(self):
        with patch.dict(os.environ, {"AULA_IA_LISTA_TEST": "m2,m1,m2"}):
            lista = configuracion._modelos_configurados(
                "m1", "AULA_IA_LISTA_TEST"
            )
        self.assertEqual(lista, ["m1", "m2"])

    def test_sin_modelos_por_defecto(self):
        with patch.dict(os.environ, {"AULA_IA_LISTA_TEST": ""}):
            self.assertEqual(
                configuracion._modelos_configurados("", "AULA_IA_LISTA_TEST"),
                [],
            )

    def test_orden_objetivo_y_deduplicacion(self):
        orden = configuracion._normalizar_orden_proveedores(
            " Gemini, nvidia, groq, openrouter, gemini "
        )
        self.assertEqual(
            orden, ["gemini", "nvidia", "groq", "openrouter"]
        )

    def test_orden_vacio_no_inventa_proveedores(self):
        self.assertEqual(
            configuracion._normalizar_orden_proveedores(" , , "), []
        )


if __name__ == "__main__":
    unittest.main()
