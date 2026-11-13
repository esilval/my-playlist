# El certificado del dominio público, en us-east-1 porque lo usa CloudFront (D1).
resource "aws_acm_certificate" "public" {
  provider = aws.us_east_1

  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Un certificado de un solo nombre tiene una sola opción de validación. Este registro valida
# también el certificado del ALB, que cubre el mismo nombre: el cómputo recibe su nombre
# (`public_validation_fqdn`) y no crea otro.
locals {
  public_validation = one(aws_acm_certificate.public.domain_validation_options)
}

resource "aws_route53_record" "public_validation" {
  zone_id         = var.zone_id
  name            = local.public_validation.resource_record_name
  type            = local.public_validation.resource_record_type
  records         = [local.public_validation.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "public" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.public.arn
  validation_record_fqdns = [aws_route53_record.public_validation.fqdn]
}
