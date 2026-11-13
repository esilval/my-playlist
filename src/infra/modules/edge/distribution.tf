# La distribución (D1): el único origen público. /api/* y /socket.io/* van al ALB por
# HTTPS, sin caché; lo demás, al bucket de la SPA.
locals {
  spa_origin = "spa"
  alb_origin = "alb"

  # Las políticas de caché gestionadas de AWS: sus identificadores son fijos y los mismos en
  # todas las cuentas.
  cache_policy = {
    disabled  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # Managed-CachingDisabled
    optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
  }
}

# Al ALB le llega todo lo del visitante (cookies, cabeceras y la cadena de consulta), y
# además CloudFront-Viewer-Address, de donde la API toma la IP en los 401 y 403 (D11, R020).
# El certificado del ALB cubre también el dominio público, porque Host llega tal cual (D1).
resource "aws_cloudfront_origin_request_policy" "alb" {
  name    = "${var.name}-alb"
  comment = "Todo lo del visitante y CloudFront-Viewer-Address (D1, D11)"

  cookies_config {
    cookie_behavior = "all"
  }

  headers_config {
    header_behavior = "allViewerAndWhitelistCloudFront"

    headers {
      items = ["CloudFront-Viewer-Address"]
    }
  }

  query_strings_config {
    query_string_behavior = "all"
  }
}

# El valor de la cabecera queda en el estado: la configuración del origen no tiene atributo
# de solo escritura (excepción aceptada en D6). Es el mismo secreto que lee el cómputo.
data "aws_secretsmanager_secret_version" "origin_header" {
  secret_id = var.origin_header_secret_arn
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  comment             = var.name
  aliases             = [var.domain]
  default_root_object = "index.html"
  # Norteamérica y Europa: Bogotá se sirve desde los puntos de Norteamérica.
  price_class = "PriceClass_100"
  # Sin registros de acceso: llevarían la cadena de consulta con el texto buscado (R016).
  # Sin respuestas de error personalizadas: convertirían los 404 y 403 de la API en
  # index.html (R013 de 001). Las rutas de la SPA las reescribe la función.

  origin {
    origin_id                = local.spa_origin
    domain_name              = aws_s3_bucket.spa.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.spa.id
  }

  origin {
    origin_id   = local.alb_origin
    domain_name = var.origin_domain

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = var.origin_header_name
      value = data.aws_secretsmanager_secret_version.origin_header.secret_string
    }
  }

  default_cache_behavior {
    target_origin_id       = local.spa_origin
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = local.cache_policy.optimized
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.edge.arn
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = ["/api/*", "/socket.io/*"]

    content {
      path_pattern             = ordered_cache_behavior.value
      target_origin_id         = local.alb_origin
      viewer_protocol_policy   = "redirect-to-https"
      allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods           = ["GET", "HEAD"]
      cache_policy_id          = local.cache_policy.disabled
      origin_request_policy_id = aws_cloudfront_origin_request_policy.alb.id
      compress                 = true

      function_association {
        event_type   = "viewer-request"
        function_arn = aws_cloudfront_function.edge.arn
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.public.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

# El dominio público apunta a la distribución, en IPv4 e IPv6.
resource "aws_route53_record" "public" {
  for_each = toset(["A", "AAAA"])

  zone_id = var.zone_id
  name    = var.domain
  type    = each.key

  alias {
    name                   = aws_cloudfront_distribution.this.domain_name
    zone_id                = aws_cloudfront_distribution.this.hosted_zone_id
    evaluate_target_health = false
  }
}
