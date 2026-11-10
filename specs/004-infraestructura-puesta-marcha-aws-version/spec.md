# Spec: Infraestructura y puesta en marcha en AWS

| Campo  | Valor        |
| ------ | ------------ |
| ID     | `004-infraestructura-puesta-marcha-aws-version`     |
| Fecha  | 2026-11-04     |
| Estado | Approved · d21dd056b1f4        |
| Tipo   | funcionalidad |
| Issue  | —            |

> Este documento describe **qué** y **por qué**, nunca **cómo**.
> Toda decisión de implementación (librerías, esquemas, servicios) va en `plan.md`.
>
> Sustituye todo texto en cursiva; si una sección no aplica, escribe
> «No aplica.». Solo el usuario cambia el Estado, con `/sdd:approve`.

## Problema

La versión 0.1.0 está publicada, pero solo corre en el equipo del desarrollador. Ningún establecimiento del piloto puede usarla:
- no hay una dirección pública a la que lleve el QR;
- los correos de verificación no salen hacia buzones reales;
- nadie se entera si el servicio se cae o va lento.

Además, quedan sin comprobar varias cosas que solo se pueden medir en un entorno real:
- la carga completa del piloto (Q2);
- la disponibilidad del mes (Q3);
- las pruebas manuales que exigen HTTPS (escanear el QR con un móvil, Safari y Edge), pendientes desde las features 001 y 002.

## Contexto

- **Versión que se pone en marcha:** la 0.2.0, la primera que incluye esta feature. Lleva las features 001, 002 y 003 de `releases/v0.1.0.md` y lo que esta añade a la aplicación (la instrumentación de las señales y el modo de preproducción), sin cambios de comportamiento para los usuarios. El código de la etiqueta `v0.1.0` no basta: sin esa instrumentación no se cumplen R011, R016 ni R022.
- **Preparación operativa aprobada:** `operations/v0.1.0.md`, de la que parte la de la 0.2.0. Fija:
  - los pasos de la puesta en marcha;
  - las señales SG1 a SG8, con su umbral;
  - la vuelta atrás y su disparador.

  Esta feature hace posible lo que esa preparación da por existente.
- **Arquitectura aprobada:**
  - ADR-0006: el entorno de destino, en la nube y con contenedores;
  - ADR-0011: el correo transaccional;
  - ADR-0015: varios procesos de la API;
  - los atributos de calidad Q1 a Q8.
- **Lo que ya existe:**
  - La aplicación se niega a arrancar en producción con valores de desarrollo: secretos, correo, catálogo o política de tratamiento.
  - Los servicios exponen una comprobación de salud.
  - La prueba de carga `src/perf/client.js` existe, pero en local solo corre a escala (20 establecimientos, D10 de 003).
- **Lo que falta en la aplicación para medir las señales:**
  - la duración de cada petición en los registros;
  - las métricas del servicio de tiempo real;
  - el hueco entre una canción y la siguiente.
- **Constitución:** desplegar a producción exige la aprobación explícita de una persona, y ningún secreto se versiona.
- **Decidido al clarificar (2026-11-09):**
  - El dominio del servicio es `200oklabs.com`, adquirido para este proyecto. Sus registros DNS y sus certificados se pueden gestionar desde AWS si hace falta (confirmado por el usuario).
  - Las alertas llegan por correo al responsable de operación (hoy, el desarrollador), a cualquier hora, sin compromiso de respuesta inmediata.
  - La prueba de carga de Q2 corre en una preproducción temporal, igual a producción pero con el catálogo de música falso, que se destruye al terminar. Así no se gasta la cuota diaria de YouTube (una búsqueda gasta 100 de sus 10 000 unidades) ni se escriben datos de prueba en producción.
  - No hay un tope de coste: el plan estima el coste mensual antes de aprobarse.

## Alcance

### Dentro

- Un entorno de producción en el que corre la versión 0.2.0, accesible desde un dominio público con HTTPS.
- Un despliegue repetible desde una versión etiquetada, que una persona aprueba, con las migraciones aplicadas una sola vez.
- Secretos y configuración de producción fuera del repositorio.
- Correo transaccional desde el dominio del servicio, que llega a buzones reales.
- Tolerancia a la caída de una instancia o de una zona, y copias de la base de datos.
- La medición continua de las señales SG1 a SG6 con alertas por correo, incluida la instrumentación que hoy falta en la aplicación. SG7 y SG8 se comprueban con una revisión y con las pruebas en dispositivos reales (R016, R018, R019).
- Retirar el servicio con una página de mantenimiento sin perder datos.
- Una preproducción temporal para la prueba de carga.
- Comprobar en el entorno real lo que quedó pendiente:
  - la carga completa de Q2, en la preproducción;
  - el escaneo del QR con un móvil;
  - Safari y Edge.

### Fuera (non-goals)

- **Funcionalidades nuevas del producto** (B04 a B10). La aplicación solo cambia para medir las señales.
- **Más de una región,** o escalar más allá de los 50 establecimientos del piloto (Q2).
- **Entornos efímeros** por PR.
- **Guardias 24/7** o un acuerdo de nivel de servicio con terceros. Las alertas van al responsable de operación.
- **Redactar la política de tratamiento definitiva:** la aporta el negocio (ver Supuestos).
- **Una preproducción permanente:** la temporal solo existe mientras corre la prueba de carga.
- **Volver a una versión anterior con datos migrados:** con la primera versión no la hay. La vuelta atrás es retirar el servicio (`operations/v0.1.0.md`).
- **Facturación y cobro de la suscripción** (B09).

## Requisitos

| ID   | Prioridad | Requisito |
| ---- | --------- | --------- |
| R001 | MUST      | CUANDO una persona autorizada aprueba el despliegue de una versión etiquetada, el sistema DEBERÁ ponerla en marcha en producción a partir de esa etiqueta, siguiendo siempre el mismo procedimiento, sin pasos que dependan del equipo de quien despliega. |
| R002 | MUST      | SI se intenta desplegar en producción sin la aprobación explícita de una persona autorizada, o desde algo que no es una versión etiquetada, ENTONCES el sistema DEBERÁ rechazar el despliegue sin cambiar lo que está en marcha. |
| R003 | MUST      | El sistema DEBERÁ servir todas sus páginas y su API bajo el dominio `200oklabs.com` solo por HTTPS, con un certificado válido, y redirigir cualquier acceso por HTTP a HTTPS. |
| R004 | MUST      | CUANDO se despliega una versión con migraciones de la base de datos, el sistema DEBERÁ aplicarlas una sola vez y antes de que la versión nueva atienda peticiones. |
| R005 | MUST      | SI una migración falla, o la versión nueva no supera su comprobación de salud, ENTONCES el sistema DEBERÁ detener el despliegue y seguir atendiendo con lo que estaba en marcha, sin perder datos. |
| R006 | MUST      | El sistema DEBERÁ entregar los secretos de producción a los servicios solo en el momento de ejecutarlos, sin que aparezcan en el repositorio, en las imágenes de los servicios ni en los registros. |
| R007 | MUST      | SI la configuración de producción falta o conserva un valor de desarrollo, ENTONCES el sistema DEBERÁ impedir que la versión nueva atienda peticiones y avisar del valor que falla. |
| R008 | MUST      | CUANDO la aplicación envía un correo (verificación, recuperación de contraseña o aviso de intento de registro), el sistema DEBERÁ enviarlo desde una dirección del dominio `200oklabs.com`, autenticada ante los proveedores de correo, de modo que llegue a la bandeja de entrada y no a la de spam. |
| R009 | MUST      | SI deja de funcionar una instancia de cualquiera de los servicios, o una zona completa del proveedor, ENTONCES el sistema DEBERÁ seguir atendiendo las peticiones, reponer la capacidad perdida sin intervención de una persona y no perder datos ya confirmados. |
| R010 | MUST      | El sistema DEBERÁ conservar copias de la base de datos que permitan restaurarla en cualquier momento de los últimos 7 días, con una pérdida máxima de 5 minutos de datos. |
| R011 | MUST      | El sistema DEBERÁ medir de forma continua las señales SG1 a SG6 de `operations/v0.1.0.md`, cada una con la cifra que compara su umbral, y conservar su historial al menos 30 días. |
| R012 | MUST      | CUANDO una señal supera su umbral de `operations/v0.1.0.md`, el sistema DEBERÁ enviar un correo al responsable de operación en menos de 5 minutos, a cualquier hora, con la señal, su valor y la hora. |
| R013 | MUST      | El sistema DEBERÁ comprobar cada minuto, desde fuera del entorno de producción, que el servicio responde, y dar la disponibilidad del mes en curso (SG3). |
| R014 | MUST      | CUANDO el responsable de operación decide retirar el servicio, el sistema DEBERÁ, en menos de 10 minutos: mostrar una página de mantenimiento en todas las direcciones públicas, incluida la del QR; dejar de aceptar pedidos y de enviar correos; y conservar todos los datos. |
| R015 | MUST      | CUANDO el responsable de operación vuelve a poner en marcha un servicio retirado, el sistema DEBERÁ atender de nuevo con los mismos datos que tenía al retirarse. |
| R016 | MUST      | El sistema DEBERÁ conservar como mucho 30 días los registros que contienen la dirección IP de quien hace la petición, y no guardar en ningún registro contraseñas, tokens, cookies ni el texto de las búsquedas de los clientes. |
| R017 | MUST      | MIENTRAS en la preproducción 50 establecimientos tienen la sesión de música abierta, con 100 clientes cada uno al ritmo de la hora pico de la feature 003, el sistema DEBERÁ responder a las búsquedas con un p95 por debajo de 2 s y al estado del cliente con un p95 por debajo de 1 s, sin errores del servidor. |
| R018 | MUST      | CUANDO una persona escanea con la cámara de un móvil real el QR impreso de un establecimiento en producción, el sistema DEBERÁ abrir su página por HTTPS y permitir buscar y pedir una canción, en Chrome y en Safari del móvil. |
| R019 | MUST      | CUANDO el propietario usa el panel y el reproductor en producción, el sistema DEBERÁ funcionar en Chrome, Edge, Firefox y Safari de escritorio: registrarse, verificar el correo, descargar el QR, abrir la sesión de música y reproducir la cola. |
| R020 | SHOULD    | SI desde una misma dirección IP llegan más de 50 rechazos por falta de permiso en un minuto, ENTONCES el sistema DEBERÁ avisar al responsable de operación como posible intento de acceso a otro establecimiento (SG6). |
| R021 | SHOULD    | CUANDO la cuota diaria del proveedor de música llega al 80 %, el sistema DEBERÁ avisar al responsable de operación antes de que la búsqueda deje de estar disponible. |
| R022 | MUST      | CUANDO se va a correr la prueba de carga, el sistema DEBERÁ poder levantar una preproducción con la misma definición, capacidad y configuración que producción, salvo el catálogo de música, que es el falso, y sus propios datos y secretos; y destruirla al terminar sin dejar recursos en marcha ni afectar a producción. |

## Criterios de aceptación

### R001

- **Dado** la etiqueta `v0.2.0` y la aprobación de una persona autorizada **cuando** se lanza el despliegue **entonces** producción atiende con las imágenes construidas desde esa etiqueta, y el registro del despliegue muestra la etiqueta, quién lo aprobó y la hora.
- **Dado** un despliegue ya hecho de `v0.2.0` **cuando** se repite desde otro equipo con la misma etiqueta **entonces** el resultado es el mismo, sin pasos distintos.

### R002

- **Dado** una rama o un commit sin etiqueta de versión **cuando** se intenta desplegar en producción **entonces** se rechaza y lo que estaba en marcha no cambia.
- **Dado** una versión etiquetada sin aprobación **cuando** se intenta desplegar **entonces** el despliegue espera la aprobación y no cambia nada hasta recibirla.

### R003

- **Dado** el dominio `200oklabs.com` **cuando** se abre `http://` en cualquier página **entonces** redirige a `https://` en la misma ruta.
- **Dado** un navegador actual **cuando** se abre cualquier página por HTTPS **entonces** el certificado es válido y el navegador no muestra ninguna advertencia.

### R004

- **Dado** una versión con dos servicios que arrancan a la vez **cuando** se despliega **entonces** las migraciones se ejecutan una sola vez, la revisión de la base de datos coincide con la de la versión, y ninguna petición la atiende la versión nueva antes de que terminen.

### R005

- **Dado** una migración que falla a propósito en un entorno de prueba **cuando** se despliega **entonces** el despliegue se detiene, la versión anterior sigue atendiendo y la base de datos queda en su revisión anterior.
- **Dado** una versión que no supera su comprobación de salud **cuando** se despliega **entonces** no recibe tráfico y la anterior sigue atendiendo.

### R006

- **Dado** el repositorio, las imágenes publicadas y los registros de un despliegue **cuando** se buscan los valores de los secretos de producción **entonces** no aparece ninguno.

### R007

- **Dado** una configuración de producción sin el secreto que firma la identificación de los dispositivos, o con su valor de desarrollo, **cuando** se despliega **entonces** la versión nueva no recibe tráfico y el registro del despliegue nombra la variable que falla.

### R008

- **Dado** una cuenta nueva registrada con un buzón de Gmail y otra con uno de Outlook **cuando** se envía el correo de verificación **entonces** llega a la bandeja de entrada de ambos, y sus cabeceras muestran la autenticación del dominio aprobada.

### R009

- **Dado** el servicio atendiendo una prueba de tráfico constante **cuando** se detiene a la fuerza una instancia de la API, otra del trabajador y otra del tiempo real **entonces** la tasa de errores del servidor no pasa del 1 % durante la prueba, y la capacidad vuelve a la inicial sin intervención en menos de 5 minutos.
- **Dado** una conmutación forzada de la base de datos a su réplica en otra zona **cuando** termina **entonces** el servicio vuelve a atender en menos de 5 minutos y no falta ningún pedido confirmado antes de la conmutación.

### R010

- **Dado** pedidos hechos en un momento conocido **cuando** se restaura una copia de la base de datos de 10 minutos después en un entorno aparte **entonces** la copia restaurada contiene esos pedidos.
- **Dado** el registro de copias **cuando** se consulta **entonces** se puede restaurar cualquier momento de los últimos 7 días.

### R011

- **Dado** el servicio en marcha **cuando** se consultan las señales SG1 a SG6 **entonces** cada una muestra la cifra que compara su umbral (p95 de la búsqueda, tasa de errores, disponibilidad, p95 del estado del cliente, hueco entre canciones y tasa de canciones fallidas, rechazos por permiso), con datos de al menos los últimos 30 días.

### R012

- **Dado** una señal forzada por encima de su umbral en un entorno de prueba **cuando** se mantiene el tiempo que fija su umbral **entonces** el responsable de operación recibe un correo en menos de 5 minutos, con el nombre de la señal, su valor y la hora.
- **Dado** una señal forzada por encima de su umbral fuera del horario de los locales **cuando** se mantiene el tiempo que fija su umbral **entonces** el correo llega igual, sin esperar al horario.

### R013

- **Dado** el servicio retirado a propósito durante 5 minutos **cuando** se consulta la comprobación externa **entonces** registra la caída con su duración, la disponibilidad del mes la descuenta, y salta el aviso de SG3.

### R014

- **Dado** el servicio en marcha **cuando** el responsable de operación lo retira **entonces** en menos de 10 minutos la dirección del QR y el panel muestran la página de mantenimiento, una petición de pedido no se acepta y no sale ningún correo.
- **Dado** el servicio retirado **cuando** se consulta la base de datos **entonces** conserva todas las cuentas, establecimientos, sesiones y pedidos que tenía.

### R015

- **Dado** el servicio retirado **cuando** el responsable de operación lo vuelve a poner en marcha **entonces** el propietario inicia sesión con su cuenta y ve su establecimiento y su QR sin cambios.

### R016

- **Dado** un registro con la IP de una petición de hace 31 días **cuando** se buscan los registros **entonces** ya no existe.
- **Dado** un inicio de sesión, una búsqueda de un cliente y un pedido **cuando** se revisan todos los registros que generaron **entonces** no aparecen la contraseña, los tokens, las cookies ni el texto buscado.

### R017

- **Dado** la preproducción levantada con la versión que se va a abrir a los establecimientos del piloto **cuando** corre la prueba de carga con 50 establecimientos y 100 clientes por establecimiento al ritmo de la hora pico de 003 **entonces** la búsqueda tiene un p95 por debajo de 2 s y el estado del cliente un p95 por debajo de 1 s, con 0 errores del servidor, y el resultado queda anotado en el script de la prueba.

### R018

- **Dado** el QR impreso de un establecimiento en producción **cuando** se escanea con la cámara de un iPhone (Safari) y de un Android (Chrome) **entonces** se abre su página por HTTPS, se busca una canción, se pide y aparece entre los pedidos del cliente; el resultado queda en `docs/qa/` con los dispositivos.

### R019

- **Dado** una cuenta nueva en producción **cuando** se recorre registro, verificación, descarga del QR, apertura de la sesión y reproducción de una canción pedida en Chrome, Edge, Firefox y Safari de escritorio **entonces** el recorrido termina en todos ellos y el resultado queda en `docs/qa/`.

### R020

- **Dado** 60 peticiones con rechazo por falta de permiso desde una IP en un minuto **cuando** termina el minuto **entonces** el responsable de operación recibe un correo con esa IP.

### R021

- **Dado** el consumo de la cuota diaria del proveedor de música al 80 % **cuando** se alcanza **entonces** el responsable de operación recibe un correo.

### R022

- **Dado** producción en marcha **cuando** se levanta la preproducción **entonces** tiene la misma capacidad y configuración que producción, usa el catálogo falso y su propia base de datos, y producción sigue atendiendo sin cambios.
- **Dado** la preproducción después de la prueba **cuando** se destruye **entonces** no queda ningún recurso suyo en marcha ni facturando, y los datos de producción no cambian.

## Requisitos no funcionales

- **Disponibilidad:** 99,5 % mensual del servicio (Q3); como mucho unas 3,6 h de caída al mes (R009, R013).
- **Rendimiento con la carga del piloto:** búsqueda p95 < 2 s (Q1); estado del cliente p95 < 1 s (Q4); 0 errores del servidor (Q2) (R017).
- **Recuperación:** pérdida máxima de datos de 5 minutos y copias de 7 días (R010). Volver a atender tras perder una zona en menos de 5 minutos (R009).
- **Alertas:** el aviso llega en menos de 5 minutos desde que una señal supera su umbral (R012).
- **Privacidad:** registros con IP conservados 30 días como mucho (R016); los datos se alojan en EE. UU., lo que la política de tratamiento tiene que informar (ADR-0006).
- **Coste:** sin tope fijado. El plan estima el coste mensual de producción y el de cada uso de la preproducción, y se aprueba con esas cifras.

## Supuestos

- Existe una cuenta de AWS a nombre del negocio, con facturación activa, en la que el desarrollador puede crear recursos.
- El negocio aporta, antes de la puesta en marcha, el texto definitivo de la política de tratamiento de datos (R022 de 001). Sin él, la aplicación no arranca en producción.
- La clave de la API de YouTube es del negocio, y su cuota diaria basta para el piloto; si no basta, se pide una ampliación a Google.
- La versión 0.2.0 solo cambia, respecto de la 0.1.0, la instrumentación de las señales, los registros y la configuración de preproducción, sin cambios de comportamiento para los usuarios.

## Preguntas abiertas

Ninguna.

## Historial de cambios

> Lo rellena `/sdd:amend` cuando cambian los requisitos después de aprobar la
> spec: fecha, qué cambió, por qué y los IDs afectados.

- **2026-11-09 — Se pone en marcha la versión 0.2.0, no la 0.1.0.** Al planificar se vio que el código de la etiqueta `v0.1.0` no puede cumplir esta spec: le falta lo que la propia feature añade a la aplicación, que es el registro de cada petición sin el texto buscado, las métricas y el modo de preproducción con el catálogo falso. El usuario eligió desplegar la primera versión que incluya la feature, la 0.2.0. Es una aclaración: los requisitos ya hablaban de «una versión etiquetada», y solo cambian el título, el contexto, el alcance, el supuesto y la etiqueta de ejemplo de los criterios de R001. IDs afectados: R001 (criterios).
