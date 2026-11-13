output "log_groups" {
  description = "Grupo de registros de cada tarea, para el módulo de cómputo (T013, T029)."
  value       = { for task, group in aws_cloudwatch_log_group.this : task => group.name }
}

output "alerts_topic_arn" {
  description = "El tema de avisos: lo usan las alarmas y, en producción, los rebotes y quejas de SES (D12, D14)."
  value       = aws_sns_topic.alerts.arn
  # El módulo de correo configura los avisos de SES con este tema: espera a que su política
  # deje publicar a SES.
  depends_on = [aws_sns_topic_policy.alerts]
}

output "canary_name" {
  value = aws_synthetics_canary.availability.name
}
