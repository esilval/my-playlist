import pytest

from app.accounts.domain.establishment import validate_establishment_changes
from app.accounts.domain.registration import FieldError, RegistrationRejected


def test_F001_R014_solo_cambian_los_campos_enviados() -> None:
    changes = validate_establishment_changes({"name": "  La Esquina Bar ", "phone": "  "})

    assert changes.values == {"name": "La Esquina Bar", "phone": None}


def test_F001_R014_nombre_vacio_se_rechaza() -> None:
    for name in ("", "   ", None):
        with pytest.raises(RegistrationRejected) as rejected:
            validate_establishment_changes({"name": name})
        assert rejected.value.errors == {"name": FieldError.REQUIRED}


def test_F001_R014_sin_campos_no_cambia_nada() -> None:
    assert validate_establishment_changes({}).values == {}
