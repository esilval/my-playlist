// El cliente de la API llega a las pantallas por contexto: en pruebas se sustituye por
// uno con un `fetch` falso, sin tocar los componentes.
import { createContext, useContext, type ReactNode } from "react";

import { api as defaultApi, type ApiClient } from "./client";

const ApiContext = createContext<ApiClient>(defaultApi);

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
  return useContext(ApiContext);
}
