"""
Pruebas de la salida estructurada de OpenRouter.

No se realizan llamadas reales: `requests.post` está sustituido por dobles.
Se verifican:
- JSON Schema por etapa, strict y require_parameters.
- Fallback entre modelos ante errores HTTP, cuota, respuesta vacía, razonamiento
  sin contenido, JSON inválido y esquema incumplido.
- Modelo real devuelto y validación local antes de aceptar.
- Límite global: cada modelo se prueba una vez por solicitud lógica.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generador_bloques as gb
import proveedores_ia as pi
from esquemas_bloques import obtener_esquema_openrouter
from proveedores_ia import (
    ErrorClaveInvalida,
    ErrorModelosAgotados,
    generar_con_openrouter_estructurado,
)

ESQUEMA = {
    "type": "object",
    "properties": {"valor": {"type": "string"}},
    "required": ["valor"],
    "additionalProperties": False,
}

PLAN = {
    "titulo": "Título",
    "disciplina": "Historia",
    "nivel": "Secundario",
    "profundidad": "breve",
    "objetivos_aprendizaje": ["Objetivo"],
    "conocimientos_previos": ["Previo"],
    "secciones": [{
        "id": "s1",
        "orden": 1,
        "titulo": "Sección",
        "conceptos_principales": ["Concepto"],
        "ejemplos_sugeridos": ["Ejemplo"],
        "recursos_visuales": [],
    }],
    "recursos_visuales_planificados": [],
}


def validador(datos):
    """Validador mínimo equivalente a los de esquemas_bloques."""
    if not isinstance(datos, dict):
        return False, ["no es un objeto"]
    valor = datos.get("valor")
    if not isinstance(valor, str) or not valor.strip():
        return False, ["falta el campo obligatorio 'valor'"]
    return True, []


class RespuestaFalsa:
    """Doble de requests.Response con status, cuerpo y texto."""

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


def cuerpo_modelo(texto, finish="stop", modelo="modelo-real",
                  razonamiento=None):
    mensaje = {"content": texto}
    if razonamiento is not None:
        mensaje["reasoning"] = razonamiento
    return {
        "model": modelo,
        "choices": [{
            "message": mensaje,
            "finish_reason": finish,
        }],
    }


class TestFallbackEstructurado(unittest.TestCase):
    """Fallback acotado y validación local antes de aceptar una respuesta."""

    def _ejecutar(self, respuestas, modelos=("m1", "m2"),
                  modelos_agotados=None, api_key="clave-test"):
        with patch("requests.post", side_effect=respuestas) as mock_post:
            resultado = generar_con_openrouter_estructurado(
                "instrucción",
                ESQUEMA,
                "prueba",
                True,
                validador,
                etapa="prueba",
                modelos=list(modelos),
                api_key=api_key,
                modelos_agotados=modelos_agotados,
            )
        return resultado, mock_post

    def test_exito_usa_json_schema_y_require_parameters(self):
        """1. El primer modelo válido se acepta con el esquema de la etapa."""
        respuestas = [respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}'))]
        (texto, modelo), mock_post = self._ejecutar(respuestas)

        self.assertEqual(texto, '{"valor": "ok"}')
        self.assertEqual(modelo, "modelo-real")
        self.assertEqual(mock_post.call_count, 1)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "m1")
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(
            payload["response_format"]["json_schema"]["schema"], ESQUEMA
        )
        self.assertTrue(
            payload["response_format"]["json_schema"]["strict"]
        )
        self.assertEqual(
            payload["provider"], {"require_parameters": True}
        )

    def test_contenido_vacio_con_razonamiento_pasa_al_siguiente(self):
        """2. Razonamiento sin contenido final no se acepta."""
        respuestas = [
            respuesta(cuerpo=cuerpo_modelo("", razonamiento="pensando")),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        (texto, modelo), mock_post = self._ejecutar(respuestas)

        self.assertEqual(texto, '{"valor": "ok"}')
        self.assertEqual(modelo, "modelo-2")
        self.assertEqual(mock_post.call_count, 2)

    def test_respuesta_truncada_pasa_al_siguiente(self):
        """3. finish_reason=length se rechaza aunque el JSON parezca válido."""
        respuestas = [
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}', finish="length")),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        (_, modelo), _ = self._ejecutar(respuestas)
        self.assertEqual(modelo, "modelo-2")

    def test_json_invalido_pasa_al_siguiente(self):
        """4. Un JSON truncado o inválido no llega al documento."""
        respuestas = [
            respuesta(cuerpo=cuerpo_modelo('{"valor": ')),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        (_, modelo), _ = self._ejecutar(respuestas)
        self.assertEqual(modelo, "modelo-2")

    def test_json_valido_sin_esquema_pasa_al_siguiente(self):
        """5. Un JSON válido que no cumple el esquema se rechaza."""
        respuestas = [
            respuesta(cuerpo=cuerpo_modelo('{"otro": "dato"}')),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        (_, modelo), _ = self._ejecutar(respuestas)
        self.assertEqual(modelo, "modelo-2")

    def test_errores_http_pasan_al_siguiente(self):
        """6. 400/404/429/5xx prueban el siguiente modelo."""
        casos = [
            (400, {"error": {"message": "bad request"}}),
            (404, {"error": {"message": "model not found"}}),
            (429, {"error": {"message": "Rate limit exceeded"}}),
            (500, {"error": {"message": "boom"}}),
            (503, {"error": {"message": "unavailable"}}),
        ]
        for status, cuerpo in casos:
            with self.subTest(status=status):
                respuestas = [
                    respuesta(status=status, cuerpo=cuerpo),
                    respuesta(cuerpo=cuerpo_modelo(
                        '{"valor": "ok"}', modelo="modelo-2"
                    )),
                ]
                (_, modelo), mock_post = self._ejecutar(respuestas)
                self.assertEqual(modelo, "modelo-2")
                self.assertEqual(mock_post.call_count, 2)

    def test_401_aborta_sin_probar_otros_modelos(self):
        """7. Una clave inválida no se reintenta con otro modelo."""
        respuestas = [
            respuesta(status=401, cuerpo={"error": {"message": "unauthorized"}}),
        ]
        with patch("requests.post", side_effect=respuestas) as mock_post:
            with self.assertRaises(ErrorClaveInvalida):
                generar_con_openrouter_estructurado(
                    "instrucción", ESQUEMA, "prueba", True, validador,
                    etapa="prueba", modelos=["m1", "m2"],
                    api_key="clave-test",
                )
        self.assertEqual(mock_post.call_count, 1)

    def test_todos_los_modelos_fallan_y_limite_global(self):
        """8. Se prueba cada modelo una sola vez y luego se aborta."""
        respuestas = [
            respuesta(cuerpo=cuerpo_modelo("", razonamiento="r")),
            respuesta(cuerpo=cuerpo_modelo("no es json")),
            respuesta(cuerpo=cuerpo_modelo('{"otro": 1}')),
        ]
        with patch("requests.post", side_effect=respuestas) as mock_post:
            with self.assertRaises(ErrorModelosAgotados):
                generar_con_openrouter_estructurado(
                    "instrucción", ESQUEMA, "prueba", True, validador,
                    etapa="prueba", modelos=["m1", "m2", "m3"],
                    api_key="clave-test",
                )

        self.assertEqual(mock_post.call_count, 3)
        modelos = [
            llamada.kwargs["json"]["model"]
            for llamada in mock_post.call_args_list
        ]
        self.assertEqual(modelos, ["m1", "m2", "m3"])

    def test_modelo_agotado_se_omite(self):
        """9. Un modelo marcado como no disponible no se vuelve a llamar."""
        agotados = {"m1"}
        respuestas = [
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        (_, modelo), mock_post = self._ejecutar(
            respuestas, modelos=["m1", "m2"], modelos_agotados=agotados
        )
        self.assertEqual(modelo, "modelo-2")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args.kwargs["json"]["model"], "m2")

    def test_404_marca_modelo_no_disponible(self):
        """10. Un 404 se recuerda para no repetirlo en los bloques siguientes."""
        agotados = set()
        respuestas = [
            respuesta(status=404, cuerpo={"error": {"message": "not found"}}),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        self._ejecutar(
            respuestas, modelos=["m1", "m2"], modelos_agotados=agotados
        )
        self.assertIn("m1", agotados)

    def test_cuota_diaria_marca_modelo(self):
        """11. Un 429 con 'per-day' se considera persistente y se omite."""
        agotados = set()
        respuestas = [
            respuesta(status=429, cuerpo={"error": {"message": (
                "Rate limit exceeded: free-models-per-day. "
                "Add 10 credits to unlock more requests."
            )}}),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        self._ejecutar(
            respuestas, modelos=["m1", "m2"], modelos_agotados=agotados
        )
        self.assertIn("m1", agotados)

    def test_cuota_transitoria_no_marca_modelo(self):
        """12. Un 429 de segundos no se recuerda como agotamiento diario."""
        agotados = set()
        respuestas = [
            respuesta(status=429, cuerpo={"error": {"message": (
                "Rate limit exceeded. Retry in 30s."
            )}}),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        self._ejecutar(
            respuestas, modelos=["m1", "m2"], modelos_agotados=agotados
        )
        self.assertNotIn("m1", agotados)

    def test_contenido_en_partes(self):
        """13. message.content puede ser una lista de partes."""
        cuerpo = {
            "model": "modelo-lista",
            "choices": [{
                "message": {"content": [
                    {"type": "text", "text": '{"valor": "ok"}'},
                ]},
                "finish_reason": "stop",
            }],
        }
        (texto, modelo), _ = self._ejecutar([respuesta(cuerpo=cuerpo)])
        self.assertEqual(texto, '{"valor": "ok"}')
        self.assertEqual(modelo, "modelo-lista")

    def test_http_200_con_error_logico_pasa_al_siguiente(self):
        """14. Un 200 con cuerpo de error no se acepta como respuesta."""
        respuestas = [
            respuesta(cuerpo={"error": {"message": (
                "No endpoints found that support response_format"
            )}}),
            respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}',
                                           modelo="modelo-2")),
        ]
        (_, modelo), _ = self._ejecutar(respuestas)
        self.assertEqual(modelo, "modelo-2")

    def test_json_object_mantiene_validacion_local(self):
        """15. En modo json_object, el esquema local sigue rechazando."""
        with patch.object(pi, "OPENROUTER_RESPONSE_FORMAT", "json_object"):
            respuestas = [
                respuesta(cuerpo=cuerpo_modelo('{"valor": ""}')),
            ]
            with patch("requests.post", side_effect=respuestas) as mock_post:
                with self.assertRaises(ErrorModelosAgotados):
                    generar_con_openrouter_estructurado(
                        "instrucción", ESQUEMA, "prueba", True, validador,
                        etapa="prueba", modelos=["m1"],
                        api_key="clave-test",
                    )
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_la_clave_no_aparece_en_los_logs(self):
        """16. El registro no debe incluir la clave."""
        with self.assertLogs("proveedores_ia", level="INFO") as logs:
            with patch("requests.post", side_effect=[
                respuesta(cuerpo=cuerpo_modelo('{"valor": "ok"}')),
            ]):
                generar_con_openrouter_estructurado(
                    "instrucción", ESQUEMA, "prueba", True, validador,
                    etapa="prueba", modelos=["m1"],
                    api_key="clave-secreta-123",
                )
        self.assertNotIn("clave-secreta-123", "\n".join(logs.output))


class TestPropagacionYLimiteGlobal(unittest.TestCase):
    """El flujo de bloques no debe multiplicar los intentos."""

    def test_generar_contenido_propaga_modelos_agotados(self):
        with patch.object(pi, "proveedor_esta_configurado", return_value=True), \
             patch.object(
                 pi, "generar_con_openrouter_estructurado",
                 side_effect=ErrorModelosAgotados("sin modelos"),
             ):
            with self.assertRaises(ErrorModelosAgotados):
                pi.generar_contenido_educativo(
                    "instrucción", ["openrouter"],
                    esquema=ESQUEMA, nombre_esquema="prueba",
                    estricto=True, validador=validador,
                    etapa="prueba",
                )

    def test_lote_no_se_reintenta_si_se_agotan_los_modelos(self):
        generador = gb.GeneradorBloques()
        generador.plan = PLAN
        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=ErrorModelosAgotados("sin modelos"),
        ) as mock_generar:
            with self.assertRaises(ErrorModelosAgotados):
                generador._generar_un_lote_ejercicios(
                    dificultad="inicial", cantidad=3,
                    contador_inicio=1, profundidad="breve",
                )
        self.assertEqual(mock_generar.call_count, 1)


class TestEsquemasPorEtapa(unittest.TestCase):
    """Los esquemas deben describir los campos reales de cada etapa."""

    def test_lote_exige_respuesta_final_y_cierra_el_objeto(self):
        nombre, esquema, estricto = obtener_esquema_openrouter(
            "lote_ejercicios"
        )
        self.assertEqual(nombre, "lote_ejercicios")
        self.assertTrue(estricto)
        item = esquema["properties"]["ejercicios"]["items"]
        self.assertIn("respuesta_final", item["required"])
        self.assertIn("consigna", item["required"])
        self.assertIn("solucion", item["required"])
        self.assertFalse(item["additionalProperties"])

    def test_plan_es_real_y_no_estricto(self):
        nombre, esquema, estricto = obtener_esquema_openrouter(
            "planificacion"
        )
        self.assertEqual(nombre, "plan_aprendizaje")
        self.assertFalse(estricto)
        self.assertIn("secciones", esquema["required"])
        self.assertIn("recursos_visuales_planificados", esquema["required"])
        recurso = esquema["properties"][
            "recursos_visuales_planificados"
        ]["items"]
        self.assertIn("id", recurso["required"])
        self.assertIn("type", recurso["required"])
        self.assertEqual(recurso["properties"]["data"], {"type": "object"})

    def test_seccion_limita_el_tipo_de_bloque(self):
        nombre, esquema, estricto = obtener_esquema_openrouter(
            "seccion_teorica"
        )
        self.assertTrue(estricto)
        bloque = esquema["properties"]["bloques"]["items"]
        self.assertIn("heading", bloque["properties"]["tipo"]["enum"])
        self.assertIn("visual_reference",
                      bloque["properties"]["tipo"]["enum"])
        self.assertIn("tipo", bloque["required"])
        self.assertFalse(bloque["additionalProperties"])

    def test_componentes_exigen_glosario_y_metadatos(self):
        nombre, esquema, estricto = obtener_esquema_openrouter(
            "componentes_finales"
        )
        self.assertTrue(estricto)
        self.assertIn("glosario", esquema["required"])
        self.assertIn("metadatos", esquema["required"])
        self.assertIn("resumen_final", esquema["required"])


if __name__ == "__main__":
    unittest.main()
