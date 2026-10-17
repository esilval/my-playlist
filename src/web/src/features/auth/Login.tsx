// Inicio de sesión del propietario (R005, R006, R007).
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";
import { Field } from "../../ui/Field";

// Mismo mensaje exista o no el correo (R006).
export const INVALID_CREDENTIALS = "Correo o contraseña incorrectos.";
export const TOO_MANY_ATTEMPTS =
  "Demasiados intentos fallidos. Espera 15 minutos y vuelve a intentarlo.";

export function Login() {
  const api = useApi();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    let response: Response;
    try {
      ({ response } = await api.POST("/api/auth/login", { body: { email, password } }));
    } catch {
      setMessage(CONNECTION_ERROR);
      return;
    } finally {
      setSubmitting(false);
    }
    if (response.ok) {
      void navigate("/panel");
      return;
    }
    setPassword("");
    if (response.status === 429) setMessage(TOO_MANY_ATTEMPTS);
    else if (response.status === 401) setMessage(INVALID_CREDENTIALS);
    else setMessage(CONNECTION_ERROR);
  }

  return (
    <main>
      <h1>Entrar</h1>
      <form onSubmit={submit} noValidate>
        <Field
          label="Correo"
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Field
          label="Contraseña"
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {message && <p role="alert">{message}</p>}
        <button type="submit" disabled={submitting}>
          Entrar
        </button>
      </form>
      <p>
        <Link to="/recuperar">¿Olvidaste tu contraseña?</Link>
      </p>
      <p>
        ¿No tienes cuenta? <Link to="/registro">Crea una</Link>
      </p>
    </main>
  );
}
