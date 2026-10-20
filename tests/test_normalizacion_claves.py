"""
Pruebas de normalización de claves JSON.

Los modelos en español suelen devolver claves con tilde ("solución",
"explicación", "sección_id"). La validación exige la forma canónica sin tilde,
así que antes de validar se normalizan las claves conocidas.

Estas pruebas reproducen el caso real que falló:
`temporal/a6f221a59640/lote_ejercicios_avanzado_3_crudo.json`.

No se realizan llamadas reales a ningún proveedor.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from esquemas_bloques import (
    normalizar_claves,
    validar_lote_ejercicios,
    validar_plan_aprendizaje,
    validar_seccion_teorica,
    validar_componentes_finales,
)


def _ejercicio_con_tildes() -> dict:
    """Ejercicio con las claves tal como las devolvió Gemini en el caso real."""
    return {
        "id": "act8",
        "dificultad": "avanzado",
        "tipo": "estudio_de_casos",
        "consigna": "Analice el caso.",
        "datos": "Datos del caso.",
        "pista": "Considere el contexto.",
        "solución": "Desarrollo paso a paso de la solución.",
        "respuesta_final": "Respuesta breve.",
        "explicación": "Por qué es correcta.",
        "criterios_corrección": "Cómo se evalúa.",
    }


class TestNormalizacionBasica(unittest.TestCase):
    """La forma canónica siempre gana."""

    def test_solucion_con_tilde_se_normaliza(self):
        """1. Reproduce el fallo real: 'solución' -> 'solucion'."""
        datos = {"ejercicios": [_ejercicio_con_tildes()]}

        # Antes de normalizar, la validación falla.
        self.assertFalse(validar_lote_ejercicios(datos)[0])

        normalizado = normalizar_claves(datos)
        ok, errores = validar_lote_ejercicios(normalizado)

        self.assertTrue(ok, errores)
        ejercicio = normalizado["ejercicios"][0]
        self.assertIn("solucion", ejercicio)
        self.assertNotIn("solución", ejercicio)
        self.assertTrue(ejercicio["solucion"])

    def test_normaliza_varias_claves_con_tilde(self):
        """2. explicación, criterios_corrección y respuesta_final."""
        normalizado = normalizar_claves({"ejercicios": [_ejercicio_con_tildes()]})
        ejercicio = normalizado["ejercicios"][0]

        self.assertIn("explicacion", ejercicio)
        self.assertIn("criterios_correccion", ejercicio)
        self.assertIn("respuesta_final", ejercicio)
        self.assertFalse(
            {"explicación", "criterios_corrección"} & set(ejercicio)
        )

    def test_clave_canonica_prevalece_sobre_la_acentuada(self):
        """3. Si están ambas formas, gana la canónica."""
        datos = {"solucion": "buena", "solución": "duplicada"}
        normalizado = normalizar_claves(datos)

        self.assertEqual(normalizado["solucion"], "buena")

    def test_contenido_no_se_modifica(self):
        """4. Solo cambian las claves, nunca los valores."""
        original = _ejercicio_con_tildes()
        normalizado = normalizar_claves({"ejercicios": [original]})["ejercicios"][0]

        for clave_canonica, clave_original in [
            ("solucion", "solución"),
            ("explicacion", "explicación"),
        ]:
            self.assertEqual(
                normalizado[clave_canonica], original[clave_original]
            )

    def test_claves_desconocidas_se_conservan(self):
        """5. Una clave que no es un campo conocido no se toca."""
        datos = {"campo_raro": 1, "ejercicios": [{"otro_campo": 2}]}
        normalizado = normalizar_claves(datos)

        self.assertEqual(normalizado["campo_raro"], 1)
        self.assertEqual(normalizado["ejercicios"][0]["otro_campo"], 2)

    def test_normalizacion_recursiva_en_listas_y_dicts(self):
        """6. Se recorre toda la estructura anidada."""
        plan = {
            "titulo": "Plan",
            "secciones": [
                {
                    "id": "s1",
                    "título": "Sección 1",
                    "conceptos_principales": ["c"],
                    "ejemplos_sugeridos": ["e"],
                    "recursos_visuales": [],
                }
            ],
        }
        normalizado = normalizar_claves(plan)

        self.assertIn("titulo", normalizado["secciones"][0])
        self.assertNotIn("título", normalizado["secciones"][0])


class TestValidacionesReales(unittest.TestCase):
    """Los esquemas aceptan las respuestas normalizadas."""

    def test_plan_con_titulo_acentuado(self):
        plan = {
            "titulo": "Plan",
            "disciplina": "Historia",
            "nivel": "Secundario",
            "profundidad": "breve",
            "objetivos_aprendizaje": ["o"],
            "conocimientos_previos": ["c"],
            "secciones": [
                {
                    "id": "s1",
                    "orden": 1,
                    "título": "Sección",
                    "conceptos_principales": ["c"],
                    "ejemplos_sugeridos": ["e"],
                    "recursos_visuales": [],
                }
            ],
            "recursos_visuales_planificados": [],
        }

        self.assertFalse(validar_plan_aprendizaje(plan)[0])
        self.assertTrue(validar_plan_aprendizaje(normalizar_claves(plan))[0])

    def test_seccion_con_seccion_id_acentuado(self):
        seccion = {
            "sección_id": "s1",
            "orden": 1,
            "titulo": "Sección",
            "bloques": [{"tipo": "paragraph", "contenido": "Texto"}],
        }

        self.assertFalse(validar_seccion_teorica(seccion)[0])
        self.assertTrue(validar_seccion_teorica(normalizar_claves(seccion))[0])

    def test_componentes_finales_con_termino_acentuado(self):
        componentes = {
            "resumen_final": "Resumen",
            "glosario": [{"término": "t", "definición": "d"}],
            "metadatos": {
                "titulo": "T",
                "tema": "tema",
                "disciplina": "Historia",
                "nivel": "Secundario",
            },
        }

        self.assertTrue(validar_componentes_finales(componentes)[0])
        normalizado = normalizar_claves(componentes)
        self.assertIn("termino", normalizado["glosario"][0])

    def test_lote_real_del_trabajo_fallido(self):
        """
        Si existe el lote real que falló en producción, debe validar
        después de normalizar. Si no está, la prueba se omite.
        """
        import pathlib

        raiz = pathlib.Path(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        ruta = raiz / "temporal" / "a6f221a59640" / (
            "lote_ejercicios_avanzado_3_crudo.json"
        )
        if not ruta.exists():
            self.skipTest("No está el lote real que falló.")

        lote = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertFalse(validar_lote_ejercicios(lote)[0])

        normalizado = normalizar_claves(lote)
        ok, errores = validar_lote_ejercicios(normalizado)
        self.assertTrue(ok, errores)
        for ejercicio in normalizado["ejercicios"]:
            self.assertTrue(ejercicio["solucion"])


if __name__ == "__main__":
    unittest.main()
