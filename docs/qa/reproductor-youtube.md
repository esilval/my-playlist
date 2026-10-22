# Prueba manual: el reproductor con YouTube real

Feature 002 (sesión de música y reproductor del local), requisitos R005 y R007, tarea
T019. Las pruebas automáticas usan un proveedor falso. Esta comprueba lo que solo se ve
con YouTube real (plan D5, Q8):
- la precarga con dos IFrame;
- los videos que no se pueden insertar;
- la publicidad;
- una pestaña en segundo plano.

Se hace en **Chrome, Edge, Firefox y Safari de escritorio**.

## Preparación

1. Levanta el entorno desde `src/` con el proveedor de YouTube. El servidor de
   desarrollo usa el falso por defecto:

   ```bash
   VITE_PLAYBACK_PROVIDER=youtube docker compose up -d --build
   ```

   Comprueba que responde en `http://localhost:5173`. Al terminar, vuelve al falso con
   `docker compose up -d --build web`.

2. Regístrate en `/registro`, verifica el correo desde Mailpit (`http://localhost:8025`)
   y, en el panel, pulsa «Abrir la sesión de música».

3. Elige los videos. La referencia de una canción es `yt:` seguido del id de 11
   caracteres del video: lo que va tras `v=` en `https://www.youtube.com/watch?v=…`.
   - **Tres que se puedan insertar**, de unos 2 o 3 minutos. Antes de usarlos,
     compruébalo en YouTube: en «Compartir», tiene que aparecer la opción «Insertar».
   - **Uno que no se pueda insertar.** Muchos videoclips oficiales de discográficas lo
     tienen desactivado. Para confirmarlo, ábrelo en
     `https://www.youtube.com/embed/<id>`: debe decir que el video no está disponible
     fuera de YouTube.
   - Anota los ids que uses en la columna «Notas» de los resultados.

4. Para agregar canciones a la cola (la herramienta de desarrollo del plan D9), desde
   `src/`:

   ```bash
   docker compose exec api python -m app.sessions.devtools enqueue \
     --email <tu correo> --title "Canción 1" --ref yt:<id>
   ```

5. En cada navegador, abre dos ventanas con la sesión iniciada:
   - el **reproductor**, en `http://localhost:5173/panel/reproductor`;
   - el **panel**, en `http://localhost:5173/panel`.

   Abre las herramientas de desarrollo del reproductor, pestaña «Red» (Network), y
   filtra por `player/events`: cada informe `started`, `ended` o `failed` tiene su hora.
   Así se miden los huecos.

## Pasos

Hazlos en orden en cada navegador. Antes de empezar con un navegador, cierra y vuelve a
abrir la sesión de música desde el panel, para empezar con la cola vacía.

### 1. Puesta en marcha

1. Agrega «Canción 1» con un video que se pueda insertar.
2. En el reproductor, pulsa «Poner en marcha».
3. **Pasa si:**
   - el video se ve y suena;
   - el reproductor dice «Suena: Canción 1»;
   - el panel muestra «Suena: Canción 1» y «El reproductor está en marcha».

### 2. Tres canciones seguidas, con huecos de menos de 3 s (R005)

1. Con la Canción 1 sonando, agrega «Canción 2» y «Canción 3», con videos que se puedan
   insertar.
2. Deja que suenen las tres sin tocar nada.
3. Para cada cambio de canción, mide el hueco entre el informe `ended` de una y el
   `started` de la siguiente, con la columna de tiempo de la pestaña «Red». Si el
   cambio lleva publicidad, el hueco se mide hasta que empieza la publicidad, no hasta
   que empieza la canción (Q5).
4. **Pasa si:**
   - los dos huecos son de menos de 3 s;
   - las canciones suenan en el orden en que entraron;
   - ninguna se repite;
   - el panel sigue cada cambio.

### 3. Un video que no se puede insertar (R007)

1. Con una canción sonando, agrega «No insertable» con el video que no se puede
   insertar y, después, «Canción 4» con uno que sí.
2. Deja que termine la canción que suena.
3. **Pasa si:**
   - «No insertable» no llega a sonar;
   - en «Red» aparece un `failed` con motivo `not_embeddable`, o `not_found` si
     YouTube lo trata como no disponible;
   - «Canción 4» empieza en menos de 3 s desde ese `failed`;
   - el panel avisa «No se pudo reproducir «No insertable»; se saltó.» en menos de
     1 s;
   - el aviso sigue al recargar el panel.
4. Si en vez de `not_embeddable` el `failed` lleva el motivo `timeout`, apúntalo: el
   reproductor tardó 10 s en darlo por fallido. El resultado sigue siendo un *pasa* en
   cuanto al salto, pero esos 10 s son tiempo sin música, y conviene saberlo.

### 4. Una hora en una pestaña en segundo plano, sin cortes

1. Agrega canciones que sumen al menos una hora, con videos que se puedan insertar.
   Puedes usar videos más largos.
2. Con el reproductor sonando, pasa a otra pestaña del mismo navegador o minimiza la
   ventana. Deja el equipo una hora sin dormir la pantalla.
3. Vuelve al reproductor.
4. **Pasa si:**
   - durante la hora no hubo cortes ni silencios de más de 3 s entre canciones; se ve
     en la secuencia de informes de «Red», sin ningún `failed` con motivo `timeout`;
   - el reproductor sigue en marcha y no dice «La música sigue en otro dispositivo»;
   - el panel, al recargarlo, muestra la canción que suena y «El reproductor está en
     marcha».
5. **Qué observar:** los navegadores frenan los temporizadores de las pestañas en
   segundo plano. Chrome y Edge no lo hacen con las que reproducen sonido. Si el panel
   da el reproductor por inactivo durante la prueba, apúntalo en «Notas», aunque la
   música no se corte. El latido es cada 15 s, y el panel considera inactivo un
   reproductor sin latido en 45 s.

## Resultados

Rellena una fila por navegador. «Resultado» es *pasa* si se cumplen los cuatro pasos.
Si alguno falla, anota cuál y qué pasó.

| Fecha | Navegador | Versión | Sistema | 1. Puesta en marcha | 2. Huecos (ms) | 3. No insertable | 4. Una hora en segundo plano | Resultado | Notas |
|-------|-----------|---------|---------|---------------------|----------------|------------------|------------------------------|-----------|-------|
| _pendiente_ | Chrome | | | | | | | | |
| _pendiente_ | Edge | | | | | | | | |
| _pendiente_ | Firefox | | | | | | | | |
| _pendiente_ | Safari | | macOS | | | | | | |

Hasta que estas filas tengan resultado, T019 sigue pendiente. Las pruebas de componente
y las e2e ya cubren el orden, los huecos y los fallos con el proveedor falso, en
`src/web/src/features/player/` y `src/web/e2e/player.spec.ts`. No sustituyen esta
prueba: el IFrame de YouTube, su publicidad y los navegadores reales son justo lo que
esas pruebas no ven.
