import pytest

from app.accounts.domain.registration import (
    FieldError,
    RegistrationForm,
    RegistrationRejected,
    normalize_email,
    validate_registration,
)

CURRENT_POLICY = "2026-10"


def _form(**overrides: object) -> RegistrationForm:
    values: dict[str, object] = {
        "email": "dueno@ejemplo.com",
        "password": "12345678",
        "establishment_name": "Bar La Esquina",
        "address": None,
        "phone": None,
        "data_authorization": True,
        "policy_version": CURRENT_POLICY,
    }
    values.update(overrides)
    return RegistrationForm(**values)  # type: ignore[arg-type]


def _errors(form: RegistrationForm) -> dict[str, FieldError]:
    with pytest.raises(RegistrationRejected) as rejected:
        validate_registration(form, CURRENT_POLICY)
    return rejected.value.errors


def test_F001_R003_rechaza_cada_campo_invalido() -> None:
    errors = _errors(_form(establishment_name="   ", email="sin-arroba", password="1234567"))

    assert errors == {
        "establishment_name": FieldError.REQUIRED,
        "email": FieldError.INVALID_EMAIL,
        "password": FieldError.PASSWORD_TOO_SHORT,
    }


def test_F001_R003_campos_obligatorios_vacios() -> None:
    errors = _errors(_form(email="", password="", establishment_name=""))

    assert errors == {
        "email": FieldError.REQUIRED,
        "password": FieldError.REQUIRED,
        "establishment_name": FieldError.REQUIRED,
    }


def test_F001_R003_contrasena_de_8_caracteres_es_valida() -> None:
    assert validate_registration(_form(password="ñandú-12"), CURRENT_POLICY).password == "ñandú-12"


def test_F001_R004_exige_autorizacion() -> None:
    assert _errors(_form(data_authorization=False)) == {
        "data_authorization": FieldError.AUTHORIZATION_REQUIRED
    }


def test_F001_R024_normaliza_mayusculas_y_espacios() -> None:
    assert normalize_email("  Dueno@Ejemplo.COM ") == "dueno@ejemplo.com"

    valid = validate_registration(_form(email=" Dueno@Ejemplo.COM "), CURRENT_POLICY)
    assert valid.email == "Dueno@Ejemplo.COM"
    assert valid.email_normalized == "dueno@ejemplo.com"


def test_F001_R023_direccion_y_telefono_son_opcionales() -> None:
    empty = validate_registration(_form(address="  ", phone=""), CURRENT_POLICY)
    assert (empty.address, empty.phone) == (None, None)

    given = validate_registration(
        _form(address=" Calle 1 # 2-3 ", phone=" 3001234567 "), CURRENT_POLICY
    )
    assert (given.address, given.phone) == ("Calle 1 # 2-3", "3001234567")
    assert given.establishment_name == "Bar La Esquina"


def test_F001_R022_version_de_politica_desfasada() -> None:
    assert _errors(_form(policy_version="2025-01")) == {"policy_version": FieldError.OUTDATED}
    assert validate_registration(_form(), CURRENT_POLICY).policy_version == CURRENT_POLICY
