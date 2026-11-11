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
