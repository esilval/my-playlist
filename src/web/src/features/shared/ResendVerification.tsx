// Reenviar el enlace de verificación (R018, R027). Lo usan la pantalla de verificación
// y el panel. Sin sesión, el cliente lleva a /entrar al recibir el 401 (plan D11).
import { useState } from "react";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";

const RESEND_MESSAGES: Record<number, string> = {
  202: "Te enviamos un enlace nuevo. Revisa tu correo.",
  409: "Tu correo ya está verificado.",
  429: "Ya pediste varios enlaces. Espera una hora y vuelve a intentarlo.",
};

export function ResendVerification({ label = "Reenviar el enlace" }: { label?: string }) {
  const api = useApi();
  const [message, setMessage] = useState<string | null>(null);

  async function resend() {
    try {
      const { response } = await api.POST("/api/owner/email-verification/resend");
      if (response.status !== 401) {
        setMessage(RESEND_MESSAGES[response.status] ?? CONNECTION_ERROR);
      }
    } catch {
      setMessage(CONNECTION_ERROR);
    }
  }

  return (
    <>
      <button type="button" onClick={() => void resend()}>
        {label}
      </button>
      {message && <p role="status">{message}</p>}
    </>
  );
}
