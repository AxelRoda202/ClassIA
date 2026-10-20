"""
Pruebas del flujo segmentado completo con proveedores simulados.

Verifican que:
- Cada etapa emite hitos de progreso reales y monótonos.
- Un bloque truncado se reintenta y luego se recupera.
- Los reintentos son limitados (sin bucles infinitos).
- Los bloques ya validados no se regeneran.
- Un error de integración no se confunde con JSON truncado.

No se realizan llamadas reales a ningún proveedor.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generador_bloques as gb
from proveedores_ia import ErrorIntegracion, ErrorIA


PLAN = {
    "titulo": "Plan de prueba",
    "disciplina": "Historia",
    "nivel": "Secundario",
    "profundidad": "breve",
    "objetivos_aprendizaje": ["Objetivo 1"],
    "conocimientos_previos": ["Conocimiento 1"],
    "secciones": [
        {
            "id": "s1", "orden": 1, "titulo": "Sección 1",
            "conceptos_principales": ["Concepto"],
            "ejemplos_sugeridos": ["Ejemplo"],
            "recursos_visuales": [],
        },
        {
            "id": "s2", "orden": 2, "titulo": "Sección 2",
            "conceptos_principales": ["Concepto"],
            "ejemplos_sugeridos": ["Ejemplo"],
            "recursos_visuales": [],
        },
    ],
    "recursos_visuales_planificados": [],
}


def _seccion(seccion_id: str, orden: int) -> dict:
    return {
        "seccion_id": seccion_id,
        "orden": orden,
        "titulo": f"Sección {orden}",
        "bloques": [{"tipo": "paragraph", "contenido": "Contenido de prueba."}],
    }


def _ejercicio(numero: int) -> dict:
    return {
        "id": f"ej{numero}",
        "dificultad": "inicial",
        "tipo": "calculo",
        "consigna": "Consigna",
        "solucion": "Solución",
        "respuesta_final": "Respuesta",
    }


COMPONENTES = {
    "introduccion": "Introducción de prueba.",
    "resumen_final": "Resumen de prueba.",
    "glosario": [{"termino": "Término", "definicion": "Definición"}],
    "metadatos": {
        "titulo": "Título",
        "tema": "Tema",
        "disciplina": "Historia",
        "nivel": "Secundario",
    },
}


def _respuestas_felices() -> list:
    """Secuencia de respuestas válidas para un documento de 8 ejercicios."""
    return [
        json.dumps(PLAN),
        json.dumps(_seccion("s1", 1)),
        json.dumps(_seccion("s2", 2)),
        json.dumps({"ejercicios": [_ejercicio(1), _ejercicio(2), _ejercicio(3)]}),
        json.dumps({"ejercicios": [_ejercicio(4), _ejercicio(5), _ejercicio(6)]}),
        json.dumps({"ejercicios": [_ejercicio(7), _ejercicio(8)]}),
        json.dumps(COMPONENTES),
    ]


class TestProgresoPorEtapas(unittest.TestCase):
    """Los hitos de progreso deben reflejar operaciones reales."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _ejecutar(self, respuestas, eventos=None, trabajo_id="progreso"):
        eventos = eventos if eventos is not None else []
        generador = gb.GeneradorBloques()
        iterador = iter(respuestas)

        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=lambda *a, **k: (next(iterador), "gemini"),
        ), patch.object(gb, "construir_pdf", return_value=True), \
             patch.object(
                 generador, "_crear_carpeta_trabajo",
                 return_value=self.carpeta,
             ):
            resultado = generador.generar(
                tema="Tema",
                disciplina="Historia",
                nivel="Secundario",
                profundidad="breve",
                cantidad_actividades=8,
                recursos_visuales=False,
                usar_demostracion=False,
                trabajo_id=trabajo_id,
                callback_progreso=lambda p, e: eventos.append((p, e)),
            )
        return resultado, eventos

    def test_flujo_completo_emite_hitos_monotonos(self):
        """1. El progreso avanza y nunca retrocede."""
        resultado, eventos = self._ejecutar(_respuestas_felices())

        self.assertTrue(resultado["exito"], resultado["mensaje"])
        self.assertTrue(eventos)

        valores = [p for p, _ in eventos]
        self.assertEqual(
            valores, sorted(valores),
            f"El progreso retrocedió: {eventos}",
        )
        self.assertEqual(valores[-1], 1.0)

    def test_hitos_incluyen_plan_secciones_y_ejercicios(self):
        """2. Se informan plan, cada sección y cada lote de ejercicios."""
        _, eventos = self._ejecutar(_respuestas_felices())
        textos = [e for _, e in eventos]

        self.assertTrue(any("Planificación" in t for t in textos))
        self.assertTrue(any("Sección 1 de 2" in t for t in textos))
        self.assertTrue(any("Sección 2 de 2" in t for t in textos))
        self.assertTrue(any("lote 1 de 3" in t for t in textos))
        self.assertTrue(any("lote 3 de 3" in t for t in textos))
        self.assertTrue(any("PDF" in t for t in textos))

    def test_secciones_no_se_regeneran_si_ya_existen(self):
        """3. Un bloque validado en disco no se vuelve a pedir a la IA."""
        (self.carpeta / "plan.json").write_text(
            json.dumps(PLAN), encoding="utf-8"
        )
        (self.carpeta / "seccion_s1.json").write_text(
            json.dumps(_seccion("s1", 1)), encoding="utf-8"
        )
        (self.carpeta / "seccion_s2.json").write_text(
            json.dumps(_seccion("s2", 2)), encoding="utf-8"
        )

        llamadas = []

        def generar_simulado(instruccion, orden, proveedores_agotados=None,
                             **kwargs):
            llamadas.append(instruccion[:60])
            texto = instruccion.lower()
            # Solo deberían pedirse ejercicios y componentes finales.
            if "vas a generar" in texto and "ejercicios de dificultad" in texto:
                import re

                coincidencia = re.search(r"generar (\d+) ejercicios", texto)
                cantidad = int(coincidencia.group(1)) if coincidencia else 1
                return json.dumps(
                    {
                        "ejercicios": [
                            _ejercicio(len(llamadas) * 10 + n)
                            for n in range(cantidad)
                        ]
                    }
                ), "gemini"
            return json.dumps(COMPONENTES), "gemini"

        generador = gb.GeneradorBloques()
        with patch.object(
            gb, "generar_contenido_educativo", side_effect=generar_simulado
        ), patch.object(gb, "construir_pdf", return_value=True), \
             patch.object(
                 generador, "_crear_carpeta_trabajo", return_value=self.carpeta
             ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="reuso",
            )

        self.assertTrue(resultado["exito"], resultado["mensaje"])
        # Ninguna llamada debió pedir una sección teórica.
        self.assertFalse(
            any("sección" in l.lower() and "teóric" in l.lower() for l in llamadas),
            llamadas,
        )

    def test_seccion_truncada_se_recupera_con_version_mas_corta(self):
        """4. Tras un truncamiento, el reintento produce una sección válida."""
        truncada = '{"seccion_id": "s1", "orden": 1, "titulo": "S1", "bloques": ['
        respuestas = [
            json.dumps(PLAN),
            truncada,
            json.dumps(_seccion("s1", 1)),
            json.dumps(_seccion("s2", 2)),
            json.dumps({"ejercicios": [_ejercicio(1), _ejercicio(2), _ejercicio(3)]}),
            json.dumps({"ejercicios": [_ejercicio(4), _ejercicio(5), _ejercicio(6)]}),
            json.dumps({"ejercicios": [_ejercicio(7), _ejercicio(8)]}),
            json.dumps(COMPONENTES),
        ]

        resultado, eventos = self._ejecutar(respuestas, trabajo_id="truncada")

        self.assertTrue(resultado["exito"], resultado["mensaje"])
        # La respuesta truncada se conserva para diagnóstico.
        self.assertTrue((self.carpeta / "seccion_s1_crudo.json").exists())

    def test_reintentos_limitados_sin_bucle_infinito(self):
        """5. Un bloque que siempre falla agota los reintentos y termina."""
        respuestas = [json.dumps(PLAN)] + ["{invalido"] * 5

        resultado, _ = self._ejecutar(respuestas, trabajo_id="agotado")

        self.assertFalse(resultado["exito"])
        self.assertIn("sección", resultado["mensaje"].lower())

    def test_error_integracion_no_se_reintenta(self):
        """6. Un TypeError del SDK aborta de inmediato, sin reintentos."""
        generador = gb.GeneradorBloques()
        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=ErrorIntegracion("argumento no admitido"),
        ) as mock_generar, patch.object(
            generador, "_crear_carpeta_trabajo", return_value=self.carpeta
        ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="integracion",
            )

        self.assertFalse(resultado["exito"])
        self.assertIn("integración", resultado["mensaje"].lower())
        # Una sola llamada: no se reintenta un error de programación.
        self.assertEqual(mock_generar.call_count, 1)

    def test_error_proveedor_no_se_convierte_en_contenido(self):
        """7. Un fallo de proveedor no se trata como respuesta del modelo."""
        generador = gb.GeneradorBloques()
        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=ErrorIA("503 service unavailable"),
        ), patch.object(
            generador, "_crear_carpeta_trabajo", return_value=self.carpeta
        ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="proveedor",
            )

        self.assertFalse(resultado["exito"])
        self.assertIn("503", resultado["mensaje"])
        # No se guardó ningún plan: no hay contenido válido.
        self.assertFalse((self.carpeta / "plan.json").exists())

    def test_callback_que_falla_no_interrumpe(self):
        """8. Un fallo al refrescar la UI no cancela la generación."""
        def callback_roto(progreso, etapa):
            raise RuntimeError("An attempt to fetch destroyed session.")

        generador = gb.GeneradorBloques()
        iterador = iter(_respuestas_felices())
        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=lambda *a, **k: (next(iterador), "gemini"),
        ), patch.object(gb, "construir_pdf", return_value=True), \
             patch.object(
                 generador, "_crear_carpeta_trabajo", return_value=self.carpeta
             ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="callback_roto",
                callback_progreso=callback_roto,
            )

        self.assertTrue(resultado["exito"], resultado["mensaje"])

    def test_estado_final_completado(self):
        """9. El manifiesto solo queda completado si el PDF se construyó."""
        resultado, _ = self._ejecutar(_respuestas_felices(), trabajo_id="estado")

        self.assertTrue(resultado["exito"])
        estado = json.loads(
            (self.carpeta / "estado.json").read_text(encoding="utf-8")
        )
        self.assertEqual(estado["estado"], gb.ESTADO_COMPLETED)

    def test_estado_fallido_no_se_marca_completado(self):
        """10. Un fallo deja el manifiesto en failed, nunca en completed."""
        respuestas = [json.dumps(PLAN)] + ["{invalido"] * 5
        resultado, _ = self._ejecutar(respuestas, trabajo_id="fallido")

        self.assertFalse(resultado["exito"])
        estado = json.loads(
            (self.carpeta / "estado.json").read_text(encoding="utf-8")
        )
        self.assertEqual(estado["estado"], gb.ESTADO_FAILED)
        self.assertNotEqual(estado["estado"], gb.ESTADO_COMPLETED)


class TestCancelacionCooperativa(unittest.TestCase):
    """
    Al cerrar la ventana se pide detener el trabajo.

    La cancelación se comprueba en puntos seguros (entre bloques), nunca en
    medio de una solicitud HTTP. Los bloques ya validados se conservan.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _generar_con_cancelacion(self, evento, trabajo_id="cancelado"):
        generador = gb.GeneradorBloques()

        def proveedor(instruccion, orden, proveedores_agotados=None, **kwargs):
            # El plan se genera; en cuanto termina, el usuario cierra la ventana.
            evento.set()
            return json.dumps(PLAN), "gemini"

        with patch.object(
            gb, "generar_contenido_educativo", side_effect=proveedor
        ), patch.object(gb, "construir_pdf", return_value=True), \
             patch.object(
                 generador, "_crear_carpeta_trabajo", return_value=self.carpeta
             ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id=trabajo_id, cancelacion=evento,
            )
        return resultado

    def test_cancelacion_detiene_flujo_y_conserva_plan(self):
        """1. La cancelación corta el flujo sin borrar lo ya validado."""
        evento = threading.Event()
        resultado = self._generar_con_cancelacion(evento)

        self.assertFalse(resultado["exito"])
        self.assertTrue(resultado["cancelado"])
        self.assertIn("cancelada", resultado["mensaje"].lower())
        # El plan validado antes de la cancelación no se pierde.
        self.assertTrue((self.carpeta / "plan.json").exists())

    def test_cancelacion_no_marca_el_trabajo_como_completado(self):
        """2. Un trabajo cancelado queda `failed`, nunca `completed`."""
        evento = threading.Event()
        self._generar_con_cancelacion(evento, trabajo_id="cancelado_estado")

        estado = json.loads(
            (self.carpeta / "estado.json").read_text(encoding="utf-8")
        )
        self.assertEqual(estado["estado"], gb.ESTADO_FAILED)
        self.assertNotEqual(estado["estado"], gb.ESTADO_COMPLETED)
        self.assertEqual(estado.get("tipo_error"), "cancelado")

    def test_sin_cancelacion_el_flujo_termina(self):
        """3. Sin señal de cancelación, el flujo segmentado termina bien."""
        evento = threading.Event()  # nunca se activa
        generador = gb.GeneradorBloques()
        iterador = iter(_respuestas_felices())

        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=lambda *a, **k: (next(iterador), "gemini"),
        ), patch.object(gb, "construir_pdf", return_value=True), \
             patch.object(
                 generador, "_crear_carpeta_trabajo", return_value=self.carpeta
             ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="sin_cancelar", cancelacion=evento,
            )

        self.assertTrue(resultado["exito"], resultado["mensaje"])
        self.assertFalse(resultado["cancelado"])


class TestClavesConTilde(unittest.TestCase):
    """
    Un lote con claves acentuadas ("solución", "explicación") se normaliza
    y no debe hacer fallar la generación.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _ejercicio_acentuado(numero: int) -> dict:
        return {
            "id": f"ej{numero}",
            "dificultad": "inicial",
            "tipo": "calculo",
            "consigna": "Consigna",
            "solución": "Desarrollo de la solución.",
            "respuesta_final": "Respuesta",
            "explicación": "Justificación.",
        }

    def test_lote_con_claves_acentuadas_genera_documento(self):
        respuestas = [
            json.dumps(PLAN),
            json.dumps(_seccion("s1", 1)),
            json.dumps(_seccion("s2", 2)),
            json.dumps({"ejercicios": [
                self._ejercicio_acentuado(1),
                self._ejercicio_acentuado(2),
                self._ejercicio_acentuado(3),
            ]}),
            json.dumps({"ejercicios": [
                self._ejercicio_acentuado(4),
                self._ejercicio_acentuado(5),
                self._ejercicio_acentuado(6),
            ]}),
            json.dumps({"ejercicios": [
                self._ejercicio_acentuado(7),
                self._ejercicio_acentuado(8),
            ]}),
            json.dumps(COMPONENTES),
        ]

        generador = gb.GeneradorBloques()
        iterador = iter(respuestas)
        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=lambda *a, **k: (next(iterador), "gemini"),
        ), patch.object(gb, "construir_pdf", return_value=True), \
             patch.object(
                 generador, "_crear_carpeta_trabajo", return_value=self.carpeta
             ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="tildes",
            )

        self.assertTrue(resultado["exito"], resultado["mensaje"])

        documento = json.loads(
            (self.carpeta / "documento_ensamblado.json").read_text(
                encoding="utf-8"
            )
        )
        for actividad in documento["actividades"]:
            self.assertIn("solucion", actividad)
            self.assertNotIn("solución", actividad)
            self.assertTrue(actividad["solucion"])

        # El solucionario del PDF se arma desde 'solucion'.
        self.assertTrue(documento["solucionario"][0]["procedimiento"])


class TestDemostracion(unittest.TestCase):
    """El modo demostración construye un PDF sin llamar a ninguna API."""

    def test_demostracion_genera_pdf_y_progreso_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            eventos = []
            generador = gb.GeneradorBloques()

            with patch.object(
                generador, "_crear_carpeta_trabajo", return_value=carpeta
            ), patch.object(gb, "construir_pdf", return_value=True):
                resultado = generador.generar(
                    tema="Tema de demostración",
                    disciplina="Historia",
                    nivel="Secundario",
                    profundidad="breve",
                    cantidad_actividades=8,
                    recursos_visuales=True,
                    usar_demostracion=True,
                    trabajo_id="demo",
                    callback_progreso=lambda p, e: eventos.append((p, e)),
                )

            self.assertTrue(resultado["exito"], resultado["mensaje"])
            self.assertEqual(eventos[-1][0], 1.0)
            self.assertTrue((carpeta / "material_validado.json").exists())
            self.assertTrue((carpeta / "documento_ensamblado.json").exists())


if __name__ == "__main__":
    unittest.main()
