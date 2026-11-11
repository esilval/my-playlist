// Métricas del tiempo real (feature 004, plan D11, ADR-0018): cada 60 s, una línea JSON en
// la salida estándar con el formato EMF de CloudWatch, que la convierte en métricas sin
// agente ni llamadas de red. La única dimensión es `Service`: nunca el establecimiento.
//
//   Connections    conexiones abiertas en ese momento
//   EventsRelayed  eventos reenviados a sus salas en el periodo
//   RelayDelay     ms entre que el monolito publicó cada evento (`published_at`) y su envío
//   RedisErrors    errores de Redis en el periodo

export const FLUSH_INTERVAL_MS = 60_000;
// EMF admite como mucho 100 valores por métrica en una lista; con más, CloudWatch no extrae
// ninguna métrica de la línea. Los retrasos van en tramos de este tamaño, cada uno en su línea.
export const MAX_VALUES_PER_LINE = 100;
// Tope de muestras por periodo: una ráfaga de eventos no hace crecer la lista sin límite. Se
// guardan las primeras: si el retraso empeora al final de un minuto saturado, el p95 de ese
// minuto no lo recoge. Con la carga del piloto (Q2) no se llega al tope.
export const MAX_DELAY_SAMPLES = 10_000;
const SERVICE = "realtime";

export function namespaceFor(env: string | undefined): string {
  return `MyPlaylist/${env ?? "local"}`;
}

export class RealtimeMetrics {
  private connections = 0;
  private eventsRelayed = 0;
  private redisErrors = 0;
  private relayDelays: number[] = [];

  constructor(
    private readonly namespace: string,
    private readonly write: (line: string) => void = (line) => process.stdout.write(`${line}\n`),
    private readonly nowMs: () => number = () => Date.now(),
  ) {}

  onConnect(): void {
    this.connections += 1;
  }

  onDisconnect(): void {
    this.connections = Math.max(0, this.connections - 1);
  }

  /** Un evento reenviado. `publishedAt` es opcional: un monolito anterior no lo manda. */
  onRelay(publishedAt: unknown): void {
    this.eventsRelayed += 1;
    if (
      typeof publishedAt === "number" &&
      Number.isFinite(publishedAt) &&
      this.relayDelays.length < MAX_DELAY_SAMPLES
    ) {
      this.relayDelays.push(Math.max(0, this.nowMs() - publishedAt));
    }
  }

  onRedisError(): void {
    this.redisErrors += 1;
  }

  /** Escribe las líneas del periodo y empieza otro. Las conexiones no se reinician. */
  flush(): void {
    const timestamp = this.nowMs();
    this.write(
      this.line(timestamp, {
        Connections: this.connections,
        EventsRelayed: this.eventsRelayed,
        RedisErrors: this.redisErrors,
      }),
    );
    // EMF admite una lista de valores, de la que CloudWatch calcula el p95, pero de 100 como mucho.
    for (let start = 0; start < this.relayDelays.length; start += MAX_VALUES_PER_LINE) {
      const chunk = this.relayDelays.slice(start, start + MAX_VALUES_PER_LINE);
      this.write(this.line(timestamp, { RelayDelay: chunk }));
    }
    this.eventsRelayed = 0;
    this.redisErrors = 0;
    this.relayDelays = [];
  }

  private line(timestamp: number, values: Record<string, number | number[]>): string {
    const metrics = Object.keys(values).map((name) => ({
      Name: name,
      Unit: name === "RelayDelay" ? "Milliseconds" : "Count",
    }));
    return JSON.stringify({
      event: "metric",
      Service: SERVICE,
      ...values,
      _aws: {
        Timestamp: timestamp,
        CloudWatchMetrics: [{ Namespace: this.namespace, Dimensions: [["Service"]], Metrics: metrics }],
      },
    });
  }

  /** Escribe la línea cada `intervalMs`. El temporizador no impide que el proceso termine. */
  start(intervalMs: number = FLUSH_INTERVAL_MS): () => void {
    const timer = setInterval(() => this.flush(), intervalMs);
    timer.unref();
    return () => clearInterval(timer);
  }
}
