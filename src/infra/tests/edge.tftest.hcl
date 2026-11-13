# Pruebas del borde (feature 004, T014, plan D1, D10, D11), sin AWS: los dos proveedores
# están simulados, así que `apply` no crea nada real. La función `edge` se prueba aparte,
# con `node --test` (modules/edge/functions/edge.test.js).
mock_provider "aws" {
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn                         = "arn:aws:s3:::myplaylist-production-spa-955519187424"
      bucket_regional_domain_name = "myplaylist-production-spa-955519187424.s3.us-east-2.amazonaws.com"
    }
  }
  mock_resource "aws_cloudfront_key_value_store" {
    defaults = {
      arn = "arn:aws:cloudfront::955519187424:key-value-store/0a1b2c3d-4e5f-6789-abcd-ef0123456789"
    }
  }
  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::955519187424:function/myplaylist-production-edge"
    }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::955519187424:distribution/E2PRUEBA"
      domain_name    = "d1prueba.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "955519187424"
    }
  }
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{}"
    }
  }
  mock_data "aws_secretsmanager_secret_version" {
    defaults = {
      secret_string = "cabecera-de-pruebas-de-48-caracteres-0123456789a"
    }
  }
}

mock_provider "aws" {
  alias = "us_east_1"

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:955519187424:certificate/publico"
      domain_validation_options = [{
        domain_name           = "myplaylist.200oklabs.com"
        resource_record_name  = "_ghi.myplaylist.200oklabs.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_jkl.acm-validations.aws."
      }]
    }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = {
      certificate_arn = "arn:aws:acm:us-east-1:955519187424:certificate/publico"
    }
  }
}

variables {
  name                     = "myplaylist-production"
  production               = true
  domain                   = "myplaylist.200oklabs.com"
  zone_id                  = "Z0639081273LJQWTITRKS"
  origin_domain            = "origin.myplaylist.200oklabs.com"
  origin_header_name       = "X-Origin-Verify"
  origin_header_secret_arn = "arn:aws:secretsmanager:us-east-2:955519187424:secret:myplaylist/production/cloudfront-origin-header"
}

run "F004_R003_todas_las_rutas_redirigen_http_a_https_con_tls_1_2" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.this.default_cache_behavior).viewer_protocol_policy == "redirect-to-https" &&
      alltrue([for behavior in aws_cloudfront_distribution.this.ordered_cache_behavior : behavior.viewer_protocol_policy == "redirect-to-https"])
    )
    error_message = "Toda ruta pedida por HTTP se redirige a HTTPS (R003)."
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.this.viewer_certificate).minimum_protocol_version == "TLSv1.2_2021" &&
      one(aws_cloudfront_distribution.this.viewer_certificate).ssl_support_method == "sni-only" &&
      one(aws_cloudfront_distribution.this.viewer_certificate).acm_certificate_arn == aws_acm_certificate_validation.public.certificate_arn
    )
    error_message = "HTTPS con TLS 1.2 como mínimo y el certificado validado del dominio (R003)."
  }

  # El certificado sale del proveedor de us-east-1, el único que admite CloudFront: su ARN
  # simulado es de esa región.
  assert {
    condition = (
      aws_acm_certificate.public.domain_name == "myplaylist.200oklabs.com" &&
      aws_acm_certificate.public.validation_method == "DNS" &&
      startswith(aws_acm_certificate.public.arn, "arn:aws:acm:us-east-1:") &&
      aws_route53_record.public_validation.zone_id == "Z0639081273LJQWTITRKS"
    )
    error_message = "El certificado del dominio público está en us-east-1 y se valida por DNS en la zona (D1)."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.this.aliases == toset(["myplaylist.200oklabs.com"]) &&
      toset(keys(aws_route53_record.public)) == toset(["A", "AAAA"]) &&
      alltrue([for record in aws_route53_record.public : one(record.alias).name == aws_cloudfront_distribution.this.domain_name])
    )
    error_message = "El dominio de los QR apunta a la distribución (D1)."
  }
}

run "F004_R003_api_y_socket_io_van_al_alb_sin_cache" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = [for behavior in aws_cloudfront_distribution.this.ordered_cache_behavior : behavior.path_pattern] == ["/api/*", "/socket.io/*"]
    error_message = "/api/* y /socket.io/* tienen su propio comportamiento (D1)."
  }

  assert {
    condition = alltrue([
      for behavior in aws_cloudfront_distribution.this.ordered_cache_behavior :
      behavior.target_origin_id == "alb" &&
      behavior.cache_policy_id == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" &&
      contains(behavior.allowed_methods, "POST") && contains(behavior.allowed_methods, "DELETE")
    ])
    error_message = "Los dos van al ALB, sin caché (Managed-CachingDisabled) y con todos los métodos (D1)."
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.this.default_cache_behavior).target_origin_id == "spa" &&
      one(aws_cloudfront_distribution.this.default_cache_behavior).cache_policy_id == "658327ea-f89d-4fab-a63d-7e88639e58f6"
    )
    error_message = "Lo demás es la SPA, desde S3 y con caché (Managed-CachingOptimized) (D1)."
  }
}

run "F004_R003_cloudfront_habla_con_el_alb_por_https" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = anytrue([
      for origin in aws_cloudfront_distribution.this.origin :
      origin.origin_id == "alb" &&
      origin.domain_name == "origin.myplaylist.200oklabs.com" &&
      one(origin.custom_origin_config).origin_protocol_policy == "https-only" &&
      one(origin.custom_origin_config).origin_ssl_protocols == toset(["TLSv1.2"])
    ])
    error_message = "CloudFront llega al ALB por origin.<dominio>, solo por HTTPS y con TLS 1.2 (D1)."
  }

  # La SPA, en cambio, sale de un bucket privado que solo lee esta distribución.
  assert {
    condition = anytrue([
      for origin in aws_cloudfront_distribution.this.origin :
      origin.origin_id == "spa" && origin.origin_access_control_id == aws_cloudfront_origin_access_control.spa.id
    ])
    error_message = "El origen de la SPA usa Origin Access Control (D1)."
  }

  assert {
    condition = (
      aws_s3_bucket_public_access_block.spa.block_public_acls && aws_s3_bucket_public_access_block.spa.block_public_policy &&
      aws_s3_bucket_public_access_block.spa.ignore_public_acls && aws_s3_bucket_public_access_block.spa.restrict_public_buckets
    )
    error_message = "El bucket de la SPA no es público (D1)."
  }

  assert {
    condition     = toset(one(data.aws_iam_policy_document.spa.statement[0].condition).values) == toset([aws_cloudfront_distribution.this.arn])
    error_message = "Solo esta distribución puede leer el bucket (D1)."
  }
}

run "F004_R009_cloudfront_pone_la_cabecera_que_exige_el_alb" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = anytrue([
      for origin in aws_cloudfront_distribution.this.origin :
      origin.origin_id == "alb" && anytrue([
        for header in origin.custom_header :
        header.name == "X-Origin-Verify" && header.value == data.aws_secretsmanager_secret_version.origin_header.secret_string
      ])
    ])
    error_message = "CloudFront pone en el origen del ALB la cabecera que exigen sus reglas (D1)."
  }

  # El cómputo lee el mismo secreto para las reglas del ALB (tests/compute.tftest.hcl): el
  # entorno les pasa el mismo ARN (T017).
  assert {
    condition     = data.aws_secretsmanager_secret_version.origin_header.secret_id == var.origin_header_secret_arn
    error_message = "El valor sale del secreto cloudfront-origin-header (D6)."
  }
}

run "F004_R014_la_funcion_edge_esta_en_viewer_request_en_los_tres_comportamientos" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = alltrue([
      for behavior in concat(aws_cloudfront_distribution.this.default_cache_behavior, aws_cloudfront_distribution.this.ordered_cache_behavior) :
      length(behavior.function_association) == 1 &&
      one(behavior.function_association).event_type == "viewer-request" &&
      one(behavior.function_association).function_arn == aws_cloudfront_function.edge.arn
    ])
    error_message = "La misma función está en viewer-request en los tres comportamientos (D1, D10)."
  }

  assert {
    condition = (
      aws_cloudfront_function.edge.runtime == "cloudfront-js-2.0" &&
      aws_cloudfront_function.edge.publish &&
      aws_cloudfront_function.edge.key_value_store_associations == toset([aws_cloudfront_key_value_store.maintenance.arn])
    )
    error_message = "La función se publica con el almacén de claves del mantenimiento (D10)."
  }

  assert {
    condition = (
      strcontains(aws_cloudfront_function.edge.code, "cf.kvs(\"0a1b2c3d-4e5f-6789-abcd-ef0123456789\")") &&
      !strcontains(aws_cloudfront_function.edge.code, "__KVS_ID__")
    )
    error_message = "El código lleva el identificador del almacén (D10)."
  }

  assert {
    condition = (
      aws_cloudfrontkeyvaluestore_key.maintenance.key == "maintenance" &&
      aws_cloudfrontkeyvaluestore_key.maintenance.value == "off" &&
      aws_cloudfrontkeyvaluestore_key.maintenance.key_value_store_arn == aws_cloudfront_key_value_store.maintenance.arn
    )
    error_message = "La clave maintenance nace en off (D10)."
  }
}

run "F004_R003_la_distribucion_no_tiene_respuestas_de_error_personalizadas" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = length(aws_cloudfront_distribution.this.custom_error_response) == 0
    error_message = "Sin respuestas de error personalizadas: los 404 y 403 de la API llegan tal cual (R013 de 001)."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.this.logging_config) == 0
    error_message = "Sin registros de acceso, que llevarían el texto buscado (R016)."
  }
}

run "F004_R020_api_reenvia_cloudfront_viewer_address_al_origen" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = (
      one(aws_cloudfront_origin_request_policy.alb.headers_config).header_behavior == "allViewerAndWhitelistCloudFront" &&
      one(one(aws_cloudfront_origin_request_policy.alb.headers_config).headers).items == toset(["CloudFront-Viewer-Address"])
    )
    error_message = "Al ALB le llegan las cabeceras del visitante y CloudFront-Viewer-Address, de donde la API toma la IP (D11, R020)."
  }

  assert {
    condition = (
      one(aws_cloudfront_origin_request_policy.alb.cookies_config).cookie_behavior == "all" &&
      one(aws_cloudfront_origin_request_policy.alb.query_strings_config).query_string_behavior == "all"
    )
    error_message = "Y las cookies y la cadena de consulta (D1)."
  }

  assert {
    condition = alltrue([
      for behavior in aws_cloudfront_distribution.this.ordered_cache_behavior :
      behavior.origin_request_policy_id == aws_cloudfront_origin_request_policy.alb.id
    ])
    error_message = "/api/* y /socket.io/* usan esa política (D1)."
  }
}

run "F004_R022_la_preproduccion_borra_el_bucket_de_la_spa" {
  command   = apply
  state_key = "preproduction"

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  variables {
    name          = "myplaylist-preproduction"
    production    = false
    domain        = "pre.myplaylist.200oklabs.com"
    origin_domain = "origin.pre.myplaylist.200oklabs.com"
  }

  override_resource {
    target = aws_acm_certificate.public
    values = {
      arn = "arn:aws:acm:us-east-1:955519187424:certificate/publico-pre"
      domain_validation_options = [{
        domain_name           = "pre.myplaylist.200oklabs.com"
        resource_record_name  = "_ghi.pre.myplaylist.200oklabs.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_jkl.acm-validations.aws."
      }]
    }
  }

  assert {
    condition     = aws_s3_bucket.spa.force_destroy
    error_message = "Destruir la preproducción vacía y borra su bucket (R022)."
  }
}

# T016 (R016): la parte de CloudFront. La del ALB está en compute.tftest.hcl, con el mismo nombre.
run "F004_R016_sin_registros_de_acceso_del_alb_ni_de_cloudfront" {
  command = apply

  module {
    source = "./modules/edge"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = length(aws_cloudfront_distribution.this.logging_config) == 0
    error_message = "CloudFront no guarda registros de acceso: llevarían la cadena de consulta con el texto buscado (R016)."
  }
}
