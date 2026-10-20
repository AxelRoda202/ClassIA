"""
Coordinador de generación educativa con IA.

Usa el sistema de generación segmentada por bloques (generador_bloques.py)
para evitar respuestas JSON truncadas de los proveedores de IA.

El flujo es:
1. Planificación general (una solicitud pequeña)
2. Desarrollo de secciones teóricas por bloque
3. Generación de ejercicios en lotes
4. Componentes finales (resumen, glosario, metadatos)
5. Ensamblado local y generación de PDF

Cada etapa valida su respuesta antes de continuar, guarda el progreso
en disco y permite recuperación si falla un bloque.
"""
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from configuracion import (
    CARPETA_TEMPORAL, CARPETA_SALIDA,
    MODO_DEMOSTRACION, TIMEOUT_SEGUNDOS,
    MAX_EXTERNAL_IMAGES_PER_PDF,
)
from generador_bloques import GeneradorBloques


class GeneradorIA:
    """
    Coordina todo el flujo: solicitud a IA, validación, gráficos, PDF y recuperación.

    Usa internamente GeneradorBloques para la generación segmentada.
    Mantiene la misma interfaz pública que la versión anterior.
    """

    def __init__(self):
        self.trabajo_id: Optional[str] = None
        self.carpeta_trabajo: Optional[Path] = None
        self._generador_bloques = GeneradorBloques()

    # ------------------------------------------------------------------
    # Delegación a GeneradorBloques
    # ------------------------------------------------------------------

    def generar(
        self,
        tema: str,
        disciplina: str,
        nivel: str,
        profundidad: str,
        cantidad_actividades: int,
        recursos_visuales: bool,
        usar_imagenes_externas: bool = False,
        usar_demostracion: bool = False,
        callback_progreso: Optional[callable] = None,
        cancelacion: Optional[object] = None,
        trabajo_id: Optional[str] = None,
        reanudar: bool = False,
    ) -> Dict[str, Any]:
        """
        Ejecuta el flujo completo de generación segmentada.

        Devuelve un diccionario con el resultado: éxito, ruta del PDF,
        material, mensajes de error, etc.
        """
        self.trabajo_id = trabajo_id or uuid.uuid4().hex[:12]
        self.carpeta_trabajo = Path(CARPETA_TEMPORAL) / self.trabajo_id
        self.carpeta_trabajo.mkdir(parents=True, exist_ok=True)

        # Delegar en GeneradorBloques con callback de progreso
        resultado = self._generador_bloques.generar(
            tema=tema,
            disciplina=disciplina,
            nivel=nivel,
            profundidad=profundidad,
            cantidad_actividades=cantidad_actividades,
            recursos_visuales=recursos_visuales,
            usar_imagenes_externas=usar_imagenes_externas,
            usar_demostracion=usar_demostracion,
            trabajo_id=self.trabajo_id,
            callback_progreso=callback_progreso,
            cancelacion=cancelacion,
            reanudar=reanudar,
        )

        # Sincronizar IDs para compatibilidad con la interfaz
        resultado["trabajo_id"] = self.trabajo_id
        return resultado

    def regenerar_pdf_desde_trabajo(self, trabajo_id: str) -> Dict[str, Any]:
        """
        Intenta regenerar el PDF a partir de un trabajo guardado,
        sin llamar nuevamente a la IA.
        """
        return self._generador_bloques.regenerar_desde_trabajo(trabajo_id)

    def listar_trabajos_recuperables(self):
        """
        Lista los trabajos guardados que se pueden reconstruir o continuar.
        No llama a la IA ni modifica archivos.
        """
        return self._generador_bloques.listar_trabajos_recuperables()

    def continuar_desde_trabajo(
        self,
        trabajo_id: str,
        callback_progreso: Optional[callable] = None,
        cancelacion: Optional[object] = None,
    ) -> Dict[str, Any]:
        """
        Reanuda un trabajo incompleto y reutiliza plan, secciones, lotes y
        componentes ya validados. Sólo pide a la IA lo que falte.
        """
        resultado = self._generador_bloques.continuar_desde_trabajo(
            trabajo_id,
            callback_progreso=callback_progreso,
            cancelacion=cancelacion,
        )
        self.trabajo_id = trabajo_id
        self.carpeta_trabajo = Path(CARPETA_TEMPORAL) / trabajo_id
        resultado.setdefault("trabajo_id", trabajo_id)
        return resultado
