# La función `edge` y el almacén de claves del mantenimiento (D1, D10).
resource "aws_cloudfront_key_value_store" "maintenance" {
  name    = "${var.name}-maintenance"
  comment = "maintenance=on retira el servicio (D10)"
}

# La clave nace en `off`. La cambia `maintenance.yml`, así que Terraform no la deshace.
resource "aws_cloudfrontkeyvaluestore_key" "maintenance" {
  key_value_store_arn = aws_cloudfront_key_value_store.maintenance.arn
  key                 = "maintenance"
  value               = "off"

  lifecycle {
    ignore_changes = [value]
  }
}

locals {
  # El identificador del almacén es el final de su ARN: `…:key-value-store/<id>`.
  key_value_store_id = element(split("/", aws_cloudfront_key_value_store.maintenance.arn), 1)
}

resource "aws_cloudfront_function" "edge" {
  name                         = "${var.name}-edge"
  runtime                      = "cloudfront-js-2.0"
  comment                      = "Rutas de la SPA y mantenimiento (D1, D10)"
  publish                      = true
  key_value_store_associations = [aws_cloudfront_key_value_store.maintenance.arn]
  code                         = replace(file("${path.module}/functions/edge.js"), "__KVS_ID__", local.key_value_store_id)
}
