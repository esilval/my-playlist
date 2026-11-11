output "database_host" {
  description = "Anfitrión de PostgreSQL: DATABASE_HOST de las tareas (D6)."
  value       = aws_db_instance.postgres.address
}

output "database_port" {
  value = aws_db_instance.postgres.port
}

output "database_name" {
  value = aws_db_instance.postgres.db_name
}

output "master_user_secret_arn" {
  description = "El secreto del usuario maestro que gestiona RDS: solo para la tarea de migración (D5, D8)."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "redis_host" {
  description = "Anfitrión primario de Redis: REDIS_HOST de las tareas (D6)."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "redis_port" {
  value = aws_elasticache_replication_group.redis.port
}
