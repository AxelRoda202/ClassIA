"""
Pruebas de las referencias a recursos visuales (objetivo C).

Verifican que:
- El prompt de sección incluye los identificadores planificados.
- Una referencia inventada se reconecta a un recurso del catálogo.
- Un recurso planificado que el modelo no referenció se agrega.
- Nunca queda una referencia colgante en el documento ensamblado.
- La validación previa al PDF sigue activa.

Incluye una prueba sobre los artefactos reales del trabajo fallido
`temporal/cd72a7516ba3/` (sólo lectura). No se realizan llamadas reales.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generador_bloques as gb
import plantillas
from esquemas_bloques import validar_seccion_teorica
from validador import validar_estructura_material

RAIZ = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _recurso_planificado(rid: str, tipo: str, ubicacion: dict) -> dict:
    return {
        "id": rid,
        "type": tipo,
        "title": f"Recurso {rid}",
        "educational_purpose": "Propósito",
        "description": "Descripción",
        "image_generation_prompt": "Prompt",
        "alt_text": "Texto alternativo",
        "caption": "Pie",
        "ubicacion": ubicacion,
        "render_strategy": tipo,
        "data": {},
        "status": "pendiente",
        "generated_asset_path": None,
    }


def _plan_con_recursos() -> dict:
    ubic1 = {"seccion_id": "s1", "posicion": "despues_bloque",
             "bloque_referencia": None, "orden_relativo": 1}
    ubic2 = {"seccion_id": "s2", "posicion": "final_seccion",
             "bloque_referencia": None, "orden_relativo": 1}
    return {
        "titulo": "Plan de prueba",
        "disciplina": "Historia",
        "nivel": "Secundario",
        "profundidad": "breve",
        "objetivos_aprendizaje": ["Objetivo"],
        "conocimientos_previos": ["Conocimiento"],
        "secciones": [
            {
                "id": "s1", "orden": 1, "titulo": "Sección 1",
                "conceptos_principales": ["Concepto"],
                "ejemplos_sugeridos": ["Ejemplo"],
                "recursos_visuales": [{
                    "id": "recurso1", "tipo": "timeline",
                    "titulo": "Línea de tiempo", "descripcion": "Desc",
                    "ubicacion": ubic1,
                }],
            },
            {
                "id": "s2", "orden": 2, "titulo": "Sección 2",
                "conceptos_principales": ["Concepto"],
                "ejemplos_sugeridos": ["Ejemplo"],
                "recursos_visuales": [{
                    "id": "recurso2", "tipo": "table",
                    "titulo": "Tabla", "descripcion": "Desc",
                    "ubicacion": ubic2,
                }],
            },
        ],
        "recursos_visuales_planificados": [
            _recurso_planificado("recurso1", "timeline", ubic1),
            _recurso_planificado("recurso2", "table", ubic2),
        ],
    }


def _ejercicio(numero: int) -> dict:
    return {
        "id": f"ej{numero}", "dificultad": "inicial", "tipo": "calculo",
        "consigna": "Consigna", "solucion": "Solución",
        "respuesta_final": "Respuesta",
    }


COMPONENTES = {
    "introduccion": "Introducción.",
    "resumen_final": "Resumen.",
    "glosario": [{"termino": "T", "definicion": "D"}],
    "metadatos": {"titulo": "Título", "tema": "Tema",
                  "disciplina": "Historia", "nivel": "Secundario"},
}


def _refs(seccion: dict) -> list:
    return [
        b.get("recurso_id") for b in seccion.get("bloques", [])
        if isinstance(b, dict) and b.get("tipo") == "visual_reference"
    ]


class TestPromptRecursosVisuales(unittest.TestCase):
    """El prompt debe comunicar los ids exactos del plan."""

    def test_prompt_incluye_ids_planificados(self):
        """1. El id planificado aparece y se prohíbe inventar ids."""
        seccion_plan = _plan_con_recursos()["secciones"][0]
        texto = plantillas.obtener_instruccion_seccion_teorica(
            seccion_plan, "Tema", "Historia", "Secundario", "breve"
        )

        self.assertIn("recurso1", texto)
        self.assertIn("RECURSOS VISUALES PLANIFICADOS", texto)
        self.assertIn("No inventes identificadores nuevos", texto)

    def test_prompt_sin_recursos_prohibe_visual_reference(self):
        """2. Sin recursos planificados, se prohíbe visual_reference."""
        seccion_plan = dict(_plan_con_recursos()["secciones"][0])
        seccion_plan["recursos_visuales"] = []
        texto = plantillas.obtener_instruccion_seccion_teorica(
            seccion_plan, "Tema", "Historia", "Secundario", "breve"
        )

        self.assertIn("ninguno", texto)
        self.assertIn('No incluyas bloques de tipo "visual_reference"', texto)


class TestEsquemaSeccionVisuales(unittest.TestCase):
    """El esquema de sección rechaza referencias incompletas o vacías."""

    def test_visual_reference_sin_recurso_id_es_invalido(self):
        """3. Un visual_reference sin id es inválido."""
        seccion = {
            "seccion_id": "s1", "orden": 1, "titulo": "S1",
            "bloques": [
                {"tipo": "paragraph", "texto": "Contenido"},
                {"tipo": "visual_reference", "posicion": "despues_bloque"},
            ],
        }
        valido, errores = validar_seccion_teorica(seccion)
        self.assertFalse(valido)
        self.assertTrue(any("recurso_id" in e for e in errores))

    def test_seccion_sin_contenido_es_invalida(self):
        """4. Una sección con todos los bloques vacíos es inválida."""
        seccion = {
            "seccion_id": "s1", "orden": 1, "titulo": "S1",
            "bloques": [
                {"tipo": "paragraph", "texto": ""},
                {"tipo": "bullet_list", "items": []},
            ],
        }
        valido, errores = validar_seccion_teorica(seccion)
        self.assertFalse(valido)
        self.assertTrue(any("contenido" in e for e in errores))

    def test_seccion_valida_con_referencia(self):
        """5. Una sección con contenido y referencia válida se acepta."""
        seccion = {
            "seccion_id": "s1", "orden": 1, "titulo": "S1",
            "bloques": [
                {"tipo": "paragraph", "texto": "Contenido"},
                {"tipo": "visual_reference", "recurso_id": "recurso1",
                 "posicion": "despues_bloque"},
            ],
        }
        valido, errores = validar_seccion_teorica(seccion)
        self.assertTrue(valido, errores)


class TestReconciliacionSeccion(unittest.TestCase):
    """Reconciliación de referencias dentro de una sección."""

    def _gen(self) -> gb.GeneradorBloques:
        generador = gb.GeneradorBloques()
        generador.plan = _plan_con_recursos()
        return generador

    def _seccion(self, refs: list) -> dict:
        bloques = [{"tipo": "paragraph", "texto": "Contenido"}]
        for ref in refs:
            bloque = {"tipo": "visual_reference", "posicion": "despues_bloque"}
            if ref is not None:
                bloque["recurso_id"] = ref
            bloques.append(bloque)
        return {"seccion_id": "s1", "orden": 1, "titulo": "S1", "bloques": bloques}

    def test_referencia_valida_se_conserva(self):
        """6. Una referencia al catálogo se conserva."""
        resultado = self._gen()._reconciliar_referencias_de_seccion(
            self._seccion(["recurso1"]), ["recurso1"]
        )
        self.assertEqual(_refs(resultado), ["recurso1"])

    def test_referencia_inventada_se_reconecta(self):
        """7. Una referencia inventada se reconecta al recurso planificado."""
        resultado = self._gen()._reconciliar_referencias_de_seccion(
            self._seccion(["mapa_inventado"]), ["recurso1"]
        )
        self.assertEqual(_refs(resultado), ["recurso1"])

    def test_referencia_ausente_se_agrega(self):
        """8. Un recurso planificado no referenciado se agrega."""
        resultado = self._gen()._reconciliar_referencias_de_seccion(
            self._seccion([]), ["recurso1"]
        )
        self.assertEqual(_refs(resultado), ["recurso1"])

    def test_referencia_duplicada_se_elimina(self):
        """9. Una referencia duplicada se reduce a una sola."""
        resultado = self._gen()._reconciliar_referencias_de_seccion(
            self._seccion(["recurso1", "recurso1"]), ["recurso1"]
        )
        self.assertEqual(_refs(resultado), ["recurso1"])

    def test_sin_recurso_planificado_se_elimina_la_colgante(self):
        """10. Sin recurso disponible, la referencia colgante se elimina."""
        resultado = self._gen()._reconciliar_referencias_de_seccion(
            self._seccion(["mapa_inventado"]), []
        )
        self.assertEqual(_refs(resultado), [])

    def test_dos_referencias_inventadas_se_reconectan_una_a_una(self):
        """11. Cada referencia inventada usa un recurso planificado libre."""
        resultado = self._gen()._reconciliar_referencias_de_seccion(
            self._seccion(["inventado_a", "inventado_b"]),
            ["recurso1", "recurso2"],
        )
        self.assertEqual(_refs(resultado), ["recurso1", "recurso2"])

    def test_no_modifica_la_seccion_original(self):
        """12. La reconciliación no altera el diccionario recibido."""
        original = self._seccion(["mapa_inventado"])
        copia = json.loads(json.dumps(original))

        self._gen()._reconciliar_referencias_de_seccion(original, ["recurso1"])

        self.assertEqual(original, copia)


class TestReconciliacionDocumento(unittest.TestCase):
    """Reconciliación a nivel de documento completo."""

    def test_documento_sin_referencias_colgantes(self):
        """13. Tras reconciliar, ningún id queda fuera del catálogo."""
        plan = _plan_con_recursos()
        gen = gb.GeneradorBloques()
        gen.plan = plan
        documento = {
            "secciones": [
                {"seccion_id": "s1", "orden": 1, "titulo": "S1",
                 "bloques": [{"tipo": "visual_reference",
                              "recurso_id": "inventado"}]},
                {"seccion_id": "s2", "orden": 2, "titulo": "S2",
                 "bloques": [{"tipo": "paragraph", "texto": "x"}]},
            ],
            "recursos_visuales": plan["recursos_visuales_planificados"],
        }

        resultado = gen._reconciliar_referencias_visuales(documento)

        catalogo = {r["id"] for r in resultado["recursos_visuales"]}
        referenciados = [
            b["recurso_id"]
            for s in resultado["secciones"]
            for b in s["bloques"]
            if b.get("tipo") == "visual_reference"
        ]
        self.assertTrue(all(r in catalogo for r in referenciados))
        self.assertEqual(set(referenciados), catalogo)


class TestFlujoConReferenciasInventadas(unittest.TestCase):
    """Generación completa con secciones que traen ids inventados."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _seccion_respuesta(self, sid: str, orden: int, refs: list) -> dict:
        bloques = [{"tipo": "paragraph", "texto": "Contenido de la sección."}]
        for ref in refs:
            bloques.append({"tipo": "visual_reference", "recurso_id": ref,
                            "posicion": "despues_bloque"})
        return {"seccion_id": sid, "orden": orden,
                "titulo": f"Sección {orden}", "bloques": bloques}

    def test_generacion_con_referencias_inventadas_termina_bien(self):
        """14. Ids inventados no impiden terminar y quedan reconciliados."""
        plan = _plan_con_recursos()
        respuestas = [
            json.dumps(plan),
            json.dumps(self._seccion_respuesta("s1", 1, ["mapa_raro_1"])),
            json.dumps(self._seccion_respuesta("s2", 2, [])),
            json.dumps({"ejercicios": [_ejercicio(1), _ejercicio(2), _ejercicio(3)]}),
            json.dumps({"ejercicios": [_ejercicio(4), _ejercicio(5), _ejercicio(6)]}),
            json.dumps({"ejercicios": [_ejercicio(7), _ejercicio(8)]}),
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
                trabajo_id="refs_inventadas",
            )

        self.assertTrue(resultado["exito"], resultado["mensaje"])

        documento = json.loads(
            (self.carpeta / "documento_ensamblado.json").read_text(encoding="utf-8")
        )
        catalogo = {r["id"] for r in documento["recursos_visuales"]}
        referenciados = [
            b["recurso_id"]
            for s in documento["secciones"]
            for b in s["bloques"]
            if b.get("tipo") == "visual_reference"
        ]
        self.assertTrue(referenciados)
        self.assertTrue(all(r in catalogo for r in referenciados))
        self.assertEqual(set(referenciados), catalogo)

        # La validación del PDF sigue activa y sin errores.
        valido, errores = validar_estructura_material(documento, 8)
        self.assertTrue(valido, errores)

    def test_fallo_total_no_construye_pdf(self):
        """15. Si no se puede generar una sección, no se produce PDF."""
        plan = _plan_con_recursos()
        respuestas = [json.dumps(plan), "", "", ""]
        generador = gb.GeneradorBloques()
        iterador = iter(respuestas)

        with patch.object(
            gb, "generar_contenido_educativo",
            side_effect=lambda *a, **k: (next(iterador), "gemini"),
        ), patch.object(gb, "construir_pdf", return_value=True) as mock_pdf, \
             patch.object(
                 generador, "_crear_carpeta_trabajo", return_value=self.carpeta
             ):
            resultado = generador.generar(
                tema="Tema", disciplina="Historia", nivel="Secundario",
                profundidad="breve", cantidad_actividades=8,
                recursos_visuales=False, usar_demostracion=False,
                trabajo_id="fallo_total",
            )

        self.assertFalse(resultado["exito"])
        self.assertIsNone(resultado["ruta_pdf"])
        mock_pdf.assert_not_called()
        estado = json.loads(
            (self.carpeta / "estado.json").read_text(encoding="utf-8")
        )
        self.assertEqual(estado["estado"], gb.ESTADO_FAILED)


class TestArtefactosReales(unittest.TestCase):
    """Replay de sólo lectura del trabajo real que falló (cd72a7516ba3)."""

    CARPETA = RAIZ / "temporal" / "cd72a7516ba3"

    def test_documento_real_se_reconcilia_y_valida(self):
        """16. El documento real falla antes y valida después de reconciliar."""
        if not (self.CARPETA / "plan.json").exists():
            self.skipTest("No están los artefactos reales del trabajo fallido.")

        plan = json.loads((self.CARPETA / "plan.json").read_text(encoding="utf-8"))
        secciones = [
            json.loads((self.CARPETA / nombre).read_text(encoding="utf-8"))
            for nombre in
            ["seccion_seccion1.json", "seccion_seccion2.json", "seccion_seccion3.json"]
            if (self.CARPETA / nombre).exists()
        ]
        componentes = json.loads(
            (self.CARPETA / "componentes_finales.json").read_text(encoding="utf-8")
        )

        documento = {
            "metadatos": componentes.get("metadatos", {}),
            "objetivos_aprendizaje": plan.get("objetivos_aprendizaje", []),
            "conocimientos_previos": plan.get("conocimientos_previos", []),
            "introduccion": componentes.get("introduccion", ""),
            "secciones": secciones,
            "ejemplos_resueltos": [],
            "actividades": [_ejercicio(1)],
            "solucionario": [{"actividad_id": "ej1", "respuesta": "R"}],
            "glosario": componentes.get("glosario", []),
            "resumen_final": componentes.get("resumen_final", ""),
            "recursos_visuales": plan.get("recursos_visuales_planificados", []),
        }

        valido_antes, errores_antes = validar_estructura_material(documento, 1)
        self.assertFalse(valido_antes)
        self.assertTrue(
            any("recurso visual inexistente" in e for e in errores_antes),
            errores_antes,
        )

        generador = gb.GeneradorBloques()
        generador.plan = plan
        reconciliado = generador._reconciliar_referencias_visuales(documento)

        valido_despues, errores_despues = validar_estructura_material(reconciliado, 1)
        self.assertTrue(valido_despues, errores_despues)

        catalogo = {r["id"] for r in reconciliado["recursos_visuales"]}
        referenciados = [
            b["recurso_id"]
            for s in reconciliado["secciones"]
            for b in s["bloques"]
            if b.get("tipo") == "visual_reference"
        ]
        self.assertTrue(all(r in catalogo for r in referenciados))
        self.assertTrue(catalogo.issubset(set(referenciados)))


if __name__ == "__main__":
    unittest.main()
