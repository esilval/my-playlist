# Pruebas del cómputo (feature 004, T013, plan D1, D3, D6, D8), sin AWS: el proveedor está
# simulado, así que `apply` no crea nada real.
mock_provider "aws" {
  mock_resource "aws_ecr_repository" {
    defaults = {
      repository_url = "955519187424.dkr.ecr.us-east-2.amazonaws.com/myplaylist-production"
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::955519187424:role/myplaylist-production-tarea"
    }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen"
      domain_validation_options = [
        {
          domain_name           = "origin.myplaylist.200oklabs.com"
          resource_record_name  = "_abc.origin.myplaylist.200oklabs.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_def.acm-validations.aws."
        },
        {
          domain_name           = "myplaylist.200oklabs.com"
          resource_record_name  = "_ghi.myplaylist.200oklabs.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_jkl.acm-validations.aws."
        },
      ]
    }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = {
      certificate_arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen"
    }
  }
  mock_resource "aws_lb" {
    defaults = {
      arn        = "arn:aws:elasticloadbalancing:us-east-2:955519187424:loadbalancer/app/myplaylist-production/1"
      dns_name   = "myplaylist-production-1.us-east-2.elb.amazonaws.com"
      zone_id    = "Z3AADJGX6KTTL2"
      arn_suffix = "app/myplaylist-production/1"
    }
  }
  mock_resource "aws_lb_target_group" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-2:955519187424:targetgroup/myplaylist-production/1"
    }
  }
  mock_resource "aws_lb_listener" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-2:955519187424:listener/app/myplaylist-production/1/1"
    }
  }
  mock_resource "aws_service_discovery_service" {
    defaults = {
      arn = "arn:aws:servicediscovery:us-east-2:955519187424:service/srv-mailpit"
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

variables {
  name                    = "myplaylist-production"
  production              = true
  domain                  = "myplaylist.200oklabs.com"
  zone_id                 = "Z0639081273LJQWTITRKS"
  vpc_id                  = "vpc-prueba"
  public_subnet_ids       = ["subnet-publica-a", "subnet-publica-b"]
  alb_security_group_id   = "sg-alb"
  tasks_security_group_id = "sg-tareas"
  public_validation_fqdn  = "_ghi.myplaylist.200oklabs.com"
  email_identity_arn      = "arn:aws:ses:us-east-2:955519187424:identity/myplaylist.200oklabs.com"
  master_user_secret_arn  = "arn:aws:secretsmanager:us-east-2:955519187424:secret:rds!db-prueba"
  image_tag               = "v0.2.0-rc.1"
  database                = { host = "db.prueba", port = 5432, name = "myplaylist" }
  redis                   = { host = "redis.prueba", port = 6379 }
  secret_arns = {
    for name in [
      "realtime-ticket-secret", "device-token-secret", "redis-auth-token", "database-api-password",
      "database-worker-password", "cloudfront-origin-header", "youtube-api-key",
    ] : name => "arn:aws:secretsmanager:us-east-2:955519187424:secret:myplaylist/production/${name}"
  }
  log_groups = {
    for task in ["api", "worker", "realtime", "migrate"] : task => "/myplaylist/production/${task}"
  }
  app_environment = {
    ENV                 = "production"
    EMAIL_BACKEND       = "ses"
    EMAIL_FROM          = "MyPlaylist <no-responder@myplaylist.200oklabs.com>"
    PUBLIC_BASE_URL     = "https://myplaylist.200oklabs.com"
    CATALOG_PROVIDER    = "youtube"
    DATA_POLICY_VERSION = "2026-10"
  }
}

run "F004_R009_cada_servicio_tiene_dos_tareas_o_mas_en_dos_zonas" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition     = keys(aws_ecs_service.this) == ["api", "realtime", "worker"]
    error_message = "Hay tres servicios: la API, el trabajador y el tiempo real (D3). La migración no es un servicio."
  }

  assert {
    condition     = alltrue([for service in aws_ecs_service.this : service.desired_count >= 2 && service.launch_type == "FARGATE"])
    error_message = "Cada servicio arranca con al menos dos tareas de Fargate (Q3)."
  }

  assert {
    condition = alltrue([
      for service in aws_ecs_service.this :
      toset(one(service.network_configuration).subnets) == toset(["subnet-publica-a", "subnet-publica-b"]) &&
      service.availability_zone_rebalancing == "ENABLED"
    ])
    error_message = "Cada servicio reparte sus tareas entre las subredes de las dos zonas y las reequilibra si una zona cae (R009)."
  }

  assert {
    condition = (
      aws_appautoscaling_target.this["api"].min_capacity == 2 && aws_appautoscaling_target.this["api"].max_capacity == 6 &&
      aws_appautoscaling_target.this["realtime"].min_capacity == 2 && aws_appautoscaling_target.this["realtime"].max_capacity == 4 &&
      !contains(keys(aws_appautoscaling_target.this), "worker")
    )
    error_message = "La API escala de 2 a 6 tareas y el tiempo real de 2 a 4; el trabajador tiene 2 fijas (D3)."
  }

  assert {
    condition = alltrue([
      for policy in aws_appautoscaling_policy.cpu :
      one(policy.target_tracking_scaling_policy_configuration).target_value == 60
    ])
    error_message = "El autoescalado sigue el 60 % de CPU (D3)."
  }
}

run "F004_R009_un_servicio_con_una_sola_tarea_no_se_admite" {
  command = plan

  module {
    source = "./modules/compute"
  }

  variables {
    capacity = {
      api      = { cpu = 2048, memory = 4096, min = 1, max = 6 }
      worker   = { cpu = 256, memory = 512, min = 2, max = 2 }
      realtime = { cpu = 512, memory = 1024, min = 2, max = 4 }
    }
  }

  expect_failures = [var.capacity]
}

run "F004_R005_los_servicios_tienen_circuit_breaker_con_vuelta_atras" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition = alltrue([
      for service in aws_ecs_service.this :
      one(service.deployment_circuit_breaker).enable && one(service.deployment_circuit_breaker).rollback
    ])
    error_message = "Si las tareas nuevas no arrancan, ECS vuelve solo a la revisión anterior (R005)."
  }

  assert {
    condition     = alltrue([for service in aws_ecs_service.this : service.deployment_minimum_healthy_percent == 100])
    error_message = "Durante un despliegue siguen atendiendo todas las tareas de la revisión anterior (R005)."
  }

  assert {
    condition = alltrue([
      for group in aws_lb_target_group.this :
      one(group.health_check).healthy_threshold == 2 && one(group.health_check).interval == 10
    ])
    error_message = "Una tarea recibe tráfico tras superar dos comprobaciones seguidas, cada 10 s (D3)."
  }

  assert {
    condition = (
      one(aws_lb_target_group.this["api"].health_check).path == "/api/health" &&
      one(aws_lb_target_group.this["realtime"].health_check).path == "/health"
    )
    error_message = "Cada grupo comprueba la ruta de salud de su servicio (D3)."
  }
}

run "F004_R004_la_api_no_migra_y_existe_la_tarea_de_migracion" {
  command = apply

  module {
    source = "./modules/compute"
  }

  # La API usa el mando de la imagen, que no migra (lo prueba test_dockerfile.py).
  assert {
    condition     = !can(jsondecode(aws_ecs_task_definition.this["api"].container_definitions)[0].command[0])
    error_message = "La API arranca con el mando de la imagen, sin migrar (D8)."
  }

  assert {
    condition = alltrue([
      for task in ["api", "worker", "realtime"] :
      !strcontains(jsonencode(try(jsondecode(aws_ecs_task_definition.this[task].container_definitions)[0].command, [])), "alembic")
    ])
    error_message = "Ningún servicio migra al arrancar: con varias tareas, migrarían a la vez (R004)."
  }

  assert {
    condition = (
      strcontains(join(" ", jsondecode(aws_ecs_task_definition.this["migrate"].container_definitions)[0].command), "alembic upgrade head && exec python -m app.ops.db_users") &&
      !contains(keys(aws_ecs_service.this), "migrate")
    )
    error_message = "La migración es una tarea de un solo uso que migra y crea los usuarios de servicio (D5, D8)."
  }

  assert {
    condition = alltrue([
      for task, definition in aws_ecs_task_definition.this :
      strcontains(jsonencode(jsondecode(definition.container_definitions)[0].secrets), "rds!db-prueba") == (task == "migrate")
    ])
    error_message = "Solo la tarea de migración recibe el usuario maestro de RDS (D5)."
  }
}

run "F004_R006_los_secretos_llegan_como_secrets_y_no_como_environment" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition = alltrue(flatten([
      for definition in aws_ecs_task_definition.this : [
        for secret in jsondecode(definition.container_definitions)[0].secrets :
        startswith(secret.valueFrom, "arn:aws:secretsmanager:us-east-2:955519187424:secret:")
      ]
    ]))
    error_message = "Cada secreto llega por su ARN de Secrets Manager, nunca por su valor (D6)."
  }

  assert {
    condition = alltrue(flatten([
      for definition in aws_ecs_task_definition.this : [
        for variable in jsondecode(definition.container_definitions)[0].environment :
        !contains([
          "REALTIME_TICKET_SECRET", "DEVICE_TOKEN_SECRET", "YOUTUBE_API_KEY", "REDIS_AUTH_TOKEN",
          "DATABASE_PASSWORD", "DATABASE_API_PASSWORD", "DATABASE_WORKER_PASSWORD", "DATABASE_URL", "REDIS_URL",
        ], variable.name) && !startswith(variable.value, "arn:aws:secretsmanager:")
      ]
    ]))
    error_message = "Ningún secreto va en environment, que se ve en la consola y en la API de ECS (R006)."
  }

  assert {
    condition = (
      [for secret in jsondecode(aws_ecs_task_definition.this["api"].container_definitions)[0].secrets : secret.name] ==
      ["DATABASE_PASSWORD", "DEVICE_TOKEN_SECRET", "REALTIME_TICKET_SECRET", "REDIS_AUTH_TOKEN", "YOUTUBE_API_KEY"] &&
      [for secret in jsondecode(aws_ecs_task_definition.this["realtime"].container_definitions)[0].secrets : secret.name] ==
      ["REALTIME_TICKET_SECRET", "REDIS_AUTH_TOKEN"]
    )
    error_message = "Cada tarea recibe solo los secretos que usa (D6)."
  }

  assert {
    condition = (
      contains(data.aws_iam_policy_document.read_secrets["api"].statement[0].resources, var.secret_arns["database-api-password"]) &&
      !contains(data.aws_iam_policy_document.read_secrets["api"].statement[0].resources, var.secret_arns["database-worker-password"]) &&
      !contains(data.aws_iam_policy_document.read_secrets["api"].statement[0].resources, var.master_user_secret_arn) &&
      contains(data.aws_iam_policy_document.read_secrets["migrate"].statement[0].resources, var.master_user_secret_arn)
    )
    error_message = "El rol de ejecución de cada tarea solo lee sus secretos: el maestro, solo la migración (D5, D6)."
  }
}

# La imagen de Node no tiene app.ops.env: el mando compone REDIS_URL con TLS y el token,
# que ECS sustituye al arrancar. Un `redis://` sin TLS, o sin el token, solo se vería en AWS.
run "F004_R006_el_tiempo_real_compone_redis_url_con_tls_y_el_token_al_arrancar" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition = (
      strcontains(join(" ", jsondecode(aws_ecs_task_definition.this["realtime"].container_definitions)[0].command), "export REDIS_URL=\"rediss://:$${REDIS_AUTH_TOKEN}@$${REDIS_HOST}:$${REDIS_PORT}/0\" && exec node dist/server.js") &&
      !contains([for variable in jsondecode(aws_ecs_task_definition.this["realtime"].container_definitions)[0].environment : variable.name], "REDIS_URL")
    )
    error_message = "El tiempo real compone rediss://:<token>@<anfitrión> en su mando, con el token de secrets (D4, D6)."
  }
}

run "F004_R006_un_secreto_en_app_environment_no_se_admite" {
  command = plan

  module {
    source = "./modules/compute"
  }

  variables {
    app_environment = {
      ENV                    = "production"
      REALTIME_TICKET_SECRET = "en-claro"
    }
  }

  expect_failures = [var.app_environment]
}

run "F004_R009_el_alb_solo_admite_cloudfront_y_su_cabecera" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition     = aws_lb.this.security_groups == toset(["sg-alb"]) && !aws_lb.this.internal && aws_lb.this.drop_invalid_header_fields
    error_message = "El ALB usa solo el grupo que admite a CloudFront (D1)."
  }

  assert {
    condition     = one(aws_lb_listener.https.default_action).type == "fixed-response" && one(one(aws_lb_listener.https.default_action).fixed_response).status_code == "403"
    error_message = "Lo que no casa con ninguna regla recibe 403 (D1)."
  }

  assert {
    condition = alltrue([
      for rule in aws_lb_listener_rule.this : anytrue([
        for condition in rule.condition :
        length(condition.http_header) == 1 &&
        one(condition.http_header).http_header_name == "X-Origin-Verify" &&
        one(condition.http_header).values == toset([data.aws_secretsmanager_secret_version.origin_header.secret_string])
      ])
    ])
    error_message = "Cada regla exige la cabecera secreta de CloudFront, con el valor de su secreto (D1, D6)."
  }

  assert {
    condition     = data.aws_secretsmanager_secret_version.origin_header.secret_id == var.secret_arns["cloudfront-origin-header"]
    error_message = "El valor de la cabecera sale del secreto que genera el módulo de secretos (D6)."
  }

  assert {
    condition = (
      one(aws_lb_listener_rule.this["api"].action).target_group_arn == aws_lb_target_group.this["api"].arn &&
      one(aws_lb_listener_rule.this["realtime"].action).target_group_arn == aws_lb_target_group.this["realtime"].arn &&
      anytrue([for condition in aws_lb_listener_rule.this["api"].condition : length(condition.path_pattern) == 1 && one(condition.path_pattern).values == toset(["/api/*"])]) &&
      anytrue([for condition in aws_lb_listener_rule.this["realtime"].condition : length(condition.path_pattern) == 1 && one(condition.path_pattern).values == toset(["/socket.io/*"])])
    )
    error_message = "/api/* va a la API y /socket.io/* al tiempo real (D1)."
  }
}

run "F004_R003_el_alb_solo_escucha_https_con_el_certificado_del_origen" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition = (
      aws_lb_listener.https.port == 443 &&
      aws_lb_listener.https.protocol == "HTTPS" &&
      aws_lb_listener.https.ssl_policy == "ELBSecurityPolicy-TLS13-1-2-2021-06"
    )
    error_message = "El ALB escucha solo en 443, por HTTPS y con TLS 1.2 como mínimo (D1)."
  }

  assert {
    condition = (
      aws_acm_certificate.origin.domain_name == "origin.myplaylist.200oklabs.com" &&
      aws_acm_certificate.origin.validation_method == "DNS" &&
      aws_lb_listener.https.certificate_arn == aws_acm_certificate_validation.origin.certificate_arn
    )
    error_message = "El listener usa el certificado de origin.<dominio>, validado por DNS (D1)."
  }

  # CloudFront reenvía Host y comprueba el certificado del origen contra el dominio público.
  assert {
    condition     = aws_acm_certificate.origin.subject_alternative_names == toset(["myplaylist.200oklabs.com"])
    error_message = "El certificado del ALB cubre también el dominio público, que llega en Host (D1, D11)."
  }

  assert {
    condition = (
      aws_route53_record.origin_validation.zone_id == "Z0639081273LJQWTITRKS" &&
      aws_route53_record.origin_validation.name == "_abc.origin.myplaylist.200oklabs.com."
    )
    error_message = "El registro de validación de origin.<dominio> está en la zona del dominio (D1)."
  }

  # El del dominio público lo crea el borde; aquí solo se espera (un solo dueño del registro).
  assert {
    condition     = aws_acm_certificate_validation.origin.validation_record_fqdns == toset([aws_route53_record.origin_validation.fqdn, "_ghi.myplaylist.200oklabs.com"])
    error_message = "La validación espera el registro de origin.<dominio> y el del dominio público, que es del borde (D1)."
  }

  assert {
    condition = (
      aws_route53_record.origin.name == "origin.myplaylist.200oklabs.com" &&
      aws_route53_record.origin.type == "A" &&
      one(aws_route53_record.origin.alias).name == aws_lb.this.dns_name &&
      one(aws_route53_record.origin.alias).zone_id == aws_lb.this.zone_id
    )
    error_message = "origin.<dominio> es un alias del ALB (D1)."
  }
}

run "F004_R008_las_tareas_fijan_aws_region_us_east_2" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition = alltrue([
      for definition in aws_ecs_task_definition.this :
      contains(jsondecode(definition.container_definitions)[0].environment, { name = "AWS_REGION", value = "us-east-2" }) &&
      jsondecode(definition.container_definitions)[0].logConfiguration.options["awslogs-region"] == "us-east-2"
    ])
    error_message = "Todas las tareas fijan AWS_REGION=us-east-2, la región de SES (D6, D14, ADR-0019)."
  }

  # Solo el trabajador envía correo, y solo desde el dominio (D14).
  assert {
    condition     = length(aws_iam_role_policy.send_email) == 1 && aws_iam_role_policy.send_email[0].role == aws_iam_role.task["worker"].id
    error_message = "Solo el trabajador, que es quien envía el correo, puede usar SES (D14)."
  }

  assert {
    condition = (
      toset(data.aws_iam_policy_document.send_email[0].statement[0].actions) == toset(["ses:SendEmail"]) &&
      toset(data.aws_iam_policy_document.send_email[0].statement[0].resources) == toset(["arn:aws:ses:us-east-2:955519187424:identity/*"])
    )
    error_message = "El trabajador solo puede enviar correo, con las identidades de la cuenta en us-east-2: en el sandbox, SES comprueba también la del destinatario (D14)."
  }

  assert {
    condition     = toset(one(data.aws_iam_policy_document.send_email[0].statement[0].condition).values) == toset(["*@myplaylist.200oklabs.com"])
    error_message = "El trabajador solo envía como el dominio (D14)."
  }
}

run "F004_R001_ecr_tiene_etiquetas_inmutables" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition = alltrue([
      for repository in aws_ecr_repository.this :
      repository.image_tag_mutability == "IMMUTABLE" && one(repository.image_scanning_configuration).scan_on_push && !repository.force_delete
    ])
    error_message = "Una etiqueta de ECR no se puede volver a subir con otra imagen, y producción no borra las suyas (R001)."
  }

  assert {
    condition = alltrue([
      for definition in aws_ecs_task_definition.this :
      endswith(jsondecode(definition.container_definitions)[0].image, ":v0.2.0-rc.1")
    ])
    error_message = "Las tareas usan la imagen de la etiqueta pedida (R001)."
  }
}

run "F004_R022_la_preproduccion_usa_el_catalogo_falso_y_borra_sus_imagenes" {
  command = apply
  # Un estado propio: la preproducción es otro entorno, no un cambio del de producción.
  state_key = "preproduction"

  module {
    source = "./modules/compute"
  }

  variables {
    name               = "myplaylist-preproduction"
    production         = false
    domain             = "pre.myplaylist.200oklabs.com"
    email_identity_arn = null
    log_groups = {
      for task in ["api", "worker", "realtime", "migrate", "mailpit", "k6"] : task => "/myplaylist/preproduction/${task}"
    }
    app_environment = {
      ENV              = "preproduction"
      EMAIL_BACKEND    = "smtp"
      PUBLIC_BASE_URL  = "https://pre.myplaylist.200oklabs.com"
      CATALOG_PROVIDER = "fake"
    }
  }

  override_resource {
    target = aws_acm_certificate.origin
    values = {
      arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen-pre"
      domain_validation_options = [
        for domain in ["origin.pre.myplaylist.200oklabs.com", "pre.myplaylist.200oklabs.com"] : {
          domain_name           = domain
          resource_record_name  = "_abc.${domain}."
          resource_record_type  = "CNAME"
          resource_record_value = "_def.acm-validations.aws."
        }
      ]
    }
  }

  assert {
    condition     = alltrue([for repository in aws_ecr_repository.this : repository.force_delete])
    error_message = "Destruir la preproducción borra también sus imágenes (R022)."
  }

  assert {
    condition     = length(aws_iam_role_policy.send_email) == 0
    error_message = "Sin identidad de SES, como en preproducción, ninguna tarea puede enviar con SES (D13, D14)."
  }

  assert {
    condition = alltrue([
      for definition in aws_ecs_task_definition.this :
      !strcontains(jsonencode(jsondecode(definition.container_definitions)[0].secrets), "youtube-api-key")
    ])
    error_message = "Con el catálogo falso ninguna tarea pide la clave de YouTube, que no tiene valor (D6)."
  }

  assert {
    condition     = aws_acm_certificate.origin.domain_name == "origin.pre.myplaylist.200oklabs.com"
    error_message = "La preproducción tiene su propio origen (D1)."
  }

  assert {
    condition     = alltrue([for group in aws_lb_target_group.this : length(group.name) <= 32])
    error_message = "Los nombres de los grupos de destino caben en 32 caracteres también en preproducción."
  }
}

# T029 (D13): solo la preproducción tiene Mailpit y la tarea de k6.
run "F004_R022_preproduccion_tiene_mailpit_con_dns_privado" {
  command   = apply
  state_key = "preproduction"

  module {
    source = "./modules/compute"
  }

  variables {
    name               = "myplaylist-preproduction"
    production         = false
    domain             = "pre.myplaylist.200oklabs.com"
    email_identity_arn = null
    log_groups = {
      for task in ["api", "worker", "realtime", "migrate", "mailpit", "k6"] : task => "/myplaylist/preproduction/${task}"
    }
    app_environment = {
      ENV              = "preproduction"
      EMAIL_BACKEND    = "smtp"
      PUBLIC_BASE_URL  = "https://pre.myplaylist.200oklabs.com"
      CATALOG_PROVIDER = "fake"
    }
  }

  override_resource {
    target = aws_acm_certificate.origin
    values = {
      arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen-pre"
      domain_validation_options = [
        for domain in ["origin.pre.myplaylist.200oklabs.com", "pre.myplaylist.200oklabs.com"] : {
          domain_name           = domain
          resource_record_name  = "_abc.${domain}."
          resource_record_type  = "CNAME"
          resource_record_value = "_def.acm-validations.aws."
        }
      ]
    }
  }

  assert {
    condition = (
      aws_service_discovery_private_dns_namespace.this[0].name == "myplaylist-preproduction.internal" &&
      aws_service_discovery_private_dns_namespace.this[0].vpc == "vpc-prueba" &&
      aws_service_discovery_service.mailpit[0].name == "mailpit"
    )
    error_message = "Mailpit tiene un nombre en una zona DNS privada de la VPC, que solo se ve desde dentro (D13)."
  }

  assert {
    condition = (
      aws_ecs_service.mailpit[0].desired_count == 1 &&
      one(aws_ecs_service.mailpit[0].service_registries).registry_arn == aws_service_discovery_service.mailpit[0].arn &&
      one(aws_ecs_service.mailpit[0].network_configuration).security_groups == toset(["sg-tareas"]) &&
      length(aws_ecs_service.mailpit[0].load_balancer) == 0 &&
      aws_ecs_service.mailpit[0].propagate_tags == "SERVICE"
    )
    error_message = "Mailpit es un servicio de una tarea, registrado en esa zona, con el grupo de las tareas y sin pasar por el ALB (D13)."
  }

  assert {
    condition = (
      jsondecode(aws_ecs_task_definition.tools["mailpit"].container_definitions)[0].image == "axllent/mailpit:v1.31.6" &&
      toset([for mapping in jsondecode(aws_ecs_task_definition.tools["mailpit"].container_definitions)[0].portMappings : mapping.containerPort]) == toset([1025, 8025])
    )
    error_message = "Mailpit en la versión del compose, con SMTP en 1025 y su API en 8025 (D13)."
  }

  assert {
    condition = alltrue([
      for task in ["api", "worker"] :
      contains(jsondecode(aws_ecs_task_definition.this[task].container_definitions)[0].environment, { name = "SMTP_HOST", value = "mailpit.myplaylist-preproduction.internal" }) &&
      contains(jsondecode(aws_ecs_task_definition.this[task].container_definitions)[0].environment, { name = "SMTP_PORT", value = "1025" })
    ])
    error_message = "La API y el trabajador envían el correo a Mailpit por su nombre (D13)."
  }

  assert {
    condition     = output.mailpit_ports.smtp == 1025 && output.mailpit_ports.http == 8025 && length(output.mailpit_ports) == 2
    error_message = "El cómputo da al módulo de red los puertos que tiene que abrir entre las tareas (D13)."
  }
}

run "F004_R017_preproduccion_tiene_la_definicion_de_k6" {
  command   = apply
  state_key = "preproduction"

  module {
    source = "./modules/compute"
  }

  variables {
    name               = "myplaylist-preproduction"
    production         = false
    domain             = "pre.myplaylist.200oklabs.com"
    email_identity_arn = null
    log_groups = {
      for task in ["api", "worker", "realtime", "migrate", "mailpit", "k6"] : task => "/myplaylist/preproduction/${task}"
    }
    app_environment = {
      ENV              = "preproduction"
      EMAIL_BACKEND    = "smtp"
      PUBLIC_BASE_URL  = "https://pre.myplaylist.200oklabs.com"
      CATALOG_PROVIDER = "fake"
    }
  }

  override_resource {
    target = aws_acm_certificate.origin
    values = {
      arn = "arn:aws:acm:us-east-2:955519187424:certificate/origen-pre"
      domain_validation_options = [
        for domain in ["origin.pre.myplaylist.200oklabs.com", "pre.myplaylist.200oklabs.com"] : {
          domain_name           = domain
          resource_record_name  = "_abc.${domain}."
          resource_record_type  = "CNAME"
          resource_record_value = "_def.acm-validations.aws."
        }
      ]
    }
  }

  assert {
    condition = (
      aws_ecs_task_definition.tools["k6"].cpu == "4096" &&
      aws_ecs_task_definition.tools["k6"].memory == "8192" &&
      jsondecode(aws_ecs_task_definition.tools["k6"].container_definitions)[0].image == "grafana/k6:1.4.0"
    )
    error_message = "k6 corre en una tarea de 4 vCPU y 8 GiB, con una versión fija (D13)."
  }

  assert {
    condition = (
      contains(jsondecode(aws_ecs_task_definition.tools["k6"].container_definitions)[0].environment, { name = "API_URL", value = "https://pre.myplaylist.200oklabs.com" }) &&
      contains(jsondecode(aws_ecs_task_definition.tools["k6"].container_definitions)[0].environment, { name = "MAILPIT_URL", value = "http://mailpit.myplaylist-preproduction.internal:8025" }) &&
      contains(jsondecode(aws_ecs_task_definition.tools["k6"].container_definitions)[0].environment, { name = "ESTABLISHMENTS", value = "50" })
    )
    error_message = "k6 pasa por el dominio público, como un cliente real, lee Mailpit dentro de la VPC y simula 50 establecimientos (D13, R017)."
  }

  assert {
    condition     = !contains(keys(aws_ecs_service.this), "k6") && output.load_test_task_definition == "myplaylist-preproduction-k6"
    error_message = "k6 es una tarea que se lanza para cada prueba, no un servicio (D13)."
  }

  assert {
    condition     = !can(jsondecode(aws_ecs_task_definition.tools["k6"].container_definitions)[0].secrets)
    error_message = "k6 no recibe ningún secreto (R006)."
  }
}

run "F004_R022_produccion_no_tiene_mailpit_ni_k6" {
  command = apply

  module {
    source = "./modules/compute"
  }

  assert {
    condition = (
      length(aws_ecs_task_definition.tools) == 0 &&
      length(aws_ecs_service.mailpit) == 0 &&
      length(aws_service_discovery_private_dns_namespace.this) == 0 &&
      length(aws_iam_role.tools_execution) == 0 &&
      output.load_test_task_definition == null &&
      length(output.mailpit_ports) == 0
    )
    error_message = "Producción no tiene Mailpit, k6 ni su zona DNS (D13)."
  }

  assert {
    condition = alltrue([
      for definition in aws_ecs_task_definition.this : !anytrue([
        for variable in jsondecode(definition.container_definitions)[0].environment : startswith(variable.name, "SMTP_")
      ])
    ])
    error_message = "En producción, el correo sale por SES y no hay SMTP (D14)."
  }
}
