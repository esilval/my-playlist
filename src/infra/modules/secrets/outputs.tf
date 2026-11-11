output "secret_arns" {
  description = "ARN de cada secreto, por nombre: lo que las definiciones de tarea ponen en `secrets` (D6)."
  value       = { for key, secret in aws_secretsmanager_secret.this : key => secret.arn }
}

output "secret_length" {
  description = "Longitud de los secretos generados (D6)."
  value       = local.secret_length
}
