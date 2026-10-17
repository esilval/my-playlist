// Abrir el enlace de verificación (R017, R025, R026, R028).
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useApi } from "../../api/context";
import { errorCode } from "../../api/errors";
import { ResendVerification } from "../shared/ResendVerification";

type Outcome = "checking" | "already_verified" | "invalid_token" | "expired_token";

export function VerifyEmail() {
  const api = useApi();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [outcome, setOutcome] = useState<Outcome>("checking");
  // El enlace es de un solo uso: en desarrollo StrictMode monta dos veces el efecto, y
  // la segunda llamada respondería «ya verificado» tapando la primera.
  const requested = useRef(false);

  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    void (async () => {
      const { data, error } = await api.POST("/api/auth/verify-email", {
        body: { token: params.get("token") ?? "" },
      });
      if (data?.status === "verified") {
        // Primer uso: queda dentro del panel (R025).
        void navigate("/panel", { replace: true });
      } else if (data?.status === "already_verified") {
        setOutcome("already_verified");
      } else {
        setOutcome(errorCode(error) === "expired_token" ? "expired_token" : "invalid_token");
      }
    })();
  }, [api, navigate, params]);

  if (outcome === "checking") {
    return (
      <main>
        <p role="status">Verificando tu correo…</p>
      </main>
    );
  }
  if (outcome === "already_verified") {
    return (
      <main>
        <h1>Tu correo ya está verificado</h1>
        <Link to="/entrar">Entrar</Link>
      </main>
    );
  }
  return (
    <main>
      <h1>{outcome === "expired_token" ? "El enlace caducó" : "El enlace no es válido"}</h1>
      <p role="alert">
        {outcome === "expired_token"
          ? "Los enlaces de verificación caducan a los 7 días."
          : "El enlace no es válido o se reemplazó por uno más reciente."}
      </p>
      <RequestNewLink />
    </main>
  );
}

function RequestNewLink() {
  return (
    <>
      <ResendVerification label="Pedir un enlace nuevo" />
      <p>
        Si no has iniciado sesión, te llevaremos a <Link to="/entrar">entrar</Link> primero.
      </p>
    </>
  );
}
