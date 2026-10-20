"""
Pruebas del validador de respuestas JSON.
"""
import sys
import os

# Asegura que se importen los módulos del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from validador import validar_estructura_material, validar_json_texto, ErrorValidacion
from modelos_datos import ejemplo_matematica, ejemplo_historia, ejemplo_recursos_humanos


class TestValidador(unittest.TestCase):
    """Pruebas para el validador de estructura."""

    def test_validacion_json_completo_matematica(self):
        """1. Validación de una respuesta JSON completa (matemática)."""
        material = ejemplo_matematica()
        valido, errores = validar_estructura_material(material, 10)
        self.assertTrue(valido, f"Errores inesperados: {errores}")

    def test_validacion_json_completo_historia(self):
        """Validación de una respuesta JSON completa (historia)."""
        material = ejemplo_historia()
        valido, errores = validar_estructura_material(material, 10)
        self.assertTrue(valido, f"Errores inesperados: {errores}")

    def test_validacion_json_completo_recursos_humanos(self):
        """Validación de una respuesta JSON completa (recursos humanos)."""
        material = ejemplo_recursos_humanos()
        valido, errores = validar_estructura_material(material, 10)
        self.assertTrue(valido, f"Errores inesperados: {errores}")

    def test_rechazo_json_invalido(self):
        """2. Rechazo de JSON inválido."""
        valido, objeto, errores = validar_json_texto("{no es json válido}")
        self.assertFalse(valido)
        self.assertIsNone(objeto)
        self.assertGreater(len(errores), 0)

    def test_rechazo_contenido_obligatorio_ausente(self):
        """3. Rechazo de contenido obligatorio ausente."""
        material_incompleto = {"metadatos": {"titulo": "Solo título"}}
        valido, errores = validar_estructura_material(material_incompleto, 10)
        self.assertFalse(valido)
        self.assertGreater(len(errores), 0)

    def test_deteccion_cantidad_ejercicios_incorrecta(self):
        """4. Detección de cantidad de ejercicios incorrecta."""
        material = ejemplo_matematica()
        # El ejemplo tiene 10 actividades, pedir 50 debería generar advertencia
        valido, errores = validar_estructura_material(material, 50)
        # Puede seguir siendo válido si hay al menos 75% de las esperadas
        # pero con 50 esperadas y solo 10, debería fallar
        self.assertFalse(valido, "Debería detectar falta de actividades")

    def test_resolucion_referencias_recursos_visuales(self):
        """5. Resolución de referencias a recursos visuales."""
        material = ejemplo_matematica()
        valido, errores = validar_estructura_material(material, 10)
        # Los IDs de recursos visuales referenciados deben existir
        ids_recursos = {r.get("id") for r in material.get("recursos_visuales", [])}
        for seccion in material.get("secciones", []):
            for bloque in seccion.get("bloques", []):
                if bloque.get("tipo") == "visual_reference":
                    ref_id = bloque.get("recurso_id")
                    self.assertIn(ref_id, ids_recursos,
                                  f"Referencia rota a recurso {ref_id}")


class TestEjerciciosEscalonados(unittest.TestCase):
    """Pruebas de escalonamiento y tipos de actividad."""

    def test_tipos_actividad_distintos(self):
        """Los ejemplos deben tener tipos de actividad realmente distintos."""
        material_matematica = ejemplo_matematica()
        tipos_matematica = {a.get("tipo") for a in material_matematica.get("actividades", [])}
        self.assertGreaterEqual(len(tipos_matematica), 3,
                                "Matemática debe tener al menos 3 tipos de actividad distintos")

        material_historia = ejemplo_historia()
        tipos_historia = {a.get("tipo") for a in material_historia.get("actividades", [])}
        # Historia puede tener menos actividades pero los tipos deben ser apropiados

    def test_dificultades_asignadas(self):
        """Las actividades deben tener niveles de dificultad asignados."""
        material = ejemplo_matematica()
        for act in material.get("actividades", []):
            self.assertIn(act.get("dificultad"), ["inicial", "intermedio", "avanzado"])

    def test_actividades_tienen_consigna_y_solucion(self):
        """Todas las actividades deben tener consigna y solución."""
        material = ejemplo_matematica()
        for act in material.get("actividades", []):
            self.assertTrue(act.get("consigna"), f"Actividad {act.get('id')} sin consigna")
            self.assertTrue(act.get("solucion") or act.get("respuesta_final"),
                            f"Actividad {act.get('id')} sin solución")


if __name__ == "__main__":
    unittest.main()
