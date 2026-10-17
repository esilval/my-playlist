// El QR del local: descargar e imprimir solo con el correo verificado (R010, R011, R018).
import { Link } from "react-router";

import { ResendVerification } from "../shared/ResendVerification";

export const QR_URL = "/api/owner/establishment/qr.png";

interface Props {
  emailVerified: boolean;
  publicUrl: string;
  name: string;
}

export function QrCard({ emailVerified, publicUrl, name }: Props) {
  // La vista previa cambia de URL con el nombre: al guardar uno nuevo, el navegador
  // vuelve a pedir el PNG, que lleva el nombre impreso (R014).
  const preview = `${QR_URL}?v=${encodeURIComponent(name)}`;
  return (
    <section aria-labelledby="qr-heading">
      <h2 id="qr-heading">Tu código QR</h2>
      {emailVerified ? (
        <>
          <img src={preview} alt="Código QR del establecimiento" width={240} height={272} />
          <p>
            Lleva a <a href={publicUrl}>{publicUrl}</a>
          </p>
          <p>
            <a href={`${QR_URL}?download=1`} download>
              Descargar el QR
            </a>{" "}
            · <Link to="/panel/qr/imprimir">Imprimir el QR</Link>
          </p>
        </>
      ) : (
        <>
          <p role="alert">
            Para descargar o imprimir tu QR, primero verifica tu correo con el enlace que te
            enviamos.
          </p>
          <ResendVerification />
        </>
      )}
    </section>
  );
}
