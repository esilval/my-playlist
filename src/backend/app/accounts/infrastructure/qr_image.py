"""Imagen del QR: segno para el código y Pillow para componerla con el nombre (plan D6).

Unos 1200 x 1360 px: el QR con corrección de errores M y 4 módulos de margen, y el
nombre del establecimiento debajo, en dos líneas como mucho. Pensada para imprimirse
en tamaño carta y escanearse con la cámara del móvil.
"""

import io
from functools import cache
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Inter-Variable.ttf"

WIDTH = 1200
QR_SIZE = 1100  # máximo; la escala entera de los módulos lo deja algo por debajo
MARGIN_TOP = 50
TEXT_GAP = 20
LINE_HEIGHT = 84
FONT_SIZE = 64
QUIET_ZONE = 4
MAX_LINES = 2


@cache
def _font() -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
    font.set_variation_by_name("SemiBold")
    return font


def _wrap(name: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Reparte el nombre en dos líneas como mucho; recorta con «…» si no cabe."""
    lines: list[str] = []
    current = ""
    for word in name.split():
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if len(lines) > MAX_LINES:
        lines = [*lines[: MAX_LINES - 1], " ".join(lines[MAX_LINES - 1 :])]
    fitted = []
    for line in lines:
        while font.getlength(line) > max_width and len(line) > 1:
            line = line[:-2].rstrip() + "…"
        fitted.append(line)
    return fitted


class SegnoQrImageRenderer:
    def render(self, url: str, establishment_name: str) -> bytes:
        qr = segno.make_qr(url, error="m")
        modules = qr.symbol_size(scale=1, border=QUIET_ZONE)[0]
        scale = QR_SIZE // modules
        buffer = io.BytesIO()
        qr.save(buffer, kind="png", scale=scale, border=QUIET_ZONE)
        code = Image.open(io.BytesIO(buffer.getvalue())).convert("L")

        font = _font()
        lines = _wrap(establishment_name, font, QR_SIZE)
        text_top = MARGIN_TOP + code.height + TEXT_GAP
        height = text_top + MAX_LINES * LINE_HEIGHT + MARGIN_TOP

        canvas = Image.new("L", (WIDTH, height), color=255)
        canvas.paste(code, ((WIDTH - code.width) // 2, MARGIN_TOP))

        draw = ImageDraw.Draw(canvas)
        for index, line in enumerate(lines):
            line_width = font.getlength(line)
            draw.text(
                ((WIDTH - line_width) / 2, text_top + index * LINE_HEIGHT), line, fill=0, font=font
            )

        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue()
