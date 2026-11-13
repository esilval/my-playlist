# Una alarma por umbral de cada señal (D12, ADR-0020), todas en us-east-2. Cada una avisa
# al tema al entrar en ALARM y al volver a OK (R012). Ninguna usa métricas de Route 53 ni de
# CloudFront: solo existen en us-east-1, donde la organización deniega CloudWatch (D18).
locals {
  search_route = "/api/public/establishments/{code}/search"
  music_route  = "/api/public/establishments/{code}/music"

  # Las alarmas de una sola métrica.
  metric_alarms = {
    "sg1-busqueda-p95" = {
      description = "SG1: la búsqueda tarda más de 2 s en el p95, 5 minutos seguidos"
      namespace   = local.namespace
      metric      = "RequestLatency"
      dimensions  = { Route = local.search_route }
      statistic   = null
      percentile  = "p95"
      period      = 60
      evaluations = 5
      operator    = "GreaterThanThreshold"
      threshold   = 2000
      missing     = "notBreaching"
    }
    "sg2-cpu-api" = {
      description = "SG2: la CPU de la API pasa del 80 % durante 10 minutos"
      namespace   = "AWS/ECS"
      metric      = "CPUUtilization"
      dimensions  = { ClusterName = var.cluster_name, ServiceName = "api" }
      statistic   = "Average"
      percentile  = null
      period      = 300
      evaluations = 2
      operator    = "GreaterThanThreshold"
      threshold   = 80
      missing     = "notBreaching"
    }
    "sg2-conexiones-rds" = {
      description = "SG2: las conexiones a RDS pasan del 80 % de max_connections"
      namespace   = "AWS/RDS"
      metric      = "DatabaseConnections"
      dimensions  = { DBInstanceIdentifier = var.name }
      statistic   = "Maximum"
      percentile  = null
      period      = 300
      evaluations = 1
      operator    = "GreaterThanThreshold"
      threshold   = floor(var.database_max_connections * 0.8)
      missing     = "notBreaching"
    }
    # Sin datos cuenta como fallo: un canario que no corre no prueba que el servicio
    # responda (ADR-0020).
    "sg3-canario" = {
      description = "SG3: el canario de disponibilidad falla durante 5 minutos"
      namespace   = "CloudWatchSynthetics"
      metric      = "SuccessPercent"
      dimensions  = { CanaryName = aws_synthetics_canary.availability.name }
      statistic   = "Average"
      percentile  = null
      period      = 60
      evaluations = 5
      operator    = "LessThanThreshold"
      threshold   = 100
      missing     = "breaching"
      # Parado el canario, no hay datos y la alarma estaría en ALARM: no avisa hasta que el
      # entorno atiende (canary_enabled).
      availability = true
    }
    "sg3-tareas-sanas-api" = {
      description  = "SG3: la API se queda sin tareas sanas en el ALB"
      namespace    = "AWS/ApplicationELB"
      metric       = "HealthyHostCount"
      dimensions   = { TargetGroup = var.target_group_arn_suffixes["api"], LoadBalancer = var.alb_arn_suffix }
      statistic    = "Minimum"
      percentile   = null
      period       = 60
      evaluations  = 2
      operator     = "LessThanThreshold"
      threshold    = 1
      missing      = "breaching"
      availability = true
    }
    "sg3-tareas-sanas-realtime" = {
      description  = "SG3: el tiempo real se queda sin tareas sanas en el ALB"
      namespace    = "AWS/ApplicationELB"
      metric       = "HealthyHostCount"
      dimensions   = { TargetGroup = var.target_group_arn_suffixes["realtime"], LoadBalancer = var.alb_arn_suffix }
      statistic    = "Minimum"
      percentile   = null
      period       = 60
      evaluations  = 2
      operator     = "LessThanThreshold"
      threshold    = 1
      missing      = "breaching"
      availability = true
    }
    "sg4-musica-p95" = {
      description = "SG4: el estado de la música tarda más de 1 s en el p95"
      namespace   = local.namespace
      metric      = "RequestLatency"
      dimensions  = { Route = local.music_route }
      statistic   = null
      percentile  = "p95"
      period      = 300
      evaluations = 1
      operator    = "GreaterThanThreshold"
      threshold   = 1000
      missing     = "notBreaching"
    }
    "sg4-reenvio-p95" = {
      description = "SG4: el tiempo real tarda más de 1 s en reenviar un evento, en el p95"
      namespace   = local.namespace
      metric      = "RelayDelay"
      dimensions  = { Service = "realtime" }
      statistic   = null
      percentile  = "p95"
      period      = 300
      evaluations = 1
      operator    = "GreaterThanThreshold"
      threshold   = 1000
      missing     = "notBreaching"
    }
    "sg5-hueco-p99" = {
      description = "SG5: el hueco entre canciones pasa de 3 s en el p99, en una hora"
      namespace   = local.namespace
      metric      = "TrackGap"
      dimensions  = {}
      statistic   = null
      percentile  = "p99"
      period      = 3600
      evaluations = 1
      operator    = "GreaterThanThreshold"
      threshold   = 3000
      missing     = "notBreaching"
    }
    # Un total del día, no una cuenta: con Maximum, varias llamadas en un minuto no suman
    # totales (D12). Un minuto sin llamadas no la dispara.
    "r021-cuota-youtube" = {
      description = "R021: la cuota de YouTube del día llega a 8000 unidades"
      namespace   = local.namespace
      metric      = "YouTubeQuotaUsed"
      dimensions  = {}
      statistic   = "Maximum"
      percentile  = null
      period      = 60
      evaluations = 1
      operator    = "GreaterThanOrEqualToThreshold"
      threshold   = 8000
      missing     = "notBreaching"
    }
  }

  # Las alarmas sobre una proporción entre dos métricas, en %: e = 100 * m1 / m2.
  ratio_alarms = {
    "sg1-busqueda-no-disponible" = {
      description = "SG1: más del 5 % de las búsquedas responden 503 search_unavailable, en 5 minutos"
      period      = 300
      threshold   = 5
      m1          = { namespace = local.namespace, metric = "SearchUnavailable", dimensions = {} }
      m2          = { namespace = local.namespace, metric = "RequestLatency", dimensions = { Route = local.search_route }, stat = "SampleCount" }
    }
    "sg2-5xx-alb" = {
      description = "SG2: más del 0,1 % de las peticiones al ALB acaban en 5xx, en 5 minutos"
      period      = 300
      threshold   = 0.1
      m1          = { namespace = "AWS/ApplicationELB", metric = "HTTPCode_Target_5XX_Count", dimensions = { LoadBalancer = var.alb_arn_suffix } }
      m2          = { namespace = "AWS/ApplicationELB", metric = "RequestCount", dimensions = { LoadBalancer = var.alb_arn_suffix }, stat = "Sum" }
    }
    "sg5-fallos-reproduccion" = {
      description = "SG5: más del 2 % de las canciones fallan, en una hora"
      period      = 3600
      threshold   = 2
      m1          = { namespace = local.namespace, metric = "TrackFailed", dimensions = {} }
      m2          = { namespace = local.namespace, metric = "TrackStarted", dimensions = {}, stat = "Sum" }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "metric" {
  for_each = local.metric_alarms

  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  statistic           = each.value.statistic
  extended_statistic  = each.value.percentile
  period              = each.value.period
  evaluation_periods  = each.value.evaluations
  datapoints_to_alarm = each.value.evaluations
  comparison_operator = each.value.operator
  threshold           = each.value.threshold
  treat_missing_data  = each.value.missing
  actions_enabled     = lookup(each.value, "availability", false) ? var.canary_enabled : true
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ratio" {
  for_each = local.ratio_alarms

  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = each.value.description
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = each.value.threshold
  # Sin tráfico no hay proporción: no salta.
  treat_missing_data = "notBreaching"
  alarm_actions      = [aws_sns_topic.alerts.arn]
  ok_actions         = [aws_sns_topic.alerts.arn]

  metric_query {
    id          = "e"
    expression  = "100 * FILL(m1, 0) / m2"
    label       = each.key
    return_data = true
  }

  metric_query {
    id = "m1"

    metric {
      namespace   = each.value.m1.namespace
      metric_name = each.value.m1.metric
      dimensions  = each.value.m1.dimensions
      period      = each.value.period
      stat        = "Sum"
    }
  }

  metric_query {
    id = "m2"

    metric {
      namespace   = each.value.m2.namespace
      metric_name = each.value.m2.metric
      dimensions  = each.value.m2.dimensions
      period      = each.value.period
      stat        = each.value.m2.stat
    }
  }
}

# SG6 (R020): más de 50 rechazos desde una misma IP en un minuto.
resource "aws_cloudwatch_metric_alarm" "rejections" {
  alarm_name = "${var.name}-sg6-rechazos-por-ip"
  # El aviso lleva la cifra, no la IP: la tabla «SG6 · rechazos por IP» del panel dice cuál
  # es (R020).
  alarm_description   = "SG6: más de 50 respuestas 401 o 403 a una misma IP en un minuto. La IP está en el panel ${var.name}, en «SG6 · rechazos por IP»."
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 50
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  metric_query {
    id          = "e"
    expression  = "INSIGHT_RULE_METRIC(\"${aws_cloudwatch_contributor_insight_rule.rejections.rule_name}\", \"MaxContributorValue\")"
    period      = 60
    label       = "rechazos de la IP con más"
    return_data = true
  }
}
