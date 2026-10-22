// Informes del reproductor que aún no llegaron a la API (plan D4, R012).
//
// Cada informe se guarda antes de enviarlo y se borra cuando la API lo confirma: así,
// tras un corte o al recargar la pestaña, se reenvían en orden. Van en `sessionStorage`,
// no en `localStorage`, para que otra pestaña con otro reproductor no los entregue con
// una época que no es la suya (D11). Si el almacenamiento no está disponible (modo
// privado, cuota), siguen en memoria mientras la página esté abierta.
import type { components } from "../../api/schema";

export type PlayerReport = components["schemas"]["PlayerEventIn"];

export const STORAGE_KEY = "myplaylist:player:pending-reports";

export interface PendingReports {
  /** Los informes por entregar, del más antiguo al más reciente. */
  all(): readonly PlayerReport[];
  push(report: PlayerReport): void;
  /** Quita el más antiguo, cuando la API ya lo aplicó o lo descartó. */
  shift(): void;
  clear(): void;
}

function tabStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isReport(value: unknown): value is PlayerReport {
  if (typeof value !== "object" || value === null) return false;
  const { epoch, item_id, type } = value as Record<string, unknown>;
  return (
    typeof epoch === "number" &&
    typeof item_id === "string" &&
    (type === "started" || type === "ended" || type === "failed")
  );
}

function read(storage: Storage | null): PlayerReport[] {
  try {
    const parsed: unknown = JSON.parse(storage?.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isReport) : [];
  } catch {
    return [];
  }
}

export function createPendingReports(storage: Storage | null = tabStorage()): PendingReports {
  let reports = read(storage);

  function persist(): void {
    try {
      if (reports.length === 0) storage?.removeItem(STORAGE_KEY);
      else storage?.setItem(STORAGE_KEY, JSON.stringify(reports));
    } catch {
      // Sin almacenamiento: quedan en memoria.
    }
  }

  return {
    all: () => reports,
    push(report) {
      reports = [...reports, report];
      persist();
    },
    shift() {
      reports = reports.slice(1);
      persist();
    },
    clear() {
      reports = [];
      persist();
    },
  };
}
