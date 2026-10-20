"""
Pruebas del ciclo de vida de la sesión Flet en la interfaz.

Verifican que, si el usuario cierra la ventana mientras se genera
contenido, la aplicación no intenta actualizar una sesión destruida
(RuntimeError: An attempt to fetch destroyed session).

No se inicia una aplicación Flet real: la página se sustituye por un
doble de prueba que reproduce el comportamiento de Flet 1.0.4.
"""
import asyncio
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import interfaz
from interfaz import AulaIAApp


class PaginaFalsa:
    """
    Doble de ft.Page.

    Simula una sesión que puede destruirse: tras `destruir()`, cualquier
    acceso a `page.session` lanza el RuntimeError de Flet y `update()`
    también falla.
    """

    def __init__(self, destruida: bool = False):
        self.destruida = destruida
        self.actualizaciones = 0
        self.titulo = ""
        self.bgcolor = ""
        self.theme_mode = None
        self.padding = 0
        self.spacing = 0
        self.overlay = []
        self.on_disconnect = None
        self.on_close = None
        self.window = MagicMock()
        self.window.on_event = None
        self._controles = []
        self.tareas = []

    # --- propiedades que Flet valida con RuntimeError ---
    @property
    def session(self):
        if self.destruida:
            raise RuntimeError("An attempt to fetch destroyed session.")
        return MagicMock()

    def add(self, *controles):
        self._controles.extend(controles)

    def update(self):
        if self.destruida:
            raise RuntimeError("An attempt to fetch destroyed session.")
        self.actualizaciones += 1

    def run_task(self, handler, *args):
        if self.destruida:
            raise RuntimeError("An attempt to fetch destroyed session.")
        self.tareas.append((handler, args))

    def show_dialog(self, dialogo):
        if self.destruida:
            raise RuntimeError("An attempt to fetch destroyed session.")

    def pop_dialog(self):
        if self.destruida:
            raise RuntimeError("An attempt to fetch destroyed session.")

    def destruir(self):
        self.destruida = True


def _crear_app(destruida: bool = False) -> AulaIAApp:
    """Construye la app sobre una página falsa."""
    return AulaIAApp(PaginaFalsa(destruida=destruida))


class TestSesionDestruida(unittest.TestCase):
    """La UI no debe tocarse cuando la sesión ya no existe."""

    def test_app_inicia_con_sesion_viva(self):
        app = _crear_app()
        self.assertTrue(app._sesion_disponible())
        self.assertTrue(app._actualizar_pagina())

    def test_no_actualiza_sesion_destruida(self):
        app = _crear_app()
        app.page.destruir()

        # No lanza excepción y no cuenta como actualización.
        self.assertFalse(app._actualizar_pagina())
        self.assertFalse(app._sesion_disponible())
        self.assertEqual(app.page.actualizaciones, 0)

    def test_actualizar_estado_ignora_sesion_destruida(self):
        app = _crear_app()
        app.page.destruir()

        # No debe lanzar RuntimeError ni modificar controles.
        app._actualizar_estado("Etapa", 0.5)
        self.assertFalse(app._sesion_disponible())

    def test_evento_de_cierre_marca_sesion_inactiva(self):
        app = _crear_app()

        evento = MagicMock()
        evento.type = interfaz.ft.WindowEventType.CLOSE
        app._on_evento_ventana(evento)

        self.assertFalse(app._sesion_disponible())
        self.assertTrue(app._cierre_solicitado)
        # Tras el cierre, actualizar no hace nada.
        self.assertFalse(app._actualizar_pagina())

    def test_desconexion_marca_sesion_inactiva(self):
        app = _crear_app()
        app._on_sesion_finalizada(None)

        self.assertFalse(app._sesion_disponible())
        self.assertFalse(app._carga_activa)

    def test_cierre_activa_la_senal_de_cancelacion(self):
        """Al cerrar, el hilo de trabajo recibe la señal de detenerse."""
        app = _crear_app()
        self.assertFalse(app._cancelacion.is_set())

        app._on_sesion_finalizada(None)

        self.assertTrue(app._cancelacion.is_set())

    def test_evento_de_ventana_activa_la_senal_de_cancelacion(self):
        app = _crear_app()

        evento = MagicMock()
        evento.type = interfaz.ft.WindowEventType.CLOSE
        app._on_evento_ventana(evento)

        self.assertTrue(app._cancelacion.is_set())

    def test_runtime_error_de_sesion_no_se_propaga(self):
        app = _crear_app()

        # La sesión se destruye justo antes de la actualización.
        app.page.destruida = True
        resultado = app._actualizar_pagina()

        self.assertFalse(resultado)
        self.assertFalse(app._sesion_activa)

    def test_on_generar_no_arranca_si_sesion_destruida(self):
        app = _crear_app()
        app.campo_tema.value = "Tema de prueba"
        app.page.destruir()

        app._on_generar(None)

        # No se encoló ninguna tarea.
        self.assertEqual(app.page.tareas, [])

    def test_generacion_no_falla_al_cerrar_durante_el_trabajo(self):
        """
        Si la ventana se cierra mientras el hilo de generación trabaja,
        el flujo termina sin intentar actualizar la UI ni propagar errores.
        """
        app = _crear_app()

        resultado_simulado = {
            "exito": True,
            "ruta_pdf": "salida/prueba.pdf",
            "material": {"metadatos": {"titulo": "Prueba"}},
            "mensaje": "Documento generado correctamente.",
        }

        # La generación "cierra la ventana" antes de devolver el resultado.
        actualizaciones_al_cerrar = {}

        def generar_y_cerrar(**kwargs):
            app.page.destruir()
            actualizaciones_al_cerrar["n"] = app.page.actualizaciones
            return resultado_simulado

        configuracion = {
            "tema": "Tema",
            "disciplina": "Historia",
            "nivel": "Secundario",
            "profundidad": "breve",
            "cantidad_actividades": 8,
            "recursos_visuales": False,
            "usar_imagenes_externas": False,
            "usar_demostracion": True,
        }

        with patch.object(app.generador, "generar", side_effect=generar_y_cerrar):
            # No debe lanzar RuntimeError ni dejar tareas pendientes.
            asyncio.run(app._ejecutar_generacion(configuracion))

        self.assertFalse(app._sesion_activa)
        # Tras el cierre no se intentó ninguna actualización más.
        self.assertEqual(
            app.page.actualizaciones,
            actualizaciones_al_cerrar["n"],
        )

    def test_progreso_tras_cierre_no_lanza(self):
        """El callback de progreso no rompe si la sesión ya no existe."""
        app = _crear_app()
        app.page.destruir()

        # Simula lo que hace el callback del hilo de trabajo.
        try:
            app._actualizar_estado("Sección 1 de 3 completada", 0.25)
        except RuntimeError as ex:  # pragma: no cover
            self.fail(f"No debía propagar RuntimeError: {ex}")

    def test_cierre_cancela_la_espera_de_la_tarea(self):
        """El cierre cancela la espera asíncrona, no el hilo de trabajo."""
        app = _crear_app()

        tarea = MagicMock()
        tarea.done.return_value = False
        app._tarea_generacion = tarea

        app._on_sesion_finalizada(None)

        tarea.cancel.assert_called_once()
        self.assertIsNone(app._tarea_generacion)

    def test_cierre_con_tarea_ya_terminada_no_falla(self):
        """Cancelar una tarea terminada es un no-op seguro."""
        app = _crear_app()

        tarea = MagicMock()
        tarea.done.return_value = True
        app._tarea_generacion = tarea

        app._on_sesion_finalizada(None)

        tarea.cancel.assert_not_called()
        self.assertIsNone(app._tarea_generacion)

    def test_dialogo_no_se_abre_con_sesion_destruida(self):
        """La configuración no intenta abrir un diálogo en una sesión muerta."""
        app = _crear_app()
        app.page.destruir()

        app._abrir_configuracion(None)  # No debe lanzar.

        self.assertFalse(app._sesion_activa)

    def test_mostrar_error_restaura_color_rojo(self):
        """Un mensaje de error nunca queda verde por una copia previa."""
        app = _crear_app()
        app.mensaje_error.color = "verde"

        app._mostrar_error("Falló algo")

        self.assertEqual(app.mensaje_error.color, interfaz.ft.Colors.RED_400)

    def test_el_generador_recibe_la_senal_de_cancelacion(self):
        """La interfaz entrega al generador el mismo evento de cancelación."""
        app = _crear_app()
        capturado = {}

        def generar_simulado(**kwargs):
            capturado.update(kwargs)
            return {
                "exito": False,
                "cancelado": True,
                "mensaje": "Generación cancelada.",
                "ruta_pdf": None,
            }

        configuracion = {
            "tema": "Tema", "disciplina": "Historia", "nivel": "Secundario",
            "profundidad": "breve", "cantidad_actividades": 8,
            "recursos_visuales": False, "usar_imagenes_externas": False,
            "usar_demostracion": False,
        }

        with patch.object(app.generador, "generar", side_effect=generar_simulado):
            asyncio.run(app._ejecutar_generacion(configuracion))

        self.assertIs(capturado["cancelacion"], app._cancelacion)

    def test_on_generar_reinicia_la_senal_de_cancelacion(self):
        """Un trabajo nuevo no hereda una cancelación anterior."""
        app = _crear_app()
        app.campo_tema.value = "Tema de prueba"
        app._cancelacion.set()

        app._on_generar(None)

        self.assertFalse(app._cancelacion.is_set())


class TestCallbackProgreso(unittest.TestCase):
    """El callback de progreso informa hitos reales, no actividad inventada."""

    def test_generar_acepta_callback_y_lo_usa(self):
        from generador_bloques import GeneradorBloques

        generador = GeneradorBloques()
        eventos = []

        with patch("generador_bloques.MODO_DEMOSTRACION", True), \
             patch.object(generador, "_crear_carpeta_trabajo") as mock_carpeta:
            mock_carpeta.return_value = MagicMock()
            generador.generar(
                tema="Tema",
                disciplina="Historia",
                nivel="Secundario",
                profundidad="breve",
                cantidad_actividades=8,
                recursos_visuales=False,
                callback_progreso=lambda p, e: eventos.append((p, e)),
            )

        self.assertTrue(eventos)
        # El último hito es el 100 % real.
        self.assertEqual(eventos[-1][0], 1.0)

    def test_fallo_del_callback_no_interrumpe_la_generacion(self):
        from generador_bloques import GeneradorBloques

        generador = GeneradorBloques()

        def callback_que_falla(progreso, etapa):
            raise RuntimeError("UI no disponible")

        with patch("generador_bloques.MODO_DEMOSTRACION", True), \
             patch.object(generador, "_crear_carpeta_trabajo") as mock_carpeta:
            mock_carpeta.return_value = MagicMock()
            resultado = generador.generar(
                tema="Tema",
                disciplina="Historia",
                nivel="Secundario",
                profundidad="breve",
                cantidad_actividades=8,
                recursos_visuales=False,
                callback_progreso=callback_que_falla,
            )

        self.assertTrue(resultado["exito"])


class TestRestauracionUI(unittest.TestCase):
    """El botón de restauración no debe romper la UI ni llamar a la IA."""

    INFO = {
        "trabajo_id": "rec",
        "titulo": "Tema de prueba",
        "estado": "failed",
        "fecha": "2026-10-19 10:00:00",
        "secciones_ok": 2,
        "secciones_total": 2,
        "secciones_faltantes": [],
        "ejercicios": 8,
        "componentes": True,
        "mensaje_error": "",
        "puede_reconstruir_sin_ia": True,
        "puede_continuar_con_ia": True,
    }

    def test_on_restaurar_construye_dialogo(self):
        app = _crear_app()
        with patch.object(
            app.generador,
            "listar_trabajos_recuperables",
            return_value=[self.INFO],
        ):
            app._on_restaurar(None)
        # El diálogo se construyó y la sesión sigue viva.
        self.assertTrue(app._sesion_disponible())

    def test_iniciar_restauracion_encola_tarea(self):
        app = _crear_app()
        app._iniciar_restauracion("rec", False)
        self.assertEqual(len(app.page.tareas), 1)
        self.assertEqual(app.page.tareas[0][1], ("rec", False))
        self.assertTrue(app.btn_generar.disabled)
        self.assertTrue(app.btn_restaurar.disabled)

    def test_timeout_muestra_el_resultado_que_termina_despues(self):
        """
        Un hilo de executor no se puede cancelar. Si termina bien durante el
        cierre, se muestra su resultado en vez de un error de timeout.
        """
        app = _crear_app()
        resultado = {
            "exito": True,
            "ruta_pdf": "tarde.pdf",
            "material": {"metadatos": {"titulo": "Tarde"}},
        }

        def _generar_tarde(**kwargs):
            time.sleep(0.05)
            return resultado

        app.generador.generar = MagicMock(side_effect=_generar_tarde)

        async def _timeout_inmediato(tarea, timeout):
            raise asyncio.TimeoutError()

        configuracion = {
            "tema": "Tema",
            "disciplina": "Historia",
            "nivel": "Secundario",
            "profundidad": "breve",
            "cantidad_actividades": 4,
            "recursos_visuales": False,
            "usar_imagenes_externas": False,
            "usar_demostracion": False,
        }
        with patch.object(
            interfaz.asyncio, "wait_for", side_effect=_timeout_inmediato
        ):
            asyncio.run(app._ejecutar_generacion(configuracion))

        self.assertEqual(app.ruta_pdf_generada, "tarde.pdf")
        self.assertEqual(app.titulo_generado, "Tarde")
        self.assertTrue(app.resultado_panel.visible)
        self.assertFalse(app.mensaje_error.visible)


if __name__ == "__main__":
    unittest.main()
