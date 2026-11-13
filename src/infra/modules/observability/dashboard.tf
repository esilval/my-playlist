# El panel (R011, R013): una gráfica por señal, con las tasas que comparan los umbrales, y
# arriba la disponibilidad: la media de SuccessPercent del canario en el periodo que se
# mire. Por defecto, los últimos 30 días; para el mes natural, se elige ese rango en el
# panel.
locals {
  metric_widgets = [
    { title = "SG1 · búsqueda p95 (ms)", metrics = [[local.namespace, "RequestLatency", "Route", local.search_route, { stat = "p95" }]] },
    {
      title = "SG1 · búsquedas no disponibles (%)"
      metrics = [
        [{ expression = "100 * FILL(m1, 0) / m2", label = "% no disponibles", id = "e1" }],
        [local.namespace, "SearchUnavailable", { stat = "Sum", id = "m1", visible = false }],
        [local.namespace, "RequestLatency", "Route", local.search_route, { stat = "SampleCount", id = "m2", visible = false }],
      ]
    },
    {
      title = "SG2 · 5xx del ALB (%)"
      metrics = [
        [{ expression = "100 * FILL(m1, 0) / m2", label = "% 5xx", id = "e1" }],
        ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", var.alb_arn_suffix, { stat = "Sum", id = "m1", visible = false }],
        ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", var.alb_arn_suffix, { stat = "Sum", id = "m2", visible = false }],
      ]
    },
    { title = "SG2 · CPU de la API (%)", metrics = [["AWS/ECS", "CPUUtilization", "ClusterName", var.cluster_name, "ServiceName", "api"]] },
    { title = "SG2 · conexiones a RDS", metrics = [["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", var.name, { stat = "Maximum" }]] },
    { title = "SG3 · canario (% de éxito)", metrics = [["CloudWatchSynthetics", "SuccessPercent", "CanaryName", aws_synthetics_canary.availability.name]] },
    { title = "SG4 · estado de la música p95 (ms)", metrics = [[local.namespace, "RequestLatency", "Route", local.music_route, { stat = "p95" }]] },
    { title = "SG4 · reenvío del tiempo real p95 (ms)", metrics = [[local.namespace, "RelayDelay", "Service", "realtime", { stat = "p95" }]] },
    { title = "SG4 · conexiones abiertas", metrics = [[local.namespace, "Connections", "Service", "realtime", { stat = "Sum" }]] },
    {
      title = "SG5 · canciones fallidas (%)"
      metrics = [
        [{ expression = "100 * FILL(m1, 0) / m2", label = "% fallidas", id = "e1" }],
        [local.namespace, "TrackFailed", { stat = "Sum", id = "m1", visible = false }],
        [local.namespace, "TrackStarted", { stat = "Sum", id = "m2", visible = false }],
      ]
    },
    { title = "SG5 · hueco entre canciones p99 (ms)", metrics = [[local.namespace, "TrackGap", { stat = "p99" }]] },
    { title = "R021 · cuota de YouTube del día", metrics = [[local.namespace, "YouTubeQuotaUsed", { stat = "Maximum" }]] },
  ]
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = var.name
  dashboard_body = jsonencode({
    # El panel abre con los últimos 30 días; el selector de rango lo cambia para todos los
    # widgets, también el de disponibilidad.
    start = "-P30D"
    widgets = concat(
      [
        {
          type   = "metric"
          x      = 0
          y      = 0
          width  = 24
          height = 4
          properties = {
            title  = "SG3 · disponibilidad en el periodo del panel (%)"
            region = "us-east-2"
            view   = "singleValue"
            stat   = "Average"
            # Un solo valor para todo el rango que se mira, no el del último periodo.
            setPeriodToTimeRange = true
            metrics              = [["CloudWatchSynthetics", "SuccessPercent", "CanaryName", aws_synthetics_canary.availability.name]]
          }
        },
        {
          type   = "log"
          x      = 0
          y      = 4
          width  = 24
          height = 6
          properties = {
            title  = "SG6 · rechazos por IP"
            region = "us-east-2"
            query  = "SOURCE '${aws_cloudwatch_log_group.this["api"].name}' | filter status in [401, 403] | stats count(*) as rechazos by client_ip | sort rechazos desc | limit 10"
          }
        },
      ],
      [
        for index, widget in local.metric_widgets : {
          type   = "metric"
          x      = (index % 2) * 12
          y      = 10 + floor(index / 2) * 6
          width  = 12
          height = 6
          properties = {
            title   = widget.title
            region  = "us-east-2"
            period  = 60
            metrics = widget.metrics
          }
        }
      ],
    )
  })
}
