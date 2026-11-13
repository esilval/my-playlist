# Los rechazos por IP (SG6, R020): cuenta los 401 y 403 de los registros de la API por
# `client_ip`, que la API solo escribe en esas respuestas (D11).
resource "aws_cloudwatch_contributor_insight_rule" "rejections" {
  rule_name  = "${var.name}-rechazos-por-ip"
  rule_state = "ENABLED"
  rule_definition = jsonencode({
    Schema        = { Name = "CloudWatchLogRule", Version = 1 }
    LogGroupNames = [aws_cloudwatch_log_group.this["api"].name]
    LogFormat     = "JSON"
    Contribution = {
      Keys    = ["$.client_ip"]
      Filters = [{ Match = "$.status", In = [401, 403] }]
    }
    AggregateOn = "Count"
  })
}
