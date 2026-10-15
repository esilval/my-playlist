# My Playlist - Encolador de canciones

Bienvenido a My Playlist, la aplicación que te permite crear y gestionar tus listas de reproducción de canciones de manera sencilla y eficiente. Con My Playlist, puedes agregar tus canciones favoritas, organizarlas en diferentes listas y disfrutar de tu música en cualquier momento.

## Descripción

El encolador de canciones es una herramienta online que provee el servicio de pedir música on-demand para que sea escuchada en varios estableciminetos en la ciudad de Bogotá (inicialmente). Los clientes de los establecimientos podrán pedir sus canciones a través de un buscador que estará disponible mediante un código QR, el cual habilitará la búsqueda de hasta 5 canciones (parametrizables) por cada cliente. Estas serán enlistadas en el playlis principal y serán reproducidas en el orden en que fueron solicitadas.

## Propuesta

Se propone crear una aplicación de encolamiento de canciones de diferentes plataformas de Streaming (Youtube (inicialmente), Spotify, Youtube Music, etc).

Inicialmente, la aplicación dispondrá de un buscador de canciones el cual estará conectado al buscador de la plataforma de streaming configurada. Dicha búsqueda debe estar disponible mediante un código QR.

Toda búsqueda de canciones estará asiciada a un establecimiento. Esto, para evitar que múltiples búsquedas se mezclen y se generen conflictos en la reproducción de las canciones. Cada establecimiento tendrá su propio código QR, el cual permitirá a los clientes realizar búsquedas de canciones y agregarlas a la lista de reproducción del establecimiento.

El buscador de canciones permitirá a los clientes buscar canciones por nombre, artista o álbum. Una vez que el cliente encuentre la canción que desea, podrá agregarla a la lista de reproducción del establecimiento. La aplicación se encargará de reproducir las canciones en el orden en que fueron solicitadas. Sólo se permitirá un máximo de 5 canciones por cliente, para garantizar que todos los clientes tengan la oportunidad de escuchar sus canciones favoritas.

El propietario del establecimiento tendrá la posibilidad de ver la playlist de la sesión actual. Sólamente él tendrá la capacidad de modificar el orden o eliminar las canciones que sean necesarias. Esto permitirá al propietario del establecimiento tener un control total sobre la música que se reproduce en su local. Asimismo, el propietario podrá incluir canciones de manera manual en la playlist, para garantizar que la música que se reproduce sea acorde al ambiente del establecimiento, ya que dispondrá de un buscador de canciones similar al que tienen los clientes, pero con la capacidad de agregar canciones sin límite de cantidad.

La aplicación podrá detectar si hay pantallas conectadas al sistema de audio del establecimiento o de la terminal donde se encuentra la aplicación. Al ser una aplicación desplegada en la web y con la capacidad de detectar pantallas conectadas, se podrá mostrar la lista de reproducción en tiempo real para que los clientes puedan ver qué canciones se están reproduciendo y cuáles están en cola. Esto mejorará la experiencia del cliente y fomentará la interacción con la aplicación. Esta configuración debe ser guardada para que el propietario del establecimiento pueda modificarla según sus necesidades.

Si la playlist finaliza y aún hay funcionamiento del establecimiento, la. aplicación tomará hasta 10 artistas al azar y buscará una canción de cada uno de ellos para reproducirla en la playlist. Esto permitirá que la música continúe reproduciéndose y que los clientes puedan seguir disfrutando de su experiencia en el establecimiento.

## Alcance

El alcance de la aplicación es proporcionar una experiencia de usuario fluida y agradable para los clientes de los establecimientos, permitiéndoles interactuar con la música que se reproduce en el lugar. Además, se busca ofrecer a los propietarios de los establecimientos un control total sobre la música que se reproduce, garantizando que la experiencia musical sea acorde al ambiente del lugar.

A nivel de producto, se cuenta con el siguiente alcance:

- Búsqueda de canciones por nombre, artista o álbum.
- Agregar canciones a la lista de reproducción del establecimiento.
- Reproducción de canciones en el orden en que fueron solicitadas.
- Administración de la lista de reproducción por parte del propietario del establecimiento.
- Limitación de hasta 5 canciones por cliente.
- Control total del propietario del establecimiento sobre la lista de reproducción.
- Extensión de la aplicación a diferentes plataformas de streaming.

## Fuera del alcance

- Subida de videos o canciones a la plataforma de streaming.
- Transmisión de eventos en vivo
- Creación de playlist en plataformas de streaming.
- Si hay publicidad en la plataforma de streaming, esta será reproducida y no se podrá controlar desde la aplicación.
- Gestión de suscripciones a plataformas de streaming. La aplicación no se encargará de gestionar las suscripciones de los usuarios a las plataformas de streaming, por lo que los usuarios deberán tener una cuenta activa en la plataforma correspondiente para poder utilizar la aplicación.

El alcance se limita a la funcionalidad de búsqueda y reproducción de canciones, así como a la gestión de la lista de reproducción por parte del propietario del establecimiento. Cualquier otra funcionalidad que no esté relacionada con estos aspectos se considera fuera del alcance de la aplicación.

## MyPlaylist como Software as a Service (SaaS)

MyPlaylist se presenta como un servicio de software como un servicio (SaaS), lo que significa que los usuarios pueden acceder a la aplicación a través de internet sin necesidad de instalarla en sus dispositivos. Esto permite una mayor accesibilidad y facilidad de uso para los clientes y propietarios de los establecimientos.

## Suscripción y pago

Idealmente, cada establecimiento debe tener una suscripción activa para poder utilizar la aplicación. La suscripción permitirá a los propietarios de los establecimientos acceder a todas las funcionalidades de la aplicación, incluyendo la gestión de la lista de reproducción y el control total sobre la música que se reproduce en su local.

Inicialmente , se ofrecerá un periodo de prueba gratuito para que los propietarios de los establecimientos puedan evaluar la aplicación y sus funcionalidades antes de comprometerse con una suscripción. Una vez finalizado el periodo de prueba, los propietarios deberán suscribirse a un plan de pago para continuar utilizando la aplicación.

### Modelos de suscripción

- **Plan Básico:** Acceso a la funcionalidad de búsqueda y reproducción de canciones, con un límite de 5 canciones por cliente y control total del propietario sobre la lista de reproducción.
- **Plan Premium:** Acceso a todas las funcionalidades de la aplicación, incluyendo la capacidad de agregar canciones sin límite de cantidad, personalización de la experiencia musical y soporte prioritario.

> Esta parte estará sujeta a revisiones y posibles cambios según la evolución del proyecto y las necesidades de los usuarios.

## Atributos de calidad

- **Rendimiento**: La aplicación debe ser capaz de manejar múltiples solicitudes de búsqueda y reproducción de canciones de manera eficiente, sin afectar la experiencia del usuario.

- **Disponibilidad**: La aplicación debe estar disponible en todo momento, garantizando que los clientes puedan interactuar con la música en cualquier momento durante el funcionamiento del establecimiento.

- **Seguridad**: La aplicación debe garantizar la seguridad de los datos de los usuarios y propietarios de los establecimientos, protegiendo la información personal y evitando accesos no autorizados.

- **Usabilidad**: La aplicación debe ser fácil de usar y navegar, proporcionando una experiencia de usuario intuitiva y agradable para los clientes y propietarios de los establecimientos.


