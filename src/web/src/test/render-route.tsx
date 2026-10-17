// Monta la SPA real (sus rutas) en una URL, con la API falsa.
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import type { ApiClient } from "../api/client";
import { ApiProvider } from "../api/context";
import { routes } from "../router";

export function renderRoute(url: string, client: ApiClient) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(
    <ApiProvider client={client}>
      <RouterProvider router={router} />
    </ApiProvider>,
  );
  return router;
}
