from app.accounts.infrastructure.qr_image import MAX_LINES, QR_SIZE, _font, _wrap


def test_F001_R010_nombre_corto_en_una_linea() -> None:
    assert _wrap("Café Ñandú", _font(), QR_SIZE) == ["Café Ñandú"]


def test_F001_R010_nombre_largo_en_dos_lineas_con_puntos_suspensivos() -> None:
    name = "Restaurante y Bar La Gran Esquina de los Amigos del Barrio Chapinero Alto Bogotá"
    lines = _wrap(name, _font(), QR_SIZE)

    assert len(lines) == MAX_LINES
    assert lines[-1].endswith("…")
    assert all(_font().getlength(line) <= QR_SIZE for line in lines)
    assert lines[0].startswith("Restaurante y Bar")


def test_F001_R010_palabra_sin_espacios_mas_ancha_que_el_qr_se_recorta() -> None:
    [line] = _wrap("A" * 200, _font(), QR_SIZE)

    assert line.endswith("…") and _font().getlength(line) <= QR_SIZE
