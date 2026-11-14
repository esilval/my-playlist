output "state_bucket" {
  description = "Bucket del estado: lo usan los entornos y la migración del estado del arranque."
  value       = aws_s3_bucket.state.bucket
}

output "name_servers" {
  description = "Servidores de nombres que hay que poner en el registrador de 200oklabs.com (D17)."
  value       = aws_route53_zone.domain.name_servers
}

output "zone_id" {
  description = "Zona de Route 53 del dominio."
  value       = aws_route53_zone.domain.zone_id
}

output "deploy_role_arn" {
  description = "Rol que asumen los flujos de despliegue (secreto AWS_DEPLOY_ROLE_ARN de los entornos de GitHub)."
  value       = aws_iam_role.deploy.arn
}

output "github_oidc_provider_arn" {
  description = "Proveedor OIDC de GitHub que usan los roles: el que hay que crear si no lo crea este arranque (D18)."
  value       = local.github_oidc_provider_arn
}
