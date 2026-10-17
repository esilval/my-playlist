// Datos del establecimiento (R014, R019): el QR no cambia al editarlos.
import { useState, type FormEvent } from "react";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR, fieldErrors, type FieldErrors } from "../../api/errors";
import { Field } from "../../ui/Field";
import type { Establishment } from "./types";

interface Props {
  establishment: Establishment;
  onSaved: (establishment: Establishment) => void;
}

export function EstablishmentForm({ establishment, onSaved }: Props) {
  const api = useApi();
  const [form, setForm] = useState({
    name: establishment.name,
    address: establishment.address ?? "",
    phone: establishment.phone ?? "",
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [status, setStatus] = useState<string | null>(null);

  function update(field: keyof typeof form) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus(null);
    try {
      const { data, error, response } = await api.PATCH("/api/owner/establishment", {
        body: form,
      });
      if (data) {
        setErrors({});
        setStatus("Datos guardados.");
        onSaved(data);
      } else if (response.status === 422) {
        setErrors(fieldErrors(error));
      } else if (response.status !== 401) {
        setStatus(CONNECTION_ERROR);
      }
    } catch {
      setStatus(CONNECTION_ERROR);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-labelledby="establishment-heading">
      <h2 id="establishment-heading">Datos del establecimiento</h2>
      <Field
        label="Nombre"
        name="name"
        value={form.name}
        onChange={update("name")}
        error={errors.name ? "Escribe el nombre de tu establecimiento." : undefined}
      />
      <Field label="Dirección (opcional)" name="address" value={form.address} onChange={update("address")} />
      <Field label="Teléfono (opcional)" type="tel" name="phone" value={form.phone} onChange={update("phone")} />
      {status && <p role="status">{status}</p>}
      <button type="submit">Guardar</button>
    </form>
  );
}
