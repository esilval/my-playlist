// Registro del propietario (R003, R004, R022, R023, plan D11, D12).
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR, fieldErrors, fieldMessage, type FieldErrors } from "../../api/errors";
import { Field } from "../../ui/Field";

const EMPTY = { email: "", password: "", establishment_name: "", address: "", phone: "" };

export function Register() {
  const api = useApi();
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [authorized, setAuthorized] = useState(false);
  const [policyVersion, setPolicyVersion] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function loadPolicyVersion() {
    const { data } = await api.GET("/api/public/data-policy");
    setPolicyVersion(data?.version ?? null);
  }

  // La versión vigente de la política, que es la que se autoriza (R022, D12).
  useEffect(() => {
    let active = true;
    void api.GET("/api/public/data-policy").then(({ data }) => {
      if (active) setPolicyVersion(data?.version ?? null);
    });
    return () => {
      active = false;
    };
  }, [api]);

  function update(field: keyof typeof EMPTY) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setFailure(null);
    let result;
    try {
      result = await api.POST("/api/auth/register", {
        body: {
          ...form,
          address: form.address || null,
          phone: form.phone || null,
          data_authorization: authorized,
          policy_version: policyVersion ?? "",
        },
      });
    } catch {
      setFailure(CONNECTION_ERROR);
      return;
    } finally {
      setSubmitting(false);
    }
    const { response, error } = result;
    if (response.status >= 500) {
      setFailure(CONNECTION_ERROR);
      return;
    }
    if (response.status === 202) {
      // Sin sesión: se entra al verificar el correo (R023, R025).
      void navigate("/registro/revisa-tu-correo");
      return;
    }
    const found = fieldErrors(error);
    setErrors(found);
    // Se conserva lo escrito salvo la contraseña (R003).
    setForm((current) => ({ ...current, password: "" }));
    if (found.policy_version) {
      setAuthorized(false);
      await loadPolicyVersion();
    }
  }

  return (
    <main>
      <h1>Crea tu cuenta</h1>
      <form onSubmit={submit} noValidate>
        <Field
          label="Correo"
          type="email"
          name="email"
          autoComplete="email"
          value={form.email}
          onChange={update("email")}
          error={fieldMessage("email", errors.email)}
        />
        <Field
          label="Contraseña"
          type="password"
          name="password"
          autoComplete="new-password"
          value={form.password}
          onChange={update("password")}
          error={fieldMessage("password", errors.password)}
        />
        <Field
          label="Nombre del establecimiento"
          name="establishment_name"
          autoComplete="organization"
          value={form.establishment_name}
          onChange={update("establishment_name")}
          error={fieldMessage("establishment_name", errors.establishment_name)}
        />
        <Field
          label="Dirección (opcional)"
          name="address"
          autoComplete="street-address"
          value={form.address}
          onChange={update("address")}
        />
        <Field
          label="Teléfono (opcional)"
          type="tel"
          name="phone"
          autoComplete="tel"
          value={form.phone}
          onChange={update("phone")}
        />
        <div className="checkbox">
          <input
            id="data-authorization"
            type="checkbox"
            checked={authorized}
            onChange={(event) => setAuthorized(event.target.checked)}
            aria-invalid={errors.data_authorization ? true : undefined}
            aria-describedby={errors.data_authorization ? "data-authorization-error" : undefined}
          />
          <label htmlFor="data-authorization">
            Autorizo el tratamiento de mis datos según la{" "}
            <Link to="/politica-de-datos" target="_blank" rel="noopener">
              política de tratamiento de datos
            </Link>
            .
          </label>
        </div>
        {errors.data_authorization && (
          <p id="data-authorization-error" className="field-error">
            {fieldMessage("data_authorization", errors.data_authorization)}
          </p>
        )}
        {errors.policy_version && (
          <p role="alert">{fieldMessage("policy_version", errors.policy_version)}</p>
        )}
        {failure && <p role="alert">{failure}</p>}
        {/* Sin la versión vigente de la política no hay nada que autorizar (D12). */}
        <button type="submit" disabled={submitting || policyVersion === null}>
          Crear cuenta
        </button>
      </form>
      <p>
        ¿Ya tienes cuenta? <Link to="/entrar">Entra</Link>
      </p>
    </main>
  );
}
