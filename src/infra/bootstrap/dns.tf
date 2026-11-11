# Zona del dominio (plan D1). Los servidores de nombres que devuelve hay que ponerlos, a
# mano y una sola vez, en el registrador de 200oklabs.com (D17).
resource "aws_route53_zone" "domain" {
  name    = var.domain
  comment = "MyPlaylist (feature 004)"

  lifecycle {
    prevent_destroy = true
  }
}
