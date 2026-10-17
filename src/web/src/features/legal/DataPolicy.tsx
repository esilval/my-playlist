// Política de tratamiento de datos (R022, plan D12): pública, sin sesión, con su versión.
import { useEffect, useState } from "react";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";
import { Markdown } from "./markdown";

type PolicyState =
  | { status: "loading" }
  | { status: "ready"; version: string; content: string }
  | { status: "error" };

export function DataPolicy() {
  const api = useApi();
  const [state, setState] = useState<PolicyState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api.GET("/api/public/data-policy").then(
      ({ data }) => {
        if (active) setState(data ? { status: "ready", ...data } : { status: "error" });
      },
      () => {
        if (active) setState({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [api]);

  if (state.status === "loading") {
    return (
      <main>
        <p role="status">Cargando la política…</p>
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
      <h1>Política de tratamiento de datos</h1>
      <p>
        Versión <strong>{state.version}</strong>
      </p>
      <article>
        <Markdown source={state.content} />
      </article>
    </main>
  );
}
