// Formatos de error de la API (plan Contratos): 422 `{errors: {campo: código}}` y el
// resto `{error: código}`. No van tipados en el OpenAPI porque la API los construye a
// mano, así que se leen con cuidado.

export type FieldErrors = Record<string, string>;

export function fieldErrors(body: unknown): FieldErrors {
  if (typeof body === "object" && body !== null && "errors" in body) {
    const errors = (body as { errors: unknown }).errors;
    if (typeof errors === "object" && errors !== null) {
      return Object.fromEntries(
        Object.entries(errors).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
      );
    }
  }
  return {};
}

export function errorCode(body: unknown): string | undefined {
  if (typeof body === "object" && body !== null && "error" in body) {
    const code = (body as { error: unknown }).error;
    return typeof code === "string" ? code : undefined;
  }
  return undefined;
}

// Fallo de red o del servidor: nunca se presenta como un error del usuario.
export const CONNECTION_ERROR =
  "No se pudo conectar con MyPlaylist. Revisa tu conexión y vuelve a intentarlo.";

// Mensajes por campo, en el idioma del propietario.
const FIELD_MESSAGES: Record<string, Record<string, string>> = {
  email: {
    required: "Escribe tu correo.",
    invalid_email: "Ese correo no tiene un formato válido.",
    invalid: "Ese correo no tiene un formato válido.",
  },
  password: {
    required: "Escribe una contraseña.",
    password_too_short: "La contraseña debe tener al menos 8 caracteres.",
    invalid: "La contraseña no es válida.",
  },
  establishment_name: {
    required: "Escribe el nombre de tu establecimiento.",
    invalid: "El nombre no es válido.",
  },
  data_authorization: {
    authorization_required: "Para crear la cuenta tienes que aceptar la política de tratamiento de datos.",
    invalid: "Para crear la cuenta tienes que aceptar la política de tratamiento de datos.",
  },
  policy_version: {
    outdated: "La política de tratamiento de datos se actualizó. Revísala y vuelve a aceptarla.",
  },
};

export function fieldMessage(field: string, code: string | undefined): string | undefined {
  if (code === undefined) return undefined;
  return FIELD_MESSAGES[field]?.[code] ?? "Revisa este campo.";
}
