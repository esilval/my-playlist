// Los datos del panel. Un 401 lo resuelve el cliente llevando a /entrar (R015, R020).
import { useEffect, useState } from "react";

import { useApi } from "../../api/context";
import type { OwnerMe } from "./types";

export type MeState =
  | { status: "loading" }
  | { status: "ready"; me: OwnerMe }
  | { status: "unauthenticated" }
  | { status: "error" };

export function useOwnerMe() {
  const api = useApi();
  const [state, setState] = useState<MeState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api.GET("/api/owner/me").then(
      ({ data, response }) => {
        if (!active) return;
        if (data) setState({ status: "ready", me: data });
        // El cliente ya lleva a /entrar; mientras tanto no se pinta nada.
        else if (response.status === 401) setState({ status: "unauthenticated" });
        else setState({ status: "error" });
      },
      () => {
        if (active) setState({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [api]);

  return [state, setState] as const;
}
