// Interfaz del proveedor de reproducción (plan D5, ADR-0010).
//
// El reproductor del local (C4) solo habla con esta interfaz; el adaptador de cada
// proveedor es el único que traduce `trackRef` (la referencia opaca que guarda C2) a algo
// que el proveedor entiende. Así se puede cambiar YouTube por un proveedor B2B sin tocar
// el reproductor ni la cola.

export interface PlaybackEvents {
  /**
   * La canción empezó a sonar de verdad. Puede llegar más de una vez por canción (tras
   * cargar más, una pausa o publicidad): quien lo escucha tiene que tolerarlo.
   */
  onPlaying(trackRef: string): void;
  /** La canción terminó. */
  onEnded(trackRef: string): void;
  /** La canción no se puede reproducir (retirada, privada, no se puede insertar…). */
  onError(trackRef: string, reason: string): void;
}

export interface PlaybackProvider {
  /** Precarga la canción, para que empiece sin esperar (Q5). */
  load(trackRef: string): void;
  /** Reproduce ya la canción; si estaba precargada, empieza al instante. */
  play(trackRef: string): void;
  /** Detiene la reproducción (cierre de la sesión u otro reproductor activo). */
  stop(): void;
  /** Libera el proveedor al desmontar el reproductor. */
  destroy(): void;
}
