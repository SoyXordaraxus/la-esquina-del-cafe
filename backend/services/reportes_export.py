"""
Exportación de reportes (RF 12) a PDF y CSV, 100% local (RF 20).

Los dos formatos salen de la misma estructura que arma routes/reportes_admin.py:

    reporte = {
        "titulo":     "Reporte de Ventas Netas",
        "columnas":   ["Fecha", "Ventas completadas", ...],
        "alineacion": ["L", "R", ...],          # L = texto, R = números
        "filas":      [["21/11/2026", "3", "$150.00", ...], ...],   # ya formateadas
        "total":      ["TOTAL", "3", "$150.00", ...],                # o None
    }
    meta = {"periodo": (date_ini, date_fin), "usuario": "Andres Mosso", "generado": datetime local}

PDF: fpdf2 (Python puro, sin internet). Tabla con encabezado café repetido en cada
página, filas alternadas, números a la derecha, fila de TOTAL y "Página X de Y".
Si las columnas no caben en vertical, la hoja va en horizontal.

CSV: UTF-8 con BOM (Excel muestra bien los acentos), mismos encabezados y TOTAL.
"""
import csv
import io
from datetime import date, datetime
from typing import Dict, List, Optional

NOMBRE_NEGOCIO = "La Esquina del Café"
SIN_REGISTROS = "Sin registros en este periodo"

# Colores (RGB) de la paleta del sistema (estilos.css: --cafe-oscuro #4E342E)
CAFE_OSCURO = (78, 52, 46)
CREMA_FILA = (246, 240, 234)
CREMA_TOTAL = (232, 220, 208)
TEXTO_SUAVE = (110, 98, 87)


# ---------------------------------------------------------------- formato
def dinero(valor: float, negativo: bool = False) -> str:
    """$1,234.50. negativo=True -> -$1,234.50, salvo cero, que siempre es $0.00."""
    valor = round(float(valor or 0), 2)
    if valor == 0:
        return "$0.00"
    signo = "-" if (negativo or valor < 0) else ""
    return f"{signo}${abs(valor):,.2f}"


def numero(valor: float) -> str:
    """1,234.5 · 2,000 · 0.25 (sin ceros de más)."""
    valor = round(float(valor or 0), 2)
    texto = f"{valor:,.2f}".rstrip("0").rstrip(".")
    return texto or "0"


def fecha_dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def cantidades_por_unidad(acumulado: Dict[str, float]) -> str:
    """{'g': 1200, 'ml': 300} -> '1,200 g · 300 ml' (no se suman unidades distintas)."""
    if not acumulado:
        return "0"
    return " · ".join(f"{numero(v)} {u}".strip() for u, v in sorted(acumulado.items()))


def _lineas_encabezado(reporte: dict, meta: dict) -> List[str]:
    ini, fin = meta["periodo"]
    return [
        NOMBRE_NEGOCIO,
        reporte["titulo"],
        f"Periodo: {fecha_dmy(ini)} al {fecha_dmy(fin)}",
        f"Generado el {meta['generado'].strftime('%d/%m/%Y %H:%M')} por {meta['usuario']}",
    ]


# ---------------------------------------------------------------- CSV
def generar_csv(reporte: dict, meta: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for linea in _lineas_encabezado(reporte, meta):
        writer.writerow([linea])
    writer.writerow([])
    writer.writerow(reporte["columnas"])
    if reporte["filas"]:
        writer.writerows(reporte["filas"])
    else:
        writer.writerow([SIN_REGISTROS])
    if reporte.get("total"):
        writer.writerow(reporte["total"])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- PDF
# Las fuentes estándar del PDF (Helvetica) usan latin-1: acentos, ñ, ü, ¿, ¡ y · sí
# caben; otros signos tipográficos se cambian por su equivalente simple.
_SUSTITUTOS = {"—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "·", "≤": "<=", "≥": ">=", "→": "->"}


def _pdf_texto(texto) -> str:
    t = str(texto if texto is not None else "")
    for original, cambio in _SUSTITUTOS.items():
        t = t.replace(original, cambio)
    return t.encode("latin-1", errors="replace").decode("latin-1")


def generar_pdf(reporte: dict, meta: dict) -> bytes:
    try:
        from fpdf import FPDF
        from fpdf.fonts import FontFace
    except ImportError as exc:   # pragma: no cover - depende de la instalación
        raise RuntimeError(
            "Falta la biblioteca fpdf2 para generar PDF. Instálala con: pip install -r requirements.txt"
        ) from exc

    columnas = [_pdf_texto(c) for c in reporte["columnas"]]
    alineacion = reporte.get("alineacion") or ["L"] * len(columnas)
    filas = [[_pdf_texto(c) for c in fila] for fila in reporte["filas"]]
    total = [_pdf_texto(c) for c in reporte["total"]] if reporte.get("total") else None
    encabezado = [_pdf_texto(t) for t in _lineas_encabezado(reporte, meta)]

    margen, tam_letra, relleno = 12, 9, 2.2

    class PDFReporte(FPDF):
        def header(self):
            self.set_text_color(*CAFE_OSCURO)
            self.set_font("Helvetica", "B", 15)
            self.cell(0, 7, encabezado[0], new_x="LMARGIN", new_y="NEXT")
            self.set_font("Helvetica", "B", 12)
            self.cell(0, 6, encabezado[1], new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(*TEXTO_SUAVE)
            self.set_font("Helvetica", "", 9)
            self.cell(0, 5, encabezado[2], new_x="LMARGIN", new_y="NEXT")
            self.cell(0, 5, encabezado[3], new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*CAFE_OSCURO)
            self.set_line_width(0.4)
            self.line(self.l_margin, self.get_y() + 1.5, self.w - self.r_margin, self.get_y() + 1.5)
            self.ln(5)
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*TEXTO_SUAVE)
            self.cell(0, 6, _pdf_texto(f"{NOMBRE_NEGOCIO} · {reporte['titulo']}"), align="L")
            self.set_x(self.l_margin)
            self.cell(0, 6, f"Página {self.page_no()} de {{nb}}", align="R")

    # Ancho natural de cada columna: el texto más largo (medido en negritas, como el
    # encabezado y el TOTAL), sin pasar de 70 mm; lo que exceda se parte en renglones.
    medidor = FPDF()
    medidor.add_page()
    medidor.set_font("Helvetica", "B", tam_letra)
    anchos = []
    for i, col in enumerate(columnas):
        ancho = medidor.get_string_width(col)
        for fila in filas + ([total] if total else []):
            if i < len(fila):
                ancho = max(ancho, medidor.get_string_width(fila[i]))
        anchos.append(min(ancho + 2 * relleno + 2, 70))
    vertical_util = 215.9 - 2 * margen   # carta vertical
    orientacion = "P" if sum(anchos) <= vertical_util else "L"

    pdf = PDFReporte(orientation=orientacion, unit="mm", format="Letter")
    pdf.set_margins(margen, margen, margen)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_title(_pdf_texto(f"{NOMBRE_NEGOCIO} - {reporte['titulo']}"))
    pdf.set_author(_pdf_texto(meta["usuario"]))
    pdf.set_creator(_pdf_texto(NOMBRE_NEGOCIO))
    pdf.set_creation_date(meta["generado"])
    pdf.add_page()
    pdf.set_font("Helvetica", "", tam_letra)

    util = pdf.w - 2 * margen
    escala = util / sum(anchos)
    anchos_mm = [a * escala for a in anchos]   # columnas fijas que llenan el ancho útil

    estilo_encabezado = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=CAFE_OSCURO)
    estilo_total = FontFace(emphasis="BOLD", color=CAFE_OSCURO, fill_color=CREMA_TOTAL)
    estilo_vacio = FontFace(emphasis="ITALICS", color=TEXTO_SUAVE)

    with pdf.table(
        col_widths=anchos_mm,
        width=util,
        align="LEFT",
        text_align=tuple("RIGHT" if a == "R" else "LEFT" for a in alineacion),
        headings_style=estilo_encabezado,
        cell_fill_color=CREMA_FILA,
        cell_fill_mode="ROWS",
        borders_layout="HORIZONTAL_LINES",
        line_height=tam_letra * 0.5,
        padding=relleno,
        repeat_headings=1,
    ) as tabla:
        tabla.row(columnas)
        if filas:
            for fila in filas:
                tabla.row(fila)
        else:
            tabla.row().cell(SIN_REGISTROS, colspan=len(columnas), align="CENTER", style=estilo_vacio)
        if total:
            fila_total = tabla.row(style=estilo_total)
            for valor, alin in zip(total, alineacion):
                fila_total.cell(valor, align="RIGHT" if alin == "R" else "LEFT")

    return bytes(pdf.output())


def nombre_archivo(tipo: str, ini: date, fin: date, formato: str) -> str:
    return f"reporte_{tipo}_{ini:%Y%m%d}_{fin:%Y%m%d}.{formato}"


def meta_reporte(periodo, usuario: str, generado: Optional[datetime]) -> dict:
    return {"periodo": periodo, "usuario": usuario, "generado": generado}
