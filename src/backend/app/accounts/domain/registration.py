"""Reglas del formulario de registro (R003, R004, R022) y normalización del correo (D8)."""

from dataclasses import dataclass
from enum import StrEnum

from email_validator import EmailNotValidError, validate_email

MIN_PASSWORD_LENGTH = 8


class FieldError(StrEnum):
    REQUIRED = "required"
    INVALID_EMAIL = "invalid_email"
    PASSWORD_TOO_SHORT = "password_too_short"
    AUTHORIZATION_REQUIRED = "authorization_required"
    OUTDATED = "outdated"


@dataclass(frozen=True)
class RegistrationForm:
    email: str
    password: str
    establishment_name: str
    address: str | None
    phone: str | None
    data_authorization: bool
    # Versión de la política que el formulario mostró junto a la autorización (R022).
    policy_version: str


@dataclass(frozen=True)
class ValidRegistration:
    email: str
    email_normalized: str
    password: str
    establishment_name: str
    address: str | None
    phone: str | None
    policy_version: str


class RegistrationRejected(Exception):
    """El formulario tiene campos inválidos; `errors` los lista todos a la vez (R003)."""

    def __init__(self, errors: dict[str, FieldError]) -> None:
        super().__init__(f"registro rechazado: {sorted(errors)}")
        self.errors = errors


def normalize_email(email: str) -> str:
    """Clave de cuenta: todo alta y toda búsqueda por correo pasan por aquí (D8)."""
    return email.strip().lower()


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _is_valid_email(email: str) -> bool:
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return False
    return True


def password_error(password: str) -> FieldError | None:
    """Regla de contraseña del registro y del restablecimiento (R003, R016)."""
    if not password:
        return FieldError.REQUIRED
    if len(password) < MIN_PASSWORD_LENGTH:
        return FieldError.PASSWORD_TOO_SHORT
    return None


def validate_registration(form: RegistrationForm, current_policy_version: str) -> ValidRegistration:
    errors: dict[str, FieldError] = {}

    email = form.email.strip()
    if not email:
        errors["email"] = FieldError.REQUIRED
    elif not _is_valid_email(email):
        errors["email"] = FieldError.INVALID_EMAIL

    if (error := password_error(form.password)) is not None:
        errors["password"] = error

    name = form.establishment_name.strip()
    if not name:
        errors["establishment_name"] = FieldError.REQUIRED

    if not form.data_authorization:
        errors["data_authorization"] = FieldError.AUTHORIZATION_REQUIRED
    elif form.policy_version != current_policy_version:
        # La autorización guardada tiene que ser sobre la política que el propietario vio.
        errors["policy_version"] = FieldError.OUTDATED

    if errors:
        raise RegistrationRejected(errors)

    return ValidRegistration(
        email=email,
        email_normalized=normalize_email(email),
        password=form.password,
        establishment_name=name,
        address=_optional(form.address),
        phone=_optional(form.phone),
        policy_version=form.policy_version,
    )
