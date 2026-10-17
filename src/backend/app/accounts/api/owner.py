"""Rutas del panel del propietario (plan Contratos: /api/owner/*).

Ninguna recibe el establecimiento: sale de la sesión (D9, R015).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.accounts.api.deps import CurrentOwner
from app.accounts.application.get_owner import GetOwnerProfile
from app.accounts.application.get_qr import EmailNotVerified, GetQr
from app.accounts.application.resend_verification import (
    AlreadyVerified,
    ResendRateLimited,
    ResendVerification,
)
from app.accounts.application.update_establishment import UpdateEstablishment
from app.accounts.domain.ports import OwnerProfile
from app.accounts.domain.registration import RegistrationRejected
from app.shared.config import Settings

router = APIRouter(prefix="/owner")


class ResendOut(BaseModel):
    status: Literal["check_email"] = "check_email"


def _resend_verification(request: Request) -> ResendVerification:
    resend: ResendVerification = request.app.state.resend_verification
    return resend


@router.post(
    "/email-verification/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ResendOut,
    responses={
        409: {"description": "already_verified"},
        429: {"description": "resend_rate_limited"},
    },
)
async def resend_verification(
    owner: CurrentOwner,
    resend: Annotated[ResendVerification, Depends(_resend_verification)],
) -> ResendOut | JSONResponse:
    try:
        await resend(owner)
    except AlreadyVerified:
        return JSONResponse(status_code=409, content={"error": "already_verified"})
    except ResendRateLimited:
        # Sin peligro de revelar nada: el propietario ya tiene sesión (R027).
        return JSONResponse(status_code=429, content={"error": "resend_rate_limited"})
    return ResendOut()


class AccountOut(BaseModel):
    email: str
    email_verified: bool


class EstablishmentOut(BaseModel):
    name: str
    address: str | None
    phone: str | None
    public_url: str


class OwnerMeOut(BaseModel):
    account: AccountOut
    establishment: EstablishmentOut


class EstablishmentPatchIn(BaseModel):
    # Los campos que no llegan no cambian; cualquier otro campo (p. ej. un
    # establishment_id) se ignora: el establecimiento sale de la sesión (D9).
    name: str | None = None
    address: str | None = None
    phone: str | None = None


def _get_owner_profile(request: Request) -> GetOwnerProfile:
    get_profile: GetOwnerProfile = request.app.state.get_owner_profile
    return get_profile


def _update_establishment(request: Request) -> UpdateEstablishment:
    update: UpdateEstablishment = request.app.state.update_establishment
    return update


def _establishment_out(request: Request, profile: OwnerProfile) -> EstablishmentOut:
    settings: Settings = request.app.state.settings
    return EstablishmentOut(
        name=profile.name,
        address=profile.address,
        phone=profile.phone,
        # La URL que codifica el QR (plan D1).
        public_url=f"{settings.public_base_url}/l/{profile.public_code}",
    )


@router.get("/me", response_model=OwnerMeOut)
async def me(
    request: Request,
    owner: CurrentOwner,
    get_profile: Annotated[GetOwnerProfile, Depends(_get_owner_profile)],
) -> OwnerMeOut:
    profile = await get_profile(owner)
    return OwnerMeOut(
        account=AccountOut(email=profile.email, email_verified=profile.email_verified),
        establishment=_establishment_out(request, profile),
    )


@router.patch(
    "/establishment",
    response_model=EstablishmentOut,
    responses={422: {"description": "Errores por campo: {errors: {campo: código}}"}},
)
async def update_establishment(
    request: Request,
    body: EstablishmentPatchIn,
    owner: CurrentOwner,
    update: Annotated[UpdateEstablishment, Depends(_update_establishment)],
) -> EstablishmentOut | JSONResponse:
    submitted = {name: getattr(body, name) for name in body.model_fields_set}
    try:
        profile = await update(owner, submitted)
    except RegistrationRejected as rejected:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"errors": {field: str(code) for field, code in rejected.errors.items()}},
        )
    return _establishment_out(request, profile)


def _get_qr(request: Request) -> GetQr:
    get_qr: GetQr = request.app.state.get_qr
    return get_qr


@router.get(
    "/establishment/qr.png",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        403: {"description": "email_not_verified"},
    },
)
async def establishment_qr(
    owner: CurrentOwner, get_qr: Annotated[GetQr, Depends(_get_qr)], download: bool = False
) -> Response:
    try:
        image = await get_qr(owner)
    except EmailNotVerified:
        return JSONResponse(status_code=403, content={"error": "email_not_verified"})
    headers = {"Cache-Control": "no-store"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="qr-{image.public_code}.png"'
    return Response(content=image.png, media_type="image/png", headers=headers)
