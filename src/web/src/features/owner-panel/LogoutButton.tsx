// Cerrar sesión (R008): solo se sale cuando el servidor confirma que revocó la sesión.
import { useState } from "react";
import { useNavigate } from "react-router";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";

export function LogoutButton() {
  const api = useApi();
  const navigate = useNavigate();
  const [failure, setFailure] = useState<string | null>(null);

  async function logout() {
    setFailure(null);
    try {
      const { response } = await api.POST("/api/auth/logout");
      // 401: ya no había sesión, así que también se está fuera.
      if (response.status === 204 || response.status === 401) {
        void navigate("/entrar", { replace: true });
        return;
      }
    } catch {
      // Sin respuesta no se sabe si la sesión se revocó: no se finge que sí.
    }
    setFailure(`No se pudo cerrar la sesión. ${CONNECTION_ERROR}`);
  }

  return (
    <>
      <button type="button" onClick={() => void logout()}>
        Cerrar sesión
      </button>
      {failure && <span role="alert">{failure}</span>}
    </>
  );
}
