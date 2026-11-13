# Pruebas de los entornos (feature 004, T017, plan D13), sin AWS: los proveedores están
# simulados, así que `apply` no crea nada real. Prueban el módulo raíz, que los dos
# entornos aplican con su archivo de variables.
mock_provider "aws" {
  mock_resource "aws_secretsmanager_secret" {
    defaults = {
      arn = "arn:aws:secretsmanager:us-east-2:955519187424:secret:myplaylist/prueba"
    }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-2:955519187424:secret:rds!db-prueba", kms_key_id = "", secret_status = "active" }]
    }
  }
  mock_resource "aws_ecr_repository" {
    defaults = {
      repository_url = "955519187424.dkr.ecr.us-east-2.amazonaws.com/myplaylist"
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::955519187424:role/myplaylist-prueba"
    }
  }
  mock_resource "aws_lb" {
    defaults = {
      arn        = "arn:aws:elasticloadbalancing:us-east-2:955519187424:loadbalancer/app/myplaylist/1"
      dns_name   = "myplaylist-1.us-east-2.elb.amazonaws.com"
      zone_id    = "Z3AADJGX6KTTL2"
      arn_suffix = "app/myplaylist/1"
    }
  }
  mock_resource "aws_lb_target_group" {
    defaults = {
      arn        = "arn:aws:elasticloadbalancing:us-east-2:955519187424:targetgroup/myplaylist/1"
      arn_suffix = "targetgroup/myplaylist/1"
    }
  }
  mock_resource "aws_lb_listener" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-2:955519187424:listener/app/myplaylist/1/1"
    }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = {
      certificate_arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen"
    }
  }
  mock_resource "aws_service_discovery_service" {
    defaults = {
      arn = "arn:aws:servicediscovery:us-east-2:955519187424:service/srv-mailpit"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn                         = "arn:aws:s3:::myplaylist-prueba"
      bucket_regional_domain_name = "myplaylist-prueba.s3.us-east-2.amazonaws.com"
    }
  }
  mock_resource "aws_sns_topic" {
    defaults = {
      arn = "arn:aws:sns:us-east-2:955519187424:myplaylist-alerts"
    }
  }
  mock_resource "aws_cloudfront_key_value_store" {
    defaults = {
      arn = "arn:aws:cloudfront::955519187424:key-value-store/0a1b2c3d-4e5f-6789-abcd-ef0123456789"
    }
  }
  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::955519187424:function/myplaylist-edge"
    }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::955519187424:distribution/E2PRUEBA"
      domain_name    = "d1prueba.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }
  mock_resource "aws_sesv2_email_identity" {
    defaults = {
      arn = "arn:aws:ses:us-east-2:955519187424:identity/myplaylist.200oklabs.com"
      dkim_signing_attributes = {
        current_signing_key_length = "RSA_2048_BIT"
        signing_attributes_origin  = "AWS_SES"
        status                     = "PENDING"
        tokens                     = ["clave1", "clave2", "clave3"]
      }
    }
  }
  # El token de Redis efímero simulado tiene que pasar la validación de longitud de
  # ElastiCache.
  mock_ephemeral "aws_secretsmanager_secret_version" {
    defaults = {
      secret_string = "token-de-pruebas-de-48-caracteres-0123456789abcd"
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
  mock_data "aws_ec2_managed_prefix_list" {
    defaults = {
      id = "pl-3b927c52"
    }
  }
}

mock_provider "aws" {
  alias = "us_east_1"

  mock_resource "aws_acm_certificate_validation" {
    defaults = {
      certificate_arn = "arn:aws:acm:us-east-1:955519187424:certificate/publico"
    }
  }
}

mock_provider "random" {}
mock_provider "archive" {}

variables {
  environment = "production"
  zone_id     = "Z0639081273LJQWTITRKS"
  image_tag   = "v0.2.0-rc.1"
  alert_email = "operacion@200oklabs.com"
  # Producción no admite el borrador (T026): las pruebas usan una versión definitiva.
  data_policy_version = "2026-10"
}

# Los certificados simulados necesitan las opciones de validación de sus nombres.
override_resource {
  target = module.compute.aws_acm_certificate.origin
  values = {
    arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen"
    domain_validation_options = [
      for domain in ["origin.myplaylist.200oklabs.com", "myplaylist.200oklabs.com"] : {
        domain_name           = domain
        resource_record_name  = "_v.${domain}."
        resource_record_type  = "CNAME"
        resource_record_value = "_v.acm-validations.aws."
      }
    ]
  }
}

override_resource {
  target = module.edge.aws_acm_certificate.public
  values = {
    arn = "arn:aws:acm:us-east-1:955519187424:certificate/publico"
    domain_validation_options = [{
      domain_name           = "myplaylist.200oklabs.com"
      resource_record_name  = "_v.myplaylist.200oklabs.com."
      resource_record_type  = "CNAME"
      resource_record_value = "_v.acm-validations.aws."
    }]
  }
}

run "F004_R022_los_dos_entornos_usan_el_mismo_modulo_y_la_misma_capacidad" {
  command = plan

  # Los archivos de variables solo fijan el entorno, su zona, la etiqueta inicial y valores
  # de operación; nunca la capacidad ni la definición: lo demás sale de `environment`, en
  # este mismo módulo raíz (D13).
  assert {
    condition = var.environment == "production" && alltrue([
      for environment in ["production", "preproduction"] :
      length(setsubtract(
        flatten(regexall("(?m)^([a-z_]+)\\s*=", file("environments/${environment}.tfvars"))),
        ["environment", "zone_id", "image_tag", "data_policy_version", "canary_enabled", "canary_establishment_code"],
      )) == 0
    ])
    error_message = "Los .tfvars no cambian la capacidad ni la definición: solo el entorno, su zona, la etiqueta y valores de operación (R022)."
  }

  assert {
    condition = var.environment == "production" && (
      strcontains(file("environments/production.backend.hcl"), "key          = \"production/terraform.tfstate\"") &&
      strcontains(file("environments/preproduction.backend.hcl"), "key          = \"preproduction/terraform.tfstate\"")
    )
    error_message = "Cada entorno tiene su propio estado (D13)."
  }
}

run "F004_R022_preproduccion_usa_el_catalogo_falso_mailpit_y_su_dominio" {
  command   = apply
  state_key = "preproduction"

  variables {
    environment = "preproduction"
  }

  override_resource {
    target = module.compute.aws_acm_certificate.origin
    values = {
      arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen-pre"
      domain_validation_options = [
        for domain in ["origin.pre.myplaylist.200oklabs.com", "pre.myplaylist.200oklabs.com"] : {
          domain_name           = domain
          resource_record_name  = "_v.${domain}."
          resource_record_type  = "CNAME"
          resource_record_value = "_v.acm-validations.aws."
        }
      ]
    }
  }

  override_resource {
    target = module.edge.aws_acm_certificate.public
    values = {
      arn = "arn:aws:acm:us-east-1:955519187424:certificate/publico-pre"
      domain_validation_options = [{
        domain_name           = "pre.myplaylist.200oklabs.com"
        resource_record_name  = "_v.pre.myplaylist.200oklabs.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_v.acm-validations.aws."
      }]
    }
  }

  # Desde el módulo raíz solo se ven sus locals y las salidas de los módulos; lo de dentro
  # de cada módulo lo prueba su propio archivo.
  assert {
    condition = (
      local.app_environment == tomap({
        ENV              = "preproduction"
        EMAIL_BACKEND    = "smtp"
        PUBLIC_BASE_URL  = "https://pre.myplaylist.200oklabs.com"
        CATALOG_PROVIDER = "fake"
      }) &&
      !local.production
    )
    error_message = "La preproducción usa el catálogo falso y envía el correo por SMTP, a Mailpit (D13)."
  }

  assert {
    condition = (
      module.compute.mailpit_ports.smtp == 1025 && module.compute.mailpit_ports.http == 8025 &&
      length(regexall("(?m)^\\s*mailpit_ports\\s*=\\s*module\\.compute\\.mailpit_ports\\s*$", file("main.tf"))) == 1
    )
    error_message = "Mailpit corre, y el entorno pasa sus puertos a la red (D13)."
  }

  assert {
    condition     = local.domain == "pre.myplaylist.200oklabs.com" && local.name == "myplaylist-preproduction"
    error_message = "La preproducción tiene su dominio, pre.myplaylist.200oklabs.com (D13)."
  }

  assert {
    condition     = length(module.email) == 0
    error_message = "La preproducción no tiene el correo de SES (D13)."
  }
}

run "F004_R022_preproduccion_tiene_la_tarea_de_k6_y_produccion_no" {
  command = apply

  assert {
    condition     = output.load_test_task_definition == null && length(module.compute.mailpit_ports) == 0
    error_message = "Producción no tiene k6 ni Mailpit (D13)."
  }

  assert {
    condition     = run.F004_R022_preproduccion_usa_el_catalogo_falso_mailpit_y_su_dominio.load_test_task_definition == "myplaylist-preproduction-k6"
    error_message = "La preproducción tiene la tarea de k6 (D13, R017)."
  }
}

run "F004_R022_todos_los_recursos_llevan_la_etiqueta_environment" {
  command = plan

  # Los dos proveedores ponen la etiqueta a todo lo que crean; los módulos no la repiten.
  assert {
    condition     = length(regexall("(?m)^\\s*default_tags\\s*\\{\\s*\\n\\s*tags\\s*=\\s*local\\.tags\\s*\\n\\s*\\}", file("main.tf"))) == 2 && local.tags.environment == "production"
    error_message = "Los dos proveedores, el de us-east-2 y el de us-east-1, etiquetan todo con environment (R022)."
  }
}

run "F004_R006_redis_recibe_el_token_de_su_secreto_por_solo_escritura" {
  command = plan

  # Un valor efímero no se puede leer en una aserción: se comprueba cómo está cableado.
  assert {
    condition = var.environment == "production" && (
      length(regexall("(?m)^\\s*secret_id\\s*=\\s*module\\.secrets\\.secret_arns\\[\"redis-auth-token\"\\]\\s*$", file("main.tf"))) == 1 &&
      length(regexall("(?m)^\\s*redis_auth_token\\s*=\\s*ephemeral\\.aws_secretsmanager_secret_version\\.redis_auth_token\\.secret_string\\s*$", file("main.tf"))) == 1 &&
      length(regexall("(?m)^\\s*auth_token_wo\\s*=\\s*var\\.redis_auth_token\\s*$", file("modules/data/redis.tf"))) == 1
    )
    error_message = "El token de Redis se lee de su secreto con un recurso efímero y llega a ElastiCache por solo escritura (D6)."
  }
}

run "F004_R008_solo_produccion_tiene_el_correo_de_ses" {
  command = apply

  assert {
    condition = (
      length(module.email) == 1 &&
      local.app_environment["EMAIL_BACKEND"] == "ses" &&
      local.app_environment["EMAIL_FROM"] == "MyPlaylist <no-responder@myplaylist.200oklabs.com>" &&
      local.app_environment["CATALOG_PROVIDER"] == "youtube" &&
      length(regexall("(?m)^\\s*email_identity_arn\\s*=\\s*local\\.production \\? module\\.email\\[0\\]\\.identity_arn : null\\s*$", file("main.tf"))) == 2
    )
    error_message = "Producción compone el correo de SES y pasa su identidad y su remitente al cómputo (D14)."
  }

  assert {
    condition     = run.F004_R022_preproduccion_usa_el_catalogo_falso_mailpit_y_su_dominio.canary_name == "myplaylist-pre"
    error_message = "La preproducción se aplicó con su propio estado."
  }
}

run "F004_R003_el_computo_recibe_el_registro_de_validacion_del_borde" {
  command = apply

  assert {
    condition = (
      module.edge.public_validation_fqdn != "" &&
      length(regexall("(?m)^\\s*public_validation_fqdn\\s*=\\s*module\\.edge\\.public_validation_fqdn\\s*$", file("main.tf"))) == 1
    )
    error_message = "El certificado del ALB espera el registro de validación del dominio público, que crea el borde (D1)."
  }
}

run "F004_R016_el_computo_recibe_los_grupos_de_la_observabilidad" {
  command = apply

  assert {
    condition = (
      toset(keys(module.observability.log_groups)) == toset(["api", "worker", "realtime", "migrate"]) &&
      length(regexall("(?m)^\\s*log_groups\\s*=\\s*module\\.observability\\.log_groups\\s*$", file("main.tf"))) == 1 &&
      length(regexall("(?m)^\\s*depends_on\\s*=.*module\\.(compute|observability)", file("main.tf"))) == 0
    )
    error_message = "El cómputo usa los grupos de 30 días de la observabilidad, sin depends_on entre los dos: las alarmas dependen del cómputo (R016)."
  }
}

run "F004_R006_computo_y_borde_se_aplican_despues_de_los_secretos" {
  command = plan

  # Cada bloque `module` de main.tf, por separado: el texto hasta el siguiente.
  assert {
    condition = var.environment == "production" && alltrue([
      for module_name in ["compute", "edge"] :
      length(regexall("(?m)^\\s*depends_on\\s*=\\s*\\[module\\.secrets\\]\\s*$", one([for block in split("\nmodule \"", file("main.tf")) : block if startswith(block, "${module_name}\"")]))) == 1
    ])
    error_message = "El cómputo y el borde esperan al módulo de secretos, para leer la cabecera ya con versión (D6)."
  }
}

run "F004_R013_un_entorno_nuevo_arranca_con_el_canario_parado" {
  command = plan

  assert {
    condition     = !var.canary_enabled && var.canary_establishment_code == ""
    error_message = "Un entorno nuevo no arranca el canario hasta que exista su establecimiento de prueba (T016, T018)."
  }
}

run "F004_R013_el_canario_no_arranca_sin_establecimiento_de_prueba" {
  command = plan

  variables {
    canary_enabled = true
  }

  expect_failures = [var.canary_establishment_code]
}

run "F004_R007_produccion_no_se_aplica_con_la_politica_en_borrador" {
  command = plan

  variables {
    data_policy_version = "0000-borrador"
  }

  expect_failures = [var.data_policy_version]
}
