// La página que abre el QR (R012, R013): sin registro, sin instalar nada y sin datos
// de más. Es la entrada de C5; el buscador de canciones llega con B03.
import { useEffect, useState } from "react";
import { useParams } from "react-router";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";

type PageState =
  | { status: "loading" }
  | { status: "found"; name: string }
  | { status: "not_found" }
  | { status: "error" };

export function PublicEstablishment() {
  const { code = "" } = useParams();
  // Una página nueva por código: nunca se ve el nombre de otro local mientras carga (R013).
  return <EstablishmentPage key={code} code={code} />;
}

function EstablishmentPage({ code }: { code: string }) {
  const api = useApi();
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api.GET("/api/public/establishments/{code}", { params: { path: { code } } }).then(
      ({ data, response }) => {
        if (!active) return;
        if (data) setState({ status: "found", name: data.name });
        else if (response.status === 404) setState({ status: "not_found" });
        else setState({ status: "error" });
      },
      () => {
        if (active) setState({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [api, code]);

  if (state.status === "loading") {
    return (
      <main>
        <p role="status">Cargando…</p>
      </main>
    );
  }
  if (state.status === "not_found") {
    return (
      <main>
        <h1>Establecimiento no encontrado</h1>
        <p>Revisa que el enlace o el código QR estén completos.</p>
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
    <main>
      <h1>{state.name}</h1>
      <p>Te damos la bienvenida a {state.name}.</p>
    </main>
  );
}
