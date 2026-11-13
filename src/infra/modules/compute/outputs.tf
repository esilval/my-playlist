output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_names" {
  description = "Los servicios, en el orden en que los actualiza el despliegue (D9)."
  value       = ["realtime", "api", "worker"]
}

output "migration_task_definition" {
  description = "La familia de la tarea de migración, que lanza el flujo de despliegue (D8)."
  value       = aws_ecs_task_definition.this["migrate"].family
}

output "repository_urls" {
  value = { for key, repository in aws_ecr_repository.this : key => repository.repository_url }
}

output "origin_domain" {
  description = "El nombre con que CloudFront llega al ALB por HTTPS (D1)."
  value       = aws_route53_record.origin.fqdn
}

output "origin_header_name" {
  description = "La cabecera que el ALB exige y CloudFront pone (D1)."
  value       = local.origin_header_name
}

output "alb_arn_suffix" {
  description = "Para las métricas y alarmas del ALB (D12)."
  value       = aws_lb.this.arn_suffix
}

output "load_test_task_definition" {
  description = "Solo en preproducción: la familia de la tarea de k6, que lanza preproduction.yml (D13, T019)."
  value       = local.preproduction ? aws_ecs_task_definition.tools["k6"].family : null
}

output "mailpit_ports" {
  description = "Los puertos que el módulo de red abre entre las tareas en preproducción (D13)."
  value       = local.preproduction ? local.mailpit_ports : {}
}

output "target_group_arn_suffixes" {
  description = "El sufijo del ARN de cada grupo de destino, para las alarmas de tareas sanas (D12, ADR-0020)."
  value       = { for key, group in aws_lb_target_group.this : key => group.arn_suffix }
}
