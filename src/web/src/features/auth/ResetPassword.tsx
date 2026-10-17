// Fijar la contraseña nueva con el enlace de recuperación (R016, R021).
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { useApi } from "../../api/context";
import { fieldErrors, fieldMessage } from "../../api/errors";
import { Field } from "../../ui/Field";

export function ResetPassword() {
  const api = useApi();
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [state, setState] = useState<"form" | "done" | "invalid">("form");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const { response, error: body } = await api.POST("/api/auth/password-reset/confirm", {
      body: { token: params.get("token") ?? "", password },
    });
    setPassword("");
    if (response.status === 204) {
      setState("done");
    } else if (response.status === 422) {
      setError(fieldMessage("password", fieldErrors(body).password));
    } else {
      setState("invalid");
    }
  }

  if (state === "done") {
    return (
      <main>
        <h1>Contraseña cambiada</h1>
        <p role="status">
          Ya puedes entrar con tu contraseña nueva. Por seguridad, cerramos las sesiones que
          tenías abiertas.
        </p>
        <Link to="/entrar">Entrar</Link>
      </main>
    );
  }
  if (state === "invalid") {
    return (
      <main>
        <h1>Enlace no válido</h1>
        <p role="alert">El enlace no es válido, ya se usó o caducó.</p>
        <Link to="/recuperar">Pedir un enlace nuevo</Link>
      </main>
    );
  }
  return (
    <main>
      <h1>Nueva contraseña</h1>
      <form onSubmit={submit} noValidate>
        <Field
          label="Contraseña nueva"
          type="password"
          name="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={error}
        />
        <button type="submit">Guardar contraseña</button>
      </form>
    </main>
  );
}
