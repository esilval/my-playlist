# Spec: Alta del establecimiento y su QR

| Campo  | Valor        |
| ------ | ------------ |
| ID     | `001-alta-establecimiento-qr`     |
| Fecha  | 2026-10-16     |
| Estado | Approved · 4d07554196e2        |
| Issue  | —            |
| Origen | B01 · G2, G4 · D1§2, D1§5 |

> Este documento describe **qué** y **por qué**, nunca **cómo**.
> Toda decisión de implementación (librerías, esquemas, servicios) va en `plan.md`.
>
> Sustituye todo texto en cursiva; si una sección no aplica, escribe
> «No aplica.». Solo el usuario cambia el Estado, con `/sdd:approve`.

## Problema

El propietario no tiene forma de poner su local en MyPlaylist ni de dar a sus clientes un punto de entrada.

## Contexto

Feature creada desde la candidata B01 «Alta del establecimiento y su QR» de `product/backlog.md`, con el producto de discovery aprobado.

- **G2 — El propietario controla la música de su local:** el propietario decide qué suena: abre y cierra la sesión, ve la cola, la reordena, elimina canciones y agrega las suyas. Se nota en que nada suena en el local sin que él pueda quitarlo.
- **G4 — MyPlaylist se sostiene como SaaS por suscripción:** los establecimientos se dan de alta solos por la web, prueban gratis y luego pagan un plan (Básico o Premium) para seguir usándolo. Se nota en establecimientos que pasan de la prueba a un plan de pago.
- **Origen D1§2** «Propuesta»: `product/sources/D1-overview.md`
- **Origen D1§5** «MyPlaylist como Software as a Service (SaaS)»: `product/sources/D1-overview.md`

## Alcance

### Dentro

- El propietario crea su cuenta y su establecimiento desde la web, inicia sesión y descarga o imprime el QR único de su local.
- Registro e inicio de sesión del propietario, datos del establecimiento, generación del QR por establecimiento.

### Fuera (non-goals)

- Pagos, prueba gratuita y planes (B09).
- Empleados u otros administradores; varios establecimientos por cuenta.
- Inicio de sesión con cuentas de terceros (redes sociales).
- Buscar y pedir canciones desde la página del QR (B03).
- Abrir la sesión de música y reproducir (B02).
- Controlar que el QR solo se use dentro del local (decidido en el brief: no se controla).
- Borrar la cuenta o el establecimiento, y regenerar o rotar el QR.

## Requisitos

Notación EARS. Cada requisito lleva un ID estable que se referencia después en
`plan.md`, `tasks.md` y en los tests.

Patrones:

| Patrón      | Forma                                                       |
| ----------- | ----------------------------------------------------------- |
| Ubicuo      | El sistema DEBERÁ \<respuesta\>                             |
| Evento      | CUANDO \<disparador\>, el sistema DEBERÁ \<respuesta\>      |
| Estado      | MIENTRAS \<estado\>, el sistema DEBERÁ \<respuesta\>        |
| Opcional    | DONDE \<característica\>, el sistema DEBERÁ \<respuesta\>   |
| No deseado  | SI \<condición\>, ENTONCES el sistema DEBERÁ \<respuesta\>  |

| ID   | Prioridad | Requisito |
| ---- | --------- | --------- |
| R001 | OBSOLETO  | CUANDO un visitante envía el formulario de registro con correo, contraseña, nombre del establecimiento y la autorización de tratamiento de datos, y opcionalmente la dirección y el teléfono del establecimiento, el sistema DEBERÁ crear la cuenta del propietario junto con su único establecimiento y dejarlo con la sesión iniciada en el panel de ese establecimiento. (reemplazado por R023 y R025) |
| R002 | OBSOLETO  | SI el correo del registro ya pertenece a una cuenta, ENTONCES el sistema DEBERÁ rechazar el registro sin crear nada y ofrecer ir al inicio de sesión. (reemplazado por R024) |
| R003 | MUST      | SI falta un dato obligatorio del registro, el correo no tiene formato válido o la contraseña tiene menos de 8 caracteres, ENTONCES el sistema DEBERÁ rechazar el registro indicando cada campo inválido y conservar lo escrito salvo la contraseña. |
| R004 | MUST      | SI el visitante no acepta la autorización de tratamiento de datos personales, ENTONCES el sistema DEBERÁ impedir el registro. |
| R005 | MUST      | CUANDO el propietario inicia sesión con un correo y una contraseña correctos, el sistema DEBERÁ darle acceso al panel de su establecimiento. |
| R006 | MUST      | SI el correo o la contraseña del inicio de sesión son incorrectos, ENTONCES el sistema DEBERÁ rechazar el acceso con un mismo mensaje genérico, sin revelar cuál de los dos falló ni si el correo existe. |
| R007 | SHOULD    | SI se producen 5 intentos fallidos de inicio de sesión sobre un mismo correo en 15 minutos, ENTONCES el sistema DEBERÁ rechazar nuevos intentos sobre ese correo durante 15 minutos. |
| R008 | MUST      | CUANDO el propietario cierra sesión, el sistema DEBERÁ terminar su sesión de forma que el panel no sea accesible sin volver a iniciarla. |
| R009 | MUST      | El sistema DEBERÁ asignar a cada establecimiento, al crearlo, un código QR único que no cambia durante la vida del establecimiento. |
| R010 | MUST      | CUANDO el propietario pide descargar el QR desde su panel, el sistema DEBERÁ entregarle un archivo de imagen con el QR de su establecimiento y el nombre del establecimiento visible. |
| R011 | SHOULD    | CUANDO el propietario pide imprimir el QR desde su panel, el sistema DEBERÁ mostrar una versión lista para imprimir con el QR y el nombre del establecimiento. |
| R012 | MUST      | CUANDO cualquier persona escanea el QR de un establecimiento con la cámara de su móvil, el sistema DEBERÁ abrir en el navegador la página de ese establecimiento mostrando su nombre, sin pedir instalar nada ni registrarse. |
| R013 | MUST      | SI se abre el enlace de un establecimiento que no existe, ENTONCES el sistema DEBERÁ mostrar un aviso de establecimiento no encontrado sin revelar datos de ningún otro establecimiento. |
| R014 | MUST      | CUANDO el propietario modifica los datos de su establecimiento, el sistema DEBERÁ guardar solo los datos enviados y mantener el mismo QR; SI el nombre queda vacío, DEBERÁ rechazar el cambio indicándolo en el campo. |
| R015 | MUST      | SI una persona sin sesión, o con la sesión de otro propietario, intenta ver o modificar el panel, los datos o el QR de un establecimiento, ENTONCES el sistema DEBERÁ denegar el acceso sin mostrar datos de ese establecimiento. |
| R016 | SHOULD    | CUANDO el propietario solicita recuperar su contraseña indicando su correo, el sistema DEBERÁ enviar a ese correo, si pertenece a una cuenta, un enlace de un solo uso válido 60 minutos para fijar una nueva contraseña de al menos 8 caracteres, y mostrar el mismo mensaje exista o no la cuenta; SI la contraseña nueva es más corta, DEBERÁ rechazarla indicándolo y el enlace seguirá sirviendo. |
| R017 | MUST      | CUANDO se crea una cuenta, el sistema DEBERÁ enviar al correo registrado un enlace de verificación de un solo uso que, al abrirse, marca el correo como verificado. |
| R018 | MUST      | SI el propietario con el correo sin verificar pide descargar o imprimir el QR, ENTONCES el sistema DEBERÁ impedirlo, indicar que debe verificar su correo y ofrecer reenviar el enlace de verificación. |
| R019 | MUST      | MIENTRAS el correo del propietario no esté verificado, el sistema DEBERÁ permitirle entrar al panel y editar los datos de su establecimiento. |
| R020 | MUST      | SI la sesión del propietario pasa 12 horas sin actividad, ENTONCES el sistema DEBERÁ cerrarla y pedir de nuevo el inicio de sesión al siguiente acceso al panel. |
| R021 | MUST      | CUANDO el propietario fija una nueva contraseña mediante un enlace de recuperación, el sistema DEBERÁ cerrar todas las sesiones de esa cuenta que estuvieran abiertas, de forma que ninguna dé acceso al panel sin volver a iniciar sesión. |
| R022 | MUST      | El sistema DEBERÁ publicar la política de tratamiento de datos personales en una página accesible sin sesión, enlazarla desde el formulario de registro junto a la autorización, y guardar con cada autorización la versión de la política aceptada y su fecha. |
| R023 | MUST      | CUANDO un visitante envía el formulario de registro válido con un correo que no pertenece a ninguna cuenta, con contraseña, nombre del establecimiento y la autorización de tratamiento de datos, y opcionalmente la dirección y el teléfono del establecimiento, el sistema DEBERÁ crear la cuenta del propietario junto con su único establecimiento, sin iniciar sesión, y mostrar un mensaje que pide revisar el correo para continuar. |
| R024 | MUST      | SI el correo del registro ya pertenece a una cuenta, ENTONCES el sistema DEBERÁ no crear nada, mostrar exactamente el mismo mensaje que en un registro nuevo y enviar a ese correo un aviso del intento con enlaces para iniciar sesión y para recuperar la contraseña. |
| R025 | MUST      | CUANDO el propietario abre por primera vez un enlace de verificación válido, el sistema DEBERÁ marcar su correo como verificado y dejarlo con la sesión iniciada en el panel de su establecimiento. |
| R026 | MUST      | SI se abre un enlace de verificación inexistente, alterado o reemplazado por un reenvío posterior, ENTONCES el sistema DEBERÁ indicar que el enlace no es válido, no verificar ningún correo ni iniciar sesión, y ofrecer pedir un enlace nuevo. |
| R027 | SHOULD    | SI para un mismo correo se piden en 60 minutos más de 3 correos de un mismo tipo (recuperación de contraseña, reenvío de verificación o aviso de intento de registro), ENTONCES el sistema DEBERÁ no enviar más correos de ese tipo hasta que pasen los 60 minutos, mostrando la misma respuesta que en una solicitud atendida salvo en el reenvío de verificación, donde indicará que se espere. |
| R028 | MUST      | SI se abre un enlace de verificación sin usar que se emitió hace más de 7 días, ENTONCES el sistema DEBERÁ indicar que el enlace caducó, no verificar el correo ni iniciar sesión, y ofrecer pedir un enlace nuevo. |

## Criterios de aceptación

### R001

- **Dado** un visitante sin cuenta **cuando** envía el registro con un correo nuevo, una contraseña de 8 o más caracteres, el nombre «Bar La Esquina» y la autorización marcada **entonces** queda dentro del panel del establecimiento «Bar La Esquina» con la sesión iniciada.
- **Dado** el registro anterior completado **cuando** el propietario cierra sesión y vuelve a entrar con ese correo y contraseña **entonces** ve el mismo establecimiento, y es el único asociado a su cuenta.

- **Dado** un visitante sin cuenta **cuando** se registra indicando además dirección y teléfono **entonces** ambos aparecen en los datos de su establecimiento; si los deja vacíos, el registro se completa igual.

### R002

- **Dado** una cuenta existente con el correo `a@ejemplo.com` **cuando** un visitante intenta registrarse con `a@ejemplo.com` (con o sin mayúsculas distintas) **entonces** el registro se rechaza, no se crea ningún establecimiento y se ofrece ir al inicio de sesión.

### R003

- **Dado** el formulario de registro **cuando** se envía sin nombre de establecimiento **entonces** se rechaza señalando ese campo y el correo escrito sigue en el formulario.
- **Dado** el formulario de registro **cuando** se envía con el correo `sin-arroba` y una contraseña de 7 caracteres **entonces** se rechaza señalando ambos campos y la contraseña queda vacía.

### R004

- **Dado** un formulario de registro con todos los datos válidos **cuando** se envía sin marcar la autorización de tratamiento de datos **entonces** no se crea la cuenta y se indica que la autorización es obligatoria.

### R005

- **Dado** un propietario registrado sin sesión **cuando** inicia sesión con su correo y contraseña **entonces** entra al panel de su establecimiento.

### R006

- **Dado** un propietario registrado **cuando** inicia sesión con su correo y una contraseña errónea **entonces** ve un mensaje genérico de credenciales incorrectas.
- **Dado** un correo que no pertenece a ninguna cuenta **cuando** se intenta iniciar sesión con él **entonces** el mensaje es idéntico al del caso anterior.

### R007

- **Dado** 5 intentos fallidos sobre un correo en menos de 15 minutos **cuando** se hace un sexto intento, aun con la contraseña correcta **entonces** se rechaza indicando que se espere; pasados 15 minutos, la contraseña correcta vuelve a dar acceso.

### R008

- **Dado** un propietario con sesión iniciada **cuando** cierra sesión y luego abre el enlace de su panel **entonces** se le pide iniciar sesión.

### R009

- **Dado** dos establecimientos registrados **cuando** se comparan sus QR **entonces** cada uno lleva a la página de su propio establecimiento y no al del otro.
- **Dado** un QR descargado hoy **cuando** se escanea días después **entonces** sigue abriendo la página del mismo establecimiento.

### R010

- **Dado** un propietario con sesión iniciada y correo verificado **cuando** descarga el QR **entonces** obtiene un archivo de imagen con el QR y el nombre de su establecimiento, y al escanear la imagen impresa en tamaño carta con un móvil se abre la página de su establecimiento.

### R011

- **Dado** un propietario con sesión iniciada y correo verificado **cuando** elige imprimir el QR **entonces** se abre el diálogo de impresión con una página que contiene solo el QR y el nombre del establecimiento.

### R012

- **Dado** un establecimiento registrado **cuando** un móvil sin la aplicación ni cuenta escanea su QR **entonces** el navegador abre una página que muestra el nombre del establecimiento sin pedir registro ni instalación.

### R013

- **Dado** un enlace de establecimiento alterado o inexistente **cuando** se abre en el navegador **entonces** se muestra «establecimiento no encontrado» y ningún nombre ni dato de otro establecimiento.

### R014

- **Dado** el establecimiento «Bar La Esquina» con su QR descargado **cuando** el propietario cambia el nombre a «La Esquina Bar» **entonces** el panel muestra el nombre nuevo y el QR ya impreso abre la página con el nombre nuevo.
- **Dado** el establecimiento «Bar La Esquina» **cuando** el propietario deja el nombre en blanco y guarda **entonces** ve el error en el campo del nombre y el nombre sigue siendo «Bar La Esquina».
- **Dado** el establecimiento con dirección y teléfono guardados **cuando** el propietario borra la dirección y guarda **entonces** la dirección queda vacía y el teléfono no cambia.

### R015

- **Dado** una persona sin sesión **cuando** abre el enlace del panel de un establecimiento **entonces** se le pide iniciar sesión y no ve datos del establecimiento.
- **Dado** el propietario A con sesión iniciada **cuando** intenta ver, modificar o descargar el QR del establecimiento del propietario B **entonces** se le deniega el acceso y los datos de B no cambian.

### R016

- **Dado** un propietario registrado **cuando** pide recuperar la contraseña con su correo **entonces** recibe un enlace; al usarlo fija una contraseña nueva, con la que entra, y el mismo enlace ya no sirve una segunda vez.
- **Dado** un enlace de recuperación de más de 60 minutos **cuando** se abre **entonces** se rechaza y se ofrece pedir uno nuevo.
- **Dado** un enlace de recuperación vigente **cuando** el propietario fija una contraseña de 7 caracteres **entonces** se rechaza indicando el mínimo, la contraseña anterior sigue valiendo y el mismo enlace sirve para fijar una de 8 o más.

### R017

- **Dado** un registro recién completado **cuando** el propietario abre el enlace recibido en su correo **entonces** su correo queda verificado y puede descargar el QR; abrir el mismo enlace otra vez muestra que ya está verificado y no cambia nada.

### R018

- **Dado** un propietario con el correo sin verificar **cuando** intenta descargar o imprimir el QR **entonces** no obtiene el QR, ve que debe verificar el correo y puede pedir que se le reenvíe el enlace.

### R019

- **Dado** un propietario con el correo sin verificar **cuando** inicia sesión y cambia el teléfono del establecimiento **entonces** entra al panel y el cambio queda guardado.

### R020

- **Dado** un propietario con sesión iniciada **cuando** pasa 12 horas sin actividad y abre el panel **entonces** se le pide iniciar sesión.
- **Dado** un propietario con sesión iniciada **cuando** usa el panel al menos una vez cada pocas horas durante 14 horas **entonces** la sesión sigue abierta.

### R021

- **Dado** un propietario con sesión iniciada en dos navegadores **cuando** fija una nueva contraseña desde un enlace de recuperación **entonces** al abrir el panel en cualquiera de los dos se le pide iniciar sesión, y entra con la contraseña nueva.
- **Dado** un propietario que fijó una nueva contraseña desde un enlace de recuperación **cuando** intenta iniciar sesión con la contraseña anterior **entonces** se rechaza con el mensaje genérico de credenciales incorrectas.

### R022

- **Dado** el formulario de registro **cuando** el visitante sigue el enlace junto a la autorización **entonces** ve la política de tratamiento de datos sin haber iniciado sesión.
- **Dado** un registro completado con la política vigente en la versión «2026-10» **cuando** se consulta la autorización guardada **entonces** consta la versión «2026-10» y la fecha del registro.

### R023

- **Dado** un visitante sin cuenta **cuando** envía el registro con un correo nuevo, una contraseña de 8 o más caracteres, el nombre «Bar La Esquina» y la autorización marcada **entonces** ve el mensaje de revisar el correo, no queda con la sesión iniciada y existe una cuenta con el establecimiento «Bar La Esquina» como único asociado.
- **Dado** el registro anterior **cuando** el propietario inicia sesión con ese correo y contraseña **entonces** entra al panel de «Bar La Esquina».
- **Dado** un visitante sin cuenta **cuando** se registra indicando además dirección y teléfono **entonces** ambos aparecen en los datos de su establecimiento; si los deja vacíos, el registro se completa igual.

### R024

- **Dado** una cuenta existente con el correo `a@ejemplo.com` **cuando** un visitante se registra con `A@Ejemplo.com` **entonces** ve exactamente el mismo mensaje que en un registro nuevo, no se crea ningún establecimiento y a `a@ejemplo.com` le llega un aviso del intento con enlaces para iniciar sesión y recuperar la contraseña.
- **Dado** un registro con correo nuevo y otro con correo existente **cuando** se comparan las dos respuestas que ve el visitante **entonces** son idénticas.

### R025

- **Dado** un registro recién completado **cuando** el propietario abre el enlace de verificación por primera vez **entonces** su correo queda verificado y está dentro del panel de su establecimiento.
- **Dado** un enlace de verificación ya usado **cuando** se abre otra vez sin sesión **entonces** se muestra que el correo ya está verificado y no se inicia sesión.

### R026

- **Dado** un enlace de verificación alterado **cuando** se abre **entonces** se indica que el enlace no es válido, no se inicia sesión y se ofrece pedir uno nuevo.
- **Dado** un propietario que pidió un reenvío **cuando** abre el enlace anterior al reenvío **entonces** se indica que no es válido y su correo sigue sin verificar.

### R027

- **Dado** 3 correos de recuperación pedidos para un correo en los últimos 60 minutos **cuando** se pide un cuarto **entonces** se muestra el mismo mensaje de siempre y no llega ningún correo nuevo; pasados 60 minutos desde el primero, la siguiente solicitud vuelve a enviar.
- **Dado** un propietario con 3 reenvíos de verificación en los últimos 60 minutos **cuando** pide otro **entonces** se le indica que espere y no se envía nada.

### R028

- **Dado** un registro hecho hace 8 días cuyo enlace de verificación nunca se abrió **cuando** se abre ese enlace **entonces** se indica que caducó, el correo sigue sin verificar, no se inicia sesión y se ofrece pedir uno nuevo.
- **Dado** un enlace de verificación emitido hace 6 días **cuando** se abre por primera vez **entonces** verifica el correo y deja la sesión iniciada en el panel.

## Requisitos no funcionales

- **Privacidad:** del propietario solo se guardan los datos de cuenta pedidos en el registro (correo, contraseña) y los del establecimiento (nombre y, si los da, dirección y teléfono); el tratamiento cumple la Ley 1581 de 2012, con autorización expresa registrada con su fecha.
- **Seguridad:** ninguna contraseña puede leerse en claro por nadie, incluido el personal de MyPlaylist; todo el tráfico entre navegador y servicio va cifrado.
- **Rendimiento:** registro, inicio de sesión y descarga del QR responden en menos de 2 s en el percentil 95, con hasta 50 establecimientos registrados usando el servicio a la vez.
- **Disponibilidad:** 99,5 % mensual para el inicio de sesión del propietario y para la página que abre el QR.
- **Compatibilidad:** el QR impreso en tamaño carta se escanea con la cámara nativa de iOS y Android de los últimos 3 años sin aplicaciones adicionales.

## Supuestos

- Una cuenta corresponde a un único establecimiento y a una única persona, sin empleados (brief, Usuarios).
- El QR es fijo por establecimiento y no se controla el acceso desde fuera del local en esta versión (brief, Preguntas).
- La página que abre el QR solo identifica el establecimiento; buscar y pedir canciones llega con B03.
- El registro no exige pago ni elegir plan; la prueba gratuita y los planes los define B09.
- El texto de la política de tratamiento de datos (responsable, finalidades, derechos del titular, transferencia internacional a EE. UU.) lo aporta el negocio con asesoría legal; esta feature lo publica y versiona, no lo redacta (R022).

## Preguntas abiertas

> Cita entre paréntesis el requisito al que afecta cada pregunta:
> `- [ ] (R002) ¿Cuánto dura la sesión?`. Una pregunta abierta sobre un MUST
> impide aprobar la spec. Al resolverla, conviértela en requisito o criterio y
> borra la línea.

No quedan preguntas abiertas.

## Historial de cambios

> Lo rellena `/sdd:amend` cuando cambian los requisitos después de aprobar la
> spec: fecha, qué cambió, por qué y los IDs afectados.

- **2026-10-16 — Requisito nuevo R021.** Al fijar una nueva contraseña por recuperación se cierran todas las sesiones abiertas de la cuenta. Motivo: sin esto, una sesión robada sobrevive a la recuperación de la contraseña (riesgo detectado en `plan.md`). IDs afectados: R021 (nuevo); R016 sin cambios.
- **2026-10-16 — Enmienda tras `/sdd:analyze`.**
  - **Requisito nuevo R022** (política de tratamiento): R004 pedía aceptar una autorización sin que existiera la política que se autoriza (Ley 1581).
  - **Cambio de comportamiento:** R001 → OBSOLETO, reemplazado por R023 y R025; R002 → OBSOLETO, reemplazado por R024. El registro con un correo existente revelaba que la cuenta existía y anulaba la protección de R006 y R016. Ahora registro nuevo y duplicado muestran el mismo mensaje, el duplicado avisa por correo al titular, y la sesión se inicia al verificar el correo.
  - **Requisito nuevo R026:** enlace de verificación inválido o reemplazado.
  - **Requisito nuevo R027 (SHOULD):** límite de 3 correos por tipo y hora para evitar inundar un buzón.
  - **Aclaración sin cambio de comportamiento** en R013 y en los criterios de R008, R013 y R015: «dirección» pasa a «enlace» cuando se refiere a una URL, para no confundirla con la dirección postal de R001.
  - IDs afectados: R001, R002 (obsoletos); R013 (aclarado); R022–R027 (nuevos).
- **2026-10-16 — Requisito nuevo R028.** El enlace de verificación caduca a los 7 días de emitirse. Motivo: desde R025 el enlace inicia sesión, y sin caducidad un correo antiguo filtrado daría acceso al panel (riesgo detectado en `plan.md`). IDs afectados: R028 (nuevo); R025 y R026 sin cambios.
- **2026-10-17 — Aclaración sin cambio de comportamiento en R014.** Se escribe lo que la implementación ya hacía y probaba: solo se guardan los datos enviados (un campo opcional vacío se borra y uno que no se envía no cambia), y un nombre vacío se rechaza en su campo, con la misma regla que el registro (R003). Motivo: pendiente anotado al implementar T014. IDs afectados: R014 (aclarado, con dos criterios nuevos).
- **2026-10-17 — Aclaraciones sin cambio de comportamiento en R016 y R026**, tras `/sdd:analyze`.
  - **R016:** la contraseña nueva de la recuperación sigue la misma regla de 8 caracteres que el registro (R003); si es más corta se rechaza y el enlace sigue sirviendo. La implementación ya lo hacía y lo probaba, pero ningún requisito lo pedía. Se añade un criterio.
  - **R026:** «con el token alterado» pasa a «alterado», para no usar un término de implementación en la spec.
  - IDs afectados: R016 y R026 (aclarados).
