# Prueba manual: imprimir y escanear el QR

Feature 001 (alta de establecimiento con QR), requisitos R010, R011 y R012. Comprueba
que el QR impreso desde el panel se lee con la cámara nativa del móvil, sin instalar
ninguna aplicación, y abre la página pública del establecimiento.

## Preparación

1. Levanta el entorno desde `src/`: `docker compose up -d --build`.
2. El QR codifica `PUBLIC_BASE_URL/l/<código>`. Para que un móvil lo abra, ese origen
   tiene que ser alcanzable desde el móvil: en local, cambia `PUBLIC_BASE_URL` en
   `src/docker-compose.yml` por la IP de la máquina en la wifi (`http://192.168.x.y:5173`).
   En un entorno desplegado, usa su URL pública.
3. Regístrate en `/registro` con un nombre largo con tildes y eñe, por ejemplo
   «Café y Bar La Ñapa de la Esquina del Parque», y verifica el correo desde Mailpit
   (`http://localhost:8025`).

## Pasos

1. En el panel, pulsa «Imprimir el QR». Se abre el diálogo de impresión del navegador.
2. Imprime en papel carta (216 × 279 mm), escala 100 %, sin «ajustar a la página».
3. Comprueba en el papel: solo aparecen el QR y el nombre del establecimiento debajo;
   el nombre largo ocupa dos líneas como mucho, termina en «…» si no cabe, y las
   tildes y la eñe se ven bien.
4. Con la cámara nativa de cada móvil (sin otra aplicación), apunta al QR a unos 30 cm
   y a 1 m, con buena luz y con luz de interior normal.
5. Toca el enlace que ofrece la cámara: tiene que abrir el navegador del móvil en la
   página pública, con el nombre del establecimiento y sin pedir cuenta ni instalar nada.

## Resultados

Rellena una fila por dispositivo. «Resultado» es *pasa* si se cumplen los pasos 3 a 5.

| Fecha | Dispositivo | Sistema | Cámara / app | Impresora | Distancia y luz | Resultado | Notas |
|-------|-------------|---------|--------------|-----------|-----------------|-----------|-------|
| _pendiente_ | iPhone (modelo) | iOS (versión) | Cámara nativa | | 30 cm y 1 m, interior | | |
| _pendiente_ | Android (modelo) | Android (versión) | Cámara nativa o Google Lens del sistema | | 30 cm y 1 m, interior | | |

Hasta que estas filas tengan resultado, la prueba sigue pendiente. La lectura
automática del PNG ya la cubre `src/backend/tests/integration/test_qr.py`
(`test_F001_R010_png_decodifica_a_la_url_publica`), pero no sustituye esta prueba:
la impresión y las cámaras reales son justo lo que esa prueba no ve.
