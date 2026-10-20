"""
Pruebas de recuperación de trabajos interrumpidos.

Verifican que `regenerar_desde_trabajo`:
- no reutilice respuestas crudas (`*_crudo.json`) como si fueran bloques
  validados;
- no cuente bloques dos veces;
- no ensamble un documento al que le falten secciones planificadas;
- no construya un PDF cuando falta contenido obligatorio.

No se realizan llamadas reales: `construir_pdf` está sustituido por un doble.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generador_bloques as gb


PLAN = {
    "titulo": "Plan de recuperación",
    "disciplina": "Historia",
    "nivel": "Secundario",
    "profundidad": "breve",
    "objetivos_aprendizaje": ["Objetivo"],
    "conocimientos_previos": ["Conocimiento"],
    "secciones": [
        {"id": "s1", "orden": 1, "titulo": "Sección 1",
         "conceptos_principales": ["c"], "ejemplos_sugeridos": ["e"],
         "recursos_visuales": []},
        {"id": "s2", "orden": 2, "titulo": "Sección 2",
         "conceptos_principales": ["c"], "ejemplos_sugeridos": ["e"],
         "recursos_visuales": []},
    ],
    "recursos_visuales_planificados": [],
}

COMPONENTES = {
    "introduccion": "Introducción.",
    "resumen_final": "Resumen final.",
    "glosario": [{"termino": "T", "definicion": "D"}],
    "metadatos": {"titulo": "Título", "tema": "Tema",
                  "disciplina": "Historia", "nivel": "Secundario"},
}


def _seccion(sid: str, orden: int) -> dict:
    return {
        "seccion_id": sid,
        "orden": orden,
        "titulo": f"Sección {orden}",
        "bloques": [{"tipo": "paragraph", "texto": "Contenido real."}],
    }


def _seccion_invalida(sid: str, orden: int) -> dict:
    return {
        "seccion_id": sid,
        "orden": orden,
        "titulo": f"Sección {orden}",
        "bloques": [{"tipo": "paragraph", "texto": ""}],
    }


def _lote(ids) -> dict:
    return {
        "ejercicios": [
            {"id": i, "dificultad": "inicial", "tipo": "calculo",
             "consigna": "Consigna", "solucion": "Solución",
             "respuesta_final": "Respuesta"}
            for i in ids
        ]
    }


def _lote_dificultad(ids, dificultad: str) -> dict:
    lote = _lote(ids)
    for ejercicio in lote["ejercicios"]:
        ejercicio["dificultad"] = dificultad
    return lote


class TestRecuperacionDesdeBloques(unittest.TestCase):
    """Recuperación usando bloques guardados."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.carpeta = self.base / "rec"
        self.carpeta.mkdir()
        (self.carpeta / "estado.json").write_text(
            json.dumps({"trabajo_id": "rec", "estado": "failed"}),
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _escribir(self, nombre: str, datos) -> None:
        (self.carpeta / nombre).write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8"
        )

    def _recuperar(self):
        mock_pdf = MagicMock(return_value=True)
        with patch.object(gb, "CARPETA_TEMPORAL", self.base), \
             patch.object(gb, "CARPETA_SALIDA", self.base / "salida"), \
             patch.object(gb, "construir_pdf", mock_pdf):
            resultado = gb.GeneradorBloques().regenerar_desde_trabajo("rec")
        return resultado, mock_pdf

    def test_ignora_crudos_y_no_duplica_ejercicios(self):
        """1. Los *_crudo.json no se reutilizan ni duplican ejercicios."""
        self._escribir("plan.json", PLAN)
        self._escribir("seccion_s1.json", _seccion("s1", 1))
        # Copia cruda de la misma sección: no debe contarse dos veces.
        self._escribir("seccion_s1_crudo.json", _seccion("s1", 1))
        self._escribir("seccion_s2.json", _seccion("s2", 2))
        self._escribir("lote_ejercicios_inicial_1.json", _lote(["act1", "act2"]))
        # Lote crudo con los mismos ids: no debe incorporarse.
        self._escribir("lote_ejercicios_inicial_2_crudo.json", _lote(["act1", "act2"]))
        self._escribir("lote_ejercicios_intermedio_3.json",
                       _lote(["act3", "act4", "act5"]))
        self._escribir("componentes_finales.json", COMPONENTES)

        resultado, mock_pdf = self._recuperar()

        self.assertTrue(resultado["exito"], resultado["mensaje"])
        mock_pdf.assert_called_once()
        documento = mock_pdf.call_args[0][0]

        ids_seccion = [s["seccion_id"] for s in documento["secciones"]]
        self.assertEqual(ids_seccion, ["s1", "s2"])

        ids_actividad = [a["id"] for a in documento["actividades"]]
        self.assertEqual(ids_actividad, ["act1", "act2", "act3", "act4", "act5"])
        self.assertEqual(len(ids_actividad), len(set(ids_actividad)))

    def test_deduplica_ids_repetidos_entre_lotes_validos(self):
        """2. Si dos lotes válidos repiten un id, se usa una sola vez."""
        self._escribir("plan.json", PLAN)
        self._escribir("seccion_s1.json", _seccion("s1", 1))
        self._escribir("seccion_s2.json", _seccion("s2", 2))
        self._escribir("lote_ejercicios_inicial_1.json", _lote(["act1", "act2"]))
        self._escribir("lote_ejercicios_intermedio_3.json", _lote(["act2", "act3"]))
        self._escribir("componentes_finales.json", COMPONENTES)

        resultado, mock_pdf = self._recuperar()

        self.assertTrue(resultado["exito"], resultado["mensaje"])
        documento = mock_pdf.call_args[0][0]
        ids_actividad = [a["id"] for a in documento["actividades"]]
        self.assertEqual(sorted(ids_actividad), ["act1", "act2", "act3"])

    def test_no_ensambla_si_falta_una_seccion(self):
        """3. No se genera PDF si falta una sección planificada."""
        self._escribir("plan.json", PLAN)
        self._escribir("seccion_s1.json", _seccion("s1", 1))
        self._escribir("seccion_s2.json", _seccion_invalida("s2", 2))
        self._escribir("lote_ejercicios_inicial_1.json", _lote(["act1"]))
        self._escribir("componentes_finales.json", COMPONENTES)

        resultado, mock_pdf = self._recuperar()

        self.assertFalse(resultado["exito"])
        self.assertIn("s2", resultado["mensaje"])
        mock_pdf.assert_not_called()

    def test_crudo_no_cuenta_como_seccion_valida(self):
        """4. Una sección sin validar no reemplaza a la sección real."""
        self._escribir("plan.json", PLAN)
        # Sólo existe el crudo de s1 (no la sección validada).
        self._escribir("seccion_s1_crudo.json", _seccion("s1", 1))
        self._escribir("seccion_s2.json", _seccion("s2", 2))
        self._escribir("lote_ejercicios_inicial_1.json", _lote(["act1"]))
        self._escribir("componentes_finales.json", COMPONENTES)

        resultado, mock_pdf = self._recuperar()

        self.assertFalse(resultado["exito"])
        self.assertIn("s1", resultado["mensaje"])
        mock_pdf.assert_not_called()


class TestAnalisisYReanudacion(unittest.TestCase):
    """Análisis de trabajos y reanudación sin repetir bloques."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.carpeta = self.base / "rec"
        self.carpeta.mkdir()
        self.configuracion = {
            "tema": "Tema de prueba",
            "disciplina": "Historia",
            "nivel": "Secundario",
            "profundidad": "breve",
            "cantidad_actividades": 8,
            "recursos_visuales": False,
            "usar_imagenes_externas": False,
            "usar_demostracion": False,
        }
        self._escribir("estado.json", {
            "trabajo_id": "rec",
            "estado": "failed",
            "configuracion": self.configuracion,
        })
        self._escribir("configuracion.json", self.configuracion)
        self._escribir("plan.json", PLAN)
        self._escribir("seccion_s1.json", _seccion("s1", 1))
        self._escribir("seccion_s2.json", _seccion("s2", 2))
        self._escribir(
            "lote_ejercicios_inicial_1.json",
            _lote_dificultad(["act1", "act2"], "inicial"),
        )
        self._escribir(
            "lote_ejercicios_intermedio_3.json",
            _lote_dificultad(["act3", "act4", "act5"], "intermedio"),
        )
        self._escribir(
            "lote_ejercicios_avanzado_6.json",
            _lote_dificultad(["act6", "act7", "act8"], "avanzado"),
        )
        self._escribir("componentes_finales.json", COMPONENTES)

    def tearDown(self):
        self._tmp.cleanup()

    def _escribir(self, nombre: str, datos) -> None:
        (self.carpeta / nombre).write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8"
        )

    def test_analizar_trabajo_cuenta_bloques_y_configuracion(self):
        with patch.object(gb, "CARPETA_TEMPORAL", self.base):
            generador = gb.GeneradorBloques()
            info = generador.analizar_trabajo("rec")
            lista = generador.listar_trabajos_recuperables()

        self.assertIsNotNone(info)
        self.assertEqual(info["secciones_ok"], 2)
        self.assertEqual(info["secciones_total"], 2)
        self.assertEqual(info["ejercicios"], 8)
        self.assertTrue(info["componentes"])
        self.assertTrue(info["puede_reconstruir_sin_ia"])
        self.assertTrue(info["puede_continuar_con_ia"])
        self.assertEqual(info["configuracion"]["tema"], "Tema de prueba")
        self.assertEqual([item["trabajo_id"] for item in lista], ["rec"])

    def test_trabajo_completado_con_pdf_no_se_lista(self):
        pdf = self.base / "listo.pdf"
        pdf.write_bytes(b"%PDF-1.4 prueba")
        self._escribir("estado.json", {
            "trabajo_id": "rec",
            "estado": "completed",
            "ruta_pdf": str(pdf),
            "configuracion": self.configuracion,
        })
        with patch.object(gb, "CARPETA_TEMPORAL", self.base):
            lista = gb.GeneradorBloques().listar_trabajos_recuperables()
        self.assertEqual(lista, [])

    def test_guardar_estado_conserva_configuracion(self):
        generador = gb.GeneradorBloques()
        generador.trabajo_id = "rec"
        generador.carpeta_trabajo = self.carpeta

        generador._guardar_estado(
            gb.ESTADO_FAILED, {"tipo_error": "prueba"}, "fallo"
        )

        estado = json.loads(
            (self.carpeta / "estado.json").read_text(encoding="utf-8")
        )
        self.assertEqual(estado["estado"], gb.ESTADO_FAILED)
        self.assertEqual(estado["mensaje_error"], "fallo")
        self.assertEqual(estado["tipo_error"], "prueba")
        self.assertEqual(
            estado["configuracion"]["tema"], "Tema de prueba"
        )

    def test_continuar_reutiliza_todos_los_bloques_sin_ia(self):
        mock_pdf = MagicMock(return_value=True)
        with patch.object(gb, "CARPETA_TEMPORAL", self.base), \
             patch.object(gb, "CARPETA_SALIDA", self.base / "salida"), \
             patch.object(gb, "construir_pdf", mock_pdf), \
             patch.object(
                 gb, "generar_contenido_educativo",
                 side_effect=AssertionError("No debe llamar a la IA"),
             ):
            resultado = gb.GeneradorBloques().continuar_desde_trabajo("rec")

        self.assertTrue(resultado["exito"], resultado.get("mensaje"))
        actividades = resultado["material"]["actividades"]
        self.assertEqual(len(actividades), 8)
        ids = [actividad["id"] for actividad in actividades]
        self.assertEqual(len(ids), len(set(ids)))
        mock_pdf.assert_called_once()

    def test_reanudar_solo_genera_la_dificultad_faltante(self):
        (self.carpeta / "lote_ejercicios_avanzado_6.json").unlink()
        generador = gb.GeneradorBloques()
        generador.carpeta_trabajo = self.carpeta
        generador.plan = PLAN
        generador._reanudando = True
        llamadas = []

        def _fake(dificultad, cantidad, contador_inicio, profundidad):
            llamadas.append((dificultad, cantidad, contador_inicio))
            return _lote_dificultad(
                [f"act{contador_inicio + i}" for i in range(cantidad)],
                dificultad,
            )["ejercicios"]

        with patch.object(
            generador, "_generar_un_lote_ejercicios", side_effect=_fake
        ):
            ejercicios = generador._generar_ejercicios(8, "breve")

        self.assertEqual(len(ejercicios), 8)
        self.assertEqual(llamadas, [("avanzado", 3, 6)])
        ids = [ejercicio["id"] for ejercicio in ejercicios]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            set(ids),
            {"act1", "act2", "act3", "act4", "act5",
             "act6", "act7", "act8"},
        )


if __name__ == "__main__":
    unittest.main()
