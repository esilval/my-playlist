"""Rutas de autenticación del propietario (plan Contratos: /api/auth/*)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.accounts.api.deps import SESSION_COOKIE
from app.accounts.application.confirm_password_reset import (
    ConfirmPasswordReset,
    InvalidResetToken,
)
from app.accounts.application.login import InvalidCredentials, LoginOwner, TooManyAttempts
from app.accounts.application.logout import LogoutOwner
from app.accounts.application.register import RegisterOwner
from app.accounts.application.request_password_reset import RequestPasswordReset
from app.accounts.application.verify_email import (
    ExpiredVerificationToken,
    InvalidVerificationToken,
    VerifyEmail,
)
from app.accounts.domain.registration import RegistrationForm, RegistrationRejected

router = APIRouter(prefix="/auth")


class RegisterIn(BaseModel):
    # Todo es texto con valor por defecto: la validación de campos es del dominio, para
    # responder siempre con el mismo formato de errores (R003).
    email: str = ""
    password: str = ""
    establishment_name: str = ""
    address: str | None = None
    phone: str | None = None
    data_authorization: bool = False
    policy_version: str = ""


class CheckEmailOut(BaseModel):
    status: Literal["check_email"] = "check_email"


def _register_owner(request: Request) -> RegisterOwner:
    register_owner: RegisterOwner = request.app.state.register_owner
    return register_owner


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CheckEmailOut,
    responses={422: {"description": "Errores por campo: {errors: {campo: código}}"}},
)
async def register(
    body: RegisterIn, register_owner: Annotated[RegisterOwner, Depends(_register_owner)]
) -> CheckEmailOut | JSONResponse:
    try:
        await register_owner(RegistrationForm(**body.model_dump()))
    except RegistrationRejected as rejected:
        # La contraseña nunca vuelve en la respuesta (R003).
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"errors": {field: str(code) for field, code in rejected.errors.items()}},
        )
    return CheckEmailOut()


class LoginIn(BaseModel):
    email: str = ""
    password: str = ""


class AuthenticatedOut(BaseModel):
    status: Literal["authenticated"] = "authenticated"


def _login_owner(request: Request) -> LoginOwner:
    login_owner: LoginOwner = request.app.state.login_owner
    return login_owner


def _logout_owner(request: Request) -> LogoutOwner:
    logout_owner: LogoutOwner = request.app.state.logout_owner
    return logout_owner


def _set_session_cookie(response: Response, token: str) -> None:
    # Sin Max-Age: la caducidad la decide el servidor (12 h sin actividad, R020).
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=True, samesite="lax", path="/api"
    )


@router.post(
    "/login",
    response_model=AuthenticatedOut,
    responses={
        401: {"description": "invalid_credentials"},
        429: {"description": "too_many_attempts"},
    },
)
async def login(
    body: LoginIn, login_owner: Annotated[LoginOwner, Depends(_login_owner)]
) -> AuthenticatedOut | JSONResponse:
    try:
        token = await login_owner(body.email, body.password)
    except InvalidCredentials:
        # Mismo código y mismo cuerpo exista o no el correo (R006).
        return JSONResponse(status_code=401, content={"error": "invalid_credentials"})
    except TooManyAttempts:
        return JSONResponse(status_code=429, content={"error": "too_many_attempts"})
    response = JSONResponse(content=AuthenticatedOut().model_dump())
    _set_session_cookie(response, token)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    logout_owner: Annotated[LogoutOwner, Depends(_logout_owner)],
    mp_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    await logout_owner(mp_session)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/api", secure=True, httponly=True, samesite="lax")
    return response


class VerifyEmailIn(BaseModel):
    token: str = ""


class VerifyEmailOut(BaseModel):
    status: Literal["verified", "already_verified"]


def _verify_email(request: Request) -> VerifyEmail:
    verify_email: VerifyEmail = request.app.state.verify_email
    return verify_email


@router.post(
    "/verify-email",
    response_model=VerifyEmailOut,
    responses={400: {"description": "invalid_token · expired_token"}},
)
async def verify_email(
    body: VerifyEmailIn, verify: Annotated[VerifyEmail, Depends(_verify_email)]
) -> VerifyEmailOut | JSONResponse:
    try:
        verified = await verify(body.token)
    except InvalidVerificationToken:
        return JSONResponse(status_code=400, content={"error": "invalid_token"})
    except ExpiredVerificationToken:
        # La SPA dice «el enlace caducó» y ofrece pedir uno nuevo (R028).
        return JSONResponse(status_code=400, content={"error": "expired_token"})
    if verified.session_token is None:
        return VerifyEmailOut(status="already_verified")
    # El primer uso del enlace deja al propietario dentro del panel (R025).
    response = JSONResponse(content=VerifyEmailOut(status="verified").model_dump())
    _set_session_cookie(response, verified.session_token)
    return response


class PasswordResetIn(BaseModel):
    email: str = ""


class PasswordResetOut(BaseModel):
    status: Literal["check_email"] = "check_email"


class PasswordResetConfirmIn(BaseModel):
    token: str = ""
    password: str = ""


def _request_password_reset(request: Request) -> RequestPasswordReset:
    request_reset: RequestPasswordReset = request.app.state.request_password_reset
    return request_reset


def _confirm_password_reset(request: Request) -> ConfirmPasswordReset:
    confirm: ConfirmPasswordReset = request.app.state.confirm_password_reset
    return confirm


@router.post(
    "/password-reset", status_code=status.HTTP_202_ACCEPTED, response_model=PasswordResetOut
)
async def password_reset(
    body: PasswordResetIn,
    request_reset: Annotated[RequestPasswordReset, Depends(_request_password_reset)],
) -> PasswordResetOut:
    # La misma respuesta exista o no la cuenta (R016).
    await request_reset(body.email)
    return PasswordResetOut()


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"description": "invalid_or_expired_token"}, 422: {"description": "errors"}},
)
async def password_reset_confirm(
    body: PasswordResetConfirmIn,
    confirm: Annotated[ConfirmPasswordReset, Depends(_confirm_password_reset)],
) -> Response:
    try:
        await confirm(body.token, body.password)
    except RegistrationRejected as rejected:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"errors": {field: str(code) for field, code in rejected.errors.items()}},
        )
    except InvalidResetToken:
        return JSONResponse(status_code=400, content={"error": "invalid_or_expired_token"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
