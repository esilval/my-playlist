import type { RouteObject } from "react-router";

// Una ruta por pantalla de la SPA (plan D9). Cada una se carga bajo demanda, para
// que el móvil que llega por el QR no descargue el panel ni el registro (ADR-0003).
export const routes: RouteObject[] = [
  { path: "/registro", lazy: () => import("./routes/register") },
  { path: "/registro/revisa-tu-correo", lazy: () => import("./routes/check-email") },
  { path: "/entrar", lazy: () => import("./routes/login") },
  { path: "/recuperar", lazy: () => import("./routes/forgot-password") },
  { path: "/restablecer", lazy: () => import("./routes/reset-password") },
  { path: "/verificar", lazy: () => import("./routes/verify-email") },
  { path: "/politica-de-datos", lazy: () => import("./routes/data-policy") },
  { path: "/panel", lazy: () => import("./routes/panel") },
  { path: "/panel/qr/imprimir", lazy: () => import("./routes/print-qr") },
  { path: "/l/:code", lazy: () => import("./routes/public-establishment") },
];
