
"""
Generación del PDF con ReportLab.

Construye un documento A4 con portada, identidad institucional,
encabezados, pies de página, numeración y los bloques de contenido
definidos en el JSON validado.
"""
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Image, Table, TableStyle, PageBreak, KeepTogether, HRFlowable,
)
from reportlab.lib.utils import ImageReader

from configuracion import (
    CARPETA_SALIDA, LOGO_PDF_POR_DEFECTO, LOGO_POR_DEFECTO,
    COLOR_ROJO_INSTITUCIONAL, COLOR_AMARILLO_INSTITUCIONAL,
)

ANCHO_PAGE, ALTO_PAGE = A4
MARGEN = 20 * mm


def fecha_local() -> str:
    """Fecha de generación calculada localmente, nunca tomada de la IA."""
    return datetime.now().strftime("%d/%m/%Y")


def escapar_texto(texto: str) -> str:
    """Escapa caracteres especiales para los componentes de ReportLab."""
    if not texto:
        return ""
    texto = texto.replace("&", "&amp;")
    texto = texto.replace("<", "&lt;")
    texto = texto.replace(">", "&gt;")
    return texto


def crear_estilos() -> Dict[str, ParagraphStyle]:
    """Crea y devuelve los estilos de párrafo del documento."""
    return {
        "portada_titulo": ParagraphStyle(
            "portada_titulo", fontName="Helvetica-Bold", fontSize=26,
            leading=34, alignment=TA_CENTER, textColor=colors.HexColor(COLOR_ROJO_INSTITUCIONAL),
            spaceAfter=6,
        ),
        "portada_subtitulo": ParagraphStyle(
            "portada_subtitulo", fontName="Helvetica", fontSize=14,
            leading=20, alignment=TA_CENTER, textColor=colors.HexColor("#333333"),
            spaceAfter=18,
        ),
        "portada_datos": ParagraphStyle(
            "portada_datos", fontName="Helvetica", fontSize=11,
            leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#333333"),
        ),
        "h1": ParagraphStyle(
            "h1", fontName="Helvetica-Bold", fontSize=16, leading=20,
            textColor=colors.HexColor(COLOR_ROJO_INSTITUCIONAL),
            spaceBefore=14, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2", fontName="Helvetica-Bold", fontSize=13, leading=17,
            textColor=colors.HexColor("#555555"),
            spaceBefore=10, spaceAfter=6,
        ),
        "parrafo": ParagraphStyle(
            "parrafo", fontName="Helvetica", fontSize=10.5, leading=15,
            alignment=TA_JUSTIFY, textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=10.5, leading=15,
            alignment=TA_JUSTIFY, textColor=colors.HexColor("#1a1a1a"),
            leftIndent=14, bulletIndent=4, spaceAfter=3,
        ),
        "numero": ParagraphStyle(
            "numero", fontName="Helvetica", fontSize=10.5, leading=15,
            alignment=TA_JUSTIFY, textColor=colors.HexColor("#1a1a1a"),
            leftIndent=14, bulletIndent=4, spaceAfter=3,
        ),
        "definicion": ParagraphStyle(
            "definicion", fontName="Helvetica-Oblique", fontSize=10, leading=14,
            textColor=colors.HexColor("#333333"), leftIndent=14,
            spaceAfter=6,
        ),
        "callout": ParagraphStyle(
            "callout", fontName="Helvetica-Oblique", fontSize=10.5, leading=14,
            textColor=colors.HexColor("#1a1a1a"),
            backColor=colors.HexColor("#FFF8E1"),
            borderColor=colors.HexColor(COLOR_AMARILLO_INSTITUCIONAL),
            borderWidth=1, borderPadding=8, spaceBefore=8, spaceAfter=8,
        ),
        "actividad_titulo": ParagraphStyle(
            "actividad_titulo", fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=colors.HexColor(COLOR_ROJO_INSTITUCIONAL),
            spaceBefore=10, spaceAfter=4,
        ),
        "actividad_texto": ParagraphStyle(
            "actividad_texto", fontName="Helvetica", fontSize=10, leading=14,
            textColor=colors.HexColor("#1a1a1a"), leftIndent=10,
            spaceAfter=3,
        ),
        "solucionario_titulo": ParagraphStyle(
            "solucionario_titulo", fontName="Helvetica-Bold", fontSize=16, leading=20,
            textColor=colors.HexColor(COLOR_ROJO_INSTITUCIONAL),
            spaceBefore=14, spaceAfter=8,
        ),
        "pie": ParagraphStyle(
            "pie", fontName="Helvetica", fontSize=8, leading=10,
            alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
        ),
        "advertencia": ParagraphStyle(
            "advertencia", fontName="Helvetica-Oblique", fontSize=8.5, leading=11,
            alignment=TA_CENTER, textColor=colors.HexColor("#888888"),
            spaceBefore=10,
        ),
    }


def _dibujar_encabezado_pie(canvas, doc, mostrar_logo: bool = True):
    """Dibuja encabezado y pie de página en cada hoja."""
    canvas.saveState()

    # Línea superior del encabezado
    canvas.setStrokeColor(colors.HexColor(COLOR_ROJO_INSTITUCIONAL))
    canvas.setLineWidth(1.2)
    canvas.line(MARGEN, ALTO_PAGE - 14 * mm, ANCHO_PAGE - MARGEN, ALTO_PAGE - 14 * mm)

    # Logo pequeño en el encabezado (derecha) - escudo institucional del PDF
    if mostrar_logo and LOGO_PDF_POR_DEFECTO.exists():
        try:
            logo = ImageReader(str(LOGO_PDF_POR_DEFECTO))
            ancho_logo = 14 * mm
            alto_logo = ancho_logo  # proporciones cuadradas aproximadas
            canvas.drawImage(
                logo,
                ANCHO_PAGE - MARGEN - ancho_logo,
                ALTO_PAGE - 13 * mm,
                width=ancho_logo, height=alto_logo,
                preserveAspectRatio=True,
            )
        except Exception:
            pass

    # Pie de página
    canvas.setStrokeColor(colors.HexColor(COLOR_AMARILLO_INSTITUCIONAL))
    canvas.setLineWidth(0.8)
    canvas.line(MARGEN, 14 * mm, ANCHO_PAGE - MARGEN, 14 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(
        MARGEN, 10 * mm,
        "Aula IA - Material generado con Inteligencia Artificial"
    )
    canvas.drawRightString(
        ANCHO_PAGE - MARGEN, 10 * mm,
        f"Página {doc.page}"
    )

    canvas.restoreState()


def construir_pdf(
    material: Dict[str, Any],
    rutas_graficos: Dict[str, str],
    ruta_salida: Path,
) -> bool:
    """
    Construye el PDF a partir del material validado y las rutas de gráficos.

    Devuelve True si se generó correctamente, False en caso contrario.
    """
    try:
        metadatos = material.get("metadatos", {})
        titulo = metadatos.get("titulo", "Material educativo")
        subtitulo = metadatos.get("subtitulo", "")
        tema = metadatos.get("tema", "")
        nivel = metadatos.get("nivel", "")
        disciplina = metadatos.get("disciplina", "")
        fecha = fecha_local()

        doc = BaseDocTemplate(
            str(ruta_salida),
            pagesize=A4,
            leftMargin=MARGEN, rightMargin=MARGEN,
            topMargin=22 * mm, bottomMargin=20 * mm,
            title=titulo,
            author="Aula IA",
            subject=tema,
        )

        frame = Frame(
            MARGEN, 20 * mm,
            ANCHO_PAGE - 2 * MARGEN,
            ALTO_PAGE - 22 * mm - 20 * mm,
            id="contenido",
        )
        doc.addPageTemplates([
            PageTemplate(id="pagina", frames=[frame],
                         onPage=lambda c, d: _dibujar_encabezado_pie(c, d))
        ])

        estilos = crear_estilos()
        elementos = []

        # ---------- PORTADA ----------
        if LOGO_PDF_POR_DEFECTO.exists():
            try:
                img_logo = Image(str(LOGO_PDF_POR_DEFECTO))
                ancho_disponible = ANCHO_PAGE - 2 * MARGEN
                alto_max = 45 * mm
                ratio = img_logo.imageHeight / img_logo.imageWidth
                ancho_logo = min(ancho_disponible, 60 * mm)
                alto_logo = ancho_logo * ratio
                if alto_logo > alto_max:
                    alto_logo = alto_max
                    ancho_logo = alto_logo / ratio
                img_logo.drawWidth = ancho_logo
                img_logo.drawHeight = alto_logo
                elementos.append(img_logo)
            except Exception:
                pass

        elementos.append(Spacer(1, 10 * mm))
        elementos.append(Paragraph(escapar_texto(titulo), estilos["portada_titulo"]))
        if subtitulo:
            elementos.append(Paragraph(escapar_texto(subtitulo), estilos["portada_subtitulo"]))

        elementos.append(HRFlowable(
            width="60%", thickness=2, color=colors.HexColor(COLOR_AMARILLO_INSTITUCIONAL),
            hAlign="CENTER", spaceBefore=4, spaceAfter=10,
        ))

        datos_portada = [
            [Paragraph("<b>Tema:</b>", estilos["portada_datos"]), Paragraph(escapar_texto(tema), estilos["portada_datos"])],
            [Paragraph("<b>Disciplina:</b>", estilos["portada_datos"]), Paragraph(escapar_texto(disciplina), estilos["portada_datos"])],
            [Paragraph("<b>Nivel:</b>", estilos["portada_datos"]), Paragraph(escapar_texto(nivel), estilos["portada_datos"])],
            [Paragraph("<b>Fecha:</b>", estilos["portada_datos"]), Paragraph(escapar_texto(fecha), estilos["portada_datos"])],
        ]
        tabla_portada = Table(datos_portada)
        tabla_portada.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        elementos.append(tabla_portada)

        elementos.append(Spacer(1, 8 * mm))
        elementos.append(Paragraph(
            escapar_texto(material.get("advertencia_ia", "")),
            estilos["advertencia"],
        ))

        elementos.append(PageBreak())

        # ---------- INTRODUCCIÓN Y OBJETIVOS ----------
        elementos.append(Paragraph("Introducción y objetivos", estilos["h1"]))
        if material.get("introduccion"):
            elementos.append(Paragraph(escapar_texto(material["introduccion"]), estilos["parrafo"]))

        objetivos = material.get("objetivos_aprendizaje", [])
        if objetivos:
            elementos.append(Paragraph("Objetivos de aprendizaje", estilos["h2"]))
            for obj in objetivos:
                elementos.append(Paragraph(
                    f"• {escapar_texto(obj)}", estilos["bullet"],
                ))

        previos = material.get("conocimientos_previos", [])
        if previos:
            elementos.append(Paragraph("Conocimientos previos recomendados", estilos["h2"]))
            for prev in previos:
                elementos.append(Paragraph(
                    f"• {escapar_texto(prev)}", estilos["bullet"],
                ))

        # ---------- SECCIONES ----------
        for seccion in material.get("secciones", []):
            elementos.append(Paragraph(escapar_texto(seccion.get("titulo", "")), estilos["h1"]))

            for bloque in seccion.get("bloques", []):
                tipo = bloque.get("tipo", "")

                if tipo == "heading":
                    elementos.append(Paragraph(escapar_texto(bloque.get("texto", "")), estilos["h2"]))

                elif tipo == "paragraph":
                    elementos.append(Paragraph(escapar_texto(bloque.get("texto", "")), estilos["parrafo"]))

                elif tipo == "bullet_list":
                    items = bloque.get("items", [])
                    for item in items:
                        elementos.append(Paragraph(
                            f"• {escapar_texto(item)}", estilos["bullet"],
                        ))

                elif tipo == "numbered_list":
                    items = bloque.get("items", [])
                    for idx, item in enumerate(items, 1):
                        elementos.append(Paragraph(
                            f"{idx}. {escapar_texto(item)}", estilos["numero"],
                        ))

                elif tipo == "equation":
                    expresion = bloque.get("expresion_matematica", bloque.get("expresion_texto", ""))
                    desc = bloque.get("descripcion", "")
                    elementos.append(Paragraph(
                        f"<b>{escapar_texto(desc)}:</b> {escapar_texto(expresion)}",
                        estilos["definicion"],
                    ))

                elif tipo == "definition":
                    termino = bloque.get("termino", "")
                    definicion = bloque.get("definicion", "")
                    elementos.append(Paragraph(
                        f"<b>{escapar_texto(termino)}.</b> {escapar_texto(definicion)}",
                        estilos["definicion"],
                    ))

                elif tipo == "callout":
                    elementos.append(Paragraph(
                        f"<i>{escapar_texto(bloque.get('texto', ''))}</i>",
                        estilos["callout"],
                    ))

                elif tipo == "visual_reference":
                    recurso_id = bloque.get("recurso_id", "")
                    # Buscar el diccionario completo del recurso en recursos_visuales
                    recurso_completo = {}
                    for rv in material.get("recursos_visuales", []):
                        if rv.get("id") == recurso_id:
                            recurso_completo = rv
                            break
                    _agregar_recurso_visual(
                        elementos, recurso_completo, rutas_graficos, estilos
                    )

        # ---------- EJEMPLOS RESUELTOS ----------
        ejemplos = material.get("ejemplos_resueltos", [])
        if ejemplos:
            elementos.append(Paragraph("Ejemplos resueltos", estilos["h1"]))
            for ejemplo in ejemplos:
                elementos.append(Paragraph(
                    f"<b>{escapar_texto(ejemplo.get('titulo', ''))}</b>",
                    estilos["actividad_titulo"],
                ))
                for paso in ejemplo.get("pasos", []):
                    elementos.append(Paragraph(
                        f"• {escapar_texto(paso)}", estilos["actividad_texto"],
                    ))
                elementos.append(Paragraph(
                    f"<b>Resultado:</b> {escapar_texto(ejemplo.get('resultado', ''))}",
                    estilos["actividad_texto"],
                ))

        # ---------- ACTIVIDADES ----------
        actividades = material.get("actividades", [])
        if actividades:
            elementos.append(Paragraph("Actividades de práctica", estilos["h1"]))
            for act in actividades:
                bloque_act = KeepTogether([
                    Paragraph(
                        f"<b>{escapar_texto(act.get('dificultad', '').upper())} - "
                        f"{escapar_texto(act.get('tipo', ''))}</b>",
                        estilos["actividad_titulo"],
                    ),
                    Paragraph(
                        f"{escapar_texto(act.get('consigna', ''))}",
                        estilos["actividad_texto"],
                    ),
                ])
                if act.get("pista"):
                    bloque_act = KeepTogether([
                        Paragraph(
                            f"<b>{escapar_texto(act.get('dificultad', '').upper())} - "
                            f"{escapar_texto(act.get('tipo', ''))}</b>",
                            estilos["actividad_titulo"],
                        ),
                        Paragraph(
                            f"{escapar_texto(act.get('consigna', ''))}",
                            estilos["actividad_texto"],
                        ),
                        Paragraph(
                            f"<i>Pista: {escapar_texto(act.get('pista', ''))}</i>",
                            estilos["actividad_texto"],
                        ),
                    ])
                elementos.append(bloque_act)

        # ---------- RESUMEN Y GLOSARIO ----------
        resumen = material.get("resumen_final", "")
        if resumen:
            elementos.append(Paragraph("Resumen", estilos["h1"]))
            elementos.append(Paragraph(escapar_texto(resumen), estilos["parrafo"]))

        glosario = material.get("glosario", [])
        if glosario:
            elementos.append(Paragraph("Glosario", estilos["h1"]))
            for item in glosario:
                elementos.append(Paragraph(
                    f"<b>{escapar_texto(item.get('termino', ''))}.</b> "
                    f"{escapar_texto(item.get('definicion', ''))}",
                    estilos["definicion"],
                ))

        # ---------- SOLUCIONARIO ----------
        solucionario = material.get("solucionario", [])
        if solucionario:
            elementos.append(Paragraph("Solucionario", estilos["solucionario_titulo"]))
            for sol in solucionario:
                elementos.append(Paragraph(
                    f"<b>Actividad {escapar_texto(sol.get('actividad_id', ''))}:</b> "
                    f"{escapar_texto(sol.get('respuesta', ''))}",
                    estilos["actividad_texto"],
                ))
                if sol.get("procedimiento"):
                    elementos.append(Paragraph(
                        f"Procedimiento: {escapar_texto(sol.get('procedimiento', ''))}",
                        estilos["actividad_texto"],
                    ))
                if sol.get("explicacion"):
                    elementos.append(Paragraph(
                        f"Explicación: {escapar_texto(sol.get('explicacion', ''))}",
                        estilos["actividad_texto"],
                    ))

        elementos.append(Spacer(1, 6 * mm))
        elementos.append(Paragraph(
            escapar_texto(material.get("advertencia_ia", "")),
            estilos["advertencia"],
        ))

        doc.build(elementos)
        return True

    except Exception as e:
        print(f"[generador_pdf] Error construyendo PDF: {e}")
        return False


def _agregar_recurso_visual(
    elementos: List[Any],
    recurso: Dict[str, Any],
    rutas_graficos: Dict[str, str],
    estilos: Dict[str, Any],
) -> None:
    """
    Agrega un recurso visual (imagen generada o tarjeta provisional) al flujo.

    Ahora recibe el diccionario completo del recurso para poder usar sus metadatos
    (título, pie de imagen, propósito educativo, texto alternativo) en la tarjeta
    provisional y en la inserción de la imagen.
    """
    recurso_id = recurso.get("id", "")
    tipo = recurso.get("type", "").strip().lower()
    titulo = recurso.get("title", "Recurso visual")
    caption = recurso.get("caption", "")
    descripcion = recurso.get("description", "")
    proposito = recurso.get("educational_purpose", "")
    ruta_imagen = rutas_graficos.get(recurso_id)

    if ruta_imagen and Path(ruta_imagen).exists():
        try:
            img = Image(ruta_imagen)
            ancho_max = ANCHO_PAGE - 2 * MARGEN
            ratio = img.imageHeight / img.imageWidth
            ancho = min(ancho_max, 110 * mm)
            alto = ancho * ratio
            img.drawWidth = ancho
            img.drawHeight = alto
            bloque = [Spacer(1, 3 * mm), img]
            if caption:
                bloque.append(Paragraph(
                    f"<i>{escapar_texto(caption)}</i>",
                    estilos["pie"],
                ))
            bloque.append(Spacer(1, 2 * mm))
            # La imagen y su pie deben quedar en la misma página.
            elementos.append(KeepTogether(bloque))
            return
        except Exception:
            pass

    # Tarjeta provisional para recursos externos no disponibles
    tarjeta_contenido = [
        Paragraph(
            f"<b>{escapar_texto(titulo)}</b>",
            estilos["actividad_titulo"],
        ),
        Paragraph(
            f"<i>{escapar_texto(descripcion)}</i>",
            estilos["actividad_texto"],
        ),
    ]
    if proposito:
        tarjeta_contenido.append(Paragraph(
            f"<b>Propósito:</b> {escapar_texto(proposito)}",
            estilos["actividad_texto"],
        ))
    if tipo == "external_image":
        tarjeta_contenido.append(Paragraph(
            "Ilustración propuesta para generación externa mediante IA. "
            "Este espacio se reemplazará automáticamente cuando se genere la imagen.",
            estilos["actividad_texto"],
        ))
    else:
        tarjeta_contenido.append(Paragraph(
            "Este espacio está reservado para un recurso visual que se añadirá "
            "cuando se integre la generación correspondiente.",
            estilos["actividad_texto"],
        ))

    tarjeta = Table(
        [tarjeta_contenido],
        colWidths=[ANCHO_PAGE - 2 * MARGEN],
    )
    tarjeta.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(COLOR_AMARILLO_INSTITUCIONAL)),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    # La tarjeta es un único bloque: si no cabe al final de la página, se
    # mueve completa a la siguiente en lugar de cortarse en una franja.
    elementos.append(KeepTogether([
        Spacer(1, 3 * mm),
        tarjeta,
        Spacer(1, 2 * mm),
    ]))
