// Versión imprimible del QR (R011, R018): solo la imagen, que ya lleva el nombre.
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";
import { ResendVerification } from "../shared/ResendVerification";
import "./print.css";

type PrintState =
  | { status: "loading" }
  | { status: "ready"; src: string; name: string }
  | { status: "not_verified" }
  | { status: "error" };

export function PrintQr({ print = () => window.print() }: { print?: () => void }) {
  const api = useApi();
  const [state, setState] = useState<PrintState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const [qr, me] = await Promise.all([
          api.GET("/api/owner/establishment/qr.png", { parseAs: "blob" }),
          api.GET("/api/owner/me"),
        ]);
        if (!active) return;
        if (qr.response.status === 403) {
          // El bloqueo vive en el servidor: sin correo verificado no hay QR (R018).
          setState({ status: "not_verified" });
        } else if (qr.response.ok && qr.data && me.data) {
          // Con parseAs: "blob" el cuerpo es un Blob (sin `instanceof`: en pruebas el
          // Blob de fetch no es el global de jsdom).
          objectUrl = URL.createObjectURL(qr.data as Blob);
          setState({ status: "ready", src: objectUrl, name: me.data.establishment.name });
        } else if (qr.response.status !== 401) {
          setState({ status: "error" });
        }
      } catch {
        if (active) setState({ status: "error" });
      }
    })();
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api]);

  if (state.status === "loading") {
    return (
      <main>
        <p role="status">Preparando el QR…</p>
      </main>
    );
  }
  if (state.status === "not_verified") {
    return (
      <main>
        <h1>Verifica tu correo</h1>
        <p role="alert">
          Para imprimir tu QR, primero verifica tu correo con el enlace que te enviamos.
        </p>
        <ResendVerification />
        <Link to="/panel">Volver al panel</Link>
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main>
        <p role="alert">{CONNECTION_ERROR}</p>
      </main>
    );
  }
  return (
    <main className="print-sheet">
      {/* El PNG ya lleva el nombre debajo del QR (plan D6). */}
      <img src={state.src} alt={`Código QR de ${state.name}`} onLoad={print} />
      <p className="no-print">
        <Link to="/panel">Volver al panel</Link>
      </p>
    </main>
  );
}
