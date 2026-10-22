"""
Interfaz de usuario con Flet.

Pantalla principal: encabezado, formulario de generación, estado de operación
y resultado. Usa concurrencia para no bloquear la UI durante llamadas a IA.
"""
import asyncio
import logging
import os
import threading
import webbrowser
import shutil
import time
from pathlib import Path
from typing import Optional

import flet as ft

from configuracion import (
    CARPETA_SALIDA, CARPETA_TEMPORAL,
    COLOR_ROJO_INSTITUCIONAL, COLOR_AMARILLO_INSTITUCIONAL,
    COLOR_FONDO_OSCURO, COLOR_PANEL, COLOR_TEXTO_CLARO,
    LOGO_POR_DEFECTO, MODO_DEMOSTRACION,
    IMAGE_GENERATION_ENABLED,
    TIEMPO_MAX_GENERACION_SEGUNDOS,
)
from generador_ia import GeneradorIA


logger = logging.getLogger(__name__)


def colors_gris_borde():
    return "#4A4A4A"


class AulaIAApp:
    """Clase principal de la interfaz de Aula IA."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.generador = GeneradorIA()
        self.ruta_pdf_generada: Optional[str] = None
        self.titulo_generado: Optional[str] = None
        self._file_picker: Optional[ft.FilePicker] = None

        # Estado de carga y animación
        self._hora_inicio: Optional[float] = None
        self._etapa_actual = ""
        self._progreso_actual = 0.0
        self._carga_activa = False
        self._animacion_timer = None

        # Ciclo de vida de la sesión Flet: si el usuario cierra la ventana,
        # no se debe intentar actualizar una sesión ya destruida.
        self._sesion_activa = True
        self._cierre_solicitado = False
        self._tarea_generacion: Optional[asyncio.Future] = None
        # Señal de cancelación cooperativa para el hilo de trabajo.
        self._cancelacion = threading.Event()

        self._configurar_pagina()
        # Los manejadores se registran antes del primer page.add(), para que
        # viajen al cliente en el envío inicial de la página.
        self._registrar_eventos_cierre()
        self._construir_ui()

    def _configurar_pagina(self):
        self.page.title = "Aula IA - Generador Educativo de PDF"
        self.page.bgcolor = COLOR_FONDO_OSCURO
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 20
        self.page.spacing = 0
        # En Flet 1.x el tamaño de ventana se configura en page.window.
        try:
            self.page.window.width = 900
            self.page.window.height = 700
            self.page.window.resizable = True
        except Exception:
            # Si la versión no expone page.window, se conservan los valores
            # por defecto sin interrumpir el arranque.
            pass

    # ------------------------------------------------------------------
    # Ciclo de vida de la sesión
    # ------------------------------------------------------------------

    def _registrar_eventos_cierre(self) -> None:
        """Registra manejadores para detectar el cierre de la ventana."""
        try:
            self.page.on_disconnect = self._on_sesion_finalizada
        except Exception:
            pass
        try:
            self.page.on_close = self._on_sesion_finalizada
        except Exception:
            pass
        try:
            self.page.window.on_event = self._on_evento_ventana
        except Exception:
            pass

    def _on_sesion_finalizada(self, e=None):
        """Marca la sesión como no disponible y pide detener el trabajo."""
        self._sesion_activa = False
        self._carga_activa = False
        self._animacion_timer = None
        self._cancelacion.set()
        self._cancelar_tarea_generacion()

    def _cancelar_tarea_generacion(self):
        """
        Cancela la espera de la tarea de generación, si sigue activa.

        El hilo de trabajo no se puede interrumpir de forma segura: continúa
        y guarda cada bloque validado en `temporal/<trabajo_id>/`. Solo se
        cancela la espera asíncrona para liberar recursos del event loop.
        """
        tarea = self._tarea_generacion
        if tarea is None:
            return
        self._tarea_generacion = None
        try:
            if not tarea.done():
                tarea.cancel()
        except Exception:
            pass

    def _on_evento_ventana(self, e=None):
        """Detecta el pedido de cierre de la ventana nativa."""
        try:
            tipo = getattr(e, "type", None)
            if tipo == ft.WindowEventType.CLOSE:
                self._cierre_solicitado = True
                self._sesion_activa = False
                self._cancelacion.set()
                self._cancelar_tarea_generacion()
        except Exception:
            pass

    def _sesion_disponible(self) -> bool:
        """
        Indica si la sesión de Flet sigue viva.

        Flet lanza RuntimeError('An attempt to fetch destroyed session.')
        al acceder a page.session después de que el cliente se desconecta.
        Se consulta ese mismo mecanismo para no enviar actualizaciones a una
        sesión destruida.
        """
        if not self._sesion_activa or self._cierre_solicitado:
            return False
        try:
            # El acceso a page.session es la comprobación fiable en Flet 1.x.
            getattr(self.page, "session", None)
            return True
        except RuntimeError:
            self._sesion_activa = False
            return False
        except Exception:
            # Si no se puede determinar, se asume que la sesión sigue viva.
            return True

    def _actualizar_pagina(self) -> bool:
        """
        Refresca la UI solo si la sesión sigue activa.

        Devuelve True si la actualización se intentó y no falló por sesión
        destruida. Nunca propaga el RuntimeError de sesión destruida.
        """
        if not self._sesion_disponible():
            return False
        try:
            self.page.update()
            return True
        except RuntimeError as ex:
            if "destroyed session" in str(ex).lower():
                self._sesion_activa = False
            else:
                logger.warning("No se pudo refrescar la interfaz: %s", ex)
            return False
        except Exception as ex:
            # Un fallo de refresco no debe abortar la generación ni el cierre.
            logger.warning("No se pudo refrescar la interfaz: %s", ex)
            return False

    def _construir_ui(self):
        encabezado = self._construir_encabezado()
        formulario = self._construir_formulario()

        # Indicador animado de carga (círculo giratorio simulado con ProgressRing)
        self.indicador_carga = ft.ProgressRing(
            width=24, height=24, stroke_width=3,
            color=COLOR_AMARILLO_INSTITUCIONAL,
            visible=False,
        )

        self.estado_texto = ft.Text("Listo para generar.", size=13, color=COLOR_TEXTO_CLARO)
        self.etapa_texto = ft.Text("", size=11, color=ft.Colors.GREY_400, italic=True)
        self.tiempo_texto = ft.Text("", size=11, color=ft.Colors.GREY_400)
        self.barra_progreso = ft.ProgressBar(value=0, width=400, color=COLOR_AMARILLO_INSTITUCIONAL)
        self.estado_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.indicador_carga,
                    ft.Container(
                        content=ft.Text("Estado de la operación", size=14, weight="bold", color=COLOR_AMARILLO_INSTITUCIONAL),
                        padding=ft.Padding.only(right=8),
                    ),
                    ft.Container(
                        width=4, height=16,
                        bgcolor=COLOR_ROJO_INSTITUCIONAL,
                        border_radius=2,
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.estado_texto,
                self.etapa_texto,
                ft.Row([
                    self.tiempo_texto,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.barra_progreso,
            ], spacing=8),
            visible=False,
            padding=15,
            bgcolor=COLOR_PANEL,
            border_radius=8,
            border=ft.Border.only(
                left=ft.BorderSide(4, COLOR_ROJO_INSTITUCIONAL),
                top=ft.BorderSide(1, colors_gris_borde()),
                right=ft.BorderSide(1, colors_gris_borde()),
                bottom=ft.BorderSide(1, colors_gris_borde()),
            ),
        )

        self.resultado_titulo = ft.Text("", size=16, weight="bold", color=COLOR_TEXTO_CLARO)
        self.resultado_ruta = ft.Text("", size=12, color=COLOR_TEXTO_CLARO, selectable=True)
        self.btn_abrir_pdf = ft.FilledButton(
            "Abrir documento", icon=ft.icons.Icons.OPEN_IN_NEW, on_click=self._abrir_pdf, visible=False,
            bgcolor=COLOR_ROJO_INSTITUCIONAL,
        )
        self.btn_guardar_copia = ft.FilledButton(
            "Guardar copia en...", icon=ft.icons.Icons.SAVE, on_click=self._guardar_copia, visible=False,
            bgcolor=COLOR_AMARILLO_INSTITUCIONAL,
            color=ft.Colors.BLACK,
        )
        self.mensaje_error = ft.Text("", size=13, color=ft.Colors.RED_400, visible=False)
        self.mensaje_advertencia = ft.Text("", size=13, color=COLOR_AMARILLO_INSTITUCIONAL, visible=False)

        self.resultado_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=ft.Text("Resultado", size=14, weight="bold", color=COLOR_AMARILLO_INSTITUCIONAL),
                        padding=ft.Padding.only(right=8),
                    ),
                    ft.Container(
                        width=4, height=16,
                        bgcolor=COLOR_AMARILLO_INSTITUCIONAL,
                        border_radius=2,
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.resultado_titulo,
                self.resultado_ruta,
                ft.Row([self.btn_abrir_pdf, self.btn_guardar_copia], spacing=10),
                self.mensaje_error,
                self.mensaje_advertencia,
            ], spacing=10),
            visible=False,
            padding=15,
            bgcolor=COLOR_PANEL,
            border_radius=8,
            border=ft.Border.only(
                left=ft.BorderSide(4, COLOR_AMARILLO_INSTITUCIONAL),
                top=ft.BorderSide(1, colors_gris_borde()),
                right=ft.BorderSide(1, colors_gris_borde()),
                bottom=ft.BorderSide(1, colors_gris_borde()),
            ),
        )

        self.btn_generar = ft.FilledButton(
            "Generar material PDF",
            icon=ft.icons.Icons.PICTURE_AS_PDF,
            on_click=self._on_generar,
            bgcolor=COLOR_ROJO_INSTITUCIONAL,
            color=COLOR_TEXTO_CLARO,
            width=260,
            height=45,
        )

        self.btn_restaurar = ft.OutlinedButton(
            "Restaurar trabajo",
            icon=ft.icons.Icons.RESTORE,
            on_click=self._on_restaurar,
            width=220,
            height=45,
            tooltip="Reconstruir un PDF o continuar un trabajo interrumpido "
                    "reutilizando los bloques ya generados.",
        )

        columna_central = ft.Column([
            encabezado,
            ft.Divider(height=1, color=colors_gris_borde()),
            ft.Container(content=formulario, padding=20, bgcolor=COLOR_PANEL,
                         border_radius=8, border=ft.Border.all(1, colors_gris_borde())),
            ft.Container(height=20),
            ft.Row([self.btn_generar, self.btn_restaurar],
                   spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
            self.estado_panel,
            self.resultado_panel,
        ], scroll=ft.ScrollMode.AUTO, spacing=0)

        contenedor_principal = ft.Container(
            content=columna_central,
            expand=True,
            bgcolor=COLOR_FONDO_OSCURO,
        )

        self.page.add(contenedor_principal)

    def _construir_encabezado(self):
        if LOGO_POR_DEFECTO.exists():
            logo_control = ft.Container(
                content=ft.Image(
                    src=str(LOGO_POR_DEFECTO),
                    width=60, height=60,
                    fit=ft.BoxFit.CONTAIN,
                ),
                border_radius=12,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )
        else:
            logo_control = ft.Container(
                content=ft.Text("IA", size=20, weight="bold"),
                width=60, height=60,
                border_radius=12,
                bgcolor=COLOR_ROJO_INSTITUCIONAL,
                alignment=ft.alignment.center,
            )

        encabezado = ft.Row([
            logo_control,
            ft.Column([
                ft.Text("Aula IA", size=26, weight="bold", color=COLOR_TEXTO_CLARO),
                ft.Text("Aprendé cualquier tema, paso a paso", size=13, color=ft.Colors.GREY_400),
            ], spacing=4, expand=True),
            ft.Container(
                content=ft.TextButton("Configuración", icon=ft.icons.Icons.SETTINGS, on_click=self._abrir_configuracion),
                alignment=ft.Alignment.CENTER_RIGHT,
            ),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

        return ft.Container(
            content=encabezado,
            padding=ft.Padding.only(bottom=16),
            border=ft.Border.only(bottom=ft.BorderSide(2, COLOR_ROJO_INSTITUCIONAL)),
        )

    def _construir_formulario(self):
        self.campo_tema = ft.TextField(
            label="Tema de estudio",
            hint_text="Ej: Leyes de Newton, Funciones cuadráticas...",
            bgcolor=COLOR_FONDO_OSCURO,
            border_color=ft.Colors.GREY_600,
            focused_border_color=COLOR_AMARILLO_INSTITUCIONAL,
            color=COLOR_TEXTO_CLARO,
            label_style=ft.TextStyle(color=ft.Colors.GREY_400),
            expand=True,
        )

        self.selector_disciplina = ft.Dropdown(
            label="Disciplina",
            value="Detectar automáticamente",
            options=[
                ft.dropdown.Option("Detectar automáticamente"),
                ft.dropdown.Option("Matemática"),
                ft.dropdown.Option("Física y química"),
                ft.dropdown.Option("Historia y geografía"),
                ft.dropdown.Option("Lengua y literatura"),
                ft.dropdown.Option("Programación e informática"),
                ft.dropdown.Option("Recursos humanos, administración y economía"),
                ft.dropdown.Option("Biología y ciencias naturales"),
                ft.dropdown.Option("Otras"),
            ],
            bgcolor=COLOR_FONDO_OSCURO,
            border_color=ft.Colors.GREY_600,
            focused_border_color=COLOR_AMARILLO_INSTITUCIONAL,
            color=COLOR_TEXTO_CLARO,
            expand=True,
        )

        self.selector_nivel = ft.Dropdown(
            label="Nivel educativo",
            value="Secundario",
            options=[
                ft.dropdown.Option("Secundario"),
                ft.dropdown.Option("Terciario"),
                ft.dropdown.Option("Universitario"),
                ft.dropdown.Option("General / profesional"),
            ],
            bgcolor=COLOR_FONDO_OSCURO,
            border_color=ft.Colors.GREY_600,
            focused_border_color=COLOR_AMARILLO_INSTITUCIONAL,
            color=COLOR_TEXTO_CLARO,
            expand=True,
        )

        self.selector_profundidad = ft.Dropdown(
            label="Profundidad",
            value="estándar (6-8 páginas)",
            options=[
                ft.dropdown.Option("breve (4-5 páginas)"),
                ft.dropdown.Option("estándar (6-8 páginas)"),
                ft.dropdown.Option("profunda (9-12 páginas)"),
            ],
            bgcolor=COLOR_FONDO_OSCURO,
            border_color=ft.Colors.GREY_600,
            focused_border_color=COLOR_AMARILLO_INSTITUCIONAL,
            color=COLOR_TEXTO_CLARO,
            expand=True,
        )

        self.selector_ejercicios = ft.Dropdown(
            label="Cantidad de ejercicios",
            value="10",
            options=[
                ft.dropdown.Option("8"),
                ft.dropdown.Option("10"),
                ft.dropdown.Option("12"),
            ],
            bgcolor=COLOR_FONDO_OSCURO,
            border_color=ft.Colors.GREY_600,
            focused_border_color=COLOR_AMARILLO_INSTITUCIONAL,
            color=COLOR_TEXTO_CLARO,
            expand=True,
        )

        self.switch_recursos_visuales = ft.Switch(
            label="Habilitar recursos visuales",
            value=True,
            active_color=COLOR_AMARILLO_INSTITUCIONAL,
        )

        self.switch_imagenes_externas = ft.Switch(
            label="Habilitar imágenes generadas por IA (externas)",
            value=IMAGE_GENERATION_ENABLED,
            active_color=COLOR_AMARILLO_INSTITUCIONAL,
            tooltip="Requiere configuración de proveedor de imágenes (Pollinations). "
                    "Máximo 2 imágenes por documento. Se desactivará automáticamente si no hay proveedor disponible.",
        )

        self.checkbox_demo = ft.Checkbox(
            label="Modo demostración (sin llamadas a IA)",
            value=MODO_DEMOSTRACION,
        )

        return ft.Column([
            ft.Text("Formulario de generación", size=16, weight="bold", color=COLOR_AMARILLO_INSTITUCIONAL),
            ft.Row([self.campo_tema], spacing=10),
            ft.Row([
                self.selector_disciplina,
                self.selector_nivel,
            ], spacing=10),
            ft.Row([
                self.selector_profundidad,
                self.selector_ejercicios,
            ], spacing=10),
            ft.Row([
                self.switch_recursos_visuales,
                self.switch_imagenes_externas,
            ], spacing=10),
            ft.Row([
                self.checkbox_demo,
            ], spacing=10),
        ], spacing=12)

    def _on_generar(self, e):
        # Si la ventana ya se cerró, no se inicia ningún trabajo nuevo.
        if not self._sesion_disponible():
            return

        tema = self.campo_tema.value.strip() if self.campo_tema.value else ""
        if not tema:
            self._mostrar_error("Ingresá un tema de estudio.")
            return

        profundidad_raw = self.selector_profundidad.value or "estándar (6-8 páginas)"
        profundidad = profundidad_raw.split(" ")[0]

        try:
            cantidad = int(self.selector_ejercicios.value or "10")
        except ValueError:
            cantidad = 10

        self._ocultar_resultado()
        self._mostrar_estado(True)
        self.btn_generar.disabled = True
        self.btn_restaurar.disabled = True
        # Reiniciar la señal de cancelación para este trabajo nuevo.
        self._cancelacion.clear()
        self._actualizar_pagina()

        try:
            self.page.run_task(self._ejecutar_generacion, {
                "tema": tema,
                "disciplina": self.selector_disciplina.value or "Detectar automáticamente",
                "nivel": self.selector_nivel.value or "Secundario",
                "profundidad": profundidad,
                "cantidad_actividades": cantidad,
                "recursos_visuales": self.switch_recursos_visuales.value,
                "usar_imagenes_externas": self.switch_imagenes_externas.value,
                "usar_demostracion": self.checkbox_demo.value,
            })
        except RuntimeError as ex:
            # La sesión pudo destruirse entre la comprobación y el arranque.
            if "destroyed session" in str(ex).lower():
                self._on_sesion_finalizada()
                return
            raise

    # ------------------------------------------------------------------
    # Restauración de trabajos guardados
    # ------------------------------------------------------------------

    @staticmethod
    def _etiqueta_trabajo(info: dict) -> str:
        """Etiqueta corta para el selector de trabajos."""
        titulo = str(info.get("titulo") or "Trabajo sin título")
        estado = str(info.get("estado") or "desconocido")
        fecha = str(info.get("fecha") or "")
        return f"{titulo} · {estado} · {fecha}"

    def _on_restaurar(self, e):
        """Muestra los trabajos guardados y permite reconstruir o continuar."""
        if not self._sesion_disponible():
            return
        if self._carga_activa or self._tarea_generacion is not None:
            self._mostrar_error("Esperá a que termine la operación actual.")
            return
        try:
            trabajos = self.generador.listar_trabajos_recuperables()
        except Exception as ex:
            self._mostrar_error(
                f"No se pudieron leer los trabajos guardados: {ex}"
            )
            return
        if not trabajos:
            self._mostrar_error(
                "No hay trabajos guardados para restaurar. Generá un "
                "material primero o revisá la carpeta temporal/."
            )
            return

        selector = ft.Dropdown(
            label="Trabajo guardado",
            value=trabajos[0]["trabajo_id"],
            options=[
                ft.dropdown.Option(
                    key=info["trabajo_id"],
                    text=self._etiqueta_trabajo(info),
                )
                for info in trabajos
            ],
            width=680,
            bgcolor=COLOR_FONDO_OSCURO,
            border_color=ft.Colors.GREY_600,
            focused_border_color=COLOR_AMARILLO_INSTITUCIONAL,
            color=COLOR_TEXTO_CLARO,
            label_style=ft.TextStyle(color=ft.Colors.GREY_400),
        )
        detalle = ft.Text(
            "", size=12, color=COLOR_TEXTO_CLARO, selectable=True
        )
        btn_sin_ia = ft.FilledButton(
            "Reconstruir PDF sin IA",
            icon=ft.icons.Icons.PICTURE_AS_PDF,
            bgcolor=COLOR_ROJO_INSTITUCIONAL,
        )
        btn_con_ia = ft.OutlinedButton(
            "Continuar con IA",
            icon=ft.icons.Icons.PLAY_ARROW,
            tooltip="Reutiliza los bloques válidos y sólo pide a la IA lo "
                    "que falte.",
        )

        def _info_seleccionada() -> dict:
            clave = selector.value
            for item in trabajos:
                if item.get("trabajo_id") == clave:
                    return item
            return trabajos[0]

        def actualizar_detalle(e=None):
            info = _info_seleccionada()
            lineas = [
                f"Estado: {info.get('estado', 'desconocido')}",
                f"Secciones válidas: {info.get('secciones_ok', 0)}/"
                f"{info.get('secciones_total', 0)}",
                f"Ejercicios válidos: {info.get('ejercicios', 0)}",
                "Componentes finales: "
                + ("sí" if info.get("componentes") else "no"),
            ]
            faltantes = info.get("secciones_faltantes") or []
            if faltantes:
                lineas.append("Secciones faltantes: " + ", ".join(faltantes))
            if info.get("mensaje_error"):
                lineas.append(
                    "Último error: " + str(info["mensaje_error"])[:400]
                )
            if info.get("puede_reconstruir_sin_ia"):
                lineas.append(
                    "Listo para reconstruir el PDF sin gastar tokens."
                )
            elif info.get("puede_continuar_con_ia"):
                lineas.append(
                    "Faltan bloques: se puede continuar con IA reutilizando "
                    "lo ya guardado."
                )
            else:
                lineas.append(
                    "No hay datos suficientes para restaurar este trabajo."
                )
            detalle.value = "\n".join(lineas)
            btn_sin_ia.disabled = not bool(
                info.get("puede_reconstruir_sin_ia")
            )
            btn_con_ia.disabled = (
                not bool(info.get("puede_continuar_con_ia"))
                or bool(info.get("puede_reconstruir_sin_ia"))
            )
            self._actualizar_pagina()

        selector.on_select = actualizar_detalle
        btn_sin_ia.on_click = lambda _: self._iniciar_restauracion(
            selector.value, False
        )
        btn_con_ia.on_click = lambda _: self._iniciar_restauracion(
            selector.value, True
        )

        dialogo = ft.AlertDialog(
            title=ft.Text("Restaurar trabajo"),
            content=ft.Column([
                ft.Text(
                    "Elegí un trabajo guardado. La reconstrucción sin IA no "
                    "hace llamadas externas; continuar con IA sólo genera lo "
                    "que falte.",
                    size=12,
                    color=ft.Colors.GREY_400,
                ),
                selector,
                detalle,
            ], width=700, height=320, spacing=14,
                scroll=ft.ScrollMode.AUTO),
            actions=[
                btn_sin_ia,
                btn_con_ia,
                ft.TextButton("Cancelar",
                              on_click=lambda _: self.page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        actualizar_detalle()
        self.page.show_dialog(dialogo)

    def _iniciar_restauracion(self, trabajo_id: str, usar_ia: bool):
        """Cierra el diálogo y arranca la restauración en segundo plano."""
        if not self._sesion_disponible() or not trabajo_id:
            return
        try:
            self.page.pop_dialog()
        except Exception:
            pass
        self._ocultar_resultado()
        self._mostrar_estado(True)
        self.btn_generar.disabled = True
        self.btn_restaurar.disabled = True
        self._cancelacion.clear()
        self._actualizar_pagina()
        try:
            self.page.run_task(
                self._ejecutar_restauracion, trabajo_id, usar_ia
            )
        except RuntimeError as ex:
            if "destroyed session" in str(ex).lower():
                self._on_sesion_finalizada()
                return
            raise

    async def _ejecutar_restauracion(self, trabajo_id: str, usar_ia: bool):
        """Reconstruye un PDF o continúa un trabajo sin bloquear la UI."""
        try:
            if not self._sesion_disponible():
                return
            self._iniciar_carga()
            loop = asyncio.get_running_loop()

            def _actualizar_estado_hilo(texto: str, progreso: float):
                try:
                    self._actualizar_estado(texto, progreso)
                except Exception:
                    pass

            def callback_progreso(progreso: float, etapa: str):
                try:
                    loop.call_soon_threadsafe(
                        _actualizar_estado_hilo, etapa, progreso
                    )
                except RuntimeError:
                    pass

            hilo_terminado = threading.Event()
            resultado_hilo: dict = {}

            def _restaurar_sync():
                try:
                    if usar_ia:
                        resultado_hilo["resultado"] = (
                            self.generador.continuar_desde_trabajo(
                                trabajo_id,
                                callback_progreso=callback_progreso,
                                cancelacion=self._cancelacion,
                            )
                        )
                    else:
                        resultado_hilo["resultado"] = (
                            self.generador.regenerar_pdf_desde_trabajo(
                                trabajo_id
                            )
                        )
                    return resultado_hilo["resultado"]
                finally:
                    hilo_terminado.set()

            tarea = asyncio.ensure_future(
                loop.run_in_executor(None, _restaurar_sync)
            )
            self._tarea_generacion = tarea
            timeout = (
                TIEMPO_MAX_GENERACION_SEGUNDOS + 120
                if usar_ia else 300
            )
            resultado = await asyncio.wait_for(tarea, timeout=timeout)

            if not self._sesion_disponible():
                return

            if resultado.get("exito"):
                self._actualizar_estado("Trabajo restaurado", 1.0)
                self.ruta_pdf_generada = resultado.get("ruta_pdf")
                material = resultado.get("material") or {}
                metadatos = material.get("metadatos", {}) or {}
                self.titulo_generado = (
                    metadatos.get("titulo") or "Material restaurado"
                )
                self._mostrar_resultado(resultado)
            else:
                self._mostrar_error(
                    resultado.get(
                        "mensaje", "No se pudo restaurar el trabajo."
                    )
                )

        except asyncio.CancelledError:
            logger.info("Restauración cancelada por cierre de la ventana.")
            raise
        except asyncio.TimeoutError:
            self._cancelacion.set()
            try:
                await asyncio.to_thread(hilo_terminado.wait, 30)
            except Exception:
                pass

            if not self._sesion_disponible():
                return

            resultado_tardio = resultado_hilo.get("resultado")
            if resultado_tardio and resultado_tardio.get("exito"):
                self._actualizar_estado(
                    "Trabajo restaurado (terminó durante el cierre)", 1.0
                )
                self.ruta_pdf_generada = resultado_tardio.get("ruta_pdf")
                material = resultado_tardio.get("material") or {}
                metadatos = material.get("metadatos", {}) or {}
                self.titulo_generado = (
                    metadatos.get("titulo") or "Material restaurado"
                )
                self._mostrar_resultado(resultado_tardio)
            else:
                self._mostrar_error(
                    "La restauración superó el tiempo máximo de espera. "
                    "El trabajo puede seguir guardándose en disco; volvé a "
                    "usar 'Restaurar trabajo' en unos instantes."
                )
        except Exception as ex:
            if self._sesion_disponible():
                self._mostrar_error(f"Error al restaurar: {ex}")
        finally:
            self._tarea_generacion = None
            self._detener_carga()
            self.btn_generar.disabled = False
            self.btn_restaurar.disabled = False
            self._actualizar_pagina()

    async def _ejecutar_generacion(self, configuracion: dict):
        try:
            if not self._sesion_disponible():
                return

            self._iniciar_carga()

            loop = asyncio.get_running_loop()

            def _actualizar_estado_hilo(texto: str, progreso: float):
                """Se ejecuta en el hilo del event loop de Flet."""
                try:
                    self._actualizar_estado(texto, progreso)
                except Exception:
                    # Un fallo de refresco no debe abortar la generación.
                    pass

            # Callback de progreso invocado desde el hilo de trabajo:
            # se reenvía al hilo del event loop para actualizar la UI.
            def callback_progreso(progreso: float, etapa: str):
                try:
                    loop.call_soon_threadsafe(
                        _actualizar_estado_hilo, etapa, progreso
                    )
                except RuntimeError:
                    # El loop ya no está disponible: se ignora el refresco.
                    pass

            # Ejecutar la generación en un hilo separado para no bloquear la UI.
            # El evento permite saber si el hilo realmente terminó cuando
            # asyncio.wait_for deja de esperar: un hilo de executor no se
            # puede cancelar y no debe tocarse el mismo trabajo en paralelo.
            hilo_terminado = threading.Event()
            resultado_hilo: dict = {}

            def _ejecutar_generacion_sync():
                try:
                    resultado_hilo["resultado"] = self.generador.generar(
                        tema=configuracion["tema"],
                        disciplina=configuracion["disciplina"],
                        nivel=configuracion["nivel"],
                        profundidad=configuracion["profundidad"],
                        cantidad_actividades=configuracion["cantidad_actividades"],
                        recursos_visuales=configuracion["recursos_visuales"],
                        usar_imagenes_externas=configuracion["usar_imagenes_externas"],
                        usar_demostracion=configuracion["usar_demostracion"],
                        callback_progreso=callback_progreso,
                        cancelacion=self._cancelacion,
                    )
                    return resultado_hilo["resultado"]
                finally:
                    hilo_terminado.set()

            tarea = asyncio.ensure_future(
                loop.run_in_executor(None, _ejecutar_generacion_sync)
            )
            self._tarea_generacion = tarea
            resultado = await asyncio.wait_for(
                tarea,
                # Margen para el ensamblado y el PDF locales, que se
                # terminan aunque se alcance el límite de las etapas de IA.
                timeout=TIEMPO_MAX_GENERACION_SEGUNDOS + 120,
            )

            # Si el usuario cerró la ventana mientras se generaba, el trabajo
            # ya quedó guardado en disco: no se intenta actualizar la UI.
            if not self._sesion_disponible():
                logger.info(
                    "La ventana se cerró durante la generación; el progreso "
                    "quedó guardado en disco."
                )
                return

            if resultado["exito"]:
                self._actualizar_estado("Material listo para estudiar", 1.0)
                self.ruta_pdf_generada = resultado["ruta_pdf"]
                material = resultado.get("material") or {}
                self.titulo_generado = material.get("metadatos", {}).get("titulo", "Material generado")
                self._mostrar_resultado(resultado)
            else:
                self._mostrar_error(resultado.get("mensaje", "Error desconocido."))

        except asyncio.CancelledError:
            # Cancelación por cierre de ventana: se propaga sin tocar la UI.
            logger.info("Generación cancelada por cierre de la ventana.")
            raise
        except asyncio.TimeoutError:
            # El hilo de trabajo no se puede cancelar: se pide cancelación
            # cooperativa y se espera un tiempo acotado antes de habilitar
            # otra operación sobre el mismo trabajo.
            self._cancelacion.set()
            try:
                await asyncio.to_thread(hilo_terminado.wait, 60)
            except Exception:
                pass

            if not self._sesion_disponible():
                return

            # Si el hilo terminó bien justo después del límite (por ejemplo,
            # durante el ensamblado local), se muestra el resultado en vez de
            # un error engañoso.
            resultado_tardio = resultado_hilo.get("resultado")
            if resultado_tardio and resultado_tardio.get("exito"):
                self._actualizar_estado(
                    "Material listo (terminó durante el cierre)", 1.0
                )
                self.ruta_pdf_generada = resultado_tardio.get("ruta_pdf")
                material = resultado_tardio.get("material") or {}
                self.titulo_generado = (
                    material.get("metadatos", {}).get(
                        "titulo", "Material generado"
                    )
                )
                self._mostrar_resultado(resultado_tardio)
            else:
                self._mostrar_error(
                    f"La generación superó el tiempo máximo de espera "
                    f"({TIEMPO_MAX_GENERACION_SEGUNDOS} segundos). "
                    f"Los bloques ya validados quedaron guardados: usá "
                    f"'Restaurar trabajo' para reconstruir el PDF o "
                    f"continuar sin repetir todo."
                )
        except Exception as ex:
            if self._sesion_disponible():
                self._mostrar_error(f"Error inesperado: {ex}")
        finally:
            self._tarea_generacion = None
            self._detener_carga()
            self.btn_generar.disabled = False
            self.btn_restaurar.disabled = False
            self._actualizar_pagina()

    def _iniciar_carga(self):
        """Inicia la animación de carga y registra el tiempo de inicio."""
        self._hora_inicio = time.time()
        self._carga_activa = True
        self.estado_panel.visible = True
        self.resultado_panel.visible = False
        self.indicador_carga.visible = True
        self.btn_generar.disabled = True
        self.btn_restaurar.disabled = True
        self._actualizar_pagina()

    def _detener_carga(self):
        """Detiene la animación de carga y restaura controles."""
        self._carga_activa = False
        self.indicador_carga.visible = False
        self.btn_generar.disabled = False
        self.btn_restaurar.disabled = False
        self._actualizar_pagina()

    async def _espera_animada(self, segundos: float):
        """Espera un tiempo corto permitiendo que la UI se actualice (no bloquea)."""
        await asyncio.sleep(segundos)
        self._actualizar_pagina()

    def _actualizar_estado(self, texto_estado: str, progreso: float):
        """Actualiza el texto de la etapa, el progreso y el tiempo transcurrido."""
        # Nunca se modifican controles de una sesión ya destruida.
        if not self._sesion_disponible():
            return

        self.estado_texto.value = texto_estado
        self.etapa_texto.value = texto_estado
        self.barra_progreso.value = progreso

        if self._hora_inicio is not None:
            transcurrido = time.time() - self._hora_inicio
            minutos = int(transcurrido // 60)
            segundos = int(transcurrido % 60)
            self.tiempo_texto.value = f"Tiempo transcurrido: {minutos:02d}:{segundos:02d}"

        self._actualizar_pagina()

    def _mostrar_estado(self, visible: bool):
        self.estado_panel.visible = visible
        self.resultado_panel.visible = False
        self._actualizar_pagina()

    def _ocultar_resultado(self):
        self.resultado_panel.visible = False
        self.mensaje_error.visible = False
        self.mensaje_advertencia.visible = False

    def _mostrar_resultado(self, resultado: dict):
        self.estado_panel.visible = False
        self.resultado_panel.visible = True
        self.resultado_titulo.value = self.titulo_generado or "Material generado"
        self.resultado_ruta.value = self.ruta_pdf_generada or ""
        self.btn_abrir_pdf.visible = True
        self.btn_guardar_copia.visible = True
        self.mensaje_error.visible = False
        advertencia = resultado.get("advertencia_imagenes", "")
        if advertencia:
            self.mensaje_advertencia.value = advertencia
            self.mensaje_advertencia.visible = True
        else:
            self.mensaje_advertencia.visible = False
        self._actualizar_pagina()

    def _mostrar_error(self, mensaje: str):
        self.estado_panel.visible = False
        self.resultado_panel.visible = True
        self.resultado_titulo.value = "Error"
        self.resultado_ruta.value = ""
        self.btn_abrir_pdf.visible = False
        self.btn_guardar_copia.visible = False
        self.mensaje_error.value = mensaje
        # Restaurar el color de error: _on_file_picker_result lo cambia a verde
        # al confirmar una copia guardada.
        self.mensaje_error.color = ft.Colors.RED_400
        self.mensaje_error.visible = True
        self.mensaje_advertencia.visible = False
        self._actualizar_pagina()

    def _abrir_pdf(self, e):
        if self.ruta_pdf_generada and Path(self.ruta_pdf_generada).exists():
            try:
                webbrowser.open(self.ruta_pdf_generada)
            except Exception as ex:
                self._mostrar_error(f"No se pudo abrir el documento: {ex}")

    def _guardar_copia(self, e):
        if not self.ruta_pdf_generada:
            return
        if not self._sesion_disponible():
            return
        # Crear el FilePicker de forma perezosa para evitar problemas en Flet 1.x
        if self._file_picker is None:
            self._file_picker = ft.FilePicker(on_result=self._on_file_picker_result)
            try:
                self.page.overlay.append(self._file_picker)
                self._actualizar_pagina()
            except Exception:
                self._mostrar_error("No se pudo inicializar el selector de archivos. "
                                    "Copiá manualmente la ruta del PDF mostrada.")
                return
        nombre_sugerido = Path(self.ruta_pdf_generada).name
        try:
            self._file_picker.save_file(
                dialog_title="Guardar copia del PDF",
                file_name=nombre_sugerido,
                allowed_extensions=["pdf"],
            )
        except RuntimeError as ex:
            # La ventana pudo cerrarse entre la comprobación y la llamada.
            if "destroyed session" in str(ex).lower():
                self._on_sesion_finalizada()
                return
            logger.warning("No se pudo abrir el selector de archivos: %s", ex)

    def _on_file_picker_result(self, e: ft.FilePickerResultEvent):
        if e.path:
            try:
                shutil.copy2(self.ruta_pdf_generada, e.path)
                self.mensaje_error.value = f"Copia guardada en: {e.path}"
                self.mensaje_error.color = ft.Colors.GREEN_400
                self.mensaje_error.visible = True
                self._actualizar_pagina()
            except Exception as ex:
                self._mostrar_error(f"No se pudo guardar la copia: {ex}")

    def _abrir_configuracion(self, e):
        if not self._sesion_disponible():
            return
        from proveedores_ia import obtener_proveedores_disponibles
        proveedores = obtener_proveedores_disponibles()

        texto = (
            "Configuración de Aula IA\n\n"
            f"Modo demostración: {'activado' if MODO_DEMOSTRACION else 'desactivado'}\n"
            f"Proveedores configurados: {', '.join(proveedores) if proveedores else 'ninguno'}\n\n"
            "Edita el archivo .env en la carpeta del proyecto para configurar "
            "GEMINI_API_KEY, NVIDIA_API_KEY con sus modelos candidatos, "
            "GROQ_API_KEY con sus modelos candidatos u OPENROUTER_API_KEY."
        )

        dialogo = ft.AlertDialog(
            title=ft.Text("Configuración"),
            content=ft.Text(texto),
            actions=[ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())],
        )
        try:
            self.page.show_dialog(dialogo)
        except RuntimeError as ex:
            if "destroyed session" in str(ex).lower():
                self._on_sesion_finalizada()
                return
            logger.warning("No se pudo mostrar el diálogo: %s", ex)


def main(page: ft.Page):
    AulaIAApp(page)
