"""
Pruebas de robustez ante campos obligatorios faltantes.

Cubren:
- completar sólo campos derivables (dificultad e id), sin inventar contenido;
- reintentar un lote o los componentes inválidos en vez de abortar;
- que el reintento incluya una instrucción correctiva con los errores.

No se realizan llamadas reales: el proveedor está sustituido por un doble.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generador_bloques as gb
from esquemas_bloques import validar_lote_ejercicios

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


def _ejercicio(numero=1, con_dificultad=True, con_consigna=True):
    ejercicio = {
        "id": f"act{numero}",
        "tipo": "calculo",
        "solucion": "S",
        "respuesta_final": "R",
    }
    if con_dificultad:
        ejercicio["dificultad"] = "inicial"
    if con_consigna:
        ejercicio["consigna"] = "C"
    return ejercicio


class TestCamposDerivables(unittest.TestCase):
    """Sólo se completan campos que el programa ya conoce."""

    def test_completa_dificultad_e_id_faltantes(self):
        """1. Dificultad e id se completan y el lote pasa a ser válido."""
        lote = {"ejercicios": [{
            "tipo": "calculo", "consigna": "C", "solucion": "S",
            "respuesta_final": "R",
        }]}

        resultado = gb._completar_campos_derivables_ejercicios(
            lote, "avanzado", 7
        )

        ejercicio = resultado["ejercicios"][0]
        self.assertEqual(ejercicio["dificultad"], "avanzado")
        self.assertEqual(ejercicio["id"], "act7")
        ok, errores = validar_lote_ejercicios(resultado)
        self.assertTrue(ok, errores)

    def test_normaliza_variantes_de_dificultad(self):
        """2. Variantes como 'media' o 'básico' se normalizan."""
        casos = [("media", "intermedio"), ("básico", "inicial"),
                 ("difícil", "avanzado")]

        for variante, esperada in casos:
            lote = {"ejercicios": [{"dificultad": variante}]}
            resultado = gb._completar_campos_derivables_ejercicios(
                lote, "inicial", 1
            )
            self.assertEqual(
                resultado["ejercicios"][0]["dificultad"], esperada
            )

    def test_no_inventa_campos_de_contenido(self):
        """3. La consigna faltante no se inventa: el lote sigue siendo inválido."""
        lote = {"ejercicios": [{
            "id": "act1", "dificultad": "inicial", "tipo": "calculo",
            "solucion": "S", "respuesta_final": "R",
        }]}

        resultado = gb._completar_campos_derivables_ejercicios(
            lote, "inicial", 1
        )

        self.assertNotIn("consigna", resultado["ejercicios"][0])
        ok, errores = validar_lote_ejercicios(resultado)
        self.assertFalse(ok)
        self.assertTrue(any("consigna" in error for error in errores))


class TestReintentoPorEsquema(unittest.TestCase):
    """Un fallo de esquema se reintenta con feedback, no aborta de inmediato."""

    def setUp(self):
        self.generador = gb.GeneradorBloques()
        self.generador.plan = PLAN

    def test_lote_invalido_se_reintenta_con_instruccion_correctiva(self):
        """4. Un lote sin 'consigna' se reintenta y termina bien."""
        respuestas = [
            json.dumps({"ejercicios": [_ejercicio(con_consigna=False)]}),
            json.dumps({"ejercicios": [_ejercicio()]}),
        ]
        instrucciones = []

        def proveedor(instruccion, orden, proveedores_agotados=None, **kwargs):
            instrucciones.append(instruccion)
            return respuestas.pop(0), "gemini"

        with patch.object(gb, "generar_contenido_educativo",
                          side_effect=proveedor), \
             patch.object(self.generador, "_guardar_respuesta_cruda"), \
             patch.object(self.generador, "_guardar_bloque_validado"):
            lote = self.generador._generar_un_lote_ejercicios(
                "inicial", 1, 1, "breve"
            )

        self.assertEqual(len(lote), 1)
        self.assertEqual(len(instrucciones), 2)
        self.assertIn("NO cumplió el esquema", instrucciones[1])
        self.assertIn("consigna", instrucciones[1])

    def test_lote_sin_dificultad_se_completa_sin_reintento(self):
        """5. El caso real (falta 'dificultad') se resuelve sin gastar un reintento."""
        respuesta = {"ejercicios": [{
            "id": "act1", "tipo": "calculo", "consigna": "C",
            "solucion": "S", "respuesta_final": "R",
        }]}
        llamadas = []

        def proveedor(instruccion, orden, proveedores_agotados=None, **kwargs):
            llamadas.append(instruccion)
            return json.dumps(respuesta), "gemini"

        with patch.object(gb, "generar_contenido_educativo",
                          side_effect=proveedor), \
             patch.object(self.generador, "_guardar_respuesta_cruda"), \
             patch.object(self.generador, "_guardar_bloque_validado"):
            lote = self.generador._generar_un_lote_ejercicios(
                "avanzado", 1, 1, "breve"
            )

        self.assertEqual(len(llamadas), 1)
        self.assertEqual(lote[0]["dificultad"], "avanzado")
        self.assertEqual(lote[0]["id"], "act1")

    def test_componentes_invalidos_se_reintentan(self):
        """6. Unos componentes sin 'glosario' se reintentan y terminan bien."""
        invalidos = {
            "resumen_final": "R",
            "metadatos": {"titulo": "T", "tema": "T",
                          "disciplina": "D", "nivel": "N"},
        }
        validos = {
            "resumen_final": "R",
            "glosario": [{"termino": "T", "definicion": "D"}],
            "metadatos": {"titulo": "T", "tema": "T",
                          "disciplina": "D", "nivel": "N"},
        }
        respuestas = [json.dumps(invalidos), json.dumps(validos)]
        instrucciones = []

        def proveedor(instruccion, orden, proveedores_agotados=None, **kwargs):
            instrucciones.append(instruccion)
            return respuestas.pop(0), "gemini"

        with patch.object(gb, "generar_contenido_educativo",
                          side_effect=proveedor), \
             patch.object(self.generador, "_guardar_respuesta_cruda"), \
             patch.object(self.generador, "_guardar_bloque_validado"):
            componentes = self.generador._generar_componentes_finales()

        self.assertEqual(componentes["resumen_final"], "R")
        self.assertEqual(len(instrucciones), 2)
        self.assertIn("NO cumplió el esquema", instrucciones[1])
        self.assertIn("glosario", instrucciones[1])


if __name__ == "__main__":
    unittest.main()
