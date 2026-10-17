# Atributos de calidad

| Campo  | Valor |
| ------ | ----- |
| Estado | Approved · 830f3b617c9e |

> Cómo debe comportarse el sistema, como escenarios medibles: estímulo,
> respuesta y medida con cifra («500 peticiones/s con p95 < 300 ms», no
> «escalable»). Cada atributo cita su motivo: un objetivo del brief (`G2`) o la
> sección de origen de una de sus restricciones (`D1§5`).
>
> Sustituye todo texto en cursiva. Solo el usuario cambia el Estado, con
> `/architecture:approve`.

## Atributos

### Q1 — Búsqueda rápida de canciones

- **Escenario:** un cliente o el propietario busca por nombre, artista o álbum en el proveedor de música (YouTube en el piloto); los resultados aparecen en su pantalla en menos de 2 s, también con la carga de Q2.
- **Motivo:** G1, D1§7

### Q2 — Carga simultánea del piloto

- **Escenario:** 50 establecimientos con la sesión abierta y 100 clientes por establecimiento conectados a la vez (5000 clientes); el sistema atiende búsquedas, pedidos y actualizaciones de cola cumpliendo Q1 y Q4 sin rechazar peticiones.
- **Motivo:** D1§7

### Q3 — Disponibilidad del servicio

- **Escenario:** a lo largo de un mes, el servicio (pedidos, panel del propietario, reproductor y pantalla de cola) está disponible al menos el 99,5 % del tiempo, es decir, como máximo unas 3,6 h de caída al mes.
- **Motivo:** G3, D1§7

### Q4 — Cola en tiempo real

- **Escenario:** se produce un cambio en la cola de una sesión abierta (pedido, reorden, eliminación o cambio de canción); el cambio se ve en el móvil de los clientes conectados, en el panel del propietario y en la pantalla de cola en menos de 1 s.
- **Motivo:** G1, G2

### Q5 — Música sin silencios

- **Escenario:** con la sesión abierta termina una canción, una canción falla y se salta, o la cola se vacía y entra el relleno; la siguiente canción empieza a sonar en el local en menos de 3 s, sin que el propietario intervenga.
- **Motivo:** G3

### Q6 — Aislamiento entre establecimientos

- **Escenario:** un cliente o propietario de un establecimiento intenta leer o modificar la cola, los pedidos o las búsquedas de otro establecimiento (por URL, QR o petición directa); el 100 % de los intentos se rechaza y 0 datos de otro establecimiento quedan expuestos.
- **Motivo:** G2, D1§2

### Q7 — Datos personales mínimos

- **Escenario:** un cliente usa la aplicación desde el QR sin registrarse; se guardan 0 datos personales del cliente (solo un identificador anónimo del dispositivo), y del propietario solo los datos de cuenta y facturación, conforme a la Ley 1581 de 2012.
- **Motivo:** D1§7

### Q8 — Sin instalación

- **Escenario:** un cliente escanea el QR o el propietario abre el panel, el reproductor o la pantalla de cola; todo funciona en un navegador web estándar con 0 aplicaciones que instalar en ningún dispositivo.
- **Motivo:** D1§5
