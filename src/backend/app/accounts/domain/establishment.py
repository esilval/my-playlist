"""Edición de los datos del establecimiento (R014, R019).

Un campo que no llega no cambia. El nombre, si llega, no puede quedar vacío;
dirección y teléfono son opcionales y se pueden vaciar. El código público del QR
no se edita nunca (R009).
"""

from dataclasses import dataclass, field

from app.accounts.domain.registration import FieldError, RegistrationRejected


@dataclass(frozen=True)
class EstablishmentChanges:
    # Solo los campos presentes en la petición; None en address/phone los vacía.
    values: dict[str, str | None] = field(default_factory=dict)


def validate_establishment_changes(
    submitted: dict[str, str | None],
) -> EstablishmentChanges:
    """Lanza RegistrationRejected con los campos inválidos, en el formato de R003."""
    values: dict[str, str | None] = {}
    errors: dict[str, FieldError] = {}
    if "name" in submitted:
        name = (submitted["name"] or "").strip()
        if name:
            values["name"] = name
        else:
            errors["name"] = FieldError.REQUIRED
    for optional in ("address", "phone"):
        if optional in submitted:
            value = (submitted[optional] or "").strip()
            values[optional] = value or None
    if errors:
        raise RegistrationRejected(errors)
    return EstablishmentChanges(values=values)
