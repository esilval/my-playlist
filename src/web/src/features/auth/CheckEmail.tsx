// Tras registrarse: la misma pantalla exista o no el correo (R023, R024).
import { Link } from "react-router";

export function CheckEmail() {
  return (
    <main>
      <h1>Revisa tu correo</h1>
      <p>
        Te enviamos un correo para continuar. Abre el enlace que contiene para verificar tu
        correo y entrar al panel de tu establecimiento.
      </p>
      <p>
        Si no lo encuentras, revisa la carpeta de correo no deseado. También puedes{" "}
        <Link to="/entrar">entrar con tu contraseña</Link>.
      </p>
    </main>
  );
}
