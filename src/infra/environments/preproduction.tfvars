# Preproducción temporal (feature 004, plan D13): la misma definición que producción. El
# catálogo falso, Mailpit y su dominio salen de `environment`. El correo de avisos llega
# aparte, en TF_VAR_alert_email: no se versiona.
environment = "preproduction"
zone_id     = "Z0639081273LJQWTITRKS"
image_tag   = "v0.2.0-rc.1"
