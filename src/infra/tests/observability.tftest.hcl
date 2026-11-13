# Pruebas de la observabilidad (feature 004, T016, plan D12, ADR-0020), sin AWS: los
# proveedores están simulados, así que `apply` no crea nada real. El guion del canario se
# prueba aparte, con `node --test` (modules/observability/canary/canary.test.js).
mock_provider "aws" {
  mock_resource "aws_sns_topic" {
    defaults = {
      arn = "arn:aws:sns:us-east-2:955519187424:myplaylist-production-alerts"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::myplaylist-production-canary-955519187424"
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::955519187424:role/myplaylist-production-canary"
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
}

mock_provider "archive" {}

variables {
  name                      = "myplaylist-production"
  environment               = "production"
  domain                    = "myplaylist.200oklabs.com"
  canary_establishment_code = "PRUEBA01"
  alert_email               = "operacion@200oklabs.com"
  cluster_name              = "myplaylist-production"
  alb_arn_suffix            = "app/myplaylist-production/1"
  target_group_arn_suffixes = {
    api      = "targetgroup/myplaylist-production-api/1"
    realtime = "targetgroup/myplaylist-production-rt/2"
  }
  email_identity_arn = "arn:aws:ses:us-east-2:955519187424:identity/myplaylist.200oklabs.com"
}

run "F004_R011_hay_una_alarma_por_umbral_de_sg1_a_sg6" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = (
      length(aws_cloudwatch_metric_alarm.metric) + length(aws_cloudwatch_metric_alarm.ratio) + 1 == 14 &&
      alltrue([
        for signal in ["SG1", "SG2", "SG3", "SG4", "SG5", "SG6"] :
        anytrue([for alarm in concat(values(aws_cloudwatch_metric_alarm.metric), values(aws_cloudwatch_metric_alarm.ratio), [aws_cloudwatch_metric_alarm.rejections]) : startswith(alarm.alarm_description, "${signal}:")])
      ])
    )
    error_message = "Hay 14 alarmas, y al menos una por cada señal de SG1 a SG6 (D12)."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].extended_statistic == "p95" &&
      aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].threshold == 2000 &&
      aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].period == 60 &&
      aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].evaluation_periods == 5 &&
      aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].datapoints_to_alarm == 5 &&
      aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].dimensions == tomap({ Route = "/api/public/establishments/{code}/search" }) &&
      aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].namespace == "MyPlaylist/production"
    )
    error_message = "SG1: la búsqueda, p95 > 2000 ms en 5 de 5 minutos, con la plantilla de la ruta (D11, D12)."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.ratio["sg1-busqueda-no-disponible"].threshold == 5 &&
      aws_cloudwatch_metric_alarm.ratio["sg2-5xx-alb"].threshold == 0.1 &&
      aws_cloudwatch_metric_alarm.ratio["sg5-fallos-reproduccion"].threshold == 2 &&
      alltrue([for alarm in aws_cloudwatch_metric_alarm.ratio : anytrue([for query in alarm.metric_query : query.expression == "100 * FILL(m1, 0) / m2"])])
    )
    error_message = "Las proporciones: 5 % de búsquedas no disponibles, 0,1 % de 5xx y 2 % de canciones fallidas (D12)."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.metric["sg2-cpu-api"].threshold == 80 &&
      aws_cloudwatch_metric_alarm.metric["sg2-cpu-api"].period * aws_cloudwatch_metric_alarm.metric["sg2-cpu-api"].evaluation_periods == 600 &&
      aws_cloudwatch_metric_alarm.metric["sg2-conexiones-rds"].threshold == 320 &&
      aws_cloudwatch_metric_alarm.metric["sg2-conexiones-rds"].dimensions == tomap({ DBInstanceIdentifier = "myplaylist-production" })
    )
    error_message = "SG2: la CPU de la API > 80 % en 10 minutos, y las conexiones a RDS > 80 % de 400 (D4, D12)."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.metric["sg4-musica-p95"].threshold == 1000 &&
      aws_cloudwatch_metric_alarm.metric["sg4-reenvio-p95"].threshold == 1000 &&
      aws_cloudwatch_metric_alarm.metric["sg4-reenvio-p95"].dimensions == tomap({ Service = "realtime" }) &&
      aws_cloudwatch_metric_alarm.metric["sg5-hueco-p99"].extended_statistic == "p99" &&
      aws_cloudwatch_metric_alarm.metric["sg5-hueco-p99"].threshold == 3000 &&
      aws_cloudwatch_metric_alarm.metric["sg5-hueco-p99"].period == 3600 &&
      aws_cloudwatch_metric_alarm.ratio["sg5-fallos-reproduccion"].threshold == 2
    )
    error_message = "SG4: la música y el reenvío, p95 > 1 s; SG5: el hueco, p99 > 3 s en una hora (D12)."
  }
}

run "F004_R012_cada_alarma_avisa_al_tema_con_la_suscripcion_por_correo" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = alltrue([
      for alarm in concat(values(aws_cloudwatch_metric_alarm.metric), values(aws_cloudwatch_metric_alarm.ratio), [aws_cloudwatch_metric_alarm.rejections]) :
      alarm.alarm_actions == toset([aws_sns_topic.alerts.arn]) && alarm.ok_actions == toset([aws_sns_topic.alerts.arn])
    ])
    error_message = "Cada alarma avisa al tema al entrar en ALARM y al volver a OK (R012)."
  }

  assert {
    condition = (
      aws_sns_topic_subscription.email.topic_arn == aws_sns_topic.alerts.arn &&
      aws_sns_topic_subscription.email.protocol == "email" &&
      aws_sns_topic_subscription.email.endpoint == "operacion@200oklabs.com"
    )
    error_message = "El tema envía un correo al responsable de operación (R012)."
  }

  assert {
    condition = anytrue([
      for statement in data.aws_iam_policy_document.alerts.statement :
      toset(statement.actions) == toset(["sns:Publish"]) && anytrue([for principal in statement.principals : toset(principal.identifiers) == toset(["cloudwatch.amazonaws.com"])])
    ])
    error_message = "La política del tema deja publicar a CloudWatch, que envía los avisos de las alarmas (R012)."
  }
}

run "F004_R013_el_canario_comprueba_cada_minuto_las_tres_rutas_en_us_east_2" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.metric["sg3-canario"].actions_enabled
    error_message = "En un entorno que atiende, SG3 avisa."
  }

  assert {
    condition = (
      one(aws_synthetics_canary.availability.schedule).expression == "rate(1 minute)" &&
      aws_synthetics_canary.availability.runtime_version == "syn-nodejs-puppeteer-18.0" &&
      aws_synthetics_canary.availability.start_canary &&
      aws_synthetics_canary.availability.handler == "canary.handler"
    )
    error_message = "Un canario cada minuto, con la versión del entorno fijada, que arranca al crearse (R013, ADR-0020)."
  }

  assert {
    condition = (
      one(aws_synthetics_canary.availability.run_config).environment_variables == tomap({
        CANARY_HOSTNAME    = "myplaylist.200oklabs.com"
        ESTABLISHMENT_CODE = "PRUEBA01"
      })
    )
    error_message = "El canario recorre el dominio público y la página del establecimiento de prueba (ADR-0020)."
  }

  # Los tres pasos y que no guarda capturas ni cuerpos los prueba canary.test.js.
  assert {
    condition = (
      aws_synthetics_canary.availability.zip_file == data.archive_file.canary.output_path &&
      anytrue([for source in data.archive_file.canary.source : source.filename == "nodejs/node_modules/canary.js" && strcontains(source.content, "\"/socket.io/health\"")])
    )
    error_message = "El zip lleva el guion del canario donde lo busca Synthetics."
  }

  assert {
    condition = (
      aws_synthetics_canary.availability.artifact_s3_location == "s3://${aws_s3_bucket.canary.bucket}/" &&
      one(one(aws_s3_bucket_lifecycle_configuration.canary.rule).expiration).days == 30 &&
      aws_synthetics_canary.availability.success_retention_period == 30 &&
      aws_synthetics_canary.availability.failure_retention_period == 30 &&
      aws_s3_bucket_public_access_block.canary.restrict_public_buckets
    )
    error_message = "Los artefactos van a un bucket privado que caduca a los 30 días (ADR-0020)."
  }

  assert {
    condition = (
      aws_synthetics_canary.availability.delete_lambda &&
      strcontains(data.archive_file.canary.output_path, sha1(file("./modules/observability/canary/canary.js")))
    )
    error_message = "Destruir el canario borra su Lambda (R022), y un cambio del guion cambia la ruta del zip, así que el canario se actualiza."
  }

  assert {
    condition     = length(aws_synthetics_canary.availability.name) <= 21 && aws_synthetics_canary.availability.name == "myplaylist-prod"
    error_message = "El nombre del canario cabe en los 21 caracteres de Synthetics."
  }
}

run "F004_R013_sg3_salta_si_el_canario_falla_o_no_hay_datos" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.metric["sg3-canario"].namespace == "CloudWatchSynthetics" &&
      aws_cloudwatch_metric_alarm.metric["sg3-canario"].metric_name == "SuccessPercent" &&
      aws_cloudwatch_metric_alarm.metric["sg3-canario"].dimensions == tomap({ CanaryName = "myplaylist-prod" }) &&
      aws_cloudwatch_metric_alarm.metric["sg3-canario"].comparison_operator == "LessThanThreshold" &&
      aws_cloudwatch_metric_alarm.metric["sg3-canario"].threshold == 100 &&
      aws_cloudwatch_metric_alarm.metric["sg3-canario"].period * aws_cloudwatch_metric_alarm.metric["sg3-canario"].evaluation_periods == 300 &&
      aws_cloudwatch_metric_alarm.metric["sg3-canario"].treat_missing_data == "breaching"
    )
    error_message = "SG3 salta si el canario falla durante 5 minutos, y también si no da datos (R013, ADR-0020)."
  }

  assert {
    condition = alltrue([
      for service, suffix in var.target_group_arn_suffixes :
      aws_cloudwatch_metric_alarm.metric["sg3-tareas-sanas-${service}"].metric_name == "HealthyHostCount" &&
      aws_cloudwatch_metric_alarm.metric["sg3-tareas-sanas-${service}"].dimensions == tomap({ TargetGroup = suffix, LoadBalancer = "app/myplaylist-production/1" }) &&
      aws_cloudwatch_metric_alarm.metric["sg3-tareas-sanas-${service}"].threshold == 1 &&
      aws_cloudwatch_metric_alarm.metric["sg3-tareas-sanas-${service}"].treat_missing_data == "breaching"
    ])
    error_message = "Y si un grupo de destino del ALB se queda sin tareas sanas (ADR-0020)."
  }
}

run "F004_R013_ninguna_alarma_usa_metricas_de_us_east_1" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = alltrue(flatten([
      [for alarm in aws_cloudwatch_metric_alarm.metric : !contains(["AWS/Route53", "AWS/CloudFront"], alarm.namespace)],
      [for alarm in aws_cloudwatch_metric_alarm.ratio : [for query in alarm.metric_query : [for metric in query.metric : !contains(["AWS/Route53", "AWS/CloudFront"], metric.namespace)]]],
    ]))
    error_message = "Ninguna alarma usa métricas de Route 53 ni de CloudFront, que solo existen en us-east-1 (D18, ADR-0020)."
  }

  assert {
    condition     = !strcontains(aws_cloudwatch_dashboard.this.dashboard_body, "AWS/Route53") && !strcontains(aws_cloudwatch_dashboard.this.dashboard_body, "AWS/CloudFront") && !strcontains(aws_cloudwatch_dashboard.this.dashboard_body, "us-east-1")
    error_message = "El panel tampoco las muestra."
  }
}

run "F004_R016_produccion_tiene_un_grupo_de_30_dias_por_tarea" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = (
      toset(keys(aws_cloudwatch_log_group.this)) == toset(["api", "worker", "realtime", "migrate"]) &&
      alltrue([for group in aws_cloudwatch_log_group.this : group.retention_in_days == 30]) &&
      output.log_groups["api"] == "/myplaylist/production/api"
    )
    error_message = "Cada tarea de producción tiene su grupo, con 30 días (R016)."
  }
}

run "F004_R016_todos_los_grupos_de_registros_guardan_30_dias" {
  command   = apply
  state_key = "preproduction"

  module {
    source = "./modules/observability"
  }

  variables {
    name               = "myplaylist-preproduction"
    environment        = "preproduction"
    domain             = "pre.myplaylist.200oklabs.com"
    email_identity_arn = null
  }


  assert {
    condition = (
      toset(keys(aws_cloudwatch_log_group.this)) == toset(["api", "worker", "realtime", "migrate", "mailpit", "k6"]) &&
      alltrue([for group in aws_cloudwatch_log_group.this : group.retention_in_days == 30])
    )
    error_message = "La preproducción añade los grupos de Mailpit y k6, también con 30 días (R016, T029)."
  }

  assert {
    condition     = length(aws_budgets_budget.monthly) == 0 && aws_synthetics_canary.availability.name == "myplaylist-pre"
    error_message = "La preproducción tiene su canario, pero no el presupuesto, que es de toda la cuenta (D12)."
  }

  assert {
    condition     = !anytrue([for statement in data.aws_iam_policy_document.alerts.statement : statement.sid == "RebotesYQuejasDeSes"])
    error_message = "Sin identidad de SES, el tema no admite a SES (D13)."
  }
}

run "F004_R020_contributor_insights_cuenta_401_y_403_por_ip" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = (
      jsondecode(aws_cloudwatch_contributor_insight_rule.rejections.rule_definition).LogGroupNames == ["/myplaylist/production/api"] &&
      jsondecode(aws_cloudwatch_contributor_insight_rule.rejections.rule_definition).Contribution.Keys == ["$.client_ip"] &&
      jsondecode(aws_cloudwatch_contributor_insight_rule.rejections.rule_definition).Contribution.Filters == [{ Match = "$.status", In = [401, 403] }]
    )
    error_message = "La regla cuenta los 401 y 403 de la API por client_ip (R020, D11)."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.rejections.threshold == 50 &&
      anytrue([for query in aws_cloudwatch_metric_alarm.rejections.metric_query : strcontains(query.expression, "INSIGHT_RULE_METRIC(\"myplaylist-production-rechazos-por-ip\", \"MaxContributorValue\")") && query.period == 60])
    )
    error_message = "SG6 salta con más de 50 rechazos de una misma IP en un minuto (R020)."
  }
}

run "F004_R008_el_tema_de_avisos_admite_a_ses" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = anytrue([
      for statement in data.aws_iam_policy_document.alerts.statement :
      statement.sid == "RebotesYQuejasDeSes" &&
      toset(statement.actions) == toset(["sns:Publish"]) &&
      anytrue([for principal in statement.principals : toset(principal.identifiers) == toset(["ses.amazonaws.com"])]) &&
      anytrue([for condition in statement.condition : condition.variable == "AWS:SourceArn" && toset(condition.values) == toset(["arn:aws:ses:us-east-2:955519187424:identity/myplaylist.200oklabs.com"])])
    ])
    error_message = "El tema deja publicar a SES, con la identidad del correo como origen (D14)."
  }

  assert {
    condition     = aws_sns_topic_policy.alerts.arn == aws_sns_topic.alerts.arn
    error_message = "La política se aplica al tema de avisos."
  }
}

run "F004_R021_alarma_de_cuota_de_youtube_en_8000" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.metric["r021-cuota-youtube"].metric_name == "YouTubeQuotaUsed" &&
      aws_cloudwatch_metric_alarm.metric["r021-cuota-youtube"].statistic == "Maximum" &&
      aws_cloudwatch_metric_alarm.metric["r021-cuota-youtube"].period == 60 &&
      aws_cloudwatch_metric_alarm.metric["r021-cuota-youtube"].comparison_operator == "GreaterThanOrEqualToThreshold" &&
      aws_cloudwatch_metric_alarm.metric["r021-cuota-youtube"].threshold == 8000 &&
      aws_cloudwatch_metric_alarm.metric["r021-cuota-youtube"].treat_missing_data == "notBreaching"
    )
    error_message = "R021: el total del día con Maximum, en 1 minuto, salta en 8000; un minuto sin datos no la dispara (D12)."
  }
}

run "F004_R011_el_panel_muestra_sg1_a_sg6_y_la_disponibilidad_del_mes" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = alltrue([
      for signal in ["SG1", "SG2", "SG3", "SG4", "SG5", "SG6"] :
      anytrue([for widget in jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets : startswith(widget.properties.title, signal)])
    ])
    error_message = "El panel tiene al menos una gráfica por señal (R011)."
  }

  assert {
    condition = (
      jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets[0].properties.view == "singleValue" &&
      jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets[0].properties.metrics == [["CloudWatchSynthetics", "SuccessPercent", "CanaryName", "myplaylist-prod"]] &&
      jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets[0].properties.stat == "Average" &&
      jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets[0].properties.setPeriodToTimeRange &&
      !can(jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets[0].properties.start) &&
      jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).start == "-P30D"
    )
    error_message = "Arriba, la disponibilidad: la media de SuccessPercent del canario en todo el rango que se mira (R013)."
  }

  assert {
    condition = alltrue([
      for signal in ["SG1 · búsquedas no disponibles (%)", "SG2 · 5xx del ALB (%)", "SG5 · canciones fallidas (%)"] :
      anytrue([
        for widget in jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets :
        widget.properties.title == signal && anytrue([for line in widget.properties.metrics : try(line[0].expression, "") == "100 * FILL(m1, 0) / m2"])
      ])
    ])
    error_message = "El panel muestra las tasas que comparan los umbrales de SG1, SG2 y SG5, no solo los recuentos (R011)."
  }

  assert {
    condition = anytrue([
      for widget in jsondecode(aws_cloudwatch_dashboard.this.dashboard_body).widgets :
      widget.type == "log" && strcontains(widget.properties.query, "by client_ip") && strcontains(widget.properties.query, "/myplaylist/production/api")
    ]) && strcontains(aws_cloudwatch_metric_alarm.rejections.alarm_description, "SG6 · rechazos por IP")
    error_message = "El aviso de SG6 remite a la tabla del panel con las IP que más rechazos tienen (R020)."
  }
}

run "presupuesto_con_aviso_por_correo" {
  command = apply

  module {
    source = "./modules/observability"
  }

  assert {
    condition = (
      length(aws_budgets_budget.monthly) == 1 &&
      aws_budgets_budget.monthly[0].limit_amount == "510" &&
      aws_budgets_budget.monthly[0].time_unit == "MONTHLY" &&
      anytrue([
        for notification in aws_budgets_budget.monthly[0].notification :
        notification.notification_type == "FORECASTED" &&
        notification.threshold == 120 &&
        notification.threshold_type == "PERCENTAGE" &&
        notification.subscriber_email_addresses == toset(["operacion@200oklabs.com"])
      ])
    )
    error_message = "Un correo cuando el gasto previsto del mes supera en un 20 % el estimado del plan (D12)."
  }
}

run "F004_R013_un_entorno_nuevo_no_avisa_de_sg3_hasta_que_atiende" {
  command   = apply
  state_key = "nuevo"

  module {
    source = "./modules/observability"
  }

  variables {
    canary_enabled = false
  }

  assert {
    condition     = !aws_synthetics_canary.availability.start_canary
    error_message = "Hasta el primer despliegue, el canario no corre: el establecimiento de prueba aún no existe (T017, T018)."
  }

  assert {
    condition = alltrue([
      for key in ["sg3-canario", "sg3-tareas-sanas-api", "sg3-tareas-sanas-realtime"] :
      !aws_cloudwatch_metric_alarm.metric[key].actions_enabled
    ]) && aws_cloudwatch_metric_alarm.metric["sg1-busqueda-p95"].actions_enabled
    error_message = "Y las alarmas de SG3 no avisan, porque sin canario ni tareas estarían en ALARM sin motivo; las demás, sí."
  }
}
