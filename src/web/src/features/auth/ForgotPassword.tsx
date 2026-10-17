// Pedir la recuperación de la contraseña (R016): el mismo mensaje exista o no la cuenta.
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";
import { Field } from "../../ui/Field";

export const RESET_REQUESTED =
  "Si ese correo tiene una cuenta, te enviamos un enlace para fijar una contraseña nueva. " +
  "El enlace sirve una sola vez y caduca en 60 minutos.";

export function ForgotPassword() {
  const api = useApi();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const { response } = await api.POST("/api/auth/password-reset", { body: { email } });
      if (response.status >= 500) {
        setFailure(CONNECTION_ERROR);
        return;
      }
    } catch {
      setFailure(CONNECTION_ERROR);
      return;
    }
    // Cualquier respuesta de la API (también un límite alcanzado) da el mismo mensaje.
    setSent(true);
  }

  return (
    <main>
      <h1>Recuperar contraseña</h1>
      {sent ? (
        <p role="status">{RESET_REQUESTED}</p>
      ) : (
        <form onSubmit={submit} noValidate>
          <Field
            label="Correo"
            type="email"
            name="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          {failure && <p role="alert">{failure}</p>}
          <button type="submit">Enviar enlace</button>
        </form>
      )}
      <p>
        <Link to="/entrar">Volver a entrar</Link>
      </p>
    </main>
  );
}
