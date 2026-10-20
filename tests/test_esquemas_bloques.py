"""
Pruebas para los esquemas de datos de bloques (esquemas_bloques.py).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from esquemas_bloques import (
    validar_plan_aprendizaje,
    validar_seccion_teorica,
    validar_lote_ejercicios,
    validar_componentes_finales,
    validar_documento_ensamblado,
)


class TestEsquemasBloques(unittest.TestCase):
    """Pruebas para los esquemas de validación de bloques."""

    # ------------------------------------------------------------------
    # Plan de aprendizaje
    # ------------------------------------------------------------------

    def test_plan_aprendizaje_valido(self):
        """Plan válido pasa la validación."""
        plan = {
            "titulo": "Caída del Imperio Romano",
            "disciplina": "Historia y geografía",
            "nivel": "Secundario",
            "profundidad": "estándar",
            "objetivos_aprendizaje": ["Entender causas", "Analizar consecuencias"],
            "conocimientos_previos": ["Edad Antigua"],
            "secciones": [
                {
                    "id": "s1",
                    "orden": 1,
                    "titulo": "Crisis del siglo III",
                    "conceptos_principales": ["inestabilidad", "invasiones"],
                    "ejemplos_sugeridos": ["ejemplo 1"],
                    "recursos_visuales": [
                        {
                            "id": "r1",
                            "tipo": "timeline",
                            "titulo": "Línea de tiempo",
                            "descripcion": "Eventos clave",
                            "ubicacion": {
                                "seccion_id": "s1",
                                "posicion": "despues_bloque",
                                "bloque_referencia": None,
                                "orden_relativo": 1,
                            },
                        }
                    ],
                }
            ],
            "recursos_visuales_planificados": [
                {
                    "id": "r1",
                    "type": "timeline",
                    "title": "Línea de tiempo",
                    "educational_purpose": "Visualizar cronología",
                    "description": "Eventos clave del siglo III",
                    "image_generation_prompt": "Línea de tiempo histórica",
                    "alt_text": "Línea temporal",
                    "caption": "Eventos del siglo III",
                    "ubicacion": {
                        "seccion_id": "s1",
                        "posicion": "despues_bloque",
                        "bloque_referencia": None,
                        "orden_relativo": 1,
                    },
                    "render_strategy": "timeline",
                    "data": {},
                    "status": "pendiente",
                    "generated_asset_path": None,
                }
            ],
            "distribucion_actividades": {"inicial": 3, "intermedio": 4, "avanzado": 3},
        }
        valido, errores = validar_plan_aprendizaje(plan)
        self.assertTrue(valido, f"Errores: {errores}")

    def test_plan_sin_secciones(self):
        """Plan sin secciones es rechazado."""
        plan = {
            "titulo": "Test",
            "disciplina": "Historia",
            "nivel": "Secundario",
            "profundidad": "breve",
            "objetivos_aprendizaje": [],
            "conocimientos_previos": [],
            "secciones": [],
            "recursos_visuales_planificados": [],
            "distribucion_actividades": {},
        }
        valido, errores = validar_plan_aprendizaje(plan)
        self.assertFalse(valido)
        self.assertTrue(any("una sección" in e for e in errores))

    def test_plan_campos_faltantes(self):
        """Plan con campos obligatorios faltantes es rechazado."""
        plan = {"titulo": "Test"}
        valido, errores = validar_plan_aprendizaje(plan)
        self.assertFalse(valido)
        self.assertGreater(len(errores), 0)

    # ------------------------------------------------------------------
    # Sección teórica
    # ------------------------------------------------------------------

    def test_seccion_teorica_valida(self):
        """Sección teórica válida pasa la validación."""
        seccion = {
            "seccion_id": "s1",
            "orden": 1,
            "titulo": "Crisis del siglo III",
            "bloques": [
                {"tipo": "heading", "texto": "Introducción"},
                {"tipo": "paragraph", "texto": "Texto explicativo"},
                {"tipo": "definition", "termino": "Crisis", "definicion": "Período difícil"},
                {"tipo": "visual_reference", "recurso_id": "r1", "posicion": "despues_bloque"},
            ],
        }
        valido, errores = validar_seccion_teorica(seccion)
        self.assertTrue(valido, f"Errores: {errores}")

    def test_seccion_tipo_invalido(self):
        """Sección con tipo de bloque inválido es rechazada."""
        seccion = {
            "seccion_id": "s1",
            "orden": 1,
            "titulo": "Test",
            "bloques": [
                {"tipo": "tipo_inexistente", "texto": "texto"},
            ],
        }
        valido, errores = validar_seccion_teorica(seccion)
        self.assertFalse(valido)
        self.assertTrue(any("tipo" in e.lower() for e in errores))

    # ------------------------------------------------------------------
    # Lote de ejercicios
    # ------------------------------------------------------------------

    def test_lote_ejercicios_valido(self):
        """Lote de ejercicios válido pasa la validación."""
        lote = {
            "ejercicios": [
                {
                    "id": "act1",
                    "dificultad": "inicial",
                    "tipo": "calculo",
                    "consigna": "Pregunta 1",
                    "datos": None,
                    "pista": None,
                    "solucion": "Respuesta 1",
                    "respuesta_final": "R1",
                    "explicacion": "Explicación 1",
                    "criterios_correccion": "Criterios 1",
                }
            ],
        }
        valido, errores = validar_lote_ejercicios(lote)
        self.assertTrue(valido, f"Errores: {errores}")

    def test_lote_dificultad_invalida(self):
        """Lote con dificultad inválida es rechazado."""
        lote = {
            "ejercicios": [
                {
                    "id": "act1",
                    "dificultad": "imposible",
                    "tipo": "calculo",
                    "consigna": "Pregunta",
                    "solucion": "Solución",
                    "respuesta_final": "R",
                    "explicacion": "Exp",
                    "criterios_correccion": "Crit",
                }
            ],
        }
        valido, errores = validar_lote_ejercicios(lote)
        self.assertFalse(valido)
        self.assertTrue(any("dificultad" in e.lower() for e in errores))

    # ------------------------------------------------------------------
    # Componentes finales
    # ------------------------------------------------------------------

    def test_componentes_finales_validos(self):
        """Componentes finales válidos pasan la validación."""
        componentes = {
            "metadatos": {
                "titulo": "Material",
                "subtitulo": "Sub",
                "tema": "Tema",
                "disciplina": "Historia",
                "nivel": "Secundario",
                "profundidad": "breve",
                "cantidad_actividades": 10,
                "fecha_generacion": "01/01/2024",
                "generado_por_ia": True,
                "modo_demostracion": False,
            },
            "introduccion": "Intro",
            "resumen_final": "Resumen",
            "glosario": [{"termino": "T1", "definicion": "D1"}],
            "fuentes": [],
        }
        valido, errores = validar_componentes_finales(componentes)
        self.assertTrue(valido, f"Errores: {errores}")

    # ------------------------------------------------------------------
    # Documento ensamblado
    # ------------------------------------------------------------------

    def test_documento_ensamblado_valido(self):
        """Documento ensamblado válido pasa la validación."""
        doc = {
            "metadatos": {"titulo": "T", "tema": "T", "disciplina": "D", "nivel": "N"},
            "objetivos_aprendizaje": [],
            "conocimientos_previos": [],
            "introduccion": "Intro",
            "secciones": [],
            "ejemplos_resueltos": [],
            "actividades": [],
            "solucionario": [],
            "glosario": [],
            "resumen_final": "Resumen",
            "recursos_visuales": [],
        }
        valido, errores = validar_documento_ensamblado(doc)
        self.assertTrue(valido, f"Errores: {errores}")


if __name__ == "__main__":
    unittest.main()
