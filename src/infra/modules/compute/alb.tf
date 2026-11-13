# El ALB (D1): público, pero su grupo solo admite a CloudFront, y solo en 443. Atiende
# `origin.<dominio>` con un certificado propio en us-east-2, y cada regla exige además la
# cabecera secreta que pone CloudFront. Sin ella, 403.
#
# El certificado cubre también el dominio público: CloudFront reenvía la cabecera Host del
# visitante (D11), y entonces comprueba el certificado del origen contra ese nombre.
locals {
  origin_domain = "origin.${var.domain}"
  # El nombre de la cabecera no es secreto; su valor sí. El módulo de borde pone el mismo.
  origin_header_name = "X-Origin-Verify"
}

resource "aws_acm_certificate" "origin" {
  domain_name               = local.origin_domain
  subject_alternative_names = [var.domain]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Este módulo solo crea el registro de validación de `origin.<dominio>`. El del dominio
# público es del módulo de borde, que lo crea para el certificado de CloudFront: ACM usa el
# mismo CNAME para un nombre en cualquier región de la cuenta, así que valida los dos
# certificados. Un solo dueño, para que destruir uno no deje sin renovación al otro.
locals {
  origin_validation = one([
    for option in aws_acm_certificate.origin.domain_validation_options : option
    if option.domain_name == local.origin_domain
  ])
}

resource "aws_route53_record" "origin_validation" {
  zone_id         = var.zone_id
  name            = local.origin_validation.resource_record_name
  type            = local.origin_validation.resource_record_type
  records         = [local.origin_validation.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "origin" {
  certificate_arn         = aws_acm_certificate.origin.arn
  validation_record_fqdns = [aws_route53_record.origin_validation.fqdn, var.public_validation_fqdn]
}

resource "aws_lb" "this" {
  name                       = var.name
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = var.public_subnet_ids
  security_groups            = [var.alb_security_group_id]
  drop_invalid_header_fields = true
  # Sin registros de acceso: llevarían la cadena de consulta con el texto buscado (D11, R016).
}

resource "aws_route53_record" "origin" {
  zone_id = var.zone_id
  name    = local.origin_domain
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = false
  }
}

# El valor de la cabecera: queda en el estado, porque la regla del listener no tiene
# atributo de solo escritura. Es la excepción aceptada en D6. El entorno (T017) aplica este
# módulo después del de secretos, para que el secreto ya tenga su versión.
data "aws_secretsmanager_secret_version" "origin_header" {
  secret_id = var.secret_arns["cloudfront-origin-header"]
}

resource "aws_lb_target_group" "this" {
  for_each = local.web_services

  # Los grupos de destino admiten 32 caracteres: `myplaylist-preproduction-realtime` no cabe.
  name                 = "${var.name}-${each.value.short_name}"
  port                 = each.value.port
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = 30

  # Dos comprobaciones seguidas, cada 10 s, para recibir tráfico (D3).
  health_check {
    path                = each.value.health_path
    matcher             = "200"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  # TLS 1.2 como mínimo, y 1.3 si el cliente lo admite (D1).
  ssl_policy      = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn = aws_acm_certificate_validation.origin.certificate_arn

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Forbidden"
      status_code  = "403"
    }
  }
}

resource "aws_lb_listener_rule" "this" {
  for_each = local.web_services

  listener_arn = aws_lb_listener.https.arn
  priority     = each.value.priority

  condition {
    path_pattern {
      values = [each.value.path]
    }
  }

  condition {
    http_header {
      http_header_name = local.origin_header_name
      values           = [data.aws_secretsmanager_secret_version.origin_header.secret_string]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this[each.key].arn
  }
}
