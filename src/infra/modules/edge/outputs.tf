output "distribution_id" {
  description = "Para invalidar la caché al publicar la SPA (D9)."
  value       = aws_cloudfront_distribution.this.id
}

output "spa_bucket" {
  description = "Donde el despliegue publica la SPA (D9)."
  value       = aws_s3_bucket.spa.bucket
}

output "key_value_store_arn" {
  description = "El almacén de la clave `maintenance`, que cambia maintenance.yml (D10)."
  value       = aws_cloudfront_key_value_store.maintenance.arn
}

output "public_validation_fqdn" {
  description = "El registro que valida el dominio público en ACM. El cómputo lo usa también para el certificado del ALB, que cubre ese nombre (D1)."
  value       = aws_route53_record.public_validation.fqdn
}
