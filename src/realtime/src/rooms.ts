// Salas por establecimiento (ADR-0005, S8): cada socket entra solo en la sala
// `est:{id}` de su ticket. No hay ningún evento con el que el navegador pida unirse a
// otra sala: las salas las decide siempre el servidor.
import type { Server, Socket } from "socket.io";

import { InvalidTicket, verifyTicket, type TicketRole } from "./ticket.js";

export interface SocketData {
  establishmentId: string;
  role: TicketRole;
}

export function roomFor(establishmentId: string): string {
  return `est:${establishmentId}`;
}

/** Rechaza la conexión sin un ticket válido (ADR-0014). */
export function requireTicket(secret: string, nowSeconds: () => number) {
  return (socket: Socket, next: (error?: Error) => void): void => {
    const ticket: unknown = socket.handshake.auth?.ticket;
    if (typeof ticket !== "string") {
      next(new Error("unauthorized"));
      return;
    }
    try {
      const claims = verifyTicket(secret, ticket, nowSeconds());
      const data: SocketData = { establishmentId: claims.establishmentId, role: claims.role };
      socket.data = data;
      next();
    } catch (error) {
      // El motivo no se le dice al navegador: solo que no está autorizado. Un error que
      // no sea un ticket inválido es un fallo del servidor y queda en su log.
      if (!(error instanceof InvalidTicket)) console.error("fallo al validar un ticket", error);
      next(new Error("unauthorized"));
    }
  };
}

export function useEstablishmentRooms(io: Server, secret: string, nowSeconds: () => number): void {
  io.use(requireTicket(secret, nowSeconds));
  io.on("connection", (socket) => {
    const { establishmentId } = socket.data as SocketData;
    void socket.join(roomFor(establishmentId));
  });
}
