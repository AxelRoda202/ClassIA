"""
Pruebas para el generador de bloques segmentados (generador_bloques.py).

Pruebas de unidad para los esquemas de validación y el modo demostración.
Las pruebas de integración completa con mocks de API están en test_integracion.py.
"""
import sys
import os
import json
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generador_bloques import GeneradorBloques, ErrorBloque
from esquemas_bloques import (
    validar_plan_aprendizaje,
    validar_seccion_teorica,
    validar_lote_ejercicios,
    validar_componentes_finales,
    validar_documento_ensamblado,
)
from validador import validar_estructura_material
from generador_pdf import construir_pdf
from configuracion import CARPETA_TEMPORAL


class TestEsquemasBloques(unittest.TestCase):
    """Pruebas para los esquemas de validación de bloques."""

    def test_plan_aprendizaje_valido(self):
        """Plan válido pasa la validación."""
        plan = {
            "titulo": "Test Plan",
            "disciplina": "Historia",
            "nivel": "Secundario",
            "profundidad": "breve",
            "objetivos_aprendizaje": ["O1"],
            "conocimientos_previos": ["CP1"],
            "secciones": [{"id": "s1", "orden": 1, "titulo": "S1",
                          "conceptos_principales": [], "ejemplos_sugeridos": [],
                          "recursos_visuales": []}],
            "recursos_visuales_planificados": [],
            "distribucion_actividades": {"inicial": 1, "intermedio": 0, "avanzado": 0},
        }
        valido, errores = validar_plan_aprendizaje(plan)
        self.assertTrue(valido, f"Errores: {errores}")

    def test_plan_sin_secciones_rechazado(self):
        """Plan sin secciones es rechazado."""
        plan = {
            "titulo": "Test", "disciplina": "H", "nivel": "S",
            "profundidad": "b", "objetivos_aprendizaje": [],
            "conocimientos_previos": [], "secciones": [],
            "recursos_visuales_planificados": [],
            "distribucion_actividades": {},
        }
        valido, errores = validar_plan_aprendizaje(plan)
        self.assertFalse(valido)

    def test_seccion_teorica_valida(self):
        """Sección teórica válida pasa la validación."""
        seccion = {
            "seccion_id": "s1", "orden": 1, "titulo": "S1",
            "bloques": [
                {"tipo": "heading", "texto": "T"},
                {"tipo": "paragraph", "texto": "C"},
                {"tipo": "definition", "termino": "t", "definicion": "d"},
                {"tipo": "visual_reference", "recurso_id": "r1",
                 "posicion": "despues_bloque"},
            ],
        }
        valido, errores = validar_seccion_teorica(seccion)
        self.assertTrue(valido, f"Errores: {errores}")

    def test_lote_ejercicios_valido(self):
        """Lote de ejercicios válido pasa la validación."""
        lote = {
            "ejercicios": [{"id": "act1", "dificultad": "inicial",
                          "tipo": "calculo", "consigna": "P",
                          "datos": None, "pista": None,
                          "solucion": "S", "respuesta_final": "R",
                          "explicacion": "E", "criterios_correccion": "C"}],
        }
        valido, errores = validar_lote_ejercicios(lote)
        self.assertTrue(valido, f"Errores: {errores}")

    def test_documento_ensamblado_valido(self):
        """Documento ensamblado válido pasa la validación."""
        doc = {
            "metadatos": {"titulo": "T", "tema": "T", "disciplina": "D",
                          "nivel": "N"},
            "objetivos_aprendizaje": [], "conocimientos_previos": [],
            "introduccion": "I", "secciones": [],
            "ejemplos_resueltos": [], "actividades": [],
            "solucionario": [], "glosario": [],
            "resumen_final": "R", "recursos_visuales": [],
        }
        valido, errores = validar_documento_ensamblado(doc)
        self.assertTrue(valido, f"Errores: {errores}")


class TestGeneradorBloquesModoDemostracion(unittest.TestCase):
    """Pruebas del generador de bloques en modo demostración."""

    def setUp(self):
        self.generador = GeneradorBloques()

    def test_generacion_demostracion_completa(self):
        """Modo demostración genera PDF completo sin API."""
        resultado = self.generador.generar(
            tema="Funciones cuadráticas",
            disciplina="Matemática",
            nivel="Secundario",
            profundidad="estándar",
            cantidad_actividades=10,
            recursos_visuales=True,
            usar_demostracion=True,
        )

        self.assertTrue(resultado["exito"], f"Fallo: {resultado.get('mensaje')}")
        self.assertIsNotNone(resultado["ruta_pdf"])
        self.assertTrue(Path(resultado["ruta_pdf"]).exists())
        self.assertGreater(Path(resultado["ruta_pdf"]).stat().st_size, 1000)

    def test_regenerar_desde_trabajo_demostracion(self):
        """Regenerar PDF desde trabajo de demostración guardado."""
        generador = GeneradorBloques()
        resultado = generador.generar(
            tema="Revolución Francesa",
            disciplina="Historia y geografía",
            nivel="Secundario",
            profundidad="breve",
            cantidad_actividades=8,
            recursos_visuales=False,
            usar_demostracion=True,
        )

        self.assertTrue(resultado["exito"], f"Fallo: {resultado.get('mensaje')}")
        trabajo_id = resultado["trabajo_id"]

        generador2 = GeneradorBloques()
        recuperacion = generador2.regenerar_desde_trabajo(trabajo_id)

        self.assertTrue(recuperacion["exito"], f"Fallo: {recuperacion.get('mensaje')}")
        self.assertIsNotNone(recuperacion["ruta_pdf"])
        self.assertTrue(Path(recuperacion["ruta_pdf"]).exists())

    def test_preservacion_respuestas_crudas_demostracion(self):
        """Modo demostración guarda material validado en disco."""
        generador = GeneradorBloques()
        resultado = generador.generar(
            tema="Test",
            disciplina="Historia",
            nivel="Secundario",
            profundidad="breve",
            cantidad_actividades=5,
            recursos_visuales=False,
            usar_demostracion=True,
        )

        self.assertTrue(resultado["exito"])

        carpeta = CARPETA_TEMPORAL / resultado["trabajo_id"]
        self.assertTrue((carpeta / "material_validado.json").exists())
        self.assertTrue((carpeta / "documento_ensamblado.json").exists())
        self.assertTrue((carpeta / "estado.json").exists())

    def test_pdf_con_datos_simulados(self):
        """PDF se genera con datos simulados sin llamada a API."""
        desde_modelos = __import__("modelos_datos")
        material = desde_modelos.ejemplo_matematica()
        material["metadatos"]["tema"] = "Funciones cuadráticas"
        material["metadatos"]["modo_demostracion"] = True

        carpeta = CARPETA_TEMPORAL / "test_pdf_simulado"
        carpeta.mkdir(parents=True, exist_ok=True)

        rutas_graficos = {}
        ruta_pdf = carpeta / "test.pdf"

        exito = construir_pdf(material, rutas_graficos, ruta_pdf)
        self.assertTrue(exito)
        self.assertTrue(ruta_pdf.exists())
        self.assertGreater(ruta_pdf.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
