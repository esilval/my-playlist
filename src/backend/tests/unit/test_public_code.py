from app.accounts.domain.public_code import ALPHABET, LENGTH, generate_public_code, is_public_code


def test_F001_R009_public_code_10_caracteres_crockford() -> None:
    codes = {generate_public_code() for _ in range(2000)}

    assert LENGTH == 10
    assert ALPHABET == "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    assert all(len(code) == 10 and set(code) <= set(ALPHABET) for code in codes)
    assert not set(ALPHABET) & set("ILOU")
    # 2000 códigos de ~50 bits: una colisión aquí indicaría una fuente no aleatoria.
    assert len(codes) == 2000


def test_F001_R009_public_code_usa_todo_el_alfabeto() -> None:
    seen = set("".join(generate_public_code() for _ in range(500)))

    assert seen == set(ALPHABET)


def test_F001_R013_forma_del_codigo_publico() -> None:
    code = generate_public_code()

    assert is_public_code(code)
    for bad in (code.lower(), code[:-1], code + "0", "", "\x00" + code[1:], "O" + code[1:]):
        assert not is_public_code(bad), bad
