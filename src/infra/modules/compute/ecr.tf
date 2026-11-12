# Una imagen para el monolito (la API, el trabajador y la migración) y otra para el tiempo
# real (ADR-0001). Etiquetas inmutables: una versión desplegada es siempre la imagen que se
# construyó desde su etiqueta (D9, R001).
locals {
  repositories = toset(["api", "realtime"])
}

resource "aws_ecr_repository" "this" {
  for_each = local.repositories

  name                 = "${var.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = !var.production

  image_scanning_configuration {
    scan_on_push = true
  }
}
